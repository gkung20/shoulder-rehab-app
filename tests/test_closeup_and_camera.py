"""Tight camera framing must not invent hidden landmarks or block shoulder setup."""
from dataclasses import replace
from unittest.mock import Mock

import pytest

from src.capture import VideoCaptureManager
from src.geometry import Point2D, calculate_shoulder_reference_angle
from src.session_processor import SessionProcessor, repetition_log
from tests.test_session_processor import body, config


def cropped_body(angle=0, shoulders_only=False, out_of_frame=False, arm="right", mirrored=False):
    pts, world = body(angle,arm=arm,mirrored=mirrored)
    # Simulate clipped face and lower body. World output is intentionally still
    # confident, to prove inferred off-screen hips are not treated as observations.
    hidden = list(range(11)) + list(range(23,33))
    if shoulders_only:
        hidden += list(range(13,23))
    for index in hidden:
        pts[index] = (Point2D(pts[index].x,1.3,1.) if out_of_frame
                      else replace(pts[index],visibility=0.))
    return pts, world


@pytest.mark.parametrize("out_of_frame",[False,True])
def test_shoulders_alone_can_calibrate_without_face_hips_or_elbow(out_of_frame):
    proc = SessionProcessor(config())
    for i in range(30):
        analysis = proc.process(*cropped_body(shoulders_only=True,out_of_frame=out_of_frame),640,480,i/30)
    data = proc.calibrator.calibrated_data
    assert data.is_calibrated
    assert data.reference_mode == "shoulders"
    assert data.baseline_ear_shoulder_dist is None
    assert data.baseline_trunk_lean_deg is None
    assert analysis.status == "EPAULES PRETES"
    assert analysis.metrics["abduction"] is None
    assert "coude" in analysis.cue.message
    assert proc.rules_engine.session.total_repetitions == 0


@pytest.mark.parametrize("arm,mirrored",[("left",False),("right",False),("right",True)])
def test_closeup_counts_observed_arm_and_marks_posture_unassessed(arm,mirrored):
    proc = SessionProcessor(config(),arm)
    angles = [0]*30 + [i*1.5 for i in range(61)] + [90]*30 + [90-i*1.5 for i in range(1,61)] + [0]*10
    evaluations=[]
    for i,angle in enumerate(angles):
        analysis=proc.process(*cropped_body(angle,arm=arm,mirrored=mirrored),640,480,i/30)
        if analysis.new_evaluation:
            evaluations.append(analysis.new_evaluation)
    assert len(evaluations) == 1
    result=evaluations[0]
    assert result.arm == arm
    assert result.metrics.peak_abduction_deg == pytest.approx(90)
    assert result.metrics.angle_reference == "shoulders"
    assert result.status_label == "INDETERMINE"
    assert not result.is_correct
    log=repetition_log(result)
    assert log["reference_angle"] == "shoulders"
    assert log["inclinaison_max_deg"] is None
    assert log["haussement_max_pct"] is None
    assert log["derive_max_deg"] is None


def test_visible_face_is_optional_when_only_ears_are_unreliable():
    proc=SessionProcessor(config())
    for i in range(30):
        pts,world=body()
        for index in range(11):
            pts[index]=replace(pts[index],visibility=0.)
        frame=proc.process(pts,world,640,480,i/30)
    assert proc.calibrator.calibrated_data.is_calibrated
    assert frame.status == "MESURES PARTIELLES"
    assert frame.metrics["shrug"] is None


def test_switching_to_closeup_discards_inflight_rep_once_then_uses_new_reference():
    proc=SessionProcessor(config())
    for i in range(30):
        proc.process(*body(),640,480,i/30)
    proc.process(*body(40),640,480,1.)
    frame=proc.process(*cropped_body(85),640,480,1.1)
    assert frame.status == "REPOS REQUIS"
    assert frame.angle_reference == "shoulders"
    assert proc.rules_engine.session.interrupted_attempts == 1
    proc.process(*cropped_body(85),640,480,1.2)
    assert proc.rules_engine.session.interrupted_attempts == 1
    assert proc.rules_engine.session.total_repetitions == 0


def test_shoulder_reference_follows_camera_roll_and_rejects_degenerate_shoulders():
    # Unit-scale vectors: shoulder line rotated 45 degrees, arm perpendicular.
    left,right=Point2D(.2,.2),Point2D(.5,.5)
    shoulder=right
    elbow=Point2D(.3,.7)
    assert calculate_shoulder_reference_angle(left,right,shoulder,elbow) == pytest.approx(0,abs=1e-5)
    assert calculate_shoulder_reference_angle(left,left,shoulder,elbow) is None


def test_external_camera_honors_requested_index_and_reports_actual_resolution(monkeypatch):
    import src.capture as capture_module
    cap=Mock()
    cap.isOpened.return_value=True
    cap.get.side_effect=lambda key: {capture_module.cv2.CAP_PROP_FRAME_WIDTH:1920,
        capture_module.cv2.CAP_PROP_FRAME_HEIGHT:1080,capture_module.cv2.CAP_PROP_FPS:30}.get(key,0)
    cap.set.side_effect=lambda key,value: key != capture_module.cv2.CAP_PROP_ZOOM
    constructor=Mock(return_value=cap)
    monkeypatch.setattr(capture_module.cv2,"VideoCapture",constructor)
    camera=VideoCaptureManager(camera_index=2,width=1920,height=1080,zoom=0.)
    try:
        assert camera.open()
        assert constructor.call_args.args[0] == 2
        assert camera.actual_width == 1920
        assert camera.actual_height == 1080
        assert camera.zoom_applied is False
        assert "non pris en charge" in camera.status_message
    finally:
        camera.release()
    cap.release.assert_called_once()


def test_missing_selected_camera_does_not_silently_use_builtin_device(monkeypatch):
    import src.capture as capture_module
    cap=Mock()
    cap.isOpened.return_value=False
    constructor=Mock(return_value=cap)
    monkeypatch.setattr(capture_module.cv2,"VideoCapture",constructor)
    assert not VideoCaptureManager(camera_index=4).open()
    constructor.assert_called_once()
    assert constructor.call_args.args[0] == 4
    cap.release.assert_called_once()
