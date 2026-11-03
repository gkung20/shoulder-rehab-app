"""Non-blocking French coaching, using a local neural voice and fresh guidance."""
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

LOGGER = logging.getLogger(__name__)


def spoken_french(message):
    """Keep screen-compatible ASCII out of pronunciation; stabilize countdown cues."""
    key = unicodedata.normalize("NFKD", message).encode("ascii", "ignore").decode().strip().lower()
    phrases = {
        "pret : levez le bras sur le cote": "Quand vous êtes prêt, levez doucement le bras sur le côté.",
        "montez lentement le bras...": "Montez le bras doucement, sans forcer.",
        "presque ! rejoignez votre zone cible": "Vous y êtes presque. Rejoignez votre zone cible.",
        "maintenez dans la zone cible, puis redescendez": "Gardez cette position un petit instant.",
        "bien ! redescendez doucement jusqu'au repos": "Bien ! Maintenant, redescendez doucement.",
        "controlez la descente lentement": "Redescendez doucement, sans vous précipiter.",
        "gardez l'epaule basse !": "Gardez l'épaule basse, sans forcer.",
        "gardez le tronc droit !": "Gardez le buste droit.",
        "gardez le bras tendu !": "Gardez le bras tendu, sans le raidir.",
        "gardez le bras dans le plan du corps !": "Gardez le bras sur le côté du corps.",
        "un peu moins haut : revenez dans la zone cible": "Un peu moins haut. Revenez doucement dans la zone cible.",
        "epaules pretes : montrez le coude du bras actif pour compter": "C'est prêt. Montrez maintenant le coude du bras suivi.",
        "baissez le bras avant de commencer une repetition": "Baissez d'abord le bras, puis commencez la répétition.",
        "baissez le bras pour terminer la calibration": "Gardez le bras baissé pendant la calibration.",
        "montrez les deux epaules, gardez le bras au repos": "Montrez vos deux épaules et gardez le bras au repos.",
    }
    if key in phrases:
        return phrases[key]
    if key.startswith(("restez au repos encore", "images valides :")):
        return "Gardez le bras au repos pendant la calibration."
    if key.startswith("calibration en attente"):
        return "Je ne distingue pas bien vos épaules. Ajustez légèrement le cadrage."
    if key.startswith("aucun squelette detecte"):
        return "Je ne vous distingue plus. Ajustez le cadrage pour montrer vos épaules."
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


