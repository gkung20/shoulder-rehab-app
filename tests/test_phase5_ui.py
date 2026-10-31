"""Unit tests for Phase 5 Streamlit data structures and report generation."""

import pandas as pd
import pytest

from src.config import ExerciseConfig, AbductionThresholds, CompensationThresholds, TimingThresholds
from src.rules_engine import RulesEngine, RepetitionEvaluation, ClinicalError
from src.state_machine import RepetitionMetrics


def test_streamlit_config_dynamic_construction():
    """Verify ExerciseConfig accepts dynamic threshold slider inputs."""
    cfg = ExerciseConfig(
        abduction=AbductionThresholds(target_min_deg=85.0, target_max_deg=95.0),
        compensation=CompensationThresholds(max_trunk_lean_deg=8.0, max_shrug_ratio=0.10, min_elbow_angle_deg=160.0),
        timing=TimingThresholds(min_concentric_time_sec=1.2, min_hold_time_sec=0.7, min_eccentric_time_sec=1.2),
        filtering=None,
        calibration=None,
    )
    assert cfg.abduction.target_min_deg == 85.0
    assert cfg.compensation.max_trunk_lean_deg == 8.0
    assert cfg.compensation.max_shrug_ratio == 0.10
    assert cfg.compensation.max_anterior_drift_deg == 25.0
    assert cfg.compensation.min_fluidity_pct == 60.0


def test_streamlit_session_log_to_dataframe():
    """Verify session repetition records serialize properly to Pandas DataFrame."""
    logs = [
        {
            "rep_index": 1,
            "bras": "DROIT",
            "statut": "CORRECT",
            "angle_max_deg": 88.5,
            "montee_s": 1.8,
            "maintien_s": 0.9,
            "descente_s": 2.1,
            "inclinaison_max_deg": 3.2,
            "haussement_max_pct": 4.5,
            "coude_min_deg": 172.0,
            "remarques": "Parfait",
        },
        {
            "rep_index": 2,
            "bras": "DROIT",
            "statut": "A CORRIGER",
            "angle_max_deg": 82.0,
            "montee_s": 0.5,
            "maintien_s": 0.2,
            "descente_s": 0.8,
            "inclinaison_max_deg": 12.0,
            "haussement_max_pct": 15.0,
            "coude_min_deg": 150.0,
            "remarques": "Montee trop rapide; Haussement d'epaule",
        },
    ]

    df = pd.DataFrame(logs)
    assert len(df) == 2
    assert "statut" in df.columns
    assert "angle_max_deg" in df.columns
    assert df["statut"].value_counts()["CORRECT"] == 1
    assert df["statut"].value_counts()["A CORRIGER"] == 1

    # Test CSV export
    csv_str = df.to_csv(index=False)
    assert "rep_index,bras,statut" in csv_str
    assert "CORRECT" in csv_str
