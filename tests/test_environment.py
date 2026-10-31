"""Sanity check for Phase 0: verify runtime environment, libraries, and config."""

from pathlib import Path
import pytest
import yaml


def test_core_imports():
    """Verify all required libraries are installed and importable."""
    import cv2
    import mediapipe as mp
    import numpy as np
    import streamlit

    assert cv2.__version__ is not None
    assert mp.__version__ is not None
    assert np.__version__ is not None
    assert streamlit.__version__ is not None


def test_mediapipe_tasks_pose_landmarker():
    """Verify modern MediaPipe Tasks PoseLandmarker loads with local task model."""
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision

    model_path = Path(__file__).resolve().parent.parent / "models" / "pose_landmarker_lite.task"
    assert model_path.exists(), f"Model file not found at {model_path}"
    assert model_path.stat().st_size > 1_000_000, "Model file appears incomplete"

    base_options = python.BaseOptions(model_asset_path=str(model_path))
    options = vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.IMAGE,
        num_poses=1,
    )
    with vision.PoseLandmarker.create_from_options(options) as landmarker:
        assert landmarker is not None


def test_exercise_config_file_integrity():
    """Verify config/exercise_config.yaml exists and contains all required sections."""
    config_path = Path(__file__).resolve().parent.parent / "config" / "exercise_config.yaml"
    assert config_path.exists(), f"Config file not found at {config_path}"

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert "thresholds" in data
    assert "abduction" in data["thresholds"]
    assert "compensation" in data["thresholds"]
    assert "timing" in data["thresholds"]
    assert "filtering" in data
    assert "calibration" in data

    # Verify placeholder values exist
    assert data["thresholds"]["abduction"]["target_min_deg"] == 80.0
    assert data["thresholds"]["compensation"]["max_trunk_lean_deg"] == 10.0
    assert data["thresholds"]["compensation"]["max_shrug_ratio"] == 0.12
    assert data["thresholds"]["compensation"]["min_elbow_angle_deg"] == 155.0
    assert data["thresholds"]["compensation"]["max_anterior_drift_deg"] == 25.0
