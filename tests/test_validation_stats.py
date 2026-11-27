"""Phase 7.3: the validation report on synthetic data with a known error."""
import math

import numpy as np
import pytest

from src import validation_data as vd
from src import validation_stats as vs
from src.validation_stats import Pair


def synthetic_study(folder, bias=3., noise=2., subjects=10, seed=11, reps_error=None, frames=False):
    """10 volunteers x 2 arms x 5 positions x 3 trials; app = goniometer + bias + N(0, noise)."""
    rng = np.random.default_rng(seed)
    for s in range(1, subjects + 1):
        subject = f"V{s:02d}"
        for arm in ("right", "left"):
            for trial in (1, 2, 3):
                for target in vd.POSITIONS:
                    reference = round(target + rng.normal(0, 4), 1)  # the volunteer is never exactly at the target
                    app = reference + bias + rng.normal(0, noise)
                    row = {"trial_id": vd.trial_id(subject, arm, "hold", target, trial), "subject": subject,
                           "arm": arm, "kind": "hold", "target_deg": target, "trial": trial,
                           "reference_deg": reference, "app_deg": round(app, 2), "status": "ok"}
                    if frames:  # 3 s of frames around the app's value, a few frames without an angle
                        name = f"{subject}/{row['trial_id']}.csv"
                        rows = [{"time_s": i / 30, "angle_deg": round(app + rng.normal(0, .3), 2),
                                 "angle_valid": int(i % 10 != 0)} for i in range(90)]
                        vd.write_frames(folder / name, [{**{f: "" for f in vd.FRAME_FIELDS}, **r} for r in rows])
                        row["frames_file"] = name
                    vd.append_trial(folder, row)
            app_reps = 10 if reps_error is None else 10 + reps_error(s, arm)
            vd.append_trial(folder, {"trial_id": vd.trial_id(subject, arm, "reps", None, 1), "subject": subject,
                                     "arm": arm, "kind": "reps", "trial": 1, "observer_reps": 10,
                                     "app_reps": app_reps, "status": "ok"})


def test_a_known_error_is_found_back(tmp_path):
    synthetic_study(tmp_path)
    result = vs.report(tmp_path)
    overall = result["overall"]
    assert overall["n"] == 300 and overall["subjects"] == 10
    assert abs(overall["bias"] - 3.) < .4
    assert abs(overall["sd"] - 2.) < .3
    low, high = overall["loa"]
    assert abs(low - (3 - 1.96 * 2)) < .8 and abs(high - (3 + 1.96 * 2)) < .8
    expected_mae = 2 * math.sqrt(2 / math.pi) * math.exp(-(1.5 ** 2) / 2) + 3 * math.erf(1.5 / math.sqrt(2))
    assert abs(overall["mae"] - expected_mae) < .35  # E|N(3, 2)| = 3.27
    assert overall["icc"] > .95
    for target, stats in result["by_target"].items():
        assert stats["n"] == 60 and abs(stats["bias"] - 3) < 1
    ci = result["ci"]["bias"]
    assert ci[0] < overall["bias"] < ci[1] and ci[1] - ci[0] < 1.5
    assert result["counting"]["correct_pct"] == 100.
    report = (tmp_path / "report" / "validation_report.md").read_text(encoding="utf-8")
    assert "Bland–Altman" in report and "✔ atteinte" in report and "ICC(2,1)" in report
    for chart in ("bland_altman.png", "app_vs_reference.png", "error_by_angle.png"):
        assert (tmp_path / "report" / chart).stat().st_size > 10_000
    assert (tmp_path / "report" / "validation_pairs.csv").read_text(encoding="utf-8-sig").count("\n") == 301


def test_targets_not_met_are_reported_as_such(tmp_path):
    synthetic_study(tmp_path, bias=8., noise=4., reps_error=lambda s, arm: -2 if s % 2 else 0)
    result = vs.report(tmp_path, lang="en")
    report = (tmp_path / "report" / "validation_report.md").read_text(encoding="utf-8")
    assert result["overall"]["mae"] > 5 and report.count("✘ not met") == 3
    counting = result["counting"]
    assert counting["missed"] == 20 and counting["extra"] == 0 and counting["correct_pct"] == pytest.approx(90.)


