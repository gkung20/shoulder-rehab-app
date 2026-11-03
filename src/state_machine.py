"""Repetition finite state machine with hysteresis for active shoulder abduction.

Models the concentric (raising), isometric (hold), and eccentric (lowering)
phases of rehabilitation exercises while preventing jitter from triggering false repetitions.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import List, Optional, Tuple

from src.geometry import calculate_trajectory_smoothness


class ExercisePhase(str, Enum):
    """Phases of an active shoulder abduction repetition."""
    REST = "REST"            # Arm hanging down in neutral rest position
    RISING = "RISING"        # Concentric phase: arm raising laterally
    HOLD = "HOLD"            # Isometric phase: arm sustained at target abduction
    LOWERING = "LOWERING"    # Eccentric phase: arm returning down under control


@dataclass
class RepetitionMetrics:
    """Detailed biomechanical telemetry captured for a completed repetition."""
    rep_index: int
    arm: str
    peak_abduction_deg: float
    target_reached: bool
    concentric_duration_sec: float
    hold_duration_sec: float
    eccentric_duration_sec: float
    total_duration_sec: float
    max_trunk_lean_deg: float
    max_shrug_ratio: float
    min_elbow_angle_deg: float
    max_drift_deg: float = 0.0
    fluidity_score_pct: Optional[float] = None
    missing_metrics: Tuple[str, ...] = ()
    session_id: str = ""
    config_snapshot: dict = field(default_factory=dict)
    calibration_snapshot: dict = field(default_factory=dict)
    angle_reference: str = "torso"


class RepetitionStateMachine:
    """Hysteresis counts attempts; timing uses only observed, valid frame intervals."""

    def __init__(self, rest_threshold_deg=25.0, rising_start_deg=32.0,
                 target_min_deg=80.0, target_max_deg=100.0,
                 min_hold_time_sec=0.5, arm="right"):
        if not 0 <= rest_threshold_deg < rising_start_deg < target_min_deg <= target_max_deg <= 180:
            raise ValueError("Invalid repetition thresholds")
        self.rest_threshold_deg = rest_threshold_deg
        self.rising_start_deg = rising_start_deg
        self.target_min_deg = target_min_deg
        self.target_max_deg = target_max_deg
        self.min_hold_time_sec = min_hold_time_sec
        self.arm = arm
        self.completed_reps = []
        self._rep_counter = 0
        self.reset_current_rep()

    @property
    def rep_count(self):
        return len(self.completed_reps)

    @property
    def hold_duration_sec(self):
        return self._durations[ExercisePhase.HOLD]

    def reset_current_rep(self):
        self.current_phase = ExercisePhase.REST
        self._durations = {p: 0.0 for p in ExercisePhase}
        self._last_timestamp = None
        self._last_angle = None
        self._current_peak_angle = 0.0
        self._max_lean = 0.0
        self._max_shrug = 0.0
        self._min_elbow = 180.0
        self._max_drift = 0.0
        self._trajectory_times = []
        self._trajectory_angles = []
        self._missing = set()

    def reset_all(self):
        self.reset_current_rep()
        self.completed_reps.clear()
        self._rep_counter = 0

    def set_arm(self, arm):
        if arm not in ("left", "right"):
            raise ValueError("arm must be left or right")
        self.arm = arm
        self.reset_current_rep()

    def pause(self):
        if self.current_phase != ExercisePhase.REST:
            self._missing.add("suivi interrompu")
        self._last_timestamp = None
        self._last_angle = None

    def update(self, current_angle, timestamp_sec, current_lean=None,
               current_shrug=None, current_elbow=None, current_drift=None,
               missing_metrics=()):
        if current_angle is None or not math.isfinite(current_angle):
            self.pause()
            return None
        if not math.isfinite(timestamp_sec):
            raise ValueError("Timestamp must be finite")
        if self._last_timestamp is not None and timestamp_sec <= self._last_timestamp:
            raise ValueError("Timestamps must strictly increase")
        phase = self.current_phase
        if phase == ExercisePhase.REST:
            if current_angle < self.rising_start_deg:
                return None
            self.current_phase = ExercisePhase.RISING
            phase = ExercisePhase.RISING
        elif self._last_timestamp is not None:
            dt = timestamp_sec - self._last_timestamp
            timed_phase = phase
            if phase == ExercisePhase.RISING and current_angle < self._current_peak_angle - 5:
                self.current_phase = ExercisePhase.LOWERING
                timed_phase = ExercisePhase.LOWERING
            # Hysteresis controls state transitions, but only the target band earns hold time.
            if phase == ExercisePhase.HOLD and not (
                self._last_angle is not None and
                self.target_min_deg <= self._last_angle <= self.target_max_deg and
                self.target_min_deg <= current_angle <= self.target_max_deg
            ):
                timed_phase = ExercisePhase.LOWERING if current_angle < self.target_min_deg else ExercisePhase.RISING
            self._durations[timed_phase] += dt
        self._last_timestamp = timestamp_sec
        self._last_angle = current_angle
        self._current_peak_angle = max(self._current_peak_angle, current_angle)
        self._trajectory_times.append(timestamp_sec)
        self._trajectory_angles.append(current_angle)
        self._missing.update(missing_metrics)
        for value, label in ((current_lean, "tronc"), (current_shrug, "epaule"),
                             (current_elbow, "coude"), (current_drift, "derive 3D")):
            if value is None or not math.isfinite(value):
                self._missing.add(label)
        if current_lean is not None:
            self._max_lean = max(self._max_lean, current_lean)
        if current_shrug is not None:
            self._max_shrug = max(self._max_shrug, current_shrug)
        if current_elbow is not None:
            self._min_elbow = min(self._min_elbow, current_elbow)
        if current_drift is not None:
            self._max_drift = max(self._max_drift, current_drift)

        if current_angle <= self.rest_threshold_deg:
            return self._complete()
        if self.current_phase == ExercisePhase.RISING and current_angle >= self.target_min_deg:
            self.current_phase = ExercisePhase.HOLD
        elif self.current_phase == ExercisePhase.HOLD and current_angle < self.target_min_deg - 5:
            self.current_phase = ExercisePhase.LOWERING
        elif self.current_phase == ExercisePhase.LOWERING and current_angle >= self.target_min_deg:
            self.current_phase = ExercisePhase.HOLD
        return None

    def _complete(self):
        self._rep_counter += 1
        fluidity = None
        if (len(self._trajectory_times) >= 5 and
                self._trajectory_times[-1] - self._trajectory_times[0] > 0.15 and
                "suivi interrompu" not in self._missing):
            _, fluidity = calculate_trajectory_smoothness(self._trajectory_times, self._trajectory_angles)
        record = RepetitionMetrics(
            rep_index=self._rep_counter, arm=self.arm,
            peak_abduction_deg=self._current_peak_angle,
            target_reached=self._current_peak_angle >= self.target_min_deg,
            concentric_duration_sec=self._durations[ExercisePhase.RISING],
            hold_duration_sec=self._durations[ExercisePhase.HOLD],
            eccentric_duration_sec=self._durations[ExercisePhase.LOWERING],
            total_duration_sec=sum(self._durations.values()),
            max_trunk_lean_deg=self._max_lean, max_shrug_ratio=self._max_shrug,
            min_elbow_angle_deg=self._min_elbow, max_drift_deg=self._max_drift,
            fluidity_score_pct=fluidity, missing_metrics=tuple(sorted(self._missing)),
        )
        self.completed_reps.append(record)
        self.reset_current_rep()
        return record
