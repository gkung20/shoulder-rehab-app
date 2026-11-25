"""Synthetic MediaPipe-style landmarks for tests, previews and tools (never used live).

`body()` builds a standing person facing the camera, in "image-height units" like the
regression tests: the shoulders are 0.35 apart, the upper arm is 0.20 long and the
whole arm 0.36. Both arms can be raised sideways, the body can turn around the
vertical axis (`yaw`), move (`center`, `shift_y`) or sit (hips and knees hidden).
It returns `(normalized, world)`: 33 `Point2D` in [0, 1] image coordinates and
33 `Point3D` in metres-like body coordinates, as `PoseDetector` would.
"""
from __future__ import annotations

import math

from src.geometry import Point2D, Point3D

NOSE, L_EAR, R_EAR = 0, 7, 8
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28

HALF_SHOULDERS = .175
UPPER_ARM = .20
WHOLE_ARM = .36


def _arm(shoulder, angle, side):
    """Elbow and wrist for an arm raised sideways by `angle` degrees (side -1 = right)."""
    rad = math.radians(angle)
    sx, sy = shoulder
    elbow = (sx + side * UPPER_ARM * math.sin(rad), sy + UPPER_ARM * math.cos(rad))
    wrist = (sx + side * WHOLE_ARM * math.sin(rad), sy + WHOLE_ARM * math.cos(rad))
    return elbow, wrist


def body(right=0., left=0., *, width=640, height=480, visibility=1., mirrored=False, yaw=0.,
         center=.775, shift_y=0., seated=False, left_hand_up=False, right_hand_up=False,
         hip_visibility=None):
    """A synthetic person; see the module docstring. Angles in degrees."""
    hw = HALF_SHOULDERS
    # Body-space points: x offset from the body's vertical axis, y from the top.
    points = {i: (0., .1) for i in range(33)}
    points.update({
        NOSE: (0., .12), L_EAR: (hw * .35, .1), R_EAR: (-hw * .35, .1),
        R_SHOULDER: (-hw, .25), L_SHOULDER: (hw, .25),
        R_HIP: (-hw, .7), L_HIP: (hw, .7),  # straight below the shoulders: 0 deg = arm down
        R_KNEE: (-hw * .6, .85), L_KNEE: (hw * .6, .85),
        R_ANKLE: (-hw * .6, .98), L_ANKLE: (hw * .6, .98),
    })
    if seated:  # knees forward, so they appear just below the hips and the table hides both
        points.update({R_KNEE: (-hw * .6, .76), L_KNEE: (hw * .6, .76)})
    points[R_ELBOW], points[R_WRIST] = _arm(points[R_SHOULDER], right, -1)
    points[L_ELBOW], points[L_WRIST] = _arm(points[L_SHOULDER], left, 1)
    if left_hand_up:
        points[L_ELBOW], points[L_WRIST] = (hw + .03, .1), (hw * .5, -.02)
    if right_hand_up:
        points[R_ELBOW], points[R_WRIST] = (-hw - .03, .1), (-hw * .5, -.02)

    cos_yaw, sin_yaw = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    low = visibility if hip_visibility is None else hip_visibility
    if seated and hip_visibility is None:
        low = .1
    normalized, world = [], []
    for index in range(33):
        x, y = points[index]
        vis = low if index in (L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE) and low != visibility else visibility
        image_x = (center + x * cos_yaw) * height / width
        image_y = y + shift_y
        world_x, world_z = x * cos_yaw, x * sin_yaw
        if mirrored:
            image_x, world_x = 1 - image_x, -world_x
        normalized.append(Point2D(image_x, image_y, vis))
        world.append(Point3D(world_x, y - .5, world_z, vis))
    return normalized, world


def rep_angles(peak=90., fps=30, rest=30, rise=60, hold=30, settle=10):
    """Angles of one clean repetition: rest, gradual rise, hold, descent, rest."""
    return ([0.] * rest + [i * peak / rise for i in range(rise + 1)] + [peak] * hold
            + [peak - i * peak / rise for i in range(1, rise + 1)] + [0.] * settle)
