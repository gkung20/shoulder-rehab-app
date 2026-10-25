"""Signal filtering and smoothing for biomechanical angles and landmark jitter.

Implements Exponential Moving Average (EMA), equivalent to a lerp() damping
commonly used in game camera tracking and physical simulation.
"""

from typing import Dict, Optional


class ExponentialSmoother:
    """Exponential Moving Average (EMA) filter for scalar streams."""

    def __init__(self, alpha: float = 0.35):
        """Initialize the filter.

        Args:
            alpha: Smoothing factor in range (0.0, 1.0].
                   Higher alpha = more responsive, less smoothing.
                   Lower alpha = smoother, slight temporal lag.
        """
        if not (0.0 < alpha <= 1.0):
            raise ValueError(f"Smoothing factor alpha must be in (0.0, 1.0], got {alpha}")
        self.alpha = alpha
        self._value: Optional[float] = None

    def update(self, raw_value: Optional[float], is_valid: bool = True) -> Optional[float]:
        """Update filter with new frame measurement.

        Args:
            raw_value: New raw numerical sample (or None if unmeasurable).
            is_valid: Flag indicating whether landmark visibility is acceptable.
                      If False, the update is rejected and the last valid value is preserved.

        Returns:
            Smoothed value, or None if no valid sample has been observed.
        """
        if raw_value is None or not is_valid:
            return self._value

        if self._value is None:
            # First observation: initialize directly without lag
            self._value = float(raw_value)
        else:
            # EMA formula: S_t = alpha * X_t + (1 - alpha) * S_{t-1}
            # (In game dev terminology: lerp(self._value, raw_value, self.alpha))
            self._value = (self.alpha * float(raw_value)) + ((1.0 - self.alpha) * self._value)

        return self._value

    @property
    def value(self) -> Optional[float]:
        """Current smoothed value."""
        return self._value

    def reset(self) -> None:
        """Reset the filter state."""
        self._value = None


class MultiMetricSmoother:
    """Convenience container for smoothing multiple exercise metrics simultaneously."""

    def __init__(self, alpha: float = 0.35):
        self.alpha = alpha
        self._smoothers: Dict[str, ExponentialSmoother] = {}

    def get_smoother(self, name: str) -> ExponentialSmoother:
        """Retrieve or lazily create a smoother for the given metric."""
        if name not in self._smoothers:
            self._smoothers[name] = ExponentialSmoother(alpha=self.alpha)
        return self._smoothers[name]

    def update(self, name: str, raw_value: Optional[float], is_valid: bool = True) -> Optional[float]:
        """Update a specific metric smoother."""
        return self.get_smoother(name).update(raw_value, is_valid=is_valid)

    def reset_all(self) -> None:
        """Reset all metric filters."""
        for smoother in self._smoothers.values():
            smoother.reset()
