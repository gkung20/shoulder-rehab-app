"""Free hand above the head for 2 s: pause/resume or Next, never from the working arm."""
from src.gesture import HandRaise
from src.geometry import Point2D
from src.synthetic_pose import body


def hold(gesture, seconds, start=0., **pose):
    fired = False
    for i in range(int(seconds * 30) + 1):
        landmarks, _ = body(**pose)
        fired = gesture.update(landmarks, "right", start + i / 30) or fired
    return fired


def test_fires_after_two_seconds_not_before():
    assert not hold(HandRaise(), 1.5, left_hand_up=True)
    gesture = HandRaise()
    assert hold(gesture, 2.05, left_hand_up=True)
    assert not hold(gesture, 2.5, start=2.1, left_hand_up=True)  # 3-second cool-down
    assert hold(gesture, 2.1, start=6., left_hand_up=True)


def test_progress_and_wrist_while_held():
    gesture = HandRaise()
    hold(gesture, 1.0, left_hand_up=True)
    assert 0.45 < gesture.progress < .55 and gesture.wrist is not None


def test_the_working_arm_never_triggers_it():
    assert not hold(HandRaise(), 3, right=160)
    assert not hold(HandRaise(), 3, right=160, right_hand_up=True)


def test_low_visibility_never_triggers_it():
    def dim(landmarks):
        return [Point2D(p.x, p.y, .3) if i == 15 else p for i, p in enumerate(landmarks)]
    gesture = HandRaise()
    fired = False
    for i in range(90):
        landmarks, _ = body(left_hand_up=True)
        fired = gesture.update(dim(landmarks), "right", i / 30) or fired
    assert not fired


def test_pause_and_resume_from_a_distance(monkeypatch, tmp_path):
    from src import layout as L
    from tests.app_fakes import ScriptedWindow, make_app

    def patient(window):
        app = window.app
        if app.director.screen == "home":
            window.click_action("home_start", app.director.overlay.hit_boxes)
        elif app.controls.mode == "ready" and app.modal is None:
            window.click(L.MAIN_BUTTON)
        elif app.controls.mode == "running" and not getattr(window, "paused", False):
            app.detector.hand_up = app.processor.rules_engine.session.total_repetitions >= 1
        elif app.controls.mode == "paused":
            window.paused = True
            assert app.hands_free  # paused by the gesture: keep watching for "resume"
        elif app.controls.mode == "running" and window.paused:
            app.detector.hand_up = False
            window.resumed = True
            window.press(27)

    window = ScriptedWindow(patient)
    app = make_app(monkeypatch, tmp_path, window, language="en", tour_done=True)
    assert app.run() == 0 and window.paused and window.resumed
    said = [call.args[0] for call in app.fake_audio.say.call_args_list]
    assert said.count("Got it!") >= 2
