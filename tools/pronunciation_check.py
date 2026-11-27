"""Pronunciation pass (Phase 9.3): every line Willy says, read by its Piper voice's phonemizer.

    python tools/pronunciation_check.py                          # both languages, summary
    python tools/pronunciation_check.py --report docs/pronunciation.md
    python tools/pronunciation_check.py --strict                 # exit 1 while a problem is left

Each line is filled in like the app does (every {a / b} option, the singular form, sample
counts, a first name and a tip), changed by assets/willy/pronounce.yaml, then phonemized.
The flags are about the text the voice reads:

  missing       a sound the voice has no symbol for: Piper drops it without a word
  foreign       a sound of the other language (an English word in a French line, or the
                reverse); the word is named. Fix it with a respelling, or list the word
                under "checked" once it sounds right
  symbol        a character the voice may skip or read oddly (/, &, ...)
  abbreviation  capitals (PDF) or a letter on its own ("2 m")
  number        a number: listen to check it is read as meant (decimals, ranges)

The first four are problems (--strict fails on them); numbers are only to listen to.
Listen to any line with tools/render_voices.py.
"""
from __future__ import annotations

import argparse
from collections import namedtuple
from datetime import date
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import cues  # noqa: E402
from src.audio_feedback import spoken_french  # noqa: E402
from src.pronounce import Pronunciation  # noqa: E402
from src.speech import VOICE_DIRECTORY, WILLY_BASE_VOICE, WILLY_ENGLISH_VOICE  # noqa: E402
from src.willy_lines import LANGUAGES, WillyScript, fill  # noqa: E402

VOICES = {"fr": WILLY_BASE_VOICE, "en": WILLY_ENGLISH_VOICE}
# What the app puts in the fields: counts, a first name, a tip (the text of a correction line).
SAMPLE = {"n": 3, "k": 2, "c": 5, "name": "Sara"}
SAMPLE_TIP = "E5.16"
# Screen cues without a Willy line: in complete guidance, the French voice reads their text.
SPOKEN_CUES = sorted(cues.SCREEN_ONLY, key=lambda cue: cue.value)
# Sounds of the other language. French has no "ɪ", "ʊ", "θ" or "ɹ" (espeak-ng's French does
# lengthen some vowels, "côte" kˈoːt, so "ː" is not on the list); English has no "ʁ", "y" (as
# in "tu"), "ø", "œ", "ɥ", "ɲ" or nasal vowels.
FOREIGN = {
    "fr": frozenset("ɪʊʌæθðɹɚɜɐᵻɾʔhɒɝ"),
    "en": frozenset("ʁyøœɥɲ̃"),
}
SINGLE_LETTER_WORDS = {"fr": {"a", "à", "y"}, "en": {"a", "I"}}
SPEAKABLE = set(" ,.;:!?'’-–«»\"()…  ")
PROBLEMS = ("missing", "foreign", "symbol", "abbreviation")

Sample = namedtuple("Sample", "line_id language label text")
Finding = namedtuple("Finding", "sample spoken phonemes flags")


def sample_texts(script, languages=LANGUAGES):
    """Every text the app can say: each line, each {a / b} option, the singular form."""
    samples = []
    for line_id in script.ids():
        entry = script.entries[line_id]
        for language in languages:
            tip = script.text(SAMPLE_TIP, language).rstrip(" .")
            values = dict(SAMPLE, tip=tip)
            templates = [("", entry[language])]
            one = (entry.get("one") or {}).get(language)
            if one:
                templates.append(("one", one))
            for form, template in templates:
                options = [len(group.split("/")) for group in re.findall(r"\{([^{}]*/[^{}]*)\}", template)]
                for choice in range(max(options, default=1)):
                    label = " ".join(part for part in (form, f"option {choice + 1}" if options else "") if part)
                    counts = {"n": 1, "k": 1, "c": 1} if form == "one" else {}
                    text = fill(template, dict(values, choice=choice, **counts))
                    samples.append(Sample(line_id, language, label, text))
    if "fr" in languages:
        for cue in SPOKEN_CUES:
            samples.append(Sample(f"cue {cue.value}", "fr", "", spoken_french(cues.text(cue))))
    return samples


def load_voices(languages=LANGUAGES, directory=VOICE_DIRECTORY):
    """The installed Piper voices, by language (a missing one is left out)."""
    from piper import PiperVoice

    voices = {}
    for language in languages:
        path = Path(directory) / f"{VOICES[language]}.onnx"
        if path.is_file() and path.with_suffix(".onnx.json").is_file():
            voices[language] = PiperVoice.load(path)
    return voices


def _sounds(voice, text):
    return [phoneme for sentence in voice.phonemize(text) for phoneme in sentence]


def text_flags(text, language, checked=frozenset()):
    """Flags that need no voice: symbols, abbreviations, numbers."""
    flags = []
    symbols = sorted({ch for ch in text if not (ch.isalnum() or ch in SPEAKABLE
                                                or unicodedata.combining(ch))})
    if symbols:
        flags.append(("symbol", " ".join(symbols)))
    words = re.findall(r"(?<![\w'’])([A-Z]{2,})(?![\w'’])", text)
    words += [letter for letter in re.findall(r"(?<![\w'’])([^\W\d_])(?![\w'’])", text)
              if letter not in SINGLE_LETTER_WORDS.get(language, ())
              and letter.lower() not in SINGLE_LETTER_WORDS.get(language, ())]  # "À la prochaine"
    words = [word for word in dict.fromkeys(words) if word not in checked]
    if words:
        flags.append(("abbreviation", ", ".join(words)))
    numbers = re.findall(r"\d+(?:[.,]\d+)*", text)
    if numbers:
        flags.append(("number", ", ".join(dict.fromkeys(numbers))))
    return flags


