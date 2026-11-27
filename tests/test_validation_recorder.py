"""Phase 7.2: the validation recorder, with a fake camera and pose (no camera is opened)."""
import csv
from dataclasses import replace

import numpy as np

import src.validation_recorder as vr
from src import validation_data as vd
from src.config import ExerciseConfig
from src.synthetic_pose import body, rep_angles
from src.validation_recorder import ENTER, ESC, SPACE, Item, Recorder


def quick_config():
    c = ExerciseConfig.from_yaml()
    return replace(c, calibration=replace(c.calibration, duration_sec=.6), filtering=replace(c.filtering, ema_alpha=1))


class FakeCapture:
    def __init__(self):
        self.t, self.released = 0, False

    def read_frame(self):
        self.t += 33
        return True, np.zeros((480, 640, 3), np.uint8), self.t, 30.

    def reconnect(self):
        return True

    def release(self):
        self.released = True


class FakeDetector:
    """The volunteer rests for the calibration, then holds `target + error` (or does reps)."""
    model_info = {"file": "fake.task"}

    def __init__(self, error=3., lost_while_recording=False, reps=3):
        self.error, self.lost, self.reps = error, lost_while_recording, reps
        self.recorder, self.last_world_landmarks, self.frames_recording = None, None, 0
        self.closed = False

    def angle(self):
        r = self.recorder
        if r is None or r.state not in ("countdown", "recording"):
            self.frames_recording = 0
            return 0.
        if r.item.kind == "reps":
            if r.state == "countdown":
                return 0.
            angles = rep_angles(peak=100) * self.reps
            self.frames_recording += 1
            return angles[min(self.frames_recording, len(angles) - 1)]
        return r.item.target + self.error

    def detect(self, frame, timestamp_ms):
        r = self.recorder
        if self.lost and r is not None and r.state == "recording" and len(r.rows) > 5:
            self.last_world_landmarks = None
            return None
        angle = self.angle()
        arm = r.item.arm if r is not None else "right"
        pts, world = body(right=angle if arm == "right" else 0., left=angle if arm == "left" else 0.)
        self.last_world_landmarks = world
        return pts

    def close(self):
        self.closed = True


class ScriptedWindow:
    """Plays the operator: starts each trial once calibrated and types the reading."""

    def __init__(self, reading="60", observer="3", end_reps_after=None, limit=6000, on_reading=None,
                 stop_after=None):
        self.reading, self.observer, self.end_reps_after = reading, observer, end_reps_after
        self.limit, self.frames, self.queue, self.recorder = limit, 0, [], None
        self.on_reading, self.shown, self.stop_after = on_reading, None, stop_after

    def show(self, image):
        self.shown, self.frames = image, self.frames + 1

    def key(self):
        r = self.recorder
        if self.queue:
            return self.queue.pop(0)
        if self.stop_after is not None and r.saved >= self.stop_after:
            return ESC  # the operator closes the window
        if r.state == "ready" and r.landmarks and r.calibrated():
            return SPACE
        if r.state == "recording" and r.item.kind == "reps" and self.end_reps_after is not None:
            if r.processor.rules_engine.session.total_repetitions - r.reps_start >= self.end_reps_after:
                return SPACE
        if r.state == "reading":
            if self.on_reading is not None:
                key = self.on_reading(r)
                if key is not None:
                    return key
            text = self.reading if r.item.kind == "hold" else self.observer
            self.queue = [ord(c) for c in text[1:]] + [ENTER[1]]
            return ord(text[0])
        if r.state == "finished":
            return ESC
        return -1

    def is_open(self):
        return self.frames < self.limit

    def close(self):
        pass


def recorder(tmp_path, items, detector=None, window=None, **options):
    detector = detector or FakeDetector()
    window = window or ScriptedWindow()
    options = {"hold_sec": 1., "countdown_sec": .3, **options}
    rec = Recorder("V01", tmp_path, FakeCapture(), detector, window, quick_config(), items=items, **options)
    detector.recorder = window.recorder = rec
    return rec