def test_exactly_on_a_target_counts_as_met(tmp_path):
    synthetic_study(tmp_path, subjects=4, reps_error=lambda s, arm: -1 if s % 2 else 0)
    result = vs.report(tmp_path)
    assert result["counting"]["correct_pct"] == pytest.approx(95.)
    report = (tmp_path / "report" / "validation_report.md").read_text(encoding="utf-8")
    assert "| 95,0 % | ≥ 95 % | ✔ atteinte |" in report


def test_the_frame_files_are_the_source_of_the_apps_angle(tmp_path):
    synthetic_study(tmp_path, subjects=3, frames=True)
    pairs, _, left_out, _ = vs.collect(tmp_path)
    assert len(pairs) == 90 and not left_out
    # a hold whose frames mostly lack an angle is left out, even if trials.csv has a value
    first = vd.load_trials(tmp_path)[0]
    rows = vd.read_frames(tmp_path / first["frames_file"])
    for row in rows[:70]:
        row["angle_valid"] = "0"
    vd.write_frames(tmp_path / first["frames_file"], rows)
    pairs, _, left_out, _ = vs.collect(tmp_path)
    assert len(pairs) == 89 and left_out == {"holds_not_assessed": 1}


def test_icc_and_repeated_limits_match_published_and_hand_calculations():
    # Shrout & Fleiss (1979), 6 targets rated by 4 judges: ICC(2,1) = 0.29 in the paper
    judges = ([9, 6, 8, 7, 10, 6], [2, 1, 4, 1, 5, 2], [5, 3, 6, 2, 6, 4], [8, 2, 8, 6, 9, 7])
    assert vs.icc_a1(*judges) == pytest.approx(.29, abs=.005)
    # judges 1 and 2 only, by hand: MSR = 4.683, MSC = 80.083, MSE = 0.683, so
    # ICC = (4.683 - 0.683) / (4.683 + 0.683 + 2 (80.083 - 0.683) / 6) = 4 / 31.833
    assert vs.icc_a1(judges[0], judges[1]) == pytest.approx(4 / 31.8333, abs=1e-3)
    assert vs.icc_a1([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.)
    # equal trials per volunteer and no between-volunteer spread: the plain SD
    groups = [[1., 3.], [1., 3.], [1., 3.]]
    plain = np.std(sum(groups, []), ddof=1)
    assert vs.sd_repeated(groups) == pytest.approx(math.sqrt(2.), abs=1e-9) and plain < math.sqrt(2.) + .01
    # a volunteer offset adds the between-volunteer part
    assert vs.sd_repeated([[0., 0.], [4., 4.], [8., 8.]]) == pytest.approx(4., abs=1e-9)


def test_rep_counting():
    rows = [{"app_reps": "10", "observer_reps": "10"}, {"app_reps": "11", "observer_reps": "10"},
            {"app_reps": "8", "observer_reps": "10"}]
    counting = vs.rep_counting(rows)
    assert counting == {"sets": 3, "exact": 1, "observed": 30, "counted": 29, "extra": 1, "missed": 2,
                        "correct_pct": pytest.approx(90.)}


def test_an_empty_study_gives_a_short_report(tmp_path):
    vd.append_trial(tmp_path, {"trial_id": "V01_right_hold060_t1", "subject": "V01", "kind": "hold",
                               "status": "skipped"})
    result = vs.report(tmp_path)
    assert result["overall"] is None
    assert "Aucun maintien" in (tmp_path / "report" / "validation_report.md").read_text(encoding="utf-8")


def test_command_line(tmp_path, capsys):
    import evaluate_dataset
    assert evaluate_dataset.main([]) == 2
    assert evaluate_dataset.main(["angles", "--data", str(tmp_path / "none")]) == 1
    synthetic_study(tmp_path, subjects=3)
    assert evaluate_dataset.main(["angles", "--data", str(tmp_path), "--out", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out" / "validation_report.md").exists()
    assert "erreur absolue moyenne" in capsys.readouterr().out


def test_pairs_know_their_difference():
    assert Pair("V01", "right", 60, 1, 58., 61.5).diff == pytest.approx(3.5)
