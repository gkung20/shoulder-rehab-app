"""Willy, the on-screen guide: always drawn, never part of the measurements."""
import io
import numpy as np
import pytest

from src.config import ExerciseConfig
from src.dashboard import WILLY_BOX, render_dashboard, CANVAS_SIZE
from src.session_processor import FrameAnalysis, SessionProcessor
from src.state_machine import ExercisePhase
from src.speech import willy_voice
from src.willy import WillyGuide, exercise_screen_side, willy_portrait


@pytest.fixture(scope="module")
def guide():
    return WillyGuide()


def _analysis(status="", abduction=None, phase=ExercisePhase.REST, hold=0.):
    analysis = FrameAnalysis(0., metrics={} if abduction is None else {"abduction": abduction}, status=status)
    analysis.phase = phase
    analysis.hold_seconds = hold
    return analysis


def test_sprites_load_and_render_with_transparency(guide):
    sprite = guide.render(208, 276)
    assert sprite.shape == (276, 208, 4) and sprite.dtype == np.uint8
    alpha = sprite[..., 3]
    assert alpha.max() == 255 and alpha[0, 0] == 0  # opaque robot, transparent corners
    assert (alpha > 0).mean() > .15


def test_mirror_side_matches_patient_screen_side():
    assert exercise_screen_side("right", mirror=True) == "R"
    assert exercise_screen_side("left", mirror=True) == "L"
    assert exercise_screen_side("right", mirror=False) == "L"


def test_willy_raises_the_tracked_arm_with_the_patient():
    processor = SessionProcessor(ExerciseConfig.from_yaml())
    willy = WillyGuide()
    now = 100.
    for _ in range(40):
        now += .05
        pose = willy.update(_analysis("EN COURS", 85., ExercisePhase.HOLD, 1.), "running", processor, now=now)
    assert pose.arm_r == pytest.approx(85., abs=2) and pose.arm_l < 2
    assert pose.eyes == "happy"  # target held long enough


def test_willy_stays_calm_during_calibration_and_talks_with_the_voice():
    processor = SessionProcessor(ExerciseConfig.from_yaml())
    willy = WillyGuide()
    mouths = set()
    now = 10.
    for _ in range(60):
        now += .05
        pose = willy.update(_analysis("CALIBRATION", 90.), "running", processor, speaking=True, now=now)
        mouths.add(pose.mouth)
    assert pose.arm_l < 1 and pose.arm_r < 1
    assert {"talk1", "talk2"} <= mouths
    quiet = willy.update(_analysis("CALIBRATION"), "running", processor, speaking=False, now=now + .05)
    assert quiet.mouth == "smile"


def test_willy_waves_before_the_session_and_cheers_at_the_end():
    processor = SessionProcessor(ExerciseConfig.from_yaml())
    willy = WillyGuide()
    assert willy.update(_analysis(), "ready", processor, now=0.).wave_side == "R"
    willy.update(_analysis(), "finished", processor, now=5.)
    for step in range(20):
        pose = willy.update(_analysis(), "finished", processor, now=5. + step * .05)
    assert pose.eyes == "happy" and pose.arm_l > 100 and pose.arm_r > 100


@pytest.mark.parametrize("mode", ["ready", "running", "paused", "finished"])
@pytest.mark.parametrize("avatars", [True, False])
def test_dashboard_always_shows_willy(guide, mode, avatars):
    processor = SessionProcessor(ExerciseConfig.from_yaml())
    camera = np.full((480, 640, 3), 40, np.uint8)
    image = render_dashboard(camera, _analysis(), processor, mode=mode, avatars=avatars, help_visible=mode == "paused",
                             willy=guide)
    left, top, right, bottom = WILLY_BOX
    region = image[top:bottom, left:right].astype(int)
    background = np.array((249, 250, 250))  # BG in BGR order
    assert (np.abs(region - background).sum(axis=2) > 60).mean() > .1


def test_dashboard_scales_willy_with_the_window(guide):
    processor = SessionProcessor(ExerciseConfig.from_yaml())
    camera = np.zeros((480, 640, 3), np.uint8)
    image = render_dashboard(camera, _analysis(), processor, mode="ready", output_size=(1920, 1260), willy=guide)
    assert image.shape[:2] == (1260, 1920)


def test_portrait_for_streamlit():
    portrait = willy_portrait(220, 250)
    assert portrait.shape == (250, 220, 4)


