"""Unit tests for src/audio_feedback.py offline French audio coaching."""

import time
import pytest
from types import SimpleNamespace

from src.audio_feedback import AudioCoach
from src.rules_engine import FeedbackLevel, LiveFeedback, RepetitionEvaluation, ClinicalError
from src.state_machine import RepetitionMetrics


@pytest.fixture(autouse=True)
def silent_speech_backend(monkeypatch):
    """Unit tests must never play audio or depend on installed Windows voices."""
    class SilentSpeech:
        label = "French test voice"
        def say(self, text, cancel):
            pass
        def close(self):
            pass
    monkeypatch.setattr(AudioCoach, "_make_backend", lambda self: SilentSpeech())


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
    coach = AudioCoach(enabled=True, min_interval_sec=0, repeat_cooldown_sec=2.0)
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
    coach = AudioCoach(enabled=True, repeat_cooldown_sec=0.01, min_interval_sec=0.01,guidance_mode="complete")
    try:
        # Warning cue is vocalized
        warn_cue = LiveFeedback(message="Gardez l'epaule basse !", level=FeedbackLevel.WARNING)
        assert coach.speak_cue(warn_cue) is True
        time.sleep(0.05)

        # Success cue is vocalized
        succ_cue = LiveFeedback(message="Tres bien ! Maintenez la position...", level=FeedbackLevel.SUCCESS)
        assert coach.speak_cue(succ_cue) is True
        time.sleep(0.05)

        # Phase instructions are also spoken, using cooldowns to avoid rapid repeats
        info_cue = LiveFeedback(message="Montez lentement le bras...", level=FeedbackLevel.INFO)
        assert coach.speak_cue(info_cue) is True
    finally:
        coach.stop()


def test_audio_coach_speak_evaluation():
    """Verify end-of-repetition audio announcements."""
    coach = AudioCoach(enabled=True, min_interval_sec=0.01, repeat_cooldown_sec=0.01,guidance_mode="complete")
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


def test_spoken_french_restores_accents_and_stabilizes_calibration_countdown():
    from src.audio_feedback import spoken_french
    assert "épaule" in spoken_french("Gardez l'epaule basse !")
    assert "côté" in spoken_french("Pret : levez le bras sur le cote")
    assert spoken_french("Restez au repos encore 2.9 s") == spoken_french("Restez au repos encore 0.1 s")


def test_only_french_system_voices_are_accepted():
    from src.speech import french_voice
    english = SimpleNamespace(name="Microsoft David",id="en-US",languages=["en-US"])
    french = SimpleNamespace(name="Microsoft Hortense",id="fr-FR",languages=[b"\x05fr-FR"])
    assert french_voice([english]) is None
    assert french_voice([english,french]) is french


def test_new_guidance_replaces_stale_pending_cues_and_mute_clears_queue(monkeypatch):
    monkeypatch.setattr(AudioCoach,"_start_worker",lambda self: None)
    coach=AudioCoach(min_interval_sec=0,repeat_cooldown_sec=0)
    coach.speak("Première consigne")
    coach.speak("Deuxième consigne")
    assert coach._queue.qsize() == 1
    assert coach._queue.queue[0].text == "Deuxième consigne"
    coach.speak("Résultat de répétition",force=True)
    coach.speak("Prochaine consigne")
    assert coach._queue.qsize() == 2
    assert coach._queue.queue[0].result
    assert coach.toggle() is False
    assert coach._queue.empty()
    assert coach._playback_cancel.is_set()
    coach.stop()


def test_worker_discards_expired_guidance(monkeypatch):
    from src.audio_feedback import _SpeechItem
    monkeypatch.setattr(AudioCoach,"_start_worker",lambda self: None)
    coach=AudioCoach()
    spoken=[]
    class Voice:
        label="Test French"
        def say(self,text,cancel):
            spoken.append(text)
            coach._stop_event.set()
        def close(self):
            pass
    monkeypatch.setattr(coach,"_make_backend",lambda: Voice())
    coach._queue.put(_SpeechItem("ancienne consigne",time.monotonic()-10))
    coach._queue.put(_SpeechItem("nouvelle consigne",time.monotonic()))
    coach._worker_loop()
    assert spoken == ["nouvelle consigne"]
    assert coach._queue.unfinished_tasks == 0
    coach.stop()


