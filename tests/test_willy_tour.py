"""Willy's tour, home screen and everyday lines, driven with a fake clock and a silent voice."""
import datetime as dt
from types import SimpleNamespace

import numpy as np

from src.rules_engine import ClinicalError, FeedbackLevel, LiveFeedback, RepetitionEvaluation
from src.session_processor import FrameAnalysis
from src.state_machine import ExercisePhase
from src.user_profile import Profile
from src.willy_tour import SCREEN_TOUR, ZONES, Moment, WillyDirector


class FakeAudio:
    def __init__(self, enabled=True):
        self.enabled, self.available, self.busy = enabled, True, False
        self.language = "fr"
        self.said = []
        self.last_line, self.last_line_at = None, float("-inf")

    def say(self, text, language=None, interrupt=True, ttl=20.):
        if not self.enabled:
            return False
        self.said.append((language, text))
        return True

    def set_language(self, language):
        self.language = language


class Session:
    def __init__(self):
        self.evaluations = []

    @property
    def total_repetitions(self):
        return len(self.evaluations)

    @property
    def correct_repetitions(self):
        return sum(e.is_correct for e in self.evaluations)

    @property
    def assessed_repetitions(self):
        return sum(e.status_label != "INDETERMINE" for e in self.evaluations)


class Harness:
    def __init__(self, tmp_path, **profile):
        self.t = 100.
        self.profile = Profile.load(tmp_path / "profile.json")
        for key, value in profile.items():
            setattr(self.profile, key, value)
        self.audio = FakeAudio()
        self.session = Session()
        self.processor = SimpleNamespace(arm="right", rules_engine=SimpleNamespace(session=self.session))
        self.director = WillyDirector(self.profile, self.audio, guide=None, clock=lambda: self.t)
        self.mode = "ready"
        self.alignment = None

    def frame(self, analysis=None, dt_=.1):
        self.t += dt_
        analysis = analysis or FrameAnalysis(self.t, metrics={}, status=self.mode.upper())
        self.director.update(Moment(self.t, self.mode, analysis, self.processor, self.alignment))

    def run(self, seconds, analysis=None):
        for _ in range(int(seconds / .1)):
            self.frame(analysis)

    def until(self, line_id, seconds=30, analysis=None):
        for _ in range(int(seconds / .1)):
            if self.line == line_id:
                return
            self.frame(analysis)
        raise AssertionError(f"waited for {line_id}, Willy is at {self.line}")

    @property
    def line(self):
        current = self.director.current
        return current.line_id if current else None

    @property
    def text(self):
        return self.director.current.texts[0]

    def press(self, action):
        self.director.notify(action)
        self.frame()


def _analysis(t, status="SUIVI ACTIF", phase=ExercisePhase.REST, cue="Continuez le mouvement", evaluation=None):
    analysis = FrameAnalysis(t, metrics={}, status=status, cue=LiveFeedback(cue, FeedbackLevel.INFO))
    analysis.phase = phase
    analysis.new_evaluation = evaluation
    return analysis


