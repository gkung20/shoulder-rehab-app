"""Shared test helpers.

Tests that need a downloaded MediaPipe model use `requires_pose_model`: they run when the
model is installed (as in CI and on Marwane's PC) and skip with a clear reason otherwise.
"""
from pathlib import Path

import pytest

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
POSE_MODEL = MODELS_DIR / "pose_landmarker_full.task"

requires_pose_model = pytest.mark.skipif(
    not POSE_MODEL.exists(),
    reason="MediaPipe pose model missing: run 'python models/download_models.py pose_landmarker_full.task'",
)


@pytest.fixture(autouse=True)
def fresh_screen_cache():
    """Each test draws the exercise screen's static layer itself (it is cached between frames)."""
    from src.dashboard import _chrome
    _chrome.cache_clear()
    yield
