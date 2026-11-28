"""Exercises defined in YAML (`config/exercises/*.yaml`).

An exercise says what is measured and how (camera view, one arm or both, Willy's demo) and
may override the movement thresholds of `config/exercise_config.yaml`. `Exercise.apply()`
returns the effective configuration that the processor, state machine and rules engine
read, so each layer (exercise, then the patient's plan in src.user_profile) only changes
what it defines.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

import yaml

EXERCISES_DIR = Path(__file__).resolve().parents[1] / "config" / "exercises"
DEFAULT_EXERCISE = "abduction"
CAMERA_VIEWS = ("front", "side")
ARMS = ("one", "both")
# Threshold names an exercise may override, by group of ExerciseConfig.
OVERRIDABLE = {
    "abduction": ("rest_threshold_deg", "rising_start_deg", "target_min_deg", "target_max_deg", "overshoot_warn_deg"),
    "timing": ("min_concentric_time_sec", "max_concentric_time_sec", "min_hold_time_sec",
               "min_eccentric_time_sec", "max_eccentric_time_sec"),
}


@dataclass(frozen=True)
class Exercise:
    id: str
    names: dict
    camera_view: str = "front"
    measured_angle: str = "abduction"
    arms: str = "one"
    willy_demo: str = "raise_side"
    thresholds: dict = field(default_factory=dict)  # {"abduction": {...}, "timing": {...}}
    short: dict = field(default_factory=dict)       # a short name for the settings ("Deux bras")

    def __post_init__(self):
        if not self.id or not isinstance(self.names, dict) or not {"fr", "en"} <= set(self.names):
            raise ValueError("An exercise needs an id and names in French and English")
        if self.camera_view not in CAMERA_VIEWS or self.arms not in ARMS:
            raise ValueError(f"Unknown camera view or arms for exercise {self.id}")
        for group, values in self.thresholds.items():
            unknown = set(values) - set(OVERRIDABLE.get(group, ()))
            if group not in OVERRIDABLE or unknown:
                raise ValueError(f"Exercise {self.id}: unknown thresholds {group} {sorted(unknown)}")

    def name(self, language="fr"):
        return self.names.get(language) or self.names["fr"]

    def short_name(self, language="fr"):
        return self.short.get(language) or self.short.get("fr") or self.name(language)

    @property
    def both_arms(self):
        return self.arms == "both"

    def apply(self, config):
        """The configuration with this exercise's thresholds (validated by ExerciseConfig)."""
        changes = {group: replace(getattr(config, group), **{k: float(v) for k, v in values.items()})
                   for group, values in self.thresholds.items()}
        return replace(config, **changes) if changes else config

    @classmethod
    def from_yaml(cls, path):
        with open(path, "r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        known = {"id", "names", "camera_view", "measured_angle", "arms", "willy_demo", "thresholds", "short"}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"{Path(path).name}: unknown keys {sorted(unknown)}")
        return cls(**{**raw, "thresholds": raw.get("thresholds") or {}, "short": raw.get("short") or {}})


def load_exercises(directory=EXERCISES_DIR):
    """Every exercise in the folder, by id (read once per folder)."""
    return dict(_load(str(Path(directory).resolve())))


@lru_cache(maxsize=8)
def _load(directory):
    exercises = {}
    for path in sorted(Path(directory).glob("*.yaml")):
        exercise = Exercise.from_yaml(path)
        if exercise.id in exercises:
            raise ValueError(f"Two exercises use the id {exercise.id}")
        exercises[exercise.id] = exercise
    return tuple(exercises.items())


def get_exercise(exercise_id=None, directory=EXERCISES_DIR):
    exercises = load_exercises(directory)
    return exercises.get(exercise_id or DEFAULT_EXERCISE) or exercises[DEFAULT_EXERCISE]
