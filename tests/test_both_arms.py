"""Phase 10.1: the second exercise, both arms raised sideways together."""
from dataclasses import replace

import numpy as np
import pytest

from src.config import ExerciseConfig
from src.cues import Cue
from src.exercises import get_exercise, load_exercises
from src.physio_settings import BOTH_ARMS_LABEL, SettingsForm, render_settings
from src.rules_engine import ERR_ARMS_UNEVEN
from src.session_processor import SessionProcessor, repetition_log
from src.silhouette import ARM_REACH_SIDE, EDGE, layout, patient_alignment
from src.synthetic_pose import body
from src.user_profile import Plan
from src.willy import WillyGuide
from src.willy_lines import WillyScript, tip_line_id

WIDTH, HEIGHT = 1280, 720


def config():
    c = ExerciseConfig.from_yaml()
    return replace(c, calibration=replace(c.calibration, duration_sec=.6), filtering=replace(c.filtering, ema_alpha=1))


def both_processor(**plan):
    exercise = get_exercise("both_arms")
    return SessionProcessor(config(), "right", exercise=exercise,
                            plan=Plan(exercise="both_arms", **plan) if plan else None)


def movement(right_peak, left_peak, fps=30):
    """Rest, a two-second rise, a one-second hold and a two-second lowering, for each arm."""
    def curve(peak):
        return [0.] * 30 + [i * peak / 60 for i in range(61)] + [peak] * 30 + [peak - i * peak / 60 for i in range(1, 61)] + [0.] * 10
    return list(zip(curve(right_peak), curve(left_peak)))


def run(processor, moves, start=0.):
    frames, t = [], start
    for right, left in moves:
        pts, world = body(right, left, width=WIDTH, height=HEIGHT, center=WIDTH / HEIGHT / 2)
        frames.append(processor.process(pts, world, WIDTH, HEIGHT, t))
        t += 1 / 30
    return frames, [f.new_evaluation for f in frames if f.new_evaluation]


def test_the_exercise_file_loads_with_both_arms():
    exercise = load_exercises()["both_arms"]
    assert exercise.both_arms and exercise.camera_view == "front" and exercise.willy_demo == "raise_both"
    assert exercise.short_name("fr") == "Deux bras" and exercise.name("en") == "Both arms sideways"
    assert get_exercise("abduction").short_name("en") == "One arm"


def test_a_movement_counts_when_both_arms_reach_the_target():
    processor = both_processor()
    assert processor.arm == "both" and processor.state_machine.arm == "both"
    processor.recalibrate("left")  # nothing to choose: still both arms
    assert processor.arm == "both"
    frames, evaluations = run(processor, movement(90, 90) * 3)
    assert len(evaluations) == 3 and all(e.is_correct for e in evaluations)
    rep = evaluations[0].metrics
    assert rep.arm == "both" and rep.peaks == {"left": pytest.approx(90, abs=.5), "right": pytest.approx(90, abs=.5)}
    assert rep.max_asymmetry_deg < 2
    top = max(frames, key=lambda f: f.metrics.get("abduction") or 0)
    assert top.metrics["abduction"] == pytest.approx(min(top.metrics["abduction_left"], top.metrics["abduction_right"]))
    log = repetition_log(evaluations[0])
    assert log["bras"] == "BOTH" and log["angle_max_gauche_deg"] == pytest.approx(90, abs=.5)


def test_the_lower_arm_decides_if_the_target_was_reached():
    _, evaluations = run(both_processor(), movement(90, 60))
    assert len(evaluations) == 1
    evaluation = evaluations[0]
    assert not evaluation.metrics.target_reached and evaluation.metrics.peak_abduction_deg == pytest.approx(60, abs=.5)
    assert ERR_ARMS_UNEVEN in [error.category for error in evaluation.errors]


def test_more_than_15_degrees_between_the_arms_is_flagged_live_and_after():
    frames, evaluations = run(both_processor(), movement(100, 82))
    assert any(f.cue.code == Cue.ARMS_UNEVEN for f in frames)
    errors = [error.category for error in evaluations[0].errors]
    assert evaluations[0].metrics.target_reached and errors == [ERR_ARMS_UNEVEN]
    assert evaluations[0].metrics.max_asymmetry_deg == pytest.approx(18, abs=.5)
    assert tip_line_id(ERR_ARMS_UNEVEN) == "E5.21"
    frames, evaluations = run(both_processor(), movement(95, 85))  # 10 degrees apart: fine
    assert not any(f.cue.code == Cue.ARMS_UNEVEN for f in frames) and evaluations[0].is_correct


