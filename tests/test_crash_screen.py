"""Phase 8.3: an unexpected error keeps the session, shows Willy's error screen and lands in the journal."""
import logging
import threading

import pytest

import src.desktop_app as desktop
from src import app_log
from src import layout as L
from src.pose_worker import PoseWorker
from src.session_store import load_sessions
from tests.app_fakes import FakeCapture, ScriptedWindow, make_app


@pytest.fixture
def journal(monkeypatch, tmp_path):
    monkeypatch.setenv("MOUVEMENT_DATA_DIR", str(tmp_path))
    started = app_log.setup(console=False)
    yield started
    app_log.stop()


def patient(window):
    """Start, do movements; on the error screen open the log folder, then close."""
    app = window.app
    if app.crash_boxes:
        actions = dict(app.crash_boxes)
        if not getattr(window, "opened_logs", False):
            window.opened_logs = True
            window.click(actions["open_logs"])
        else:
            window.click(actions["close"])
    elif app.director is not None and app.director.screen == "home":
        window.click_action("home_start", app.director.overlay.hit_boxes)
    elif app.controls.mode == "ready":
        window.click(L.MAIN_BUTTON)


def test_an_error_inside_tick_saves_the_session_shows_the_screen_and_logs_the_traceback(
        monkeypatch, tmp_path, journal):
    opened = []
    monkeypatch.setattr(app_log, "open_folder", lambda path: opened.append(path) or True)
    window = ScriptedWindow(patient)
    app = make_app(monkeypatch, tmp_path, window, language="fr", tour_done=True)
    original = desktop.App.tick

    def tick(self, *args, **kwargs):
        if self.processor.rules_engine.session.total_repetitions >= 2:
            raise RuntimeError("boom inside tick")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(desktop.App, "tick", tick)
    assert app.run() == 2
    # the session was kept, marked partial
    [record] = load_sessions()
    assert record["partial"] and record["totals"]["reps"] >= 2
    # Willy's error screen, with its two buttons, until "Close"
    assert app.crash_text[0] == "Un problème est survenu."
    assert app.crash_text[1].startswith("Vos résultats sont enregistrés.")
    assert opened == [app_log.log_dir()] and app.crash_boxes is None and window.closed
    # the traceback is in the journal
    text = journal.path.read_text(encoding="utf-8")
    assert "Erreur inattendue pendant la séance" in text
    assert "Traceback" in text and "RuntimeError: boom inside tick" in text


def test_the_screen_is_drawn_in_english_too(monkeypatch, tmp_path, journal):
    texts = []
    original = desktop.render_notice

    def spy(title, body="", output_size=None, language="fr", *args, **kwargs):
        texts.append((title, language))
        return original(title, body, output_size, language, *args, **kwargs)

    monkeypatch.setattr(desktop, "render_notice", spy)
    window = ScriptedWindow(lambda w: w.press(27) if w.app.crash_boxes else patient(w))
    app = make_app(monkeypatch, tmp_path, window, language="en", tour_done=True)
    monkeypatch.setattr(desktop.App, "tick", lambda self, *a, **k: (_ for _ in ()).throw(ValueError("x")))
    assert app.run() == 2
    assert ("Un problème est survenu.", "en") in texts  # translated by the page painter
    assert "ValueError: x" in journal.path.read_text(encoding="utf-8")


def test_an_error_in_the_camera_thread_reaches_the_screen_loop(journal):
    class Broken(FakeCapture):
        def read_frame(self):
            raise OSError("camera driver crashed")

    worker = PoseWorker(Broken(), None, threaded=True).start()
    for _ in range(200):
        if worker.error is not None:
            break
        threading.Event().wait(.01)
    with pytest.raises(OSError, match="camera driver crashed"):
        worker.poll()
    worker.stop()
    assert "camera driver crashed" in journal.path.read_text(encoding="utf-8")


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_console_lines_and_unhandled_thread_errors_go_to_the_journal(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("MOUVEMENT_DATA_DIR", str(tmp_path))
    journal = app_log.setup(console=False)  # here, not in a fixture: pytest swaps the console before each test
    try:
        print("[MODELE] ligne de console")
        thread = threading.Thread(target=lambda: 1 / 0, name="audio-test")
        thread.start()
        thread.join()
    finally:
        app_log.stop()
    text = journal.path.read_text(encoding="utf-8")
    assert "[MODELE] ligne de console" in text
    assert "Erreur non gérée dans le fil audio-test" in text and "ZeroDivisionError" in text
    assert "[MODELE] ligne de console" in capsys.readouterr().out  # the console still shows it


def test_the_journal_rotates_at_one_megabyte_with_five_old_files(journal):
    handler = journal.handler
    assert handler.maxBytes == 1_000_000 and handler.backupCount == 5
    assert journal.path.parent == app_log.log_dir() and journal.path.name == "mouvement.log"
    log = logging.getLogger("mouvement")
    for _ in range(3000):
        log.info("x" * 500)
    files = sorted(p.name for p in journal.path.parent.iterdir())
    assert "mouvement.log.1" in files and len(files) <= 6