def test_first_use_tour_walks_through_every_scenario(tmp_path):
    h = Harness(tmp_path)
    d = h.director
    d.open()
    # Scenario 1: Willy greets in both languages, then the patient picks English.
    assert d.screen == "home" and h.line == "S1.01" and d.current.bilingual
    assert ("en", "Hi! I'm Willy.") in h.audio.said and ("fr", "Bonjour ! Je suis Willy.") in h.audio.said
    h.until("S1.02")
    assert [b.action for b in d.current.buttons] == ["lang_en", "lang_fr"]
    h.press("lang_en")
    assert h.profile.language == "en" and h.audio.language == "en" and h.line == "S1.03"
    h.until("S1.06")
    assert {b.action for b in d.current.buttons} == {"express_tour", "start_tour", "skip"}
    assert d.current.buttons[-1].action == "express_tour" and d.current.buttons[-1].primary  # offered first
    h.press("start_tour")  # the full tour
    assert h.line == "S1.08"
    # Scenario 2: safety, confirmed with one button; nothing else is allowed meanwhile.
    h.until("S2.03")
    assert d.current.sample == "pause"
    h.until("S2.06")
    assert not d.permits("start")
    h.press("understand")
    h.until("S3.01")
    assert d.screen == "dashboard" and d.want_avatars is True and d.want_silhouette is False
    # Scenario 3: a first name, the arm, the coach, the sound.
    h.until("S3.02")
    assert d.typing and d.overlay.text_field is not None
    for key in b"Amina":
        d.type_key(key)
    d.type_key(13)
    h.frame()
    assert h.text == "Nice to meet you, Amina!" and h.profile.name == "Amina"
    h.until("S3.04")
    assert d.current.spotlight == ZONES["arm_buttons"]
    assert d.permits("arm_left") and not d.permits("start") and not d.permits("details")
    h.processor.arm = "left"
    h.press("arm_left")
    assert h.text == "Got it: your left arm." and h.profile.arm == "left"
    h.until("S3.06")
    h.press("avatar_female")
    assert h.profile.avatar_gender == "female"
    h.until("S3.07")
    h.press("next")
    h.until("S3.08")
    h.audio.enabled = False
    h.press("audio")
    assert h.line == "S3.09"
    h.audio.enabled = True
    h.press("audio")
    assert h.line == "S3.08"
    h.press("next")
    h.until("S3.10")
    # Scenario 4: camera view with the silhouette; Willy reads the placement.
    h.until("S4.01")
    assert d.want_avatars is False and d.want_silhouette is True
    h.until("S4.04")
    assert d.wants_tracking
    h.alignment = (False, "Approchez-vous un peu")
    h.until("S4.05", seconds=6)
    assert h.text == "Come a little closer."
    h.alignment = (False, "Décalez-vous vers la droite")
    h.until("S4.07", seconds=8)
    assert h.text == "Move a little to your right."
    h.alignment = (True, "Bonne position")
    h.until("S4.09", seconds=6)
    h.until("S4.10")
    assert not d.wants_tracking and d.current.spotlight == ZONES["silhouette_button"]
    h.press("next")
    # Scenario 5: the screen, zone by zone, one Next each.
    for line_id, zone in SCREEN_TOUR:
        assert h.line == line_id
        assert d.current.spotlight == (ZONES[zone] if zone else None)
        h.press("next")
    # Scenario 6: Willy steps into the large panel and shows the movement.
    assert h.line == "S6.01" and d.overlay.willy_big
    h.until("S6.04")
    assert d.current.highlight == "shoulder_L"  # left arm, mirror view: the screen's left side
    h.until("S6.15", seconds=60)
    h.press("watch_again")
    assert h.line == "S6.02"
    h.until("S6.15", seconds=60)
    h.press("next")
    assert not d.overlay.willy_big
    # Scenario 7: the first real movements.
    assert h.line == "S7.01" and d.current.spotlight == ZONES["main_button"]
    assert d.permits("start") and not d.permits("details")
    h.mode = "running"
    h.press("start")
    assert d.coaching and d.permits("details")
    h.run(1, _analysis(h.t, status="CALIBRATION", cue="Restez au repos encore 2.0 s"))
    assert h.line == "S7.02"
    h.run(5, _analysis(h.t, status="CALIBRATION", cue="Restez au repos encore 1.0 s"))
    assert h.line == "S7.03"
    h.run(.3, _analysis(h.t))
    assert h.line == "S7.07"
    h.run(3, _analysis(h.t))
    assert h.line == "S7.08"
    h.run(2, _analysis(h.t, phase=ExercisePhase.RISING))
    assert h.line == "S7.09"
    h.run(2, _analysis(h.t, phase=ExercisePhase.HOLD))
    assert h.line == "S7.11"
    for index, correct in ((1, True), (2, False), (3, True)):
        evaluation = RepetitionEvaluation(index, "left", correct, "CORRECT" if correct else "A CORRIGER", [],
                                          errors=[] if correct else [ClinicalError("Coude plie", "x")])
        h.session.evaluations.append(evaluation)
        h.frame(_analysis(h.t, evaluation=evaluation))
        if index == 1:
            assert h.line == "S7.14"
            h.run(3, _analysis(h.t))
            h.run(1, _analysis(h.t, phase=ExercisePhase.RISING))
            assert h.line == "S7.17"
        elif index == 2:
            assert h.text == "Movement 2 done. Keep your arm straight."
            h.run(3, _analysis(h.t))
            h.run(1, _analysis(h.t, phase=ExercisePhase.RISING))
            assert h.line == "S7.18"
    h.until("S7.19", analysis=_analysis(h.t))
    assert h.profile.tour_done and not d.in_tour and d.allowed is None
    saved = Profile.load(tmp_path / "profile.json")
    assert saved.tour_done and saved.language == "en" and saved.name == "Amina" and saved.arm == "left"


