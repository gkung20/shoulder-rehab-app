"""Local speech backends for Willy, in French and English. Neural synthesis never uploads text or video."""
from collections import OrderedDict
import io
import json
from pathlib import Path
import os
import re
import tempfile
import wave

import numpy as np

from src.lip_sync import SYLLABLES_PER_SEC, text_loudness, wav_loudness
from src.pronounce import spoken

VOICE_DIRECTORY = Path(__file__).resolve().parents[1] / "models" / "voices"
# Willy's voice is the "Cartoon buddy" the user picked: a male voice (the sample used Piper's
# Ryan; Tom is its French counterpart), pitch and timbre raised 1.45x, with a light 6 Hz vibrato.
WILLY_BASE_VOICE = "fr_FR-tom-medium"
# English Willy: Piper's Ryan, the base of the approved "Cartoon buddy" sample (its licence is
# non-commercial: check it before distributing the app).
WILLY_ENGLISH_VOICE = "en_US-ryan-medium"
WILLY_PITCH = 1.45
# Piper language codes accepted for each app language.
PIPER_LANGUAGES = {"fr": ("fr_FR",), "en": ("en_US", "en_GB")}
VIBRATO_HZ = 6.0
VIBRATO_DEPTH = .08


def willy_voice(frames, pitch, rate=22050, vibrato=True):
    """Willy's cartoon voice, the same recipe as the approved sample.

    1. Pitch and timbre up together by `pitch`, like a sped-up tape (ffmpeg asetrate).
    2. A light vibrato, as ffmpeg's vibrato=f=6:d=0.08 (delay swinging up to 0.4 ms).
    The text is synthesized `pitch` times slower first, so the speaking pace stays the
    configured one. int16 mono in, int16 mono out, same sample rate.
    """
    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
    if pitch <= 1 or samples.size < 2:
        return frames
    positions = np.arange(int(samples.size / pitch)) * pitch
    shifted = np.interp(positions, np.arange(samples.size), samples)
    if vibrato and shifted.size > 1:
        index = np.arange(shifted.size)
        max_delay = VIBRATO_DEPTH * (round(rate * .005) - 1)
        delay = max_delay * (.5 + .5 * np.sin(2 * np.pi * VIBRATO_HZ * index / rate + 1.5 * np.pi))
        shifted = np.interp(index - delay, index, shifted)
    return np.clip(np.round(shifted), -32768, 32767).astype(np.int16).tobytes()


def _willy_wav(data, pitch):
    """Apply Willy's voice to a whole WAV file (bytes); stereo is mixed down to mono."""
    with wave.open(io.BytesIO(data), "rb") as source:
        params, frames = source.getparams(), source.readframes(source.getnframes())
    if params.sampwidth != 2:
        raise ValueError("WAV 16 bits attendu")
    if params.nchannels == 2:
        stereo = np.frombuffer(frames, np.int16).reshape(-1, 2).astype(np.int32)
        frames = (stereo.mean(axis=1)).astype(np.int16).tobytes()
    elif params.nchannels != 1:
        raise ValueError("WAV mono ou stereo attendu")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(params.framerate)
        wav.writeframes(willy_voice(frames, pitch, params.framerate))
    return buffer.getvalue()


def play_wav(data, cancel):
    """Play WAV bytes on the default output, stopping promptly when `cancel` is set."""
    import sounddevice as sd
    with wave.open(io.BytesIO(data), "rb") as wav:
        with sd.RawOutputStream(samplerate=wav.getframerate(), channels=wav.getnchannels(), dtype="int16") as stream:
            while not cancel.is_set():
                block = wav.readframes(1024)
                if not block:
                    break
                stream.write(block)


def installed_voices(language="fr"):
    """Piper voices already downloaded for an app language ("fr" or "en")."""
    names = set()
    for code in PIPER_LANGUAGES[language]:
        names.update(p.name[:-len(".onnx")] for p in VOICE_DIRECTORY.glob(f"{code}-*.onnx")
                     if p.with_suffix(".onnx.json").is_file())
    return sorted(names)


def installed_french_voices():
    return installed_voices("fr")


def voice_pattern(language):
    return r"(?:%s)-[a-zA-Z0-9_]+-(?:x_low|low|medium|high)" % "|".join(PIPER_LANGUAGES[language])


