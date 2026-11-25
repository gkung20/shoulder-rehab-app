"""Gentle stop rules during a session (Phase 4.3): time, fatigue, and repeated pain.

Plain logic, fed by the app with each counted movement and the active session time. It only
suggests: the app turns "fatigue" into a line from Willy, and "time_up" or "end" into a kind
end of the session. Thresholds come from `safety:` in config/exercise_config.yaml and the plan.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SafetyMonitor:
    max_minutes: float = 15.
    fatigue_drop_deg: float = 15.
    window: int = 3
    compensation_streak: int = 3
    cooldown_sec: float = 180.
    max_pain_stops: int = 2
    peaks: list = field(default_factory=list)
    streak: int = 0
    pain_stops: int = 0
    last_fatigue: float | None = None
    time_said: bool = False

    @classmethod
    def from_config(cls, safety, plan):
        return cls(max_minutes=float(plan.max_session_min), fatigue_drop_deg=safety.fatigue_drop_deg,
                   window=safety.fatigue_window_reps, compensation_streak=safety.compensation_streak,
                   cooldown_sec=safety.fatigue_cooldown_sec, max_pain_stops=safety.max_pain_stops)

    def on_rep(self, peak, quality, issues, now):
        """A counted movement; returns "fatigue" when a break should be suggested."""
        if peak is not None:
            self.peaks.append(float(peak))
        self.streak = self.streak + 1 if quality == "to_fix" and issues else 0
        tired = self.streak >= self.compensation_streak
        n = self.window
        if len(self.peaks) >= 2 * n:
            first = sum(self.peaks[:n]) / n
            last = sum(self.peaks[-n:]) / n
            tired = tired or first - last > self.fatigue_drop_deg
        if not tired or (self.last_fatigue is not None and now - self.last_fatigue < self.cooldown_sec):
            return None
        self.last_fatigue, self.streak = now, 0
        return "fatigue"

    def time_up(self, active_sec):
        """True once, when the active session time reaches the plan's longest session."""
        if self.time_said or active_sec < self.max_minutes * 60:
            return False
        self.time_said = True
        return True

    def on_pain_stop(self):
        """"It hurts" was pressed; "end" when it's the limit for one session."""
        self.pain_stops += 1
        return "end" if self.pain_stops >= self.max_pain_stops else None
