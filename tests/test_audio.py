"""Unit tests for src/audio_feedback.py offline French audio coaching."""

import time
import pytest

from src.audio_feedback import AudioCoach
from src.rules_engine import FeedbackLevel, LiveFeedback, RepetitionEvaluation, ClinicalError
from src.state_machine import RepetitionMetrics


def test_audio_coach_initialization():
    """Verify audio coach initializes cleanly with custom throttling parameters."""
    coach = AudioCoach(enabled=False, speech_rate=150, min_interval_sec=1.5, repeat_cooldown_sec=3.0)
    assert coach.enabled is False
    assert coach.speech_rate == 150
    assert coach.min_interval_sec == 1.5
    assert coach.repeat_cooldown_sec == 3.0
    coach.stop()


def test_audio_coach_disabled_rejects_messages():
    """Verify that disabled coach drops speech requests immediately without thread allocation."""
    coach = AudioCoach(enabled=False)
    res = coach.speak("Bonjour")
    assert res is False
    coach.stop()


def test_audio_coach_throttles_rapid_duplicates():
    """Verify identical messages are dropped by repeat cooldown."""
    coach = AudioCoach(enabled=True, min_interval_sec=0.1, repeat_cooldown_sec=2.0)
    try:
        first = coach.speak("Gardez le tronc droit !", force=True)
        assert first is True

        # Immediate duplicate should be throttled
        duplicate = coach.speak("Gardez le tronc droit !")
        assert duplicate is False

        # Different phrase with priority should be accepted
        different = coach.speak("Gardez l'epaule basse !", priority=True)
        assert different is True
    finally:
        coach.stop()


def test_audio_coach_toggle():
    """Verify mute / unmute toggle behavior."""
    coach = AudioCoach(enabled=True)
    try:
        assert coach.enabled is True
        new_state = coach.toggle()
        assert new_state is False
        assert coach.enabled is False
        assert coach.speak("Test") is False

        coach.toggle()
        assert coach.enabled is True
    finally:
        coach.stop()


def test_audio_coach_speak_cue():
    """Verify cues are filtered based on FeedbackLevel."""
    coach = AudioCoach(enabled=True, repeat_cooldown_sec=0.01, min_interval_sec=0.01)
    try:
        # Warning cue is vocalized
        warn_cue = LiveFeedback(message="Gardez l'epaule basse !", level=FeedbackLevel.WARNING)
        assert coach.speak_cue(warn_cue) is True
        time.sleep(0.05)

        # Success cue is vocalized
        succ_cue = LiveFeedback(message="Tres bien ! Maintenez la position...", level=FeedbackLevel.SUCCESS)
        assert coach.speak_cue(succ_cue) is True
        time.sleep(0.05)

        # Normal INFO cue during motion is omitted from vocal spam to protect cognitive load
        info_cue = LiveFeedback(message="Montez lentement le bras...", level=FeedbackLevel.INFO)
        assert coach.speak_cue(info_cue) is False
    finally:
        coach.stop()


def test_audio_coach_speak_evaluation():
    """Verify end-of-repetition audio announcements."""
    coach = AudioCoach(enabled=True, min_interval_sec=0.01, repeat_cooldown_sec=0.01)
    try:
        # 1. Correct repetition
        correct_eval = RepetitionEvaluation(
            rep_index=1,
            arm="right",
            is_correct=True,
            status_label="CORRECT",
            reasons=[],
        )
        assert coach.speak_evaluation(correct_eval) is True
        time.sleep(0.05)

        # 2. Flawed repetition
        incorrect_eval = RepetitionEvaluation(
            rep_index=2,
            arm="right",
            is_correct=False,
            status_label="A CORRIGER",
            reasons=["Haussement d'epaule excessif (18% > 12%)"],
            errors=[ClinicalError(category="Haussement", detail="Haussement d'epaule excessif")],
        )
        assert coach.speak_evaluation(incorrect_eval) is True
    finally:
        coach.stop()
