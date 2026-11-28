"""The patient's small local profile: language, first-use tour, a few choices and session days.

It stays on this computer (no network): %APPDATA%\\Mouvement\\profile.json on Windows and
~/.mouvement/profile.json elsewhere. MOUVEMENT_DATA_DIR points it somewhere else (tests).
No video, image or measurement is stored here.
"""
from dataclasses import asdict, dataclass, field, fields, replace
import datetime as dt
import json
import os
from pathlib import Path
import sys
import tempfile

MAX_DAYS = 60
SCHEMA_VERSION = 3      # 1: before plans (Nov 2026); 2: physio plan and its history; 3: a plan per exercise
MAX_PLAN_HISTORY = 20

# Settings the physio can change: (lowest, highest, step). Shared with the settings screen.
PLAN_BOUNDS = {
    "target_min_deg": (30, 160, 5),
    "target_max_deg": (30, 160, 5),
    "rest_max_deg": (10, 60, 5),
    "hold_sec": (0, 10, .5),
    "reps_per_set": (1, 30, 1),
    "sets": (1, 5, 1),
    "rest_between_sets_sec": (10, 180, 10),
    "sessions_per_week": (1, 14, 1),
    "max_session_min": (5, 30, 1),
    "pain_go_max": (0, 9, 1),
    "pain_gentle_max": (1, 10, 1),
}


@dataclass
class Plan:
    """The physio's plan for one patient. Defaults come from the exercise configuration.

    Pain bands: 0..pain_go_max = normal session; up to pain_gentle_max = gentle session;
    above = no session today.
    """
    exercise: str = "abduction"
    arm: str | None = None            # None: the patient picks the arm on the session screen
    target_min_deg: float = 80.
    target_max_deg: float = 100.
    rest_max_deg: float = 25.
    hold_sec: float = .5
    reps_per_set: int = 10
    sets: int = 3
    rest_between_sets_sec: int = 60
    sessions_per_week: int = 5
    max_session_min: int = 15
    pain_go_max: int = 3
    pain_gentle_max: int = 6
    seated: bool = False
    notes: str = ""
    updated_at: str = ""

    @classmethod
    def from_config(cls, config, exercise="abduction"):
        """The default plan: today's thresholds of the (exercise-adjusted) configuration."""
        a, t = config.abduction, config.timing
        return cls(exercise=exercise, target_min_deg=a.target_min_deg, target_max_deg=a.target_max_deg,
                   rest_max_deg=a.rest_threshold_deg, hold_sec=t.min_hold_time_sec)

    @classmethod
    def from_dict(cls, raw, fallback=None):
        plan = fallback or cls()
        if isinstance(raw, dict):
            names = {f.name: f.type for f in fields(cls)}
            values = {}
            for key, value in raw.items():
                if key not in names:
                    continue
                default = getattr(plan, key)
                try:
                    if isinstance(default, bool):
                        value = value is True
                    elif isinstance(default, int) and key in PLAN_BOUNDS:
                        value = int(value)
                    elif isinstance(default, float):
                        value = float(value)
                    elif key == "arm":
                        value = value if value in ("right", "left") else None
                    else:
                        value = str(value or "")
                except (TypeError, ValueError):
                    continue
                values[key] = value
            plan = replace(plan, **values)
        return plan.clamped()

    def clamped(self):
        """The plan with every value inside its bounds and the thresholds in a valid order."""
        values = {}
        for key, (low, high, _) in PLAN_BOUNDS.items():
            value = getattr(self, key)
            values[key] = type(value)(min(high, max(low, value)))
        if values["target_max_deg"] < values["target_min_deg"]:
            values["target_max_deg"] = values["target_min_deg"]
        # The rise threshold (rest + 7 deg) must stay below the target.
        values["rest_max_deg"] = min(values["rest_max_deg"], values["target_min_deg"] - 8)
        values["pain_gentle_max"] = max(values["pain_gentle_max"], values["pain_go_max"])
        return replace(self, **values, notes=str(self.notes)[:200])

    def apply(self, config):
        """The configuration with this plan's thresholds (rest, rise, target, hold)."""
        a, t = config.abduction, config.timing
        rest = self.rest_max_deg
        abduction = replace(a, rest_threshold_deg=rest, rising_start_deg=rest + 7.,
                            target_min_deg=self.target_min_deg, target_max_deg=self.target_max_deg,
                            overshoot_warn_deg=min(180., max(a.overshoot_warn_deg, self.target_max_deg + 10.)))
        return replace(config, abduction=abduction, timing=replace(t, min_hold_time_sec=self.hold_sec))

    def gentle(self):
        """The plan for a gentle session (pain in the middle band): target max 10 deg lower."""
        top = max(PLAN_BOUNDS["target_max_deg"][0], self.target_max_deg - 10)
        return replace(self, target_max_deg=top, target_min_deg=min(self.target_min_deg, top)).clamped()

    def pain_band(self, pain):
        """"go", "gentle" or "stop" for a pain score from 0 to 10."""
        if pain <= self.pain_go_max:
            return "go"
        return "gentle" if pain <= self.pain_gentle_max else "stop"

    @property
    def total_reps(self):
        return self.reps_per_set * self.sets


