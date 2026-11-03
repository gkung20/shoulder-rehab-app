"""Mouse-only patient flows must pause analysis and keep counts honest."""
from unittest.mock import Mock
import numpy as np
import pytest

from src.dashboard import render_dashboard, CANVAS_SIZE
from src.patient_controls import PatientControls, patient_buttons, dashboard_action_at
from src.session_processor import SessionProcessor, FrameAnalysis
from tests.test_session_processor import config, body


def test_visible_buttons_and_mouse_targets_share_one_definition():
    for mode in ("ready","running","paused","finished"):
        for button in patient_buttons(mode):
            x1,y1,x2,y2=button.bounds
            action=dashboard_action_at((x1+x2)//2,(y1+y2)//2,mode=mode)
            assert action == (button.action if button.enabled else None)
    assert dashboard_action_at(-1,-1) is None


def test_patient_can_start_pause_resume_finish_restart_without_keyboard():
    state=PatientControls()
    assert not state.apply("resume")
    assert state.apply("start") and state.mode == "running"
    assert not state.apply("arm_left")
    assert state.apply("pause") and state.mode == "paused"
    assert state.apply("arm_left")
    assert state.apply("resume") and state.mode == "running"
    assert state.apply("finish") and state.mode == "finished"
    assert not state.apply("pause")
    assert state.apply("restart") and state.mode == "ready"


def test_reading_help_automatically_pauses_and_does_not_automatically_resume():
    state=PatientControls(mode="running")
    assert state.apply("help")
    assert state.help_visible and state.mode == "paused"
    assert state.apply("help")
    assert not state.help_visible and state.mode == "paused"


def test_patient_renderer_handles_states_without_altering_camera_or_measurements():
    processor=SessionProcessor(config())
    image=np.full((480,640,3),90,np.uint8)
    original=image.copy()
    analysis=FrameAnalysis(0,metrics={"abduction":45.})
    for mode in ("ready","running","paused","finished"):
        rendered=render_dashboard(image,analysis,processor,mode=mode,help_visible=mode == "paused")
        assert rendered.shape == (CANVAS_SIZE[1],CANVAS_SIZE[0],3)
        assert np.array_equal(image,original)
        assert analysis.metrics == {"abduction":45.}


def test_fullscreen_text_is_rasterized_at_native_font_size_not_enlarged(monkeypatch):
    from PIL import ImageDraw
    recorded=[]
    original=ImageDraw.ImageDraw.text
    def record(draw,xy,text,*args,**kwargs):
        recorded.append((str(text),kwargs["font"].size))
        return original(draw,xy,text,*args,**kwargs)
    monkeypatch.setattr(ImageDraw.ImageDraw,"text",record)
    processor=SessionProcessor(config())
    source=np.zeros((720,1280,3),np.uint8)
    analysis=FrameAnalysis(0,metrics={})
    base=render_dashboard(source,analysis,processor,mode="ready")
    base_title=next(size for text,size in recorded if text == "mouvement")
    recorded.clear()
    fullscreen=render_dashboard(source,analysis,processor,mode="ready",output_size=(1920,1080))
    native_title=next(size for text,size in recorded if text == "mouvement")
    assert base.shape == (840,1280,3)
    assert fullscreen.shape == (1080,1920,3)
    assert base_title == 30
    assert native_title >= 38  # A bitmap upscale would still use the original 30px glyphs.
    assert np.count_nonzero(source) == 0


@pytest.mark.parametrize("window_dimensions",[(1280,840),(1920,1080)])
def test_native_mouse_buttons_pause_inference_and_finish_before_closing(monkeypatch,window_dimensions):
    import app_live_cv as app
    monkeypatch.setattr(app,"enable_high_dpi",lambda: None)
    created=[]
    original_processor=SessionProcessor
    def make_processor(cfg,arm="right"):
        processor=original_processor(cfg,arm)
        processor.process=Mock(wraps=processor.process)
        created.append(processor)
        return processor
    monkeypatch.setattr(app,"SessionProcessor",make_processor)
    saved_config=config()
    monkeypatch.setattr(app.ExerciseConfig,"from_yaml",lambda: saved_config)
    class Capture:
        status_message="Test camera"
        def __init__(self,**kwargs):
            self.t=0
        def __enter__(self):
            return self
        def __exit__(self,*args):
            pass
        def read_frame(self):
            self.t+=33
            return True,np.zeros((480,640,3),np.uint8),self.t,30.
    detector=Mock()
    detector.model_info={"file":"test"}
    detector.last_world_landmarks=body()[1]
    detector.detect.return_value=body()[0]
    detector.__enter__=Mock(return_value=detector)
    detector.__exit__=Mock(return_value=False)
    audio=Mock(enabled=True,status_message="Test voice")
    audio.__enter__=Mock(return_value=audio)
    audio.__exit__=Mock(return_value=False)
    monkeypatch.setattr(app,"VideoCaptureManager",Capture)
    monkeypatch.setattr(app,"PoseDetector",lambda **kwargs: detector)
    monkeypatch.setattr(app.AudioCoach,"from_config",lambda *args,**kwargs: audio)
    rendered_sizes=[]
    def fake_render(*args,**kwargs):
        width,height=kwargs["output_size"]
        rendered_sizes.append((width,height))
        return np.zeros((height,width,3),np.uint8)
    monkeypatch.setattr(app,"render_dashboard",fake_render)
    for name in ("namedWindow","resizeWindow","imshow","destroyAllWindows"):
        monkeypatch.setattr(app.cv2,name,lambda *args: None)
    displayed_shapes=[]
    monkeypatch.setattr(app.cv2,"imshow",lambda name,image: displayed_shapes.append(image.shape))
    monkeypatch.setattr(app.cv2,"getWindowImageRect",lambda name: (0,0,*window_dimensions))
    mouse={}
    monkeypatch.setattr(app.cv2,"setMouseCallback",lambda name,callback: mouse.update(callback=callback))
    monkeypatch.setattr(app.cv2,"getWindowProperty",lambda *args: 1)
    # First click starts; third pauses; sixth resumes; eighth finishes; tenth closes.
    clicks=iter([(100,760),None,(100,760),None,None,(100,760),None,(380,760),None,(1150,760)])
    def wait_key(delay):
        point=next(clicks)
        if point:
            width,height=window_dimensions
            scale=min(width/1280,height/840)
            x=(width-round(1280*scale))//2+round(point[0]*scale)
            y=(height-round(840*scale))//2+round(point[1]*scale)
            mouse["callback"](app.cv2.EVENT_LBUTTONUP,x,y,None,None)
        return 255
    monkeypatch.setattr(app.cv2,"waitKey",wait_key)
    assert app.main([]) == 0
    assert created[0].process.call_count == 4
    assert detector.detect.call_count == 4
    assert all(size == window_dimensions for size in rendered_sizes)
    assert all(shape == (window_dimensions[1],window_dimensions[0],3) for shape in displayed_shapes)
    audio.begin_session.assert_called_once()
    assert audio.silence.call_count >= 2


def test_live_session_paused_read_never_runs_detector_or_counts():
    from src.live_session import LiveSession
    session=object.__new__(LiveSession)
    session.closed=False
    session.paused=False
    session._resume_calibration=False
    session.capture=Mock()
    session.capture.read_frame.return_value=(True,np.zeros((480,640,3),np.uint8),1000,30.)
    session.detector=Mock()
    session.audio=Mock()
    session.processor=SessionProcessor(config())
    try:
        session.pause()
        _,analysis,_=session.read()
        assert analysis.status == "PAUSE"
        session.detector.detect.assert_not_called()
        assert session.processor.rules_engine.session.total_repetitions == 0
        session.audio.silence.assert_called_once()
    finally:
        session.close()
