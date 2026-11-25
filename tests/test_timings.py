"""--debug timings: per-stage milliseconds on screen and in timings.csv."""
import csv

import numpy as np

from src.timings import STAGES, StageTimer


def test_stages_are_measured_drawn_and_logged(tmp_path):
    timer = StageTimer(True, tmp_path / "timings.csv", every=2)
    for _ in range(4):
        timer.begin_frame()
        with timer.stage("draw"):
            sum(range(20000))
        timer.record("pose", 40.)
    assert timer.ms["draw"] > 0 and timer.ms["pose"] == 40. and timer.fps > 0
    image = np.zeros((300, 400, 3), np.uint8)
    timer.overlay(image)
    assert image[10:100, 10:200].any()
    rows = list(csv.reader(open(tmp_path / "timings.csv", encoding="utf-8")))
    assert rows[0] == ["frame", "screen_fps", "pose_fps", *STAGES] and len(rows) == 3


def test_disabled_timer_costs_nothing(tmp_path):
    timer = StageTimer(False, tmp_path / "t.csv")
    timer.begin_frame()
    with timer.stage("draw"):
        pass
    image = np.zeros((10, 10, 3), np.uint8)
    assert not timer.overlay(image).any() and not (tmp_path / "t.csv").exists()
