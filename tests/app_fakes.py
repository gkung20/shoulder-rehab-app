"""Fakes to run the desktop app headless in tests (camera, pose model, voice, window, clock)."""
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

    def __init__(self, camera_index=0, **kwargs):
        self.t = 0
        self.camera_index = camera_index
        self.reconnects = 0

    def reconnect(self):
        self.reconnects += 1
        return True

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
        self.rest = 40
        self.cycle = rep_angles(rest=10, rise=30, hold=40, settle=10)
        self.last_world_landmarks = None
        self.hand_up = False  # a test can raise the free hand

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def detect(self, frame, timestamp_ms):
        angle = 0. if self.calls < self.rest else self.cycle[(self.calls - self.rest) % len(self.cycle)]
        self.calls += 1
        landmarks, self.last_world_landmarks = body(angle, left_hand_up=self.hand_up)
        return landmarks


class ScriptedWindow:
    """A window whose patient is a function: `script(window)` runs after each frame."""

    def __init__(self, script=None, size=(1280, 840), auto_pain=1):
        self.app = None
        self.script = script
        self.auto_pain = auto_pain  # answers the pain check with this score (None: let the script answer)
        self.size = size
        self.shown = 0
        self.closed = False
        self.last = None
        self.keys = []

    def open(self, size, on_mouse):
        self.on_mouse = on_mouse

    def output_size(self):
        return self.size

    def show(self, image):
        assert image.shape == (self.size[1], self.size[0], 3)
        self.shown += 1
        self.last = image

    def click(self, rect):
        x, y = L.Rect(*rect).center
        self.on_mouse(cv2.EVENT_LBUTTONUP, round(x), round(y), None, None)

    def click_action(self, action, boxes):
        for name, box in boxes:
            if name == action:
                self.click(box)
                return True
        return False

    def press(self, key):
        self.keys.append(ord(key) if isinstance(key, str) else key)

    def read_key(self):
        assert self.shown < 3000, "the scripted patient never finished"
        app = self.app
        if (self.auto_pain is not None and app is not None and app.modal == "pain"
                and not app.screens["pain"].check.choices and not self.keys):
            return ord(str(self.auto_pain))
        if self.script:
            self.script(self)
        return self.keys.pop(0) if self.keys else 255

    def pump(self):
        self.pumps = getattr(self, "pumps", 0) + 1

    def is_open(self):
        return True

    def close(self):
        self.closed = True


def make_app(monkeypatch, tmp_path, window, args=("--no-avatars", "--no-hands"), calibration_sec=.6, **profile_fields):
    """A desktop App with fake devices and a fake clock, and a saved profile with `profile_fields`."""
    monkeypatch.setenv("MOUVEMENT_DATA_DIR", str(tmp_path))
    profile = Profile.load()
    for key, value in profile_fields.items():
        setattr(profile, key, value)
    profile.save()
    clock = [1000.]

    def tick():
        clock[0] += .05
        return clock[0]

    class Director(WillyDirector):
        def __init__(self, *a, **kwargs):
            super().__init__(*a, clock=lambda: clock[0], **kwargs)

    audio = Mock(enabled=True, available=True, busy=False, speaking=False, last_line=None, status_message="Fake voice")
    audio.say.return_value = True
    audio.__enter__ = Mock(return_value=audio)
    audio.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(desktop, "VideoCaptureManager", FakeCapture)
    monkeypatch.setattr(desktop, "PoseDetector", FakeDetector)
    monkeypatch.setattr(desktop.AudioCoach, "from_config", lambda *a, **kwargs: audio)
    monkeypatch.setattr(desktop, "enable_high_dpi", lambda: None)
    monkeypatch.setattr(desktop, "WillyDirector", Director)
    monkeypatch.setattr(desktop, "time", SimpleNamespace(monotonic=tick))
    config = ExerciseConfig.from_yaml()
    config = replace(config, calibration=replace(config.calibration, duration_sec=calibration_sec),
                     performance=replace(config.performance, pose_thread=False))  # one frame per step
    _, parsed = cli.parse_args(list(args))
    app = desktop.App(parsed, config, Profile.load(), window=window)
    window.app = app
    app.fake_audio = audio
    return app
