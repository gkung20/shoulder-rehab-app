"""Transparent guide silhouette drawn over the camera view.

The silhouette shows where to stand (a fixed, well-framed position) and performs
the abduction at a slow, steady rhythm the patient can follow. When the pose
model sees the patient, its outline turns green once the shoulders line up with
the silhouette's. It is a visual aid only: nothing here feeds counting or scoring.
"""
import math
import time

import cv2
import numpy as np

from src.avatar_motion import demonstration_angle
from src.geometry import PoseLandmarkIndex as I
from src.willy import exercise_screen_side

# Ideal framing, as fractions of the frame height (shoulder width) and size.
SHOULDER_WIDTH = .30      # x frame height
SHOULDER_Y = .40          # x frame height
FILL = (255, 255, 255)    # BGR
OUTLINE_IDLE = (214, 190, 82)    # soft teal
OUTLINE_GOOD = (90, 190, 60)     # green
OUTLINE_ADJUST = (40, 160, 245)  # orange


class SilhouetteGuide:
    def __init__(self):
        self.elapsed = 0.
        self._last = None

    def advance(self, mode, now=None):
        """The demo runs before and during the session, freezes in pause, restarts from rest after a break."""
        now = time.monotonic() if now is None else now
        if self._last is None or now - self._last > .75:
            self.elapsed = 0.  # just switched on: start from the resting position
        elif mode in ("ready", "running"):
            self.elapsed += now - self._last
        self._last = now
        return self.elapsed

    def step(self, target=90., hold=1.):
        """Current angle and the matching instruction."""
        hold = max(.5, hold)
        t = self.elapsed % (6.5 + hold)
        angle = demonstration_angle(self.elapsed, target, hold)
        label = "Repos" if t < 1.5 else "Levez" if t < 4. else "Maintenez" if t < 4. + hold else "Redescendez"
        return angle, label


def layout(width, height):
    """Pixel anchors of the ideal standing position in the displayed (possibly mirrored) frame."""
    sw = SHOULDER_WIDTH * height
    return {"cx": width / 2, "sy": SHOULDER_Y * height, "sw": sw}


def patient_alignment(landmarks, width, height, mirror=True, min_visibility=.5):
    """Compare the patient's shoulders with the silhouette's; None when they are not both visible.

    Returns (is_aligned, advice) with advice phrased from the patient's own point of view.
    """
    if not landmarks or len(landmarks) <= max(I.LEFT_SHOULDER, I.RIGHT_SHOULDER):
        return None
    left, right = landmarks[I.LEFT_SHOULDER], landmarks[I.RIGHT_SHOULDER]
    if min(getattr(left, "visibility", 1.), getattr(right, "visibility", 1.)) < min_visibility:
        return None
    xs = [p.x * width for p in (left, right)]
    if mirror:
        xs = [width - x for x in xs]
    mid_x, mid_y = sum(xs) / 2, (left.y + right.y) / 2 * height
    span = math.hypot(xs[0] - xs[1], (left.y - right.y) * height)
    ideal = layout(width, height)
    sw = ideal["sw"]
    scale, dx, dy = span / sw, (mid_x - ideal["cx"]) / sw, (mid_y - ideal["sy"]) / sw
    if scale < .78:
        return False, "Approchez-vous un peu"
    if scale > 1.28:
        return False, "Reculez un peu"
    if abs(dx) > .3:
        # In a mirror view, the image follows the patient's own left/right.
        toward_screen_right = dx < 0
        patient_right = toward_screen_right if mirror else not toward_screen_right
        return False, "Décalez-vous vers la " + ("droite" if patient_right else "gauche")
    if dy > .4:
        return False, "Baissez un peu la caméra"
    if dy < -.4:
        return False, "Montez un peu la caméra"
    return True, "Bien placé"


def _limb(mask, a, b, thickness):
    a, b = tuple(int(round(v)) for v in a), tuple(int(round(v)) for v in b)
    cv2.line(mask, a, b, 255, max(1, int(thickness)), cv2.LINE_AA)


def silhouette_mask(width, height, active_side, angle):
    """Filled figure (uint8 mask) at the ideal position, the active screen-side arm raised by `angle` degrees."""
    mask = np.zeros((height, width), np.uint8)
    p = layout(width, height)
    cx, sy, sw = p["cx"], p["sy"], p["sw"]
    head = (int(cx), int(sy - .70 * sw))
    cv2.ellipse(mask, head, (int(.25 * sw), int(.32 * sw)), 0, 0, 360, 255, -1, cv2.LINE_AA)
    cv2.rectangle(mask, (int(cx - .1 * sw), int(sy - .45 * sw)), (int(cx + .1 * sw), int(sy)), 255, -1)
    torso = np.array([(cx - .5 * sw, sy - .02 * sw), (cx + .5 * sw, sy - .02 * sw), (cx + .42 * sw, sy + .7 * sw),
                      (cx + .38 * sw, sy + 1.3 * sw), (cx - .38 * sw, sy + 1.3 * sw), (cx - .42 * sw, sy + .7 * sw)],
                     np.int32)
    cv2.fillPoly(mask, [torso], 255, cv2.LINE_AA)
    for sign in (-1, 1):  # legs, cropped by the frame when the camera is close
        hip = (cx + sign * .2 * sw, sy + 1.25 * sw)
        _limb(mask, hip, (cx + sign * .24 * sw, sy + 2.6 * sw), .3 * sw)
    for side, sign in (("L", -1), ("R", 1)):
        a = math.radians(angle if side == active_side else 6.)
        shoulder = np.array((cx + sign * .47 * sw, sy + .06 * sw))
        direction = np.array((sign * math.sin(a), math.cos(a)))
        elbow = shoulder + .62 * sw * direction
        wrist = elbow + .55 * sw * direction
        cv2.circle(mask, tuple(int(v) for v in shoulder), int(.13 * sw), 255, -1, cv2.LINE_AA)
        _limb(mask, shoulder, elbow, .2 * sw)
        _limb(mask, elbow, wrist, .16 * sw)
        cv2.circle(mask, tuple(int(v) for v in wrist), int(.1 * sw), 255, -1, cv2.LINE_AA)
    return mask


def draw_silhouette(frame, angle, active_side, alignment=None, opacity=.32):
    """Blend the transparent figure and its outline into a BGR frame in place."""
    h, w = frame.shape[:2]
    mask = silhouette_mask(w, h, active_side, angle)
    alpha = cv2.GaussianBlur(mask, (0, 0), max(1., h / 360)).astype(np.float32) / 255. * opacity
    frame[:] = (frame * (1 - alpha[..., None]) + np.array(FILL, np.float32) * alpha[..., None]).astype(np.uint8)
    color = OUTLINE_IDLE if alignment is None else OUTLINE_GOOD if alignment[0] else OUTLINE_ADJUST
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(frame, contours, -1, color, max(2, h // 240), cv2.LINE_AA)
    return frame


def silhouette_frame(video, analysis, mode, processor, mirror, guide, now=None):
    """Draw the guide on the displayed camera frame; returns (instruction, placement text, alignment)."""
    guide.advance(mode, now)
    abduction = processor.config.abduction
    target = (abduction.target_min_deg + abduction.target_max_deg) / 2
    angle, instruction = guide.step(target, processor.config.timing.min_hold_time_sec)
    h, w = video.shape[:2]
    alignment = patient_alignment(getattr(analysis, "landmarks", None), w, h, mirror)
    draw_silhouette(video, angle, exercise_screen_side(processor.arm, mirror), alignment)
    placement = "Placez-vous dans la silhouette" if alignment is None else alignment[1]
    return instruction, placement, alignment
