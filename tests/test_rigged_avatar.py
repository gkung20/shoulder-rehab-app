"""Bind-space retargeting must preserve limb length without scene-scale spikes."""
import json
from pathlib import Path
import struct
import numpy as np
import pytest
from src.avatar_motion import arm_pose
from src.rigged_avatar import GlbSkin,rotation_between
from src.patient_controls import PatientControls,patient_buttons,dashboard_action_at


@pytest.fixture
def skin_file(tmp_path):
    arrays=[]
    views=[]
    accessors=[]
    offset=0
    def put(array,kind,component=5126):
        nonlocal offset
        array=np.asarray(array,dtype={5126:'<f4',5123:'<u2'}[component])
        raw=array.tobytes()
        views.append({'buffer':0,'byteOffset':offset,'byteLength':len(raw)})
        arrays.append(raw+b'\0'*((-len(raw))%4))
        offset+=len(arrays[-1])
        accessors.append({'bufferView':len(views)-1,'componentType':component,'count':len(array),'type':kind})
        return len(accessors)-1
    # Mesh positions and inverse binds agree, but scene wrappers are exaggerated.
    joint_positions=np.array([[.2,1.4,0],[.6,1.4,0],[1.,1.4,0],[-.2,1.4,0],[-.6,1.4,0],[-1.,1.4,0]])
    matrices=np.repeat(np.eye(4)[None],6,axis=0)
    matrices[:,:3,3]=-joint_positions
    inv=put(matrices.transpose(0,2,1).reshape(6,16),'MAT4')
    vertices=put([[.2,1.4,0],[.6,1.4,0],[.6,1.5,0],[-.2,0,0],[-.6,1.4,0],[-.6,1.5,0]],'VEC3')
    normals=put([[0,0,1]]*6,'VEC3')
    weights=put([[1,0,0,0]]*6,'VEC4')
    joints=put([[0,0,0,0],[1,0,0,0],[1,0,0,0],[3,0,0,0],[4,0,0,0],[4,0,0,0]],'VEC4',5123)
    uv=put([[0,0]]*6,'VEC2')
    indices=put([[0],[1],[2],[3],[4],[5]],'SCALAR',5123)
    nodes=[{'name':'wrapper','scale':[10000]*3,'children':[1,4,7]}]
    for side in ('L','R'):
        start=len(nodes)
        for i,name in enumerate(('upper_arm','forearm','hand')):
            nodes.append({'name':f'{name}.{side}_0','children':[start+i+1] if i<2 else []})
    nodes.append({'mesh':0,'skin':0})
    binary=b''.join(arrays)
    document={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)}],
        'bufferViews':views,'accessors':accessors,'nodes':nodes,
        'skins':[{'joints':list(range(1,7)),'inverseBindMatrices':inv}],
        'materials':[{}],'meshes':[{'primitives':[{'attributes':{'POSITION':vertices,'NORMAL':normals,
            'JOINTS_0':joints,'WEIGHTS_0':weights,'TEXCOORD_0':uv},'indices':indices}]}]}
    encoded=json.dumps(document).encode()
    encoded+=b' '*((-len(encoded))%4)
    raw=struct.pack('<4sII',b'glTF',2,28+len(encoded)+len(binary))
    raw+=struct.pack('<II',len(encoded),0x4e4f534a)+encoded
    raw+=struct.pack('<II',len(binary),0x004e4942)+binary
    path=tmp_path/'skin.glb'
    path.write_bytes(raw)
    return path


def test_scene_wrapper_scale_is_not_applied_twice(skin_file):
    skin=GlbSkin(skin_file)
    assert np.ptp(skin.primitives[0]['positions'][:,2]) == pytest.approx(1.92)
    matrices=np.repeat(np.eye(4)[None],len(skin.joints),axis=0)
    vertices,normals=skin.deform(skin.primitives[0],matrices)
    assert np.allclose(vertices,skin.primitives[0]['positions'])
    assert np.allclose(np.linalg.norm(normals,axis=1),1)


