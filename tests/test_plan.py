"""The physio's plan: defaults equal today's thresholds, saved with its history, used by the processor."""
import json

from src.config import ExerciseConfig
from src.session_processor import SessionProcessor
from src.user_profile import MAX_PLAN_HISTORY, PLAN_BOUNDS, SCHEMA_VERSION, Plan, Profile


def test_default_plan_is_todays_configuration():
    config = ExerciseConfig.from_yaml()
    plan = Plan.from_config(config)
    assert (plan.target_min_deg, plan.target_max_deg, plan.rest_max_deg) == (80, 100, 25)
    assert plan.apply(config) == config
    assert plan.total_reps == 30


def test_plan_is_saved_with_history_and_reloaded(tmp_path):
    path = tmp_path / "profile.json"
    profile = Profile.load(path)
    config = ExerciseConfig.from_yaml()
    assert profile.plans == {} and profile.current_plan(config) == Plan.from_config(config)
    for target in range(MAX_PLAN_HISTORY + 3):
        profile.set_plan(Plan(target_min_deg=40 + target, target_max_deg=90))
    profile.save()
    again = Profile.load(path)
    assert again.current_plan(config).target_min_deg == 40 + MAX_PLAN_HISTORY + 2
    assert len(again.plan_history) == MAX_PLAN_HISTORY and again.plans["abduction"]["updated_at"]
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == SCHEMA_VERSION


def test_old_profiles_without_a_plan_still_load(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({"language": "fr", "tour_done": True, "session_days": ["2026-11-20"]}),
                    encoding="utf-8")
    profile = Profile.load(path)
    assert profile.tour_done and profile.plans == {} and profile.plan_history == []
    assert profile.schema_version == SCHEMA_VERSION
    path.write_text(json.dumps({"plan": {"target_min_deg": "abc", "sets": 99, "made_up": 1}}), encoding="utf-8")
    plan = Profile.load(path).current_plan(ExerciseConfig.from_yaml())
    assert plan.sets == PLAN_BOUNDS["sets"][1] and plan.target_min_deg == 80


def test_values_are_kept_in_bounds_and_in_a_valid_order():
    plan = Plan(target_min_deg=200, target_max_deg=10, rest_max_deg=90, hold_sec=-3, reps_per_set=0,
                pain_go_max=8, pain_gentle_max=2).clamped()
    assert plan.target_min_deg == 160 and plan.target_max_deg == 160
    assert plan.rest_max_deg == 60 and plan.hold_sec == 0 and plan.reps_per_set == 1
    assert plan.pain_gentle_max == 8
    low = Plan(target_min_deg=30, rest_max_deg=40).clamped()
    assert low.rest_max_deg + 7 < low.target_min_deg
    low.apply(ExerciseConfig.from_yaml())  # still a valid configuration


def test_the_processor_counts_with_the_plan():
    plan = Plan(target_min_deg=60, target_max_deg=70, rest_max_deg=20, hold_sec=1.)
    processor = SessionProcessor(ExerciseConfig.from_yaml(), plan=plan)
    machine = processor.state_machine
    assert (machine.rest_threshold_deg, machine.rising_start_deg) == (20, 27)
    assert (machine.target_min_deg, machine.target_max_deg) == (60, 70)
    assert processor.config.timing.min_hold_time_sec == 1. and processor.plan is plan


def test_pain_bands():
    plan = Plan()
    assert [plan.pain_band(p) for p in (0, 3, 4, 6, 7, 10)] == ["go", "go", "gentle", "gentle", "stop", "stop"]


def test_a_version_2_plan_becomes_the_plan_of_its_exercise(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({"schema_version": 2, "plan": {"exercise": "abduction", "target_min_deg": 60, "sets": 2}}),
                    encoding="utf-8")
    profile = Profile.load(path)
    config = ExerciseConfig.from_yaml()
    assert profile.exercise == "abduction" and set(profile.plans) == {"abduction"}
    assert profile.current_plan(config).target_min_deg == 60 and profile.current_plan(config).sets == 2
    assert profile.current_plan(config, "both_arms") == Plan.from_config(config, "both_arms")  # untouched
    profile.save()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert "plan" not in saved and saved["schema_version"] == SCHEMA_VERSION == 3


def test_each_exercise_keeps_its_own_plan(tmp_path):
    path = tmp_path / "profile.json"
    profile = Profile.load(path)
    config = ExerciseConfig.from_yaml()
    profile.set_plan(Plan(exercise="abduction", target_min_deg=70))
    profile.set_plan(Plan(exercise="both_arms", target_min_deg=50, reps_per_set=5))
    profile.exercise = "both_arms"
    profile.save()
    again = Profile.load(path)
    assert again.exercise == "both_arms"
    assert again.current_plan(config, "abduction").target_min_deg == 70
    both = again.current_plan(config, "both_arms")
    assert (both.exercise, both.target_min_deg, both.reps_per_set) == ("both_arms", 50, 5)
    assert again.plan_history == []  # a first plan for each exercise replaces nothing
