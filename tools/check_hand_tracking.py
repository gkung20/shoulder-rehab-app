"""Check a real hand model on an optional public sample, then render its gestures.

Run with a local image: python -m tools.check_hand_tracking output/official-hand-sample.jpg
The source image is not shown inside the patient app or sent to another service.
"""
import sys
from pathlib import Path
import cv2
from src.avatar_stage import AvatarStage
from src.hand_detector import HandDetector
from src.geometry import Point2D
from src.avatar_motion import arm_pose
from src.session_processor import SessionProcessor,FrameAnalysis


def main():
    path=Path(sys.argv[1]) if len(sys.argv)>1 else Path('output/official-hand-sample.jpg')
    frame=cv2.imread(str(path))
    if frame is None:
        raise SystemExit('Provide a local hand sample image')
    stage=AvatarStage()
    detector=HandDetector()
    try:
        mp=detector.mp
        h,w=frame.shape[:2]
        resized=cv2.resize(frame,(640,round(h*640/w)))
        image=mp.Image(image_format=mp.ImageFormat.SRGB,data=cv2.cvtColor(resized,cv2.COLOR_BGR2RGB))
        raw=detector.model.detect_for_video(image,1)
        assert raw.hand_landmarks,'No hands detected in sample'
        body=[Point2D(.5,.5,0.) for _ in range(33)]
        for index,points in zip((15,16),raw.hand_landmarks):
            body[index]=Point2D(points[0].x,points[0].y,1.)
        hands=detector.detect(frame,2,body)
        assert hands,'Real hand landmarks could not be associated with wrist locations'
        print('Real model detected',len(hands),'hands with 21 keypoints each')
        for side,observation in hands.items():
            print(side,'confidence',round(observation.confidence,3),'finger bends',
                  {k:round(v) for k,v in observation.curls.items()})
        def sample_update(*args):
            pose=arm_pose(65,'left')
            stage.motion.display_pose=pose
            stage.motion.resting_sides=set()
            stage.motion.hand_observations={'right' if side=='left' else 'left':obs for side,obs in hands.items()}
            stage.motion.frame_dt=1/30
            return arm_pose(65,'left'),pose
        stage.motion.update=sample_update
        processor=SessionProcessor()
        for gender in ('male','female'):
            stage.set_user_gender(gender)
            for tick in range(80):
                rgb,_=stage.render(FrameAnalysis(tick/30),processor,'running',(640,480),(1242,705))
            cv2.imwrite(f'output/avatar-detailed-hands-{gender}.png',cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
        assert processor.rules_engine.session.total_repetitions==0
        print('Detailed hand gestures rendered on both user avatars; counting unchanged')
    finally:
        detector.close()
        stage.close()


if __name__=='__main__':
    main()
