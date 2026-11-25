"""The whole desktop app runs headless: home, a session with two counted movements, close."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np

import app_live_cv as cli
import src.desktop_app as desktop
from src import layout as L
from src.config import ExerciseConfig
from src.synthetic_pose import body, rep_angles
from src.user_profile import Profile
from src.willy_tour import WillyDirector


class FakeCapture:
    status_message = "Fake camera"

    def __init__(self, **kwargs):
        self.t = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read_frame(self):
        self.t += 33
        return True, np.full((480, 640, 3), 60, np.uint8), self.t, 30.


class FakeDetector:
    """Rest long enough to calibrate, then clean repetitions."""

    model_info = {"file": "fake"}

    def __init__(self, **kwargs):
        self.calls = 0
        self.angles = [0.] * 40 + rep_angles(rest=10, rise=30, hold=40, settle=10) * 4
        self.last_world_landmarks = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def detect(self, frame, timestamp_ms):
        angle = self.angles[min(self.calls, len(self.angles) - 1)]
        self.calls += 1
        landmarks, self.last_world_landmarks = body(angle)
        return landmarks


class FakeWindow:
    """Plays the patient: Start on Willy's home, Start the session, Finish after 2 movements, Close."""

    def __init__(self):
        self.app = None
        self.shown = 0
        self.closed = False
        self.clicked_quit = False

    def open(self, size, on_mouse):
        self.on_mouse = on_mouse

    def output_size(self):
        return (1280, 840)

    def show(self, image):
        assert image.shape == (840, 1280, 3)
        self.shown += 1

    def click(self, rect):
        x, y = rect.center
        self.on_mouse(cv2.EVENT_LBUTTONUP, round(x), round(y), None, None)

    def read_key(self):
        app = self.app
        assert self.shown < 3000, "the app never reached the end of the session"
        if app.director.screen == "home":
            for action, box in app.director.overlay.hit_boxes:
                if action == "home_start":
                    self.click(L.Rect(*box))
        elif app.controls.mode == "ready":
            self.click(L.MAIN_BUTTON)
        elif app.controls.mode == "running" and app.processor.rules_engine.session.total_repetitions >= 2:
            self.click(L.FINISH_BUTTON)
        elif app.controls.mode == "finished" and not self.clicked_quit and app.director.current is None:
            self.clicked_quit = True
            self.click(L.QUIT_BUTTON)
        elif app.controls.mode == "finished" and not self.clicked_quit and self.shown % 40 == 0:
            self.clicked_quit = True  # end-of-session lines still showing: close anyway
            self.click(L.QUIT_BUTTON)
        return 255

    def is_open(self):
        return True

    def close(self):
        self.closed = True


def test_app_runs_headless_from_home_to_a_finished_session(monkeypatch, tmp_path):
    monkeypatch.setenv("MOUVEMENT_DATA_DIR", str(tmp_path))
    profile = Profile.load()
    profile.language, profile.tour_done = "fr", True
    profile.save()
    clock = [1000.]

    def tick():
        clock[0] += .05
        return clock[0]

    class Director(WillyDirector):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, clock=lambda: clock[0], **kwargs)

    audio = Mock(enabled=True, available=True, busy=False, speaking=False, last_line=None, status_message="Fake voice")
    audio.say.return_value = True
    audio.__enter__ = Mock(return_value=audio)
    audio.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(desktop, "VideoCaptureManager", FakeCapture)
    monkeypatch.setattr(desktop, "PoseDetector", FakeDetector)
    monkeypatch.setattr(desktop.AudioCoach, "from_config", lambda *args, **kwargs: audio)
    monkeypatch.setattr(desktop, "enable_high_dpi", lambda: None)
    monkeypatch.setattr(desktop, "WillyDirector", Director)
    monkeypatch.setattr(desktop, "time", SimpleNamespace(monotonic=tick))

    config = ExerciseConfig.from_yaml()
    config = replace(config, calibration=replace(config.calibration, duration_sec=.6))
    _, args = cli.parse_args(["--no-avatars", "--no-hands"])
    window = FakeWindow()
    app = desktop.App(args, config, Profile.load(), window=window)
    window.app = app

    assert app.run() == 0
    session = app.processor.rules_engine.session
    assert session.total_repetitions >= 2
    assert window.shown >= 300 and window.closed
    assert Profile.load().session_days  # the session was recorded in the profile