class PiperSpeech:
    """A local Piper voice for one app language, with Willy's cartoon effect on top."""
    language = "fr"

    def __init__(self, voice=WILLY_BASE_VOICE, length_scale=1.30, volume=.85, willy_pitch=1.0, language=None):
        self.language = language or self.language
        if self.language not in PIPER_LANGUAGES:
            raise ValueError("Language must be fr or en")
        if not re.fullmatch(voice_pattern(self.language), voice):
            raise ValueError("Choose a French Piper voice name" if self.language == "fr" else "Choose an English Piper voice name")
        path = VOICE_DIRECTORY / f"{voice}.onnx"
        if not path.is_file() or not path.with_suffix(".onnx.json").is_file():
            target = "voice" if self.language == "fr" else "voice-en"
            raise FileNotFoundError(f"Voix {voice} manquante. Lancez : python models/download_models.py {target}")
        from piper import PiperConfig, PiperVoice, SynthesisConfig
        import onnxruntime as ort
        with open(path.with_suffix(".onnx.json"), encoding="utf-8") as f:
            config = json.load(f)
        if config.get("language", {}).get("code") not in PIPER_LANGUAGES[self.language]:
            raise ValueError("Le modele vocal doit etre francais (fr_FR)" if self.language == "fr"
                             else "The voice model must be English (en_US or en_GB)")
        # Leave CPU time for the camera/pose model instead of occupying all cores.
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.voice = PiperVoice(
            session=ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"]),
            config=PiperConfig.from_dict(config), download_dir=VOICE_DIRECTORY,
        )
        self.willy_pitch = max(1., float(willy_pitch))
        self.settings = SynthesisConfig(length_scale=length_scale * self.willy_pitch, volume=volume, normalize_audio=True)
        self.length_scale = length_scale
        kind = "francais local" if self.language == "fr" else "local English"
        self.label = f"Piper / {kind} / {voice}" + (" / voix de Willy" if self.willy_pitch > 1 else "")
        self._cache = OrderedDict()

    def set_speed(self, length_scale, speech_rate=None):
        """A new pace (Phase 10.2, slower speech): greater length_scale = slower. Clears the cache."""
        import dataclasses
        self.length_scale = float(length_scale)
        self.settings = dataclasses.replace(self.settings, length_scale=self.length_scale * self.willy_pitch)
        self._cache.clear()

    def synthesize(self, text):
        """Bounded in-memory cache for repeated guidance; no patient speech cache on disk.

        The voice reads `text` as respelled by assets/willy/pronounce.yaml (Phase 9.3).
        """
        if text in self._cache:
            self._cache.move_to_end(text)
            return self._cache[text]
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            self.voice.synthesize_wav(spoken(text, self.language), wav, syn_config=self.settings)
        data = buffer.getvalue()
        if self.willy_pitch > 1:
            data = _willy_wav(data, self.willy_pitch)
        self._cache[text] = data
        if len(self._cache) > 32:
            self._cache.popitem(last=False)
        return data

    def say(self, text, cancel, on_start=None):
        """Play a line; `on_start(envelope)` gets its loudness just before it starts (lip sync)."""
        data = self.synthesize(text)
        if not cancel.is_set():
            if on_start is not None:
                on_start(wav_loudness(data))
            play_wav(data, cancel)

    def close(self):
        self._cache.clear()


class PiperFrenchSpeech(PiperSpeech):
    language = "fr"

    def __init__(self, voice=WILLY_BASE_VOICE, length_scale=1.30, volume=.85, willy_pitch=1.0):
        super().__init__(voice, length_scale, volume, willy_pitch, "fr")


class PiperEnglishSpeech(PiperSpeech):
    language = "en"

    def __init__(self, voice=WILLY_ENGLISH_VOICE, length_scale=1.30, volume=.85, willy_pitch=1.0):
        super().__init__(voice, length_scale, volume, willy_pitch, "en")


_SYSTEM_VOICE_KEYS = {
    "fr": ("fr-fr", "fr_fr", "frfr", "french", "français", "hortense", "040c"),
    "en": ("en-us", "en_us", "enus", "en-gb", "en_gb", "engb", "english", "0409", "0809", "david", "zira", "hazel"),
}
_MALE_NAMES = {"fr": ("paul",), "en": ("david", "mark", "george", "guy")}


def system_voice(voices, language="fr", prefer_male=False):
    """A system voice for one language only: never read French with an English voice, or the reverse.

    With prefer_male (Willy's voice is built on a male voice), a male voice such as Windows
    "Paul" (French) or "David" (English) is chosen when one is installed.
    """
    matching = []
    for voice in voices:
        languages = [x.decode("utf-8", errors="ignore") if isinstance(x, bytes) else str(x)
                     for x in (getattr(voice, "languages", None) or [])]
        description = " ".join([str(voice.name), str(voice.id), *languages]).lower()
        if any(key in description for key in _SYSTEM_VOICE_KEYS[language]):
            matching.append(voice)
    if prefer_male:
        for voice in matching:
            gender = str(getattr(voice, "gender", "") or "").lower()
            if gender == "male" or any(name in str(voice.name).lower() for name in _MALE_NAMES[language]):
                return voice
    return matching[0] if matching else None


def french_voice(voices, prefer_male=False):
    """Never read French instructions with an English default voice."""
    return system_voice(voices, "fr", prefer_male)


