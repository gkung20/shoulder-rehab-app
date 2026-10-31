"""Unit tests for src/rules_engine.py clinical thresholds and feedback."""

import pytest

from src.config import ExerciseConfig, AbductionThresholds, CompensationThresholds, TimingThresholds
from src.rules_engine import RulesEngine, FeedbackLevel
from src.state_machine import ExercisePhase, RepetitionMetrics


@pytest.fixture
def test_engine():
    """Create a RulesEngine with explicit test thresholds."""
    config = ExerciseConfig(
        abduction=AbductionThresholds(target_min_deg=80.0, target_max_deg=100.0, overshoot_warn_deg=110.0),
        compensation=CompensationThresholds(
            max_trunk_lean_deg=10.0,
            max_shrug_ratio=0.12,
            min_elbow_angle_deg=155.0,
            max_anterior_drift_deg=25.0,
            min_fluidity_pct=60.0,
        ),
        timing=TimingThresholds(min_concentric_time_sec=1.0, min_hold_time_sec=0.5, min_eccentric_time_sec=1.0),
        filtering=None,
        calibration=None,
    )
    return RulesEngine(config=config)


def test_evaluate_perfect_repetition(test_engine):
    """Verify that a repetition adhering to all clinical guidelines evaluates as CORRECT."""
    rep = RepetitionMetrics(
        rep_index=1,
        arm="right",
        peak_abduction_deg=88.0,
        target_reached=True,
        concentric_duration_sec=2.0,
        hold_duration_sec=1.0,
        eccentric_duration_sec=2.2,
        total_duration_sec=5.2,
        max_trunk_lean_deg=4.0,       # < 10.0 deg
        max_shrug_ratio=0.04,         # < 0.12
        min_elbow_angle_deg=175.0,    # > 155.0 deg
    )

    eval_result = test_engine.evaluate_repetition(rep)
    assert eval_result.is_correct is True
    assert eval_result.status_label == "CORRECT"
    assert len(eval_result.reasons) == 0


def test_evaluate_repetition_with_shrug(test_engine):
    """Verify shoulder shrug flags an error in French."""
    rep = RepetitionMetrics(
        rep_index=2,
        arm="right",
        peak_abduction_deg=85.0,
        target_reached=True,
        concentric_duration_sec=2.0,
        hold_duration_sec=0.8,
        eccentric_duration_sec=1.5,
        total_duration_sec=4.3,
        max_trunk_lean_deg=3.0,
        max_shrug_ratio=0.19,         # > 0.12 EXCEEDED
        min_elbow_angle_deg=170.0,
    )

    eval_result = test_engine.evaluate_repetition(rep)
    assert eval_result.is_correct is False
    assert eval_result.status_label == "A CORRIGER"
    assert any("Haussement" in r for r in eval_result.reasons)


def test_evaluate_repetition_with_trunk_lean(test_engine):
    """Verify lateral trunk lean flags an error in French."""
    rep = RepetitionMetrics(
        rep_index=3,
        arm="left",
        peak_abduction_deg=90.0,
        target_reached=True,
        concentric_duration_sec=2.0,
        hold_duration_sec=0.8,
        eccentric_duration_sec=1.5,
        total_duration_sec=4.3,
        max_trunk_lean_deg=16.0,      # > 10.0 deg EXCEEDED
        max_shrug_ratio=0.03,
        min_elbow_angle_deg=170.0,
    )

    eval_result = test_engine.evaluate_repetition(rep)
    assert eval_result.is_correct is False
    assert any("Inclinaison" in r for r in eval_result.reasons)


def test_evaluate_repetition_with_bent_elbow(test_engine):
    """Verify bent elbow flags an error in French."""
    rep = RepetitionMetrics(
        rep_index=4,
        arm="right",
        peak_abduction_deg=85.0,
        target_reached=True,
        concentric_duration_sec=2.0,
        hold_duration_sec=0.8,
        eccentric_duration_sec=1.5,
        total_duration_sec=4.3,
        max_trunk_lean_deg=3.0,
        max_shrug_ratio=0.03,
        min_elbow_angle_deg=135.0,    # < 155.0 deg EXCEEDED
    )

    eval_result = test_engine.evaluate_repetition(rep)
    assert eval_result.is_correct is False
    assert any("Coude" in r for r in eval_result.reasons)


def test_evaluate_repetition_too_fast(test_engine):
    """Verify ballistic / uncontrolled movement flags speed error."""
    rep = RepetitionMetrics(
        rep_index=5,
        arm="right",
        peak_abduction_deg=85.0,
        target_reached=True,
        concentric_duration_sec=0.4,  # < 1.0s TOO FAST
        hold_duration_sec=0.1,        # < 0.5s TOO SHORT
        eccentric_duration_sec=0.3,   # < 1.0s TOO FAST
        total_duration_sec=0.8,
        max_trunk_lean_deg=3.0,
        max_shrug_ratio=0.03,
        min_elbow_angle_deg=175.0,
    )

    eval_result = test_engine.evaluate_repetition(rep)
    assert eval_result.is_correct is False
    assert any("Montee trop rapide" in r for r in eval_result.reasons)
    assert any("Descente trop rapide" in r for r in eval_result.reasons)


