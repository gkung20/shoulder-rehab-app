"""Transparent 3D guide silhouette drawn over the camera view.

A 3D body (pre-rendered from body-1/Male-low.OBJ by tools/silhouette_frames/render_frames.py)
is blended see-through over the video. The silhouette shows where to stand (a fixed,
well-framed position) and performs the abduction at a slow, steady rhythm the patient can
follow. When the pose model sees the patient, its outline turns green once the shoulders line
up with the silhouette's. It is a visual aid only: nothing here feeds counting or scoring.

Half body: the abduction needs the head, shoulders, elbows and hips, not the legs, so the
silhouette stops at the hands' reach and fills the picture from there to the head. The patient
stands about a quarter closer to the screen than with the whole body (Marwane, 27 Nov).
"""
import json
import math
from pathlib import Path
import time

import cv2
import numpy as np

from src.avatar_motion import demonstration_angle
from src.geometry import PoseLandmarkIndex as I
from src.willy import exercise_screen_side

ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "silhouette"

# Body proportions, in shoulder widths (distance between the shoulder joints), measured on the frames.
HEAD_ABOVE_SHOULDERS = .89    # top of the head, above the shoulder joints
REACH_BELOW_SHOULDERS = 1.65  # fingertips of a hanging arm: where the half body stops
FADE = .15                    # the cut fades out over this height
ARM_REACH_SIDE = 2.0          # hand of the raised arm (90-100 deg), from the middle of the body
OTHER_SIDE = .75              # the hanging arm, on the other side
# Ideal framing: the head 5% below the top of the picture, the hands' reach at 98%.
TOP, BOTTOM, EDGE = .05, .98, .02     # x frame height, x frame height, x frame width
SHOULDER_WIDTH = (BOTTOM - TOP) / (HEAD_ABOVE_SHOULDERS + REACH_BELOW_SHOULDERS)  # x frame height (.37)
SHOULDER_Y = TOP + HEAD_ABOVE_SHOULDERS * SHOULDER_WIDTH                           # x frame height (.38)
# The hips (1.14 shoulder widths below the shoulders) must stay well inside the picture: the app
# measures the arm against the shoulder-hip line, and without the hips falls back to a rougher
# angle. Closer than 1.15x the ideal size, or shoulders more than .3 shoulder width too high or
# too low, the patient is asked to step back or to move the camera.
HIPS_BELOW_SHOULDERS = 1.14
TOO_CLOSE = 1.15
HEIGHT_TOLERANCE = .3
FILL = (176, 98, 10)      # BGR: deep blue body
OUTLINE_IDLE = (255, 215, 120)   # light blue rim
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


def layout(width, height, side=None):
    """Pixel anchors of the ideal position in the displayed (possibly mirrored) frame.

    `side` is the screen side of the raised arm ("R" or "L"). The body is centred, unless the
    raised hand would leave a narrow (4:3) picture: then it moves to the other side, just enough.
    """
    sw = SHOULDER_WIDTH * height
    cx = width / 2
    arm_limit, other_limit = width * (1 - EDGE) - ARM_REACH_SIDE * sw, width * EDGE + OTHER_SIDE * sw
    if side == "R":
        cx = max(min(cx, arm_limit), other_limit)
    elif side == "L":
        cx = min(max(cx, width - arm_limit), width - other_limit)
    return {"cx": cx, "sy": SHOULDER_Y * height, "sw": sw}


def half_body(channels, shoulders):
    """Coverage faded out below the hands' reach, and the rows under it dropped."""
    (lx, ly), (rx, ry) = shoulders
    width = float(np.hypot(rx - lx, ry - ly))
    reach = (ly + ry) / 2 + REACH_BELOW_SHOULDERS * width
    rows = np.arange(channels.shape[0], dtype=np.float32)
    t = np.clip((reach - rows) / (FADE * width), 0., 1.)
    keep = t * t * (3 - 2 * t)  # smoothstep: a soft edge, not a hard cut
    out = channels[:int(np.ceil(reach)) + 1].copy()
    out[..., 2] = (out[..., 2] * keep[:len(out), None]).astype(np.uint8)
    return out


