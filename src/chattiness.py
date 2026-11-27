"""How much Willy talks (Phase 9.5): "Willy parle : beaucoup / normalement / peu".

The level changes the coach's pauses between spoken lines and which everyday lines play
(encouragements, tips, "still there?", the details at the end of a session). Safety and pain
lines always play, and so do the lines that are needed to go on: setup and framing, the
camera, the voice failing, the sets of the plan, the start and the end of a session.
"""
from __future__ import annotations

LEVELS = ("lots", "normal", "little")
DEFAULT = "normal"
LABELS = {"lots": "Beaucoup", "normal": "Normalement", "little": "Peu"}  # shown in French, translated by i18n

# Coach timing, as factors of the configured values (config/exercise_config.yaml, "audio:").
COACH = {
    "lots": {"interval": .6, "cooldown": .6, "every_reps": 3, "guidance": "complete"},
    "normal": {"interval": 1., "cooldown": 1., "every_reps": None, "guidance": None},  # None: as configured
    "little": {"interval": 2., "cooldown": 2.5, "every_reps": 10, "guidance": "essential"},
}
# Seconds without movement before Willy asks "Still there?" (None: he doesn't ask).
IDLE_AFTER = {"lots": 20., "normal": 30., "little": None}
# Everyday lines and the levels at which they play.
EVERYDAY = {
    "E6.02": ("lots", "normal"),           # three spot-on movements in a row
    "E6.04": ("lots", "normal"),           # still there?
    "E7.02": ("lots", "normal"),           # more spot-on movements than last time
    "E1.06": ("lots", "normal"),           # several days in a row
    "S8.01": ("lots", "normal"),           # where the Pause button is (once)
    "S8.04": ("lots", "normal"),           # where the Finish button is (once)
    "S8.07": ("lots", "normal"),           # movements not fully measured
    "S8.09": ("lots", "normal"),           # the tip for next time
}
# Always played, whatever the level (safety, pain, and what the patient needs to go on).
ALWAYS = ("E2.", "E9.", "E3.", "E8.", "E6.07", "E6.08", "E6.09", "E6.10", "E6.11", "S8.05", "S8.06",
          "E7.01", "S8.14", "E7.03")


def level_of(value):
    return value if value in LEVELS else DEFAULT


def always(line_id):
    return any(line_id == prefix or line_id.startswith(prefix) for prefix in ALWAYS if prefix.endswith("."))\
        or line_id in ALWAYS


def plays(line_id, level):
    """Whether an everyday line plays at this level; safety and pain lines always do."""
    if always(line_id):
        return True
    return level_of(level) in EVERYDAY.get(line_id, LEVELS)


def coach_settings(level, base):
    """The coach's timing for a level, from the configured audio settings `base`."""
    rule = COACH[level_of(level)]
    return {
        "min_interval_sec": base.min_interval_sec * rule["interval"],
        "repeat_cooldown_sec": base.repeat_cooldown_sec * rule["cooldown"],
        "announce_every_reps": rule["every_reps"] or base.announce_every_reps,
        "guidance_mode": rule["guidance"] or base.guidance_mode,
    }
