"""Transparent guide silhouette over the camera view: placement and follow-along movement."""
from types import SimpleNamespace

import numpy as np
import pytest

from src.config import ExerciseConfig
from src.dashboard import render_dashboard
from src.patient_controls import PatientControls, dashboard_action_at, patient_buttons
from src.session_processor import FrameAnalysis, SessionProcessor
from src.silhouette import SilhouetteGuide, layout, patient_alignment, silhouette_mask


def _landmarks(width, height, scale=1., shift=0., mirror=True):
    """Shoulders placed relative to the silhouette, given in displayed-frame terms."""
    ideal = layout(width, height)
    half = ideal["sw"] * scale / 2
    xs = [ideal["cx"] + shift * ideal["sw"] + half, ideal["cx"] + shift * ideal["sw"] - half]
    if mirror:
        xs = [width - x for x in xs]
    points = [SimpleNamespace(x=.5, y=.5, visibility=0.) for _ in range(33)]
    points[11] = SimpleNamespace(x=xs[0] / width, y=ideal["sy"] / height, visibility=.99)
    points[12] = SimpleNamespace(x=xs[1] / width, y=ideal["sy"] / height, visibility=.99)
    return points


def test_alignment_advice():
    w, h = 1280, 720
    assert patient_alignment(_landmarks(w, h), w, h) == (True, "Bien placé")
    assert patient_alignment(_landmarks(w, h, scale=.6), w, h)[1] == "Approchez-vous un peu"
    assert patient_alignment(_landmarks(w, h, scale=1.5), w, h)[1] == "Reculez un peu"
    # Patient appears too far to the screen's left; in a mirror they step to their right.
    assert patient_alignment(_landmarks(w, h, shift=-.6), w, h)[1] == "Décalez-vous vers la droite"
    assert patient_alignment(_landmarks(w, h, shift=-.6, mirror=False), w, h, mirror=False)[1] == "Décalez-vous vers la gauche"
    assert patient_alignment([], w, h) is None


def test_silhouette_raises_the_active_arm():
    w, h = 640, 360
    down, up = silhouette_mask(w, h, "R", 0.), silhouette_mask(w, h, "R", 90.)
    ideal = layout(w, h)
    row = int(ideal["sy"] + .06 * ideal["sw"])
    far_right = int(ideal["cx"] + ideal["sw"] * 1.4)
    assert up[row, far_right] > 0 and down[row, far_right] == 0
    assert silhouette_mask(w, h, "L", 90.)[row, w - far_right] > 0


def test_guide_follows_the_demo_cycle_and_freezes_in_pause():
    guide = SilhouetteGuide()
    guide.advance("ready", now=0.)
    labels = []
    for step in range(1, 90):
        guide.advance("running", now=step * .1)
        labels.append(guide.step(90., .5)[1])
    assert {"Repos", "Levez", "Maintenez", "Redescendez"} <= set(labels)
    frozen = guide.elapsed
    guide.advance("paused", now=9.)
    assert guide.elapsed == frozen
    guide.advance("running", now=20.)  # long gap: restart from rest
    assert guide.elapsed == 0.


def test_button_only_in_camera_view_and_toggles():
    controls = PatientControls(avatars=False)
    state = dict(mode="ready", avatars=False, silhouette=False)
    button = next(b for b in patient_buttons(**state) if b.action == "silhouette")
    x, y = (button.bounds[0] + button.bounds[2]) // 2, (button.bounds[1] + button.bounds[3]) // 2
    assert dashboard_action_at(x, y, **state) == "silhouette"
    assert controls.apply("silhouette") and controls.silhouette
    assert not any(b.action == "silhouette" for b in patient_buttons(mode="ready", avatars=True))
    assert not any(b.action == "silhouette" for b in patient_buttons(mode="ready", avatars=False, help_visible=True))


@pytest.mark.parametrize("mode", ["ready", "running", "paused"])
def test_dashboard_draws_silhouette_over_camera(mode):
    processor = SessionProcessor(ExerciseConfig.from_yaml())
    camera = np.full((720, 1280, 3), 40, np.uint8)
    plain = render_dashboard(camera, FrameAnalysis(0.), processor, mode=mode, avatars=False)
    guided = render_dashboard(camera, FrameAnalysis(0.), processor, mode=mode, avatars=False, silhouette=True)
    video = (slice(200, 560), slice(250, 640))
    assert np.abs(guided[video].astype(int) - plain[video].astype(int)).sum(axis=2).mean() > 10
