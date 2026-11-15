"""Read local GLB skins and animate in their actual mesh bind space.

The supplied FBX-to-GLB exports contain redundant scene rotations/scales. Using
inverse bind matrices directly avoids applying those wrappers twice. All skin
deformation is display-only; detector landmarks remain the scoring input.
"""
import io
import json
from pathlib import Path
import struct
import math
import numpy as np
from PIL import Image
from src.avatar_filter import arm_angles,forward_angles,direction_3d,limit_elbow_direction
from src.avatar_life import rotation_xyz
from src.avatar_filter import LimitedAngle


def rotation_between(source,target):
    source=np.asarray(source,dtype=float)
    target=np.asarray(target,dtype=float)
    a=source/max(np.linalg.norm(source),1e-9)
    b=target/max(np.linalg.norm(target),1e-9)
    if np.linalg.norm(a)<.5 or np.linalg.norm(b)<.5:
        return np.eye(3)
    cross=np.cross(a,b)
    cosine=float(np.clip(a@b,-1,1))
    if cosine < -.999999:
        axis=np.cross(a,np.eye(3)[np.argmin(np.abs(a))])
        axis/=np.linalg.norm(axis)
        return 2*np.outer(axis,axis)-np.eye(3)
    skew=np.array([[0,-cross[2],cross[1]],[cross[2],0,-cross[0]],[-cross[1],cross[0],0]])
    return np.eye(3)+skew+skew@skew/max(1+cosine,1e-9)


def around(pivot,rotation):
    matrix=np.eye(4)
    matrix[:3,:3]=rotation
    matrix[:3,3]=pivot-rotation@pivot
    return matrix


def axis_rotation(axis,degrees):
    axis=np.asarray(axis,dtype=float)
    norm=np.linalg.norm(axis)
    if norm<1e-8:
        return np.eye(3)
    axis/=norm
    x,y,z=axis
    skew=np.array([[0,-z,y],[z,0,-x],[-y,x,0]])
    angle=math.radians(degrees)
    return np.eye(3)+math.sin(angle)*skew+(1-math.cos(angle))*(skew@skew)


def front_clearance(direction,pivot,length,margin=-.22,force=False,strength=1.):
    """Keep an elevated elbow/hand crossing the torso on its visible front side.

    The front-view camera is on negative Y. Reconstruct the direction on the
    unit sphere so a clearance correction never stretches the bone.
    """
    target=pivot+length*direction
    influence=float(np.clip((.35-abs(target[0]))/.10,0,1))
    influence*=float(np.clip((target[2]-.90)/.10,0,1))*float(np.clip((1.75-target[2])/.10,0,1))
    influence*=float(np.clip((target[2]-pivot[2]+.24)/.08,0,1))
    influence=strength if force else influence
    if influence>0 and target[1]>margin:
        goal=float(np.clip((margin-pivot[1])/max(length,1e-6),-.95,.95))
        dy=direction[1]+influence*(goal-direction[1])
        xz=np.array([direction[0],direction[2]])
        if np.linalg.norm(xz)<1e-8:
            xz=np.array([0.,-1.])
        xz=xz/np.linalg.norm(xz)*math.sqrt(max(0.,1.-dy*dy))
        return np.array([xz[0],dy,xz[1]])
    return direction


