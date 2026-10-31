"""Offline Text-To-Speech audio feedback coach in French.

Runs entirely locally without cloud dependencies using Windows SAPI5 / pyttsx3.
Uses a non-blocking background worker thread and smart phrase throttling so
the computer vision loop remains ultra-responsive (~30-60 FPS).
"""

import queue
import threading
import time
from typing import Dict, Optional

try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False

from src.rules_engine import FeedbackLevel, LiveFeedback, RepetitionEvaluation


class AudioCoach:
    """Non-blocking offline French audio coach for real-time rehabilitation biofeedback."""

    def __init__(
        self,
        enabled: bool = True,
        speech_rate: int = 160,
        min_interval_sec: float = 1.8,
        repeat_cooldown_sec: float = 3.5,
    ):
        """Initialize the AudioCoach.

        Args:
            enabled: Initial audio enabled state.
            speech_rate: Words per minute (default 160 is natural conversational pace).
            min_interval_sec: Minimum time between any two spoken utterances.
            repeat_cooldown_sec: Minimum cooldown before repeating the exact same cue.
        """
        self.enabled = enabled and HAS_PYTTSX3
        self.speech_rate = speech_rate
        self.min_interval_sec = min_interval_sec
        self.repeat_cooldown_sec = repeat_cooldown_sec

        self._queue: queue.Queue = queue.Queue(maxsize=3)
        self._stop_event = threading.Event()
        self._last_speech_time: float = 0.0
        self._last_spoken_cues: Dict[str, float] = {}
        self._lock = threading.Lock()

        self._thread: Optional[threading.Thread] = None
        if self.enabled:
            self._start_worker()

    def _start_worker(self) -> None:
        """Start the background daemon speech synthesis worker."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def _worker_loop(self) -> None:
        """Background thread target that consumes speech tasks."""
        engine = None
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", self.speech_rate)

            # Prefer native French voice if present
            voices = engine.getProperty("voices")
            for v in voices:
                name_lower = v.name.lower()
                id_lower = v.id.lower()
                if "french" in name_lower or "hortense" in name_lower or "fr-fr" in id_lower or "_fr_" in id_lower:
                    engine.setProperty("voice", v.id)
                    break
        except Exception:
            # Fallback if engine fails to initialize
            engine = None

        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if item is None:
                self._queue.task_done()
                break

            text = item
            if engine is not None and self.enabled:
                try:
                    engine.say(text)
                    engine.runAndWait()
                except Exception:
                    pass

            self._queue.task_done()

        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass

    def speak(self, message: str, priority: bool = False, force: bool = False) -> bool:
        """Queue a message to be spoken if throttling permits.

        Args:
            message: French text to vocalize.
            priority: If True, bypasses non-critical interval gating.
            force: If True, ignores all cooldown timers.

        Returns:
            True if message was accepted into queue, False if dropped by throttling.
        """
        if not self.enabled or not message:
            return False

        now = time.monotonic()
        clean_msg = message.strip()

        with self._lock:
            # Check repetition cooldown for identical phrase
            last_time = self._last_spoken_cues.get(clean_msg, 0.0)
            if not force and (now - last_time < self.repeat_cooldown_sec):
                return False

            # Check general speech pacing interval
            if not force and not priority and (now - self._last_speech_time < self.min_interval_sec):
                return False

            # Drop stale item if queue is full to prioritize fresh guidance
            if self._queue.full():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except (queue.Empty, ValueError):
                    pass

            try:
                self._queue.put_nowait(clean_msg)
                self._last_speech_time = now
                self._last_spoken_cues[clean_msg] = now
                return True
            except queue.Full:
                return False

    def speak_cue(self, feedback: Optional[LiveFeedback]) -> bool:
        """Process and optionally vocalize a live coaching cue."""
        if feedback is None or not feedback.message:
            return False

        is_priority = (feedback.level == FeedbackLevel.WARNING)
        # We vocalize warning corrections and success affirmations
        if feedback.level in (FeedbackLevel.WARNING, FeedbackLevel.SUCCESS):
            return self.speak(feedback.message, priority=is_priority)

        return False

    def speak_evaluation(self, eval_result: RepetitionEvaluation) -> bool:
        """Announce the result of a completed repetition.

        Args:
            eval_result: Diagnostic report of the completed repetition.

        Returns:
            True if queued successfully.
        """
        if eval_result.is_correct:
            msg = f"Répétition {eval_result.rep_index} validée !"
        else:
            if eval_result.reasons:
                first_reason = eval_result.reasons[0].split("(")[0].strip()
                msg = f"Répétition {eval_result.rep_index} à corriger : {first_reason}"
            else:
                msg = f"Répétition {eval_result.rep_index} à corriger."

        return self.speak(msg, priority=True, force=True)

    def toggle(self) -> bool:
        """Toggle audio feedback on/off.

        Returns:
            New enabled state.
        """
        self.enabled = not self.enabled
        if self.enabled and (self._thread is None or not self._thread.is_alive()):
            self._start_worker()
        return self.enabled

    def stop(self) -> None:
        """Gracefully terminate the background speech synthesis thread."""
        self._stop_event.set()
        try:
            self._queue.put_nowait(None)
        except (queue.Full, ValueError):
            pass

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
