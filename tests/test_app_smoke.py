"""The whole desktop app runs headless: home, a session with two counted movements, close."""
from src import layout as L
from src.session_store import load_sessions
from src.user_profile import Profile
from tests.app_fakes import ScriptedWindow, make_app


def patient(window):
    """Start on Willy's home, Start the session, Finish after 2 movements, then Close."""
    app = window.app
    if app.director.screen == "home":
        window.click_action("home_start", app.director.overlay.hit_boxes)
    elif app.controls.mode == "ready":
        window.click(L.MAIN_BUTTON)
    elif app.controls.mode == "running" and app.processor.rules_engine.session.total_repetitions >= 2:
        window.click(L.FINISH_BUTTON)
    elif app.controls.mode == "finished" and not getattr(window, "quit_clicked", False):
        if app.director.current is None or window.shown % 40 == 0:
            window.quit_clicked = True
            window.click(L.QUIT_BUTTON)


def test_app_runs_headless_from_home_to_a_finished_session(monkeypatch, tmp_path):
    window = ScriptedWindow(patient)
    app = make_app(monkeypatch, tmp_path, window, language="fr", tour_done=True)
    assert app.run() == 0
    assert app.processor.rules_engine.session.total_repetitions >= 2
    assert window.shown >= 300 and window.closed
    assert Profile.load().session_days  # the session was recorded in the profile
    sessions = load_sessions()
    assert len(sessions) == 1 and sessions[0]["totals"]["reps"] >= 2 and not sessions[0]["partial"]


def test_the_window_opens_at_once_with_willy_getting_ready(monkeypatch, tmp_path):
    shown = []

    class Window(ScriptedWindow):
        def show(self, image):
            shown.append(self.app.director is None)  # still loading: no Willy flow yet
            super().show(image)

    window = Window(lambda w: w.press(27))
    app = make_app(monkeypatch, tmp_path, window, language="en", tour_done=True)
    assert app.run() == 0
    assert shown[0] is True and window.pumps >= 3  # loading screens painted before anything else
    assert app.timings["first_window"] < 1.0 and app.timings["ready"] >= app.timings["first_window"]
