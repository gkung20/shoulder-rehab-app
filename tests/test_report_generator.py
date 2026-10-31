"""Unit tests for src/report_generator.py clinical PDF reporting."""

from pathlib import Path
import pytest

from src.report_generator import generate_clinical_pdf_report
from src.rules_engine import ClinicalError, RepetitionEvaluation, SessionSummary
from src.state_machine import RepetitionMetrics


def test_generate_pdf_empty_session():
    """Verify PDF generation succeeds gracefully on an empty session."""
    session = SessionSummary()
    pdf_bytes = generate_clinical_pdf_report(
        session_summary=session,
        arm="right",
        target_min=80.0,
        target_max=100.0,
        patient_id="TEST-EMPTY",
    )
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")


def test_generate_pdf_populated_session(tmp_path):
    """Verify PDF generation with multiple correct and compensatory repetitions."""
    session = SessionSummary()

    # Repetition 1: Correct
    rep1 = RepetitionMetrics(
        rep_index=1,
        arm="right",
        peak_abduction_deg=88.5,
        target_reached=True,
        concentric_duration_sec=1.8,
        hold_duration_sec=0.8,
        eccentric_duration_sec=2.0,
        total_duration_sec=4.6,
        max_trunk_lean_deg=3.5,
        max_shrug_ratio=0.04,
        min_elbow_angle_deg=175.0,
        max_drift_deg=8.0,
    )
    session.record(RepetitionEvaluation(
        rep_index=1,
        arm="right",
        is_correct=True,
        status_label="CORRECT",
        reasons=[],
        errors=[],
        metrics=rep1,
    ))

    # Repetition 2: Compensations
    rep2 = RepetitionMetrics(
        rep_index=2,
        arm="right",
        peak_abduction_deg=92.0,
        target_reached=True,
        concentric_duration_sec=0.5,
        hold_duration_sec=0.2,
        eccentric_duration_sec=0.6,
        total_duration_sec=1.3,
        max_trunk_lean_deg=14.0,
        max_shrug_ratio=0.18,
        min_elbow_angle_deg=145.0,
        max_drift_deg=32.0,
    )
    session.record(RepetitionEvaluation(
        rep_index=2,
        arm="right",
        is_correct=False,
        status_label="A CORRIGER",
        reasons=[
            "Haussement d'epaule excessif (18.0% > 12%)",
            "Inclinaison du tronc excessive (14.0 deg > 10 deg)",
            "Bras projete vers l'avant (32.0 deg > 25 deg)",
        ],
        errors=[
            ClinicalError("Haussement d'epaule excessif", "Haussement"),
            ClinicalError("Inclinaison du tronc", "Tronc"),
            ClinicalError("Bras projete vers l'avant (hors plan)", "Derive"),
        ],
        metrics=rep2,
    ))

    out_file = tmp_path / "bilan_test.pdf"
    pdf_bytes = generate_clinical_pdf_report(
        session_summary=session,
        arm="right",
        target_min=80.0,
        target_max=100.0,
        patient_id="TEST-PATIENT-42",
        output_path=out_file,
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 5000
    assert pdf_bytes.startswith(b"%PDF-")
    assert out_file.exists()
    assert out_file.stat().st_size == len(pdf_bytes)
