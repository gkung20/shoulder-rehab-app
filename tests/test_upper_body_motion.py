"""Upper-body animation must leave the lower body fixed and loss unassessed."""
from pathlib import Path
import numpy as np
import pytest
from src.avatar_filter import RestingAvatarPose,SafeAvatarArms,arm_angles
from src.avatar_motion import arm_pose,AvatarMotion
from src.rigged_avatar import GlbSkin
from src.session_processor import FrameAnalysis
from tests.test_session_processor import body


def test_missing_hand_lowers_whole_arm_without_removing_any_joints():
    fallback=RestingAvatarPose()
    raised=arm_pose(90,'left')
    fallback.update(raised,1/30)
    missing=dict(raised)
    missing['left']=(*raised['left'][:2],None)
    previous=90.
    for _ in range(60):
        rendered=fallback.update(missing,1/30)
        assert all(p is not None for p in rendered['left'])
        angle,_=arm_angles(rendered['left'],'left')
        assert 0<=previous-angle<=90/30+1e-7
        previous=angle
    assert previous==pytest.approx(0,abs=1e-6)
    assert fallback.resting_sides=={'left'}
    assert missing['left'][2] is None


def test_complete_tracking_loss_rests_both_arms_without_spreading_or_stretching():
    fallback=RestingAvatarPose()
    fallback.update(arm_pose(110,'right'),1/30)
    for _ in range(80):
        rendered=fallback.update({},1/30)
    assert fallback.resting_sides=={'left','right'}
    for side,(s,e,w) in rendered.items():
        assert np.allclose(e-s,[0,0,-.45])
        assert np.allclose(w-e,[0,0,-.4])


def test_reacquired_hand_blends_from_rest_instead_of_snapping_up():
    fallback=RestingAvatarPose()
    fallback.update({},1/30)
    raised=arm_pose(100,'left')
    rendered=fallback.update(raised,1/30)
    angle,_=arm_angles(rendered['left'],'left')
    assert 0<angle<=150/30+1e-7
    assert not fallback.resting_sides


def test_no_hands_still_allows_observed_shoulders_to_move_above_fixed_belly():
    fallback=RestingAvatarPose()
    pose=arm_pose(0,'left')
    lifted=pose['left'][0]+[0,0,.08]
    pose['left']=(lifted,None,None)
    for _ in range(40):
        rendered=fallback.update(pose,1/30)
    assert rendered['left'][0][2]==pytest.approx(1.56)
    assert arm_angles(rendered['left'],'left')[0]==pytest.approx(0.)


def test_observed_shoulder_line_reaches_filtered_pose_without_requiring_face():
    filt=SafeAvatarArms()
    pose=arm_pose(45,'left')
    pose['left']=tuple(p+[0,0,.08] for p in pose['left'])
    for _ in range(20):
        filtered=filt.update(pose,1/30)
    assert filtered['left'][0][2]>1.54
    assert np.linalg.norm(filtered['left'][1]-filtered['left'][0])==pytest.approx(.45)


def test_rest_pose_never_becomes_a_fresh_observation_or_measurement():
    motion=AvatarMotion()
    args=('running',1280,720,'right',80,.5,.6)
    landmarks=body()[0]
    for i in range(15):
        motion.update(FrameAnalysis(i/30,landmarks=landmarks),*args)
    analysis=FrameAnalysis(.6,metrics={})
    _,observed=motion.update(analysis,*args)
    assert not observed and not motion.smoothed
    assert motion.display_pose and motion.resting_sides=={'left','right'}
    assert analysis.metrics=={} and not analysis.landmarks


@pytest.mark.parametrize('filename',[
    'Stylized_Male_Character_-_Game_Ready_Base_mesh.glb',
    'Stylized_Female_Character_Game_Ready_Base_mesh.glb',
    'Stylized_Man_Doctor_-_Mixamo_Rigged_Character.glb'])
def test_local_clavicles_chest_and_arms_move_while_belly_legs_remain_exactly_fixed(filename):
    path=Path(__file__).resolve().parents[1]/'alo'/filename
    if not path.exists():
        pytest.skip('Local character asset not bundled')
    skin=GlbSkin(path)
    assert skin.chest is not None and all(i is not None for i in skin.clavicles.values())
    rest,_=skin.matrices(arm_pose(0,'left'))
    posed=arm_pose(100,'left')
    posed['left']=tuple(p+[0,0,.08] for p in posed['left'])
    matrices,hidden=skin.matrices(posed)
    assert not hidden
    assert not np.allclose(matrices[skin.chest],np.eye(4))
    clavicle=skin.clavicles['left']
    assert not np.allclose(matrices[clavicle],rest[clavicle])
    upper,lower,_=skin.arms['left']
    def transformed(m,i):
        return (m[i]@np.append(skin.joints[i],1))[:3]
    assert transformed(matrices,upper)[2]>transformed(rest,upper)[2]+.01
    assert np.linalg.norm(transformed(matrices,lower)-transformed(matrices,upper))==pytest.approx(
        np.linalg.norm(skin.joints[lower]-skin.joints[upper]))
    for primitive in skin.primitives:
        positions,normals=skin.deform(primitive,matrices)
        fixed=(primitive['positions'][:,2]<=1.20) & ~primitive['arm_vertices']
        assert fixed.any()
        assert np.allclose(positions[fixed],primitive['positions'][fixed],atol=1e-7)
        assert np.isfinite(positions).all() and np.max(np.abs(positions))<2.5