def test_session_summary_aggregation(test_engine):
    """Verify session summary tallies counts and error distribution accurately."""
    rep_good = RepetitionMetrics(1, "right", 85.0, True, 2.0, 1.0, 2.0, 5.0, 2.0, 0.02, 175.0)
    rep_shrug1 = RepetitionMetrics(2, "right", 85.0, True, 2.0, 1.0, 2.0, 5.0, 2.0, 0.20, 175.0)
    rep_shrug2 = RepetitionMetrics(3, "right", 85.0, True, 2.0, 1.0, 2.0, 5.0, 2.0, 0.18, 175.0)

    test_engine.evaluate_repetition(rep_good)
    test_engine.evaluate_repetition(rep_shrug1)
    test_engine.evaluate_repetition(rep_shrug2)

    assert test_engine.session.total_repetitions == 3
    assert test_engine.session.correct_repetitions == 1
    assert pytest.approx(test_engine.session.success_rate_percent, abs=1e-1) == 33.3

    most_common = test_engine.session.get_most_frequent_errors(top_n=1)
    assert len(most_common) == 1
    assert "Haussement" in most_common[0][0]
    assert most_common[0][1] == 2  # Happened twice


def test_evaluate_repetition_with_anterior_drift(test_engine):
    """Verify 3D forward arm drift flags an error in French."""
    rep = RepetitionMetrics(
        rep_index=6,
        arm="right",
        peak_abduction_deg=88.0,
        target_reached=True,
        concentric_duration_sec=2.0,
        hold_duration_sec=0.8,
        eccentric_duration_sec=1.5,
        total_duration_sec=4.3,
        max_trunk_lean_deg=3.0,
        max_shrug_ratio=0.03,
        min_elbow_angle_deg=170.0,
        max_drift_deg=32.0,          # > 25.0 deg EXCEEDED
    )

    eval_result = test_engine.evaluate_repetition(rep)
    assert eval_result.is_correct is False
    assert any("avant" in r.lower() or "hors plan" in r.lower() for r in eval_result.reasons)


def test_evaluate_repetition_with_jerky_motion(test_engine):
    """Verify lack of motor smoothness / jerky movement flags an error."""
    rep = RepetitionMetrics(
        rep_index=7,
        arm="right",
        peak_abduction_deg=88.0,
        target_reached=True,
        concentric_duration_sec=2.0,
        hold_duration_sec=0.8,
        eccentric_duration_sec=1.5,
        total_duration_sec=4.3,
        max_trunk_lean_deg=3.0,
        max_shrug_ratio=0.03,
        min_elbow_angle_deg=170.0,
        max_drift_deg=5.0,
        fluidity_score_pct=35.0,     # < 60% EXCEEDED
    )

    eval_result = test_engine.evaluate_repetition(rep)
    assert eval_result.is_correct is False
    assert any("saccade" in r.lower() or "fluidite" in r.lower() for r in eval_result.reasons)


def test_live_feedback_cues(test_engine):
    """Verify real-time live cues in French."""
    # Shrug warning takes highest priority
    fb_shrug = test_engine.evaluate_live_frame(
        current_angle=60.0, current_lean=0.0, current_shrug=0.25, current_elbow=175.0, current_phase=ExercisePhase.RISING
    )
    assert fb_shrug.level == FeedbackLevel.WARNING
    assert "epaule basse" in fb_shrug.message.lower()

    # Trunk lean warning
    fb_lean = test_engine.evaluate_live_frame(
        current_angle=60.0, current_lean=20.0, current_shrug=0.02, current_elbow=175.0, current_phase=ExercisePhase.RISING
    )
    assert fb_lean.level == FeedbackLevel.WARNING
    assert "tronc droit" in fb_lean.message.lower()

    # Anterior drift warning
    fb_drift = test_engine.evaluate_live_frame(
        current_angle=60.0,
        current_lean=2.0,
        current_shrug=0.02,
        current_elbow=175.0,
        current_phase=ExercisePhase.RISING,
        current_drift=35.0,
    )
    assert fb_drift.level == FeedbackLevel.WARNING
    assert "plan du corps" in fb_drift.message.lower()

    # Apex hold encouragement
    fb_hold = test_engine.evaluate_live_frame(
        current_angle=90.0, current_lean=2.0, current_shrug=0.02, current_elbow=175.0, current_phase=ExercisePhase.HOLD
    )
    assert fb_hold.level == FeedbackLevel.SUCCESS
    assert "maintenez" in fb_hold.message.lower()
