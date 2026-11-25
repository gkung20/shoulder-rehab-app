"""Sessions are saved as small JSON files (numbers only), pruned to the last 365, loaded safely."""
import datetime as dt
import json
from types import SimpleNamespace

from src.session_plan import SetTracker
from src.session_store import SessionLog, load_sessions, save_session, session_files, sessions_dir
from src.user_profile import Plan


def evaluation(n, peak, correct=True, label="CORRECT"):
    metrics = SimpleNamespace(peak_abduction_deg=peak, hold_duration_sec=.8, concentric_duration_sec=1.5,
                              eccentric_duration_sec=1.6, target_reached=peak >= 80)
    errors = [] if correct else [SimpleNamespace(category="Inclinaison du tronc")]
    return SimpleNamespace(rep_index=n, metrics=metrics, is_correct=correct, status_label=label, errors=errors)


def test_a_session_round_trips(tmp_path):
    log = SessionLog.start("abduction", "right", Plan(reps_per_set=2, sets=1), now=dt.datetime(2026, 11, 24, 10, 30))
    log.pain_before = 2
    log.add_rep(evaluation(1, 88.4), 12.3)
    log.add_rep(evaluation(2, 74.9, correct=False, label="A CORRIGER"), 20.1)
    log.add_stop("break", 25)
    sets = SetTracker(reps_per_set=2, sets=1)
    sets.add_rep(0)
    sets.add_rep(0)
    record = log.record(sets=sets, model="pose_landmarker_full.task", fps=29.7, resting_angle=8.,
                        now=dt.datetime(2026, 11, 24, 10, 34))
    path = save_session(record, tmp_path)
    assert path.name == "2026-11-24_103000.json"
    loaded = load_sessions(tmp_path)[0]
    assert loaded["totals"] == {"reps": 2, "correct": 1, "to_fix": 1, "unknown": 0, "best_peak_deg": 88.4,
                                "mean_peak_deg": 81.7, "goal": 2, "goal_reached": True, "sets_done": 1}
    assert loaded["reps"][1]["tip"] == "E5.13" and loaded["duration_s"] == 240.
    assert loaded["plan"]["reps_per_set"] == 2 and loaded["pain_before"] == 2
    assert "jpg" not in path.read_text() and "png" not in path.read_text()  # numbers only


def test_files_are_pruned_and_bad_files_skipped(tmp_path):
    for day in range(1, 8):
        save_session({"started_at": f"2026-11-0{day}T09:00:00", "reps": []}, tmp_path, keep=5)
    files = session_files(tmp_path)
    assert len(files) == 5 and files[0].name.startswith("2026-11-03")
    (tmp_path / "2026-11-09_090000.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "2026-11-10_090000.json").write_text(json.dumps([1, 2]), encoding="utf-8")
    assert len(load_sessions(tmp_path)) == 5
    assert len(load_sessions(tmp_path, since=dt.date(2026, 11, 6))) == 2
    save_session({"started_at": "2026-11-07T09:00:00", "reps": []}, tmp_path, keep=10)
    assert (tmp_path / "2026-11-07_090000_2.json").exists()  # same second: a new name, nothing lost


def test_data_folder_override(monkeypatch, tmp_path):
    monkeypatch.setenv("MOUVEMENT_DATA_DIR", str(tmp_path))
    assert sessions_dir() == tmp_path / "sessions"
    save_session({"started_at": "2026-11-24T10:00:00", "reps": []})
    assert len(load_sessions()) == 1