class AudioCoach:
    def __init__(self, enabled=True, speech_rate=130, min_interval_sec=8.,
                 repeat_cooldown_sec=40., backend="auto", voice="fr_FR-siwis-medium",
                 length_scale=1.30, volume=.85, guidance_mode="essential",
                 warning_persistence_sec=1.5, announce_every_reps=5):
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
        self._setup_announced = False
        self._warning_text = None
        self._warning_since = None
        self.available = None
        self.status_message = "Audio désactivé" if not enabled else "Chargement de la voix française…"
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
    def from_config(cls, settings, enabled=True):
        return cls(enabled=enabled, **asdict(settings))

    def _make_backend(self):
        return create_speech_backend(self.backend, self.voice, self.length_scale, self.volume, self.speech_rate)

    def _start_worker(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker_loop, name="french-coach", daemon=True)
        self._thread.start()

    def _worker_loop(self):
        engine = None
        try:
            engine = self._make_backend()
            self.available = True
            self.status_message = engine.label
            while not self._stop_event.is_set():
                try:
                    item = self._queue.get(timeout=.15)
                except queue.Empty:
                    continue
                try:
                    if time.monotonic() - item.created_at > (8. if item.result else 4.):
                        continue
                    with self._lock:
                        if not self.enabled or self._stop_event.is_set():
                            continue
                        self._playback_cancel.clear()
                    engine.say(item.text, self._playback_cancel)
                finally:
                    self._queue.task_done()
        except Exception as error:
            self.available = False
            self.last_error = str(error)
            self.status_message = "Voix française indisponible : voir la console"
            LOGGER.warning("Audio français indisponible : %s", error)
        finally:
            if engine is not None:
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

    def speak(self, message, priority=False, force=False):
        text = spoken_french(message) if message else ""
        now = time.monotonic()
        with self._lock:
            if not self.enabled or self.available is False or self._closed or not text:
                return False
            last_time = self._last_spoken_cues.get(text, float("-inf"))
            if not force and now-last_time < self.repeat_cooldown_sec:
                return False
            if not force and now-self._last_speech_time < self.min_interval_sec:
                return False
            if priority or force:
                self._playback_cancel.set()  # Stop an obsolete instruction for a correction/result.
            # New phases replace old queued instructions; keep at most one pending result.
            self._clear_pending(keep_result=not force)
            self._queue.put_nowait(_SpeechItem(text, now, result=force))
            self._last_speech_time = now
            self._last_spoken_cues[text] = now
            if len(self._last_spoken_cues) > 64:
                self._last_spoken_cues.popitem(last=False)
            return True

    def speak_cue(self, feedback: LiveFeedback):
        if feedback is None:
            return False
        if self.guidance_mode == "essential":
            text = spoken_french(feedback.message)
            now = time.monotonic()
            if feedback.level == FeedbackLevel.WARNING:
                if text != self._warning_text:
                    self._warning_text, self._warning_since = text, now
                if now - self._warning_since < self.warning_persistence_sec:
                    return False
                return self.speak(text, priority=True)
            self._warning_text = self._warning_since = None
            # One setup instruction per session. Exercise phases stay on screen.
            key = unicodedata.normalize("NFKD", feedback.message).encode("ascii", "ignore").decode().lower()
            setup = any(part in key for part in ("calibration", "epaules", "au repos encore", "images valides"))
            if self._setup_announced or not setup:
                return False
            accepted = self.speak("Installez-vous confortablement. Gardez le bras au repos.")
            if accepted:
                self._setup_announced = True
            return accepted
        return self.speak(feedback.message, priority=feedback.level == FeedbackLevel.WARNING)

    def speak_evaluation(self, result: RepetitionEvaluation):
        if self.guidance_mode == "essential":
            if result.rep_index % self.announce_every_reps:
                return False
            return self.speak(f"{result.rep_index} mouvements effectués. Continuez à votre rythme.")
        if result.status_label == "INDETERMINE":
            message = f"Répétition {result.rep_index} terminée. Posture partiellement évaluée."
        elif result.is_correct:
            message = f"Bravo ! Répétition {result.rep_index} validée."
        else:
            advice = {
                "Haussement d'epaule excessif": "Gardez l'épaule basse.",
                "Inclinaison du tronc": "Gardez le buste droit.",
                "Coude plie": "Gardez le bras tendu.",
                "Amplitude insuffisante": "Essayez de rejoindre votre zone cible, sans forcer.",
                "Elevation excessive": "Levez un peu moins haut.",
                "Montee trop rapide": "Prenez plus de temps pour monter le bras.",
                "Maintien trop court": "Gardez la position un peu plus longtemps.",
                "Descente trop rapide": "Redescendez plus doucement.",
            }
            first = result.errors[0].category if result.errors else ""
            message = f"Répétition {result.rep_index} terminée. " + advice.get(first, "Reprenons doucement le mouvement.")
        return self.speak(message, priority=True, force=True)

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
    parser.add_argument("--preview", default="output/voix_francaise.wav", help="Fichier WAV à générer")
    parser.add_argument("--text", default="Bonjour ! Je suis votre coach. Levez doucement le bras sur le côté. Très bien ! Maintenant, redescendez tranquillement.")
    args = parser.parse_args()
    config = ExerciseConfig.from_yaml().audio
    voice = PiperFrenchSpeech(config.voice, config.length_scale, config.volume)
    try:
        path = Path(args.preview)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(voice.synthesize(args.text))
        print(f"Extrait français créé : {path.resolve()}")
    finally:
        voice.close()


if __name__ == "__main__":
    main()
