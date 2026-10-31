"""Repetition finite state machine with hysteresis for active shoulder abduction.

Models the concentric (raising), isometric (hold), and eccentric (lowering)
phases of rehabilitation exercises while preventing jitter from triggering false repetitions.
"""

from dataclasses import dataclass, field
from enum import Enum
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
    fluidity_score_pct: float = 100.0


class RepetitionStateMachine:
    """Finite State Machine tracking repetition progress and phase timing with hysteresis."""

    def __init__(
        self,
        rest_threshold_deg: float = 25.0,
        rising_start_deg: float = 32.0,
        target_min_deg: float = 80.0,
        target_max_deg: float = 100.0,
        min_hold_time_sec: float = 0.5,
        arm: str = "right",
    ):
        """Initialize the state machine.

        Args:
            rest_threshold_deg: Upper bound for REST state (hysteresis low trigger).
            rising_start_deg: Lower bound to enter RISING state (hysteresis high trigger).
            target_min_deg: Minimum abduction required for target achievement.
            target_max_deg: Upper limit of target abduction range.
            min_hold_time_sec: Minimum duration in target zone to fulfill hold phase.
            arm: Active arm being tracked ('left' or 'right').
        """
        assert rising_start_deg > rest_threshold_deg, (
            "rising_start_deg must be strictly greater than rest_threshold_deg for hysteresis"
        )
        self.rest_threshold_deg = rest_threshold_deg
        self.rising_start_deg = rising_start_deg
        self.target_min_deg = target_min_deg
        self.target_max_deg = target_max_deg
        self.min_hold_time_sec = min_hold_time_sec
        self.arm = arm

        # State tracking
        self.current_phase: ExercisePhase = ExercisePhase.REST
        self.completed_reps: List[RepetitionMetrics] = []
        self._rep_counter: int = 0

        # Phase timestamps
        self._concentric_start_time: Optional[float] = None
        self._hold_start_time: Optional[float] = None
        self._eccentric_start_time: Optional[float] = None
        self._hold_duration_accumulated: float = 0.0

        # Peak and compensation tracking during current repetition
        self._current_peak_angle: float = 0.0
        self._max_lean: float = 0.0
        self._max_shrug: float = 0.0
        self._min_elbow: float = 180.0
        self._max_drift: float = 0.0
        self._trajectory_times: List[float] = []
        self._trajectory_angles: List[float] = []

    @property
    def rep_count(self) -> int:
        """Total number of successfully completed repetitions."""
        return len(self.completed_reps)

    def set_arm(self, arm: str) -> None:
        """Switch active arm and reset current in-flight repetition state."""
        self.arm = arm
        self.reset_current_rep()

    def reset_current_rep(self) -> None:
        """Reset currently tracked repetition without clearing historical count."""
        self.current_phase = ExercisePhase.REST
        self._concentric_start_time = None
        self._hold_start_time = None
        self._eccentric_start_time = None
        self._hold_duration_accumulated = 0.0
        self._current_peak_angle = 0.0
        self._max_lean = 0.0
        self._max_shrug = 0.0
        self._min_elbow = 180.0
        self._max_drift = 0.0
        self._trajectory_times.clear()
        self._trajectory_angles.clear()

    def reset_all(self) -> None:
        """Clear all counters and historical records."""
        self.reset_current_rep()
        self.completed_reps.clear()
        self._rep_counter = 0

    def update(
        self,
        current_angle: Optional[float],
        timestamp_sec: float,
        current_lean: Optional[float] = None,
        current_shrug: Optional[float] = None,
        current_elbow: Optional[float] = None,
        current_drift: Optional[float] = None,
    ) -> Optional[RepetitionMetrics]:
        """Process one frame through the state machine.

        Args:
            current_angle: Current smoothed abduction angle in degrees (or None).
            timestamp_sec: Current monotonic timestamp in seconds.
            current_lean: Current lateral trunk lean in degrees.
            current_shrug: Current normalized shoulder shrug ratio.
            current_elbow: Current elbow extension angle in degrees.
            current_drift: Current 3D out-of-plane forward drift angle in degrees.

        Returns:
            A completed RepetitionMetrics instance if a repetition ended on this frame,
            otherwise None.
        """
        if current_angle is None:
            return None

        # Update telemetry extrema during any active movement
        if self.current_phase != ExercisePhase.REST:
            self._current_peak_angle = max(self._current_peak_angle, current_angle)
            self._trajectory_times.append(timestamp_sec)
            self._trajectory_angles.append(current_angle)
            if current_lean is not None:
                self._max_lean = max(self._max_lean, current_lean)
            if current_shrug is not None:
                self._max_shrug = max(self._max_shrug, current_shrug)
            if current_elbow is not None:
                self._min_elbow = min(self._min_elbow, current_elbow)
            if current_drift is not None:
                self._max_drift = max(self._max_drift, current_drift)

        completed_record: Optional[RepetitionMetrics] = None

        # State Transition Logic with Hysteresis
        if self.current_phase == ExercisePhase.REST:
            # Hysteresis: only enter RISING when angle crosses rising_start_deg (> rest_threshold_deg)
            if current_angle >= self.rising_start_deg:
                self.current_phase = ExercisePhase.RISING
                self._concentric_start_time = timestamp_sec
                self._current_peak_angle = current_angle
                self._hold_duration_accumulated = 0.0
                self._trajectory_times = [timestamp_sec]
                self._trajectory_angles = [current_angle]
                if current_lean is not None:
                    self._max_lean = current_lean
                if current_shrug is not None:
                    self._max_shrug = current_shrug
                if current_elbow is not None:
                    self._min_elbow = current_elbow
                if current_drift is not None:
                    self._max_drift = current_drift
                if current_elbow is not None:
                    self._min_elbow = current_elbow if current_elbow is not None else 180.0

        elif self.current_phase == ExercisePhase.RISING:
            # Check if entered target hold range
            if current_angle >= self.target_min_deg:
                self.current_phase = ExercisePhase.HOLD
                self._hold_start_time = timestamp_sec
            # If patient aborts and drops arm back into rest without reaching target
            elif current_angle <= self.rest_threshold_deg:
                # Aborted repetition: reset back to REST without incrementing count
                self.reset_current_rep()

        elif self.current_phase == ExercisePhase.HOLD:
            if self._hold_start_time is not None:
                self._hold_duration_accumulated = timestamp_sec - self._hold_start_time

            # If arm begins descending below target range
            if current_angle < self.target_min_deg - 5.0:  # 5 deg hysteresis buffer on hold exit
                self.current_phase = ExercisePhase.LOWERING
                self._eccentric_start_time = timestamp_sec

        elif self.current_phase == ExercisePhase.LOWERING:
            # Return to target zone (re-elevation)
            if current_angle >= self.target_min_deg:
                self.current_phase = ExercisePhase.HOLD
                self._hold_start_time = timestamp_sec

            # Hysteresis: only complete repetition when arm drops back below rest_threshold_deg
            elif current_angle <= self.rest_threshold_deg:
                self._rep_counter += 1

                # Calculate phase durations
                concentric_t = (
                    (self._hold_start_time - self._concentric_start_time)
                    if (self._hold_start_time and self._concentric_start_time)
                    else 0.0
                )
                hold_t = max(0.0, self._hold_duration_accumulated)
                eccentric_t = (
                    (timestamp_sec - self._eccentric_start_time)
                    if self._eccentric_start_time
                    else 0.0
                )
                total_t = (
                    (timestamp_sec - self._concentric_start_time)
                    if self._concentric_start_time
                    else (concentric_t + hold_t + eccentric_t)
                )

                # Calculate motor control smoothness (Fluidity score via Normalized Jerk)
                _, fluidity = calculate_trajectory_smoothness(
                    self._trajectory_times, self._trajectory_angles
                )

                completed_record = RepetitionMetrics(
                    rep_index=self._rep_counter,
                    arm=self.arm,
                    peak_abduction_deg=self._current_peak_angle,
                    target_reached=(self._current_peak_angle >= self.target_min_deg),
                    concentric_duration_sec=max(0.0, concentric_t),
                    hold_duration_sec=max(0.0, hold_t),
                    eccentric_duration_sec=max(0.0, eccentric_t),
                    total_duration_sec=max(0.0, total_t),
                    max_trunk_lean_deg=self._max_lean,
                    max_shrug_ratio=self._max_shrug,
                    min_elbow_angle_deg=self._min_elbow,
                    max_drift_deg=self._max_drift,
                    fluidity_score_pct=fluidity,
                )

                self.completed_reps.append(completed_record)
                self.reset_current_rep()

        return completed_record
