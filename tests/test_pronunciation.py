"""Phase 9.3: respellings for Willy's voice, the pronunciation pass and the voice render."""
from collections import OrderedDict
import importlib.util
import io
import threading
import wave
from pathlib import Path

import pytest

from src.pronounce import Pronunciation, spoken
from src.speech import VOICE_DIRECTORY, PiperSpeech, WindowsSpeech
from src.willy_lines import WillyScript, shared_script

ROOT = Path(__file__).resolve().parents[1]


def _tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = _tool("pronunciation_check")
render_voices = _tool("render_voices")

RULES = Pronunciation({
    "fr": {"words": {"Willy": "Houili", "coach": "kôtch"},
           "units": {"°": ["degré", "degrés"], "m": ["mètre", "mètres"], "cm": ["centimètre", "centimètres"]},
           "symbols": {"%": " pour cent"}, "checked": ["C"]},
    "en": {"units": {"°": ["degree", "degrees"], "m": ["metre", "metres"]}, "symbols": {"%": " percent"}},
})


def test_the_voice_reads_the_respelling_and_the_screen_keeps_the_line():
    assert spoken("Bonjour ! Je suis Willy.", "fr") == "Bonjour ! Je suis Houili."
    assert spoken("Hi! I'm Willy.", "en") == "Hi! I'm Willy."  # French respellings only in French
    assert shared_script().text("S1.01", "fr") == "Bonjour ! Je suis Willy."  # the bubble


def test_words_units_and_symbols():
    assert RULES.spoken("Le coach, à gauche.", "fr") == "Le kôtch, à gauche."
    assert RULES.spoken("Le coaching.", "fr") == "Le coaching."  # whole words only
    assert RULES.spoken("Montez à 90°.", "fr") == "Montez à 90 degrés."
    assert RULES.spoken("Encore 1° !", "fr") == "Encore 1 degré !"
    assert RULES.spoken("À 1,5 m de l'écran, 10 cm plus haut.", "fr") == "À 1,5 mètres de l'écran, 10 centimètres plus haut."
    assert RULES.spoken("Dans 2 mois.", "fr") == "Dans 2 mois."  # "m" followed by letters is a word
    assert RULES.spoken("1 m away, 1.5 m, 10% better", "en") == "1 metre away, 1.5 metres, 10 percent better"
    assert RULES.spoken("Raise it 1° more.", "en") == "Raise it 1 degree more."
    assert RULES.spoken("Willy", "de") == "Willy"  # a language without rules is left alone


def test_both_voices_read_the_respelled_text():
    said = []

    class Voice:
        def synthesize_wav(self, text, wav, syn_config=None):
            said.append(text)
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(22050)
            wav.writeframes(b"\0\0" * 220)

    piper = object.__new__(PiperSpeech)
    piper.language, piper.voice, piper.settings, piper.willy_pitch, piper._cache = "fr", Voice(), None, 1., OrderedDict()
    piper.synthesize("Je suis Willy.")

    class Engine:
        def say(self, text):
            said.append(text)

        def runAndWait(self):
            pass

    windows = object.__new__(WindowsSpeech)
    windows.language, windows.engine, windows.willy_pitch, windows.speech_rate = "fr", Engine(), 1., 130
    windows.say("Je suis Willy.", threading.Event())
    assert said == ["Je suis Houili.", "Je suis Houili."]


def test_text_flags_need_no_voice():
    flags = dict(check.text_flags("Tenez-vous à 2 m, 3/10.", "fr"))
    assert flags["abbreviation"] == "m" and flags["symbol"] == "/" and flags["number"] == "2, 3, 10"
    assert check.text_flags("À la prochaine ! A little higher.", "fr") == []  # "À" is a word
    assert dict(check.text_flags("OK, PDF.", "en"))["abbreviation"] == "OK, PDF"
    assert dict(check.text_flags("OK, PDF.", "en", checked={"OK"}))["abbreviation"] == "PDF"


def test_every_text_the_app_can_say_is_sampled():
    samples = check.sample_texts(WillyScript())
    texts = {(s.line_id, s.language, s.label): s.text for s in samples}
    assert texts[("S3.05", "fr", "option 2")] == "C'est noté : votre bras gauche."
    assert texts[("S8.06", "en", "one")] == "You did 1 movement today."
    assert texts[("S3.03", "en", "")] == "Nice to meet you, Sara!"
    assert ("cue cal_required", "fr", "") in texts  # screen cues the French voice may read
    assert not any("{" in text or "}" in text for text in texts.values())


VOICES_INSTALLED = all((VOICE_DIRECTORY / f"{voice}.onnx").is_file() for voice in check.VOICES.values())


@pytest.mark.skipif(not VOICES_INSTALLED, reason="Willy's voices are not installed")
def test_every_line_passes_the_pronunciation_check():
    voices = check.load_voices()
    findings = check.check(check.sample_texts(WillyScript()), voices, Pronunciation.load())
    todo = check.problems(findings)
    assert not todo, ("Run python tools/pronunciation_check.py and add a respelling to "
                      "assets/willy/pronounce.yaml: " + "; ".join(
                          f"{check._name(f.sample)} {f.flags}" for f in todo))
    willy = next(f for f in findings if f.sample.line_id == "S1.01" and f.sample.language == "fr")
    assert "wilˈi" in willy.phonemes and "syˌiz" not in willy.phonemes  # French "Willy", no liaison


def test_render_writes_each_line_and_one_file_to_listen_to(tmp_path):
    class Speech:
        def synthesize(self, text):
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(1000)
                wav.writeframes(b"\1\0" * (len(text) * 10))
            return buffer.getvalue()

    samples = [check.Sample("S1.01", "fr", "", "Bonjour !"), check.Sample("S3.05", "fr", "option 2", "Gauche."),
               check.Sample("cue cal_required", "fr", "", "Appuyez sur C")]
    written = render_voices.render(samples, Speech(), tmp_path, "fr")
    names = [path.name for path in written]
    assert names[:3] == ["S1.01.wav", "S3.05_option-2.wav", "cue_cal_required.wav"]
    with wave.open(str(tmp_path / "all_fr.wav"), "rb") as wav:
        total = wav.getnframes()
    assert total == sum(len(s.text) * 10 for s in samples) + 3 * 500  # half a second after each line
    index = (tmp_path / "all_fr.txt").read_text(encoding="utf-8").splitlines()
    assert index[0].startswith("00:00.0  S1.01") and index[1].startswith("00:00.6  S3.05_option-2")
    assert render_voices.pick(samples, ["S3", "cal_required"]) == samples[1:]