def test_audio_failure_is_visible_and_does_not_claim_to_speak(monkeypatch):
    monkeypatch.setattr(AudioCoach,"_start_worker",lambda self: None)
    coach=AudioCoach()
    def fail():
        raise RuntimeError("No French voice")
    monkeypatch.setattr(coach,"_make_backend",fail)
    coach._worker_loop()
    assert coach.available is False
    assert "indisponible" in coach.status_message
    assert coach.speak("Bonjour") is False
    coach.stop()


def test_quiet_voice_announces_setup_once_and_leaves_phases_to_text(monkeypatch):
    monkeypatch.setattr(AudioCoach,"_start_worker",lambda self: None)
    coach=AudioCoach(min_interval_sec=0)
    try:
        assert coach.length_scale == 1.3
        assert coach.speak_cue(LiveFeedback("Restez au repos encore 2.9 s",FeedbackLevel.INFO))
        assert not coach.speak_cue(LiveFeedback("Restez au repos encore 0.1 s",FeedbackLevel.INFO))
        for message in ("Pret : levez le bras sur le cote","Montez lentement le bras...",
                        "Maintenez dans la zone cible, puis redescendez","Controlez la descente lentement"):
            assert not coach.speak_cue(LiveFeedback(message,FeedbackLevel.INFO))
        coach.begin_session()
        assert coach.speak_cue(LiveFeedback("Montrez les deux epaules, gardez le bras au repos",FeedbackLevel.INFO))
    finally:
        coach.stop()


def test_quiet_corrections_require_persistence_spacing_and_long_repeat_cooldown(monkeypatch):
    monkeypatch.setattr(AudioCoach,"_start_worker",lambda self: None)
    clock=[0.]
    monkeypatch.setattr("src.audio_feedback.time.monotonic",lambda:clock[0])
    coach=AudioCoach()
    shoulder=LiveFeedback("Gardez l'epaule basse !",FeedbackLevel.WARNING)
    trunk=LiveFeedback("Gardez le tronc droit !",FeedbackLevel.WARNING)
    try:
        assert not coach.speak_cue(shoulder)
        clock[0]=1.6
        assert coach.speak_cue(shoulder)
        clock[0]=1.7
        assert not coach.speak_cue(trunk)
        clock[0]=3.3
        assert not coach.speak_cue(trunk)  # Different warning still respects the eight-second gap.
        clock[0]=9.7
        assert coach.speak_cue(trunk)
        clock[0]=10
        assert not coach.speak_cue(shoulder)
        clock[0]=12
        assert not coach.speak_cue(shoulder)
        clock[0]=43
        assert coach.speak_cue(shoulder)
    finally:
        coach.stop()


def test_quiet_voice_counts_milestones_without_announcing_each_result(monkeypatch):
    monkeypatch.setattr(AudioCoach,"_start_worker",lambda self: None)
    clock=[0.]
    monkeypatch.setattr("src.audio_feedback.time.monotonic",lambda:clock[0])
    coach=AudioCoach()
    accepted=[]
    try:
        for index in range(1,11):
            clock[0]=index*9.
            result=RepetitionEvaluation(index,"right",False,"INDETERMINE",[])
            if coach.speak_evaluation(result):
                accepted.append(index)
        assert accepted == [5,10]
        assert "validée" not in coach._queue.queue[-1].text
    finally:
        coach.stop()


def test_time_spent_paused_does_not_count_as_a_persistent_posture_warning(monkeypatch):
    monkeypatch.setattr(AudioCoach,"_start_worker",lambda self: None)
    clock=[0.]
    monkeypatch.setattr("src.audio_feedback.time.monotonic",lambda:clock[0])
    coach=AudioCoach()
    warning=LiveFeedback("Gardez le tronc droit !",FeedbackLevel.WARNING)
    try:
        assert not coach.speak_cue(warning)
        clock[0]=1.
        coach.silence()
        clock[0]=10.
        assert not coach.speak_cue(warning)
        clock[0]=11.6
        assert coach.speak_cue(warning)
    finally:
        coach.stop()
