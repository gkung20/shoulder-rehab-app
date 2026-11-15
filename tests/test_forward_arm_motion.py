"""Forward depth must survive mapping, smoothing and skinning without roll flips."""
from dataclasses import replace
from pathlib import Path
import numpy as np
import pytest
from src.avatar_motion import observed_arms,arm_pose
from src.avatar_filter import (direction_3d,forward_angles,SafeAvatarArms,RestingAvatarPose,
                               mirrored_pose,limit_elbow_direction)
from src.geometry import Point3D
from src.rigged_avatar import GlbSkin,front_clearance
from src.session_processor import SessionProcessor
from tests.test_session_processor import body,config


def depth_world():
    points=[Point3D(0,0,0,0) for _ in range(33)]
    for i,x,y,z in ((11,.2,0,0),(12,-.2,0,0),(13,.2,.2,0),
                    (14,-.2,.05,-.25),(15,.2,.4,0),(16,-.2,.1,-.5)):
        points[i]=Point3D(x,y,z,1.)
    return points


def test_forward_depth_uses_shoulder_relative_world_z_without_face_or_hips():
    landmarks=body()[0]
    pose=observed_arms(landmarks,1280,720,world_landmarks=depth_world())
    assert pose['right'][0][1]==0
    assert pose['right'][2][1]<pose['right'][1][1]<0
    mirrored=mirrored_pose(pose)
    assert mirrored['left'][2][1]==pose['right'][2][1]


def test_invisible_or_nonfinite_depth_does_not_replace_missing_image_observations():
    landmarks=body()[0]
    world=depth_world()
    world[16]=replace(world[16],z=float('nan'))
    assert observed_arms(landmarks,1280,720,world_landmarks=world)['right'][2][1]==0
    world=depth_world()
    world[16]=replace(world[16],visibility=0.)
    assert observed_arms(landmarks,1280,720,world_landmarks=world)['right'][2][1]==0
    landmarks[16]=replace(landmarks[16],visibility=0.)
    assert observed_arms(landmarks,1280,720,world_landmarks=depth_world())['right'][2] is None


def test_frame_carries_only_fresh_optional_depth():
    processor=SessionProcessor(config())
    landmarks=body()[0]
    first=processor.process(landmarks,depth_world(),1280,720,0.)
    second=processor.process(landmarks,None,1280,720,.033)
    assert first.world_landmarks and not second.world_landmarks


def test_forward_arm_survives_filtering_and_returns_to_rest_without_depth_snap():
    pose=arm_pose(15,'left')
    shoulder=pose['left'][0]
    elbow=shoulder+.45*direction_3d(15,65,'left')
    pose['left']=(shoulder,elbow,elbow+.4*direction_3d(20,60,'left'))
    filt=SafeAvatarArms()
    rest=RestingAvatarPose()
    for _ in range(90):
        filtered=filt.update(pose,1/30)
        rendered=rest.update(filtered,1/30)
    assert rendered['left'][2][1]<-.6
    previous_depth=forward_angles(rendered['left'])[0]
    rendered=rest.update({},1/30)
    assert 0<previous_depth-forward_angles(rendered['left'])[0]<=100/30+1e-6
    for _ in range(80):
        rendered=rest.update({},1/30)
    assert abs(rendered['left'][2][1])<1e-6


def test_front_clearance_preserves_bone_length_and_places_crossing_hand_in_front():
    pivot=np.array([.4,0.,1.4])
    direction=np.array([-1.,0.,0.])
    safe=front_clearance(direction,pivot,.3)
    assert np.linalg.norm(safe)==pytest.approx(1.)
    endpoint=pivot+.3*safe
    assert endpoint[1]<=-.219


def test_true_3d_elbow_bend_remains_limited():
    upper=direction_3d(0,70,'left')
    lower=-upper
    safe=limit_elbow_direction(upper,lower)
    assert np.linalg.norm(safe)==pytest.approx(1.)
    assert np.degrees(np.arccos(np.clip(upper@safe,-1,1)))==pytest.approx(145)


@pytest.mark.parametrize('filename',[
    'Stylized_Male_Character_-_Game_Ready_Base_mesh.glb',
    'Stylized_Female_Character_Game_Ready_Base_mesh.glb',
    'Stylized_Man_Doctor_-_Mixamo_Rigged_Character.glb'])
def test_real_mesh_hand_crosses_in_front_and_forward_bones_keep_their_lengths(filename):
    path=Path(__file__).resolve().parents[1]/'alo'/filename
    if not path.exists():
        pytest.skip('Local download not bundled')
    skin=GlbSkin(path)
    pose=arm_pose(50,'left')
    shoulder,elbow,_=pose['left']
    pose['left']=(shoulder,elbow,elbow+.4*direction_3d(-95,0,'left'))
    matrices,_=skin.matrices(pose)
    upper,lower,hand=skin.arms['left']
    def transformed(i):
        return (matrices[i]@np.append(skin.joints[i],1))[:3]
    assert transformed(hand)[1]<-.18
    assert np.linalg.norm(transformed(hand)-transformed(lower))==pytest.approx(
        np.linalg.norm(skin.joints[hand]-skin.joints[lower]))
    assert np.linalg.norm(transformed(lower)-transformed(upper))==pytest.approx(
        np.linalg.norm(skin.joints[lower]-skin.joints[upper]))
    for primitive in skin.primitives:
        vertices,_=skin.deform(primitive,matrices)
        assert np.isfinite(vertices).all() and np.max(np.abs(vertices))<2.5
