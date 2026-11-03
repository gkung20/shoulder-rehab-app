"""One analysis pipeline for camera, Streamlit and recorded video.

FrameAnalysis is a presentation-neutral contract: a future avatar can consume
the same observed joints, phase, target and cue without influencing assessment.
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import math
from typing import Optional
from uuid import uuid4

from src.calibration import CalibrationManager
from src.config import ExerciseConfig
from src.geometry import (
    PoseLandmarkIndex as I, are_landmarks_visible, to_measurement_space,
    calculate_abduction_angle, calculate_elbow_angle, calculate_trunk_lean,
    calculate_shoulder_shrug, calculate_anterior_drift_angle, calculate_distance_2d,
    calculate_shoulder_reference_angle,
)
from src.rules_engine import RulesEngine, LiveFeedback, FeedbackLevel, RepetitionEvaluation
from src.smoothing import MultiMetricSmoother
from src.state_machine import RepetitionStateMachine, ExercisePhase


@dataclass
class FrameAnalysis:
    timestamp_sec: float
    landmarks: list = field(default_factory=list)  # Original normalized detector output.
    metrics: dict = field(default_factory=dict)    # Fresh observations only; None = unavailable.
    status: str = "RECHERCHE"
    cue: LiveFeedback = field(default_factory=lambda: LiveFeedback("Placez-vous face a la camera", FeedbackLevel.INFO))
    calibration_progress: Optional[tuple] = None
    phase: ExercisePhase = ExercisePhase.REST
    hold_seconds: float = 0.0
    new_evaluation: Optional[RepetitionEvaluation] = None
    missing_metrics: tuple = ()
    angle_reference: str = "torso"


def repetition_log(evaluation):
    """CSV/JSON values keep unknowns blank and include the acquisition context."""
    m = evaluation.metrics
    return {
        "rep_index": m.rep_index, "bras": m.arm.upper(), "statut": evaluation.status_label,
        "angle_max_deg": round(m.peak_abduction_deg, 1),
        "montee_s": round(m.concentric_duration_sec, 2), "maintien_s": round(m.hold_duration_sec, 2),
        "descente_s": round(m.eccentric_duration_sec, 2),
        "inclinaison_max_deg": None if "tronc" in m.missing_metrics else round(m.max_trunk_lean_deg, 1),
        "haussement_max_pct": None if "epaule" in m.missing_metrics else round(m.max_shrug_ratio * 100, 1),
        "coude_min_deg": None if "coude" in m.missing_metrics else round(m.min_elbow_angle_deg, 1),
        "derive_max_deg": None if "derive 3D" in m.missing_metrics else round(m.max_drift_deg, 1),
        "fluidite_pct": m.fluidity_score_pct,
        "reference_angle": m.angle_reference,
        "remarques": "; ".join(evaluation.reasons) if evaluation.reasons else "Seuils du prototype respectes",
        "session_id": m.session_id, "configuration": m.config_snapshot,
        "calibration": m.calibration_snapshot, "mesures_manquantes": list(m.missing_metrics),
    }


class SessionProcessor:
    def __init__(self, config=None, arm="right", rules_engine=None):
        self.config = config or ExerciseConfig.from_yaml()
        self.arm = arm
        self.rules_engine = rules_engine or RulesEngine(self.config)
        self.rules_engine.config = self.config
        self.session_id = uuid4().hex
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.smoother = MultiMetricSmoother(self.config.filtering.ema_alpha)
        self.calibrator = CalibrationManager(
            self.config.calibration.duration_sec, self.config.calibration.max_variance_ratio,
            self.config.filtering.min_landmark_visibility, self.config.abduction.rest_threshold_deg,
            self.config.compensation.max_trunk_lean_deg,
        )
        a = self.config.abduction
        self.state_machine = RepetitionStateMachine(a.rest_threshold_deg, a.rising_start_deg,
            a.target_min_deg, a.target_max_deg, self.config.timing.min_hold_time_sec, arm)
        self.last_evaluation = None
        self.model_info = {}
        self._last_frame_time = None
        self._last_valid_time = None
        self._started = False
        self._need_rest = True
        self.interrupted_attempts = 0
        self.frames_total = 0
        self.frames_tracked = 0

    def recalibrate(self, arm=None, timestamp_sec=None):
        if timestamp_sec is None:
            timestamp_sec = self._last_frame_time if self._last_frame_time is not None else 0.0
        self.finish()
        self.arm = arm or self.arm
        self.state_machine.set_arm(self.arm)
        self.smoother.reset_all()
        self._last_valid_time = None
        self._need_rest = True
        self.last_evaluation = None
        self.calibrator.start(self.arm, timestamp_sec)
        self._calibration_id = uuid4().hex
        self._started = True

    def _pause(self, now):
        self.state_machine.pause()
        if self._last_valid_time is not None and now - self._last_valid_time > self.config.filtering.tracking_reset_sec:
            if self.state_machine.current_phase != ExercisePhase.REST:
                self.interrupted_attempts += 1
                self.rules_engine.session.interrupted_attempts += 1
            self.state_machine.reset_current_rep()
            self.smoother.reset_all()
            self._need_rest = True

    def finish(self):
        """Record a stopped, unfinished attempt without fabricating a completed rep."""
        if self.state_machine.current_phase != ExercisePhase.REST:
            self.interrupted_attempts += 1
            self.rules_engine.session.interrupted_attempts += 1
        self.state_machine.reset_current_rep()
        self._need_rest = True

    def process(self, landmarks, world_landmarks, width, height, timestamp_sec):
        now = float(timestamp_sec)
        if not math.isfinite(now) or (self._last_frame_time is not None and now <= self._last_frame_time):
            raise ValueError("Frame timestamps must be finite and strictly increasing")
        dt = now - self._last_frame_time if self._last_frame_time is not None else 1 / 30
        self._last_frame_time = now
        self.frames_total += 1
        if not self._started:
            self.recalibrate(timestamp_sec=now)
        if dt > self.config.filtering.tracking_reset_sec:
            self._pause(now)
            if self.calibrator.is_calibrating:
                self.calibrator.start(self.arm, now)
        frame = FrameAnalysis(now, landmarks or [], metrics={k: None for k in ("abduction", "lean", "shrug", "elbow", "drift")})
        if not landmarks or len(landmarks) < 33:
            if self.calibrator.is_calibrating:
                self.calibrator.update(None, self.arm, now)
            self._pause(now)
            frame.status = "SUIVI PERDU"
            frame.cue = LiveFeedback("Aucun squelette detecte : ajustez le cadrage des epaules", FeedbackLevel.INFO)
            return frame

        pts = to_measurement_space(landmarks, width, height)
        sh, hip, el, wr, ear = ((I.LEFT_SHOULDER, I.LEFT_HIP, I.LEFT_ELBOW, I.LEFT_WRIST, I.LEFT_EAR)
            if self.arm == "left" else (I.RIGHT_SHOULDER, I.RIGHT_HIP, I.RIGHT_ELBOW, I.RIGHT_WRIST, I.RIGHT_EAR))
        torso = (I.LEFT_SHOULDER, I.RIGHT_SHOULDER, I.LEFT_HIP, I.RIGHT_HIP)
        min_v = self.config.filtering.min_landmark_visibility

        def visible(indices):
            return (are_landmarks_visible([pts[i] for i in indices], min_v)
                and all(0 <= landmarks[i].x <= 1 and 0 <= landmarks[i].y <= 1 for i in indices))

        shoulders_ok = visible((I.LEFT_SHOULDER, I.RIGHT_SHOULDER)) and calculate_distance_2d(pts[I.LEFT_SHOULDER], pts[I.RIGHT_SHOULDER]) > .05
        elbow_ok = visible((sh, el)) and calculate_distance_2d(pts[sh], pts[el]) > .02
        torso_ok = visible(torso) and calculate_distance_2d(pts[sh], pts[hip]) > .1
        if self.calibrator.is_calibrating:
            # Invisible or off-screen optional landmarks must not be used as observations.
            calibration_pts = [p if visible((i,)) else type(p)(p.x, p.y, 0.) for i,p in enumerate(pts)]
            self.calibrator.update(calibration_pts if shoulders_ok else None, self.arm, now)
            frame.calibration_progress = self.calibrator.get_progress() if self.calibrator.is_calibrating else None
        baseline = self.calibrator.calibrated_data
        if baseline.is_calibrated and baseline.reference_mode == "torso" and not torso_ok:
            # Changing angle definitions in a movement would corrupt its peak/timing.
            self.finish()
            self.smoother.reset_all()
            baseline.reference_mode = "shoulders"
        mode = baseline.reference_mode if baseline.is_calibrated else ("torso" if torso_ok else "shoulders")
        frame.angle_reference = mode
        raw = frame.metrics.copy()
        if elbow_ok and mode == "torso" and torso_ok:
            raw["abduction"] = calculate_abduction_angle(pts[sh], pts[hip], pts[el])
        elif elbow_ok and shoulders_ok and mode == "shoulders":
            raw["abduction"] = calculate_shoulder_reference_angle(pts[I.LEFT_SHOULDER], pts[I.RIGHT_SHOULDER], pts[sh], pts[el])
        angle_ok = raw["abduction"] is not None
        if visible((sh, el, wr)) and calculate_distance_2d(pts[el], pts[wr]) > 0.02:
            raw["elbow"] = calculate_elbow_angle(pts[sh], pts[el], pts[wr])
        if visible(torso) and math.hypot((pts[I.LEFT_SHOULDER].x + pts[I.RIGHT_SHOULDER].x - pts[I.LEFT_HIP].x - pts[I.RIGHT_HIP].x) / 2,
                (pts[I.LEFT_SHOULDER].y + pts[I.RIGHT_SHOULDER].y - pts[I.LEFT_HIP].y - pts[I.RIGHT_HIP].y) / 2) > .1:
            raw["lean"] = calculate_trunk_lean(*(pts[i] for i in torso))
        if baseline.is_calibrated and baseline.baseline_ear_shoulder_dist is not None and visible((ear, sh)):
            raw["shrug"] = calculate_shoulder_shrug(pts[ear], pts[sh], baseline.baseline_ear_shoulder_dist, baseline.baseline_shoulder_width)
        if world_landmarks and len(world_landmarks) >= 33:
            other_sh, other_hip = ((I.RIGHT_SHOULDER, I.RIGHT_HIP) if self.arm == "left" else (I.LEFT_SHOULDER, I.LEFT_HIP))
            wpts = [world_landmarks[i] for i in (sh, other_sh, hip, other_hip, el)]
            # World hips inferred outside the image do not establish a visible torso.
            if torso_ok and elbow_ok and are_landmarks_visible(wpts, min_v):
                lateral = math.dist((wpts[0].x,wpts[0].y,wpts[0].z), (wpts[1].x,wpts[1].y,wpts[1].z))
                arm_length = math.dist((wpts[0].x,wpts[0].y,wpts[0].z), (wpts[4].x,wpts[4].y,wpts[4].z))
                if lateral > .05 and arm_length > .05:
                    raw["drift"] = calculate_anterior_drift_angle(*wpts)
                    if abs(wpts[0].z - wpts[1].z) / lateral > .5:
                        angle_ok = False
        if baseline.is_calibrated and shoulders_ok:
            width_ratio = calculate_distance_2d(pts[I.LEFT_SHOULDER], pts[I.RIGHT_SHOULDER]) / baseline.baseline_shoulder_width
            if not .65 <= width_ratio <= 1.4:
                angle_ok = False
        # A time-based EMA has the same response at different frame rates.
        alpha = 1 - (1 - self.config.filtering.ema_alpha) ** (min(dt, .1) * 30)
        for name, value in raw.items():
            smoother = self.smoother.get_smoother(name)
            smoother.alpha = alpha
            frame.metrics[name] = smoother.update(value) if value is not None else None

        if not baseline.is_calibrated:
            frame.status = "CALIBRATION"
            frame.cue = LiveFeedback(self.calibrator.status_message, FeedbackLevel.INFO)
            return frame
        if not angle_ok:
            frame.metrics["abduction"] = None
            self._pause(now)
            frame.status = "EPAULES PRETES" if shoulders_ok and not elbow_ok else "POSITION A AJUSTER"
            message = ("Epaules pretes : montrez le coude du bras actif pour compter" if shoulders_ok and not elbow_ok
                       else "Montrez les deux epaules et le coude du bras actif")
            frame.cue = LiveFeedback(message, FeedbackLevel.INFO)
            return frame
        self.frames_tracked += 1
        self._last_valid_time = now
        angle = frame.metrics["abduction"]
        if self._need_rest:
            if angle > self.config.abduction.rest_threshold_deg:
                frame.status = "REPOS REQUIS"
                frame.cue = LiveFeedback("Baissez le bras avant de commencer une repetition", FeedbackLevel.INFO)
                return frame
            self._need_rest = False
        missing = tuple(label for name, label in (("lean", "tronc"), ("shrug", "epaule"), ("elbow", "coude"), ("drift", "derive 3D")) if frame.metrics[name] is None)
        if mode == "shoulders":
            missing += ("angle estime depuis les epaules",)
        frame.missing_metrics = missing
        m = frame.metrics
        rep = self.state_machine.update(angle, now, m["lean"], m["shrug"], m["elbow"], m["drift"], missing)
        frame.phase = self.state_machine.current_phase
        frame.hold_seconds = self.state_machine.hold_duration_sec
        frame.status = "CADRAGE SERRE" if mode == "shoulders" else "SUIVI ACTIF" if not missing else "MESURES PARTIELLES"
        frame.cue = self.rules_engine.evaluate_live_frame(angle, m["lean"], m["shrug"], m["elbow"], frame.phase, m["drift"])
        if frame.phase == ExercisePhase.HOLD and frame.hold_seconds >= self.config.timing.min_hold_time_sec and frame.cue.level != FeedbackLevel.WARNING:
            frame.cue = LiveFeedback("Bien ! Redescendez doucement jusqu'au repos", FeedbackLevel.INFO)
        if rep:
            # Global numbering survives recalibration and arm changes within this processor.
            rep.rep_index = self.rules_engine.session.total_repetitions + 1
            rep.angle_reference = mode
            rep.session_id = self.session_id
            rep.config_snapshot = {"schema_version": 1, "started_at": self.started_at,
                "model": self.model_info.copy(), "captured_frame": {"width": width, "height": height}, **asdict(self.config)}
            rep.calibration_snapshot = {"calibration_id": self._calibration_id, **asdict(baseline)}
            frame.new_evaluation = self.rules_engine.evaluate_repetition(rep)
            self.last_evaluation = frame.new_evaluation
        return frame