def check(samples, voices, pronunciation):
    """Phonemize each sample's spoken text and flag what may sound wrong."""
    findings = []
    word_cache = {}
    for sample in samples:
        spoken = pronunciation.spoken(sample.text, sample.language)
        checked = pronunciation.checked.get(sample.language, frozenset())
        flags = text_flags(spoken, sample.language, checked)
        voice = voices.get(sample.language)
        phonemes = None
        if voice is not None:
            sentences = voice.phonemize(spoken)
            phonemes = " | ".join("".join(sentence) for sentence in sentences)
            known = voice.config.phoneme_id_map
            missing = sorted({p for sentence in sentences for p in sentence if p not in known})
            if missing:
                flags.insert(0, ("missing", " ".join(missing)))
            foreign_words = []
            for word in dict.fromkeys(re.findall(r"[^\W\d_][\w'’-]*", spoken)):
                if word in checked:
                    continue
                key = (sample.language, word)
                if key not in word_cache:
                    word_cache[key] = sorted(set(_sounds(voice, word)) & FOREIGN[sample.language])
                if word_cache[key]:
                    foreign_words.append(f"{word} ({''.join(word_cache[key])})")
            if foreign_words:
                flags.insert(0, ("foreign", ", ".join(foreign_words)))
        findings.append(Finding(sample, spoken, phonemes, flags))
    return findings


def problems(findings):
    return [f for f in findings if any(kind in PROBLEMS for kind, _ in f.flags)]


def _name(sample):
    return f"{sample.line_id} {sample.language}" + (f" ({sample.label})" if sample.label else "")


def _cell(text):
    return (text or "").replace("|", "\\|")


def report(findings, voices):
    """The pass as Markdown: a summary, then what to fix, what was respelled, what to listen to."""
    lines = ["# Pronunciation pass", "",
             f"Every line Willy can say, read by its voice's phonemizer (Piper, espeak-ng), on "
             f"{date.today():%d %b %Y}. Made by `python tools/pronunciation_check.py --report "
             "docs/pronunciation.md`; its first lines explain the flags. Respellings "
             "live in `assets/willy/pronounce.yaml` (spoken text only: the screen keeps the line as "
             "written). Listen to any line with `python tools/render_voices.py --only <ID>`.", "",
             "| Language | Voice | Texts read | Problems | Respelled | Numbers to listen to |",
             "| --- | --- | ---: | ---: | ---: | ---: |"]
    for language in LANGUAGES:
        mine = [f for f in findings if f.sample.language == language]
        if not mine:
            continue
        voice = VOICES[language] if language in voices else "not installed (text checks only)"
        respelled = sum(f.spoken != f.sample.text for f in mine)
        numbers = sum(any(kind == "number" for kind, _ in f.flags) for f in mine)
        lines.append(f"| {language} | {voice} | {len(mine)} | {len(problems(mine))} | {respelled} | {numbers} |")

    lines += ["", "## Problems", ""]
    todo = problems(findings)
    if todo:
        lines += ["| Line | Flags | Voice reads | Sounds |", "| --- | --- | --- | --- |"]
        for f in todo:
            flags = "; ".join(f"{kind}: {detail}" for kind, detail in f.flags if kind in PROBLEMS)
            lines.append(f"| {_name(f.sample)} | {_cell(flags)} | {_cell(f.spoken)} | {_cell(f.phonemes)} |")
    else:
        lines.append("None.")

    lines += ["", "## Respelled for the voice", ""]
    changed = [f for f in findings if f.spoken != f.sample.text]
    if changed:
        lines += ["| Line | On screen | Voice reads | Sounds |", "| --- | --- | --- | --- |"]
        for f in changed:
            lines.append(f"| {_name(f.sample)} | {_cell(f.sample.text)} | {_cell(f.spoken)} | {_cell(f.phonemes)} |")
    else:
        lines.append("None.")

    lines += ["", "## Numbers to listen to", ""]
    numbered = [f for f in findings if any(kind == "number" for kind, _ in f.flags)]
    if numbered:
        lines += ["| Line | Voice reads | Sounds |", "| --- | --- | --- |"]
        for f in numbered:
            lines.append(f"| {_name(f.sample)} | {_cell(f.spoken)} | {_cell(f.phonemes)} |")
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--language", choices=LANGUAGES, help="one language only")
    parser.add_argument("--report", type=Path, help="write the Markdown report here")
    parser.add_argument("--strict", action="store_true", help="exit 1 while a problem is left")
    args = parser.parse_args(argv)
    languages = (args.language,) if args.language else LANGUAGES
    voices = load_voices(languages)
    for language in languages:
        if language not in voices:
            print(f"[{language}] voice {VOICES[language]} not installed: text checks only "
                  f"(python models/download_models.py {'voice' if language == 'fr' else 'voice-en'})")
    findings = check(sample_texts(WillyScript(), languages), voices, Pronunciation.load())
    todo = problems(findings)
    for f in todo:
        flags = "; ".join(f"{kind}: {detail}" for kind, detail in f.flags if kind in PROBLEMS)
        print(f"{_name(f.sample)}: {flags}\n    {f.spoken}\n    {f.phonemes}")
    respelled = sum(f.spoken != f.sample.text for f in findings)
    print(f"{len(findings)} texts read, {len(todo)} with a problem, {respelled} respelled.")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report(findings, voices), encoding="utf-8")
        print(f"Report: {args.report}")
    return 1 if args.strict and todo else 0


if __name__ == "__main__":
    sys.exit(main())
