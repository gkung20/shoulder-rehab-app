"""Webcam capture manager with FPS tracking and graceful hardware error handling."""

import time
import sys
from typing import Optional, Tuple
import cv2
import numpy as np


class VideoCaptureManager:
    """Wrapper around cv2.VideoCapture offering FPS smoothing and mirror correction."""

    def __init__(
        self,
        camera_index: int = 0,
        width: int = 640,
        height: int = 480,
        target_fps: int = 30,
        mirror: bool = True,
        zoom: Optional[float] = None,
        allow_fallback: bool = False,
    ):
        """Initialize camera capture.

        Args:
            camera_index: Default hardware device index (0 is standard integrated webcam).
            width: Requested frame width in pixels.
            height: Requested frame height in pixels.
            target_fps: Target frame rate.
            mirror: If True, horizontally flips frames (intuitive selfie view).
        """
        self.camera_index = camera_index
        self.requested_width = width
        self.requested_height = height
        self.target_fps = target_fps
        self.mirror = mirror
        self.zoom = zoom
        self.allow_fallback = allow_fallback
        self.zoom_applied = None
        self.actual_zoom = None
        self.actual_width = 0
        self.actual_height = 0
        self.actual_fps = 0.
        self.status_message = ""

        self.cap: Optional[cv2.VideoCapture] = None
        self._prev_time = time.perf_counter()
        self._fps_filtered = float(target_fps)
        self._start_time_sec = time.perf_counter()
        self._last_timestamp_ms = -1

    def open(self) -> bool:
        """Open the selected device without silently substituting a different camera."""
        # Try requested index first, followed by fallback 0, 1
        indices_to_try = [self.camera_index]
        for fallback in ([0, 1] if self.allow_fallback else []):
            if fallback not in indices_to_try:
                indices_to_try.append(fallback)

        for idx in indices_to_try:
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.requested_width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.requested_height)
                cap.set(cv2.CAP_PROP_FPS, self.target_fps)
                self.zoom_applied = cap.set(cv2.CAP_PROP_ZOOM, self.zoom) if self.zoom is not None else None
                self.actual_zoom = float(cap.get(cv2.CAP_PROP_ZOOM)) if self.zoom_applied else None
                self.actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                self.actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                self.actual_fps = float(cap.get(cv2.CAP_PROP_FPS))
                self.status_message = (f"Camera {idx}: {self.actual_width}x{self.actual_height} "
                    f"(demande {self.requested_width}x{self.requested_height})")
                if self.zoom_applied is False:
                    self.status_message += " / Zoom non pris en charge par ce pilote"
                elif self.zoom_applied:
                    self.status_message += f" / Zoom demande {self.zoom:g}, pilote rapporte {self.actual_zoom:g}"
                self.cap = cap
                self.camera_index = idx
                self._start_time_sec = time.perf_counter()
                self._prev_time = time.perf_counter()
                self._last_timestamp_ms = -1
                return True
            cap.release()

        return False

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray], int, float]:
        """Read a single frame from the camera.

        Returns:
            Tuple of:
              - success (bool): True if frame read succeeded.
              - frame (np.ndarray): BGR image frame (or None).
              - timestamp_ms (int): Monotonic millisecond timestamp for MediaPipe Tasks.
              - current_fps (float): Smoothed real-time frames per second.
        """
        if self.cap is None or not self.cap.isOpened():
            return False, None, 0, 0.0

        success, frame = self.cap.read()
        now = time.perf_counter()
        dt = max(1e-5, now - self._prev_time)
        self._prev_time = now

        # Exponential smoothing on FPS
        instant_fps = 1.0 / dt
        self._fps_filtered = 0.9 * self._fps_filtered + 0.1 * instant_fps

        timestamp_ms = max(self._last_timestamp_ms + 1, int((now - self._start_time_sec) * 1000))
        self._last_timestamp_ms = timestamp_ms

        if not success or frame is None or frame.size == 0:
            return False, None, timestamp_ms, self._fps_filtered

        if self.mirror:
            frame = cv2.flip(frame, 1)

        return True, frame, timestamp_ms, self._fps_filtered

    def release(self) -> None:
        """Release camera hardware resource."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def __enter__(self):
        if not self.open():
            raise RuntimeError(
                f"Failed to open webcam at index {self.camera_index}. "
                "Ensure your camera is plugged in and not in use by another app."
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
