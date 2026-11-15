"""Verify the real character renderer and save previews without opening a webcam.

Run: python -m tools.preview_avatars
All landmarks in this diagnostic are synthetic, not patient observations.
"""
from pathlib import Path
from dataclasses import replace
import time
import cv2
import numpy as np
from src.avatar_stage import AvatarStage
from src.avatar_motion import arm_pose
from src.geometry import Point2D,Point3D
from src.session_processor import SessionProcessor,FrameAnalysis
from src.state_machine import ExercisePhase
from src.dashboard import render_dashboard


def main():
    output=Path('output')
    output.mkdir(exist_ok=True)
    stage=AvatarStage()
    processor=SessionProcessor()
    original_update=stage.motion.update
    reports=[]
    try:
        assert set(stage.characters)=={'doctor','male','female'},'Three local GLBs are required'
        # Test switching after rendering, not only constructing a hidden avatar.
        previous=None
        start=time.perf_counter()
        for gender in ('male','female','male'):
            stage.set_user_gender(gender)
            for angle in (0,45,90,110,0):
                def synthetic_update(*args,a=angle):
                    stage.motion.display_pose=arm_pose(a,'left')
                    stage.motion.resting_sides=set()
                    return arm_pose(a,'right'),arm_pose(a,'left')
                stage.motion.update=synthetic_update
                rgb,tracked=stage.render(FrameAnalysis(0),processor,'running',(1280,720),(1242,705))
                # Both panels must contain a character, not just a successful blank render.
                background=rgb[0,0].astype(int)
                left=(np.abs(rgb[:,:600].astype(int)-background).max(2)>30).sum()
                right=(np.abs(rgb[:,650:].astype(int)-background).max(2)>30).sum()
                assert left>15000 and right>15000,(gender,angle,left,right)
                if previous is not None and angle==45:
                    assert np.count_nonzero(rgb!=previous)>10000
                previous=rgb.copy()
                if angle==90:
                    cv2.imwrite(str(output/f'avatar-{gender}.png'),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
                if angle==0:
                    cv2.imwrite(str(output/f'avatar-{gender}-rest.png'),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
            reports.append(f'{gender}: rendered, animated and visible after switching')
        reports.append(f'15 frame checks: {time.perf_counter()-start:.2f}s (includes resizing and initial upload)')
        # Inspect actual observed-image mapping and the patient dashboard at native pixels.
        stage.motion.update=original_update
        stage.set_user_gender('female')
        landmarks=[Point2D(.5,.5,0.) for _ in range(33)]
        for i,x,y in ((11,.62,.35),(12,.38,.35),(13,.62,.61),(14,.20,.35),(15,.62,.84),(16,.04,.35)):
            landmarks[i]=Point2D(x,y,1.)
        camera=np.full((720,1280,3),65,np.uint8)
        for mode in ('ready','running','paused'):
            for tick in range(12):
                analysis=FrameAnalysis(tick/30,landmarks=landmarks if mode=='running' else [],status='EN COURS',phase=ExercisePhase.HOLD)
                image=render_dashboard(camera,analysis,processor,mode=mode,avatar_stage=stage,
                    avatar_gender='female',output_size=(1920,1080))
            assert image.shape==(1080,1920,3)
            cv2.imwrite(str(output/f'avatar-dashboard-{mode}.png'),image)
        assert processor.rules_engine.session.total_repetitions==0
        reports.append('1920x1080 dashboard: ready / running / paused; no assessment mutation')
        # Shoulder motion remains available without a face or hips. Simulate
        # losing the raised wrist while the other arm remains observed.
        for i in (12,14,16):
            landmarks[i]=replace(landmarks[i],y=.29)
        for tick in range(90):
            analysis=FrameAnalysis(2+tick/30,landmarks=landmarks,status='EN COURS',phase=ExercisePhase.HOLD)
            image=render_dashboard(camera,analysis,processor,mode='running',avatar_stage=stage,
                avatar_gender='female',output_size=(1920,1080))
        cv2.imwrite(str(output/'avatar-shoulders.png'),image)
        landmarks[16]=replace(landmarks[16],visibility=0.)
        for tick in range(60):
            analysis=FrameAnalysis(5+tick/30,landmarks=landmarks,status='EN COURS',phase=ExercisePhase.HOLD)
            image=render_dashboard(camera,analysis,processor,mode='running',avatar_stage=stage,
                avatar_gender='female',output_size=(1920,1080))
        assert stage.resting_sides=={'left'}
        assert stage.motion.smoothed['left'][2] is None
        from src.avatar_filter import arm_angles
        angle,_=arm_angles(stage.motion.display_pose['left'],'left')
        assert abs(angle)<.1
        cv2.imwrite(str(output/'avatar-missing-hand-rest.png'),image)
        reports.append('Shoulder tilt and missing wrist: complete lowered arm, original wrist still unobserved')
        world=[Point3D(0,0,0,0) for _ in range(33)]
        for i,x,y,z in ((11,.2,0,0),(12,-.2,0,0),(13,.2,.2,0),
                       (14,-.2,.05,-.25),(15,.2,.4,0),(16,-.2,.1,-.5)):
            world[i]=Point3D(x,y,z,1.)
        landmarks[12]=Point2D(.38,.35,1.)
        landmarks[14]=Point2D(.34,.4,1.)
        landmarks[16]=Point2D(.30,.43,1.)
        for tick in range(90):
            analysis=FrameAnalysis(8+tick/30,landmarks=landmarks,world_landmarks=world,
                status='EN COURS',phase=ExercisePhase.RISING,metrics={'abduction':30})
            image=render_dashboard(camera,analysis,processor,mode='running',avatar_stage=stage,
                avatar_gender='female',output_size=(1920,1080))
        assert stage.motion.display_pose['left'][2][1]<-.3
        cv2.imwrite(str(output/'avatar-forward-reach.png'),image)
        reports.append('Forward reach: optional depth preserved through mirrored mapping and filtering')
        from src.avatar_filter import direction_3d
        crossing=arm_pose(50,'left')
        shoulder,elbow,_=crossing['left']
        crossing['left']=(shoulder,elbow,elbow+.4*direction_3d(-95,0,'left'))
        def crossing_update(*args):
            stage.motion.display_pose=crossing
            stage.motion.resting_sides=set()
            return arm_pose(50,'left'),crossing
        stage.motion.update=crossing_update
        for gender in ('male','female'):
            stage.set_user_gender(gender)
            rgb,_=stage.render(FrameAnalysis(11),processor,'running',(1280,720),(1242,705))
            cv2.imwrite(str(output/f'avatar-crossing-{gender}.png'),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
        stage.motion.update=original_update
        reports.append('Cross-body reach: both user meshes rendered with hand in front of torso')
        # A whole-tracking loss must clear the live state immediately.
        _,tracked=stage.render(FrameAnalysis(12),processor,'running',(1280,720),(828,470))
        assert not tracked
        reports.append('Tracking loss: neutral preview, not live movement')
        print('\n'.join(reports))
    finally:
        stage.close()


if __name__=='__main__':
    main()
