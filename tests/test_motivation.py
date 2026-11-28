"""Phase 10.3: the week's sessions as dots, and gentle badges Willy celebrates once."""
import datetime as dt

from src import motivation
from src.dashboard import _Painter
from src.home_screen import render_home
from src.results_screen import render_history
from src.user_profile import Profile
from src.willy_lines import WillyScript
from tests.test_willy_tour import Harness

WEDNESDAY = dt.date(2026, 11, 25)


def days(*offsets, start=WEDNESDAY):
    return [(start + dt.timedelta(days=o)).isoformat() for o in offsets]


def test_the_week_counts_days_with_a_session_from_monday():
    assert motivation.week_progress(days(-2, -1, 0), 5, WEDNESDAY) == (3, 5)  # Monday to Wednesday
    assert motivation.week_progress(days(-3, -1), 5, WEDNESDAY) == (1, 5)     # last Sunday is another week
    assert motivation.week_progress(days(0, 0), 3, WEDNESDAY) == (1, 3)      # one day counts once
    assert motivation.week_progress([], 12, WEDNESDAY) == (0, 7)             # at most a session a day


def test_badge_rules():
    assert motivation.earned([], 0, 5) == set()
    assert motivation.earned(days(0), 3, 5) == {"first_session"}
    assert "three_days" in motivation.earned(days(-2, -1, 0), 10, 5)
    assert "three_days" not in motivation.earned(days(-4, -2, 0), 10, 5)       # gaps: no blame, just not yet
    assert "full_week" in motivation.earned(days(-2, -1, 0), 10, 3)            # Mon, Tue, Wed with a goal of 3
    assert "full_week" not in motivation.earned(days(-4, -3, 0), 10, 3)        # Fri, Sat, then Wed: two weeks
    assert "hundred_reps" in motivation.earned(days(0), 100, 5)
    assert "hundred_reps" not in motivation.earned(days(0), 99, 5)


def test_a_badge_is_earned_once_and_never_taken_back(tmp_path):
    profile = Profile.load(tmp_path / "profile.json")
    profile.session_days, profile.total_reps = days(-2, -1, 0), 120
    assert motivation.award(profile, 3, WEDNESDAY) == ["first_session", "three_days", "full_week", "hundred_reps"]
    assert profile.badges["three_days"] == WEDNESDAY.isoformat() and len(profile.badges_pending) == 4
    profile.save()
    again = Profile.load(tmp_path / "profile.json")
    assert again.badges == profile.badges and again.badges_pending == profile.badges_pending
    again.session_days, again.total_reps = [], 0  # days age out of the profile: badges stay
    assert motivation.award(again, 3, WEDNESDAY) == [] and len(again.badges) == 4


def test_the_badge_lines_only_celebrate():
    script = WillyScript()
    for line_id in motivation.BADGE_LINES.values():
        assert script.anim(line_id) == "cheer"
        for language in ("fr", "en"):
            text = script.text(line_id, language).lower()
            assert not any(word in text for word in ("manqu", "oubli", "retard", "missed", "forgot", "late", "only"))


class FakeSession:
    def __init__(self, total):
        self.total_repetitions = self.assessed_repetitions = total
        self.correct_repetitions = total
        self.evaluations = []


def test_willy_celebrates_a_new_badge_at_the_end_of_the_session_once(tmp_path):
    h = Harness(tmp_path, language="fr", tour_done=True, seen=["S8.05"])
    d = h.director
    d.screen, h.mode = "dashboard", "finished"
    d._start_episode(d._session_end(FakeSession(4)))
    said = []
    for _ in range(400):
        if h.line and (not said or said[-1] != h.line):
            said.append(h.line)
        h.frame()
    assert "E6.12" in said and h.profile.badges == {"first_session": dt.date.today().isoformat()}
    assert h.profile.badges_pending == [] and h.profile.total_reps == 4
    d._session_recorded = False
    d._start_episode(d._session_end(FakeSession(3)))
    again = []
    for _ in range(400):
        if h.line and (not again or again[-1] != h.line):
            again.append(h.line)
        h.frame()
    assert "E6.12" not in again and h.profile.total_reps == 7


def _texts(monkeypatch):
    drawn = []
    original = _Painter.put

    def put(self, point, text, font, color):
        drawn.append(text)
        return original(self, point, text, font, color)
    monkeypatch.setattr(_Painter, "put", put)
    return drawn


def test_the_home_screen_shows_the_weeks_dots(monkeypatch, tmp_path):
    h = Harness(tmp_path, language="fr", tour_done=True)
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    h.profile.session_days = sorted({monday.isoformat(), today.isoformat()})
    h.director.weekly_goal = 4
    h.director.open()
    h.run(1.)
    drawn = _texts(monkeypatch)
    render_home(h.director, None, (1280, 840))
    assert "Cette semaine" in drawn and f"{len(h.profile.session_days)}/4" in drawn


def test_the_history_shows_the_badges(monkeypatch):
    drawn = _texts(monkeypatch)
    render_history([], (1280, 840), "en", badges=("hundred_reps", "first_session"))
    assert "First session" in drawn and "100 movements" in drawn
    assert drawn.index("First session") > drawn.index("100 movements")  # drawn right to left, in badge order


def test_no_dots_during_the_tour(monkeypatch, tmp_path):
    h = Harness(tmp_path)
    h.director.open()
    h.run(.5)
    drawn = _texts(monkeypatch)
    render_home(h.director, None, (1280, 840))
    assert "Cette semaine" not in drawn and "This week" not in drawn
