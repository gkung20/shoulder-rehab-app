"""One analysis pipeline for camera, Streamlit and recorded video.

FrameAnalysis is a presentation-neutral contract: the avatar can consume
the same observed joints, phase, target and cue without influencing assessment.
"""
from dataclasses import asdict, dataclass, field, replace
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
from src.cues import Cue
from src.exercises import get_exercise
from src.rules_engine import RulesEngine, LiveFeedback, FeedbackLevel, RepetitionEvaluation, cue_feedback
from src.smoothing import MultiMetricSmoother
from src.state_machine import RepetitionStateMachine, ExercisePhase


@dataclass
class FrameAnalysis:
    timestamp_sec: float
    landmarks: list = field(default_factory=list)  # Original normalized detector output.
    metrics: dict = field(default_factory=dict)    # Fresh observations only; None = unavailable.
    status: str = "RECHERCHE"
    cue: LiveFeedback = field(default_factory=lambda: cue_feedback(Cue.PLACE_FACING))
    calibration_progress: Optional[tuple] = None
    phase: ExercisePhase = ExercisePhase.REST
    hold_seconds: float = 0.0
    new_evaluation: Optional[RepetitionEvaluation] = None
    missing_metrics: tuple = ()
    angle_reference: str = "torso"
    world_landmarks: list = field(default_factory=list)  # Fresh estimated depth, optional for rendering.
    hands: dict = field(default_factory=dict)  # Independent hand model; display only.


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
        "angle_max_gauche_deg": m.peaks.get("left"), "angle_max_droit_deg": m.peaks.get("right"),
        "ecart_bras_max_deg": None if m.max_asymmetry_deg is None else round(m.max_asymmetry_deg, 1),
        "remarques": "; ".join(evaluation.reasons) if evaluation.reasons else "Seuils du prototype respectes",
        "session_id": m.session_id, "configuration": m.config_snapshot,
        "calibration": m.calibration_snapshot, "mesures_manquantes": list(m.missing_metrics),
    }


CALIBRATION_MARGIN_DEG = 15.  # calibration accepts a resting arm up to target min - 15 deg
REST_MARGIN_DEG = 8.          # rest threshold = resting angle + 8 deg
RISE_MARGIN_DEG = 7.          # rise threshold = rest threshold + 7 deg
TARGET_GAP_DEG = 10.          # the rise threshold stays at least 10 deg below the target
SEATED_TILT_ALLOWANCE_DEG = 5.  # seated: shoulder-line tilt allowed before it counts as leaning


# Landmarks of each arm: shoulder, hip, elbow, wrist, ear.
SIDES = {"left": (I.LEFT_SHOULDER, I.LEFT_HIP, I.LEFT_ELBOW, I.LEFT_WRIST, I.LEFT_EAR),
         "right": (I.RIGHT_SHOULDER, I.RIGHT_HIP, I.RIGHT_ELBOW, I.RIGHT_WRIST, I.RIGHT_EAR)}


def shoulder_line_tilt(left, right):
    """Angle of the shoulder line from horizontal, in degrees (0 = level)."""
    return abs(math.degrees(math.atan2(left.y - right.y, abs(left.x - right.x) or 1e-9)))


