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
    assert profile.plan is None and profile.current_plan(config) == Plan.from_config(config)
    for target in range(MAX_PLAN_HISTORY + 3):
        profile.set_plan(Plan(target_min_deg=40 + target, target_max_deg=90))
    profile.save()
    again = Profile.load(path)
    assert again.current_plan(config).target_min_deg == 40 + MAX_PLAN_HISTORY + 2
    assert len(again.plan_history) == MAX_PLAN_HISTORY and again.plan["updated_at"]
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == SCHEMA_VERSION


def test_old_profiles_without_a_plan_still_load(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({"language": "fr", "tour_done": True, "session_days": ["2026-11-20"]}),
                    encoding="utf-8")
    profile = Profile.load(path)
    assert profile.tour_done and profile.plan is None and profile.plan_history == []
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
