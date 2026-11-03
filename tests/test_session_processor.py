"""Regression scenarios use observed landmarks and timestamps, without a webcam."""
from dataclasses import replace
import math

import pytest

from src.config import ExerciseConfig
from src.geometry import Point2D, Point3D, calculate_abduction_angle, to_measurement_space, calculate_trajectory_smoothness
from src.rules_engine import RulesEngine
from src.session_processor import SessionProcessor, repetition_log
from src.state_machine import RepetitionStateMachine


def body(angle=0, width=640, height=480, visibility=1., mirrored=False, arm="right"):
    """A front-facing body; arm lengths are expressed in image-height units."""
    pts = [Point2D(.775, .1, visibility) for _ in range(33)]
    for i, x, y in ((11,.95,.25),(12,.6,.25),(23,.95,.7),(24,.6,.7),
                     (7,.95,.1),(8,.6,.1),(13,.95,.45),(15,.95,.61)):
        pts[i] = Point2D(x,y,visibility)
    rad = math.radians(angle)
    pts[14] = Point2D(.6 - .2 * math.sin(rad), .25 + .2 * math.cos(rad), visibility)
    pts[16] = Point2D(.6 - .36 * math.sin(rad), .25 + .36 * math.cos(rad), visibility)
    world = [Point3D(p.x-.775, p.y-.5, 0, p.visibility) for p in pts]
    normalized = [Point2D(p.x * height / width, p.y, p.visibility) for p in pts]
    if mirrored:
        normalized = [Point2D(1-p.x,p.y,p.visibility) for p in normalized]
        world = [Point3D(-p.x,p.y,p.z,p.visibility) for p in world]
    if arm == "left":
        for left, right in ((11,12),(13,14),(15,16),(23,24),(7,8)):
            normalized[left], normalized[right] = normalized[right], normalized[left]
            world[left], world[right] = world[right], world[left]
    return normalized, world


def config():
    c = ExerciseConfig.from_yaml()
    return replace(c, calibration=replace(c.calibration, duration_sec=.6),
                   filtering=replace(c.filtering, ema_alpha=1))


def run_sequence(processor=None, width=640, height=480, mirrored=False, missing_world=False, arm="right", time_offset=0):
    processor = processor or SessionProcessor(config(),arm)
    # Fully recorded rest, gradual ascent, hold and descent at 30 FPS.
    angles = [0]*30 + [i*1.5 for i in range(61)] + [90]*30 + [90-i*1.5 for i in range(1,61)] + [0]*10
    evaluations = []
    for i, angle in enumerate(angles):
        pts, world = body(angle,width,height,mirrored=mirrored,arm=arm)
        frame = processor.process(pts, None if missing_world else world, width, height, time_offset+i/30)
        if frame.new_evaluation:
            evaluations.append(frame.new_evaluation)
    return processor, evaluations


@pytest.mark.parametrize("width,height", [(640,480),(1280,720),(480,640)])
def test_camera_aspect_ratio_does_not_change_angles_or_count(width,height):
    pts, _ = body(45,width,height)
    scaled = to_measurement_space(pts,width,height)
    assert calculate_abduction_angle(scaled[12],scaled[24],scaled[14]) == pytest.approx(45)
    # Portrait framing is deliberately shifted so the full body remains in bounds.
    if width < height:
        return
    _, evals = run_sequence(width=width,height=height)
    assert len(evals) == 1
    assert evals[0].status_label == "CORRECT"


def test_mirroring_does_not_change_quality_or_anatomical_arm():
    _, normal = run_sequence()
    _, mirror = run_sequence(mirrored=True)
    assert normal[0].status_label == mirror[0].status_label == "CORRECT"
    assert normal[0].arm == mirror[0].arm == "right"
    assert normal[0].metrics.peak_abduction_deg == pytest.approx(mirror[0].metrics.peak_abduction_deg)


def test_left_and_right_use_the_same_rules():
    _, right = run_sequence()
    _, left = run_sequence(arm="left")
    assert right[0].status_label == left[0].status_label == "CORRECT"
    assert left[0].arm == "left"
    assert right[0].metrics.peak_abduction_deg == pytest.approx(left[0].metrics.peak_abduction_deg)


def test_arm_switch_keeps_global_numbering_and_separate_calibration_context():
    proc,right = run_sequence()
    offset = proc._last_frame_time + 1/30
    proc.recalibrate("left", offset)
    _,left = run_sequence(proc,arm="left",time_offset=offset)
    assert [e.rep_index for e in proc.rules_engine.session.evaluations] == [1,2]
    assert left[0].arm == "left"
    assert right[0].metrics.calibration_snapshot["calibration_id"] != left[0].metrics.calibration_snapshot["calibration_id"]


def test_missing_depth_never_becomes_a_clean_zero_drift():
    _, evals = run_sequence(missing_world=True)
    assert evals[0].status_label == "INDETERMINE"
    assert not evals[0].is_correct
    assert "derive 3D" in evals[0].metrics.missing_metrics
    assert repetition_log(evals[0])["derive_max_deg"] is None


