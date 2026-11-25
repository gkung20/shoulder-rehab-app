"""Every named rectangle of the screens, in the 1280x840 logical canvas.

The exercise screen, the patient buttons, the home screen and Willy's tour spotlight all
read their geometry from here, so moving a button moves its tour spotlight too.
`Rect` is a tuple (left, top, right, bottom), so it works wherever a 4-tuple did.
"""
from __future__ import annotations

from typing import NamedTuple

CANVAS_SIZE = (1280, 840)


class Rect(NamedTuple):
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self):
        return self.x1 - self.x0

    @property
    def height(self):
        return self.y1 - self.y0

    @property
    def center(self):
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    def contains(self, x, y):
        """Whether a point is inside (right and bottom edges excluded, like hit testing)."""
        return self.x0 <= x < self.x1 and self.y0 <= y < self.y1

    def encloses(self, other):
        other = Rect(*other)
        return self.x0 <= other.x0 and self.y0 <= other.y0 and other.x1 <= self.x1 and other.y1 <= self.y1

    def overlaps(self, other):
        other = Rect(*other)
        return self.x0 < other.x1 and other.x0 < self.x1 and self.y0 < other.y1 and other.y0 < self.y1

    def inset(self, dx, dy=None):
        """Smaller by dx/dy on every side (negative values grow it)."""
        dy = dx if dy is None else dy
        return Rect(self.x0 + dx, self.y0 + dy, self.x1 - dx, self.y1 - dy)

    def union(self, other):
        other = Rect(*other)
        return Rect(min(self.x0, other.x0), min(self.y0, other.y0), max(self.x1, other.x1), max(self.y1, other.y1))


CANVAS = Rect(0, 0, *CANVAS_SIZE)

# --- Exercise screen: top bar -------------------------------------------------------------
LANGUAGE_BUTTON = Rect(264, 22, 404, 76)
AVATAR_MALE_BUTTON = Rect(424, 22, 550, 76)
AVATAR_FEMALE_BUTTON = Rect(558, 22, 684, 76)
ARM_RIGHT_BUTTON = Rect(728, 22, 876, 76)
ARM_LEFT_BUTTON = Rect(884, 22, 1032, 76)
AUDIO_BUTTON = Rect(1070, 22, 1248, 76)

# --- Exercise screen: bottom bar ----------------------------------------------------------
MAIN_BUTTON = Rect(32, 750, 248, 806)
FINISH_BUTTON = Rect(264, 750, 420, 806)
VIEW_BUTTON = Rect(436, 750, 614, 806)
DETAILS_BUTTON = Rect(630, 750, 814, 806)
HELP_BUTTON = Rect(830, 750, 998, 806)
QUIT_BUTTON = Rect(1096, 750, 1248, 806)

# --- Exercise screen: panels and in-panel buttons -----------------------------------------
STAGE = Rect(32, 132, 860, 602)            # camera or the two avatars
COACH_PANEL = Rect(32, 132, 446, 602)      # left half of the stage in the avatar view
PATIENT_PANEL = Rect(446, 132, 860, 602)   # right half of the stage in the avatar view
CAMERA_THUMBNAIL = Rect(366, 494, 526, 584)
REPLAY_TOUR_BUTTON = Rect(82, 526, 330, 572)   # in the help panel
SILHOUETTE_ON_BUTTON = Rect(632, 144, 848, 184)  # "Masquer la silhouette": wider label
SILHOUETTE_OFF_BUTTON = Rect(712, 144, 848, 184)
GUIDANCE_COLUMN = Rect(894, 104, 1262, 442)
GUIDANCE = Rect(912, 128, 1252, 436)
COUNTER = Rect(904, 456, 1074, 626)
PROGRESS = Rect(912, 640, 1040, 668)
STEPS = Rect(26, 608, 866, 662)
RESULT_LINE = Rect(26, 664, 866, 718)
WILLY_BOX = Rect(1040, 440, 1248, 716)        # right column, beside the repetition count
WILLY_STAGE_BOX = Rect(470, 142, 836, 600)    # the exercise demo: Willy steps into the stage

# --- Home screen --------------------------------------------------------------------------
HOME_WILLY_BOX = Rect(70, 120, 590, 800)
HOME_BUBBLE = Rect(630, 170, 1220, 800)       # left, top and right edges are used
HOME_LANGUAGE_BUTTON = Rect(1060, 28, 1240, 80)
HOME_REPLAY_BUTTON = Rect(820, 28, 1044, 80)
HOME_SETTINGS_BUTTON = Rect(596, 28, 804, 80)

# --- Willy's tour spotlight zones (exercise screen) ---------------------------------------
_PAD = 6  # spotlight margin around grouped buttons
TOUR_ZONES = {
    "top_bar": Rect(416, 16, 1256, 82),
    "avatar_buttons": AVATAR_MALE_BUTTON.union(AVATAR_FEMALE_BUTTON).inset(-_PAD),
    "arm_buttons": ARM_RIGHT_BUTTON.union(ARM_LEFT_BUTTON).inset(-_PAD),
    "sound_button": AUDIO_BUTTON.inset(-_PAD),
    "coach_panel": COACH_PANEL,
    "patient_panel": PATIENT_PANEL,
    "camera_thumbnail": CAMERA_THUMBNAIL,
    "view_button": VIEW_BUTTON,
    "guidance": GUIDANCE,
    "counter": COUNTER,
    "progress": PROGRESS,
    "steps": STEPS,
    "result_line": RESULT_LINE,
    "main_button": MAIN_BUTTON,
    "finish_button": FINISH_BUTTON,
    "details_button": DETAILS_BUTTON,
    "help_button": HELP_BUTTON,
    "close_button": QUIT_BUTTON,
    "willy": WILLY_BOX,
    "silhouette_button": SILHOUETTE_ON_BUTTON,
}
