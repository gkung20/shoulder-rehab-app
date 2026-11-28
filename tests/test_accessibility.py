"""Phase 10.2: large text, high contrast, slower speech and subtitles."""
from collections import OrderedDict
import threading

import pytest

from src import accessibility
from src.accessibility import Accessibility, contrast, readable
from src.audio_feedback import AudioCoach
from src.physio_settings import ACCESSIBILITY, SettingsForm
from src.speech import PiperSpeech, WindowsSpeech
from src.user_profile import Plan, Profile
from tests.screens import SIZE, drawn_texts, overlaps, screen_makers

# Willy's bubble is drawn over the screen on purpose: what it covers is hidden, not overlapping.
BUBBLE_OVER_CONTENT = {"dashboard_bubble"}


def test_the_wcag_contrast_formula():
    assert contrast((0, 0, 0), (255, 255, 255)) == pytest.approx(21)
    assert contrast((119, 119, 119), (255, 255, 255)) == pytest.approx(4.48, abs=.01)  # the classic #777 on white
    assert contrast((40, 40, 40), (40, 40, 40)) == 1
    dark = readable((112, 117, 122), (250, 250, 249))
    assert contrast(dark, (250, 250, 249)) >= 7 and dark[0] < 112  # darker, same hue
    light = readable((60, 60, 60), (26, 29, 32))
    assert contrast(light, (26, 29, 32)) >= 7 and light[0] > 60      # lighter on a dark button
    assert readable((0, 0, 0), (255, 255, 255)) == (0, 0, 0)          # already fine: unchanged


@pytest.mark.parametrize("language", ["fr", "en"])
def test_every_screen_still_fits_with_large_text(language):
    names = [name for name, _ in screen_makers(language)]
    texts = drawn_texts(language, large_text=True)
    assert set(texts) == set(names)
    width, height = SIZE
    for name, entries in texts.items():
        for box, text, *_ in entries:
            assert box[0] >= 0 and box[1] >= 0 and box[2] <= width and box[3] <= height, f"{name}: {text!r} leaves the window"
        if name not in BUBBLE_OVER_CONTENT:
            assert not overlaps(entries), f"{name}: texts overlap: {overlaps(entries)[:3]}"


def test_large_text_is_larger():
    normal = {n: e for n, e in drawn_texts("fr").items()}
    large = drawn_texts("fr", large_text=True)
    title = next(box for box, text, *_ in normal["settings_plan"] if text == "Réglages kiné")
    bigger = next(box for box, text, *_ in large["settings_plan"] if text == "Réglages kiné")
    assert (bigger[3] - bigger[1]) == pytest.approx(1.25 * (title[3] - title[1]), rel=.12)


@pytest.mark.parametrize("language", ["fr", "en"])
def test_high_contrast_makes_every_text_readable(language):
    texts = drawn_texts(language, high_contrast=True, large_text=True)
    for name, entries in texts.items():
        for box, text, ink, behind in entries:
            assert contrast(ink, behind) >= 4.5, f"{name}: {text!r} is {contrast(ink, behind):.2f}:1"


def test_slower_speech_changes_both_voices():
    coach = AudioCoach(enabled=False, length_scale=1.3, speech_rate=130)
    coach.set_slow(True)
    assert coach.length_scale == pytest.approx(1.3 * 1.2) and coach.speech_rate == pytest.approx(104)
    coach.set_slow(False)
    assert coach.length_scale == pytest.approx(1.3) and coach.speech_rate == pytest.approx(130)

    from piper import SynthesisConfig
    piper = object.__new__(PiperSpeech)
    piper.willy_pitch, piper._cache = 1.45, OrderedDict(a=b"old")
    piper.settings = SynthesisConfig(length_scale=1.3 * 1.45)
    piper.set_speed(1.56)
    assert piper.settings.length_scale == pytest.approx(1.56 * 1.45) and not piper._cache  # nothing said at the old pace

    class Engine:
        properties = {}

        def setProperty(self, name, value):
            self.properties[name] = value

    windows = object.__new__(WindowsSpeech)
    windows.engine, windows.willy_pitch = Engine(), 1.
    windows.set_speed(speech_rate=104)
    assert windows.speech_rate == 104 and windows.engine.properties["rate"] == 104


def test_the_voice_takes_the_new_pace_before_its_next_sentence(monkeypatch):
    paces = []

    class Engine:
        label = "fake"

        def set_speed(self, length_scale, speech_rate):
            paces.append((round(length_scale, 2), round(speech_rate)))

        def say(self, text, cancel, on_start=None):
            said.set()

        def close(self):
            pass

    said = threading.Event()
    monkeypatch.setattr(AudioCoach, "_make_backend", lambda self: Engine())
    coach = AudioCoach(enabled=True, length_scale=1.3, speech_rate=130)
    try:
        coach.set_slow(True)
        assert coach.say("Bonjour", "fr")
        assert said.wait(3)
        assert paces == [(1.56, 104)]
    finally:
        coach.stop()


def test_the_physio_sets_them_on_the_second_page_and_they_are_kept(tmp_path):
    form = SettingsForm(Plan(), page="device")
    for name in ACCESSIBILITY:
        assert form.value_text(name, "", "fr") == "Non"
        form.step(name, 1)
        assert getattr(form, name) and form.value_text(name, "", "en") == "Oui"
    profile = Profile.load(tmp_path / "profile.json")
    for name in ACCESSIBILITY:
        setattr(profile, name, True)
    profile.save()
    again = Profile.load(tmp_path / "profile.json")
    assert again.accessibility() == Accessibility(True, True, True, True)
    assert Profile.load(tmp_path / "missing.json").accessibility() == Accessibility()


def test_saving_applies_the_settings_and_subtitles_show_the_apps_own_lines(monkeypatch, tmp_path):
    from tests.app_fakes import ScriptedWindow, make_app
    window = ScriptedWindow()
    app = make_app(monkeypatch, tmp_path, window, language="fr", tour_done=True)
    app.start()
    try:
        app.open_modal("settings")
        form = app.screens["settings"].form
        app.screens["settings"].on_action(app, "page:device")
        assert form.page == "device"
        for name in ("large_text", "high_contrast", "slow_speech", "subtitles"):
            app.screens["settings"].on_action(app, f"set:+:{name}")
        app.screens["settings"].on_action(app, "settings_save")
        assert app.profile.large_text and app.profile.subtitles
        assert accessibility.current() == Accessibility(True, True, True, True)
        app.fake_audio.set_slow.assert_called_with(True)
        app.say_line("E6.08")
        shown = app.fake_audio.show.call_args.args[0]
        assert shown.id == "E6.08" and shown.text
    finally:
        app.close()
        accessibility.set_current(Accessibility())
