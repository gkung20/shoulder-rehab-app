"""Every session saved as one small JSON file, for results, history and the physio's export.

Files go to `<data folder>/sessions/2026-11-24_103015.json` (see src.user_profile.data_dir:
%APPDATA%\\Mouvement on Windows, MOUVEMENT_DATA_DIR in tests). No image or video is saved:
only numbers per movement. At most 365 files are kept (the oldest go first). Writes are
atomic (temporary file, then rename) and unreadable files are skipped when loading.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from src import __version__
from src.user_profile import data_dir
from src.willy_lines import evaluation_tip

SCHEMA = 1
MAX_SESSIONS = 365


def sessions_dir():
    return data_dir() / "sessions"


def _quality(evaluation):
    if getattr(evaluation, "status_label", "") == "INDETERMINE":
        return "unknown"
    return "correct" if evaluation.is_correct else "to_fix"


@dataclass
class SessionLog:
    """What happens during one session, kept as it goes and saved at the end."""

    exercise: str
    arm: str
    plan: dict = field(default_factory=dict)
    started_at: str = ""
    reps: list = field(default_factory=list)
    pain_before: int | None = None
    pain_after: int | None = None
    gentle: bool = False
    stops: list = field(default_factory=list)  # {"t": seconds, "kind": "pain" | "break" | "fatigue" | "time"}
    saved: bool = False

    @classmethod
    def start(cls, exercise, arm, plan=None, now=None):
        stamp = (now or dt.datetime.now()).isoformat(timespec="seconds")
        return cls(exercise=exercise, arm=arm, plan=asdict(plan) if plan is not None else {}, started_at=stamp)

    def add_rep(self, evaluation, t_sec):
        m = evaluation.metrics
        self.reps.append({
            "n": evaluation.rep_index,
            "t": round(float(t_sec), 1),
            "peak_deg": round(m.peak_abduction_deg, 1) if m else None,
            "hold_s": round(m.hold_duration_sec, 2) if m else None,
            "rise_s": round(m.concentric_duration_sec, 2) if m else None,
            "lower_s": round(m.eccentric_duration_sec, 2) if m else None,
            "target_reached": bool(m.target_reached) if m else False,
            "quality": _quality(evaluation),
            "issues": [error.category for error in evaluation.errors],
            "tip": evaluation_tip(evaluation),
        })

    def add_stop(self, kind, t_sec):
        self.stops.append({"t": round(float(t_sec), 1), "kind": kind})

    @property
    def worth_saving(self):
        return bool(self.reps) or self.pain_before is not None

    def record(self, *, sets=None, model="", fps=0., resting_angle=None, partial=False, now=None):
        """The JSON-ready record of this session."""
        ended = now or dt.datetime.now()
        started = _parse_time(self.started_at) or ended
        peaks = [r["peak_deg"] for r in self.reps if r["peak_deg"] is not None]
        counts = {q: sum(r["quality"] == q for r in self.reps) for q in ("correct", "to_fix", "unknown")}
        goal = sets.reps_per_set * sets.sets if sets is not None else None
        return {
            "schema": SCHEMA,
            "app_version": __version__,
            "exercise": self.exercise,
            "arm": self.arm,
            "plan": self.plan,
            "started_at": self.started_at,
            "ended_at": ended.isoformat(timespec="seconds"),
            "duration_s": round(max(0., (ended - started).total_seconds()), 1),
            "pain_before": self.pain_before,
            "pain_after": self.pain_after,
            "gentle": self.gentle,
            "stops": self.stops,
            "reps": self.reps,
            "totals": {
                "reps": len(self.reps), **counts,
                "best_peak_deg": max(peaks) if peaks else None,
                "mean_peak_deg": round(sum(peaks) / len(peaks), 1) if peaks else None,
                "goal": goal,
                "goal_reached": bool(sets is not None and sets.done),
                "sets_done": (sets.current_set - (0 if sets.done else 1)) if sets is not None else None,
            },
            "pose_model": model,
            "fps": round(float(fps or 0.), 1),
            "resting_angle": resting_angle,
            "partial": partial,
        }


def _parse_time(value):
    try:
        return dt.datetime.fromisoformat(str(value))
    except ValueError:
        return None


def save_session(record, directory=None, keep=MAX_SESSIONS):
    """Write one session file (atomically) and keep only the newest `keep` files."""
    directory = Path(directory or sessions_dir())
    directory.mkdir(parents=True, exist_ok=True)
    started = _parse_time(record.get("started_at")) or dt.datetime.now()
    stem = started.strftime("%Y-%m-%d_%H%M%S")
    path, suffix = directory / f"{stem}.json", 1
    while path.exists():
        suffix += 1
        path = directory / f"{stem}_{suffix}.json"
    handle, temporary = tempfile.mkstemp(dir=directory, prefix=".session-", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(record, file, ensure_ascii=False, indent=1)
        os.replace(temporary, path)
    except OSError:
        Path(temporary).unlink(missing_ok=True)
        raise
    prune(directory, keep)
    return path


def session_files(directory=None):
    directory = Path(directory or sessions_dir())
    return sorted(p for p in directory.glob("*.json") if not p.name.startswith(".")) if directory.exists() else []


def prune(directory=None, keep=MAX_SESSIONS):
    files = session_files(directory)
    for old in files[:max(0, len(files) - keep)]:
        old.unlink(missing_ok=True)


def load_sessions(directory=None, since=None):
    """Saved sessions, oldest first; files that can't be read are skipped. `since`: a date."""
    sessions = []
    for path in session_files(directory):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict) or not isinstance(record.get("reps"), list):
            continue
        started = _parse_time(record.get("started_at"))
        if started is None or (since is not None and started.date() < since):
            continue
        record["_file"] = path.name
        sessions.append(record)
    return sessions


def last_session(directory=None):
    sessions = load_sessions(directory)
    return sessions[-1] if sessions else None
