"""Jitter, teleports, mirror semantics and bounded display-only arm rotations."""
import math
import numpy as np
import pytest
from src.avatar_filter import OneEuroFilter,LimitedAngle,SafeAvatarArms,mirrored_pose,arm_angles
from src.avatar_motion import arm_pose,AvatarMotion
from src.session_processor import FrameAnalysis
from tests.test_session_processor import body


def test_one_euro_reduces_resting_jitter():
    filt=OneEuroFilter()
    raw=np.array([45+(-1)**i*2 for i in range(200)])
    smoothed=np.array([filt.apply(x,1/30) for x in raw])
    assert smoothed[40:].std()<raw[40:].std()*.25


def test_isolated_detection_flip_is_rejected_before_it_reaches_filter():
    filt=LimitedAngle(-15,155,150)
    for _ in range(20):
        filt.apply(20,1/30)
    assert filt.apply(150,1/30)==pytest.approx(20)
    assert filt.apply(20,1/30)==pytest.approx(20)


@pytest.mark.parametrize('fps',[15,30,60])
def test_persistent_new_pose_is_followed_without_exceeding_angular_speed(fps):
    filt=LimitedAngle(-15,155,150)
    previous=filt.apply(0,1/fps)
    for _ in range(fps*2):
        current=filt.apply(130,1/fps)
        assert abs(current-previous)<=150/fps+1e-8
        previous=current
    assert current>125


def test_limits_prevent_overhead_dislocations_and_elbow_overfolds():
    for filt in (LimitedAngle(-15,155,150),LimitedAngle(-145,145,210)):
        assert filt.low<=filt.apply(999,1/30)<=filt.high
        for _ in range(90):
            assert filt.low<=filt.apply(-999,1/30)<=filt.high


def test_mirror_swaps_limbs_and_reflects_coordinates_without_modifying_source():
    pose=arm_pose(80,'right')
    original=pose['right'][1].copy()
    mirrored=mirrored_pose(pose)
    assert mirrored['left'][1][2]>1.3
    assert mirrored['left'][1][0]>0
    assert mirrored['right'][1][2]<1.1
    assert np.array_equal(pose['right'][1],original)


def test_held_right_landmarks_drive_left_avatar_arm_and_keep_metrics_unchanged():
    from dataclasses import replace
    landmarks=body()[0]
    # Anatomical right shoulder/elbow/wrist: only this arm is lifted in the input.
    landmarks[14]=replace(landmarks[12],x=landmarks[12].x-.14)
    landmarks[16]=replace(landmarks[12],x=landmarks[12].x-.26)
    motion=AvatarMotion()
    for i in range(15):
        analysis=FrameAnalysis(i/30,landmarks=landmarks,metrics={'abduction':90})
        _,pose=motion.update(analysis,'running',1280,720,'right',80,.5,.6)
    assert pose['left'][1][2]==pytest.approx(pose['left'][0][2],abs=.01)
    assert pose['right'][1][2]<pose['right'][0][2]-.2
    assert analysis.metrics=={'abduction':90}


def test_zero_length_and_missing_joints_are_not_reconstructed_as_observations():
    filt=SafeAvatarArms()
    pose=arm_pose(30,'left')
    pose['left']=(pose['left'][0],pose['left'][0],None)
    result=filt.update(pose,1/30)
    assert result['left'][1:] == (None,None)


def test_lost_wrist_clears_filter_and_needs_stable_reacquisition():
    filt=SafeAvatarArms()
    pose=arm_pose(45,'left')
    for _ in range(10):
        result=filt.update(pose,1/30)
    assert result['left'][2] is not None
    missing=dict(pose)
    missing['left']=(*pose['left'][:2],None)
    assert filt.update(missing,1/30)['left'][2] is None
    assert 'elbow' not in filt.arms['left']
    assert filt.update(pose,1/30)['left'][2] is None
    for _ in range(4):
        result=filt.update(pose,1/30)
    assert result['left'][2] is not None


def test_safe_arm_has_fixed_lengths_and_reset_does_not_animate_from_stale_pose():
    filt=SafeAvatarArms()
    for _ in range(12):
        pose=filt.update(arm_pose(80,'left'),1/30)
    s,e,w=pose['left']
    assert np.linalg.norm(e-s)==pytest.approx(.45)
    assert np.linalg.norm(w-e)==pytest.approx(.4)
    assert not filt.update({},1/30)
    assert not filt.arms
    assert filt.update(arm_pose(0,'left'),1/30,reset=True)['left'][1] is None


def test_elbow_cannot_flip_bend_direction_without_returning_through_straight():
    filt=SafeAvatarArms()
    def pose(bend):
        p=arm_pose(60,'left')
        shoulder,elbow,_=p['left']
        a=math.radians(60+bend)
        p['left']=(shoulder,elbow,elbow+.4*np.array([math.sin(a),0,-math.cos(a)]))
        return p
    for _ in range(30):
        output=filt.update(pose(65),1/30)
    assert arm_angles(output['left'],'left')[1]>50
    for _ in range(60):
        output=filt.update(pose(-90),1/30)
        assert arm_angles(output['left'],'left')[1]>=-1e-6
    for _ in range(90):
        filt.update(pose(0),1/30)
    for _ in range(60):
        output=filt.update(pose(-90),1/30)
    assert arm_angles(output['left'],'left')[1]<-80