def test_one_arm_hidden_means_no_angle():
    processor = both_processor()
    run(processor, movement(0, 0)[:40])  # calibrated at rest
    pts, world = body(90, 90, width=WIDTH, height=HEIGHT, center=WIDTH / HEIGHT / 2)
    pts[13] = type(pts[13])(pts[13].x, pts[13].y, .1)  # the left elbow can't be seen
    frame = processor.process(pts, world, WIDTH, HEIGHT, 5.)
    assert frame.metrics["abduction"] is None and frame.metrics["abduction_left"] is None


def test_willy_mirrors_both_arms_and_demonstrates_with_both():
    guide = WillyGuide()
    processor = both_processor()
    frames, _ = run(processor, movement(90, 40)[:90])
    analysis = frames[-1]  # rising: right arm higher than the left
    for step in range(30):
        pose = guide.update(analysis, "running", processor, mirror=True, now=step * .05)
    # In a mirror, the patient's right arm is on the right of the screen.
    assert pose.arm_r == pytest.approx(analysis.metrics["abduction_right"], abs=2)
    assert pose.arm_l == pytest.approx(analysis.metrics["abduction_left"], abs=2)
    guide.demo_side, guide.demo_angle = "both", 90.
    guide.perform("demo", now=10.)
    pose = None
    for step in range(30):
        pose = guide.update(analysis, "ready", processor, now=10. + step * .05)
    assert pose.arm_l == pytest.approx(90, abs=1) and pose.arm_r == pytest.approx(90, abs=1)


def test_the_silhouette_for_both_arms_is_centred_and_both_hands_fit():
    for width, height in ((1280, 720), (640, 480)):
        ideal = layout(width, height, "both")
        assert ideal["cx"] == width / 2
        assert ideal["cx"] - ARM_REACH_SIDE * ideal["sw"] >= width * EDGE - 1e-6
        assert ideal["cx"] + ARM_REACH_SIDE * ideal["sw"] <= width * (1 - EDGE) + 1e-6
    assert layout(640, 480, "both")["sw"] < layout(640, 480, "R")["sw"]  # 4:3: a little further back
    pts, _ = body(0, 0, width=WIDTH, height=HEIGHT, center=WIDTH / HEIGHT / 2)
    assert patient_alignment(pts, WIDTH, HEIGHT, mirror=False, side="both") is not None


def test_lines_speak_of_both_arms_for_the_both_arm_exercise():
    script = WillyScript()
    assert script.text("E4.01", "fr") == "Quand vous voulez, levez doucement le bras sur le côté."
    script.variant = "both"
    assert script.text("E4.01", "fr") == "Quand vous voulez, levez doucement les deux bras sur les côtés."
    assert script.text("E4.01", "en") == "Whenever you like, gently raise both arms to the sides."
    assert script.text("E4.05", "fr") == WillyScript().text("E4.05", "fr")  # lines without an arm don't change
    assert script.text("E4.12", "en") == "Raise both arms to the same height."


def test_the_physio_picks_the_exercise_and_each_keeps_its_plan():
    config_ = ExerciseConfig.from_yaml()
    plans = {key: Plan.from_config(exercise.apply(config_), key) for key, exercise in load_exercises().items()}
    form = SettingsForm(plans["abduction"], plans=plans, both=("both_arms",),
                        names={"abduction": {"fr": "Un bras", "en": "One arm"},
                               "both_arms": {"fr": "Deux bras", "en": "Both arms"}})
    form.step("target_min_deg", -1)  # 75 for the one-arm exercise
    form.step("exercise", 1)
    assert form.plan.exercise == "both_arms" and form.value_text("exercise", "", "en") == "Both arms"
    assert form.value_text("arm", "", "fr") == BOTH_ARMS_LABEL
    form.step("arm", 1)  # nothing to choose with both arms
    assert form.plan.arm is None
    form.step("reps_per_set", 1)
    assert form.changed
    edited = form.all_plans()
    assert edited["abduction"].target_min_deg == 75 and edited["both_arms"].reps_per_set == 11
    form.step("exercise", 1)  # back to one arm: its edit is still there
    assert form.plan.exercise == "abduction" and form.plan.target_min_deg == 75
    image, boxes = render_settings(form, (1280, 840), "fr")
    assert image.shape == (840, 1280, 3) and ("set:+:exercise" in {action for action, _ in boxes})
    assert max(bounds[3] for action, bounds in boxes if action.startswith("set:")) < 718  # above the messages