def data_dir():
    override = os.environ.get("MOUVEMENT_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "Mouvement"
    return Path.home() / ".mouvement"


def profile_path():
    return data_dir() / "profile.json"


@dataclass
class Profile:
    language: str | None = None     # "en" or "fr"; None until the patient picks one
    tour_done: bool = False         # set after the first guided movements, or when the tour is skipped
    name: str = ""                  # optional first name, only used by Willy's lines
    arm: str | None = None          # "right" or "left"
    avatar_gender: str | None = None
    audio_enabled: bool = True
    seen: list = field(default_factory=list)          # once-only lines already played (Scenario 8)
    session_days: list = field(default_factory=list)  # ISO dates with at least one movement, oldest first
    last_correct: int | None = None                   # spot-on movements in the last session
    total_reps: int = 0             # movements counted since the start (Phase 10.3, the 100 badge)
    badges: dict = field(default_factory=dict)        # badges earned (src.motivation): {id: ISO date}
    badges_pending: list = field(default_factory=list)  # earned, still to be celebrated by Willy
    exercise: str = "abduction"     # the exercise the physio chose (config/exercises/<id>.yaml)
    plans: dict = field(default_factory=dict)         # the physio's plan for each exercise: {id: Plan as a dict}
    plan_history: list = field(default_factory=list)  # earlier plans: [{"until": iso, "plan": {...}}]
    schema_version: int = SCHEMA_VERSION
    pin_salt: str = ""              # physio PIN: salt and PBKDF2 hash (src.physio_settings); empty = 0000
    pin_hash: str = ""
    resting_angle: float | None = None  # resting abduction measured at the last calibration (deg)
    resting_date: str = ""          # ISO date of that measurement
    rest_warning: bool = False      # resting too close to the target: the plan's thresholds were kept
    camera_index: int | None = None # camera chosen in the physio settings (None: the configured one)
    pose_model: str | None = None   # "full" or "lite" forced by the physio; None = automatic
    chattiness: str = "normal"      # how much Willy talks: "lots", "normal" or "little" (Phase 9.5)
    large_text: bool = False        # accessibility (Phase 10.2): text x1.25
    high_contrast: bool = False     #   every text at least 7:1 against its background
    slow_speech: bool = False       #   Willy speaks 20% slower
    subtitles: bool = False         #   every line Willy says also shows in his bubble
    auto_lite: bool = False         # the app switched to lite by itself because the PC was too slow

    @classmethod
    def load(cls, path=None):
        path = Path(path) if path else profile_path()
        profile = cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        if isinstance(raw, dict):
            for key, value in raw.items():
                if key in cls.__dataclass_fields__:
                    setattr(profile, key, value)
        profile.language = profile.language if profile.language in ("en", "fr") else None
        profile.arm = profile.arm if profile.arm in ("right", "left") else None
        profile.avatar_gender = profile.avatar_gender if profile.avatar_gender in ("male", "female") else None
        profile.name = str(profile.name or "")[:24]
        profile.seen = [str(x) for x in profile.seen] if isinstance(profile.seen, list) else []
        days = profile.session_days if isinstance(profile.session_days, list) else []
        profile.session_days = sorted({d for d in days if _parse(d) is not None})[-MAX_DAYS:]
        # Version 1 profiles (before plans) simply have no plan yet: defaults apply. Version 2 had
        # one plan, for the exercise it names: it becomes that exercise's plan.
        plans = profile.plans if isinstance(profile.plans, dict) else {}
        if isinstance(raw, dict) and isinstance(raw.get("plan"), dict):
            plans.setdefault(str(raw["plan"].get("exercise") or "abduction"), raw["plan"])
        profile.plans = {str(key): asdict(replace(Plan.from_dict(value, Plan(exercise=str(key))), exercise=str(key)))
                         for key, value in plans.items() if isinstance(value, dict)}
        profile.exercise = str(profile.exercise or "abduction")
        history = profile.plan_history if isinstance(profile.plan_history, list) else []
        profile.plan_history = [h for h in history if isinstance(h, dict)][-MAX_PLAN_HISTORY:]
        profile.schema_version = SCHEMA_VERSION
        if not isinstance(profile.resting_angle, (int, float)) or isinstance(profile.resting_angle, bool):
            profile.resting_angle = None
        profile.resting_date = str(profile.resting_date or "") if _parse(profile.resting_date) else ""
        profile.rest_warning = profile.rest_warning is True
        profile.pose_model = profile.pose_model if profile.pose_model in ("full", "lite") else None
        profile.auto_lite = profile.auto_lite is True
        profile.chattiness = profile.chattiness if profile.chattiness in ("lots", "normal", "little") else "normal"
        for name in ("large_text", "high_contrast", "slow_speech", "subtitles"):
            setattr(profile, name, getattr(profile, name) is True)
        total = profile.total_reps
        profile.total_reps = total if isinstance(total, int) and not isinstance(total, bool) and total >= 0 else 0
        badges = profile.badges if isinstance(profile.badges, dict) else {}
        profile.badges = {str(k): str(v) for k, v in badges.items()}
        pending = profile.badges_pending if isinstance(profile.badges_pending, list) else []
        profile.badges_pending = [str(b) for b in pending if str(b) in profile.badges]
        camera = profile.camera_index
        profile.camera_index = camera if isinstance(camera, int) and not isinstance(camera, bool) and 0 <= camera <= 9 else None
        profile._path = path
        return profile

    # ------------------------------------------------------------------ the physio's plan
    def current_plan(self, config, exercise="abduction"):
        """The saved plan of this exercise, or the default one from the configuration."""
        default = Plan.from_config(config, exercise)
        saved = self.plans.get(exercise)
        return replace(Plan.from_dict(saved, default), exercise=exercise) if saved else default

    def set_plan(self, plan, now=None):
        """Save a new plan for its exercise; the previous one goes to the history (last 20 kept)."""
        stamp = (now or dt.datetime.now()).isoformat(timespec="seconds")
        previous = self.plans.get(plan.exercise)
        if previous:
            self.plan_history = (self.plan_history + [{"until": stamp, "plan": dict(previous)}])[-MAX_PLAN_HISTORY:]
        self.plans[plan.exercise] = asdict(replace(plan.clamped(), updated_at=stamp))

    def accessibility(self):
        from src.accessibility import Accessibility
        return Accessibility(self.large_text, self.high_contrast, self.slow_speech, self.subtitles)

    def save(self):
        """Best effort: a profile that cannot be written never stops the exercise."""
        path = getattr(self, "_path", None) or profile_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".profile-", suffix=".json")
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                json.dump(asdict(self), file, ensure_ascii=False, indent=2)
            os.replace(temporary, path)
            return True
        except OSError as error:
            print(f"[PROFIL] Impossible d'enregistrer le profil : {error}")
            return False

    # ------------------------------------------------------------------ once-only lines
    def has_seen(self, line_id):
        return line_id in self.seen

    def mark_seen(self, line_id):
        """True the first time; the line is then remembered so it never plays again."""
        if line_id in self.seen:
            return False
        self.seen.append(line_id)
        return True

    # ------------------------------------------------------------------ sessions
    def record_session(self, correct, day=None, reps=0):
        day = (day or dt.date.today()).isoformat()
        self.session_days = sorted(set(self.session_days) | {day})[-MAX_DAYS:]
        self.last_correct = int(correct)
        self.total_reps += max(0, int(reps))

    def last_day(self):
        return _parse(self.session_days[-1]) if self.session_days else None

    def done_today(self, today=None):
        return (today or dt.date.today()).isoformat() in self.session_days

    def days_since_last(self, today=None):
        """Days since the last session before today, or None when there was none."""
        today = today or dt.date.today()
        earlier = [d for d in (_parse(x) for x in self.session_days) if d is not None and d < today]
        return (today - max(earlier)).days if earlier else None

    def streak(self, today=None):
        """Consecutive days with a session, ending yesterday (or today if one is already done)."""
        today = today or dt.date.today()
        days = {_parse(x) for x in self.session_days}
        day = today if today in days else today - dt.timedelta(days=1)
        count = 0
        while day in days:
            count += 1
            day -= dt.timedelta(days=1)
        return count


def _parse(value):
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        return None
