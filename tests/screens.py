"""Every screen of the desktop app, drawn headless with sample content (tests and previews).

`all_screens(language)` returns [(name, BGR image)]; `drawn_texts(language, **settings)` returns
every text each screen drew, with its pixel box, the colour used and the colour behind it. The
accessibility tests (Phase 10.2) use them to check that large text still fits and that high
contrast is readable everywhere.
"""
from contextlib import contextmanager
import datetime as dt
from dataclasses import replace
from pathlib import Path
import tempfile

import numpy as np

from src import accessibility
from src.config import ExerciseConfig
from src.dashboard import _Painter, render_dashboard
from src.home_screen import render_home
from src.notice_screen import render_notice
from src.pain_screen import PainCheck, render_pain
from src.physio_settings import REST_WARNING, PinPad, SettingsForm, render_pin, render_settings
from src.results_screen import render_history, render_results
from src.session_plan import SetTracker
from src.session_processor import FrameAnalysis, SessionProcessor
from src.state_machine import ExercisePhase
from src.user_profile import Plan
from src.willy import WillyGuide
from src.willy_overlay import Overlay, TourButton

SIZE = (1280, 840)


def _record(reps=12):
    start = dt.datetime(2026, 11, 25, 10, 30)
    rows = [{"n": i + 1, "t": i * 6., "peak_deg": 84. + (i % 5) * 3, "hold_s": 1., "rise_s": 2., "lower_s": 2.,
             "target_reached": True, "quality": ("correct", "to_fix", "unknown")[i % 3],
             "issues": ["Coude plie"] if i % 3 == 1 else [], "tip": "E5.14" if i % 3 == 1 else None}
            for i in range(reps)]
    return {"schema": 1, "exercise": "abduction", "arm": "right", "plan": {"target_min_deg": 80, "target_max_deg": 100},
            "started_at": start.isoformat(), "ended_at": (start + dt.timedelta(minutes=9)).isoformat(),
            "duration_s": 540., "pain_before": 2, "pain_after": 3, "gentle": False, "stops": [], "reps": rows,
            "totals": {"reps": reps, "correct": 4, "to_fix": 4, "unknown": 4, "best_peak_deg": 96., "mean_peak_deg": 90.,
                       "goal": 30, "goal_reached": False, "sets_done": 1}}


def _history(today):
    return [dict(_record(8 + d % 6), started_at=dt.datetime.combine(today - dt.timedelta(days=d), dt.time(10)).isoformat())
            for d in range(0, 28, 2)]


def _home(language, tour_done):
    from tests.test_willy_tour import Harness
    h = Harness(Path(tempfile.mkdtemp()), **({"language": language, "tour_done": True} if tour_done else {}))
    h.director.results_available = True
    h.director.open()
    if tour_done:  # the everyday welcome, with its buttons
        h.run(1.)
    else:          # the longest offer: three buttons
        h.until("S1.02")
        h.press(f"lang_{language}")
        h.until("S1.06")
    return h.director


def screen_makers(language="fr", guide=None):
    """[(name, a function that draws the screen)], so a test can watch each one being drawn."""
    guide = guide or WillyGuide()
    config = ExerciseConfig.from_yaml()
    processor = SessionProcessor(config)
    camera = np.full((480, 640, 3), 70, np.uint8)
    makers = [("home_offer", lambda: render_home(_home(language, False), guide, SIZE)),
              ("home_welcome", lambda: render_home(_home(language, True), guide, SIZE))]

    def dashboard(mode, analysis=None, **kwargs):
        analysis = analysis or FrameAnalysis(1., metrics={"abduction": 64.}, status="SUIVI ACTIF", phase=ExercisePhase.RISING)
        return lambda: render_dashboard(camera, analysis, processor, mode=mode, output_size=SIZE, lang=language,
                                        willy=guide, avatars=False, cache=False, **kwargs)

    for mode in ("ready", "running", "paused", "finished"):
        makers.append((f"dashboard_{mode}", dashboard(mode)))
    sets = SetTracker(reps_per_set=10, sets=3, rest_sec=60.)
    for _ in range(10):
        sets.add_rep(0.)
    makers += [
        ("dashboard_rest", dashboard("paused", FrameAnalysis(1., metrics={}), sets=sets, now=10.)),
        ("dashboard_help", dashboard("ready", FrameAnalysis(1., metrics={}), help_visible=True)),
        ("dashboard_details", dashboard("running", details=True)),
        ("dashboard_bubble", dashboard("ready", FrameAnalysis(1., metrics={}), overlay=Overlay(
            bubble=["Ce grand bouton lance la séance, la met en pause et la reprend." if language == "fr"
                    else "This big button starts, pauses and resumes the session."],
            buttons=[TourButton("back", "Retour" if language == "fr" else "Back"),
                     TourButton("next", "Suivant" if language == "fr" else "Next", True)],
            spotlight=(26, 750, 210, 806), progress=(4, 6)))),
        ("pin", lambda: render_pin(PinPad(message="Code incorrect."), SIZE, language)),
    ]
    plan = Plan.from_config(config)
    for page in ("plan", "device"):
        def settings(page=page):
            form = SettingsForm(plan, resting_angle=18., resting_date="25/11/2026", page=page,
                                names={"abduction": {"fr": "Un bras", "en": "One arm"}})
            form.warning = REST_WARNING
            return render_settings(form, SIZE, language)
        makers.append((f"settings_{page}", settings))
    today = dt.date(2026, 11, 27)
    makers += [
        ("results", lambda: render_results(_record(), SIZE, language, guide)),
        ("history", lambda: render_history(_history(today), SIZE, language, streak=3, today=today, can_open=True)),
        ("pain", lambda: render_pain(PainCheck(), "Votre douleur à l'épaule maintenant, de 0 à 10 ?" if language == "fr"
                                     else "Your shoulder pain right now, from 0 to 10?", SIZE, language, guide)),
        ("notice", lambda: render_notice("Caméra déconnectée, reconnexion…", "Je reconnecte la caméra, un instant.",
                                         SIZE, language, guide)),
    ]
    return makers


def _image(result):
    return result[0] if isinstance(result, tuple) else result


def all_screens(language="fr", guide=None):
    return [(name, _image(make())) for name, make in screen_makers(language, guide)]


@contextmanager
def with_settings(**values):
    """The accessibility settings changed for a block (`with with_settings(large_text=True): ...`)."""
    previous = accessibility.current()
    accessibility.set_current(replace(previous, **values))
    try:
        yield
    finally:
        accessibility.set_current(previous)


def drawn_texts(language="fr", **settings):
    """{screen: [(pixel box, text, colour used, colour behind)]} for every text drawn."""
    original = _Painter.put
    texts, current = {}, [None]

    def put(self, point, text, font, color):
        box = self.draw.textbbox(point, text, font=font)
        if text.strip():
            texts.setdefault(current[0], []).append((box, text, self.ink(point, text, font, color), self.behind(box)))
        return original(self, point, text, font, color)

    _Painter.put = put
    try:
        with with_settings(**settings):
            for name, make in screen_makers(language):
                current[0] = name
                make()
    finally:
        _Painter.put = original
    return texts


def overlaps(entries, tolerance=2):
    """Pairs of texts whose boxes overlap by more than `tolerance` pixels both ways."""
    found = []
    for i, (a, ta, *_) in enumerate(entries):
        for b, tb, *_ in entries[i + 1:]:
            if min(a[2], b[2]) - max(a[0], b[0]) > tolerance and min(a[3], b[3]) - max(a[1], b[1]) > tolerance:
                found.append((ta, tb))
    return found
