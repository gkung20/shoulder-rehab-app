"""Every line Willy says, as WAV files to listen to (Phase 9.3).

    python tools/render_voices.py                        # both languages, into output/voices/
    python tools/render_voices.py --only S1.01 E9        # lines whose ID starts with these
    python tools/render_voices.py --language fr --natural   # the plain voice, without Willy's effect

For each language it writes one WAV per text (output/voices/fr/S1.01.wav, S3.05_option-2.wav,
S8.06_one.wav ...), then all of them in one file to hear in one go, all_fr.wav (half a second
between lines), with all_fr.txt giving the time at which each line starts. The voices read
the lines as the app does: respelled by assets/willy/pronounce.yaml, at the speed, volume and
pitch of config/exercise_config.yaml, with the same sample values as the pronunciation check
(3 movements, the first name "Sara", a tip). Nothing leaves the computer.
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import re
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import ExerciseConfig  # noqa: E402
from src.speech import PiperSpeech, VOICE_DIRECTORY  # noqa: E402
from src.willy_lines import LANGUAGES, WillyScript  # noqa: E402

_spec = importlib.util.spec_from_file_location("pronunciation_check", Path(__file__).with_name("pronunciation_check.py"))
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

OUTPUT = ROOT / "output" / "voices"
PAUSE_SEC = .5


def file_name(sample):
    """S1.01.wav, S3.05_option-2.wav, S8.06_one.wav, cue_cal_required.wav."""
    name = sample.line_id + (f"_{sample.label}" if sample.label else "")
    return re.sub(r"[^\w.\-]+", "_", name.replace("option ", "option-")) + ".wav"


def pick(samples, prefixes):
    if not prefixes:
        return samples
    return [s for s in samples if any(s.line_id.startswith(p) or s.line_id == f"cue {p}" for p in prefixes)]


def _clock(seconds):
    minutes, seconds = divmod(seconds, 60.)
    return f"{int(minutes):02d}:{seconds:04.1f}"


def render(samples, speech, folder, language):
    """One WAV per sample, then all_<language>.wav and its time index. Returns the files written."""
    folder = Path(folder)
    (folder / language).mkdir(parents=True, exist_ok=True)
    written, frames, index, params, position = [], [], [], None, 0.
    for sample in samples:
        data = speech.synthesize(sample.text)
        path = folder / language / file_name(sample)
        path.write_bytes(data)
        written.append(path)
        with wave.open(io.BytesIO(data), "rb") as wav:
            if params is None:
                params = wav.getparams()
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (
                    params.nchannels, params.sampwidth, params.framerate):
                continue  # never happens with one voice; kept out of the long file if it did
            index.append(f"{_clock(position)}  {path.name[:-4]:<22} {sample.text}")
            frames.append(wav.readframes(wav.getnframes()))
            position += wav.getnframes() / params.framerate + PAUSE_SEC
    if params is not None:
        silence = b"\0" * (params.sampwidth * params.nchannels * int(params.framerate * PAUSE_SEC))
        everything = folder / f"all_{language}.wav"
        with wave.open(str(everything), "wb") as wav:
            wav.setnchannels(params.nchannels)
            wav.setsampwidth(params.sampwidth)
            wav.setframerate(params.framerate)
            for chunk in frames:
                wav.writeframes(chunk + silence)
        (folder / f"all_{language}.txt").write_text("\n".join(index) + "\n", encoding="utf-8")
        written += [everything, folder / f"all_{language}.txt"]
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--language", choices=LANGUAGES, help="one language only")
    parser.add_argument("--only", nargs="+", metavar="ID", help="lines whose ID starts with these (S1.01, E9)")
    parser.add_argument("--out", type=Path, default=OUTPUT, help=f"folder (default {OUTPUT})")
    parser.add_argument("--natural", action="store_true", help="the plain voice, without Willy's effect")
    args = parser.parse_args(argv)
    audio = ExerciseConfig.from_yaml().audio
    script = WillyScript()
    status = 0
    for language in (args.language,) if args.language else LANGUAGES:
        voice = audio.voice_en if language == "en" else audio.voice
        if not (VOICE_DIRECTORY / f"{voice}.onnx").is_file():
            print(f"[{language}] voice {voice} not installed: "
                  f"python models/download_models.py {'voice' if language == 'fr' else 'voice-en'}")
            status = 1
            continue
        samples = pick(check.sample_texts(script, (language,)), args.only)
        if not samples:
            print(f"[{language}] no line starts with {' '.join(args.only)}")
            continue
        speech = PiperSpeech(voice, audio.length_scale, audio.volume,
                             willy_pitch=1. if args.natural else audio.willy_pitch, language=language)
        start = time.monotonic()
        written = render(samples, speech, args.out, language)
        speech.close()
        print(f"[{language}] {len(samples)} lines in {time.monotonic() - start:.0f} s: "
              f"{args.out / language}, all of them in {args.out / f'all_{language}.wav'}")
        if not written:
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
