"""Phase 11: the CC0 MakeHuman bodies (woman and man), same frames, behind a physio setting."""
import json

import cv2
import numpy as np
import pytest

from src import silhouette
from src.physio_settings import DEVICE_FIELDS, SILHOUETTE_LABELS, SettingsForm
from src.user_profile import SILHOUETTE_BODIES, Plan, Profile

NEW = ("makehuman-female", "makehuman-male")
SIZES = ((1280, 720), (640, 360), (960, 720), (640, 480))


@pytest.fixture(autouse=True)
def classic_afterwards():
    yield
    silhouette.use_body("classic")


def meta(name):
    return json.loads((silhouette.body_dir(name) / "silhouette.json").read_text(encoding="utf-8"))


def coverage(name, angle):
    rgba = cv2.imread(str(silhouette.body_dir(name) / f"arm_{angle:03d}.png"), cv2.IMREAD_UNCHANGED)
    return rgba[..., 3] / 255.


@pytest.mark.parametrize("name", NEW)
def test_the_new_bodies_keep_the_frame_format(name):
    classic, frames = meta("classic"), meta(name)
    assert set(classic) <= set(frames)  # the same keys; the proportions are added
    assert frames["angles"] == classic["angles"] and set(range(0, 161, 10)) <= set(frames["angles"])
    width, height = frames["size"]
    for angle in frames["angles"]:
        rgba = cv2.imread(str(silhouette.body_dir(name) / f"arm_{angle:03d}.png"), cv2.IMREAD_UNCHANGED)
        assert rgba.shape == (height, width, 4) and rgba[..., 3].max() == 255
    (lx, ly), (rx, ry) = frames["shoulders"]
    assert ly == ry and 0 < lx < rx < width
    assert "MakeHuman" in frames["source"] and "CC0" in frames["source"]
    # The loader is the one the classic body uses.
    loaded = silhouette._Frames(silhouette.body_dir(name))
    assert loaded.angles == frames["angles"] and loaded.proportions != silhouette.Proportions()


@pytest.mark.parametrize("name", NEW)
def test_the_stored_proportions_match_the_frames(name):
    frames = meta(name)
    body = silhouette.Proportions.from_meta(frames)
    (lx, sy), (rx, _) = frames["shoulders"]
    width = rx - lx
    rest = coverage(name, 0) > .5
    rows = np.nonzero(rest.any(axis=1))[0]
    assert (sy - rows.min()) / width == pytest.approx(body.head, abs=.03)
    raised = coverage(name, 90) > .5
    # Where the exercising arm hangs at 0 deg (the rest of the body is the same at 90 deg). Its
    # fingertips pass in front of the thigh, so the lowest visible row is a little above the reach:
    # the half body is cut just below the hand, never through it.
    hanging_arm = rest & ~raised
    lowest = (np.nonzero(hanging_arm.any(axis=1))[0].max() - sy) / width
    assert body.reach - .3 <= lowest <= body.reach + .01
    centre = (lx + rx) / 2
    assert (np.nonzero(raised.any(axis=0))[0].max() - centre) / width == pytest.approx(body.arm_side, abs=.03)
    assert 1. < body.hips < body.reach


@pytest.mark.parametrize("name", NEW)
def test_the_new_bodies_are_framed_by_their_own_proportions(name):
    silhouette.use_body(name)
    body = silhouette._frames().proportions
    classic = silhouette.layout(1280, 720, body=silhouette.Proportions())["sw"]
    assert silhouette.layout(1280, 720)["sw"] < classic  # narrower shoulders: drawn a little smaller
    for width, height in SIZES:
        for side in ("R", "L"):
            ideal = silhouette.layout(width, height, side)
            assert ideal["sy"] - body.head * ideal["sw"] >= .04 * height, (width, height)
            assert ideal["sy"] + body.hips * ideal["sw"] <= .85 * height, (width, height)
            raised = silhouette.silhouette_coverage(width, height, side, 90.)
            columns = np.nonzero(raised.max(axis=0) > .05)[0]
            assert columns.min() > 0 and columns.max() < width - 1, (name, width, height, side)
            rows = np.nonzero(silhouette.silhouette_coverage(width, height, side, 5.).max(axis=1) > 0)[0]
            assert rows.max() < height - 1  # the half body stops at the hands' reach, inside the picture
        both = silhouette.silhouette_coverage(width, height, "both", 90.)
        columns = np.nonzero(both.max(axis=0) > .05)[0]
        assert columns.min() > 0 and columns.max() < width - 1, (name, width, height, "both")


def test_the_classic_body_stays_the_default_and_unknown_bodies_fall_back_to_it(tmp_path):
    assert silhouette.current_body() == "classic" and silhouette.body_dir("classic") == silhouette.ASSET_DIR
    assert silhouette._frames().proportions == silhouette.Proportions()
    assert Profile.load(tmp_path / "missing.json").silhouette_body == "classic"
    (tmp_path / "profile.json").write_text(json.dumps({"silhouette_body": "robot"}), encoding="utf-8")
    assert Profile.load(tmp_path / "profile.json").silhouette_body == "classic"
    assert silhouette.use_body("robot") == "classic"
    assert silhouette.use_body("makehuman-male") == "makehuman-male"
    assert silhouette._frames().dir == silhouette.ASSET_DIR / "makehuman-male"


def test_the_physio_picks_the_body_on_the_screen_page(tmp_path):
    assert ("silhouette_body", "Corps de la silhouette", "") in DEVICE_FIELDS
    form = SettingsForm(Plan(), page="device")
    seen = []
    for _ in SILHOUETTE_BODIES:
        seen.append(form.value_text("silhouette_body", "", "fr"))
        form.step("silhouette_body", 1)
    assert seen == [SILHOUETTE_LABELS[name] for name in SILHOUETTE_BODIES] and form.silhouette_body == "classic"
    form.step("silhouette_body", -1)
    assert form.silhouette_body == SILHOUETTE_BODIES[-1]
    profile = Profile.load(tmp_path / "profile.json")
    profile.silhouette_body = "makehuman-female"
    profile.save()
    assert Profile.load(tmp_path / "profile.json").silhouette_body == "makehuman-female"


def test_saving_the_setting_switches_the_body_on_screen(monkeypatch, tmp_path):
    from tests.app_fakes import ScriptedWindow, make_app
    app = make_app(monkeypatch, tmp_path, ScriptedWindow(), language="fr", tour_done=True)
    app.start()
    try:
        assert silhouette.current_body() == "classic"
        app.open_modal("settings")
        app.screens["settings"].on_action(app, "page:device")
        app.screens["settings"].on_action(app, "set:+:silhouette_body")
        app.screens["settings"].on_action(app, "settings_save")
        assert app.profile.silhouette_body == "makehuman-female" == silhouette.current_body()
        assert Profile.load(app.profile._path).silhouette_body == "makehuman-female"
    finally:
        app.close()


def test_the_licence_list_records_the_new_body():
    from pathlib import Path
    licences = (Path(__file__).resolve().parents[1] / "docs" / "licences.md").read_text(encoding="utf-8")
    row = next(line for line in licences.splitlines() if "assets/silhouette/makehuman-" in line)
    assert "CC0" in row and "MakeHuman" in row
