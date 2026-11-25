"""Safety: pain check before and after, 'J'ai mal', gentle stop rules and seated mode."""
from dataclasses import replace

from src import layout as L
from src.config import ExerciseConfig
from src.safety import SafetyMonitor
from src.session_processor import SessionProcessor
from src.session_store import load_sessions
from src.state_machine import ExercisePhase
from src.synthetic_pose import body
from src.user_profile import Plan
from tests.app_fakes import ScriptedWindow, make_app


# --------------------------------------------------------------------------- rules
def test_fatigue_from_lower_angles_or_repeated_compensations():
    monitor = SafetyMonitor(fatigue_drop_deg=15, window=3, compensation_streak=3, cooldown_sec=180)
    events = [monitor.on_rep(peak, "correct", [], now=t) for t, peak in enumerate((95, 94, 96, 85, 78, 74))]
    assert events[-1] == "fatigue" and events.count("fatigue") == 1
    assert monitor.on_rep(70, "correct", [], now=10) is None  # cooldown: one suggestion per 3 minutes
    other = SafetyMonitor(compensation_streak=3)
    assert [other.on_rep(90, "to_fix", ["Inclinaison du tronc"], now=t) for t in range(3)] == [None, None, "fatigue"]
    assert other.on_rep(90, "to_fix", [], now=500) is None  # a to-fix without compensation breaks the streak


def test_time_limit_and_pain_stops():
    monitor = SafetyMonitor(max_minutes=15, max_pain_stops=2)
    assert not monitor.time_up(14 * 60) and monitor.time_up(15 * 60) and not monitor.time_up(16 * 60)
    assert monitor.on_pain_stop() is None and monitor.on_pain_stop() == "end"
    safety = ExerciseConfig.from_yaml().safety
    assert SafetyMonitor.from_config(safety, Plan(max_session_min=20)).max_minutes == 20


def test_gentle_plan_lowers_the_target():
    gentle = Plan(target_min_deg=80, target_max_deg=100).gentle()
    assert (gentle.target_min_deg, gentle.target_max_deg) == (80, 90)
    narrow = Plan(target_min_deg=90, target_max_deg=95).gentle()
    assert narrow.target_max_deg == 85 and narrow.target_min_deg == 85


# --------------------------------------------------------------------------- the app
def start_then(after):
    def patient(window):
        app = window.app
        if app.director.screen == "home":
            window.click_action("home_start", app.director.overlay.hit_boxes)
        elif app.controls.mode == "ready" and app.modal is None and not getattr(window, "started", False):
            window.started = True
            window.click(L.MAIN_BUTTON)
        else:
            after(window, app)
    return patient


def finish_after_one_rep(window, app):
    if app.controls.mode == "running" and app.processor.rules_engine.session.total_repetitions >= 1:
        window.auto_pain = window.pain_after
        window.click(L.FINISH_BUTTON)
    elif app.controls.mode == "finished" and app.modal is None and not window.keys:
        window.press(27)


def test_pain_before_and_after_are_saved_and_a_rise_is_flagged(monkeypatch, tmp_path):
    window = ScriptedWindow(start_then(finish_after_one_rep), auto_pain=2)
    window.pain_after = 5
    app = make_app(monkeypatch, tmp_path, window, language="en", tour_done=True)
    assert app.run() == 0
    record = load_sessions()[-1]
    assert (record["pain_before"], record["pain_after"], record["gentle"]) == (2, 5, False)
    said = [call.args[0] for call in app.fake_audio.say.call_args_list]
    assert "Your shoulder pain right now, from 0 to 10?" in said
    assert "And now, your shoulder pain from 0 to 10?" in said


def test_middle_pain_gives_a_gentle_session(monkeypatch, tmp_path):
    window = ScriptedWindow(start_then(finish_after_one_rep), auto_pain=5)
    window.pain_after = 5
    app = make_app(monkeypatch, tmp_path, window, language="en", tour_done=True)
    assert app.run() == 0
    assert app.session_plan.target_max_deg == 90 and app.sets.reps_per_set == 7
    assert load_sessions()[-1]["gentle"] is True
    said = [call.args[0] for call in app.fake_audio.say.call_args_list]
    assert "Let's go gently today: a lower target and fewer movements." in said


