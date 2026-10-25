"""Unit tests for src/calibration.py baseline calibration routine."""

import time
import pytest
from src.calibration import CalibrationManager
from src.geometry import Point2D


def create_stationary_body_landmarks() -> list:
    """Create a 33-landmark skeleton in clean neutral resting stance."""
    landmarks = [Point2D(0.5, 0.5, 1.0) for _ in range(33)]

    # Left and right shoulders at y = 0.25, width = 0.30 (x = 0.35 and 0.65)
    landmarks[11] = Point2D(x=0.35, y=0.25, visibility=1.0)  # LEFT_SHOULDER
    landmarks[12] = Point2D(x=0.65, y=0.25, visibility=1.0)  # RIGHT_SHOULDER

    # Ears at y = 0.10
    landmarks[7] = Point2D(x=0.35, y=0.10, visibility=1.0)   # LEFT_EAR
    landmarks[8] = Point2D(x=0.65, y=0.10, visibility=1.0)   # RIGHT_EAR

    # Hips at y = 0.70
    landmarks[23] = Point2D(x=0.35, y=0.70, visibility=1.0)  # LEFT_HIP
    landmarks[24] = Point2D(x=0.65, y=0.70, visibility=1.0)  # RIGHT_HIP

    # Elbows hanging down along torso at y = 0.45
    landmarks[13] = Point2D(x=0.35, y=0.45, visibility=1.0)  # LEFT_ELBOW
    landmarks[14] = Point2D(x=0.65, y=0.45, visibility=1.0)  # RIGHT_ELBOW

    return landmarks


def test_calibration_manager_flow():
    """Verify standard calibration run finishes successfully."""
    calibrator = CalibrationManager(duration_sec=0.1, max_variance_ratio=0.1)
    calibrator.start(arm="right")
    assert calibrator.is_calibrating is True

    landmarks = create_stationary_body_landmarks()

    # Feed enough samples to fulfill calibration
    for _ in range(25):
        calibrator.update(landmarks, arm="right")

    time.sleep(0.12)  # Wait for duration_sec to elapse

    completed, msg = calibrator.update(landmarks, arm="right")
    assert completed is True
    assert "reussie" in msg.lower()
    assert calibrator.calibrated_data.is_calibrated is True

    # Baseline ear-to-shoulder distance should be approx 0.25 - 0.10 = 0.15
    assert pytest.approx(calibrator.calibrated_data.baseline_ear_shoulder_dist, abs=1e-2) == 0.15
    # Shoulder width should be approx 0.65 - 0.35 = 0.30
    assert pytest.approx(calibrator.calibrated_data.baseline_shoulder_width, abs=1e-2) == 0.30