def test_skipping_still_shows_the_safety_rules(tmp_path):
    h = Harness(tmp_path)
    d = h.director
    d.open()
    h.until("S1.02")
    h.press("lang_fr")
    h.until("S1.06")
    h.press("skip")
    assert h.line == "S1.07" and h.text.startswith("Pas de souci")
    h.until("S2.06")
    h.press("understand")
    h.run(3)
    assert d.screen == "dashboard" and h.profile.tour_done and d.allowed is None and not d.in_tour


def test_returning_patient_is_greeted_and_starts_from_the_home_button(tmp_path):
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    h = Harness(tmp_path, tour_done=True, language="fr", session_days=[yesterday])
    d = h.director
    d.open()
    assert d.screen == "home" and h.line == "E1.01"
    assert h.text.endswith("On fait vos exercices ?")
    h.until("E1.02")
    h.run(4)
    assert [b.action for b in d.current.buttons] == ["home_start"]
    h.press("home_start")
    assert d.screen == "dashboard" and d.current is None


def test_language_switch_repeats_the_current_line(tmp_path):
    h = Harness(tmp_path, language="fr")
    d = h.director
    d.open()
    h.until("S1.06")
    d.notify("language")
    assert d.language == "en" and h.line == "S1.06"
    assert h.text == "The full tour takes about 7 minutes. You can watch it later from Help."
    assert {b.action for b in d.current.buttons} == {"express_tour", "start_tour", "skip"}


def _finish_session(h, results):
    h.mode = "running"
    h.frame(_analysis(h.t))
    for index, (correct, label) in enumerate(results, 1):
        evaluation = RepetitionEvaluation(index, "right", correct, label, [],
                                          errors=[] if correct or label == "INDETERMINE"
                                          else [ClinicalError("Haussement d'epaule excessif", "x")])
        h.session.evaluations.append(evaluation)
        h.frame(_analysis(h.t, evaluation=evaluation))
    h.mode = "finished"
    h.frame()


def test_first_session_end_explains_the_results_then_later_ones_stay_short(tmp_path):
    h = Harness(tmp_path, tour_done=True, language="en")
    d = h.director
    d.screen = "dashboard"
    results = [(True, "CORRECT")] * 3 + [(False, "A CORRIGER")] * 2 + [(False, "INDETERMINE")]
    _finish_session(h, results)
    order = []
    for _ in range(400):
        if h.line and (not order or order[-1] != h.line):
            order.append(h.line)
        h.frame()
    assert [x for x in order if x.startswith("S8")] == ["S8.05", "S8.06", "S8.07", "S8.08", "S8.09",
                                                        "S8.10", "S8.11", "S8.12", "S8.13"]
    assert "S8.01" in h.profile.seen                                   # movement 4: where the Pause button is
    assert ("en", "Three spot on in a row!") in h.audio.said             # three spot-on movements in a row
    assert h.profile.done_today() and h.profile.last_correct == 3
    # A new session: the results are short this time, and the "how to read them" lines are not repeated.
    h.session.evaluations.clear()
    h.mode = "ready"
    h.frame()
    _finish_session(h, [(True, "CORRECT")] * 5)
    order = []
    for _ in range(300):
        if h.line and (not order or order[-1] != h.line):
            order.append(h.line)
        h.frame()
    assert "S8.05" in order and "E7.02" in order and "S8.10" not in order


