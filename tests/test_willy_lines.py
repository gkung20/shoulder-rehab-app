"""Willy's script: every line in both languages, filled in correctly, and an English screen."""
import re

import numpy as np
import pytest

from src.willy_lines import (ANIMATIONS, WillyScript, cue_line_id, fill, most_frequent_tip, result_line,
                             tip_line_id)
from src.rules_engine import ClinicalError, RepetitionEvaluation


@pytest.fixture(scope="module")
def script():
    return WillyScript()


def _fields(text):
    names = set(re.findall(r"\{(\w+)\}", text))
    return {"tip" if n in ("tip", "conseil") else "Tip" if n in ("Tip", "Conseil") else n for n in names}


def test_every_scenario_line_of_the_doc_is_in_the_script(script):
    expected = {f"S1.{i:02d}" for i in range(1, 9)} | {f"S2.{i:02d}" for i in range(1, 8)}
    expected |= {f"S3.{i:02d}" for i in range(1, 11)} | {f"S4.{i:02d}" for i in range(1, 12)}
    expected |= {f"S5.{i:02d}" for i in range(1, 20)} | {f"S6.{i:02d}" for i in range(1, 16)}
    expected |= {f"S7.{i:02d}" for i in range(1, 20)} | {f"S8.{i:02d}" for i in range(1, 15)}
    expected |= {f"E1.{i:02d}" for i in range(1, 7)} | {f"E2.{i:02d}" for i in range(1, 9)}
    expected |= {f"E3.{i:02d}" for i in range(1, 8)} | {f"E4.{i:02d}" for i in range(1, 12)}
    expected |= {f"E5.{i:02d}" for i in range(1, 6)} | {f"E5.{i:02d}" for i in range(10, 21)}
    expected |= {f"E6.{i:02d}" for i in range(1, 9)} | {f"E7.{i:02d}" for i in range(1, 4)}
    assert expected <= set(script.ids())


def test_both_languages_use_the_same_blanks_and_options(script):
    for line_id in script.ids():
        entry = script.entries[line_id]
        assert entry["anim"] in ANIMATIONS
        assert _fields(entry["en"]) == _fields(entry["fr"]), line_id
        en_options = re.findall(r"\{[^{}]*/[^{}]*\}", entry["en"])
        fr_options = re.findall(r"\{[^{}]*/[^{}]*\}", entry["fr"])
        assert [o.count("/") for o in en_options] == [o.count("/") for o in fr_options], line_id
        # One idea per line: about 15 words, a little more for French.
        assert len(entry["en"].split()) <= 17 and len(entry["fr"].split()) <= 19, line_id


def test_lines_fill_names_options_counts_and_tips(script):
    assert script.text("S3.03", "en", name="Amina") == "Nice to meet you, Amina!"
    assert script.text("S3.03", "en", name="") == "Nice to meet you!"
    assert script.text("S3.03", "fr") == "Enchanté !"
    assert script.text("S3.05", "en", choice=1) == "Got it: your left arm."
    assert script.text("S3.05", "fr", choice=0) == "C'est noté : votre bras droit."
    assert script.text("S4.08", "fr", choice=1) == "Baissez un peu la caméra."
    assert script.text("E1.01", "fr", choice=2).startswith("Bonsoir")
    assert script.text("S8.06", "en", n=1) == "You did 1 movement today."
    assert script.text("S8.06", "fr", n=7) == "Vous avez fait 7 mouvements aujourd'hui."
    assert script.text("S8.08", "fr", c=1) == "1 était parfait."
    tip = script.text("E5.12", "en")
    assert script.text("S7.15", "en", tip=tip) == "One! Next time, keep your shoulder down."
    assert script.text("E5.05", "fr", n=3, tip=script.text("E5.12", "fr")) == "Répétition 3 terminée. Gardez l'épaule basse."
    with pytest.raises(KeyError):
        fill("You did {n} movements", {})


def test_live_messages_and_errors_map_to_lines():
    assert cue_line_id("Gardez l'epaule basse !") == "E4.07"
    assert cue_line_id("Restez au repos encore 2.9 s") == cue_line_id("Restez au repos encore 0.1 s") == "E3.05"
    assert cue_line_id("Epaules pretes : montrez le coude du bras actif pour compter") == "E3.04"
    assert cue_line_id("Continuez le mouvement") is None
    assert tip_line_id("Bras projete vers l'avant (hors plan)") == "E5.15"
    assert tip_line_id("Mouvement saccade (manque de fluidite)") == "E5.16"
    assert tip_line_id("something new") == "E5.20"


def test_results_and_the_session_tip(script):
    good = RepetitionEvaluation(2, "right", True, "CORRECT", [])
    shrug = RepetitionEvaluation(3, "right", False, "A CORRIGER", [],
                                 errors=[ClinicalError("Haussement d'epaule excessif", "x")])
    fast = RepetitionEvaluation(4, "right", False, "A CORRIGER", [], errors=[ClinicalError("Montee trop rapide", "x")])
    unknown = RepetitionEvaluation(5, "right", False, "INDETERMINE", [])
    assert result_line(script, good, "en").id in ("E5.01", "E5.02", "E5.03")
    assert result_line(script, shrug, "en").text == "Movement 3 done. Keep your shoulder down."
    assert result_line(script, unknown, "fr").id == "E5.04"
    assert most_frequent_tip([good, shrug, fast, shrug, unknown]) == "E5.12"
    assert most_frequent_tip([good, unknown]) is None


def _drawn_text(monkeypatch, **kwargs):
    from PIL import ImageDraw
    from src.config import ExerciseConfig
    from src.dashboard import render_dashboard
    from src.session_processor import FrameAnalysis, SessionProcessor
    seen = []
    original = ImageDraw.ImageDraw.text

    def record(draw, xy, text, *args, **kw):
        seen.append(str(text))
        return original(draw, xy, text, *args, **kw)
    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record)
    processor = SessionProcessor(ExerciseConfig.from_yaml())
    render_dashboard(np.zeros((480, 640, 3), np.uint8), FrameAnalysis(0., metrics={}), processor, lang="en", **kwargs)
    monkeypatch.setattr(ImageDraw.ImageDraw, "text", original)
    return seen


class _Stage:
    """Stands in for the 3D avatars, to draw the avatar view's labels."""
    resting_sides = {"left"}
    detailed_hands = 0

    def render(self, analysis, processor, mode, source, size):
        return np.full((size[1], size[0], 3), 200, np.uint8), True


@pytest.mark.parametrize("state", [
    {"mode": "ready"}, {"mode": "running"}, {"mode": "paused", "help_visible": True},
    {"mode": "finished", "details": True}, {"mode": "ready", "avatars": False, "silhouette": True},
    {"mode": "running", "details": True}, {"mode": "running", "avatars": True, "stage": True}])
def test_english_screen_has_no_french_left(monkeypatch, state):
    from src.i18n import EN
    state = dict(state)
    if state.pop("stage", False):
        state["avatar_stage"] = _Stage()
    drawn = _drawn_text(monkeypatch, **state)
    allowed = {"mouvement", "Français", "Silhouette"}
    for text in drawn:
        if text in allowed or text.strip().isdigit():
            continue
        assert text not in EN, f"untranslated: {text}"
        assert not re.search(r"[éèêàçôûù’«»]", text), f"French on the English screen: {text}"
