"""Follow only the patient when several people are in view (Phase 5.3).

When a session starts, the lock takes the most prominent person (the widest shoulders: the
one closest to the camera). Afterwards it follows whoever is closest to the patient's last
position and size, and refuses anyone too far from it: someone walking behind is ignored,
and a stranger alone in front is not the patient. Willy then says he can't see the patient
(the usual lost-tracking line) until they come back to their place.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12


def _torso(landmarks, min_visibility=.5):
    """(centre x, centre y, shoulder width) in image units, or None when the shoulders are unclear."""
    if not landmarks or len(landmarks) < 33:
        return None
    left, right = landmarks[LEFT_SHOULDER], landmarks[RIGHT_SHOULDER]
    if min(left.visibility or 0, right.visibility or 0) < min_visibility:
        return None
    return ((left.x + right.x) / 2, (left.y + right.y) / 2, math.hypot(left.x - right.x, left.y - right.y))


@dataclass
class PersonLock:
    max_jump: float = .25        # how far (image units) the patient's chest may be from their last place
    max_size_change: float = .4  # and how much their shoulder width may change (40%)
    center: tuple | None = None
    width: float = 0.

    def reset(self):
        self.center, self.width = None, 0.

    def choose(self, poses):
        """Index of the patient among `poses` [(landmarks, world)], or None when they're not there."""
        torsos = [(_torso(landmarks), index) for index, (landmarks, _) in enumerate(poses)]
        torsos = [(t, i) for t, i in torsos if t is not None]
        if not torsos:
            return None
        if self.center is None:
            torso, index = max(torsos, key=lambda item: item[0][2])  # the closest person
        else:
            def distance(item):
                (x, y, width), _ = item
                return math.dist((x, y), self.center) + abs(width - self.width)
            torso, index = min(torsos, key=distance)
            x, y, width = torso
            if (math.dist((x, y), self.center) > self.max_jump
                    or abs(width - self.width) > self.max_size_change * self.width):
                return None
        self.center, self.width = torso[:2], torso[2]
        return index
