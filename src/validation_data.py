"""Files of the validation study (Phase 7, see docs/validation-protocol.md).

The study folder (default `%APPDATA%\\Mouvement\\validation`, or `--out`) holds:

    trials.csv                    one row per recorded trial; when a trial is recorded again,
                                  its newest row wins
    <subject>/<trial>_<time>.csv  every frame of one trial: the app's angle and all landmarks
    <subject>/<trial>_<time>.mp4  only with --save-video and the volunteer's video consent

Plain CSV (comma, dot decimals, UTF-8) so any tool can read it.
"""
from __future__ import annotations

import csv
import math
import statistics
from pathlib import Path

from src.user_profile import data_dir

POSITIONS = (0, 30, 60, 90, 120)  # target positions of a hold trial, in degrees
HOLD_SKIP_SEC = .5     # the first half second of a hold is left out: the arm is still settling
MIN_VALID_SHARE = .5   # a hold with fewer usable frames than this is not assessed

TRIAL_FIELDS = (
    "trial_id", "subject", "arm", "kind", "target_deg", "trial",
    "reference_deg", "observer_reps", "app_deg", "app_reps", "valid_frames", "frames",
    "status", "model", "camera", "recorded_at", "frames_file", "video_file", "notes",
)
FRAME_FIELDS = (
    ("frame", "time_s", "angle_deg", "angle_valid", "status", "phase", "reps_total", "reference_mode")
    + tuple(f"n{i}_{axis}" for i in range(33) for axis in "xyv")   # image landmarks: x, y in [0, 1], visibility
    + tuple(f"w{i}_{axis}" for i in range(33) for axis in "xyz")   # world landmarks, metres around the hips
)
STATUSES = ("ok", "redo", "skipped")


def validation_dir():
    return data_dir() / "validation"


def trial_id(subject, arm, kind, target, trial):
    """V01_right_hold060_t2, V01_left_reps_t1."""
    name = f"hold{int(target):03d}" if kind == "hold" else "reps"
    return f"{subject}_{arm}_{name}_t{int(trial)}"


def safe_subject(text):
    """Anonymous IDs only: letters, digits, - and _ (V01, P-03)."""
    cleaned = "".join(c for c in str(text).strip() if c.isalnum() or c in "-_")
    return cleaned[:20]


def _number(value, digits=4):
    return "" if value is None else round(float(value), digits)


def frame_row(index, time_s, analysis, landmarks, world, reps_total):
    """One line of a trial's frame file."""
    angle = analysis.metrics.get("abduction") if analysis is not None else None
    row = {
        "frame": index, "time_s": round(time_s, 4),
        "angle_deg": _number(angle, 2), "angle_valid": int(angle is not None),
        "status": getattr(analysis, "status", ""), "phase": getattr(getattr(analysis, "phase", None), "name", ""),
        "reps_total": reps_total, "reference_mode": getattr(analysis, "angle_reference", ""),
    }
    points = list(landmarks or [])
    for i in range(33):
        point = points[i] if i < len(points) else None
        row[f"n{i}_x"] = _number(getattr(point, "x", None))
        row[f"n{i}_y"] = _number(getattr(point, "y", None))
        row[f"n{i}_v"] = _number(getattr(point, "visibility", None), 3)
    points = list(world or [])
    for i in range(33):
        point = points[i] if i < len(points) else None
        for axis in "xyz":
            row[f"w{i}_{axis}"] = _number(getattr(point, axis, None))
    return row


def write_frames(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, FRAME_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def read_frames(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def trial_app_angle(rows, skip_sec=HOLD_SKIP_SEC, min_share=MIN_VALID_SHARE):
    """The app's angle for a hold: the median of the usable frames after the first half second.

    Returns (angle or None, usable frames, frames in the window). None when fewer than half of
    the frames had an angle (person lost, turned, arm hidden): the trial is then not assessed.
    """
    times = [(_float(r.get("time_s")), r) for r in rows]
    times = [(t, r) for t, r in times if t is not None]
    if not times:
        return None, 0, 0
    start = times[0][0] + skip_sec
    window = [r for t, r in times if t >= start]
    usable = [_float(r.get("angle_deg")) for r in window if str(r.get("angle_valid")) == "1"]
    usable = [a for a in usable if a is not None]
    if not window or len(usable) < min_share * len(window):
        return None, len(usable), len(window)
    return round(statistics.median(usable), 1), len(usable), len(window)


def append_trial(folder, row):
    """Add one row to trials.csv (written with its header the first time)."""
    path = Path(folder) / "trials.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, TRIAL_FIELDS, extrasaction="ignore")
        if new:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in TRIAL_FIELDS})


def load_trials(folder):
    """One row per trial, in the order trials were first recorded.

    Each row of trials.csv is one attempt. A trial's result is its newest attempt with a
    reading ("ok"); a trial without any is shown by its newest attempt (redo or skipped).
    """
    path = Path(folder) / "trials.csv"
    if not path.exists():
        return []
    newest, newest_ok = {}, {}
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("trial_id"):
                newest[row["trial_id"]] = row
                if row.get("status") == "ok":
                    newest_ok[row["trial_id"]] = row
    return [newest_ok.get(key, row) for key, row in newest.items()]


def done_ids(folder, subject):
    """Trials of this subject already recorded with a reading (so a new session resumes)."""
    return {r["trial_id"] for r in load_trials(folder) if r.get("subject") == subject and r.get("status") == "ok"}