def test_high_pain_means_no_session_today(monkeypatch, tmp_path):
    def wait_then_close(window, app):
        if app.modal is None and app.controls.mode == "ready" and window.started and not window.keys:
            window.press(27)
    window = ScriptedWindow(start_then(wait_then_close), auto_pain=8)
    app = make_app(monkeypatch, tmp_path, window, language="en", tour_done=True)
    assert app.run() == 0
    assert app.controls.mode == "ready" and app.processor.rules_engine.session.total_repetitions == 0
    record = load_sessions()[-1]
    assert record["pain_before"] == 8 and record["totals"]["reps"] == 0
    said = [call.args[0] for call in app.fake_audio.say.call_args_list]
    assert "That's a lot of pain. No exercise today: rest, and call your physio if it lasts." in said


def hurt_twice(window, app):
    machine = app.processor.state_machine
    hurts = getattr(window, "hurts", 0)
    if app.modal == "pain" and app.screens["pain"].check.choices:
        window.click_action("hurt_rest" if app.screens["pain"].check.can_continue else "hurt_end",
                            app.screens["pain"].hit_boxes)
    elif app.controls.mode == "running" and machine.current_phase == ExercisePhase.HOLD and hurts < 2:
        window.hurts = hurts + 1
        window.reps_at_hurt = app.processor.rules_engine.session.total_repetitions
        window.press("p")
    elif app.controls.mode == "paused" and app.modal is None and app.pain_rest_until is not None:
        window.click(L.MAIN_BUTTON)  # Resume: carry on gently
    elif app.controls.mode == "finished" and app.modal is None and not window.keys:
        window.press(27)


def test_it_hurts_stops_counting_logs_the_stop_and_ends_the_second_time(monkeypatch, tmp_path):
    window = ScriptedWindow(start_then(hurt_twice), auto_pain=3)
    app = make_app(monkeypatch, tmp_path, window, language="en", tour_done=True)
    assert app.run() == 0
    assert window.hurts == 2 and app.controls.mode == "finished"
    session = app.processor.rules_engine.session
    assert session.total_repetitions == window.reps_at_hurt  # the movement in HOLD was not counted
    assert session.interrupted_attempts >= 2
    record = load_sessions()[-1]
    stops = [s for s in record["stops"] if s["kind"] == "pain"]
    assert len(stops) == 2 and all(s["pain"] == 3 for s in stops) and record["gentle"] is True
    assert record["pain_after"] == 3
    said = [call.args[0] for call in app.fake_audio.say.call_args_list]
    assert "Let's stop here. Breathe and let your arm rest." in said
    assert "Rest a minute and continue gently, or end the session?" in said


def test_the_session_ends_when_the_plan_time_is_up(monkeypatch, tmp_path):
    def shorten_then_close(window, app):
        if app.safety is not None and app.safety.max_minutes > .05:
            app.safety.max_minutes = .05  # 3 seconds of active time
        if app.controls.mode == "finished" and app.modal is None and not window.keys:
            window.press(27)
    window = ScriptedWindow(start_then(shorten_then_close), auto_pain=1)
    app = make_app(monkeypatch, tmp_path, window, language="en", tour_done=True)
    assert app.run() == 0 and app.controls.mode == "finished"
    said = [call.args[0] for call in app.fake_audio.say.call_args_list]
    assert "That's enough for today. Well done for your effort." in said


# --------------------------------------------------------------------------- seated
def short_config():
    c = ExerciseConfig.from_yaml()
    return replace(c, calibration=replace(c.calibration, duration_sec=.6), filtering=replace(c.filtering, ema_alpha=1))


def run(processor, frames):
    reps = 0
    for i, (pts, world) in enumerate(frames):
        reps += processor.process(pts, world, 640, 480, i / 30).new_evaluation is not None
    return reps


def one_rep(**kwargs):
    angles = [0] * 40 + [i * 2 for i in range(46)] + [90] * 30 + [90 - i * 2 for i in range(46)] + [0] * 20
    return [body(a, **kwargs) for a in angles]


def test_seated_patients_calibrate_and_count_without_hips():
    seated = SessionProcessor(short_config(), plan=Plan(seated=True))
    assert run(seated, one_rep(seated=True)) == 1
    assert seated.calibrator.calibrated_data.is_calibrated
    standing = SessionProcessor(short_config(), plan=Plan(seated=False))
    assert run(standing, one_rep()) == 1  # standing patients: unchanged


def test_seated_lean_uses_the_shoulder_line():
    seated = SessionProcessor(short_config(), plan=Plan(seated=True))
    frames = one_rep(seated=True)
    run(seated, frames[:40])
    tilted = [p if i not in (11, 12) else type(p)(p.x, p.y + (.05 if i == 11 else -.05), p.visibility)
              for i, p in enumerate(frames[60][0])]
    frame = seated.process(tilted, frames[60][1], 640, 480, 41 / 30)
    assert frame.metrics["lean"] is not None and frame.metrics["lean"] > 5
