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
SHOULDER_WIDTH = .28      # x frame height (distance between shoulder joints)
SHOULDER_Y = .40          # x frame height
FILL = (176, 98, 10)      # BGR: deep blue body
RIM = (240, 196, 90)       # light blue rim
OUTLINE_IDLE = (250, 205, 95)    # light blue
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


# Anatomical outline in head-height units (H), drawn from the top of the head down.
# Right half of the body without arms; mirrored for the left half.
_BODY_HALF = [
    (0.00, 0.00), (0.22, 0.04), (0.36, 0.18), (0.41, 0.40), (0.39, 0.62), (0.33, 0.82), (0.24, 0.97),
    (0.19, 1.10), (0.21, 1.25), (0.42, 1.34), (0.66, 1.42), (0.82, 1.50),          # neck, trapezius
    (0.80, 1.80), (0.72, 2.10), (0.68, 2.45), (0.62, 2.80), (0.57, 3.05),          # chest, waist
    (0.63, 3.40), (0.68, 3.75), (0.65, 4.20), (0.56, 4.80), (0.50, 5.30),          # hips, thigh, knee
    (0.53, 5.75), (0.47, 6.35), (0.35, 6.90), (0.40, 7.15), (0.33, 7.32),          # calf, ankle, foot
    (0.13, 7.30), (0.13, 6.95), (0.16, 6.40), (0.15, 5.80), (0.13, 5.30),          # inner leg
    (0.12, 4.70), (0.07, 4.25), (0.00, 4.08),                                      # inner thigh, crotch
]
# One arm hanging straight, local frame: origin at the shoulder joint, y down the arm, x away from the body.
_ARM_OUTER = [(0.02, -0.14), (0.16, -0.08), (0.26, 0.10), (0.28, 0.36), (0.24, 0.68), (0.19, 0.98),
              (0.17, 1.28), (0.20, 1.50), (0.20, 1.80), (0.15, 2.12), (0.11, 2.36)]
_ARM_INNER = [(-0.10, 2.36), (-0.12, 2.06), (-0.15, 1.66), (-0.13, 1.40), (-0.13, 1.18),
              (-0.15, 0.86), (-0.17, 0.52), (-0.19, 0.26), (-0.12, 0.04)]
_SHOULDER = (0.80, 1.56)   # joint position in the body frame (H units)
_HEAD_UNITS_PER_SHOULDER = 1.60  # distance between both shoulder joints, in H


def _smooth(points, closed=True, steps=8):
    """Catmull-Rom curve through the control points, for organic contours."""
    pts = np.asarray(points, np.float64)
    n = len(pts)
    out = []
    for i in range(n if closed else n - 1):
        p0, p1, p2, p3 = (pts[(i + k) % n] if closed else pts[min(max(i + k, 0), n - 1)] for k in (-1, 0, 1, 2))
        for t in np.linspace(0, 1, steps, endpoint=False):
            out.append(.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                             + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    return np.asarray(out)


def _arm_shapes(shoulder, sign, angle_deg, unit):
    """Arm polygon + hand strokes, rotated outward (abduction) about the shoulder joint."""
    a = math.radians(angle_deg)
    across = np.array((sign * math.cos(a), -math.sin(a)))   # local x: away from the body
    along = np.array((sign * math.sin(a), math.cos(a)))      # local y: down the arm
    to_world = lambda x, y: shoulder + unit * (x * across + y * along)
    outline = _smooth(_ARM_OUTER + _ARM_INNER)
    polygon = np.array([to_world(x, y) for x, y in outline])
    palm = [to_world(.01 + .17 * math.cos(t), 2.58 + .26 * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 24)]
    strokes = []
    for x in (-.10, -.033, .033, .10):  # fingers, slightly spread
        strokes.append((to_world(x, 2.70), to_world(x * 1.6, 3.16 - abs(x) * .9), .085 * unit))
    strokes.append((to_world(.12, 2.44), to_world(.29, 2.80), .095 * unit))  # thumb points away from the body
    return polygon, np.array(palm), strokes


def silhouette_mask(width, height, active_side, angle, scale=2):
    """Filled anatomical figure (uint8 mask) at the ideal position, active screen-side arm raised by `angle`°."""
    big = np.zeros((height * scale, width * scale), np.uint8)
    p = layout(width, height)
    unit = p["sw"] / _HEAD_UNITS_PER_SHOULDER * scale
    cx, sy = p["cx"] * scale, p["sy"] * scale
    origin = np.array((cx, sy - _SHOULDER[1] * unit))  # top of the head
    half = _BODY_HALF
    body = [(x, y) for x, y in half] + [(-x, y) for x, y in reversed(half[1:-1])]
    contour = origin + _smooth(body, steps=6) * unit
    cv2.fillPoly(big, [np.round(contour * 16).astype(np.int32)], 255, cv2.LINE_AA, shift=4)
    for side, sign in (("L", -1), ("R", 1)):
        shoulder = origin + np.array((sign * _SHOULDER[0], _SHOULDER[1])) * unit
        polygon, palm, strokes = _arm_shapes(shoulder, sign, angle if side == active_side else 7., unit)
        for shape in (polygon, palm):
            cv2.fillPoly(big, [np.round(shape * 16).astype(np.int32)], 255, cv2.LINE_AA, shift=4)
        for a, b, thick in strokes:
            cv2.line(big, tuple(np.round(a).astype(int)), tuple(np.round(b).astype(int)), 255,
                     max(1, int(thick)), cv2.LINE_AA)
    return cv2.resize(big, (width, height), interpolation=cv2.INTER_AREA)


def draw_silhouette(frame, angle, active_side, alignment=None, opacity=.42):
    """Blend the translucent blue figure, with a light glowing outline, into a BGR frame in place."""
    h, w = frame.shape[:2]
    mask = silhouette_mask(w, h, active_side, angle)
    soft = mask.astype(np.float32) / 255.
    # Slightly lighter towards the edges, like the reference's rim light.
    inner = cv2.GaussianBlur(cv2.erode(mask, np.ones((3, 3), np.uint8), iterations=max(1, h // 120)), (0, 0), h / 90)
    rim = np.clip(soft - inner.astype(np.float32) / 255., 0, 1)
    fill = np.array(FILL, np.float32)
    light = np.array(RIM, np.float32)
    color = fill[None, None] * (1 - rim[..., None]) + light[None, None] * rim[..., None]
    alpha = (soft * opacity)[..., None]
    frame[:] = np.clip(frame * (1 - alpha) + color * alpha, 0, 255).astype(np.uint8)
    edge = OUTLINE_IDLE if alignment is None else OUTLINE_GOOD if alignment[0] else OUTLINE_ADJUST
    contours, _ = cv2.findContours((mask > 110).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    glow = np.zeros_like(frame)
    cv2.drawContours(glow, contours, -1, edge, max(3, h // 140), cv2.LINE_AA)
    glow = cv2.GaussianBlur(glow, (0, 0), max(1.5, h / 300))
    frame[:] = np.clip(frame.astype(np.int16) + glow.astype(np.int16) // 2, 0, 255).astype(np.uint8)
    cv2.drawContours(frame, contours, -1, edge, max(2, h // 300), cv2.LINE_AA)
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
