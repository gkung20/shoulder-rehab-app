"""Unobserved joints must never turn into a fabricated successful movement."""
from dataclasses import replace
import numpy as np
import pytest
from src.avatar_motion import demonstration, observed_arms, AvatarMotion
from src.session_processor import FrameAnalysis
from src.state_machine import ExercisePhase
from tests.test_session_processor import body


def test_demonstration_target_hold_and_return_with_selected_arm():
    for arm in ("right","left"):
        rest=demonstration(0,arm,80,1)
        raised=demonstration(4.2,arm,80,1)
        opposite="left" if arm == "right" else "right"
        assert np.allclose(rest[opposite],raised[opposite])
        shoulder,elbow,_=raised[arm]
        direction=(elbow-shoulder)/np.linalg.norm(elbow-shoulder)
        assert np.degrees(np.arccos(-direction[2])) == pytest.approx(80)
        assert np.allclose(rest[arm],demonstration(7.5,arm,80,1)[arm])


def test_retargeting_needs_no_face_or_hips_and_corrects_aspect_ratio():
    landmarks=body()[0]
    for index in (*range(11),*range(17,33)):
        landmarks[index]=replace(landmarks[index],visibility=0.)
    poses=observed_arms(landmarks,1280,720)
    assert set(poses) == {"right","left"}
    expected=(landmarks[13].y-landmarks[11].y)*720 / (abs(landmarks[11].x-landmarks[12].x)*1280)*.72
    assert poses["left"][0][2]-poses["left"][1][2] == pytest.approx(expected)


def test_missing_elbow_is_not_filled_and_missing_shoulders_hide_all_arms():
    landmarks=body()[0]
    landmarks[13]=replace(landmarks[13],visibility=0.)
    assert observed_arms(landmarks,1280,720)["left"][1] is None
    landmarks[11]=replace(landmarks[11],visibility=0.)
    assert observed_arms(landmarks,1280,720) == {}


@pytest.mark.parametrize("value",[float("nan"),float("inf"),-1.,2.])
def test_invalid_image_joint_is_hidden(value):
    landmarks=body()[0]
    landmarks[15]=replace(landmarks[15],x=value)
    assert observed_arms(landmarks,1280,720)["left"][2] is None


def test_pause_and_loss_clear_observed_pose_without_changing_measurements():
    motion=AvatarMotion()
    analysis=FrameAnalysis(0,landmarks=body()[0],metrics={"abduction":42})
    args=(1280,720,"right",80,1,.6)
    assert motion.update(analysis,"running",*args)[1]
    assert not motion.update(FrameAnalysis(.1),"running",*args)[1]
    assert not motion.smoothed
    assert not motion.update(analysis,"paused",*args)[1]
    assert analysis.metrics == {"abduction":42}


def test_demo_time_does_not_advance_in_pause():
    motion=AvatarMotion()
    args=(1280,720,"right",80,1,.6)
    motion.update(FrameAnalysis(0),"ready",*args)
    motion.update(FrameAnalysis(.1),"ready",*args)
    before=motion.elapsed
    motion.update(FrameAnalysis(4),"paused",*args)
    motion.update(FrameAnalysis(8),"paused",*args)
    assert motion.elapsed == before


def test_coach_rises_with_phase_and_rests_during_calibration():
    motion=AvatarMotion()
    args=(1280,720,"right",80,1,.6)
    for t in range(100):
        coach,_=motion.update(FrameAnalysis(t*.033,status="EN COURS",phase=ExercisePhase.RISING),"running",*args)
    assert coach["left"][1][2] > 1.35
    for t in range(70):
        coach,_=motion.update(FrameAnalysis(4+t/30,status="CALIBRATION"),"running",*args)
    assert coach["right"][1][2] == pytest.approx(1.03)


def test_coach_shows_target_during_hold_even_without_previous_rising_frames():
    motion=AvatarMotion()
    coach,_=motion.update(FrameAnalysis(0,status='EN COURS',phase=ExercisePhase.HOLD),
        'running',1280,720,'right',90,1,.6)
    assert coach['left'][1][2] == pytest.approx(coach['left'][0][2])


def test_coach_matches_angle_pace_without_copying_elbow_compensation():
    motion=AvatarMotion()
    analysis=FrameAnalysis(0,status='EN COURS',phase=ExercisePhase.RISING,metrics={'abduction':45,'elbow':100})
    coach,_=motion.update(analysis,'running',1280,720,'right',90,1,.6)
    s,e,w=coach['left']
    assert np.linalg.norm(np.cross(e-s,w-e))<1e-9
    assert np.degrees(np.arccos(-(e-s)[2]/np.linalg.norm(e-s))) == pytest.approx(45)


def test_avatar_view_toggle_keeps_session_running():
    from src.patient_controls import PatientControls
    controls=PatientControls(mode="running")
    assert controls.avatars
    assert controls.apply("avatars")
    assert not controls.avatars and controls.mode == "running"


def test_dashboard_renders_avatars_at_native_size_and_camera_toggle_skips_stage():
    from unittest.mock import Mock
    from src.dashboard import render_dashboard
    from src.session_processor import SessionProcessor
    stage=Mock()
    def scene(analysis,processor,mode,source_size,output_size):
        w,h=output_size
        return np.full((h,w,3),240,np.uint8),True
    stage.render.side_effect=scene
    camera=np.zeros((720,1280,3),np.uint8)
    analysis=FrameAnalysis(0)
    processor=SessionProcessor()
    result=render_dashboard(camera,analysis,processor,avatar_stage=stage,output_size=(1920,1080))
    assert result.shape == (1080,1920,3)
    assert stage.render.call_args.args[-1][0] > 1000
    stage.reset_mock()
    render_dashboard(camera,analysis,processor,avatar_stage=stage,avatars=False)
    stage.render.assert_not_called()
    assert not np.any(camera)
