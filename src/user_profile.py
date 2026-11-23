"""The patient's small local profile: language, first-use tour, a few choices and session days.

It stays on this computer (no network): %APPDATA%\\Mouvement\\profile.json on Windows and
~/.mouvement/profile.json elsewhere. MOUVEMENT_DATA_DIR points it somewhere else (tests).
No video, image or measurement is stored here.
"""
from dataclasses import asdict, dataclass, field
import datetime as dt
import json
import os
from pathlib import Path
import sys
import tempfile

MAX_DAYS = 60


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
        profile._path = path
        return profile

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
    def record_session(self, correct, day=None):
        day = (day or dt.date.today()).isoformat()
        self.session_days = sorted(set(self.session_days) | {day})[-MAX_DAYS:]
        self.last_correct = int(correct)

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
