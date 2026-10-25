"""Typed configuration loader for exercise thresholds and signal filtering."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import yaml


@dataclass
class AbductionThresholds:
    rest_threshold_deg: float = 25.0
    rising_start_deg: float = 32.0
    target_min_deg: float = 80.0
    target_max_deg: 100.0 = 100.0
    overshoot_warn_deg: float = 110.0


@dataclass
class CompensationThresholds:
    max_trunk_lean_deg: float = 10.0
    max_shrug_ratio: float = 0.12
    min_elbow_angle_deg: float = 155.0


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


@dataclass
class CalibrationConfig:
    duration_sec: float = 3.0
    max_variance_ratio: float = 0.05


@dataclass
class ExerciseConfig:
    abduction: AbductionThresholds
    compensation: CompensationThresholds
    timing: TimingThresholds
    filtering: FilteringConfig
    calibration: CalibrationConfig

    @classmethod
    def from_yaml(cls, path: Optional[Path] = None) -> "ExerciseConfig":
        """Load configuration from YAML file, falling back to safe placeholder defaults."""
        if path is None:
            path = Path(__file__).resolve().parent.parent / "config" / "exercise_config.yaml"

        if not path.exists():
            return cls(
                abduction=AbductionThresholds(),
                compensation=CompensationThresholds(),
                timing=TimingThresholds(),
                filtering=FilteringConfig(),
                calibration=CalibrationConfig(),
            )

        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        thresh = raw.get("thresholds", {})
        abd = thresh.get("abduction", {})
        comp = thresh.get("compensation", {})
        tim = thresh.get("timing", {})
        filt = raw.get("filtering", {})
        calib = raw.get("calibration", {})

        return cls(
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
            ),
            calibration=CalibrationConfig(
                duration_sec=float(calib.get("duration_sec", 3.0)),
                max_variance_ratio=float(calib.get("max_variance_ratio", 0.05)),
            ),
        )
