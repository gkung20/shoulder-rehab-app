"""Each patient's own resting angle sets the rest and rise thresholds (within safe limits)."""
from dataclasses import replace

from src.config import ExerciseConfig
from src.session_processor import SessionProcessor
from src.synthetic_pose import body
from src.user_profile import Plan


def config():
    c = ExerciseConfig.from_yaml()
    return replace(c, calibration=replace(c.calibration, duration_sec=.6), filtering=replace(c.filtering, ema_alpha=1))


def run(processor, angles, start=0):
    reps = 0
    for i, angle in enumerate(angles):
        pts, world = body(angle)
        frame = processor.process(pts, world, 640, 480, (start + i) / 30)
        reps += frame.new_evaluation is not None
    return reps, frame


def one_rep(rest, peak=90):
    rise = [rest + (peak - rest) * i / 45 for i in range(46)]
    return [rest] * 20 + rise + [peak] * 30 + rise[::-1] + [rest] * 20


def test_low_resting_angle_keeps_todays_thresholds():
    processor = SessionProcessor(config())
    run(processor, [10.] * 40)
    assert processor.resting_angle == 10. and not processor.rest_warning
    machine = processor.state_machine
    assert (machine.rest_threshold_deg, machine.rising_start_deg) == (25, 32)
    reps, _ = run(processor, one_rep(10), start=40)
    assert reps == 1


def test_resting_at_30_degrees_now_counts():
    processor = SessionProcessor(config())
    run(processor, [30.] * 40)
    assert processor.calibrator.calibrated_data.is_calibrated
    machine = processor.state_machine
    assert (machine.rest_threshold_deg, machine.rising_start_deg) == (38, 45)
    assert processor.config.abduction.rest_threshold_deg == 38
    reps, _ = run(processor, one_rep(30), start=40)
    assert reps == 1


def test_resting_close_to_the_target_warns_and_keeps_the_plan():
    plan = Plan(target_min_deg=80, target_max_deg=100, rest_max_deg=25)
    processor = SessionProcessor(config(), plan=plan)
    run(processor, [60.] * 40)
    assert processor.calibrator.calibrated_data.is_calibrated and processor.rest_warning
    assert processor.state_machine.rest_threshold_deg == 25
    reps, frame = run(processor, [60.] * 30, start=40)
    assert reps == 0 and frame.status == "REPOS REQUIS"  # no crash: asks to lower the arm


def test_clearly_raised_arm_is_still_refused_at_calibration():
    processor = SessionProcessor(config())
    run(processor, [80.] * 40)
    assert not processor.calibrator.calibrated_data.is_calibrated
