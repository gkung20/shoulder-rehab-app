"""Willy's lines in English and French, read from assets/willy/lines.yaml.

The wording lives in the YAML file, written from the onboarding doc. This module only fills
in what the app knows at run time: counts, the patient's first name, the arm, a tip.
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
import unicodedata

import yaml

from src import cues as cue_lines

LINES_PATH = Path(__file__).resolve().parents[1] / "assets" / "willy" / "lines.yaml"
LANGUAGES = ("en", "fr")
ANIMATIONS = ("wave", "idle", "point", "demo", "nod", "cheer", "calm", "mirror")
LANGUAGE_NAMES = {"en": "English", "fr": "Français"}

_CHOICE = re.compile(r"\{([^{}]*/[^{}]*)\}")
_FIELD = re.compile(r"\{(\w+)\}")
_COUNTS = ("n", "k", "c")


@dataclass(frozen=True)
class Line:
    id: str
    text: str
    anim: str
    language: str


def _norm(language):
    language = (language or "fr").lower()[:2]
    if language not in LANGUAGES:
        raise ValueError(f"Unknown language: {language}")
    return language


def _lower_first(text):
    return text[:1].lower() + text[1:] if text else text


def _upper_first(text):
    return text[:1].upper() + text[1:] if text else text


def fill(template, values=None):
    """Fill one line: {a / b} choices, {name}, {tip}/{Tip} (or {conseil}), counts."""
    values = dict(values or {})
    choice = int(values.get("choice", 0) or 0)

    def pick(match):
        options = [option.strip() for option in match.group(1).split("/")]
        return options[min(max(choice, 0), len(options) - 1)]

    text = _CHOICE.sub(pick, template)
    name = str(values.get("name") or "").strip()
    if not name:  # "Nice to meet you, {name}!" -> "Nice to meet you!"
        text = re.sub(r",?\s*\{name\}", "", text)
    tip = str(values.get("tip") or "").strip()

    def field(match):
        key = match.group(1)
        if key in ("tip", "conseil"):  # inside a sentence: no capital, no full stop
            return _lower_first(tip).rstrip(" .")
        if key in ("Tip", "Conseil"):
            return _upper_first(tip)
        if key == "name":
            return name
        if key in values:
            return str(values[key])
        raise KeyError(f"Missing value '{key}' for: {template}")

    return _FIELD.sub(field, text)


class WillyScript:
    """All of Willy's lines; `text(id, language, **values)` returns a ready-to-say sentence."""

    def __init__(self, path=LINES_PATH):
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        self.entries = {}
        for line_id, entry in data.items():
            entry = dict(entry or {})
            if entry.get("anim") not in ANIMATIONS:
                raise ValueError(f"{line_id}: unknown animation {entry.get('anim')!r}")
            for language in LANGUAGES:
                if not str(entry.get(language) or "").strip():
                    raise ValueError(f"{line_id}: missing {language} text")
            self.entries[str(line_id)] = entry
        self._turns = {}

    def __contains__(self, line_id):
        return line_id in self.entries

    def ids(self, prefix=""):
        return [line_id for line_id in self.entries if line_id.startswith(prefix)]

    def anim(self, line_id):
        return self.entries[line_id]["anim"]

    def template(self, line_id, language, values=None):
        entry = self.entries[line_id]
        language = _norm(language)
        one = entry.get("one") or {}
        values = values or {}
        if one.get(language):
            for key in _COUNTS:
                if "{%s}" % key in entry[language] and values.get(key) == 1:
                    return one[language]
        return entry[language]

    def text(self, line_id, language, **values):
        return fill(self.template(line_id, language, values), values)

    def line(self, line_id, language, **values):
        return Line(line_id, self.text(line_id, language, **values), self.anim(line_id), _norm(language))

    def rotate(self, *line_ids):
        """Variants that share a moment take turns, so Willy does not repeat himself."""
        key = tuple(line_ids)
        turn = self._turns.get(key, 0)
        self._turns[key] = turn + 1
        return line_ids[turn % len(line_ids)]


@lru_cache(maxsize=1)
def shared_script():
    return WillyScript()


# --------------------------------------------------------------------------- mappings
def _key(message):
    return unicodedata.normalize("NFKD", str(message)).encode("ascii", "ignore").decode().strip().lower()


def cue_line_id(cue):
    """Willy's everyday line for a live cue (LiveFeedback, src.cues.Cue or, for old callers, its text).

    The mapping lives in src.cues.LINES and goes by the cue's code, not its French wording.
    """
    return cue_lines.line_id(cue)


# Error categories of the rules engine -> tip line.
_TIP_LINES = {
    "amplitude insuffisante": "E5.10",
    "elevation excessive": "E5.11",
    "haussement d'epaule excessif": "E5.12",
    "inclinaison du tronc": "E5.13",
    "coude plie": "E5.14",
    "bras projete vers l'avant (hors plan)": "E5.15",
    "mouvement saccade (manque de fluidite)": "E5.16",
    "montee trop rapide": "E5.17",
    "maintien trop court": "E5.18",
    "descente trop rapide": "E5.19",
}


def tip_line_id(category):
    return _TIP_LINES.get(_key(category), "E5.20")


def evaluation_tip(result):
    """Tip line for a counted movement: the first error found, or None when there is nothing to fix."""
    errors = getattr(result, "errors", None) or []
    if not errors:
        return None
    return tip_line_id(errors[0].category)


def result_line(script, result, language, tip_language=None):
    """Willy's line after a counted movement (E5.01 to E5.05)."""
    n = getattr(result, "rep_index", 0)
    if getattr(result, "status_label", "") == "INDETERMINE":
        return script.line("E5.04", language, n=n)
    if getattr(result, "is_correct", False):
        return script.line(script.rotate("E5.01", "E5.02", "E5.03"), language, n=n)
    tip_id = evaluation_tip(result) or "E5.20"
    return script.line("E5.05", language, n=n, tip=script.text(tip_id, tip_language or language))


def most_frequent_tip(evaluations):
    """Tip line for the error seen most often in a session (first seen wins a tie), or None."""
    counts = {}
    for evaluation in evaluations:
        if getattr(evaluation, "is_correct", False) or getattr(evaluation, "status_label", "") == "INDETERMINE":
            continue
        line_id = evaluation_tip(evaluation)
        if line_id:
            counts[line_id] = counts.get(line_id, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda line_id: counts[line_id])


def reading_seconds(text):
    """About how long a line takes to read or hear, so a silent Willy keeps a natural pace."""
    words = len(str(text).split())
    return min(8., 1.2 + .38 * words)