def patient_alignment(landmarks, width, height, mirror=True, min_visibility=.5, side=None):
    """Compare the patient's shoulders with the silhouette's; None when they are not both visible.

    Returns (is_aligned, advice) with advice phrased from the patient's own point of view.
    `side` is the screen side of the exercising arm, as for `layout`.
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
    ideal = layout(width, height, side)
    sw = ideal["sw"]
    scale, dx, dy = span / sw, (mid_x - ideal["cx"]) / sw, (mid_y - ideal["sy"]) / sw
    if scale < .78:
        return False, "Approchez-vous un peu"
    if scale > TOO_CLOSE:
        return False, "Reculez un peu"
    if abs(dx) > .3:
        # In a mirror view, the image follows the patient's own left/right.
        toward_screen_right = dx < 0
        patient_right = toward_screen_right if mirror else not toward_screen_right
        return False, "Décalez-vous vers la " + ("droite" if patient_right else "gauche")
    if dy > HEIGHT_TOLERANCE:
        return False, "Baissez un peu la caméra"
    if dy < -HEIGHT_TOLERANCE:
        return False, "Montez un peu la caméra"
    return True, "Bonne position"  # no word that changes with the patient's gender


class _Frames:
    """3D body frames (assets/silhouette/), scaled once per video size and blended between 5° steps."""

    def __init__(self, asset_dir=ASSET_DIR):
        meta = json.loads((asset_dir / "silhouette.json").read_text(encoding="utf-8"))
        self.angles = meta["angles"]
        self.shoulders = np.asarray(meta["shoulders"], np.float32)
        self.dir = asset_dir
        self.size = tuple(meta["size"])
        self._cache = {}

    def _frame(self, index, width, height, side):
        key = (index, width, height, side)
        if key not in self._cache:
            if len(self._cache) > 80:
                self._cache.clear()
            rgba = cv2.imread(str(self.dir / f"arm_{self.angles[index]:03d}.png"), cv2.IMREAD_UNCHANGED)
            if rgba is None:
                raise FileNotFoundError(f"Silhouette introuvable : arm_{self.angles[index]:03d}.png")
            # Stored channels (BGRA on disk): R = shading, G = rim, A = coverage.
            channels = half_body(np.dstack([rgba[..., 2], rgba[..., 1], rgba[..., 3]]), self.shoulders)
            left, right = self.shoulders
            if side == "L":  # the frames raise the screen-right arm: mirror them
                channels = channels[:, ::-1]
                left, right = (self.size[0] - right[0], right[1]), (self.size[0] - left[0], left[1])
            ideal = layout(width, height, side)
            scale = ideal["sw"] / max(1., float(np.hypot(*(np.subtract(right, left)))))
            mid = (np.add(left, right)) / 2 * scale
            ox, oy = ideal["cx"] - mid[0], ideal["sy"] - mid[1]
            scaled = cv2.resize(channels, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
            # Keep only the part that lands inside the video.
            x0, y0 = int(round(ox)), int(round(oy))
            fx0, fy0 = max(0, -x0), max(0, -y0)
            fx1, fy1 = min(scaled.shape[1], width - x0), min(scaled.shape[0], height - y0)
            crop = scaled[fy0:fy1, fx0:fx1] if fx1 > fx0 and fy1 > fy0 else scaled[:0, :0]
            self._cache[key] = (crop, (x0 + fx0, y0 + fy0))
        return self._cache[key]

    def channels(self, width, height, side, angle):
        """Blend the two nearest frames: (shading, rim, coverage) uint8 crop and its placement."""
        angle = float(np.clip(angle, self.angles[0], self.angles[-1]))
        pos = float(np.interp(angle, self.angles, np.arange(len(self.angles))))
        i0 = int(pos); i1 = min(i0 + 1, len(self.angles) - 1); t = pos - i0
        a, at = self._frame(i0, width, height, side)
        if t < .04 or i1 == i0:
            return a, at
        b, _ = self._frame(i1, width, height, side)
        if a.shape != b.shape:
            return a, at
        return cv2.addWeighted(a, 1 - t, b, t, 0), at


_FRAMES = None


def _frames():
    global _FRAMES
    if _FRAMES is None:
        _FRAMES = _Frames()
    return _FRAMES


def silhouette_coverage(width, height, active_side, angle):
    """Coverage (0..1, float32, full video size) of the 3D body at the ideal position."""
    data, (x, y) = _frames().channels(width, height, active_side, angle)
    out = np.zeros((height, width), np.float32)
    out[y:y + data.shape[0], x:x + data.shape[1]] = data[..., 2] / 255.
    return out


def draw_silhouette(frame, angle, active_side, alignment=None, opacity=.30):
    """Blend the translucent 3D body into a BGR frame in place.

    Its body stays see-through (about 30%); the fresnel rim glows brighter in the
    placement colour so the outline reads clearly over any background.
    """
    h, w = frame.shape[:2]
    data, (x, y) = _frames().channels(w, h, active_side, max(5., angle))
    if data.size == 0:
        return frame
    full = (data.shape[1], data.shape[0])
    # The body is soft and smooth: colour it at half resolution, blend at full resolution.
    small = cv2.resize(data, (max(1, full[0] // 2), max(1, full[1] // 2)), interpolation=cv2.INTER_AREA)
    shade, rim, cover = cv2.split(small.astype(np.float32) * (1 / 255.))
    edge = OUTLINE_IDLE if alignment is None else OUTLINE_GOOD if alignment[0] else OUTLINE_ADJUST
    alpha = cv2.multiply(cover, np.clip(rim * .6 + opacity, 0, .92))
    base = cv2.multiply(shade * .6 + .55, 1 - rim)
    premultiplied = cv2.merge([(base * fill + rim * glow) * alpha for fill, glow in zip(FILL, edge)])
    premultiplied = cv2.resize(premultiplied, full, interpolation=cv2.INTER_LINEAR)
    keep = cv2.resize(1 - alpha, full, interpolation=cv2.INTER_LINEAR)
    region = frame[y:y + data.shape[0], x:x + data.shape[1]]
    blended = region.astype(np.float32) * keep[..., None] + premultiplied
    region[:] = np.clip(blended, 0, 255).astype(np.uint8)
    return frame


def silhouette_frame(video, analysis, mode, processor, mirror, guide, now=None):
    """Draw the guide on the displayed camera frame; returns (instruction, placement text, alignment)."""
    guide.advance(mode, now)
    abduction = processor.config.abduction
    target = (abduction.target_min_deg + abduction.target_max_deg) / 2
    angle, instruction = guide.step(target, processor.config.timing.min_hold_time_sec)
    h, w = video.shape[:2]
    side = exercise_screen_side(processor.arm, mirror)
    alignment = patient_alignment(getattr(analysis, "landmarks", None), w, h, mirror, side=side)
    draw_silhouette(video, angle, side, alignment)
    placement = "Placez-vous dans la silhouette" if alignment is None else alignment[1]
    return instruction, placement, alignment
