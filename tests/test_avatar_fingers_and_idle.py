"""Hands follow the rig below the waist; idle motion stays small and cosmetic."""
from pathlib import Path
import numpy as np
import pytest
from src.avatar_life import natural_motion
from src.avatar_motion import arm_pose
from src.rigged_avatar import GlbSkin


FILES=(
    'Stylized_Male_Character_-_Game_Ready_Base_mesh.glb',
    'Stylized_Female_Character_Game_Ready_Base_mesh.glb',
    'Stylized_Man_Doctor_-_Mixamo_Rigged_Character.glb',
)


def local_skin(filename):
    path=Path(__file__).resolve().parents[1]/'alo'/filename
    if not path.exists():
        pytest.skip('Local download is not bundled')
    return GlbSkin(path)


@pytest.mark.parametrize('filename',FILES)
def test_all_finger_vertices_follow_skinning_even_below_fixed_belly(filename):
    skin=local_skin(filename)
    total_hand_vertices=0
    for angle in (0,45,100):
        matrices,_=skin.matrices(arm_pose(angle,'left'))
        for primitive in skin.primitives:
            vertices,_=skin.deform(primitive,matrices)
            for side,(_,_,hand) in skin.arms.items():
                hand_joints=skin.descendants(hand)
                hand_weight=(np.isin(primitive['joints'],hand_joints)*primitive['weights']).sum(axis=1)
                mask=hand_weight>.95
                total_hand_vertices+=mask.sum()
                # Exact linear skinning reference, deliberately independent of
                # the torso-freeze blend which used to pin low fingertips.
                positions=np.column_stack((primitive['positions'],np.ones(len(vertices))))
                transformed=np.einsum('nwab,nb->nwa',matrices[primitive['joints']],positions)[:,:,:3]
                expected=(transformed*primitive['weights'][:,:,None]).sum(axis=1)
                assert np.allclose(vertices[mask],expected[mask],atol=1e-6)
                rigid=hand_weight>1-1e-6
                triangles=primitive['indices'][rigid[primitive['indices']].all(axis=1)]
                if len(triangles):
                    a,b=triangles[:,0],triangles[:,1]
                    before=np.linalg.norm(primitive['positions'][a]-primitive['positions'][b],axis=1)
                    after=np.linalg.norm(vertices[a]-vertices[b],axis=1)
                    assert np.allclose(before,after,atol=1e-6)
    assert total_hand_vertices>0


def test_idle_motion_is_continuous_bounded_and_finite():
    limits={'head_yaw':3.,'head_pitch':.6,'head_roll':.7,'body_roll':.35,'breathing':.0015}
    previous=natural_motion(0)
    for t in np.arange(0,30,1/60):
        current=natural_motion(t)
        for key,limit in limits.items():
            assert abs(current[key])<=limit+1e-9
            assert abs(current[key]-previous[key])<limit*.04
        previous=current
    assert all(np.isfinite(value) for value in natural_motion(float('nan')).values())


@pytest.mark.parametrize('filename',FILES)
def test_head_moves_gently_without_moving_the_feet_or_corrupting_arm_observation(filename):
    skin=local_skin(filename)
    pose=arm_pose(35,'left')
    source=pose['left'][2].copy()
    baseline,_=skin.matrices(pose)
    secondary=natural_motion(3,phase=1.1)
    animated,_=skin.matrices(pose,secondary=secondary)
    assert skin.neck is not None
    assert not np.allclose(animated[skin.neck],baseline[skin.neck])
    rotation=animated[skin.neck,:3,:3]
    angle=np.degrees(np.arccos(np.clip((np.trace(rotation)-1)/2,-1,1)))
    assert angle<3.3
    for primitive in skin.primitives:
        vertices,_=skin.deform(primitive,animated)
        fixed=(primitive['positions'][:,2]<=1.20)&~primitive['arm_vertices']
        assert np.allclose(vertices[fixed],primitive['positions'][fixed],atol=1e-7)
        assert np.isfinite(vertices).all() and np.max(np.abs(vertices))<2.5
    assert np.array_equal(pose['left'][2],source)
