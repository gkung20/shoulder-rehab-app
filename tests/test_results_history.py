"""Results of a session and the 30-day history, from saved records, in French and English."""
import datetime as dt

import pytest

from src import layout as L
from src.results_screen import daily, most_frequent_tip, render_history, render_results, results_lines, trend
from tests.app_fakes import ScriptedWindow, make_app

TODAY = dt.date(2026, 11, 25)


def record(day, best=90., reps=10, pain=None, rows=None):
    rows = rows if rows is not None else [
        {"n": i + 1, "peak_deg": best - (i % 3) * 4, "quality": "correct" if i % 4 else "to_fix",
         "tip": None if i % 4 else "E5.13"} for i in range(reps)]
    peaks = [r["peak_deg"] for r in rows]
    return {"started_at": f"{day.isoformat()}T10:00:00", "duration_s": 372., "pain_before": pain, "pain_after": None,
            "plan": {"target_min_deg": 80, "target_max_deg": 100}, "reps": rows,
            "totals": {"reps": len(rows), "correct": sum(r["quality"] == "correct" for r in rows),
                       "best_peak_deg": max(peaks) if peaks else None,
                       "mean_peak_deg": sum(peaks) / len(peaks) if peaks else None, "goal": 30}}


def test_results_lines_and_tip():
    r = record(TODAY, reps=8)
    assert most_frequent_tip(r) == "E5.13"
    lines = results_lines(r, "en")
    assert "8 movements" in lines[0] and any("upright" in line.lower() for line in lines)
    assert results_lines(record(TODAY, rows=[]), "fr")  # nothing counted: still a kind line


@pytest.mark.parametrize("language", ["fr", "en"])
@pytest.mark.parametrize("reps", [0, 1, 30])
def test_results_screen_draws(language, reps):
    image, boxes = render_results(record(TODAY, reps=reps, pain=2), (1600, 1000), language)
    assert image.shape == (1000, 1600, 3)
    assert {a for a, _ in boxes} == {"results_back", "results_history"}


def test_daily_values_and_trends():
    days = [TODAY - dt.timedelta(days=d) for d in (10, 8, 6, 4, 2, 0)]
    rising = [record(d, best=60 + 6 * i, pain=3) for i, d in enumerate(days)]
    falling = [record(d, best=110 - 6 * i) for i, d in enumerate(days)]
    flat = [record(d, best=90 + (i % 2)) for i, d in enumerate(days)]
    assert trend(daily(rising, TODAY)) == "improving"
    assert trend(daily(falling, TODAY)) == "lower"
    assert trend(daily(flat, TODAY)) == "steady"
    assert trend(daily(rising[:3], TODAY)) is None and trend({}) is None
    values = daily(rising + [record(TODAY, best=99., reps=4, pain=5)], TODAY)
    assert values[TODAY]["reps"] == 14 and values[TODAY]["best"] == 99. and values[TODAY]["pain"] == 4.
    assert TODAY - dt.timedelta(days=40) not in daily([record(TODAY - dt.timedelta(days=40))], TODAY)


@pytest.mark.parametrize("language", ["fr", "en"])
def test_history_screen_draws_with_gaps_and_when_empty(language):
    gappy = [record(TODAY - dt.timedelta(days=d), best=80 + d, pain=d % 5) for d in (29, 20, 3, 1)]
    for records in ([], gappy):
        image, boxes, line_id = render_history(records, None, language, streak=2, today=TODAY)
        assert image.shape == (840, 1280, 3) and line_id.startswith("E7.0")
        actions = {a for a, _ in boxes}
        assert {"history_back", "history_export", "period:7", "period:30", "period:all"} <= actions
        assert all(L.CANVAS.encloses(b) for _, b in boxes)


def patient(window):
    """A short session, then "Mon bilan", then "Historique", then back and close."""
    app, state = window.app, getattr(window, "state", 0)
    if state == 0 and app.director.screen == "home":
        window.click_action("home_start", app.director.overlay.hit_boxes)
    elif state == 0 and app.controls.mode == "ready":
        window.click(L.MAIN_BUTTON)
    elif state == 0 and app.controls.mode == "running" and app.processor.rules_engine.session.total_repetitions >= 1:
        window.click(L.FINISH_BUTTON)
        window.state = 1
    elif state == 1 and app.controls.mode == "finished" and app.modal is None:
        window.click(L.FINISH_BUTTON)  # now "Mon bilan"
        window.state = 2
    elif state == 2 and app.modal == "results":
        window.click_action("results_history", app.screens["results"].hit_boxes)
        window.state = 3
    elif state == 3 and app.modal == "history":
        window.click_action("period:7", app.screens["history"].hit_boxes)
        window.click_action("history_back", app.screens["history"].hit_boxes)
        window.state = 4
    elif state == 4 and app.modal == "results":
        window.press(27)  # Esc closes the results
        window.state = 5
    elif state == 5 and app.modal is None:
        window.press(27)  # Esc closes the app
        window.state = 6


def test_results_and_history_open_after_a_session(monkeypatch, tmp_path):
    window = ScriptedWindow(patient)
    app = make_app(monkeypatch, tmp_path, window, language="en", tour_done=True)
    assert app.run() == 0 and window.state == 6
    assert app.screens["history"].period == "7" and app.screens["results"].record["totals"]["reps"] >= 1
    said = [call.args[0] for call in app.fake_audio.say.call_args_list]
    assert any("movement" in line for line in said) and any(line.startswith("Your history starts here") for line in said)
