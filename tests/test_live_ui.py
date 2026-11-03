"""Exercise actual Streamlit controls and resource cleanup without camera access."""
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock

import numpy as np
from streamlit.testing.v1 import AppTest

from src.session_processor import SessionProcessor
from tests.test_session_processor import body

APP = Path(__file__).resolve().parents[1] / "app_streamlit.py"


def button(app, label):
    return next(b for b in app.button if b.label == label)


def test_streamlit_idle_and_invalid_settings_do_not_open_camera():
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert app.session_state.runtime is None
    next(s for s in app.slider if s.label == "Cible min (deg)").set_value(120)
    app.run()
    assert not app.exception
    assert button(app,"Commencer ma séance").disabled
    assert app.sidebar.error


def test_streamlit_start_stop_and_reset_close_resources(monkeypatch):
    resources = []

    class FakeLiveSession:
        def __init__(self, config, arm, audio_enabled, rules_engine):
            self.processor = SessionProcessor(config,arm,rules_engine)
            self.t = 0.
            self.closed = False
            self.paused = False
            resources.append(self)

        def read(self):
            self.t += 1/30
            frame = self.processor.process(*body(),640,480,self.t)
            return np.zeros((480,640,3),dtype=np.uint8),frame,30

        def close(self):
            self.closed = True

        def pause(self):
            self.paused = True

        def resume(self):
            self.paused = False

    monkeypatch.setattr("src.live_session.LiveSession",FakeLiveSession)
    app = AppTest.from_file(APP).run()
    next(w for w in app.number_input if w.label.startswith("Index camera")).set_value(2).run()
    next(w for w in app.selectbox if w.label == "Modele pose").select("lite").run()
    button(app,"Commencer ma séance").click().run()
    assert not app.exception
    assert app.session_state.is_running
    assert resources[0].processor.config.camera.index == 2
    assert resources[0].processor.config.pose.model == "lite"
    assert all(s.disabled for s in app.slider)
    button(app,"Faire une pause").click().run()
    assert resources[0].paused
    button(app,"Reprendre").click().run()
    assert not resources[0].paused
    button(app,"Terminer ma séance").click().run()
    assert not app.exception
    assert resources[0].closed
    assert not app.session_state.is_running
    button(app,"Commencer une nouvelle séance").click().run()
    assert resources[-1].closed
    assert app.session_state.rules_engine.session.total_repetitions == 0


def test_patient_settings_are_simple_and_professional_settings_start_collapsed():
    app=AppTest.from_file(APP).run()
    assert not app.exception
    advanced=next(e for e in app.expander if e.label == "Réglages avancés")
    assert advanced.proto.expanded is False
    assert next(w for w in app.selectbox if w.label == "Accompagnement vocal").value == "Voix discrète"
    assert next(w for w in app.select_slider if w.label == "Vitesse de la voix").value == "Lente"


def test_model_startup_failure_releases_camera(monkeypatch):
    from src.live_session import LiveSession
    capture = Mock()
    capture.open.return_value = True
    monkeypatch.setattr("src.live_session.VideoCaptureManager",lambda **kwargs: capture)
    monkeypatch.setattr("src.live_session.PoseDetector", Mock(side_effect=FileNotFoundError("Missing model")))
    import pytest
    with pytest.raises(FileNotFoundError):
        LiveSession(None)
    capture.release.assert_called_once()


def test_zero_world_visibility_is_preserved():
    """A confidence of 0.0 must not be replaced by the default 1.0."""
    from src.pose_detector import PoseDetector
    from mediapipe.tasks.python import vision
    detector = object.__new__(PoseDetector)
    detector.running_mode = vision.RunningMode.VIDEO
    detector._last_timestamp_ms = 0
    point = SimpleNamespace(x=.5,y=.5,z=0.,visibility=0.)
    detector.landmarker = Mock()
    detector.landmarker.detect_for_video.return_value = SimpleNamespace(
        pose_landmarks=[[point]*33],pose_world_landmarks=[[point]*33])
    pts = detector.detect(np.zeros((48,64,3),dtype=np.uint8),1)
    assert pts[0].visibility == 0.
    assert detector.last_world_landmarks[0].visibility == 0.
