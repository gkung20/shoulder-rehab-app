"""Motivation without guilt (Phase 10.3): the week's sessions as dots, and a few gentle badges.

Everything here counts what the patient did, never what they missed: a day without a session
takes nothing away, a badge once earned stays, and Willy's words only celebrate.

Badges (each celebrated once, at the end of the session that earns it):
- first_session: the first session with at least one movement;
- three_days: sessions on three days in a row;
- full_week: the plan's weekly goal reached in one week (Monday to Sunday; at most 7 days count);
- hundred_reps: a hundred movements since the start.
"""
from __future__ import annotations

import datetime as dt

BADGES = ("first_session", "three_days", "full_week", "hundred_reps")
BADGE_LINES = {"first_session": "E6.12", "three_days": "E6.13", "full_week": "E6.14", "hundred_reps": "E6.15"}
BADGE_NAMES = {"first_session": "Première séance", "three_days": "3 jours de suite",
               "full_week": "Semaine complète", "hundred_reps": "100 mouvements"}
MAX_DAYS_A_WEEK = 7


def _days(session_days):
    days = set()
    for value in session_days or ():
        try:
            days.add(dt.date.fromisoformat(str(value)))
        except ValueError:
            continue
    return sorted(days)


def weekly_goal(goal):
    """The plan's sessions per week, as days: between 1 and 7."""
    return max(1, min(MAX_DAYS_A_WEEK, int(goal or 1)))


def week_progress(session_days, goal, today=None):
    """(days with a session this week, the week's goal in days); the week starts on Monday."""
    today = today or dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    done = sum(monday <= day <= today for day in _days(session_days))
    return done, weekly_goal(goal)


def longest_run(session_days):
    """The most consecutive days with a session."""
    best = run = 0
    previous = None
    for day in _days(session_days):
        run = run + 1 if previous is not None and (day - previous).days == 1 else 1
        best, previous = max(best, run), day
    return best


def earned(session_days, total_reps, goal):
    """Every badge these facts earn."""
    days = _days(session_days)
    badges = set()
    if days:
        badges.add("first_session")
    if longest_run(days) >= 3:
        badges.add("three_days")
    weeks = {}
    for day in days:
        week = day.isocalendar()[:2]
        weeks[week] = weeks.get(week, 0) + 1
    if any(count >= weekly_goal(goal) for count in weeks.values()):
        badges.add("full_week")
    if total_reps >= 100:
        badges.add("hundred_reps")
    return badges


def award(profile, goal, today=None):
    """New badges of the profile: kept with their date and queued for Willy to celebrate."""
    today = (today or dt.date.today()).isoformat()
    new = [badge for badge in BADGES
           if badge in earned(profile.session_days, profile.total_reps, goal) and badge not in profile.badges]
    for badge in new:
        profile.badges[badge] = today
        profile.badges_pending.append(badge)
    return new