def trials(tmp_path):
    with open(tmp_path / "trials.csv", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_a_held_position_is_recorded_with_every_frame_and_the_goniometer_reading(tmp_path):
    rec = recorder(tmp_path, [Item("right", "hold", 60, 1)])
    rec.run()
    assert rec.state == "done" and rec.saved == 1
    [row] = trials(tmp_path)
    assert row["trial_id"] == "V01_right_hold060_t1" and row["status"] == "ok"
    assert float(row["reference_deg"]) == 60. and abs(float(row["app_deg"]) - 63.) < .5
    assert row["model"] == "" and row["video_file"] == ""
    frames = vd.read_frames(tmp_path / row["frames_file"])
    assert list(frames[0]) == list(vd.FRAME_FIELDS)
    assert 29 <= len(frames) <= 32 and int(row["frames"]) == len(frames)  # 1 s at 30 images/s
    assert frames[10]["angle_valid"] == "1" and float(frames[10]["n14_y"]) > 0 and frames[10]["w14_z"] != ""
    assert not list(tmp_path.rglob("*.mp4"))
    assert rec.window.shown is not None and rec.window.shown.shape == (480, 640, 3)


def test_a_set_of_repetitions_compares_the_app_count_with_the_observer(tmp_path):
    rec = recorder(tmp_path, [Item("left", "reps", None, 1)], detector=FakeDetector(reps=3),
                   window=ScriptedWindow(observer="3", end_reps_after=3))
    rec.run()
    [row] = trials(tmp_path)
    assert row["kind"] == "reps" and row["arm"] == "left"
    assert row["app_reps"] == "3" and row["observer_reps"] == "3" and row["app_deg"] == ""


def test_a_hold_with_the_person_lost_is_not_assessed(tmp_path):
    rec = recorder(tmp_path, [Item("right", "hold", 90, 1)], detector=FakeDetector(lost_while_recording=True))
    rec.run()
    [row] = trials(tmp_path)
    assert row["status"] == "ok" and row["app_deg"] == ""  # the reading is kept, the app had no angle
    assert int(row["valid_frames"]) < int(row["frames"]) / 2


def test_redo_keeps_the_trial_in_the_list_and_a_new_session_resumes(tmp_path):
    items = [Item("right", "hold", 30, 1), Item("right", "hold", 60, 1)]
    answers = iter([ord("r")])  # first reading: redo; then the value is typed
    window = ScriptedWindow(reading="31", on_reading=lambda r: next(answers, None), stop_after=1)
    rec = recorder(tmp_path, items, window=window)
    rec.run()
    rows = trials(tmp_path)
    assert [r["status"] for r in rows] == ["redo", "ok"] and rows[0]["trial_id"] == rows[1]["trial_id"]
    assert [r["status"] for r in vd.load_trials(tmp_path)] == ["ok"]
    # the window was closed after the first trial: a new session starts at the second one
    again = recorder(tmp_path, items)
    assert again.item == Item("right", "hold", 60, 1)
    # a later redo of a trial already measured does not hide its measurement
    vd.append_trial(tmp_path, {**rows[1], "status": "redo"})
    assert [r["status"] for r in vd.load_trials(tmp_path)] == ["ok"]


def test_the_operator_can_choose_arm_position_and_trial(tmp_path):
    rec = recorder(tmp_path, vr.protocol(("right",), trials=3, reps_sets=1))
    assert rec.item == Item("right", "hold", 0, 1)
    for key in (ord("p"), ord("p"), ord("t"), ord("a")):
        rec.handle(key)
    assert rec.item == Item("left", "hold", 60, 2)
    for _ in range(3):  # 90, 120, then the set of repetitions
        rec.handle(ord("p"))
    assert rec.item.kind == "reps" and rec.item.trial == 1  # there is one set of repetitions
    rec.handle(ord("n"))
    assert rec.item == vr.protocol(("right",))[1]


def test_readings_are_checked(tmp_path):
    rec = recorder(tmp_path, [Item("right", "hold", 60, 1)])
    rec.state = "reading"
    for key in map(ord, "2,5"):
        rec.handle(key)
    assert rec.typed == "2.5" and rec.parse(rec.typed) == 2.5
    rec.typed = "500"
    rec.handle(ENTER[0])
    assert rec.state == "reading" and "invalide" in rec.message


class Answers:
    def __init__(self, *answers):
        self.answers = list(answers)

    def __call__(self, question):
        return self.answers.pop(0)


def run_main(monkeypatch, tmp_path, answers, extra=()):
    detector, window = FakeDetector(error=0.), ScriptedWindow(reading="45")
    original = vr.Recorder

    class Spy(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            detector.recorder = window.recorder = self

    monkeypatch.setattr(vr, "Recorder", Spy)
    argv = ["--subject", "V02", "--out", str(tmp_path), "--arms", "right", "--trials", "1", "--reps-sets", "0",
            "--hold", ".8", "--countdown", ".2", *extra]
    code = vr.main(argv, ask=Answers(*answers), open_camera=lambda config, index: FakeCapture(),
                   open_detector=lambda config, variant: detector, window=window)
    return code, detector


def test_video_is_saved_only_with_the_flag_and_the_volunteers_video_consent(monkeypatch, tmp_path):
    code, detector = run_main(monkeypatch, tmp_path / "a", ["o", "n"], ["--save-video"])
    assert code == 0 and detector.closed
    assert len(trials(tmp_path / "a")) == 5 and not list((tmp_path / "a").rglob("*.mp4"))
    code, _ = run_main(monkeypatch, tmp_path / "b", ["o", "o"], ["--save-video"])
    videos = list((tmp_path / "b").rglob("*.mp4"))
    assert code == 0 and len(videos) == 5
    assert all(row["video_file"].endswith(".mp4") for row in trials(tmp_path / "b"))


def test_nothing_is_recorded_without_the_study_consent(monkeypatch, tmp_path):
    code, _ = run_main(monkeypatch, tmp_path / "study", ["n"])
    assert code == 1 and not (tmp_path / "study").exists()


def test_record_clip_offers_both_studies(capsys):
    import record_clip
    assert record_clip.main([]) == 2
    assert "record_clip.py angles" in capsys.readouterr().out