def test_arm_rotation_preserves_lengths_and_opposite_arm(skin_file):
    skin=GlbSkin(skin_file)
    neutral,_=skin.matrices(arm_pose(0,'left'))
    raised,_=skin.matrices(arm_pose(90,'left'))
    assert np.allclose(neutral[3:],raised[3:])
    u,l,h=skin.arms['left']
    def transform(index):
        return (raised[index]@np.append(skin.joints[index],1))[:3]
    assert np.linalg.norm(transform(l)-transform(u)) == pytest.approx(np.linalg.norm(skin.joints[l]-skin.joints[u]))
    assert np.linalg.norm(transform(h)-transform(l)) == pytest.approx(np.linalg.norm(skin.joints[h]-skin.joints[l]))


def test_missing_wrist_masks_forearm_descendants(skin_file):
    skin=GlbSkin(skin_file)
    pose=arm_pose(30,'left')
    pose['left']=(*pose['left'][:2],None)
    _,hidden=skin.matrices(pose)
    upper,lower,hand=skin.arms['left']
    assert lower in hidden and hand in hidden and upper not in hidden


def test_bent_elbow_uses_forearm_direction_without_changing_bone_length(skin_file):
    skin=GlbSkin(skin_file)
    pose=arm_pose(90,'left')
    shoulder,elbow,_=pose['left']
    pose['left']=(shoulder,elbow,elbow+np.array([0,0,.4]))
    matrices,_=skin.matrices(pose)
    upper,lower,hand=skin.arms['left']
    def transformed(index):
        return (matrices[index]@np.append(skin.joints[index],1))[:3]
    direction=transformed(hand)-transformed(lower)
    assert np.allclose(direction/np.linalg.norm(direction),[0,0,1])
    assert np.linalg.norm(direction)==pytest.approx(np.linalg.norm(skin.joints[hand]-skin.joints[lower]))


@pytest.mark.parametrize('target',[[1,0,0],[-1,0,0],[0,0,-1],[0,1,0]])
def test_rotation_is_rigid_even_for_opposite_directions(target):
    matrix=rotation_between([1,0,0],target)
    assert np.allclose(matrix@[1,0,0],target)
    assert np.allclose(matrix.T@matrix,np.eye(3))
    assert np.linalg.det(matrix) == pytest.approx(1)


def test_gender_choice_is_visual_and_does_not_pause_or_change_arm():
    controls=PatientControls(mode='running')
    assert controls.apply('avatar_female')
    assert controls.avatar_gender=='female' and controls.mode=='running'
    for button in patient_buttons(avatar_gender='female'):
        if button.action=='avatar_female':
            assert button.selected
            x,y,_,_=button.bounds
            assert dashboard_action_at(x+1,y+1,avatar_gender='female')=='avatar_female'


@pytest.mark.parametrize('filename',[
    'Stylized_Male_Character_-_Game_Ready_Base_mesh.glb',
    'Stylized_Female_Character_Game_Ready_Base_mesh.glb',
    'Stylized_Man_Doctor_-_Mixamo_Rigged_Character.glb'])
def test_local_downloads_deform_without_exploding(filename):
    path=Path(__file__).resolve().parents[1]/'alo'/filename
    if not path.exists():
        pytest.skip('Local character download not bundled')
    skin=GlbSkin(path)
    for side in ('left','right'):
        for angle in (0,45,90,110):
            pose=arm_pose(angle,side)
            transforms,hidden=skin.matrices(pose)
            assert not hidden
            for primitive in skin.primitives:
                vertices,normals=skin.deform(primitive,transforms)
                assert np.isfinite(vertices).all() and np.isfinite(normals).all()
                assert np.max(np.abs(vertices))<2.5
                assert np.ptp(vertices[:,2])<2.5