class WindowsSpeech:
    """Fallback system voice. With willy_pitch > 1 the speech is rendered to a temporary WAV,
    turned into Willy's voice, played, and the file is deleted at once."""
    language = "fr"

    def __init__(self, speech_rate=130, volume=.85, willy_pitch=1.0, language=None):
        import pyttsx3
        self.language = language or self.language
        self.engine = pyttsx3.init()
        self.willy_pitch = max(1., float(willy_pitch))
        voice = system_voice(self.engine.getProperty("voices"), self.language, prefer_male=self.willy_pitch > 1)
        if voice is None:
            self.engine.stop()
            if self.language == "fr":
                raise RuntimeError("Aucune voix Windows francaise. Installez la voix Piper ou une voix Windows fr-FR.")
            raise RuntimeError("No English Windows voice. Install the English Piper voice or a Windows en-US voice.")
        self.engine.setProperty("voice", voice.id)
        self.speech_rate = speech_rate
        # Slower before the pitch-up, so Willy keeps the configured pace.
        self.engine.setProperty("rate", int(round(speech_rate / self.willy_pitch)))
        self.engine.setProperty("volume", volume)
        self.label = f"Windows / {voice.name}" + (" / voix de Willy" if self.willy_pitch > 1 else "")

    def set_speed(self, length_scale=None, speech_rate=130):
        """A new pace (Phase 10.2, slower speech), in words per minute."""
        self.speech_rate = int(round(speech_rate))
        self.engine.setProperty("rate", int(round(self.speech_rate / self.willy_pitch)))

    def _render(self, text):
        handle, path = tempfile.mkstemp(suffix=".wav", prefix="willy-")
        os.close(handle)
        try:
            self.engine.save_to_file(text, path)
            self.engine.runAndWait()
            data = Path(path).read_bytes()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        return _willy_wav(data, self.willy_pitch)

    def say(self, text, cancel, on_start=None):
        if cancel.is_set():
            return
        text = spoken(text, self.language)  # respellings for the voice only (Phase 9.3)
        if self.willy_pitch > 1:
            try:
                data = self._render(text)
            except Exception as error:  # keep talking with the plain voice rather than going silent
                print(f"[VOIX] Voix de Willy indisponible avec Windows ({error}) ; voix normale utilisee.")
                self.willy_pitch = 1.
                self.engine.setProperty("rate", self.speech_rate)
                self.label = self.label.replace(" / voix de Willy", "")
            else:
                if not cancel.is_set():
                    if on_start is not None:
                        on_start(wav_loudness(data))
                    play_wav(data, cancel)
                return
        if on_start is not None:  # no audio to measure: the mouth follows the text
            on_start(text_loudness(text, rate=SYLLABLES_PER_SEC * self.speech_rate / 130.))
        self.engine.say(text)
        self.engine.runAndWait()

    def close(self):
        self.engine.stop()


class WindowsFrenchSpeech(WindowsSpeech):
    language = "fr"

    def __init__(self, speech_rate=130, volume=.85, willy_pitch=1.0):
        super().__init__(speech_rate, volume, willy_pitch, "fr")


class WindowsEnglishSpeech(WindowsSpeech):
    language = "en"

    def __init__(self, speech_rate=130, volume=.85, willy_pitch=1.0):
        super().__init__(speech_rate, volume, willy_pitch, "en")


def create_speech_backend(backend="auto", voice=WILLY_BASE_VOICE, length_scale=1.30, volume=.85, speech_rate=130,
                          willy_pitch=1.0, language="fr"):
    if backend not in ("auto", "piper", "system"):
        raise ValueError("Audio backend must be auto, piper or system")
    if language == "en":
        return _english_backend(backend, voice, length_scale, volume, speech_rate, willy_pitch)
    if backend in ("auto", "piper"):
        neural_error = None
        # The configured voice first, then any other French Piper voice already downloaded.
        for name in [voice] + [v for v in installed_french_voices() if v != voice]:
            try:
                engine = PiperFrenchSpeech(name, length_scale, volume, willy_pitch)
            except (ImportError, OSError, ValueError, RuntimeError) as error:
                neural_error = neural_error or error
                continue
            if name != voice:
                print(f"[VOIX] {voice} absente : {name} utilisee. Pour la voix de Willy : "
                      "python models/download_models.py voice")
            return engine
        if backend == "piper":
            raise neural_error
        try:
            return WindowsFrenchSpeech(speech_rate, volume, willy_pitch)
        except Exception as error:
            raise RuntimeError(f"Piper : {neural_error}. Windows : {error}") from error
    return WindowsFrenchSpeech(speech_rate, volume, willy_pitch)


def _english_backend(backend, voice, length_scale, volume, speech_rate, willy_pitch):
    """Willy in English: the configured Piper voice, any English Piper voice, then a Windows voice."""
    voice = voice or WILLY_ENGLISH_VOICE
    if backend in ("auto", "piper"):
        neural_error = None
        for name in [voice] + [v for v in installed_voices("en") if v != voice]:
            try:
                engine = PiperEnglishSpeech(name, length_scale, volume, willy_pitch)
            except (ImportError, OSError, ValueError, RuntimeError) as error:
                neural_error = neural_error or error
                continue
            if name != voice:
                print(f"[VOICE] {voice} missing: using {name}. For Willy's voice: python models/download_models.py voice-en")
            return engine
        if backend == "piper":
            raise neural_error
        try:
            return WindowsEnglishSpeech(speech_rate, volume, willy_pitch)
        except Exception as error:
            raise RuntimeError(f"Piper: {neural_error}. Windows: {error}") from error
    return WindowsEnglishSpeech(speech_rate, volume, willy_pitch)
