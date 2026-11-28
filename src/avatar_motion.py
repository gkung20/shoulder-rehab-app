"""Presentation-only upper-body retargeting and timed demonstration motion."""
import math
import numpy as np
from src.state_machine import ExercisePhase
from src.avatar_filter import SafeAvatarArms,mirrored_pose,LimitedAngle,arm_angles,RestingAvatarPose


def demonstration(elapsed, arm="right", target=90., hold=1.):
    """A slow rest / raise / hold / lower cycle, as an arm pose."""
    return arm_pose(demonstration_angle(elapsed,target,hold),arm)


def demonstration_angle(elapsed, target=90., hold=1.):
    """A slow rest / raise / hold / lower cycle, in degrees (shared by the coach and the silhouette)."""
    hold=max(.5, hold)
    t=max(0., elapsed) % (6.5+hold)
    if t < 1.5:
        angle=0.
    elif t < 4.:
        angle=target*(.5-.5*math.cos(math.pi*(t-1.5)/2.5))
    elif t < 4.+hold:
        angle=target
    else:
        angle=target*(.5+.5*math.cos(math.pi*(t-4.-hold)/2.5))
    return angle


def arm_pose(angle,arm):
    """Both arms raise together when `arm` is "both" (Phase 10.1)."""
    result={}
    for side,sign in (("right",-1),("left",1)):
        a=math.radians(angle if arm in (side,"both") else 0.)
        shoulder=np.array([sign*.36,0.,1.48])
        direction=np.array([sign*math.sin(a),0.,-math.cos(a)])
        elbow=shoulder+.45*direction
        result[side]=(shoulder,elbow,elbow+.40*direction)
    return result


def observed_arms(landmarks, width, height, visibility=.6,world_landmarks=None):
    """Fit visible image joints with optional confidence-gated estimated depth.

    No face or hips required. Unseen elbows/wrists remain absent. Aspect ratio
    is corrected before shoulder-width normalization. Never used for scoring.
    """
    if len(landmarks) < 17:
        return {}
    def point(index):
        p=landmarks[index]
        if not all(math.isfinite(v) for v in (p.x,p.y,p.visibility)) or p.visibility < visibility:
            return None
        if not (0 <= p.x <= 1 and 0 <= p.y <= 1):
            return None
        return np.array([p.x*width, -p.y*height])
    left,right=point(11),point(12)
    if left is None or right is None:
        return {}
    span=np.linalg.norm(left-right)
    if span < 10:
        return {}
    center=(left+right)/2
    def convert(p,index,shoulder_index):
        if p is None:
            return None
        xy=(p-center)*(.72/span)
        depth=0.
        if world_landmarks and len(world_landmarks)>index:
            a,b=world_landmarks[11],world_landmarks[12]
            origin,world=world_landmarks[shoulder_index],world_landmarks[index]
            values=(a.x,a.y,a.z,b.x,b.y,b.z,origin.z,world.z)
            if all(math.isfinite(v) for v in values) and all(
                    math.isfinite(q.visibility) and q.visibility>=visibility for q in (a,b,origin,world)):
                world_span=np.linalg.norm([a.x-b.x,a.y-b.y,a.z-b.z])
                if .15<=world_span<=.8:
                    # MediaPipe's smaller Z is closer to the camera; Panda's
                    # negative Y points forward. Ignore estimated back-reaching
                    # depth in this front-view exercise rather than burying hands.
                    depth=float(np.clip((world.z-origin.z)*.72/world_span,-1.35 if index in (15,16) else -.75,0.))
        return np.array([xy[0],depth,1.48+xy[1]])
    return {side:tuple(convert(point(i),i,indices[0]) for i in indices)
            for side,indices in (("left",(11,13,15)),("right",(12,14,16)))}


class AvatarMotion:
    """Freeze the demo during pauses; clear observation history on lost joints."""
    def __init__(self):
        self.elapsed=0.
        self.previous_time=None
        self.previous_mode=None
        self.smoothed={}
        self.coach_angle=0.
        self.last_coach=None
        self.arm_filter=SafeAvatarArms()
        self.coach_filter=LimitedAngle(0,155,120)
        self.rest_pose=RestingAvatarPose()
        self.display_pose={}
        self.resting_sides=set()
        self.hand_observations={}
        self.frame_dt=0.

    def update(self, analysis, mode, width, height, arm, target, hold, visibility):
        now=analysis.timestamp_sec
        dt=0. if self.previous_time is None else max(0.,now-self.previous_time)
        self.frame_dt=min(dt,.1)
        if mode == "ready" and self.previous_mode != "ready":
            self.elapsed=0.
        if mode in ("ready","running") and self.previous_mode == mode:
            self.elapsed+=min(dt,.25)
        old_mode=self.previous_mode
        self.previous_time=now
        self.previous_mode=mode
        coach=demonstration(self.elapsed,arm,target,hold)
        if mode == "running" and analysis.status not in (
                "CALIBRATION","SUIVI PERDU","POSITION A AJUSTER","EPAULES PRETES","REPOS REQUIS"):
            if analysis.phase in (ExercisePhase.RISING,ExercisePhase.HOLD,ExercisePhase.LOWERING):
                destination=(target if analysis.phase == ExercisePhase.RISING else
                             target if analysis.phase == ExercisePhase.HOLD and analysis.hold_seconds < hold else 0.)
                step=target*min(dt,.25)/2.5
                observed_angle=analysis.metrics.get('abduction')
                if analysis.phase==ExercisePhase.HOLD and analysis.hold_seconds<hold:
                    self.coach_angle=target
                elif analysis.phase in (ExercisePhase.RISING,ExercisePhase.LOWERING) and observed_angle is not None and math.isfinite(observed_angle):
                    # Match pace using the measured arm angle, while keeping the
                    # coach's elbow straight and torso neutral. No pose feeds scoring.
                    self.coach_angle=float(np.clip(observed_angle,0,target))
                else:
                    self.coach_angle+=float(np.clip(destination-self.coach_angle,-step,step))
                coach=arm_pose(self.coach_angle,arm)
            else:
                self.coach_angle=0.
        elif mode == "running":
            coach=arm_pose(0.,arm)
            self.coach_angle=0.
        if mode in ("paused","finished") and self.last_coach is not None:
            coach=self.last_coach
        if old_mode != mode:
            self.smoothed={}
            self.arm_filter.reset()
        if mode not in ('paused','finished'):
            lead="right" if arm == "both" else arm
            desired,_=arm_angles(coach[lead],lead)
            coach=arm_pose(self.coach_filter.apply(desired if desired is not None else 0,min(dt,.1)),arm)
        self.last_coach=coach
        render_landmarks=list(analysis.landmarks)
        self.hand_observations={}
        if mode=='running' and len(render_landmarks)>=17:
            for side,observation in analysis.hands.items():
                if observation.confidence>=.6:
                    render_landmarks[15 if side=='left' else 16]=observation.wrist
                    self.hand_observations['right' if side=='left' else 'left']=observation
        observed=observed_arms(render_landmarks,width,height,visibility,
            world_landmarks=analysis.world_landmarks) if mode == "running" else {}
        fresh=self.arm_filter.update(mirrored_pose(observed),min(dt,.1),reset=dt>.35 or dt<0)
        self.smoothed=fresh
        self.display_pose=self.rest_pose.update(fresh,min(dt,.1))
        self.resting_sides=self.rest_pose.resting_sides.copy()
        return mirrored_pose(coach),fresh
