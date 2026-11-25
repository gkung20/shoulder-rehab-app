"""Camera and pose model in their own thread, so the screen keeps its pace (Phase 6.2).

The worker reads the camera and, when the app wants it, runs the pose model on each frame.
The screen loop asks for the newest result (`poll`): older ones are simply dropped. The pose
model is only ever used from the worker, so MediaPipe's VIDEO timestamps stay increasing.
When the camera stops, the worker tries to reopen it every 2 seconds.

`threaded=False` does the same work inline, one frame per `poll()` (tests, and a fallback).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class PoseFrame:
    seq: int
    ok: bool
    frame: object
    timestamp_ms: int
    fps: float
    landmarks: list | None = None
    world: list | None = None
    detected: bool = False    # the pose model ran on this frame
    pose_ms: float = 0.       # time the pose model took on this frame


class PoseWorker:
    RETRY_SEC = 2.

    def __init__(self, capture, detector, threaded=True, clock: Callable[[], float] = time.monotonic):
        self.capture, self.detector, self.threaded, self.clock = capture, detector, threaded, clock
        self.want_pose = False
        self.pose_ms = 0.          # smoothed pose model time (ms)
        self.capture_ms = 0.
        self._latest = None
        self._seq = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._next_retry = 0.

    # ------------------------------------------------------------------ lifecycle
    def start(self):
        if self.threaded and self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="pose-worker", daemon=True)
            self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.)
            self._thread = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False

    # ------------------------------------------------------------------ frames
    def poll(self):
        """The newest result, or None before the first frame."""
        if not self.threaded:
            return self._grab()
        with self._lock:
            return self._latest

    def _run(self):
        while not self._stop.is_set():
            result = self._grab()
            with self._lock:
                self._latest = result
            if not result.ok:
                self._stop.wait(.05)  # the camera is gone: don't spin

    def _grab(self):
        started = time.perf_counter()
        ok, frame, timestamp_ms, fps = self.capture.read_frame()
        self.capture_ms = .9 * self.capture_ms + .1 * (time.perf_counter() - started) * 1000
        self._seq += 1
        if not ok or frame is None:
            now = self.clock()
            if now >= self._next_retry:
                self._next_retry = now + self.RETRY_SEC
                if self._seq > 1 and hasattr(self.capture, "reconnect"):
                    self.capture.reconnect()
            return PoseFrame(self._seq, False, None, timestamp_ms, fps)
        self._next_retry = 0.
        result = PoseFrame(self._seq, True, frame, timestamp_ms, fps)
        if self.want_pose and self.detector is not None:
            began = time.perf_counter()
            result.landmarks = self.detector.detect(frame, timestamp_ms)
            result.world = self.detector.last_world_landmarks
            result.detected = True
            result.pose_ms = (time.perf_counter() - began) * 1000
            self.pose_ms = result.pose_ms if self.pose_ms == 0 else .8 * self.pose_ms + .2 * result.pose_ms
        return result