def test_pause_lines_play_once(tmp_path):
    h = Harness(tmp_path, tour_done=True, language="fr")
    d = h.director
    d.screen = "dashboard"
    h.mode = "running"
    h.frame()
    h.mode = "paused"
    h.frame()
    assert h.line == "S8.02"
    h.run(11)
    assert h.line == "S8.03" and d.current.spotlight == ZONES["main_button"]
    h.mode = "running"
    h.run(1)
    h.mode = "paused"
    h.run(12)
    assert h.line not in ("S8.02", "S8.03")


def test_goodbye_waits_only_for_a_spoken_line(tmp_path):
    h = Harness(tmp_path, tour_done=True, language="en")
    d = h.director
    d.screen = "dashboard"
    d.notify("quit")
    assert h.line == "S8.14" and not d.ready_to_close(h.t)
    d.notify("quit")  # pressed twice: still one goodbye
    assert h.audio.said.count(("en", "Rest well, and see you next session!")) == 1
    h.t += 5
    assert d.ready_to_close(h.t)
    # Next time the app closes, the everyday goodbye; with the sound off, the window closes at once.
    later = Harness(tmp_path, tour_done=True, language="en")
    later.director.screen = "dashboard"
    later.audio.enabled = False
    later.director.notify("quit")
    assert later.line == "E7.03" and later.director.ready_to_close(later.t)


def test_profile_keeps_days_streaks_and_once_lines(tmp_path):
    profile = Profile.load(tmp_path / "p.json")
    today = dt.date(2026, 11, 23)
    for back in (3, 2, 1):
        profile.record_session(2, today - dt.timedelta(days=back))
    assert profile.streak(today) == 3 and profile.days_since_last(today) == 1 and not profile.done_today(today)
    assert profile.mark_seen("S8.01") and not profile.mark_seen("S8.01")
    profile.language = "en"
    assert profile.save()
    again = Profile.load(tmp_path / "p.json")
    assert again.language == "en" and again.seen == ["S8.01"] and len(again.session_days) == 3
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert Profile.load(tmp_path / "broken.json").language is None


def test_home_screen_draws_willy_and_its_buttons_are_clickable(tmp_path):
    from src.home_screen import render_home
    from src.willy import WillyGuide
    h = Harness(tmp_path)
    d = h.director
    d.guide = WillyGuide()
    d.open()
    h.until("S1.02")
    image = render_home(d, d.guide, (1600, 1000))
    assert image.shape == (1000, 1600, 3)
    actions = [action for action, _ in d.overlay.hit_boxes]
    assert actions == ["lang_en", "lang_fr"]
    for action, (left, top, right, bottom) in d.overlay.hit_boxes:
        assert d.overlay.action_at((left + right) / 2, (top + bottom) / 2) == action


