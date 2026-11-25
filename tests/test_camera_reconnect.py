"""When the camera stops, the app keeps its window, retries every 2 seconds and carries on."""
import numpy as np

import src.capture as capture
import src.desktop_app as desktop
from src import layout as L
from tests.app_fakes import FakeCapture, ScriptedWindow, make_app


class FakeCv:
    """cv2.VideoCapture stand-in: opens; reads frames."""

    def __init__(self, index, api=None):
        self.index = index

    def isOpened(self):
        return True

    def set(self, *args):
        return True

    def get(self, prop):
        return 640.

    def read(self):
        return True, np.zeros((480, 640, 3), np.uint8)

    def release(self):
        pass


def test_reconnect_keeps_timestamps_increasing(monkeypatch):
    monkeypatch.setattr(capture.cv2, "VideoCapture", FakeCv)
    manager = capture.VideoCaptureManager(camera_index=1)
    assert manager.open()
    stamps = [manager.read_frame()[2] for _ in range(3)]
    assert manager.reconnect() and manager.camera_index == 1
    stamps += [manager.read_frame()[2] for _ in range(3)]
    assert stamps == sorted(stamps) and len(set(stamps)) == len(stamps)


class FlakyCapture(FakeCapture):
    """Stops after 80 frames; the first two reconnections fail, the third works."""

    def read_frame(self):
        self.t += 33
        if 80 * 33 <= self.t and self.reconnects < 3:
            return False, None, self.t, 0.
        return True, np.full((480, 640, 3), 60, np.uint8), self.t, 30.

    def reconnect(self):
        self.reconnects += 1
        return self.reconnects >= 3


def test_the_session_carries_on_after_the_camera_comes_back(monkeypatch, tmp_path):
    def patient(window):
        app = window.app
        if app.director.screen == "home":
            window.click_action("home_start", app.director.overlay.hit_boxes)
        elif app.controls.mode == "ready" and app.modal is None:
            window.click(L.MAIN_BUTTON)
        if app.camera_lost_since is not None:
            window.saw_lost = True
        if getattr(window, "saw_lost", False) and app.camera_lost_since is None and app.controls.mode == "running":
            window.press(27)

    window = ScriptedWindow(patient)
    app = make_app(monkeypatch, tmp_path, window, language="en", tour_done=True)
    monkeypatch.setattr(desktop, "VideoCaptureManager", FlakyCapture)
    assert app.run() == 0
    assert window.saw_lost and app.capture.reconnects == 3 and app.controls.mode == "running"
    said = [call.args[0] for call in app.fake_audio.say.call_args_list]
    assert "The camera stopped. Check its cable; I'm trying again." in said
