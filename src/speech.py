"""Local French speech backends. Neural synthesis never uploads text or video."""
from collections import OrderedDict
import io
import json
from pathlib import Path
import os
import re
import tempfile
import wave

import numpy as np

VOICE_DIRECTORY = Path(__file__).resolve().parents[1] / "models" / "voices"
# Willy's voice is the "Cartoon buddy" the user picked: a male voice (the sample used Piper's
# Ryan; Tom is its French counterpart), pitch and timbre raised 1.45x, with a light 6 Hz vibrato.
WILLY_BASE_VOICE = "fr_FR-tom-medium"
WILLY_PITCH = 1.45
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


def installed_french_voices():
    return sorted(p.name[:-len(".onnx")] for p in VOICE_DIRECTORY.glob("fr_FR-*.onnx")
                  if p.with_suffix(".onnx.json").is_file())


class PiperFrenchSpeech:
    def __init__(self, voice=WILLY_BASE_VOICE, length_scale=1.30, volume=.85, willy_pitch=1.0):
        if not re.fullmatch(r"fr_FR-[a-zA-Z0-9_]+-(?:low|medium|high)", voice):
            raise ValueError("Choose a French Piper voice name")
        path = VOICE_DIRECTORY / f"{voice}.onnx"
        if not path.is_file() or not path.with_suffix(".onnx.json").is_file():
            raise FileNotFoundError(f"Voix {voice} manquante. Lancez : python models/download_models.py voice")
        from piper import PiperConfig, PiperVoice, SynthesisConfig
        import onnxruntime as ort
        with open(path.with_suffix(".onnx.json"), encoding="utf-8") as f:
            config = json.load(f)
        if config.get("language", {}).get("code") != "fr_FR":
            raise ValueError("Le modele vocal doit etre francais (fr_FR)")
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
        self.label = f"Piper / francais local / {voice}" + (" / voix de Willy" if self.willy_pitch > 1 else "")
        self._cache = OrderedDict()

    def synthesize(self, text):
        """Bounded in-memory cache for repeated guidance; no patient speech cache on disk."""
        if text in self._cache:
            self._cache.move_to_end(text)
            return self._cache[text]
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            self.voice.synthesize_wav(text, wav, syn_config=self.settings)
        data = buffer.getvalue()
        if self.willy_pitch > 1:
            data = _willy_wav(data, self.willy_pitch)
        self._cache[text] = data
        if len(self._cache) > 32:
            self._cache.popitem(last=False)
        return data

    def say(self, text, cancel):
        data = self.synthesize(text)
        if not cancel.is_set():
            play_wav(data, cancel)

    def close(self):
        self._cache.clear()


def french_voice(voices, prefer_male=False):
    """Never read French instructions with an English default voice.

    With prefer_male (Willy's voice is built on a male voice), a male French voice such as
    Windows "Paul" is chosen when one is installed; otherwise any French voice.
    """
    french = []
    for voice in voices:
        languages = [x.decode("utf-8", errors="ignore") if isinstance(x, bytes) else str(x)
                     for x in (getattr(voice, "languages", None) or [])]
        description = " ".join([str(voice.name), str(voice.id), *languages]).lower()
        if any(key in description for key in ("fr-fr", "fr_fr", "frfr", "french", "français", "hortense", "040c")):
            french.append(voice)
    if prefer_male:
        for voice in french:
            gender = str(getattr(voice, "gender", "") or "").lower()
            if gender == "male" or "paul" in str(voice.name).lower():
                return voice
    return french[0] if french else None


class WindowsFrenchSpeech:
    """Fallback French voice. With willy_pitch > 1 the speech is rendered to a temporary WAV,
    turned into Willy's voice, played, and the file is deleted at once."""

    def __init__(self, speech_rate=130, volume=.85, willy_pitch=1.0):
        import pyttsx3
        self.engine = pyttsx3.init()
        self.willy_pitch = max(1., float(willy_pitch))
        voice = french_voice(self.engine.getProperty("voices"), prefer_male=self.willy_pitch > 1)
        if voice is None:
            self.engine.stop()
            raise RuntimeError("Aucune voix Windows francaise. Installez la voix Piper ou une voix Windows fr-FR.")
        self.engine.setProperty("voice", voice.id)
        self.speech_rate = speech_rate
        # Slower before the pitch-up, so Willy keeps the configured pace.
        self.engine.setProperty("rate", int(round(speech_rate / self.willy_pitch)))
        self.engine.setProperty("volume", volume)
        self.label = f"Windows / {voice.name}" + (" / voix de Willy" if self.willy_pitch > 1 else "")

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

    def say(self, text, cancel):
        if cancel.is_set():
            return
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
                    play_wav(data, cancel)
                return
        self.engine.say(text)
        self.engine.runAndWait()

    def close(self):
        self.engine.stop()


def create_speech_backend(backend="auto", voice=WILLY_BASE_VOICE, length_scale=1.30, volume=.85, speech_rate=130,
                          willy_pitch=1.0):
    if backend not in ("auto", "piper", "system"):
        raise ValueError("Audio backend must be auto, piper or system")
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