def test_dashboard_overlay_dims_around_the_spotlight_and_records_buttons():
    from src.config import ExerciseConfig
    from src.dashboard import render_dashboard
    from src.session_processor import SessionProcessor
    from src.willy_overlay import Overlay, TourButton
    processor = SessionProcessor(ExerciseConfig.from_yaml())
    camera = np.full((480, 640, 3), 120, np.uint8)
    plain = render_dashboard(camera, FrameAnalysis(0.), processor, mode="ready", lang="en")
    overlay = Overlay(bubble=["This big button starts the session, pauses it and resumes it."],
                      buttons=[TourButton("next", "Next", True)], spotlight=ZONES["main_button"])
    lit = render_dashboard(camera, FrameAnalysis(0.), processor, mode="ready", lang="en", overlay=overlay)
    assert [a for a, _ in overlay.hit_boxes] == ["next"]
    x1, y1, x2, y2 = ZONES["main_button"]
    inside = (slice(y1 + 10, y2 - 10), slice(x1 + 10, x2 - 10))
    assert np.abs(lit[inside].astype(int) - plain[inside].astype(int)).mean() < 2   # the zone stays bright
    assert lit[40:70, 40:200].mean() < plain[40:70, 40:200].mean() - 40              # the rest dims
    left, top, right, bottom = overlay.hit_boxes[0][1]
    assert right <= x1 or x2 <= left or bottom <= y1 or y2 <= top  # the bubble never covers the spotlight


def test_english_coach_speaks_english_lines(monkeypatch):
    from src.audio_feedback import AudioCoach
    monkeypatch.setattr(AudioCoach, "_start_worker", lambda self: None)
    coach = AudioCoach(min_interval_sec=0, repeat_cooldown_sec=0, guidance_mode="complete", language="en")
    try:
        assert coach.speak_cue(LiveFeedback("Gardez l'epaule basse !", FeedbackLevel.WARNING))
        assert coach._queue.queue[-1].text == "Keep your shoulder down, relaxed."
        assert coach.last_line.id == "E4.07"
        assert not coach.speak_cue(LiveFeedback("Un message inconnu", FeedbackLevel.INFO))  # never French in English
        coach.set_language("fr")
        assert coach.speak_cue(LiveFeedback("Gardez l'epaule basse !", FeedbackLevel.WARNING))
        assert coach._queue.queue[-1].text == "Gardez l'épaule basse, sans forcer."
    finally:
        coach.stop()


def test_bubble_shows_lines_even_with_the_sound_off(monkeypatch):
    from src.audio_feedback import AudioCoach
    monkeypatch.setattr(AudioCoach, "_start_worker", lambda self: None)
    coach = AudioCoach(enabled=False, min_interval_sec=0, language="en")
    try:
        assert coach.speak_cue(LiveFeedback("Restez au repos encore 2.9 s", FeedbackLevel.INFO)) is False
        assert coach.last_line.id == "E3.01"
        result = RepetitionEvaluation(2, "right", True, "CORRECT", [])
        assert coach.speak_evaluation(result) is False
        assert coach.last_line.id in ("E5.01", "E5.02", "E5.03")
        assert coach.say("Hello") is False
    finally:
        coach.stop()


def test_each_language_gets_its_own_voice(monkeypatch):
    from src.audio_feedback import AudioCoach, _SpeechItem
    monkeypatch.setattr(AudioCoach, "_start_worker", lambda self: None)
    coach = AudioCoach(language="fr")
    built, spoken = [], []

    class Voice:
        def __init__(self, language):
            self.language, self.label = language, f"voice {language}"

        def say(self, text, cancel):
            spoken.append((self.language, text))
            if len(spoken) == 2:
                coach._stop_event.set()

        def close(self):
            pass

    def backend(language):
        built.append(language)
        return Voice(language)
    monkeypatch.setattr(coach, "_backend_for", backend)
    import time
    coach._queue.put(_SpeechItem("Hi! I'm Willy.", time.monotonic(), True, "en", 20.))
    coach._queue.put(_SpeechItem("Bonjour ! Je suis Willy.", time.monotonic(), True, "fr", 20.))
    coach._worker_loop()
    assert built == ["fr", "en"]
    assert spoken == [("en", "Hi! I'm Willy."), ("fr", "Bonjour ! Je suis Willy.")]
    coach.stop()
