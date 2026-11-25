"""Where each frame's time goes (`python app_live_cv.py --debug`, Phase 6.1).

Milliseconds per stage (camera, pose model, analysis, Willy, drawing, showing) and the
screen's frames per second, smoothed, drawn in the corner of the window and written every
30 frames to `<data folder>/timings.csv`.
"""
from __future__ import annotations

import csv
from contextlib import contextmanager
from time import perf_counter

import cv2

STAGES = ("capture", "pose", "analysis", "director", "draw", "display")


class StageTimer:
    def __init__(self, enabled=False, csv_path=None, every=30):
        self.enabled = enabled
        self.ms = {stage: 0. for stage in STAGES}
        self.fps = 0.
        self.pose_fps = 0.
        self.csv_path = csv_path
        self.every = every
        self.frames = 0
        self._last_frame = None

    @contextmanager
    def stage(self, name):
        if not self.enabled:
            yield
            return
        started = perf_counter()
        try:
            yield
        finally:
            self.record(name, (perf_counter() - started) * 1000)

    def record(self, name, ms):
        if self.enabled:
            previous = self.ms.get(name, 0.)
            self.ms[name] = ms if previous == 0 else .9 * previous + .1 * ms

    def begin_frame(self):
        if not self.enabled:
            return
        now = perf_counter()
        if self._last_frame is not None:
            interval = max(1e-6, now - self._last_frame)
            self.fps = 1 / interval if self.fps == 0 else .9 * self.fps + .1 / interval
        self._last_frame = now
        self.frames += 1
        if self.csv_path is not None and self.frames % self.every == 0:
            self.log()

    def lines(self):
        return [f"{self.fps:5.1f} img/s ecran  {self.pose_fps:5.1f} img/s pose"] + [
            f"{stage:<9}{self.ms[stage]:6.1f} ms" for stage in STAGES]

    def overlay(self, image):
        """Draw the timings in the top-left corner of a BGR image (in place)."""
        if not self.enabled:
            return image
        lines = self.lines()
        height = 18 * len(lines) + 10
        cv2.rectangle(image, (6, 6), (250, 6 + height), (255, 255, 255), -1)
        for i, line in enumerate(lines):
            cv2.putText(image, line, (12, 22 + 18 * i), cv2.FONT_HERSHEY_SIMPLEX, .45, (20, 20, 20), 1, cv2.LINE_AA)
        return image

    def log(self):
        try:
            new = not self.csv_path.exists()
            self.csv_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.csv_path, "a", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                if new:
                    writer.writerow(["frame", "screen_fps", "pose_fps", *STAGES])
                writer.writerow([self.frames, round(self.fps, 1), round(self.pose_fps, 1),
                                 *(round(self.ms[s], 2) for s in STAGES)])
        except OSError:
            pass