class GlbSkin:
    """Validated embedded, uncompressed triangle meshes with a humanoid skin."""
    def __init__(self,path):
        self.path=Path(path)
        raw=self.path.read_bytes()
        if len(raw)<20 or struct.unpack_from('<4sII',raw) != (b'glTF',2,len(raw)):
            raise ValueError(f"GLB invalide : {self.path.name}")
        chunks={}
        offset=12
        while offset+8<=len(raw):
            length,kind=struct.unpack_from('<II',raw,offset)
            if offset+8+length>len(raw):
                raise ValueError("Truncated GLB chunk")
            chunks[kind]=raw[offset+8:offset+8+length]
            offset+=8+length
        self.document=json.loads(chunks[0x4e4f534a])
        self.binary=chunks[0x004e4942]
        d=self.document
        if len(d.get('skins',[]))!=1:
            raise ValueError("Un squelette unique est requis par personnage")
        skin=d['skins'][0]
        self.node_ids=skin['joints']
        self.names=[d['nodes'][i].get('name','') for i in self.node_ids]
        inverse=self.accessor(skin['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1)
        bind=np.linalg.inv(inverse)
        # glTF's +Y is up and +Z faces the viewer; Panda uses +Z up, -Y front.
        self.axes=np.array([[1,0,0],[0,0,-1],[0,1,0]],dtype=np.float32)
        self.joints=bind[:,:3,3]@self.axes.T
        self.parents={child:parent for parent,node in enumerate(d['nodes']) for child in node.get('children',[])}
        def optional(*prefixes):
            return next((i for i,name in enumerate(self.names) if any(name.startswith(p) for p in prefixes)),None)
        self.chest=optional('spine3_','mixamorig_Spine2_')
        self.neck=optional('neck_','mixamorig_Neck_')
        self.clavicles={'left':optional('shoulder.L_','mixamorig_LeftShoulder_'),
                        'right':optional('shoulder.R_','mixamorig_RightShoulder_')}
        self.arms={}
        for side,suffix in (("left","L"),("right","R")):
            def find(kind):
                needles={'upper':(f'upper_arm.{suffix}_',f'mixamorig_{side.title()}Arm_'),
                         'lower':(f'forearm.{suffix}_',f'mixamorig_{side.title()}ForeArm_'),
                         'hand':(f'hand.{suffix}_',f'mixamorig_{side.title()}Hand_')}[kind]
                match=next((i for i,name in enumerate(self.names) if any(name.startswith(n) for n in needles)),None)
                if match is None:
                    raise ValueError(f"Articulation {side}/{kind} absente : {self.path.name}")
                return match
            self.arms[side]=tuple(find(kind) for kind in ('upper','lower','hand'))
        self.primitives=[]
        self.fingers={}
        for side,suffix in (('left','L'),('right','R')):
            groups={}
            for digit,code in (('thumb','A'),('index','B'),('middle','C'),('ring',None),('pinky',None)):
                chain=[]
                for segment in (1,2,3):
                    prefixes=[f'mixamorig_{side.title()}Hand{digit.title()}{segment}_']
                    if code:
                        prefixes.append(f'Finger_{code}{segment}.{suffix}_')
                    match=next((i for i,n in enumerate(self.names) if any(n.startswith(p) for p in prefixes)),None)
                    if match is not None:
                        chain.append(match)
                if chain:
                    groups[digit]=chain
            self.fingers[side]=groups
        for node in d['nodes']:
            if 'mesh' not in node or 'skin' not in node:
                continue
            for primitive in d['meshes'][node['mesh']]['primitives']:
                if primitive.get('mode',4)!=4:
                    raise ValueError("Only triangle meshes are supported")
                attrs=primitive['attributes']
                positions=self.accessor(attrs['POSITION'])@self.axes.T
                normals=self.accessor(attrs['NORMAL'])@self.axes.T
                weights=self.accessor(attrs['WEIGHTS_0']).astype(np.float32)
                weights/=np.maximum(weights.sum(axis=1,keepdims=True),1e-8)
                joints=self.accessor(attrs['JOINTS_0']).astype(int)
                if joints.max()>=len(self.node_ids) or not np.all(np.isfinite(weights)):
                    raise ValueError("Invalid skin weights")
                indices=self.accessor(primitive['indices']).reshape(-1,3).astype(np.int32)
                if indices.max()>=len(positions):
                    raise ValueError("Invalid triangle index")
                uv=self.accessor(attrs['TEXCOORD_0'])
                material=d.get('materials',[])[primitive.get('material',0)]
                texture=material.get('pbrMetallicRoughness',{}).get('baseColorTexture',{})
                if not texture:
                    texture=material.get('extensions',{}).get('KHR_materials_pbrSpecularGlossiness',{}).get('diffuseTexture',{})
                image=None
                if texture:
                    image_info=d['images'][d['textures'][texture['index']]['source']]
                    view=d['bufferViews'][image_info['bufferView']]
                    start=view.get('byteOffset',0)
                    image=Image.open(io.BytesIO(self.binary[start:start+view['byteLength']])).convert('RGBA')
                self.primitives.append(dict(positions=positions,normals=normals,weights=weights,
                    joints=joints,indices=indices,uv=uv,image=image))
        vertices=np.concatenate([p['positions'] for p in self.primitives])
        lo,hi=vertices.min(0),vertices.max(0)
        self.scale=1.92/max(hi[2]-lo[2],1e-6)
        self.origin=np.array([(lo[0]+hi[0])/2,0,lo[2]])
        self.joints=(self.joints-self.origin)*self.scale
        for p in self.primitives:
            p['positions']=(p['positions']-self.origin)*self.scale
            arm_joints=set()
            for upper,_,_ in self.arms.values():
                arm_joints.update(self.descendants(upper))
            p['arm_vertices']=((np.isin(p['joints'],list(arm_joints))*p['weights']).sum(axis=1)>.25)

    def accessor(self,index):
        item=self.document['accessors'][index]
        view=self.document['bufferViews'][item['bufferView']]
        columns={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[item['type']]
        dtype=np.dtype({5121:'u1',5123:'<u2',5125:'<u4',5126:'<f4'}[item['componentType']])
        data=np.ndarray((item['count'],columns),dtype=dtype,buffer=self.binary,
            offset=view.get('byteOffset',0)+item.get('byteOffset',0),
            strides=(view.get('byteStride',columns*dtype.itemsize),dtype.itemsize)).copy()
        if item.get('normalized') and np.issubdtype(dtype,np.integer):
            data=data.astype(np.float32)/np.iinfo(dtype).max
        return data

    def descendants(self,index):
        ancestor=self.node_ids[index]
        found=[]
        for j,node in enumerate(self.node_ids):
            while True:
                if node==ancestor:
                    found.append(j)
                    break
                if node not in self.parents:
                    break
                node=self.parents[node]
        return found

    def matrices(self,pose,secondary=None):
        transforms=np.repeat(np.eye(4)[None],len(self.joints),axis=0)
        hidden=set()
        chest_matrix=np.eye(4)
        left,right=pose.get('left',(None,)*3)[0],pose.get('right',(None,)*3)[0]
        secondary=secondary or {}
        if self.chest is not None:
            tilt=math.atan2(left[2]-right[2],max(left[0]-right[0],.1)) if left is not None and right is not None else 0.
            tilt=float(np.clip(tilt,-math.radians(12),math.radians(12)))
            tilt+=math.radians(float(np.clip(secondary.get('body_roll',0.),-.35,.35)))
            c,s=math.cos(-tilt),math.sin(-tilt)
            chest_matrix=around(self.joints[self.chest],np.array([[c,0,s],[0,1,0],[-s,0,c]]))
            chest_matrix[2,3]+=float(np.clip(secondary.get('breathing',0.),-.0015,.0015))
            neck_descendants=set(self.descendants(self.neck)) if self.neck is not None else set()
            chest_joints=[i for i in self.descendants(self.chest) if i not in neck_descendants]
            transforms[chest_joints]=chest_matrix
        if self.neck is not None and secondary:
            rotation=rotation_xyz(
                x=float(np.clip(secondary.get('head_pitch',0.),-.6,.6)),
                y=float(np.clip(secondary.get('head_roll',0.),-.7,.7)),
                z=float(np.clip(secondary.get('head_yaw',0.),-3.,3.)))
            transforms[self.descendants(self.neck)]=around(self.joints[self.neck],rotation)
        for side,(upper,lower,hand) in self.arms.items():
            points=pose.get(side,(None,None,None))
            shoulder,elbow,wrist=points
            angle,bend=arm_angles(points,side)
            upper_depth,lower_depth=forward_angles(points)
            sign=1 if side=='left' else -1
            def hinge(degrees):
                a=math.radians(-sign*degrees)
                c,s=math.cos(a),math.sin(a)
                return np.array([[c,0,s],[0,1,0],[-s,0,c]])
            # Use a fixed rest frame, then a planar hinge. Recomputing a free
            # shortest-arc 3D rotation each frame can flip the hand's axial roll.
            display_angle=float(np.clip(angle if angle is not None else 0,-65,155))
            # These assets have narrow arm pivots relative to their hips/coats.
            # A slight resting clearance keeps palms outside the thighs rather
            # than burying the hands inside the body. It fades out while lifting.
            display_angle+=6.*max(0.,1.-abs(display_angle)/20.)
            upper_planar=hinge(display_angle)@rotation_between(
                self.joints[lower]-self.joints[upper],[0,0,-1])
            shoulder_matrix=chest_matrix
            clavicle=self.clavicles[side]
            if clavicle is not None:
                # A small clavicle elevation accompanies arm elevation. Measured
                # shoulder-line motion supplies the remaining lift, while the
                # upper spine tilts above a fixed abdomen and pelvis.
                elevation=float(np.clip(max(0.,(angle or 0.)-25)*.16,0,18))
                measured=float(np.clip(shoulder[2]-1.48,-.12,.12)) if shoulder is not None else 0.
                chest_lift=(chest_matrix@np.append(self.joints[upper],1))[2]-self.joints[upper,2]
                length=max(np.linalg.norm(self.joints[upper]-self.joints[clavicle]),.05)
                extra=float(np.clip(math.degrees(math.atan2(measured-chest_lift,length)),-12,12))
                shoulder_matrix=chest_matrix@around(self.joints[clavicle],hinge(float(np.clip(elevation+extra,-12,24))))
                transforms[self.descendants(clavicle)]=shoulder_matrix
            pivot=(shoulder_matrix@np.append(self.joints[upper],1))[:3]
            upper_length=np.linalg.norm(self.joints[lower]-self.joints[upper])
            upper_direction=direction_3d(display_angle,float(np.clip(upper_depth,0,80)),side)
            reaching=abs(angle or 0.)>15 or abs(bend or 0.)>20 or abs(upper_depth)>10 or abs(lower_depth)>10
            if reaching:
                upper_direction=front_clearance(upper_direction,pivot,upper_length)
            lower_angle=display_angle+float(np.clip(bend if bend is not None else 0,-145,145))
            lower_length=np.linalg.norm(self.joints[hand]-self.joints[lower])
            lower_direction=direction_3d(lower_angle,float(np.clip(lower_depth,-65,80)),side)
            preview_wrist=pivot+upper_length*upper_direction+lower_length*lower_direction
            reach=float(np.clip((.35-abs(preview_wrist[0]))/.1,0,1))
            reach*=float(np.clip((preview_wrist[2]-.90)/.1,0,1))*float(np.clip((1.75-preview_wrist[2])/.1,0,1))
            if reaching and reach>0:
                # Crossing the chest needs some shoulder/upper-arm reach too;
                # moving only the forearm cannot clear the torso on short rigs.
                upper_direction=front_clearance(upper_direction,pivot,upper_length,margin=-.10,force=True,strength=reach)
            r=rotation_between(direction_3d(display_angle,0.,side),upper_direction)@upper_planar
            upper_matrix=np.eye(4)
            upper_matrix[:3,:3]=r
            upper_matrix[:3,3]=pivot-r@self.joints[upper]
            transforms[self.descendants(upper)]=upper_matrix
            if angle is None:
                hidden.update(self.descendants(upper))
            if bend is None:
                hidden.update(self.descendants(lower))
            moved_elbow=r@(self.joints[lower]-self.joints[upper])+pivot
            if reaching:
                lower_direction=front_clearance(lower_direction,moved_elbow,lower_length)
            lower_direction=limit_elbow_direction(upper_direction,lower_direction)
            lower_planar=hinge(lower_angle)@rotation_between(self.joints[hand]-self.joints[lower],[0,0,-1])
            lower_rotation=rotation_between(direction_3d(lower_angle,0.,side),lower_direction)@lower_planar
            lower_matrix=np.eye(4)
            lower_matrix[:3,:3]=lower_rotation
            lower_matrix[:3,3]=moved_elbow-lower_rotation@self.joints[lower]
            transforms[self.descendants(lower)]=lower_matrix
        return transforms,hidden

    def deform(self,primitive,transforms):
        matrices=transforms[primitive['joints']]
        weights=primitive['weights']
        rotation=np.einsum('nwij,nw->nij',matrices[:,:,:3,:3],weights)
        translation=np.einsum('nwi,nw->ni',matrices[:,:,:3,3],weights)
        vertices=np.einsum('nij,nj->ni',rotation,primitive['positions'])+translation
        normals=np.einsum('nij,nj->ni',rotation,primitive['normals'])
        # Keep the belly, pelvis and legs exactly at rest, including stray skin
        # weights in the source assets. Blend through the upper abdomen to avoid
        # a hard seam where the animated chest begins.
        blend=np.clip((primitive['positions'][:,2]-1.20)/.20,0,1)
        blend=blend*blend*(3-2*blend)
        # Hands/fingers can sit below the waist in the source bind pose. They
        # must follow their bones at every height; a Z cutoff pins the fingertips
        # in the original pose and creates long spikes when the arm lowers.
        blend=np.maximum(blend,primitive['arm_vertices'])[:,None]
        vertices=primitive['positions']+blend*(vertices-primitive['positions'])
        normals=primitive['normals']+blend*(normals-primitive['normals'])
        normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-8)
        return vertices.astype(np.float32),normals.astype(np.float32)


class RiggedAvatar:
    """Panda geometry with vectorized bind-space skinning and embedded textures."""
    def __init__(self,parent,path,x):
        from panda3d.core import (GeomVertexData,GeomVertexFormat,Geom,GeomNode,
                                 GeomVertexWriter,Texture,SamplerState)
        self.skin=GlbSkin(path)
        self.root=parent.attachNewNode(self.skin.path.stem)
        self.root.setX(x)
        self.parts=[]
        self.visibility=None
        self.gesture_filters={}
        for p in self.skin.primitives:
            data=GeomVertexData('character',GeomVertexFormat.getV3n3t2(),Geom.UHDynamic)
            data.setNumRows(len(p['positions']))
            writer=GeomVertexWriter(data,'texcoord')
            for u,v in p['uv']:
                writer.addData2(float(u),float(1-v))
            geom=Geom(data)
            node=GeomNode('textured-skin')
            node.addGeom(geom)
            part=self.root.attachNewNode(node)
            part.setTwoSided(True)
            if p['image'] is not None:
                image=p['image']
                texture=Texture('embedded-character-texture')
                texture.setup2dTexture(image.width,image.height,Texture.TUnsignedByte,Texture.FRgba8)
                texture.setRamImageAs(image.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes(),'RGBA')
                texture.setMinfilter(SamplerState.FTLinearMipmapLinear)
                texture.setMagfilter(SamplerState.FTLinear)
                part.setTexture(texture)
            self.parts.append((p,data,geom,node))

    def pose(self,joints,observed=True,secondary=None,hands=None,dt=1/30):
        from panda3d.core import GeomTriangles,Geom
        transforms,hidden=self.skin.matrices(joints,secondary=secondary)
        self._hands(transforms,hands or {},max(0.,min(dt,.1)))
        if not observed:
            hidden=set()
        visibility=frozenset(hidden)
        for p,data,geom,node in self.parts:
            # Panda may copy shared geometry during culling. Always modify the
            # node's current geometry, including when a hidden avatar is selected.
            geom=node.modifyGeom(0)
            data=geom.modifyVertexData()
            positions,normals=self.skin.deform(p,transforms)
            # Panda's arrays are interleaved V3N3T2; update them in one bulk write.
            packed=np.column_stack((positions,normals,p['uv'][:,0],1-p['uv'][:,1])).astype(np.float32)
            data.modifyArray(0).modifyHandle().setData(packed.tobytes())
            if visibility!=self.visibility:
                triangles=p['indices']
                if hidden:
                    missing=np.isin(p['joints'],list(hidden)) & (p['weights']>.05)
                    vertices_visible=~missing.any(axis=1)
                    triangles=triangles[vertices_visible[triangles].all(axis=1)]
                primitive=GeomTriangles(Geom.UHDynamic)
                primitive.setIndexType(Geom.NTUint32)
                primitive.modifyVertices().modifyHandle().setData(triangles.astype(np.uint32).tobytes())
                geom.clearPrimitives()
                geom.addPrimitive(primitive)
            geom.markBoundsStale()
            node.markBoundsStale()
        self.visibility=visibility

    def _hands(self,transforms,observations,dt):
        for side,(_,lower,hand) in self.skin.arms.items():
            groups=self.skin.fingers[side]
            if len(groups)<2:
                continue
            first=groups.get('index',next(iter(groups.values())))[0]
            last=groups.get('pinky',groups.get('middle',list(groups.values())[-1]))[0]
            normal=np.cross(self.skin.joints[first]-self.skin.joints[hand],
                            self.skin.joints[last]-self.skin.joints[hand])
            if np.linalg.norm(normal)<1e-8:
                normal=np.array([0,-1.,0])
            normal/=np.linalg.norm(normal)
            matrix=transforms[hand].copy()
            pivot=(matrix@np.append(self.skin.joints[hand],1))[:3]
            elbow=(transforms[lower]@np.append(self.skin.joints[lower],1))[:3]
            axis=pivot-elbow
            axis/=max(np.linalg.norm(axis),1e-8)
            observation=observations.get(side)
            desired=0.
            if observation is not None:
                current=matrix[:3,:3]@normal
                target=np.asarray(observation.normal,dtype=float)
                current-=axis*(current@axis)
                target=target-axis*(target@axis)
                if min(np.linalg.norm(current),np.linalg.norm(target))>.15:
                    current/=np.linalg.norm(current)
                    target/=np.linalg.norm(target)
                    desired=math.degrees(math.atan2(axis@np.cross(current,target),current@target))
            state=self.gesture_filters.setdefault(side,{})
            roll=state.setdefault('roll',LimitedAngle(-90,90,100))
            if roll.value is None:
                roll.apply(0.,dt)
            roll_angle=roll.apply(desired,dt)
            rotation=axis_rotation(axis,roll_angle)
            forearm_matrix=around(elbow,axis_rotation(axis,.65*roll_angle))@transforms[lower]
            transforms[self.skin.descendants(lower)]=forearm_matrix
            hand_matrix=around(pivot,rotation)@matrix
            middle=groups.get('middle',groups.get('index'))
            if middle:
                forward=hand_matrix[:3,:3]@(self.skin.joints[middle[0]]-self.skin.joints[hand])
                forward/=max(np.linalg.norm(forward),1e-8)
                palm=hand_matrix[:3,:3]@normal
                palm-=forward*(palm@forward)
                palm/=max(np.linalg.norm(palm),1e-8)
                flex_axis=np.cross(forward,palm)
                desired_flex=desired_deviation=0.
                if observation is not None and observation.direction is not None:
                    target=np.asarray(observation.direction,dtype=float)
                    target=target/max(np.linalg.norm(target),1e-8)
                    bend_axis=np.cross(forward,target)
                    angle=math.degrees(math.acos(float(np.clip(forward@target,-1,1))))
                    if np.linalg.norm(bend_axis)>1e-6:
                        rotation_vector=bend_axis/np.linalg.norm(bend_axis)*min(angle,35.)
                        desired_flex=float(rotation_vector@flex_axis)
                        desired_deviation=float(rotation_vector@palm)
                flex=state.setdefault('wrist_flex',LimitedAngle(-30,30,90))
                deviation=state.setdefault('wrist_deviation',LimitedAngle(-20,20,75))
                if flex.value is None:
                    flex.apply(0.,dt)
                    deviation.apply(0.,dt)
                wrist_rotation=axis_rotation(palm,deviation.apply(desired_deviation,dt))@axis_rotation(flex_axis,flex.apply(desired_flex,dt))
                hand_matrix=around(pivot,wrist_rotation)@hand_matrix
            transforms[self.skin.descendants(hand)]=hand_matrix
            for digit,chain in groups.items():
                desired=observation.curls.get(digit,0.) if observation is not None else 0.
                filt=state.setdefault(digit,LimitedAngle(0,80,140))
                if filt.value is None:
                    filt.apply(0.,dt)
                curl=filt.apply(desired,dt)
                parent_matrix=hand_matrix
                for segment,joint in enumerate(chain):
                    child=chain[min(segment+1,len(chain)-1)]
                    direction=self.skin.joints[child]-self.skin.joints[joint] if child!=joint else self.skin.joints[joint]-self.skin.joints[chain[max(0,segment-1)]]
                    bend_axis=parent_matrix[:3,:3]@np.cross(direction,normal)
                    pivot=(parent_matrix@np.append(self.skin.joints[joint],1))[:3]
                    parent_matrix=around(pivot,axis_rotation(bend_axis,curl*(.65,.9,.7)[segment]))@parent_matrix
                    transforms[self.skin.descendants(joint)]=parent_matrix

    def show(self,visible=True):
        self.root.show() if visible else self.root.hide()
