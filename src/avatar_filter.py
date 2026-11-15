"""Display-only One Euro filtering and bounded arm kinematics with forward reach.

Algorithm: Casiez, Roussel & Vogel, CHI 2012, https://gery.casiez.net/1euro/ .
This is an independent small NumPy implementation, not a clinical motion model.
No filtered value is passed to the exercise evaluator.
"""
import math
import numpy as np


class OneEuroFilter:
    def __init__(self,min_cutoff=1.3,beta=.015,derivative_cutoff=1.):
        self.min_cutoff=min_cutoff
        self.beta=beta
        self.derivative_cutoff=derivative_cutoff
        self.value=None
        self.raw=None
        self.derivative=0.

    @staticmethod
    def alpha(cutoff,dt):
        return 1./(1.+1./(2.*math.pi*cutoff*dt))

    def apply(self,value,dt):
        if self.value is None:
            self.value=self.raw=float(value)
            return self.value
        if dt<=0:
            return self.value
        derivative=(value-self.raw)/dt
        self.raw=float(value)
        a=self.alpha(self.derivative_cutoff,dt)
        self.derivative+=a*(derivative-self.derivative)
        cutoff=self.min_cutoff+self.beta*abs(self.derivative)
        self.value+=self.alpha(cutoff,dt)*(value-self.value)
        return self.value


def mirrored_pose(pose):
    """Swap model arms AND reflect X, preserving shoulder/limb correspondence."""
    return {('left' if side=='right' else 'right'):
            tuple(None if p is None else np.asarray(p)*[-1,1,1] for p in points)
            for side,points in pose.items()}


def arm_angles(points,side):
    """Return a planar shoulder angle and relative elbow bend, or missing values."""
    shoulder,elbow,wrist=points
    if shoulder is None or elbow is None:
        return None,None
    upper=np.asarray(elbow)-shoulder
    length=np.linalg.norm(upper)
    if not np.isfinite(upper).all() or not .10<=length<=1.15:
        return None,None
    sign=1 if side=='left' else -1
    projection=math.hypot(upper[0],upper[2])
    angle=0. if projection<max(.03,.15*abs(upper[1])) else math.degrees(math.atan2(sign*upper[0],-upper[2]))
    if wrist is None:
        return angle,None
    lower=np.asarray(wrist)-elbow
    lower_length=np.linalg.norm(lower)
    if not np.isfinite(lower).all() or not .08<=lower_length<=1.0 or not .35<=lower_length/length<=1.8:
        return angle,None
    projection=math.hypot(lower[0],lower[2])
    forearm=angle if projection<max(.03,.15*abs(lower[1])) else math.degrees(math.atan2(sign*lower[0],-lower[2]))
    bend=(forearm-angle+180)%360-180
    return angle,bend


def forward_angles(points):
    result=[]
    for a,b in zip(points,points[1:]):
        if a is None or b is None:
            result.append(0.)
        else:
            v=np.asarray(b)-a
            result.append(math.degrees(math.atan2(-v[1],math.hypot(v[0],v[2]))))
    return tuple(result)


def direction_3d(angle,forward,side):
    a,p=map(math.radians,(angle,forward))
    sign=1 if side=='left' else -1
    return np.array([sign*math.sin(a)*math.cos(p),-math.sin(p),-math.cos(a)*math.cos(p)])


def limit_elbow_direction(upper,lower):
    """Limit the true 3D bend, including when arm depth changes."""
    cosine=float(np.clip(upper@lower,-1,1))
    limit=math.radians(145)
    if cosine>=math.cos(limit):
        return lower
    tangent=lower-cosine*upper
    if np.linalg.norm(tangent)<1e-6:
        tangent=np.cross(upper,[1,0,0])
        if np.linalg.norm(tangent)<1e-6:
            tangent=np.cross(upper,[0,0,1])
    tangent/=np.linalg.norm(tangent)
    return math.cos(limit)*upper+math.sin(limit)*tangent


