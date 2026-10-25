"""MediaPipe Tasks PoseLandmarker detector wrapper.

Adheres strictly to the modern Google AI Edge MediaPipe Tasks API.
Operates fully offline using local .task model bundles.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import numpy as np

from src.geometry import Point2D, PoseLandmarkIndex


class PoseDetector:
    """Encapsulates MediaPipe Pose Landmarker for real-time video stream analysis."""

    def __init__(
        self,
        model_path: Optional[Path] = None,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        running_mode: vision.RunningMode = vision.RunningMode.VIDEO,
    ):
        """Initialize the PoseDetector.

        Args:
            model_path: Path to the .task model file. Defaults to models/pose_landmarker_lite.task.
            min_detection_confidence: Minimum score for person detector.
            min_tracking_confidence: Minimum score for landmark tracking across video frames.
            running_mode: MediaPipe vision running mode (VIDEO or IMAGE).
        """
        if model_path is None:
            model_path = Path(__file__).resolve().parent.parent / "models" / "pose_landmarker_lite.task"

        if not model_path.exists():
            raise FileNotFoundError(
                f"MediaPipe model not found at {model_path}. "
                "Run 'python models/download_models.py' first."
            )

        self.model_path = model_path
        self.running_mode = running_mode
        self._last_timestamp_ms = 0

        base_options = python.BaseOptions(model_asset_path=str(self.model_path))
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=self.running_mode,
            num_poses=1,
            min_pose_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
            output_segmentation_masks=False,
        )
        self.landmarker = vision.PoseLandmarker.create_from_options(options)

    def detect(
        self, frame_bgr: np.ndarray, timestamp_ms: Optional[int] = None
    ) -> Optional[List[Point2D]]:
        """Detect pose landmarks in a BGR video frame.

        Args:
            frame_bgr: Input image in OpenCV BGR format.
            timestamp_ms: Monotonically increasing timestamp in milliseconds.
                          Required for VIDEO mode. If None, auto-increments.

        Returns:
            List of 33 Point2D landmarks if a person is detected, or None.
        """
        if frame_bgr is None or frame_bgr.size == 0:
            return None

        # MediaPipe expects RGB format
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

        if self.running_mode == vision.RunningMode.VIDEO:
            if timestamp_ms is None:
                self._last_timestamp_ms += 33  # ~30 FPS default fallback increment
                ts = self._last_timestamp_ms
            else:
                # Ensure strictly monotonic timestamps
                ts = max(timestamp_ms, self._last_timestamp_ms + 1)
                self._last_timestamp_ms = ts

            result = self.landmarker.detect_for_video(mp_image, ts)
        else:
            result = self.landmarker.detect(mp_image)

        if not result.pose_landmarks or len(result.pose_landmarks) == 0:
            return None

        # Extract primary person landmarks (33 points)
        person_landmarks = result.pose_landmarks[0]
        points: List[Point2D] = []
        for lm in person_landmarks:
            visibility = getattr(lm, "visibility", 1.0)
            if visibility is None:
                visibility = 1.0
            points.append(Point2D(x=float(lm.x), y=float(lm.y), visibility=float(visibility)))

        return points

    @staticmethod
    def get_arm_landmarks(
        landmarks: List[Point2D], arm: str = "right"
    ) -> Tuple[Point2D, Point2D, Point2D, Point2D, Point2D]:
        """Extract the keypoints for the chosen arm.

        Args:
            landmarks: 33 Point2D landmarks.
            arm: 'left' or 'right' (anatomical patient arm).

        Returns:
            Tuple of (shoulder, hip, elbow, wrist, ear).
        """
        arm_lower = arm.lower().strip()
        if arm_lower == "left":
            shoulder = landmarks[PoseLandmarkIndex.LEFT_SHOULDER]
            hip = landmarks[PoseLandmarkIndex.LEFT_HIP]
            elbow = landmarks[PoseLandmarkIndex.LEFT_ELBOW]
            wrist = landmarks[PoseLandmarkIndex.LEFT_WRIST]
            ear = landmarks[PoseLandmarkIndex.LEFT_EAR]
        elif arm_lower == "right":
            shoulder = landmarks[PoseLandmarkIndex.RIGHT_SHOULDER]
            hip = landmarks[PoseLandmarkIndex.RIGHT_HIP]
            elbow = landmarks[PoseLandmarkIndex.RIGHT_ELBOW]
            wrist = landmarks[PoseLandmarkIndex.RIGHT_WRIST]
            ear = landmarks[PoseLandmarkIndex.RIGHT_EAR]
        else:
            raise ValueError(f"Unknown arm selection '{arm}'. Must be 'left' or 'right'.")

        return shoulder, hip, elbow, wrist, ear

    def close(self) -> None:
        """Release underlying MediaPipe landmarker resources."""
        if hasattr(self, "landmarker") and self.landmarker:
            self.landmarker.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
