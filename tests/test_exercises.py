"""Exercises come from YAML; abduction keeps today's thresholds, another file can change them."""
import pytest

from src.config import ExerciseConfig
from src.exercises import Exercise, get_exercise, load_exercises
from src.session_processor import SessionProcessor
from src.synthetic_pose import body, rep_angles


def test_abduction_is_the_default_and_keeps_the_global_thresholds():
    exercise = get_exercise()
    assert exercise.id == "abduction" and "abduction" in load_exercises()
    assert exercise.name("en") == "Shoulder abduction" and exercise.camera_view == "front" and not exercise.both_arms
    config = ExerciseConfig.from_yaml()
    assert exercise.apply(config) == config
    assert SessionProcessor(config).config == config


def _run(processor):
    cues, reps = [], 0
    for i, angle in enumerate(rep_angles(hold=45) * 3):
        pts, world = body(angle)
        frame = processor.process(pts, world, 640, 480, i / 30)
        cues.append(frame.cue.code)
        reps += frame.new_evaluation is not None
    return cues, reps


def test_explicit_abduction_counts_exactly_like_before():
    config = ExerciseConfig.from_yaml()
    assert _run(SessionProcessor(config)) == _run(SessionProcessor(config, exercise=get_exercise("abduction")))


def test_a_second_exercise_file_overrides_thresholds(tmp_path):
    (tmp_path / "abduction.yaml").write_text("id: abduction\nnames: {fr: A, en: A}\n", encoding="utf-8")
    (tmp_path / "gentle.yaml").write_text(
        "id: gentle\nnames: {fr: Doux, en: Gentle}\narms: both\n"
        "thresholds:\n  abduction: {target_min_deg: 60, target_max_deg: 75}\n  timing: {min_hold_time_sec: 1.5}\n",
        encoding="utf-8")
    exercises = load_exercises(tmp_path)
    gentle = exercises["gentle"]
    assert gentle.both_arms and gentle.name("fr") == "Doux"
    processor = SessionProcessor(ExerciseConfig.from_yaml(), exercise=gentle)
    assert processor.config.abduction.target_min_deg == 60 and processor.config.timing.min_hold_time_sec == 1.5
    assert processor.state_machine.target_min_deg == 60


def test_bad_exercise_files_are_refused(tmp_path):
    with pytest.raises(ValueError):
        Exercise("x", {"fr": "x"})  # no English name
    with pytest.raises(ValueError):
        Exercise("x", {"fr": "x", "en": "x"}, thresholds={"abduction": {"made_up": 1}})
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: bad\nnames: {fr: b, en: b}\ncolour: red\n", encoding="utf-8")
    with pytest.raises(ValueError):
        Exercise.from_yaml(bad)
    with pytest.raises(ValueError):  # thresholds still go through ExerciseConfig's checks
        Exercise("x", {"fr": "x", "en": "x"}, thresholds={"abduction": {"target_min_deg": 10}}).apply(ExerciseConfig.from_yaml())
