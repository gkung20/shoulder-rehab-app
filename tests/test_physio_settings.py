"""Physio settings: PIN (default 0000, hashed when changed, lockout), safe bounds, and the app flow."""
import json

import pytest

from src import layout as L
from src.config import ExerciseConfig
from src.i18n import tr
from src.physio_settings import (DEFAULT_PIN, FIELDS, LOCK_SECONDS, MAX_TRIES, PinPad, SettingsForm,
                                 check_pin, render_pin, render_settings, set_pin)
from src.user_profile import PLAN_BOUNDS, Plan, Profile
from tests.app_fakes import ScriptedWindow, make_app


def type_pin(pad, profile, pin, now=0.):
    result = None
    for digit in pin:
        result = pad.press(digit, profile, now)
    return result


def test_default_pin_opens_and_wrong_pins_lock_the_pad(tmp_path):
    profile = Profile.load(tmp_path / "p.json")
    assert check_pin(profile, DEFAULT_PIN) and not check_pin(profile, "1234")
    pad = PinPad()
    for attempt in range(MAX_TRIES):
        assert type_pin(pad, profile, "9999", now=10.) is None
    assert pad.locked(10.) and pad.message
    assert type_pin(pad, profile, DEFAULT_PIN, now=11.) is None  # locked: even the right PIN waits
    assert type_pin(pad, profile, DEFAULT_PIN, now=11. + LOCK_SECONDS) == "open"
    assert pad.press("back", profile, 0.) is None and pad.press("cancel", profile, 0.) == "cancel"


def test_changed_pin_is_stored_as_a_salted_hash(tmp_path):
    profile = Profile.load(tmp_path / "p.json")
    pad = PinPad(mode="new")
    assert type_pin(pad, profile, "4821") is None and pad.mode == "confirm"
    assert type_pin(pad, profile, "4822") is None and pad.mode == "new" and pad.message  # mismatch: start again
    type_pin(pad, profile, "4821")
    assert type_pin(pad, profile, "4821") == "changed"
    profile.save()
    stored = (tmp_path / "p.json").read_text(encoding="utf-8")
    assert "4821" not in stored and json.loads(stored)["pin_hash"]
    again = Profile.load(tmp_path / "p.json")
    assert check_pin(again, "4821") and not check_pin(again, DEFAULT_PIN)
    other = Profile.load(tmp_path / "q.json")
    set_pin(other, "4821")
    assert other.pin_salt != again.pin_salt and other.pin_hash != again.pin_hash
    with pytest.raises(ValueError):
        set_pin(other, "12a4")


def test_settings_steps_stay_inside_safe_bounds():
    form = SettingsForm(Plan())
    for _ in range(100):
        form.step("target_min_deg", +1)
        form.step("reps_per_set", -1)
    assert form.plan.target_min_deg == PLAN_BOUNDS["target_min_deg"][1]
    assert form.plan.target_max_deg >= form.plan.target_min_deg
    assert form.plan.reps_per_set == PLAN_BOUNDS["reps_per_set"][0]
    assert form.changed
    form.step("arm", +1)
    assert form.plan.arm == "right"
    form.step("arm", +1)
    form.step("arm", +1)
    assert form.plan.arm is None
    form.step("seated", +1)
    assert form.plan.seated and form.value_text("seated", "", "fr") == "Oui"
    form.step("hold_sec", +1)
    assert form.value_text("hold_sec", "s", "fr") == "1 s"
    form.step("hold_sec", +1)
    assert form.value_text("hold_sec", "s", "fr") == "1,5 s" and form.value_text("hold_sec", "s", "en") == "1.5 s"


@pytest.mark.parametrize("language", ["fr", "en"])
def test_pin_pad_and_settings_draw_in_both_languages(language):
    image, boxes = render_pin(PinPad(), (1600, 1000), language)
    assert image.shape == (1000, 1600, 3) and {a for a, _ in boxes} >= {"pin:0", "pin:ok", "pin:cancel"}
    image, boxes = render_settings(SettingsForm(Plan(), resting_angle=18., resting_date="25/11"), None, language)
    assert image.shape == (840, 1280, 3)
    actions = {a for a, _ in boxes}
    assert {"settings_save", "settings_cancel", "settings_pin"} <= actions
    assert all(f"set:+:{key}" in actions for key, _, _ in FIELDS)
    for _, bounds in boxes:
        assert L.CANVAS.encloses(bounds)
    for _, label, _ in FIELDS:  # every label has an English version
        assert tr(label, "en") != label


def physio(window):
    """On Willy's home: open the settings, type 0000, raise the target minimum once, save."""
    app = window.app
    step = getattr(window, "step", 0)
    if step == 0 and app.director.screen == "home" and app.modal is None:
        if window.click_action("open_settings", app.director.overlay.hit_boxes):
            window.step = 1
    elif step == 1 and app.modal == "pin":
        for _ in range(4):
            window.press("0")
        window.step = 2
    elif step == 2 and app.modal == "settings":
        window.click_action("set:+:target_min_deg", app.screens["settings"].hit_boxes)
        window.step = 3
    elif step == 3:
        window.click_action("settings_save", app.screens["settings"].hit_boxes)
        window.step = 4
    elif step == 4 and app.director.current is not None and app.director.current.line_id == "E8.01":
        window.press(27)  # Esc closes the app
        window.step = 5


def test_physio_changes_the_plan_from_willys_home(monkeypatch, tmp_path):
    window = ScriptedWindow(physio)
    app = make_app(monkeypatch, tmp_path, window, language="en", tour_done=True)
    assert app.run() == 0
    assert window.step == 5
    plan = Profile.load().current_plan(ExerciseConfig.from_yaml())
    assert plan.target_min_deg == 85 and app.processor.state_machine.target_min_deg == 85
    assert app.processor.plan.target_min_deg == 85
