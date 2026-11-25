"""Hands-free control: the free hand held above the head for 2 seconds (Phase 5.1).

The free hand is the one of the arm that is NOT exercising, so a movement of the working arm
(even up to 160 deg) never triggers it. The app turns the gesture into pause / resume during a
session, and Next / OK on Willy's screens. A ring fills around the wrist while it is held.
"""
from __future__ import annotations

from dataclasses import dataclass

NOSE, LEFT_EAR, RIGHT_EAR = 0, 7, 8
WRISTS = {"left": 15, "right": 16}


def head_top(landmarks, min_visibility):
    """The height of the head in the image (smaller y is higher), or None when unsure."""
    for index in (NOSE, LEFT_EAR, RIGHT_EAR):
        point = landmarks[index]
        if (point.visibility or 0) >= min_visibility:
            return point.y
    return None


@dataclass
class HandRaise:
    hold_sec: float = 2.0
    cooldown_sec: float = 3.0
    min_visibility: float = .6
    started: float | None = None
    cooldown_until: float = 0.
    progress: float = 0.
    wrist: tuple | None = None   # normalized (x, y) of the free wrist while it is raised

    def update(self, landmarks, working_arm, now):
        """True once when the free hand has been held above the head for `hold_sec`."""
        self.progress, self.wrist = 0., None
        if not landmarks or len(landmarks) < 33 or now < self.cooldown_until:
            self.started = None
            return False
        free = "left" if working_arm == "right" else "right"
        wrist = landmarks[WRISTS[free]]
        head = head_top(landmarks, self.min_visibility)
        if head is None or (wrist.visibility or 0) < self.min_visibility or wrist.y >= head:
            self.started = None
            return False
        if self.started is None:
            self.started = now
        self.wrist = (wrist.x, wrist.y)
        self.progress = min(1., (now - self.started) / self.hold_sec)
        if self.progress < 1.:
            return False
        self.started, self.cooldown_until, self.progress = None, now + self.cooldown_sec, 0.
        return True
