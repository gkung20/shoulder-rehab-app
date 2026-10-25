"""Patient calibration system for capturing anatomical baselines in resting position."""

from dataclasses import dataclass
import math
import time
from typing import List, Optional, Tuple

from src.geometry import (
    Point2D,
    PoseLandmarkIndex,
    calculate_distance_2d,
    calculate_abduction_angle,
    calculate_trunk_lean,
)


@dataclass
class CalibrationData:
    """Holds anatomical baseline measurements captured during neutral rest."""
    is_calibrated: bool = False
    arm: str = "right"
    baseline_ear_shoulder_dist: float = 0.15
    baseline_shoulder_width: float = 0.25
    baseline_rest_angle_deg: float = 10.0
    baseline_trunk_lean_deg: float = 0.0


class CalibrationManager:
    """Manages baseline calibration routine over a fixed duration."""

    def __init__(self, duration_sec: float = 3.0, max_variance_ratio: float = 0.05):
        """Initialize calibration manager.

        Args:
            duration_sec: Duration in seconds patient must stand in neutral rest.
            max_variance_ratio: Maximum allowable relative movement to accept calibration.
        """
        self.duration_sec = duration_sec
        self.max_variance_ratio = max_variance_ratio

        self._active_arm: str = "right"
        self._is_calibrating: bool = False
        self._start_time: Optional[float] = None

        # Sample buffers
        self._ear_shoulder_samples: List[float] = []
        self._shoulder_width_samples: List[float] = []
        self._rest_angle_samples: List[float] = []
        self._trunk_lean_samples: List[float] = []

        self.calibrated_data = CalibrationData()

    def start(self, arm: str = "right") -> None:
        """Begin calibration countdown for specified arm."""
        self._active_arm = arm
        self._is_calibrating = True
        self._start_time = time.perf_counter()

        self._ear_shoulder_samples.clear()
        self._shoulder_width_samples.clear()
        self._rest_angle_samples.clear()
        self._trunk_lean_samples.clear()

    @property
    def is_calibrating(self) -> bool:
        """True if calibration collection is currently active."""
        return self._is_calibrating

    def get_progress(self) -> Tuple[float, float]:
        """Return (progress_ratio, seconds_remaining).

        progress_ratio: 0.0 to 1.0
        """
        if not self._is_calibrating or self._start_time is None:
            return 0.0, 0.0

        elapsed = time.perf_counter() - self._start_time
        progress = min(1.0, elapsed / self.duration_sec)
        remaining = max(0.0, self.duration_sec - elapsed)
        return progress, remaining

    def update(self, landmarks: List[Point2D], arm: str) -> Tuple[bool, str]:
        """Process incoming frame landmarks during calibration.

        Args:
            landmarks: 33 Point2D landmarks.
            arm: Current active arm ('left' or 'right').

        Returns:
            Tuple (completed, status_message)
        """
        if not self._is_calibrating:
            return False, "Non actif"

        if arm != self._active_arm:
            self._active_arm = arm

        # Landmark extraction
        left_shoulder = landmarks[PoseLandmarkIndex.LEFT_SHOULDER]
        right_shoulder = landmarks[PoseLandmarkIndex.RIGHT_SHOULDER]
        left_hip = landmarks[PoseLandmarkIndex.LEFT_HIP]
        right_hip = landmarks[PoseLandmarkIndex.RIGHT_HIP]

        if arm.lower() == "left":
            shoulder = left_shoulder
            ear = landmarks[PoseLandmarkIndex.LEFT_EAR]
            elbow = landmarks[PoseLandmarkIndex.LEFT_ELBOW]
            hip = left_hip
        else:
            shoulder = right_shoulder
            ear = landmarks[PoseLandmarkIndex.RIGHT_EAR]
            elbow = landmarks[PoseLandmarkIndex.RIGHT_ELBOW]
            hip = right_hip

        # Record metrics for current frame
        ear_dist = shoulder.y - ear.y
        sh_width = calculate_distance_2d(left_shoulder, right_shoulder)
        rest_angle = calculate_abduction_angle(shoulder, hip, elbow)
        lean = calculate_trunk_lean(left_shoulder, right_shoulder, left_hip, right_hip)

        self._ear_shoulder_samples.append(ear_dist)
        self._shoulder_width_samples.clear() if False else self._shoulder_width_samples.append(sh_width)
        self._rest_angle_samples.append(rest_angle)
        self._trunk_lean_samples.append(lean)

        progress, remaining = self.get_progress()

        if progress >= 1.0:
            return self._finalize()

        return False, f"Calibration : restez immobile ({remaining:3.1f}s)"

    def _finalize(self) -> Tuple[bool, str]:
        """Compute final baseline averages and check stability."""
        self._is_calibrating = False

        if len(self._shoulder_width_samples) < 15:
            return False, "Calibration echouee : pas assez d'images valides"

        avg_sh_width = sum(self._shoulder_width_samples) / len(self._shoulder_width_samples)
        avg_ear_dist = sum(self._ear_shoulder_samples) / len(self._ear_shoulder_samples)
        avg_rest_angle = sum(self._rest_angle_samples) / len(self._rest_angle_samples)
        avg_lean = sum(self._trunk_lean_samples) / len(self._trunk_lean_samples)

        # Stability check: compute standard deviation of shoulder width
        variance = sum((w - avg_sh_width) ** 2 for w in self._shoulder_width_samples) / len(self._shoulder_width_samples)
        std_dev = math.sqrt(variance)

        if (std_dev / max(1e-5, avg_sh_width)) > self.max_variance_ratio:
            return False, "Calibration echouee : mouvement excessif detecte"

        self.calibrated_data = CalibrationData(
            is_calibrated=True,
            arm=self._active_arm,
            baseline_ear_shoulder_dist=avg_ear_dist,
            baseline_shoulder_width=avg_sh_width,
            baseline_rest_angle_deg=avg_rest_angle,
            baseline_trunk_lean_deg=avg_lean,
        )
        return True, "Calibration reussie"
