"""Typed configuration loader for exercise thresholds and signal filtering."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import math
import yaml


@dataclass
class AbductionThresholds:
    rest_threshold_deg: float = 25.0
    rising_start_deg: float = 32.0
    target_min_deg: float = 80.0
    target_max_deg: float = 100.0
    overshoot_warn_deg: float = 110.0


@dataclass
class CompensationThresholds:
    max_trunk_lean_deg: float = 10.0
    max_shrug_ratio: float = 0.12
    min_elbow_angle_deg: float = 155.0
    max_anterior_drift_deg: float = 25.0
    min_fluidity_pct: float = 60.0
    evaluate_fluidity: bool = False  # Experimental proxy; not a validated quality criterion.


@dataclass
class TimingThresholds:
    min_concentric_time_sec: float = 1.0
    max_concentric_time_sec: float = 4.5
    min_hold_time_sec: float = 0.5
    min_eccentric_time_sec: float = 1.0
    max_eccentric_time_sec: float = 4.5


@dataclass
class FilteringConfig:
    ema_alpha: float = 0.35
    min_landmark_visibility: float = 0.60
    tracking_reset_sec: float = 0.75


@dataclass
class CalibrationConfig:
    duration_sec: float = 3.0
    max_variance_ratio: float = 0.05


@dataclass
class CameraConfig:
    index: int = 0
    width: int = 1280
    height: int = 720
    fps: int = 30
    zoom: Optional[float] = None  # Device-native units; None leaves the camera unchanged.


@dataclass
class PoseConfig:
    model: str = "full"


@dataclass
class AudioConfig:
    backend: str = "auto"  # Local Piper first, then a French Windows voice only.
    voice: str = "fr_FR-siwis-medium"
    length_scale: float = 1.30
    volume: float = 0.85
    speech_rate: int = 130
    min_interval_sec: float = 8.0
    repeat_cooldown_sec: float = 40.0
    guidance_mode: str = "essential"
    warning_persistence_sec: float = 1.5
    announce_every_reps: int = 5


@dataclass
class ExerciseConfig:
    abduction: AbductionThresholds
    compensation: CompensationThresholds
    timing: TimingThresholds
    filtering: FilteringConfig
    calibration: CalibrationConfig
    camera: CameraConfig = field(default_factory=CameraConfig)
    pose: PoseConfig = field(default_factory=PoseConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)

    def __post_init__(self):
        # Dataclasses used by pure rule tests may omit camera-only settings.
        groups = (self.abduction, self.compensation, self.timing, self.filtering, self.calibration)
        for group in groups:
            if group is not None:
                for value in vars(group).values():
                    if isinstance(value, (int, float)) and not math.isfinite(value):
                        raise ValueError("Configuration values must be finite")
        a = self.abduction
        if not 0 <= a.rest_threshold_deg < a.rising_start_deg < a.target_min_deg <= a.target_max_deg <= a.overshoot_warn_deg <= 180:
            raise ValueError("Expected rest < rising < target min <= target max <= overshoot <= 180")
        c = self.compensation
        if not (0 < c.max_trunk_lean_deg <= 90 and 0 < c.max_shrug_ratio <= 1
                and 0 < c.min_elbow_angle_deg <= 180 and 0 < c.max_anterior_drift_deg <= 90
                and 0 <= c.min_fluidity_pct <= 100):
            raise ValueError("Invalid compensation thresholds")
        t = self.timing
        if not (0 < t.min_concentric_time_sec <= t.max_concentric_time_sec
                and 0 < t.min_eccentric_time_sec <= t.max_eccentric_time_sec and t.min_hold_time_sec >= 0):
            raise ValueError("Invalid phase durations")
        if self.filtering is not None:
            f = self.filtering
            if not (0 < f.ema_alpha <= 1 and 0 <= f.min_landmark_visibility <= 1 and f.tracking_reset_sec > 0):
                raise ValueError("Invalid filtering settings")
        if self.calibration is not None and (self.calibration.duration_sec <= 0 or self.calibration.max_variance_ratio <= 0):
            raise ValueError("Invalid calibration settings")
        if self.pose.model not in ("lite", "full", "heavy"):
            raise ValueError("Pose model must be lite, full or heavy")
        audio = self.audio
        import re
        if (audio.backend not in ("auto", "piper", "system")
                or not re.fullmatch(r"fr_FR-[a-zA-Z0-9_]+-(?:low|medium|high)", audio.voice)
                or audio.guidance_mode not in ("essential", "complete")
                or any(not math.isfinite(v) for v in (audio.length_scale, audio.volume, audio.speech_rate, audio.min_interval_sec, audio.repeat_cooldown_sec, audio.warning_persistence_sec))
                or not .5 <= audio.length_scale <= 2 or not 0 <= audio.volume <= 1
                or not 80 <= audio.speech_rate <= 250 or audio.min_interval_sec < 0 or audio.repeat_cooldown_sec < 0
                or audio.warning_persistence_sec < 0 or not isinstance(audio.announce_every_reps, int)
                or isinstance(audio.announce_every_reps, bool) or audio.announce_every_reps < 1):
            raise ValueError("Invalid French audio settings")
        camera = self.camera
        if (any(not isinstance(v, int) or isinstance(v, bool) for v in (camera.index, camera.width, camera.height, camera.fps))
                or camera.index < 0 or min(camera.width, camera.height, camera.fps) <= 0
                or (camera.zoom is not None and (not math.isfinite(camera.zoom) or camera.zoom < 0))):
            raise ValueError("Invalid camera settings")

    @classmethod
    def from_yaml(cls, path: Optional[Path] = None) -> "ExerciseConfig":
        """Load and validate prototype settings; missing files are explicit errors."""
        if path is None:
            path = Path(__file__).resolve().parent.parent / "config" / "exercise_config.yaml"

        if not path.exists():
            raise FileNotFoundError(f"Exercise configuration not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        thresh = raw.get("thresholds", {})
        abd = thresh.get("abduction", {})
        comp = thresh.get("compensation", {})
        tim = thresh.get("timing", {})
        filt = raw.get("filtering", {})
        calib = raw.get("calibration", {})
        camera = raw.get("camera", {})
        audio = raw.get("audio", {})

        return cls(
            audio=AudioConfig(**audio),
            camera=CameraConfig(index=camera.get("index", 0), width=camera.get("width", 1280),
                height=camera.get("height", 720), fps=camera.get("fps", 30), zoom=camera.get("zoom")),
            pose=PoseConfig(model=raw.get("pose", {}).get("model", "full")),
            abduction=AbductionThresholds(
                rest_threshold_deg=float(abd.get("rest_threshold_deg", 25.0)),
                rising_start_deg=float(abd.get("rising_start_deg", 32.0)),
                target_min_deg=float(abd.get("target_min_deg", 80.0)),
                target_max_deg=float(abd.get("target_max_deg", 100.0)),
                overshoot_warn_deg=float(abd.get("overshoot_warn_deg", 110.0)),
            ),
            compensation=CompensationThresholds(
                max_trunk_lean_deg=float(comp.get("max_trunk_lean_deg", 10.0)),
                max_shrug_ratio=float(comp.get("max_shrug_ratio", 0.12)),
                min_elbow_angle_deg=float(comp.get("min_elbow_angle_deg", 155.0)),
                max_anterior_drift_deg=float(comp.get("max_anterior_drift_deg", 25.0)),
                min_fluidity_pct=float(comp.get("min_fluidity_pct", 60.0)),
                evaluate_fluidity=comp.get("evaluate_fluidity", False) is True,
            ),
            timing=TimingThresholds(
                min_concentric_time_sec=float(tim.get("min_concentric_time_sec", 1.0)),
                max_concentric_time_sec=float(tim.get("max_concentric_time_sec", 4.5)),
                min_hold_time_sec=float(tim.get("min_hold_time_sec", 0.5)),
                min_eccentric_time_sec=float(tim.get("min_eccentric_time_sec", 1.0)),
                max_eccentric_time_sec=float(tim.get("max_eccentric_time_sec", 4.5)),
            ),
            filtering=FilteringConfig(
                ema_alpha=float(filt.get("ema_alpha", 0.35)),
                min_landmark_visibility=float(filt.get("min_landmark_visibility", 0.60)),
                tracking_reset_sec=float(filt.get("tracking_reset_sec", 0.75)),
            ),
            calibration=CalibrationConfig(
                duration_sec=float(calib.get("duration_sec", 3.0)),
                max_variance_ratio=float(calib.get("max_variance_ratio", 0.05)),
            ),
        )
