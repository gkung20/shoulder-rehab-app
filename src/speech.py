"""Local French speech backends. Neural synthesis never uploads text or video."""
from collections import OrderedDict
import io
import json
from pathlib import Path
import re
import wave

VOICE_DIRECTORY = Path(__file__).resolve().parents[1] / "models" / "voices"


class PiperFrenchSpeech:
    def __init__(self, voice="fr_FR-siwis-medium", length_scale=1.30, volume=.85):
        if not re.fullmatch(r"fr_FR-[a-zA-Z0-9_]+-(?:low|medium|high)", voice):
            raise ValueError("Choose a French Piper voice name")
        path = VOICE_DIRECTORY / f"{voice}.onnx"
        if not path.is_file() or not path.with_suffix(".onnx.json").is_file():
            raise FileNotFoundError(
                f"Voix manquante. Lancez : python -m piper.download_voices {voice} --data-dir models/voices")
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
        self.settings = SynthesisConfig(length_scale=length_scale, volume=volume, normalize_audio=True)
        self.label = f"Piper / francais local / {voice}"
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
        self._cache[text] = data
        if len(self._cache) > 32:
            self._cache.popitem(last=False)
        return data

    def say(self, text, cancel):
        data = self.synthesize(text)
        if cancel.is_set():
            return
        import sounddevice as sd
        with wave.open(io.BytesIO(data), "rb") as wav:
            with sd.RawOutputStream(samplerate=wav.getframerate(), channels=wav.getnchannels(), dtype="int16") as stream:
                while not cancel.is_set():
                    block = wav.readframes(1024)
                    if not block:
                        break
                    stream.write(block)

    def close(self):
        self._cache.clear()


def french_voice(voices):
    """Never read French instructions with an English default voice."""
    for voice in voices:
        languages = [x.decode("utf-8", errors="ignore") if isinstance(x, bytes) else str(x)
                     for x in (getattr(voice, "languages", None) or [])]
        description = " ".join([str(voice.name), str(voice.id), *languages]).lower()
        if any(key in description for key in ("fr-fr", "fr_fr", "frfr", "french", "français", "hortense", "040c")):
            return voice
    return None


class WindowsFrenchSpeech:
    def __init__(self, speech_rate=130, volume=.85):
        import pyttsx3
        self.engine = pyttsx3.init()
        voice = french_voice(self.engine.getProperty("voices"))
        if voice is None:
            self.engine.stop()
            raise RuntimeError("Aucune voix Windows francaise. Installez la voix Piper ou une voix Windows fr-FR.")
        self.engine.setProperty("voice", voice.id)
        self.engine.setProperty("rate", speech_rate)
        self.engine.setProperty("volume", volume)
        self.label = f"Windows / {voice.name}"

    def say(self, text, cancel):
        if not cancel.is_set():
            self.engine.say(text)
            self.engine.runAndWait()

    def close(self):
        self.engine.stop()


def create_speech_backend(backend="auto", voice="fr_FR-siwis-medium", length_scale=1.30, volume=.85, speech_rate=130):
    if backend not in ("auto", "piper", "system"):
        raise ValueError("Audio backend must be auto, piper or system")
    if backend in ("auto", "piper"):
        try:
            return PiperFrenchSpeech(voice, length_scale, volume)
        except (ImportError, OSError, ValueError, RuntimeError) as error:
            if backend == "piper":
                raise
            neural_error = error
        try:
            return WindowsFrenchSpeech(speech_rate, volume)
        except Exception as error:
            raise RuntimeError(f"Piper : {neural_error}. Windows : {error}") from error
    return WindowsFrenchSpeech(speech_rate, volume)