class LimitedAngle:
    """Reject brief teleports before smoothing; bound the actual displayed speed."""
    def __init__(self,low,high,speed):
        self.low,self.high,self.speed=low,high,speed
        self.filter=OneEuroFilter()
        self.value=None
        self.accepted=None
        self.candidate=None
        self.candidate_time=0.

    def apply(self,value,dt):
        value=float(np.clip(value,self.low,self.high))
        if self.value is None:
            self.value=self.accepted=value
            return self.filter.apply(value,dt)
        if dt<=0:
            return self.value
        if abs(value-self.accepted)>max(45.,self.speed*dt*2):
            if self.candidate is None or abs(value-self.candidate)>15:
                self.candidate=value
                self.candidate_time=0.
            self.candidate_time+=dt
            if self.candidate_time<.12:
                value=self.accepted
            else:
                self.accepted=value
                self.candidate=None
        else:
            self.accepted=value
            self.candidate=None
            self.candidate_time=0.
        smooth=self.filter.apply(value,dt)
        self.value+=float(np.clip(smooth-self.value,-self.speed*dt,self.speed*dt))
        return float(np.clip(self.value,self.low,self.high))


class SafeAvatarArms:
    def __init__(self):
        self.arms={}

    def reset(self):
        self.arms.clear()

    def update(self,pose,dt,reset=False):
        if reset:
            self.reset()
        result={}
        for side in ('left','right'):
            if side not in pose:
                self.arms.pop(side,None)
                continue
            points=pose[side]
            upper,bend=arm_angles(points,side)
            state=self.arms.setdefault(side,{})
            if upper is None:
                state.clear()
                result[side]=(points[0],None,None)
                continue
            if 'shoulder' not in state:
                candidate=state.get('acquiring')
                if candidate is None or abs(upper-candidate[0])>20:
                    state['acquiring']=(upper,0.)
                    result[side]=(points[0],None,None)
                    continue
                duration=candidate[1]+max(0.,dt)
                state['acquiring']=(upper,duration)
                if duration<.05:
                    result[side]=(points[0],None,None)
                    continue
                state.pop('acquiring',None)
            shoulder_filter=state.setdefault('shoulder',LimitedAngle(-65,155,150))
            angle=shoulder_filter.apply(upper,dt)
            sign=1 if side=='left' else -1
            lift_filter=state.setdefault('lift',LimitedAngle(-.12,.12,.30))
            lift=lift_filter.apply(float(points[0][2]-1.48),dt)
            shoulder=np.array([sign*.36,0.,1.48+lift])
            upper_forward,lower_forward=forward_angles(points)
            depth_filter=state.setdefault('upper_depth',LimitedAngle(0,80,100))
            if depth_filter.value is None:
                depth_filter.apply(0.,dt)
            forward=depth_filter.apply(upper_forward,dt)
            def direction(degrees):
                return direction_3d(degrees,forward,side)
            elbow=shoulder+.45*direction(angle)
            wrist=None
            if bend is None:
                state.pop('elbow',None)
                state.pop('wrist_acquiring',None)
                state.pop('bend_sign',None)
                state.pop('lower_depth',None)
            else:
                candidate=state.get('wrist_acquiring')
                if 'elbow' not in state and (candidate is None or abs(bend-candidate[0])>20):
                    state['wrist_acquiring']=(bend,0.)
                else:
                    duration=(candidate[1] if candidate else 0.)+max(0.,dt)
                    state['wrist_acquiring']=(bend,duration)
                    if 'elbow' in state or duration>=.05:
                        elbow_filter=state.setdefault('elbow',LimitedAngle(0,145,210))
                        if abs(bend)<8 and (elbow_filter.value is None or elbow_filter.value<.1):
                            state.pop('bend_sign',None)
                        if 'bend_sign' not in state and abs(bend)>12:
                            state['bend_sign']=1 if bend>0 else -1
                        polarity=state.get('bend_sign',1)
                        # A hinge cannot suddenly reverse its bend through the
                        # back of the elbow. Choose the branch when leaving a
                        # straight arm, then retain it until straight again.
                        magnitude=max(0.,bend*polarity)
                        flexion=polarity*elbow_filter.apply(magnitude,dt)
                        fore_filter=state.setdefault('lower_depth',LimitedAngle(-65,80,140))
                        if fore_filter.value is None:
                            fore_filter.apply(0.,dt)
                        fore_forward=fore_filter.apply(lower_forward,dt)
                        lower=direction_3d(angle+flexion,fore_forward,side)
                        lower=limit_elbow_direction(direction(angle),lower)
                        wrist=elbow+.40*lower
            result[side]=(shoulder,elbow,wrist)
        return result


