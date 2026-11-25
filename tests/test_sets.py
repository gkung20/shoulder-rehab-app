"""Sets from the physio's plan: reps per set, rest between sets, and a session that ends by itself."""
from dataclasses import asdict

from src import layout as L
from src.session_plan import SetTracker
from src.user_profile import Plan
from tests.app_fakes import ScriptedWindow, make_app
from tests.test_willy_tour import Harness


def test_set_tracker_counts_sets_and_rests():
    sets = SetTracker(reps_per_set=3, sets=2, rest_sec=30.)
    assert [sets.add_rep(0.) for _ in range(3)] == ["rep", "rep", "set_done"]
    assert sets.resting and sets.waiting and sets.add_rep(1.) == "rep" and sets.reps_in_set == 3
    assert sets.tick(10.) is None and sets.rest_left(10.) == 20.
    assert sets.tick(30.) == "rest_over" and sets.tick(31.) is None and sets.waiting and not sets.resting
    assert sets.next_set() and sets.current_set == 2 and sets.reps_in_set == 0 and sets.is_last_set
    assert [sets.add_rep(40.) for _ in range(3)] == ["rep", "rep", "plan_done"] and sets.done
    assert sets.total_done == 6
    assert SetTracker.from_plan(Plan(reps_per_set=10), gentle=True).reps_per_set == 7


def test_willy_rests_between_sets_and_reaches_the_goal(tmp_path):
    h = Harness(tmp_path, language="en", tour_done=True)
    h.director.screen, h.mode = "dashboard", "running"
    h.run(1.)
    h.director.set_done(1)
    assert h.line == "E6.09"
    h.mode = "paused"
    h.run(15.)  # a rest between sets is not a pause: no S8.02 / S8.03
    assert "S8.02" not in h.profile.seen and "S8.03" not in h.profile.seen
    h.director.rest_over(2)
    assert h.line == "E6.10"
    h.director.set_started(2, last=True)
    assert h.line == "E6.11"
    h.mode = "running"
    h.run(1.)
    h.director.plan_done()
    h.mode = "finished"
    h.frame()
    assert h.line == "E6.03"


def patient(window):
    app = window.app
    if app.director.screen == "home":
        window.click_action("home_start", app.director.overlay.hit_boxes)
    elif app.controls.mode == "ready":
        window.click(L.MAIN_BUTTON)
    elif app.controls.mode == "paused" and app.sets is not None and app.sets.rest_over:
        window.click(L.MAIN_BUTTON)  # "Reprendre": the next set
    elif app.controls.mode == "finished":
        said = [call.args[0] for call in app.fake_audio.say.call_args_list]
        if "That's today's goal. Well done!" in said and not getattr(window, "closing", False):
            window.closing = True
            window.press(27)


def test_a_planned_session_rests_between_sets_and_finishes_by_itself(monkeypatch, tmp_path):
    plan = asdict(Plan(reps_per_set=2, sets=2, rest_between_sets_sec=10))
    window = ScriptedWindow(patient)
    app = make_app(monkeypatch, tmp_path, window, language="en", tour_done=True, plan=plan)
    assert app.run() == 0
    assert app.sets.done and app.processor.rules_engine.session.total_repetitions == 4
    said = [call.args[0] for call in app.fake_audio.say.call_args_list]
    assert "Set 1 done. Have a rest." in said and "Set 2 whenever you like: press Resume." in said
    assert "Last set! You're nearly there." in said
