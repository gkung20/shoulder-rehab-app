"""Non-blocking coaching in Willy's voice, in French or English, with fresh guidance."""
from collections import OrderedDict
from dataclasses import asdict, dataclass
import logging
from pathlib import Path
import queue
import re
import threading
import time
import unicodedata

from src.rules_engine import FeedbackLevel, LiveFeedback, RepetitionEvaluation
from src.speech import create_speech_backend
from src.willy_lines import LANGUAGES, cue_line_id, result_line, shared_script

LOGGER = logging.getLogger(__name__)


def spoken_french(message):
    """Keep screen-compatible ASCII out of pronunciation; stabilize countdown cues.

    Live messages that Willy has a line for use that line's French wording (assets/willy/lines.yaml).
    """
    line_id = cue_line_id(message)
    if line_id is not None:
        return shared_script().text(line_id, "fr")
    # Unknown cues remain French text, with common ASCII-only words restored.
    replacements = {"epaules":"épaules", "epaule":"épaule", "coude":"coude", "pret":"prêt",
        "repetez":"répétez", "repetition":"répétition", "controlez":"contrôlez", "serre":"serré",
        "detecte":"détecté", "evaluee":"évaluée", "camera":"caméra", "baissez":"baissez"}
    return re.sub(r"\b(" + "|".join(replacements) + r")\b",
                  lambda match: replacements[match.group(0).lower()], message.strip(), flags=re.IGNORECASE)


@dataclass
class _SpeechItem:
    text: str
    created_at: float
    result: bool = False
    language: str | None = None  # None: the coach's current language
    ttl: float | None = None     # seconds before a waiting sentence is dropped as stale


_UNAVAILABLE = {"fr": "Voix française indisponible : voir la console", "en": "English voice unavailable: see the console"}
_LOADING = {"fr": "Chargement de la voix française…", "en": "Loading the English voice…"}


