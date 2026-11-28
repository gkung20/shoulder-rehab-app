"""Phase 9.2: Willy points at what he talks about, looks at it, and has a livelier idle state."""
from dataclasses import replace
import random
from types import SimpleNamespace

import numpy as np
import pytest

from src.config import ExerciseConfig
from src.dashboard import WILLY_BOX, render_dashboard
from src.layout import TOUR_ZONES
from src.session_processor import FrameAnalysis, SessionProcessor
from src.willy import ARM_MAX, POINT_HOLD, POINT_MIN, WillyGuide
from src.willy_overlay import Overlay

STATE = SimpleNamespace(status="", metrics={}, phase=None, cue=None)
PROCESSOR = SimpleNamespace(arm="right")


def center(rect):
    return (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2


def settle(guide, start, seconds=2., mode="paused", **values):
    pose = None
    for step in range(int(seconds * 20)):
        pose = guide.update(STATE, mode, PROCESSOR, now=start + step * .05, **values)
    return pose


def test_he_points_at_each_zone_of_the_tour_with_the_arm_on_its_side():
    guide = WillyGuide()
    trunk_x = WILLY_BOX[0] + guide.anchor("trunk", WILLY_BOX[2] - WILLY_BOX[0], WILLY_BOX[3] - WILLY_BOX[1])[0]
    angles = {}
    for zone, rect in TOUR_ZONES.items():
        aim = guide.point_at(center(rect), WILLY_BOX)
        if zone == "willy":
            assert aim is None  # the zone is Willy himself: nothing to point at
            continue
        side, angle, _ = aim
        assert side == ("L" if center(rect)[0] < trunk_x else "R"), zone
        assert POINT_MIN <= angle <= ARM_MAX
        angles[zone] = angle
    # Higher zone, higher arm: the top bar, then the count beside him, then the buttons at the bottom.
    assert angles["top_bar"] > angles["counter"] > angles["help_button"]
    assert guide.point_at(center(TOUR_ZONES["sound_button"]), WILLY_BOX)[:2] == ("R", ARM_MAX)  # right above him
    assert guide.point_at(center(TOUR_ZONES["close_button"]), WILLY_BOX)[:2] == ("R", POINT_MIN)  # right below


def test_the_higher_the_target_the_higher_the_arm():
    guide = WillyGuide()
    for x, spread in ((300, 40), (940, 100)):  # far away the arm stays nearer level
        angles = [guide.point_at((x, y), WILLY_BOX)[1] for y in range(800, 0, -50)]
        assert all(b >= a for a, b in zip(angles, angles[1:])) and angles[-1] > angles[0] + spread


def test_the_arm_reaches_the_zone_and_the_head_turns_toward_it():
    guide = WillyGuide()
    side, angle, look = guide.point_at(center(TOUR_ZONES["view_button"]), WILLY_BOX)
    guide.perform("point", now=0.)
    pose = settle(guide, 0.)
    assert (side, look) == ("L", "L")
    assert pose.arm_l == pytest.approx(angle, abs=1.) and pose.arm_r < 1.
    assert pose.look == "L" and guide._head_layer(pose) == f"head_{pose.eyes}_{pose.mouth}_lookL"
    turned = guide.render(208, 276).copy()
    guide.pose = replace(pose, look=None)
    assert np.abs(turned.astype(int) - guide.render(208, 276).astype(int)).sum() > 0  # a different head


def test_turned_heads_exist_for_every_face():
    guide = WillyGuide()
    for eyes in ("open", "blink", "happy"):
        for mouth in ("smile", "talk1", "talk2"):
            for side in ("L", "R"):
                assert f"head_{eyes}_{mouth}_look{side}" in guide.layers


def test_a_point_without_a_zone_lasts_as_long_as_the_line():
    guide = WillyGuide()
    guide.point_at(None, WILLY_BOX)
    guide.perform("point", now=0.)
    assert settle(guide, 0., 1.).arm_l > 60  # toward the screen, as before
    assert settle(guide, POINT_HOLD + 1., 1., speaking=True).arm_l > 60  # still talking
    assert settle(guide, POINT_HOLD + 3., 1.).arm_l < 5  # then the arm comes down


def test_the_dashboard_aims_willy_at_the_spotlight():
    processor = SessionProcessor(ExerciseConfig.from_yaml())
    camera = np.zeros((480, 640, 3), np.uint8)
    guide = WillyGuide()
    guide.perform("point")
    render_dashboard(camera, FrameAnalysis(0.), processor, mode="ready", willy=guide,
                     overlay=Overlay(spotlight=TOUR_ZONES["help_button"]))
    assert guide._aim[0] == "L" and guide.pose.look == "L"
    render_dashboard(camera, FrameAnalysis(0.), processor, mode="ready", willy=guide, overlay=Overlay())
    assert guide._aim is None and guide.pose.look is None


def test_when_nothing_happens_a_glance_then_a_stretch_or_a_wave_never_the_same_twice():
    guide = WillyGuide(rng=random.Random(3))
    moves, last, now = [], None, 0.
    while now < 400.:
        pose = guide.update(STATE, "ready", PROCESSOR, now=now)
        if guide._idle is not None and guide._idle != last:
            moves.append(guide._idle)
            last = guide._idle
        if guide._idle is not None and guide._idle[0] == "glance":
            assert pose.look == "L"  # toward the patient's image
        now += .1
    names = [name for name, _ in moves]
    assert 15. <= moves[0][1] <= 31.  # after the greeting wave and 13.5-28 quiet seconds
    assert all(a != b for a, b in zip(names, names[1:]))
    assert set(names[0::2]) == {"glance"} and set(names[1::2]) == {"stretch", "wave"}
    bigs = [start for name, start in moves if name != "glance"]
    assert all(30. <= b - a <= 60.5 for a, b in zip(bigs, bigs[1:]))


def test_no_idle_move_while_he_talks_or_the_patient_exercises():
    guide = WillyGuide()
    for step in range(1200):  # two minutes, a short line every 10 s
        now = step * .1
        guide.update(STATE, "ready", PROCESSOR, speaking=now % 10. < 1., now=now)
        assert guide._idle is None
    processor = SessionProcessor(ExerciseConfig.from_yaml())
    exercising = WillyGuide()
    for step in range(1200):
        exercising.update(FrameAnalysis(0., status="EN COURS"), "running", processor, now=step * .1)
        assert exercising._idle is None


def test_he_blinks_every_three_to_six_seconds():
    guide = WillyGuide(rng=random.Random(1))
    blinks, previous = [], "open"
    for step in range(30 * 120):
        pose = guide.update(STATE, "paused", PROCESSOR, speaking=True, now=step / 30)
        if pose.eyes == "blink" and previous != "blink":
            blinks.append(step / 30)
        previous = pose.eyes
    gaps = [b - a for a, b in zip(blinks, blinks[1:])]
    assert len(gaps) > 15 and all(2.9 <= gap <= 6.1 for gap in gaps)