class RestingAvatarPose:
    """Complete render pose, separate from observations: unseen hands lower arms.

    Retained angles are used only to animate the return to rest. They never
    become observations, valid tracking, or scoring input.
    """
    def __init__(self):
        self.pose={}
        self.resting_sides=set()

    def update(self,observed,dt):
        result={}
        self.resting_sides=set()
        dt=max(0.,min(dt,.1))
        for side,sign in (('left',1),('right',-1)):
            points=observed.get(side,(None,None,None))
            if all(p is not None for p in points):
                previous=self.pose.get(side)
                if previous is None:
                    result[side]=points
                    continue
                old_upper,old_bend=arm_angles(previous,side)
                new_upper,new_bend=arm_angles(points,side)
                upper=(old_upper or 0.)+float(np.clip((new_upper or 0.)-(old_upper or 0.),-150*dt,150*dt))
                bend=(old_bend or 0.)+float(np.clip((new_bend or 0.)-(old_bend or 0.),-210*dt,210*dt))
                shoulder=previous[0]+np.clip(points[0]-previous[0],-.3*dt,.3*dt)
                old_depth=forward_angles(previous)
                new_depth=forward_angles(points)
                upper_depth=old_depth[0]+float(np.clip(new_depth[0]-old_depth[0],-100*dt,100*dt))
                lower_depth=old_depth[1]+float(np.clip(new_depth[1]-old_depth[1],-140*dt,140*dt))
                upper_direction=direction_3d(upper,upper_depth,side)
                lower_direction=limit_elbow_direction(upper_direction,direction_3d(upper+bend,lower_depth,side))
                elbow=shoulder+.45*upper_direction
                result[side]=(shoulder,elbow,elbow+.4*lower_direction)
                continue
            self.resting_sides.add(side)
            previous=self.pose.get(side)
            upper,bend=arm_angles(previous,side) if previous else (0.,0.)
            upper=0. if upper is None else upper
            bend=0. if bend is None else bend
            upper-=float(np.clip(upper,-90*dt,90*dt))
            bend-=float(np.clip(bend,-150*dt,150*dt))
            lift=previous[0][2]-1.48 if previous else 0.
            target_lift=float(np.clip(points[0][2]-1.48,-.12,.12)) if points[0] is not None else 0.
            lift+=float(np.clip(target_lift-lift,-.2*dt,.2*dt))
            shoulder=np.array([sign*.36,0.,1.48+lift])
            previous_depth=forward_angles(previous) if previous else (0.,0.)
            upper_depth=previous_depth[0]-float(np.clip(previous_depth[0],-100*dt,100*dt))
            lower_depth=previous_depth[1]-float(np.clip(previous_depth[1],-140*dt,140*dt))
            upper_direction=direction_3d(upper,upper_depth,side)
            lower_direction=limit_elbow_direction(upper_direction,direction_3d(upper+bend,lower_depth,side))
            elbow=shoulder+.45*upper_direction
            result[side]=(shoulder,elbow,elbow+.4*lower_direction)
        self.pose=result
        return result
