"""Detailed hands must match body sides, preserve wrist position and stay optional."""
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace as P
import numpy as np
import pytest
from src.hand_detector import extract_hand,match_hands,HandObservation
from src.geometry import Point2D
from src.avatar_motion import AvatarMotion,arm_pose
from src.avatar_filter import SafeAvatarArms,arm_angles
from src.rigged_avatar import RiggedAvatar,GlbSkin
from src.session_processor import FrameAnalysis
from tests.test_session_processor import body


def hand_points(closed=False):
    points=np.zeros((21,3))
    for start,x,y in ((1,-.05,-.01),(5,-.025,-.04),(9,0,-.045),(13,.02,-.04),(17,.04,-.03)):
        points[start]=[x,y,0]
        points[start+1]=points[start]+[0,-.025,0]
        points[start+2]=points[start+1]+([0,-.01,-.02] if closed else [0,-.025,0])
        points[start+3]=points[start+2]+([0,.01,-.018] if closed else [0,-.025,0])
    world=[P(x=float(x),y=float(y),z=float(z)) for x,y,z in points]
    image=[P(x=.5+x,y=.5+y,z=z) for x,y,z in points]
    return image,world


def test_hand_model_features_include_normal_and_open_closed_finger_bends():
    opened=extract_hand(*hand_points(),.9)
    closed=extract_hand(*hand_points(True),.9)
    assert np.linalg.norm(opened.normal)==pytest.approx(1.)
    assert opened.normal[1]<-.9
    assert np.linalg.norm(opened.direction)==pytest.approx(1.)
    assert max(opened.curls.values())<1e-5
    assert min(closed.curls.values())>40
    assert extract_hand(*hand_points(),.2) is None


def test_invalid_hand_geometry_is_rejected():
    image,world=hand_points()
    world[5].z=float('nan')
    assert extract_hand(image,world,.9) is None


def test_hand_body_pairing_uses_wrist_locations_not_mirrored_handedness_labels():
    landmarks=body()[0]
    a=extract_hand(*hand_points(),.9)
    b=extract_hand(*hand_points(True),.9)
    a.wrist=landmarks[15]
    b.wrist=landmarks[16]
    matched=match_hands([b,a],landmarks)
    assert matched['left'] is a and matched['right'] is b
    far=replace(a,wrist=Point2D(0,0,.9))
    assert not match_hands([far],landmarks)


def test_fresh_hand_wrist_is_render_only_and_mapping_is_mirrored():
    landmarks=body()[0]
    original=landmarks[16]
    observation=extract_hand(*hand_points(),.9)
    observation.wrist=replace(original,visibility=.95)
    analysis=FrameAnalysis(0,landmarks=landmarks,hands={'right':observation},metrics={'abduction':20})
    motion=AvatarMotion()
    motion.update(analysis,'running',1280,720,'right',80,.5,.6)
    assert motion.hand_observations['left'] is observation
    assert analysis.landmarks[16] is original and analysis.metrics=={'abduction':20}
    motion.update(FrameAnalysis(.033),'running',1280,720,'right',80,.5,.6)
    assert not motion.hand_observations


def test_cross_body_shoulder_is_not_stopped_by_old_fifteen_degree_limit():
    filt=SafeAvatarArms()
    pose=arm_pose(0,'left')
    from src.avatar_filter import direction_3d
    shoulder=pose['left'][0]
    elbow=shoulder+.45*direction_3d(-45,35,'left')
    pose['left']=(shoulder,elbow,elbow+.4*direction_3d(-45,35,'left'))
    for _ in range(60):
        output=filt.update(pose,1/30)
    assert arm_angles(output['left'],'left')[0]<-35


@pytest.mark.parametrize('filename',[
    'Stylized_Male_Character_-_Game_Ready_Base_mesh.glb',
    'Stylized_Female_Character_Game_Ready_Base_mesh.glb',
    'Stylized_Man_Doctor_-_Mixamo_Rigged_Character.glb'])
def test_palm_and_finger_bones_move_without_translating_the_wrist(filename):
    path=Path(__file__).resolve().parents[1]/'alo'/filename
    if not path.exists():
        pytest.skip('Local character download not bundled')
    avatar=RiggedAvatar.__new__(RiggedAvatar)
    avatar.skin=GlbSkin(path)
    avatar.gesture_filters={}
    observation=extract_hand(*hand_points(True),.95)
    base,_=avatar.skin.matrices(arm_pose(65,'left'))
    _,lower,hand=avatar.skin.arms['left']
    wrist=(base[hand]@np.append(avatar.skin.joints[hand],1))[:3]
    for _ in range(90):
        transformed=base.copy()
        avatar._hands(transformed,{'left':observation},1/30)
    assert np.allclose((transformed[hand]@np.append(avatar.skin.joints[hand],1))[:3],wrist)
    assert np.allclose((transformed[lower]@np.append(avatar.skin.joints[lower],1))[:3],
                       (base[lower]@np.append(avatar.skin.joints[lower],1))[:3])
    finger=avatar.skin.fingers['left']['index'][1]
    assert not np.allclose(transformed[finger],base[finger])
    assert abs(avatar.gesture_filters['left']['wrist_flex'].value)<=30
    assert abs(avatar.gesture_filters['left']['wrist_deviation'].value)<=20
    assert np.isfinite(transformed).all()
    for _ in range(120):
        transformed=base.copy()
        avatar._hands(transformed,{},1/30)
    assert abs(avatar.gesture_filters['left']['roll'].value)<.1
    assert avatar.gesture_filters['left']['index'].value<.1


def test_optional_hand_model_runs_without_any_face_input():
    from src.hand_detector import HandDetector,MODEL_PATH
    if not MODEL_PATH.exists():
        pytest.skip('Optional hand model not downloaded')
    detector=HandDetector()
    try:
        assert detector.detect(np.zeros((240,320,3),np.uint8),1,[Point2D(.5,.5,1)]*33)=={}
    finally:
        detector.close()