def test_lost_tracking_clears_display_and_cannot_complete_a_phantom_rep():
    proc = SessionProcessor(config())
    for i in range(30):
        proc.process(*body(),640,480,i/30)
    for i in range(30,50):
        proc.process(*body(85),640,480,i/30)
    frame = proc.process(None,None,640,480,2.)
    assert frame.metrics["abduction"] is None
    frame = proc.process(None,None,640,480,3.)
    assert proc.interrupted_attempts == 1
    assert frame.status == "SUIVI PERDU"
    frame = proc.process(*body(0),640,480,3.1)
    assert frame.new_evaluation is None
    assert proc.rules_engine.session.total_repetitions == 0


def test_short_gap_does_not_earn_hold_time_or_clean_result():
    proc = SessionProcessor(config())
    for i in range(30):
        proc.process(*body(),640,480,i/30)
    proc.process(*body(40),640,480,1.)
    proc.process(*body(85),640,480,1.1)
    proc.process(None,None,640,480,1.2)
    proc.process(*body(85),640,480,1.4)
    assert proc.state_machine.hold_duration_sec == 0
    proc.process(*body(50),640,480,1.5)
    frame = proc.process(*body(),640,480,1.6)
    assert frame.new_evaluation.status_label == "INDETERMINE"


def test_video_clock_calibration_requires_visible_rest_and_invalidates_old_baseline():
    proc = SessionProcessor(config())
    for i in range(30):
        frame = proc.process(*body(85),640,480,i/30)
    assert not proc.calibrator.calibrated_data.is_calibrated
    assert "Baissez" in frame.cue.message
    for i in range(30,60):
        proc.process(*body(0),640,480,i/30)
    assert proc.calibrator.calibrated_data.is_calibrated
    proc.recalibrate(timestamp_sec=2.)
    for i in range(61,90):
        proc.process(*body(0,visibility=.1),640,480,i/30)
    assert not proc.calibrator.calibrated_data.is_calibrated


def test_low_fps_calibration_extends_collection_instead_of_retrying_forever():
    from src.calibration import CalibrationManager
    calibrator = CalibrationManager(duration_sec=.6)
    calibrator.start(timestamp_sec=0.)
    pts,_ = body()
    pts = to_measurement_space(pts,640,480)
    for i in range(16):
        calibrator.update(pts,"right",timestamp_sec=i*.2)
    assert calibrator.calibrated_data.is_calibrated


def test_state_machine_zero_start_and_interrupted_holds_keep_phase_totals():
    sm = RepetitionStateMachine()
    for t,a in [(0,40),(1,85),(2,85),(3,50),(4,85),(5,85),(6,50),(7,15)]:
        rep = sm.update(a,t)
    assert rep.concentric_duration_sec == 1
    assert rep.hold_duration_sec == 2
    assert rep.eccentric_duration_sec == 4
    assert rep.total_duration_sec == 7


def test_overshoot_is_not_credited_as_target_hold():
    sm = RepetitionStateMachine()
    for t,a in [(0,40),(1,120),(2,120),(3,50),(4,15)]:
        rep = sm.update(a,t)
    assert rep.hold_duration_sec == 0


def test_recorded_context_and_incomplete_data_denominator():
    proc, evaluations = run_sequence(missing_world=True)
    log = repetition_log(evaluations[0])
    assert log["configuration"]["schema_version"] == 1
    assert log["calibration"]["is_calibrated"]
    assert log["session_id"]
    assert proc.rules_engine.session.assessed_repetitions == 0


def test_experimental_fluidity_does_not_grade_by_default():
    _, evals = run_sequence()
    rep = replace(evals[0].metrics, fluidity_score_pct=0.)
    assert RulesEngine(config()).evaluate_repetition(rep).is_correct


def test_smoothness_is_invariant_to_playback_speed():
    times = [i/30 for i in range(61)]
    angles = [90*(10*(t/2)**3 - 15*(t/2)**4 + 6*(t/2)**5) for t in times]
    j1, _ = calculate_trajectory_smoothness(times,angles)
    j2, _ = calculate_trajectory_smoothness([t*2 for t in times],angles)
    assert j1 == pytest.approx(j2,abs=.02)


def test_single_frame_recovery_after_long_gap_requires_rest():
    proc = SessionProcessor(config())
    for i in range(30):
        proc.process(*body(),640,480,i/30)
    proc.process(*body(40),640,480,1.)
    frame = proc.process(*body(85),640,480,3.)
    assert frame.status == "REPOS REQUIS"
    assert proc.interrupted_attempts == 1
    assert proc.rules_engine.session.total_repetitions == 0


def test_zero_depth_confidence_and_degenerate_plane_are_unknown():
    proc = SessionProcessor(config())
    for i in range(30):
        proc.process(*body(),640,480,i/30)
    pts, world = body(45)
    world[12] = replace(world[12],visibility=0.)
    frame = proc.process(pts,world,640,480,1.)
    assert frame.metrics["drift"] is None
    pts,world = body(50)
    # Torso and shoulder vectors collinear: the coronal plane is undefined.
    world[23] = replace(world[11],x=world[11].x+.1)
    world[24] = replace(world[12],x=world[12].x+.1)
    frame = proc.process(pts,world,640,480,1.1)
    assert frame.metrics["drift"] is None


@pytest.mark.parametrize("change", [
    {"target_min_deg":120,"target_max_deg":80},
    {"target_max_deg":120,"overshoot_warn_deg":100},
    {"target_min_deg":float("nan")},
])
def test_invalid_thresholds_are_rejected(change):
    c = config()
    with pytest.raises(ValueError):
        replace(c,abduction=replace(c.abduction,**change))
