"""Unit tests for src/state_machine.py on synthetic angle trajectories."""

import pytest
from src.state_machine import ExercisePhase, RepetitionStateMachine, RepetitionMetrics


def test_clean_single_repetition():
    """Verify standard single repetition through REST -> RISING -> HOLD -> LOWERING -> REST."""
    sm = RepetitionStateMachine(
        rest_threshold_deg=25.0,
        rising_start_deg=32.0,
        target_min_deg=80.0,
        target_max_deg=100.0,
        min_hold_time_sec=0.5,
        arm="right",
    )

    t = 0.0
    dt = 0.1  # 10 Hz synthetic simulation step

    # 1. At Rest (10 deg for 1 second)
    for _ in range(10):
        rep = sm.update(current_angle=10.0, timestamp_sec=t)
        assert rep is None
        assert sm.current_phase == ExercisePhase.REST
        t += dt

    # 2. Concentric Raising Phase (10 deg -> 85 deg over 2.0 seconds)
    # Start of rising triggers when passing 32 deg
    for angle in [20.0, 30.0, 35.0, 50.0, 65.0, 80.0]:
        rep = sm.update(current_angle=angle, timestamp_sec=t)
        assert rep is None
        t += dt
    assert sm.current_phase == ExercisePhase.HOLD

    # 3. Hold Phase (85 deg for 1.0 second)
    for _ in range(10):
        rep = sm.update(current_angle=85.0, timestamp_sec=t)
        assert rep is None
        assert sm.current_phase == ExercisePhase.HOLD
        t += dt

    # 4. Eccentric Lowering Phase (85 deg -> 15 deg over 2.0 seconds)
    # Drops below 75 deg (80 - 5 hysteresis) -> enters LOWERING
    for angle in [74.0, 60.0, 45.0, 30.0]:
        rep = sm.update(current_angle=angle, timestamp_sec=t)
        assert rep is None
        assert sm.current_phase == ExercisePhase.LOWERING
        t += dt

    # Final frame: arm drops to 15 deg (<= rest_threshold_deg 25.0)
    rep = sm.update(current_angle=15.0, timestamp_sec=t)
    assert rep is not None
    assert isinstance(rep, RepetitionMetrics)
    assert rep.rep_index == 1
    assert rep.arm == "right"
    assert rep.target_reached is True
    assert pytest.approx(rep.peak_abduction_deg, abs=1e-1) == 85.0
    assert rep.hold_duration_sec > 0.8
    assert sm.rep_count == 1
    assert sm.current_phase == ExercisePhase.REST


def test_hysteresis_prevents_jitter_trigger():
    """Verify micro-fluctuations near thresholds do not cause rapid state toggling."""
    sm = RepetitionStateMachine(
        rest_threshold_deg=25.0,
        rising_start_deg=32.0,
        target_min_deg=80.0,
    )

    t = 0.0
    # Jitter around 28-30 deg (above rest 25, below rising 32)
    for angle in [26.0, 30.0, 27.0, 31.0, 29.0]:
        sm.update(current_angle=angle, timestamp_sec=t)
        # Should stay in REST because it never crossed rising_start_deg (32.0)
        assert sm.current_phase == ExercisePhase.REST
        t += 0.1

    # Now cross into RISING
    sm.update(current_angle=33.0, timestamp_sec=t)
    assert sm.current_phase == ExercisePhase.RISING
    t += 0.1

    # Jitter down to 28.0 deg (below rising start 32, but above rest 25)
    sm.update(current_angle=28.0, timestamp_sec=t)
    # Must remain in RISING due to hysteresis!
    assert sm.current_phase == ExercisePhase.RISING


def test_aborted_incomplete_repetition():
    """Verify an aborted repetition (raised to 50 deg then dropped) does not count."""
    sm = RepetitionStateMachine(
        rest_threshold_deg=25.0,
        rising_start_deg=32.0,
        target_min_deg=80.0,
    )

    t = 0.0
    sm.update(10.0, timestamp_sec=t)
    t += 0.5

    # Rise to 55 deg
    sm.update(35.0, timestamp_sec=t)
    t += 0.5
    sm.update(55.0, timestamp_sec=t)
    assert sm.current_phase == ExercisePhase.RISING
    t += 0.5

    # Drop back down to rest (15 deg) without reaching 80 deg
    rep = sm.update(15.0, timestamp_sec=t)
    assert rep is None
    assert sm.rep_count == 0
    assert sm.current_phase == ExercisePhase.REST


def test_consecutive_three_repetitions():
    """Verify multiple back-to-back repetitions."""
    sm = RepetitionStateMachine()
    t = 0.0

    def do_rep():
        nonlocal t
        # Rest
        sm.update(10.0, t); t += 0.5
        # Rise
        sm.update(40.0, t); t += 0.5
        sm.update(85.0, t); t += 0.5
        # Hold
        sm.update(88.0, t); t += 1.0
        # Lower
        sm.update(50.0, t); t += 0.5
        result = sm.update(15.0, t); t += 0.5
        return result

    r1 = do_rep()
    assert r1 is not None and r1.rep_index == 1
    r2 = do_rep()
    assert r2 is not None and r2.rep_index == 2
    r3 = do_rep()
    assert r3 is not None and r3.rep_index == 3

    assert sm.rep_count == 3


def test_telemetry_captures_compensatory_extrema():
    """Verify maximum trunk lean, shrug, and minimum elbow angle are preserved in metrics."""
    sm = RepetitionStateMachine()
    t = 0.0

    sm.update(current_angle=10.0, timestamp_sec=t, current_lean=2.0, current_shrug=0.02, current_elbow=178.0)
    t += 0.5

    # Raising with compensatory shrug and lean and forward drift
    sm.update(current_angle=40.0, timestamp_sec=t, current_lean=12.5, current_shrug=0.18, current_elbow=160.0, current_drift=28.5)
    t += 0.5

    # Apex: elbow bends to 142 deg
    sm.update(current_angle=88.0, timestamp_sec=t, current_lean=14.0, current_shrug=0.15, current_elbow=142.0, current_drift=15.0)
    t += 1.0

    # Lowering
    sm.update(current_angle=50.0, timestamp_sec=t, current_lean=5.0, current_shrug=0.05, current_elbow=170.0, current_drift=8.0)
    t += 0.5

    # Return to rest
    final_rep = sm.update(current_angle=15.0, timestamp_sec=t, current_lean=1.0, current_shrug=0.01, current_elbow=175.0, current_drift=0.0)

    assert final_rep is not None
    assert pytest.approx(final_rep.max_trunk_lean_deg, abs=1e-1) == 14.0
    assert pytest.approx(final_rep.max_shrug_ratio, abs=1e-3) == 0.18
    assert pytest.approx(final_rep.min_elbow_angle_deg, abs=1e-1) == 142.0
    assert pytest.approx(final_rep.max_drift_deg, abs=1e-1) == 28.5
