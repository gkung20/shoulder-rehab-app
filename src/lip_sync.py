"""Willy's mouth follows his voice (Phase 9.1).

When a line is synthesised, its loudness is measured every 40 ms; while it plays, Willy shows
the mouth that matches the loudness at that moment: closed smile in the pauses, half open
(talk1) for soft sounds, open (talk2) for loud ones. A Windows voice that speaks directly,
with no audio to measure, gets an envelope made from the text instead: about five
syllables a second, with pauses at commas and full stops.
"""
from __future__ import annotations

import io
import re
import time
import wave

import numpy as np

STEP = .04                  # seconds per loudness value
QUIET, LOUD = .18, .55      # below QUIET: smile; above LOUD: talk2; between: talk1
SYLLABLES_PER_SEC = 5.
SYLLABLE = (.35, .85, 1., .7, .25)       # one syllable over 5 steps (0.2 s)
PAUSES = {",": .25, ";": .3, ":": .3, ".": .45, "!": .45, "?": .45, "…": .45}
VOWELS = re.compile(r"[aeiouyàâäéèêëîïôöùûüœæ]+", re.IGNORECASE)


def loudness(samples, rate, step=STEP):
    """RMS loudness every `step` seconds of int16 mono samples, 1.0 = the line's usual loud level."""
    data = np.asarray(samples, dtype=np.float32)
    size = max(1, int(round(rate * step)))
    count = int(np.ceil(data.size / size))
    if count == 0:
        return np.zeros(0, np.float32)
    padded = np.zeros(count * size, np.float32)
    padded[:data.size] = data
    rms = np.sqrt((padded.reshape(count, size) ** 2).mean(axis=1))
    voiced = rms[rms > rms.max() * .05] if rms.max() > 0 else rms
    reference = np.percentile(voiced, 90) if voiced.size else 0.
    return np.clip(rms / reference, 0., 1.5).astype(np.float32) if reference > 0 else np.zeros(count, np.float32)


def wav_loudness(data, step=STEP):
    """Loudness envelope of WAV bytes (16-bit; stereo is averaged)."""
    with wave.open(io.BytesIO(data), "rb") as wav:
        rate, channels = wav.getframerate(), wav.getnchannels()
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return loudness(samples, rate, step)


def text_loudness(text, step=STEP, rate=SYLLABLES_PER_SEC):
    """An envelope from the text alone, for voices that speak without giving us the audio."""
    per_syllable = max(1, int(round(1. / rate / step)))
    shape = np.interp(np.linspace(0, len(SYLLABLE) - 1, per_syllable), range(len(SYLLABLE)), SYLLABLE)
    values = []
    for token in re.findall(r"[^\s,;:.!?…]+|[,;:.!?…]", text):
        if token in PAUSES:
            values += [0.] * int(round(PAUSES[token] / step))
            continue
        for _ in range(max(1, len(VOWELS.findall(token)))):
            values += list(shape)
        values.append(.05)  # a breath between words
    return np.asarray(values, np.float32)


def mouth_for(level):
    return "smile" if level < QUIET else "talk1" if level < LOUD else "talk2"


def mouth_frames(envelope):
    """The mouth to show at each 40 ms step of an envelope."""
    return [mouth_for(float(level)) for level in envelope]


class LipTrack:
    """One line being played: its envelope and when playback started."""

    def __init__(self, envelope, started=None, step=STEP):
        self.envelope = np.asarray(envelope, np.float32)
        self.started = time.monotonic() if started is None else started
        self.step = step

    def mouth(self, now=None):
        now = time.monotonic() if now is None else now
        index = int((now - self.started) / self.step)
        if index < 0 or index >= len(self.envelope):
            return "smile"
        return mouth_for(float(self.envelope[index]))
