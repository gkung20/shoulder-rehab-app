"""Integration tests for Phase 1 end-to-end pipeline components."""

import numpy as np
import pytest

from src.geometry import Point2D, calculate_abduction_angle, PoseLandmarkIndex
from src.pose_detector import PoseDetector
from src.visualizer import draw_hud, draw_skeleton


def test_get_arm_landmarks_left_and_right():
    """Verify landmark indexing for left and right arms."""
    dummy_landmarks = [Point2D(x=float(i) / 100, y=float(i) / 100, visibility=0.9) for i in range(33)]

    # Left arm
    sh_l, hip_l, el_l, wr_l, ear_l = PoseDetector.get_arm_landmarks(dummy_landmarks, arm="left")
    assert sh_l == dummy_landmarks[PoseLandmarkIndex.LEFT_SHOULDER]
    assert hip_l == dummy_landmarks[PoseLandmarkIndex.LEFT_HIP]
    assert el_l == dummy_landmarks[PoseLandmarkIndex.LEFT_ELBOW]
    assert wr_l == dummy_landmarks[PoseLandmarkIndex.LEFT_WRIST]
    assert ear_l == dummy_landmarks[PoseLandmarkIndex.LEFT_EAR]

    # Right arm
    sh_r, hip_r, el_r, wr_r, ear_r = PoseDetector.get_arm_landmarks(dummy_landmarks, arm="right")
    assert sh_r == dummy_landmarks[PoseLandmarkIndex.RIGHT_SHOULDER]
    assert hip_r == dummy_landmarks[PoseLandmarkIndex.RIGHT_HIP]
    assert el_r == dummy_landmarks[PoseLandmarkIndex.RIGHT_ELBOW]
    assert wr_r == dummy_landmarks[PoseLandmarkIndex.RIGHT_WRIST]
    assert ear_r == dummy_landmarks[PoseLandmarkIndex.RIGHT_EAR]

    # Invalid arm
    with pytest.raises(ValueError):
        PoseDetector.get_arm_landmarks(dummy_landmarks, arm="head")


def test_pose_detector_handles_empty_or_black_frame():
    """Verify PoseDetector gracefully returns None when no human is present."""
    with PoseDetector() as detector:
        black_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = detector.detect(black_frame, timestamp_ms=100)
        assert result is None


def test_visualizer_rendering():
    """Verify draw_skeleton and draw_hud do not corrupt or crash on valid inputs."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    dummy_landmarks = [Point2D(x=0.5, y=0.5, visibility=0.9) for _ in range(33)]

    # Render skeleton
    frame = draw_skeleton(frame, dummy_landmarks, selected_arm="right", abduction_angle=88.5)
    assert frame.shape == (480, 640, 3)

    # Render HUD
    frame = draw_hud(frame, selected_arm="right", abduction_angle=88.5, fps=30.0, status_text="Test")
    assert frame.shape == (480, 640, 3)
    # Check that pixels were actually modified (not all zero anymore)
    assert np.any(frame > 0)
