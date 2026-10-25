"""Unit tests for src/smoothing.py Exponential Moving Average filters."""

import pytest
from src.smoothing import ExponentialSmoother, MultiMetricSmoother


def test_exponential_smoother_initialization():
    """Verify first sample initializes filter without lag."""
    smoother = ExponentialSmoother(alpha=0.3)
    assert smoother.value is None

    val = smoother.update(100.0)
    assert val == 100.0
    assert smoother.value == 100.0


def test_exponential_smoother_ema_math():
    """Verify EMA formula: S_t = alpha * X_t + (1 - alpha) * S_{t-1}."""
    alpha = 0.4
    smoother = ExponentialSmoother(alpha=alpha)
    smoother.update(10.0)  # S_0 = 10.0

    # Step 1: sample = 20.0
    # Expected: 0.4 * 20.0 + 0.6 * 10.0 = 8.0 + 6.0 = 14.0
    s1 = smoother.update(20.0)
    assert pytest.approx(s1, abs=1e-4) == 14.0

    # Step 2: sample = 20.0
    # Expected: 0.4 * 20.0 + 0.6 * 14.0 = 8.0 + 8.4 = 16.4
    s2 = smoother.update(20.0)
    assert pytest.approx(s2, abs=1e-4) == 16.4


def test_exponential_smoother_rejects_invalid_frames():
    """Verify filter preserves previous valid state when frame is flagged invalid."""
    smoother = ExponentialSmoother(alpha=0.5)
    smoother.update(50.0)
    smoother.update(60.0)  # S_1 = 55.0

    # Low visibility frame: raw sample is 10.0 but is_valid=False
    s_invalid = smoother.update(10.0, is_valid=False)
    assert s_invalid == 55.0

    # None raw sample
    s_none = smoother.update(None)
    assert s_none == 55.0


def test_exponential_smoother_reset():
    """Verify reset clears state."""
    smoother = ExponentialSmoother(alpha=0.5)
    smoother.update(50.0)
    smoother.reset()
    assert smoother.value is None


def test_multi_metric_smoother():
    """Verify container isolates different metrics correctly."""
    multi = MultiMetricSmoother(alpha=0.5)
    multi.update("abduction", 10.0)
    multi.update("lean", 0.0)

    assert multi.get_smoother("abduction").value == 10.0
    assert multi.get_smoother("lean").value == 0.0

    multi.reset_all()
    assert multi.get_smoother("abduction").value is None
    assert multi.get_smoother("lean").value is None