def test_both_arm_sessions_are_saved_with_each_arms_peak(tmp_path, monkeypatch):
    from src import session_store
    monkeypatch.setenv("MOUVEMENT_DATA_DIR", str(tmp_path))
    _, evaluations = run(both_processor(), movement(100, 82) + movement(90, 88))
    log = session_store.SessionLog.start("both_arms", "both", Plan(exercise="both_arms"))
    for i, evaluation in enumerate(evaluations):
        log.add_rep(evaluation, i * 5.)
    record = log.record()
    assert record["exercise"] == "both_arms" and record["arm"] == "both"
    assert record["reps"][0]["gap_deg"] == pytest.approx(18, abs=.5) and record["reps"][0]["peak_left_deg"] == pytest.approx(82, abs=.5)
    assert record["totals"]["mean_gap_deg"] == pytest.approx(10, abs=.6)
    assert np.isfinite(record["totals"]["best_peak_deg"])


def test_the_app_runs_a_both_arm_session_from_the_physios_choice(monkeypatch, tmp_path):
    from dataclasses import asdict
    from src.willy_lines import shared_script
    from tests import app_fakes
    from tests.app_fakes import ScriptedWindow, make_app
    from tests.test_sets import patient

    def detect(self, frame, timestamp_ms):
        angle = 0. if self.calls < self.rest else self.cycle[(self.calls - self.rest) % len(self.cycle)]
        self.calls += 1
        landmarks, self.last_world_landmarks = body(angle, angle)  # both arms together
        return landmarks

    monkeypatch.setattr(app_fakes.FakeDetector, "detect", detect)
    plan = asdict(Plan(exercise="both_arms", reps_per_set=2, sets=1))
    window = ScriptedWindow(patient)
    app = make_app(monkeypatch, tmp_path, window, language="en", tour_done=True, plan=plan, exercise="both_arms")
    assert app.exercise.id == "both_arms" and app.processor.arm == "both" and shared_script().variant == "both"
    assert app.run() == 0
    assert app.processor.rules_engine.session.total_repetitions == 2
    assert all(e.arm == "both" for e in app.processor.rules_engine.session.evaluations)
    assert [r["exercise"] for r in app.exercise_sessions()] == ["both_arms"]
    # The physio goes back to one arm: its own plan, its own history, Willy speaks of one arm again.
    app.set_exercise("abduction")
    assert app.processor.arm in ("left", "right") and shared_script().variant is None
    assert app.plan.exercise == "abduction" and app.exercise_sessions() == []


def test_the_express_tour_has_no_arm_question_for_both_arms(tmp_path):
    from tests.test_tour_comfort import to_offer
    from tests.test_willy_tour import Harness
    h = Harness(tmp_path)
    h.processor.arm = "both"
    to_offer(h)
    h.press("express_tour")
    seen = []
    for _ in range(4000):
        if h.line and (not seen or seen[-1] != h.line):
            seen.append(h.line)
        if h.line == "S2.06":
            h.press("understand")
        elif h.line in ("S4.04", "S4.11", "S4.10"):
            assert h.director.overlay.progress == (2, 3)
            h.press("next")
        elif h.line == "S7.01":
            assert h.director.overlay.progress == (3, 3)
            break
        h.frame()
    assert seen[-1] == "S7.01" and "S3.04" not in seen and "S3.05" not in seen


def test_the_full_tour_demo_shows_both_arms(tmp_path):
    from src.willy_lines import shared_script
    from tests.test_willy_tour import Harness
    shared_script().variant = "both"
    h = Harness(tmp_path, language="fr", tour_done=True)
    h.processor.arm = "both"
    guide = WillyGuide()
    h.director.guide = guide
    h.director.screen = "dashboard"
    h.director._start(h.director._exercise_demo())
    h.frame()
    assert h.line == "S6.01" and h.text == "Voici votre exercice : lever les deux bras sur les côtés."
    h.until("S6.03")
    h.run(1.5)
    assert guide.demo_side == "both" and guide.demo_angle > 20


def test_the_guidance_speaks_of_both_arms_in_french_and_english():
    from src.dashboard import BOTH_ARMS_TEXT, patient_guidance
    from src.i18n import tr
    from src.session_processor import FrameAnalysis
    processor = both_processor()
    assert patient_guidance(FrameAnalysis(0.), "ready", processor)[1] == \
        "Gardez les deux épaules et les deux coudes visibles, puis commencez."
    assert patient_guidance(FrameAnalysis(0., status="CALIBRATION"), "running", processor)[0] == "Gardez les bras baissés"
    for french in BOTH_ARMS_TEXT.values():
        assert tr(french, "en") != french, f"untranslated: {french}"
    assert tr("Deux bras · Son activé", "en") == "Both arms · Sound on"
