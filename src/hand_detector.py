"""Optional 21-landmark hand tracking alongside the body model, with no face gate.

Hand world coordinates describe local hand geometry, not body-relative reach.
Palm orientation/finger bends are display-only and never grade a repetition.
"""
from dataclasses import dataclass
from pathlib import Path
import math
import cv2
import numpy as np
from src.geometry import Point2D

MODEL_PATH=Path(__file__).resolve().parents[1]/'models'/'hand_landmarker.task'


@dataclass
class HandObservation:
    wrist: Point2D
    normal: np.ndarray  # Palm normal in mirrored avatar coordinates.
    curls: dict
    confidence: float
    direction: object = None  # Wrist-to-middle-knuckle direction, avatar coordinates.


def extract_hand(image_points,world_points,confidence):
    if len(image_points)!=21 or len(world_points)!=21 or confidence<.6:
        return None
    raw=np.array([[p.x,p.y,p.z] for p in world_points],dtype=float)
    if not np.isfinite(raw).all():
        return None
    # Apply the same horizontal reflection as the mirrored avatar, then form
    # the normal from transformed points (normals cannot simply be reflected).
    points=np.column_stack((-raw[:,0],raw[:,2],-raw[:,1]))
    normal=np.cross(points[5]-points[0],points[17]-points[0])
    size=np.linalg.norm(normal)
    if size<1e-6:
        return None
    curls={}
    for name,indices in {'thumb':(1,2,3,4),'index':(5,6,7,8),'middle':(9,10,11,12),
                         'ring':(13,14,15,16),'pinky':(17,18,19,20)}.items():
        bends=[]
        for a,b,c in zip(indices,indices[1:],indices[2:]):
            u,v=points[b]-points[a],points[c]-points[b]
            denom=np.linalg.norm(u)*np.linalg.norm(v)
            if denom<1e-9:
                return None
            bends.append(math.degrees(math.acos(float(np.clip(u@v/denom,-1,1)))))
        curls[name]=float(np.clip(sum(bends)/len(bends),0,85))
    wrist=image_points[0]
    if not all(math.isfinite(v) and 0<=v<=1 for v in (wrist.x,wrist.y)):
        return None
    direction=points[9]-points[0]
    if np.linalg.norm(direction)<1e-6:
        return None
    direction/=np.linalg.norm(direction)
    return HandObservation(Point2D(float(wrist.x),float(wrist.y),float(confidence)),normal/size,curls,float(confidence),direction)


def match_hands(candidates,body):
    """Match on the unmirrored camera image, not the hand classifier's labels."""
    if not body or len(body)<17:
        return {}
    pairs=[]
    for side,index in (('left',15),('right',16)):
        wrist=body[index]
        if wrist.visibility<.2:
            continue
        for i,candidate in enumerate(candidates):
            distance=math.hypot(candidate.wrist.x-wrist.x,candidate.wrist.y-wrist.y)
            if distance<.18:
                pairs.append((distance,side,i))
    matched={}
    used=set()
    for _,side,i in sorted(pairs):
        if side not in matched and i not in used:
            matched[side]=candidates[i]
            used.add(i)
    return matched


class HandDetector:
    def __init__(self,path=MODEL_PATH):
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        self.mp=mp
        self.model=vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(path)),
            running_mode=vision.RunningMode.VIDEO,num_hands=2,
            min_hand_detection_confidence=.5,min_hand_presence_confidence=.6,min_tracking_confidence=.5))

    def detect(self,frame,timestamp_ms,body):
        if not body:
            return {}
        h,w=frame.shape[:2]
        if w>640:
            frame=cv2.resize(frame,(640,max(1,round(h*640/w))))
        image=self.mp.Image(image_format=self.mp.ImageFormat.SRGB,data=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
        result=self.model.detect_for_video(image,int(timestamp_ms))
        candidates=[]
        for image_points,world_points,categories in zip(result.hand_landmarks,result.hand_world_landmarks,result.handedness):
            confidence=max((c.score for c in categories),default=0.)
            observation=extract_hand(image_points,world_points,confidence)
            if observation is not None:
                candidates.append(observation)
        return match_hands(candidates,body)

    def close(self):
        self.model.close()
