"""Face-the-camera check: a body turned by about 25 degrees is asked to face the camera."""
from dataclasses import replace

from src.config import ExerciseConfig
from src.cues import Cue
from src.session_processor import SessionProcessor
from src.synthetic_pose import body


def calibrated():
    c = ExerciseConfig.from_yaml()
    c = replace(c, calibration=replace(c.calibration, duration_sec=.6), filtering=replace(c.filtering, ema_alpha=1))
    processor = SessionProcessor(c)
    for i in range(30):
        pts, world = body(0)
        processor.process(pts, world, 640, 480, i / 30)
    assert processor.calibrator.calibrated_data.is_calibrated
    return processor


def frame_turned(processor, yaw, angle=45, with_depth=True, t=2.):
    pts, world = body(angle, yaw=yaw)
    return processor.process(pts, world if with_depth else None, 640, 480, t)


def test_turned_body_is_asked_to_face_the_camera():
    processor = calibrated()
    frame = frame_turned(processor, 25)
    assert frame.cue.code == Cue.FACE_CAMERA and frame.metrics["abduction"] is None


def test_small_turns_are_fine():
    processor = calibrated()
    for t, yaw in enumerate((0, 5, 9)):
        frame = frame_turned(processor, yaw, t=2 + t / 30)
        assert frame.cue.code != Cue.FACE_CAMERA and frame.metrics["abduction"] is not None


def test_without_depth_the_width_check_still_catches_a_bigger_turn():
    processor = calibrated()
    assert frame_turned(processor, 9, with_depth=False).cue.code != Cue.FACE_CAMERA
    assert frame_turned(processor, 36, with_depth=False, t=2.1).cue.code == Cue.FACE_CAMERA


def test_turned_movements_are_not_counted():
    processor = calibrated()
    reps = 0
    angles = [i * 2 for i in range(46)] + [90] * 30 + [90 - i * 2 for i in range(46)] + [0] * 20
    for i, angle in enumerate(angles):
        pts, world = body(angle, yaw=30)
        reps += processor.process(pts, world, 640, 480, 2 + i / 30).new_evaluation is not None
    assert reps == 0
