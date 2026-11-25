"""The camera and pose model run in their own thread; the screen keeps its pace."""
import time

import numpy as np

from src.pose_worker import PoseWorker
from src.synthetic_pose import body


class Camera:
    def __init__(self, fail_after=None):
        self.t, self.reads, self.fail_after, self.reconnects = 0, 0, fail_after, 0

    def read_frame(self):
        time.sleep(.005)
        self.reads += 1
        self.t += 33
        if self.fail_after is not None and self.reads > self.fail_after:
            return False, None, self.t, 0.
        return True, np.zeros((48, 64, 3), np.uint8), self.t, 30.

    def reconnect(self):
        self.reconnects += 1
        return False


class SlowPose:
    """A pose model taking 60 ms per frame (about 15 per second)."""

    def __init__(self):
        self.stamps = []
        self.last_world_landmarks = None

    def detect(self, frame, timestamp_ms):
        time.sleep(.06)
        self.stamps.append(timestamp_ms)
        landmarks, self.last_world_landmarks = body(0)
        return landmarks


def test_the_screen_keeps_its_pace_with_a_slow_pose_model():
    pose = SlowPose()
    worker = PoseWorker(Camera(), pose, threaded=True)
    worker.want_pose = True
    polls, seqs, stamps, slowest = 0, [], [], 0.
    with worker:
        end = time.perf_counter() + 1.
        while time.perf_counter() < end:
            started = time.perf_counter()
            result = worker.poll()
            slowest = max(slowest, time.perf_counter() - started)
            if result is not None:
                seqs.append(result.seq)
                stamps.append(result.timestamp_ms)
            polls += 1
            time.sleep(.005)
    assert slowest < .02             # asking for the newest result never waits for the model
    assert polls > 100               # the screen loop ran at its own pace (about 200 per second here)
    assert seqs == sorted(seqs) and stamps == sorted(stamps)  # never back in time
    assert len(set(seqs)) < len(seqs)  # older frames were dropped, the newest reused
    assert pose.stamps == sorted(pose.stamps) and len(set(pose.stamps)) == len(pose.stamps)
    assert 8 <= len(pose.stamps) <= 20 and 30 < worker.pose_ms < 200
    assert worker._thread is None    # stopped cleanly


def test_no_pose_model_when_not_wanted_and_inline_mode():
    pose = SlowPose()
    worker = PoseWorker(Camera(), pose, threaded=False)
    first = worker.poll()
    assert first.ok and not first.detected and pose.stamps == []
    worker.want_pose = True
    second = worker.poll()
    assert second.detected and second.landmarks is not None and second.seq == first.seq + 1


def test_a_lost_camera_is_retried_every_two_seconds():
    clock = [0.]
    camera = Camera(fail_after=1)
    worker = PoseWorker(camera, None, threaded=False, clock=lambda: clock[0])
    assert worker.poll().ok
    for step in range(50):  # 5 seconds of polls, 0.1 s apart
        assert not worker.poll().ok
        clock[0] += .1
    assert camera.reconnects == 3  # at 0, 2 and 4 seconds
