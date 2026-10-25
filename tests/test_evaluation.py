"""Unit tests for Phase 6 evaluation metrics and offline video analysis."""

import tempfile
from pathlib import Path
import cv2
import numpy as np
import pytest

from evaluate_dataset import ConfusionMatrix, analyze_video_file


def test_confusion_matrix_calculations():
    """Verify statistical metric formulas for binary classification."""
    # Scenario:
    # 10 True Positives (Correct labeled, Correct predicted)
    # 2 False Negatives (Correct labeled, A Corriger predicted)
    # 8 True Negatives (A Corriger labeled, A Corriger predicted)
    # 1 False Positive (A Corriger labeled, Correct predicted)
    # Total = 21
    cm = ConfusionMatrix(
        true_positive=10,
        false_negative=2,
        true_negative=8,
        false_positive=1,
    )

    assert cm.total == 21

    # Accuracy = (10 + 8) / 21 = 18 / 21 = ~0.8571
    assert pytest.approx(cm.accuracy, abs=1e-3) == (18.0 / 21.0)

    # Sensitivity / Recall = 10 / (10 + 2) = 10 / 12 = ~0.8333
    assert pytest.approx(cm.sensitivity, abs=1e-3) == (10.0 / 12.0)

    # Specificity = 8 / (8 + 1) = 8 / 9 = ~0.8889
    assert pytest.approx(cm.specificity, abs=1e-3) == (8.0 / 9.0)

    # Precision = 10 / (10 + 1) = 10 / 11 = ~0.9091
    assert pytest.approx(cm.precision, abs=1e-3) == (10.0 / 11.0)

    # F1-Score = 2 * (P * R) / (P + R)
    p = 10.0 / 11.0
    r = 10.0 / 12.0
    expected_f1 = 2 * (p * r) / (p + r)
    assert pytest.approx(cm.f1_score, abs=1e-3) == expected_f1


def test_confusion_matrix_zero_division_guard():
    """Verify zero division returns 0.0 safely instead of throwing an exception."""
    cm = ConfusionMatrix(0, 0, 0, 0)
    assert cm.total == 0
    assert cm.accuracy == 0.0
    assert cm.sensitivity == 0.0
    assert cm.specificity == 0.0
    assert cm.precision == 0.0
    assert cm.f1_score == 0.0


def test_analyze_video_file_on_synthetic_clip():
    """Verify analyze_video_file reads frames and returns evaluations on a synthetic test clip."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_video_path = Path(tmp_dir) / "synth_test.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(str(test_video_path), fourcc, 30.0, (320, 240))

        # Write 30 black frames
        for _ in range(30):
            frame = np.zeros((240, 320, 3), dtype=np.uint8)
            out.write(frame)
        out.release()

        evals, pred_label = analyze_video_file(test_video_path, arm="right")
        # Empty/black video has no detected human, should return A CORRIGER safely
        assert pred_label == "A CORRIGER"
        assert len(evals) == 0