class AudioCoach:
    def __init__(self, enabled=True, speech_rate=130, min_interval_sec=8.,
                 repeat_cooldown_sec=40., backend="auto", voice="fr_FR-tom-medium",
                 length_scale=1.30, volume=.85, guidance_mode="essential",
                 warning_persistence_sec=1.5, announce_every_reps=5, willy_pitch=1.45,
                 voice_en="en_US-ryan-medium", language="fr"):
        self._lang_available = {}
        self.language = language if language in LANGUAGES else "fr"
        self.voice_en = voice_en
        self.script = shared_script()
        self.last_line = None      # Willy's latest line (src.willy_lines.Line), shown in his bubble
        self.last_line_at = float("-inf")
        self.enabled = enabled
        self.speech_rate = speech_rate
        self.min_interval_sec = min_interval_sec
        self.repeat_cooldown_sec = repeat_cooldown_sec
        self.backend = backend
        self.voice = voice
        self.length_scale = length_scale
        self.volume = volume
        self.guidance_mode = guidance_mode
        self.warning_persistence_sec = warning_persistence_sec
        self.announce_every_reps = announce_every_reps
        self.willy_pitch = willy_pitch
        self.speaking = False  # True while a sentence plays: Willy moves his mouth
        self._setup_announced = False
        self._warning_text = None
        self._warning_since = None
        self.available = None
        self.status_message = "Audio désactivé" if not enabled else _LOADING[self.language]
        self.last_error = ""
        self._queue = queue.Queue(maxsize=2)
        self._stop_event = threading.Event()
        self._playback_cancel = threading.Event()
        self._last_speech_time = float("-inf")
        self._last_spoken_cues = OrderedDict()
        self._lock = threading.Lock()
        self._thread = None
        self._closed = False
        if self.enabled:
            self._start_worker()

    @classmethod
    def from_config(cls, settings, enabled=True, language="fr"):
        return cls(enabled=enabled, language=language, **asdict(settings))

    @property
    def available(self):
        """Whether Willy's voice works in the current language (None: not tried yet)."""
        return self._lang_available.get(self.language)

    @available.setter
    def available(self, value):
        self._lang_available[self.language] = value

    @property
    def busy(self):
        """True while Willy is talking or has a sentence waiting."""
        return bool(self.speaking) or not self._queue.empty()

    def _make_backend(self):
        return self._backend_for(self.language)

    def _backend_for(self, language):
        return create_speech_backend(self.backend, self.voice_en if language == "en" else self.voice,
                                     self.length_scale, self.volume, self.speech_rate,
                                     willy_pitch=self.willy_pitch, language=language)

    def _start_worker(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker_loop, name="willy-voice", daemon=True)
        self._thread.start()

    def _engine_for(self, engines, language):
        """The voice for one language, created the first time it is needed; None if it cannot work."""
        if language in engines:
            return engines[language]
        try:
            engine = self._make_backend() if language == self.language else self._backend_for(language)
        except Exception as error:
            self._lang_available[language] = False
            self.last_error = str(error)
            if language == self.language:
                self.status_message = _UNAVAILABLE[language]
            LOGGER.warning("Voice unavailable (%s): %s", language, error)
            engines[language] = None
            return None
        engines[language] = engine
        self._lang_available[language] = True
        if language == self.language:
            self.status_message = engine.label
        return engine

    def _worker_loop(self):
        engines = {}
        try:
            language = self.language
            engine = self._make_backend()
            engines[language] = engine
            self._lang_available[language] = True
            self.status_message = engine.label
            while not self._stop_event.is_set():
                try:
                    item = self._queue.get(timeout=.15)
                except queue.Empty:
                    continue
                try:
                    ttl = item.ttl if item.ttl is not None else (8. if item.result else 4.)
                    if time.monotonic() - item.created_at > ttl:
                        continue
                    with self._lock:
                        if not self.enabled or self._stop_event.is_set():
                            continue
                        self._playback_cancel.clear()
                    engine = self._engine_for(engines, item.language or self.language)
                    if engine is None:
                        continue
                    self.speaking = True
                    try:
                        engine.say(item.text, self._playback_cancel)
                    finally:
                        self.speaking = False
                finally:
                    self._queue.task_done()
        except Exception as error:
            self.available = False
            self.last_error = str(error)
            self.status_message = _UNAVAILABLE[self.language]
            LOGGER.warning("Audio indisponible : %s", error)
        finally:
            for engine in engines.values():
                if engine is None:
                    continue
                try:
                    engine.close()
                except Exception:
                    LOGGER.debug("Audio cleanup failed", exc_info=True)

    def _clear_pending(self, keep_result=False):
        latest_result = None
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if keep_result and item.result:
                latest_result = item
            self._queue.task_done()
        if latest_result is not None:
            self._queue.put_nowait(latest_result)

    def _admit(self, text, force, now):
        """Cooldowns shared by the voice and the bubble (caller holds the lock)."""
        last_time = self._last_spoken_cues.get(text, float("-inf"))
        if not force and now-last_time < self.repeat_cooldown_sec:
            return False
        if not force and now-self._last_speech_time < self.min_interval_sec:
            return False
        self._last_speech_time = now
        self._last_spoken_cues[text] = now
        if len(self._last_spoken_cues) > 64:
            self._last_spoken_cues.popitem(last=False)
        return True

    def speak(self, message, priority=False, force=False, line=None):
        """Say one sentence, respecting the cooldowns. With `line`, Willy's bubble shows it even with the sound off.

        Returns True only when the sentence was queued for the voice.
        """
        if line is not None:
            text = line.text
        else:
            text = spoken_french(message) if message and self.language == "fr" else (message or "")
        now = time.monotonic()
        with self._lock:
            if self._closed or not text:
                return False
            audible = self.enabled and self.available is not False
            if not audible and line is None:
                return False
            if not self._admit(text, force, now):
                return False
            if line is not None:
                self.last_line, self.last_line_at = line, now
            if not audible:
                return False
            if priority or force:
                self._playback_cancel.set()  # Stop an obsolete instruction for a correction/result.
            # New phases replace old queued instructions; keep at most one pending result.
            self._clear_pending(keep_result=not force)
            self._queue.put_nowait(_SpeechItem(text, now, result=force))
            return True

    def say(self, text, language=None, interrupt=True, ttl=20.):
        """A line of the tour: no cooldown, but it waits for nothing older than `ttl` seconds.

        `interrupt` stops what Willy is saying; without it the line follows the current one.
        """
        language = language if language in LANGUAGES else self.language
        now = time.monotonic()
        with self._lock:
            if self._closed or not text or not self.enabled or self._lang_available.get(language) is False:
                return False
            if interrupt:
                self._playback_cancel.set()
                self._clear_pending()
            try:
                self._queue.put_nowait(_SpeechItem(text, now, result=True, language=language, ttl=ttl))
            except queue.Full:
                return False
            # Everyday cues wait a moment after a tour line instead of talking over it.
            self._last_speech_time = now
            return True

    def show(self, line):
        """Put a line in Willy's bubble without saying it."""
        with self._lock:
            self.last_line, self.last_line_at = line, time.monotonic()

    def _cue_line(self, message):
        line_id = cue_line_id(message)
        return None if line_id is None else self.script.line(line_id, self.language)

    def speak_cue(self, feedback: LiveFeedback):
        if feedback is None:
            return False
        line = self._cue_line(feedback.message)
        if self.guidance_mode == "essential":
            text = line.text if line is not None else spoken_french(feedback.message)
            now = time.monotonic()
            if feedback.level == FeedbackLevel.WARNING:
                if text != self._warning_text:
                    self._warning_text, self._warning_since = text, now
                if now - self._warning_since < self.warning_persistence_sec:
                    return False
                if line is None and self.language != "fr":
                    return False
                return self.speak(feedback.message, priority=True, line=line)
            self._warning_text = self._warning_since = None
            # One setup instruction per session. Exercise phases stay on screen.
            key = unicodedata.normalize("NFKD", feedback.message).encode("ascii", "ignore").decode().lower()
            setup = any(part in key for part in ("calibration", "epaules", "au repos encore", "images valides"))
            if self._setup_announced or not setup:
                return False
            setup_line = self.script.line("E3.01", self.language)
            accepted = self.speak(None, line=setup_line)
            if accepted or self.last_line is setup_line:
                self._setup_announced = True
            return accepted
        if line is None:
            if self.language != "fr":
                return False
            return self.speak(feedback.message, priority=feedback.level == FeedbackLevel.WARNING)
        return self.speak(None, priority=feedback.level == FeedbackLevel.WARNING, line=line)

    def speak_evaluation(self, result: RepetitionEvaluation):
        line = result_line(self.script, result, self.language)
        if self.guidance_mode == "essential":
            if result.rep_index % self.announce_every_reps:
                self.show(line)  # the bubble shows every result; the voice keeps to milestones
                return False
            milestone = self.script.line("E6.01", self.language, n=result.rep_index)
            return self.speak(None, line=milestone)
        return self.speak(None, priority=True, force=True, line=line)

    def silence(self):
        """Cancel speech for a pause, keeping the user's voice preference."""
        with self._lock:
            self._playback_cancel.set()
            self._clear_pending()
            self._warning_text = self._warning_since = None

    def begin_session(self):
        self.silence()
        self._setup_announced = False
        self._warning_text = self._warning_since = None
        with self._lock:
            self._last_spoken_cues.clear()
            self._last_speech_time = float("-inf")

    def set_language(self, language):
        """Switch Willy's language; the matching voice loads on his next sentence."""
        if language not in LANGUAGES or language == self.language:
            return False
        with self._lock:
            self.language = language
            self._playback_cancel.set()
            self._clear_pending()
            self._warning_text = self._warning_since = None
            self._last_spoken_cues.clear()
            if self.enabled:
                self.status_message = _LOADING[language] if self.available is None else self.status_message
        if self.enabled and not self._closed and (self._thread is None or not self._thread.is_alive()):
            self._start_worker()
        return True

    def toggle(self):
        with self._lock:
            if self._closed:
                return False
            self.enabled = not self.enabled
            if not self.enabled:
                self._playback_cancel.set()
                self._clear_pending()
        if self.enabled and (self._thread is None or not self._thread.is_alive()):
            self.available = None
            self._start_worker()
        return self.enabled

    def stop(self):
        with self._lock:
            self._closed = True
            self._stop_event.set()
            self._playback_cancel.set()
            self._clear_pending()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.)
        if self._thread is not None and not self._thread.is_alive():
            self._thread = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stop()


def main():
    """Make a listening sample without opening the webcam or playing sound automatically."""
    import argparse
    from src.config import ExerciseConfig
    from src.speech import PiperFrenchSpeech
    parser = argparse.ArgumentParser(description="Créer un extrait de la voix française locale")
    parser.add_argument("--preview", default="output/voix_willy.wav", help="Fichier WAV à générer")
    parser.add_argument("--text", default="Bonjour ! Je suis Willy, votre guide. Levez doucement le bras sur le côté. Très bien ! Maintenant, redescendez tranquillement.")
    args = parser.parse_args()
    config = ExerciseConfig.from_yaml().audio
    voice = PiperFrenchSpeech(config.voice, config.length_scale, config.volume, willy_pitch=config.willy_pitch)
    try:
        path = Path(args.preview)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(voice.synthesize(args.text))
        print(f"Extrait français créé : {path.resolve()}")
    finally:
        voice.close()


if __name__ == "__main__":
    main()