class SessionProcessor:
    def __init__(self, config=None, arm="right", rules_engine=None, exercise=None, plan=None):
        """`exercise` (src.exercises.Exercise, default: abduction) and then the patient's `plan`
        (src.user_profile.Plan) may override the movement thresholds of `config`; everything
        below reads the effective `self.config`."""
        self.exercise = exercise or get_exercise()
        self.plan = plan
        self._base_config = config or ExerciseConfig.from_yaml()
        self.config = self.exercise.apply(self._base_config)
        if plan is not None:
            self.config = plan.apply(self.config)
        # Both-arm exercises measure the two arms together: arm "both" (Phase 10.1).
        self.arm = "both" if self.exercise.both_arms else arm if arm in ("left", "right") else "right"
        self.rules_engine = rules_engine or RulesEngine(self.config)
        self.rules_engine.config = self.config
        self.session_id = uuid4().hex
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.smoother = MultiMetricSmoother(self.config.filtering.ema_alpha)
        # Calibration accepts a resting arm a little raised (a stiff shoulder's own rest), but not an
        # arm clearly raised toward the target; the rest and rise thresholds then follow (Phase 2.3).
        self._planned_abduction = self.config.abduction
        ceiling = max(self.config.abduction.rest_threshold_deg, self.config.abduction.target_min_deg - CALIBRATION_MARGIN_DEG)
        self.calibrator = CalibrationManager(
            self.config.calibration.duration_sec, self.config.calibration.max_variance_ratio,
            self.config.filtering.min_landmark_visibility, ceiling,
            self.config.compensation.max_trunk_lean_deg,
        )
        self.resting_angle = None      # median resting angle of the last calibration
        self._facing_baseline = None   # shoulder width / torso height at calibration (face check)
        self.rest_warning = False      # resting too close to the target: the plan's values were kept
        self.calibrations_done = 0
        a = self.config.abduction
        self.state_machine = RepetitionStateMachine(a.rest_threshold_deg, a.rising_start_deg,
            a.target_min_deg, a.target_max_deg, self.config.timing.min_hold_time_sec, self.arm)
        self.last_evaluation = None
        self.model_info = {}
        self._last_frame_time = None
        self._last_valid_time = None
        self._started = False
        self._need_rest = True
        self.interrupted_attempts = 0
        self.frames_total = 0
        self.frames_tracked = 0
        self._reset_pair()

    def _reset_pair(self):
        """Both arms: each arm's peak and the largest gap between them in the current movement."""
        self._pair_peaks, self._pair_gap = {}, None

    @staticmethod
    def _facing_ratio(pts):
        """Shoulder width over torso height: smaller when the body turns away from the camera."""
        mid_shoulders = ((pts[I.LEFT_SHOULDER].x + pts[I.RIGHT_SHOULDER].x) / 2, (pts[I.LEFT_SHOULDER].y + pts[I.RIGHT_SHOULDER].y) / 2)
        mid_hips = ((pts[I.LEFT_HIP].x + pts[I.RIGHT_HIP].x) / 2, (pts[I.LEFT_HIP].y + pts[I.RIGHT_HIP].y) / 2)
        torso = math.dist(mid_shoulders, mid_hips)
        return calculate_distance_2d(pts[I.LEFT_SHOULDER], pts[I.RIGHT_SHOULDER]) / torso if torso > 1e-6 else None

    def set_plan(self, plan):
        """Change the plan during a session (gentle after "It hurts") without losing its movements."""
        self.plan = plan
        config = self.exercise.apply(self._base_config)
        self.config = plan.apply(config) if plan is not None else config
        self._planned_abduction = self.config.abduction
        self.rules_engine.config = self.config
        machine, a = self.state_machine, self.config.abduction
        machine.target_min_deg, machine.target_max_deg = a.target_min_deg, a.target_max_deg
        if hasattr(machine, "min_hold_time_sec"):
            machine.min_hold_time_sec = self.config.timing.min_hold_time_sec
        if self.calibrations_done:
            self.calibrations_done -= 1  # re-adapting is not a new calibration
            self._adapt_rest(self.resting_angle)
        else:
            machine.rest_threshold_deg, machine.rising_start_deg = a.rest_threshold_deg, a.rising_start_deg

    def _adapt_rest(self, resting):
        """Rest threshold = max(planned rest, resting + 8 deg); rise = rest + 7 deg, unless the
        rise would come within 10 deg of the target: then the plan's values stay (rest_warning)."""
        planned = self._planned_abduction
        self.calibrations_done += 1
        resting = None if resting is None else round(resting, 1)
        self.resting_angle, self.rest_warning = resting, False
        rest, rise = planned.rest_threshold_deg, planned.rising_start_deg
        if resting is not None and resting + REST_MARGIN_DEG > planned.rest_threshold_deg:
            candidate = resting + REST_MARGIN_DEG
            if candidate + RISE_MARGIN_DEG > planned.target_min_deg - TARGET_GAP_DEG:
                self.rest_warning = True
            else:
                rest, rise = candidate, candidate + RISE_MARGIN_DEG
        abduction = replace(planned, rest_threshold_deg=rest, rising_start_deg=rise)
        if abduction != self.config.abduction:
            self.config = replace(self.config, abduction=abduction)
            self.rules_engine.config = self.config
        self.state_machine.rest_threshold_deg, self.state_machine.rising_start_deg = rest, rise

    def recalibrate(self, arm=None, timestamp_sec=None):
        if timestamp_sec is None:
            timestamp_sec = self._last_frame_time if self._last_frame_time is not None else 0.0
        self.finish()
        if self.arm != "both":  # a both-arm exercise has no arm to choose
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
            self._reset_pair()
            self.smoother.reset_all()
            self._need_rest = True

    def finish(self):
        """Record a stopped, unfinished attempt without fabricating a completed rep."""
        if self.state_machine.current_phase != ExercisePhase.REST:
            self.interrupted_attempts += 1
            self.rules_engine.session.interrupted_attempts += 1
        self.state_machine.reset_current_rep()
        self._reset_pair()
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
        names = ("abduction", "lean", "shrug", "elbow", "drift")
        if self.arm == "both":
            names += ("abduction_left", "abduction_right", "asymmetry")
        frame = FrameAnalysis(now, landmarks or [], metrics={k: None for k in names})
        frame.world_landmarks=list(world_landmarks or [])
        if not landmarks or len(landmarks) < 33:
            if self.calibrator.is_calibrating:
                self.calibrator.update(None, self.arm, now)
            self._pause(now)
            frame.status = "SUIVI PERDU"
            frame.cue = cue_feedback(Cue.NO_SKELETON)
            return frame

        pts = to_measurement_space(landmarks, width, height)
        arms = ("left", "right") if self.arm == "both" else (self.arm,)
        sh, hip, el, wr, ear = SIDES[arms[0]]
        torso = (I.LEFT_SHOULDER, I.RIGHT_SHOULDER, I.LEFT_HIP, I.RIGHT_HIP)
        min_v = self.config.filtering.min_landmark_visibility

        def visible(indices):
            return (are_landmarks_visible([pts[i] for i in indices], min_v)
                and all(0 <= landmarks[i].x <= 1 and 0 <= landmarks[i].y <= 1 for i in indices))

        shoulders_ok = visible((I.LEFT_SHOULDER, I.RIGHT_SHOULDER)) and calculate_distance_2d(pts[I.LEFT_SHOULDER], pts[I.RIGHT_SHOULDER]) > .05
        elbow_ok = all(visible((SIDES[a][0], SIDES[a][2])) and calculate_distance_2d(pts[SIDES[a][0]], pts[SIDES[a][2]]) > .02
                       for a in arms)
        torso_ok = visible(torso) and calculate_distance_2d(pts[sh], pts[hip]) > .1
        if self.calibrator.is_calibrating:
            # Invisible or off-screen optional landmarks must not be used as observations.
            calibration_pts = [p if visible((i,)) else type(p)(p.x, p.y, 0.) for i,p in enumerate(pts)]
            self.calibrator.update(calibration_pts if shoulders_ok else None, self.arm, now)
            frame.calibration_progress = self.calibrator.get_progress() if self.calibrator.is_calibrating else None
            if not self.calibrator.is_calibrating and self.calibrator.calibrated_data.is_calibrated:
                self._adapt_rest(self.calibrator.calibrated_data.rest_angle_median_deg)
                self._facing_baseline = self._facing_ratio(pts) if torso_ok else None
        baseline = self.calibrator.calibrated_data
        if baseline.is_calibrated and baseline.reference_mode == "torso" and not torso_ok:
            # Changing angle definitions in a movement would corrupt its peak/timing.
            self.finish()
            self.smoother.reset_all()
            baseline.reference_mode = "shoulders"
        mode = baseline.reference_mode if baseline.is_calibrated else ("torso" if torso_ok else "shoulders")
        frame.angle_reference = mode
        raw = frame.metrics.copy()
        angles, elbows = {}, []
        for a in arms:
            a_sh, a_hip, a_el, a_wr, _ = SIDES[a]
            if elbow_ok and mode == "torso" and torso_ok:
                angles[a] = calculate_abduction_angle(pts[a_sh], pts[a_hip], pts[a_el])
            elif elbow_ok and shoulders_ok and mode == "shoulders":
                angles[a] = calculate_shoulder_reference_angle(pts[I.LEFT_SHOULDER], pts[I.RIGHT_SHOULDER], pts[a_sh], pts[a_el])
            if visible((a_sh, a_el, a_wr)) and calculate_distance_2d(pts[a_el], pts[a_wr]) > 0.02:
                elbows.append(calculate_elbow_angle(pts[a_sh], pts[a_el], pts[a_wr]))
        if self.arm == "both":
            # Each arm is smoothed on its own; the counted angle (the lower arm) is taken after.
            raw["abduction_left"], raw["abduction_right"] = angles.get("left"), angles.get("right")
        else:
            raw["abduction"] = angles.get(self.arm)
        angle_ok = len(angles) == len(arms)
        if len(elbows) == len(arms):
            raw["elbow"] = min(elbows)  # both arms: the more bent elbow
        if visible(torso) and math.hypot((pts[I.LEFT_SHOULDER].x + pts[I.RIGHT_SHOULDER].x - pts[I.LEFT_HIP].x - pts[I.RIGHT_HIP].x) / 2,
                (pts[I.LEFT_SHOULDER].y + pts[I.RIGHT_SHOULDER].y - pts[I.LEFT_HIP].y - pts[I.RIGHT_HIP].y) / 2) > .1:
            raw["lean"] = calculate_trunk_lean(*(pts[i] for i in torso))
        elif self.plan is not None and self.plan.seated and shoulders_ok:
            # Seated, hips hidden by the chair or table: the shoulder line's tilt stands in for the
            # trunk lean, minus a few degrees of natural tilt as the arm rises (Phase 4.4).
            raw["lean"] = max(0., shoulder_line_tilt(pts[I.LEFT_SHOULDER], pts[I.RIGHT_SHOULDER]) - SEATED_TILT_ALLOWANCE_DEG)
        if baseline.is_calibrated and baseline.baseline_ear_shoulder_dist is not None:
            shrugs = [calculate_shoulder_shrug(pts[SIDES[a][4]], pts[SIDES[a][0]], baseline.baseline_ear_shoulder_dist,
                                               baseline.baseline_shoulder_width)
                      for a in arms if visible((SIDES[a][4], SIDES[a][0]))]
            if len(shrugs) == len(arms):
                raw["shrug"] = max(shrugs)
        turned = False
        if world_landmarks and len(world_landmarks) >= 33:
            drifts = []
            for a in arms:
                a_sh, a_hip, a_el = SIDES[a][:3]
                other_sh, other_hip = SIDES["right" if a == "left" else "left"][:2]
                wpts = [world_landmarks[i] for i in (a_sh, other_sh, a_hip, other_hip, a_el)]
                # World hips inferred outside the image do not establish a visible torso.
                if torso_ok and elbow_ok and are_landmarks_visible(wpts, min_v):
                    lateral = math.dist((wpts[0].x,wpts[0].y,wpts[0].z), (wpts[1].x,wpts[1].y,wpts[1].z))
                    arm_length = math.dist((wpts[0].x,wpts[0].y,wpts[0].z), (wpts[4].x,wpts[4].y,wpts[4].z))
                    if lateral > .05 and arm_length > .05:
                        drifts.append(calculate_anterior_drift_angle(*wpts))
                        if abs(wpts[0].z - wpts[1].z) / lateral > self.config.filtering.max_turn_depth_ratio:
                            angle_ok, turned = False, True
            if drifts and len(drifts) == len(arms):
                raw["drift"] = max(drifts)
        if baseline.is_calibrated and shoulders_ok:
            width_ratio = calculate_distance_2d(pts[I.LEFT_SHOULDER], pts[I.RIGHT_SHOULDER]) / baseline.baseline_shoulder_width
            if not .65 <= width_ratio <= 1.4:
                angle_ok = False
            facing = self._facing_ratio(pts) if torso_ok else None
            if facing is not None and self._facing_baseline and facing / self._facing_baseline < self.config.filtering.min_facing_ratio:
                angle_ok, turned = False, True  # turned: the 2D angle would be wrong (Phase 5.6)
        # A time-based EMA has the same response at different frame rates.
        alpha = 1 - (1 - self.config.filtering.ema_alpha) ** (min(dt, .1) * 30)
        for name, value in raw.items():
            smoother = self.smoother.get_smoother(name)
            smoother.alpha = alpha
            frame.metrics[name] = smoother.update(value) if value is not None else None
        if self.arm == "both":
            left, right = frame.metrics["abduction_left"], frame.metrics["abduction_right"]
            if left is not None and right is not None:
                frame.metrics["abduction"] = min(left, right)  # a movement counts when both arms get there
                frame.metrics["asymmetry"] = abs(left - right)

        if not baseline.is_calibrated:
            frame.status = "CALIBRATION"
            frame.cue = LiveFeedback(self.calibrator.status_message, FeedbackLevel.INFO, self.calibrator.status_code)
            return frame
        if not angle_ok:
            frame.metrics["abduction"] = None
            if self.arm == "both":
                frame.metrics["abduction_left"] = frame.metrics["abduction_right"] = frame.metrics["asymmetry"] = None
            self._pause(now)
            frame.status = "EPAULES PRETES" if shoulders_ok and not elbow_ok else "POSITION A AJUSTER"
            frame.cue = cue_feedback(Cue.FACE_CAMERA if turned and elbow_ok else
                                     Cue.SHOULDERS_READY_SHOW_ELBOW if shoulders_ok and not elbow_ok
                                     else Cue.SHOW_SHOULDERS_AND_ELBOW)
            return frame
        self.frames_tracked += 1
        self._last_valid_time = now
        angle = frame.metrics["abduction"]
        if self._need_rest:
            if angle > self.config.abduction.rest_threshold_deg:
                frame.status = "REPOS REQUIS"
                frame.cue = cue_feedback(Cue.LOWER_BEFORE_REP)
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
        if self.arm == "both" and frame.phase != ExercisePhase.REST:
            gap = m["asymmetry"]
            self._pair_gap = gap if self._pair_gap is None else max(self._pair_gap, gap)
            for a in ("left", "right"):
                self._pair_peaks[a] = max(self._pair_peaks.get(a, 0.), m[f"abduction_{a}"])
            if gap > self.config.compensation.max_asymmetry_deg and frame.cue.level != FeedbackLevel.WARNING:
                frame.cue = cue_feedback(Cue.ARMS_UNEVEN, FeedbackLevel.WARNING)
        if frame.phase == ExercisePhase.HOLD and frame.hold_seconds >= self.config.timing.min_hold_time_sec and frame.cue.level != FeedbackLevel.WARNING:
            frame.cue = cue_feedback(Cue.HOLD_DONE_LOWER)
        if rep and self.arm == "both":
            rep.peaks = {a: round(v, 1) for a, v in self._pair_peaks.items()}
            rep.max_asymmetry_deg = self._pair_gap
            self._reset_pair()
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