def test_willy_voice_matches_the_approved_cartoon_recipe():
    rate = 22050
    t = np.arange(rate * 2) / rate
    tone = (np.sin(2 * np.pi * 200 * t) * 12000).astype(np.int16)
    shifted = np.frombuffer(willy_voice(tone.tobytes(), 1.45, rate), np.int16).astype(float)
    assert len(shifted) == int(len(tone) / 1.45)
    spectrum = np.abs(np.fft.rfft(shifted))
    peak = np.fft.rfftfreq(len(shifted), 1 / rate)[spectrum.argmax()]
    assert peak == pytest.approx(290, abs=4)          # 200 Hz x 1.45: pitch and timbre up
    # Light 6 Hz vibrato: the instantaneous pitch wobbles by under 1%.
    plain = np.frombuffer(willy_voice(tone.tobytes(), 1.45, rate, vibrato=False), np.int16).astype(float)
    assert np.abs(shifted - plain).max() > 500
    assert np.abs(shifted).max() <= 12001 and np.abs(shifted).max() > 11000  # loudness kept
    assert willy_voice(tone.tobytes(), 1.0) == tone.tobytes()


def test_windows_fallback_prefers_a_male_french_voice_for_willy():
    from types import SimpleNamespace as V
    from src.speech import french_voice
    hortense = V(name="Microsoft Hortense - French", id="fr-FR-Hortense", languages=["fr-FR"], gender=None)
    paul = V(name="Microsoft Paul - French", id="fr-FR-Paul", languages=["fr-FR"], gender=None)
    english = V(name="Microsoft David", id="en-US-David", languages=["en-US"], gender="male")
    assert french_voice([english, hortense, paul], prefer_male=True) is paul
    assert french_voice([english, hortense]) is hortense
    assert french_voice([english], prefer_male=True) is None


def test_missing_configured_voice_falls_back_to_another_installed_french_voice(monkeypatch):
    import src.speech as speech
    built = []

    class Fake:
        def __init__(self, name, *args):
            if name == "fr_FR-tom-medium":
                raise FileNotFoundError(name)
            built.append(name)
            self.label = name
    monkeypatch.setattr(speech, "PiperFrenchSpeech", Fake)
    monkeypatch.setattr(speech, "installed_french_voices", lambda: ["fr_FR-siwis-medium"])
    engine = speech.create_speech_backend("auto", "fr_FR-tom-medium", willy_pitch=1.45)
    assert engine.label == "fr_FR-siwis-medium" and built == ["fr_FR-siwis-medium"]


def test_willy_pitch_is_validated():
    from dataclasses import replace
    config = ExerciseConfig.from_yaml()
    assert config.audio.willy_pitch == pytest.approx(1.45)
    assert config.audio.voice == "fr_FR-tom-medium"
    with pytest.raises(ValueError):
        replace(config, audio=replace(config.audio, willy_pitch=3.0))


def test_windows_fallback_speaks_with_willys_voice(monkeypatch, tmp_path):
    import sys
    import types
    import wave as wavmod
    from types import SimpleNamespace as V

    class Engine:
        def __init__(self):
            self.props, self.pending = {}, None

        def getProperty(self, name):
            return [V(name="Microsoft Hortense - French", id="hortense", languages=["fr-FR"], gender=None),
                    V(name="Microsoft Paul - French", id="paul", languages=["fr-FR"], gender=None)]

        def setProperty(self, name, value):
            self.props[name] = value

        def save_to_file(self, text, path):
            self.pending = path

        def runAndWait(self):  # SAPI writes a 22.05 kHz 16-bit mono WAV
            t = np.arange(22050) / 22050
            with wavmod.open(self.pending, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
                w.writeframes((np.sin(2 * np.pi * 150 * t) * 9000).astype(np.int16).tobytes())

        def stop(self):
            pass

    monkeypatch.setitem(sys.modules, "pyttsx3", types.SimpleNamespace(init=Engine))
    from src.speech import WindowsFrenchSpeech
    voice = WindowsFrenchSpeech(130, .85, willy_pitch=1.45)
    assert voice.engine.props["voice"] == "paul" and voice.engine.props["rate"] == round(130 / 1.45)
    assert voice.label.endswith("voix de Willy")
    with wavmod.open(io.BytesIO(voice._render("Bonjour")), "rb") as w:
        assert w.getframerate() == 22050 and w.getnchannels() == 1
        assert w.getnframes() == int(22050 / 1.45)
