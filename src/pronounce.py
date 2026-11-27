"""What Willy's voice reads, which can differ from what his bubble shows (Phase 9.3).

`assets/willy/pronounce.yaml` lists respellings for each language: a word a voice reads the
wrong way (an English name in a French sentence), a unit after a number ("90°", "2 m") and
symbols. They change only the text sent to the voice; the screen keeps the original wording.
`tools/pronunciation_check.py` finds the lines that may need one.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

import yaml

PRONOUNCE_PATH = Path(__file__).resolve().parents[1] / "assets" / "willy" / "pronounce.yaml"
_NUMBER = r"(\d+(?:[.,]\d+)?)"


class Pronunciation:
    """The respellings of one file; `spoken(text, language)` gives the text for the voice."""

    def __init__(self, data=None):
        self.words, self.units, self.symbols, self.checked = {}, {}, {}, {}
        for language, entry in (data or {}).items():
            entry = entry or {}
            self.words[language] = {str(k): str(v) for k, v in (entry.get("words") or {}).items()}
            self.units[language] = {}
            for unit, forms in (entry.get("units") or {}).items():
                if isinstance(forms, str):
                    forms = [forms, forms]
                if len(forms) != 2:
                    raise ValueError(f"{language} unit {unit!r}: give [after 1, after other numbers]")
                self.units[language][str(unit)] = (str(forms[0]), str(forms[1]))
            self.symbols[language] = {str(k): str(v) for k, v in (entry.get("symbols") or {}).items()}
            self.checked[language] = frozenset(str(word) for word in (entry.get("checked") or ()))
        self._patterns = {language: self._compile(language) for language in self.words}

    @classmethod
    def load(cls, path=PRONOUNCE_PATH):
        path = Path(path)
        if not path.is_file():
            return cls()
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")) or {})

    def _compile(self, language):
        patterns = []
        units = self.units[language]
        if units:
            # Longest first, so "cm" wins over "m"; a unit is never followed by a letter ("2 mois").
            names = "|".join(re.escape(unit) for unit in sorted(units, key=len, reverse=True))
            patterns.append(("unit", re.compile(_NUMBER + r"\s*(" + names + r")(?!\w)")))
        words = self.words[language]
        if words:
            names = "|".join(re.escape(word) for word in sorted(words, key=len, reverse=True))
            patterns.append(("word", re.compile(r"(?<!\w)(" + names + r")(?!\w)")))
        return patterns

    def spoken(self, text, language):
        """The text the voice reads: units after numbers, then words, then symbols."""
        if not text or language not in self._patterns:
            return text
        for kind, pattern in self._patterns[language]:
            if kind == "unit":
                def unit(match):
                    one, many = self.units[language][match.group(2)]
                    return f"{match.group(1)} {one if match.group(1) == '1' else many}"
                text = pattern.sub(unit, text)
            else:
                text = pattern.sub(lambda match: self.words[language][match.group(1)], text)
        for symbol, said in self.symbols[language].items():
            text = text.replace(symbol, said)
        return re.sub(r"[ \t]{2,}", " ", text).strip()


@lru_cache(maxsize=1)
def shared():
    return Pronunciation.load()


def spoken(text, language):
    """What Willy's voice reads for `text` (assets/willy/pronounce.yaml)."""
    return shared().spoken(text, language)
