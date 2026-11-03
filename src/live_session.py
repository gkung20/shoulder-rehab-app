"""Own camera/model/audio resources across Streamlit fragment reruns."""
from src.capture import VideoCaptureManager
from src.pose_detector import PoseDetector
from src.audio_feedback import AudioCoach
from src.session_processor import SessionProcessor


class LiveSession:
    def __init__(self, config, arm="right", audio_enabled=False, rules_engine=None):
        from src.config import ExerciseConfig
        config = config or ExerciseConfig.from_yaml()
        c = config.camera
        self.capture = VideoCaptureManager(camera_index=c.index, width=c.width, height=c.height,
                                           target_fps=c.fps, mirror=False, zoom=c.zoom)
        self.detector = None
        self.audio = None
        self.closed = False
        self.paused = False
        self._resume_calibration = False
        try:
            if not self.capture.open():
                raise RuntimeError(f"Camera {c.index} indisponible : verifiez l'index et fermez les autres applications video")
            self.detector = PoseDetector(model_variant=config.pose.model)
            self.audio = AudioCoach.from_config(config.audio, enabled=audio_enabled)
            self.processor = SessionProcessor(config, arm, rules_engine)
            self.processor.model_info = self.detector.model_info.copy()
        except Exception:
            self.close()
            raise

    def read(self):
        ok, image, timestamp, fps = self.capture.read_frame()
        if not ok or image is None:
            raise RuntimeError("Capture interrompue : verifiez la camera puis redemarrez")
        if self.paused:
            from src.session_processor import FrameAnalysis
            return image,FrameAnalysis(timestamp/1000.,metrics={},status="PAUSE"),fps
        landmarks = self.detector.detect(image, timestamp)
        h, w = image.shape[:2]
        if self._resume_calibration:
            self.processor.recalibrate(timestamp_sec=timestamp/1000.)
            self._resume_calibration = False
        analysis = self.processor.process(landmarks, self.detector.last_world_landmarks, w, h, timestamp / 1000.)
        self.audio.speak_cue(analysis.cue)
        if analysis.new_evaluation:
            self.audio.speak_evaluation(analysis.new_evaluation)
        return image, analysis, fps

    def pause(self):
        if not self.paused:
            self.processor.finish()
            self.audio.silence()
            self.paused = True

    def resume(self):
        self.paused = False
        if self.processor.calibrator.is_calibrating:
            self._resume_calibration = True

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if hasattr(self, "processor"):
                self.processor.finish()
            self.capture.release()
        finally:
            try:
                if self.detector:
                    self.detector.close()
            finally:
                if self.audio:
                    self.audio.stop()

    def __del__(self):
        # Best effort for abandoned local browser sessions; explicit Stop closes immediately.
        try:
            self.close()
        except Exception:
            pass
