"""Timing baseline for the desktop app, without a camera or models.

    python tools/benchmark.py            # 100 runs per measurement
    python tools/benchmark.py --runs 30  # quicker

Prints a Markdown table (median and 95th percentile, in ms) for:
- drawing the exercise screen at 1280x840 (logical size) and 1920x1080;
- drawing Willy's home screen;
- analysing one frame of landmarks (SessionProcessor.process, no MediaPipe).
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import ExerciseConfig  # noqa: E402
from src.dashboard import render_dashboard  # noqa: E402
from src.home_screen import render_home  # noqa: E402
from src.session_processor import SessionProcessor  # noqa: E402
from src.synthetic_pose import body, rep_angles  # noqa: E402
from src.user_profile import Profile  # noqa: E402
from src.willy import WillyGuide  # noqa: E402
from src.willy_tour import WillyDirector  # noqa: E402


def _time(fn, runs):
    fn()  # warm-up: fonts, sprite caches
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    samples.sort()
    return statistics.median(samples), samples[min(len(samples) - 1, int(len(samples) * .95))]


def measurements(runs=100):
    config = ExerciseConfig.from_yaml()
    processor = SessionProcessor(config, "right")
    angles = rep_angles()
    analysis = None
    for i, angle in enumerate(angles[:80]):
        pts, world = body(angle)
        analysis = processor.process(pts, world, 640, 480, i / 30)
    guide = WillyGuide()
    rng = np.random.default_rng(0)
    camera = rng.integers(30, 200, (480, 640, 3), dtype=np.uint8)

    def dashboard(size):
        return lambda: render_dashboard(camera, analysis, processor, fps=30, mode="running", willy=guide,
                                        output_size=size, avatars=False)

    profile = Profile.load(Path("/nonexistent/benchmark-profile.json"))
    director = WillyDirector(profile, SimpleNamespace(), guide=guide)
    replay = SessionProcessor(config, "right")
    frames = [body(angle) for angle in angles]
    counter = iter(range(10 ** 9))

    def analyse():
        i = next(counter)
        pts, world = frames[i % len(frames)]
        replay.process(pts, world, 640, 480, i / 30)

    return [
        ("Exercise screen, 1280x840", _time(dashboard((1280, 840)), runs)),
        ("Exercise screen, 1920x1080", _time(dashboard((1920, 1080)), runs)),
        ("Home screen, 1280x840", _time(lambda: render_home(director, guide, (1280, 840)), runs)),
        ("Analysis of one frame", _time(analyse, runs * 5)),
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=100)
    args = parser.parse_args(argv)
    print("| Measurement | Median (ms) | 95th percentile (ms) |")
    print("| --- | ---: | ---: |")
    for name, (median, p95) in measurements(args.runs):
        print(f"| {name} | {median:.1f} | {p95:.1f} |")


if __name__ == "__main__":
    main()
