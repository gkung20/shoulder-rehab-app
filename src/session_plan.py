"""Sets of a session, from the physio's plan: reps per set, rest between sets, end of the plan.

`SetTracker` is plain logic (no drawing, no voice): the app feeds it each counted movement
and the clock, and asks what to show and when the session is complete.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SetTracker:
    reps_per_set: int = 10
    sets: int = 3
    rest_sec: float = 60.
    current_set: int = 1
    reps_in_set: int = 0
    rest_until: float | None = None   # set while resting between two sets
    rest_over: bool = False           # the rest ended: waiting for the patient to resume
    done: bool = False

    @classmethod
    def from_plan(cls, plan, gentle=False):
        """The sets of a plan. A gentle session (pain 4-6) has 30% fewer reps per set."""
        reps = plan.reps_per_set
        if gentle:
            reps = max(1, round(reps * .7))
        return cls(reps_per_set=reps, sets=plan.sets, rest_sec=float(plan.rest_between_sets_sec))

    @property
    def resting(self):
        return self.rest_until is not None

    @property
    def waiting(self):
        """Between two sets (resting, or rested and waiting for the patient)."""
        return self.resting or self.rest_over

    @property
    def is_last_set(self):
        return self.current_set >= self.sets

    @property
    def total_done(self):
        return (self.current_set - 1) * self.reps_per_set + self.reps_in_set

    def add_rep(self, now):
        """A counted movement: "rep", "set_done" (rest starts) or "plan_done"."""
        if self.done or self.waiting:
            return "rep"
        self.reps_in_set += 1
        if self.reps_in_set < self.reps_per_set:
            return "rep"
        if self.is_last_set:
            self.done = True
            return "plan_done"
        self.rest_until = now + self.rest_sec
        return "set_done"

    def rest_left(self, now):
        return 0. if self.rest_until is None else max(0., self.rest_until - now)

    def tick(self, now):
        """"rest_over" once, when the rest between sets ends; otherwise None."""
        if self.rest_until is not None and now >= self.rest_until:
            self.rest_until, self.rest_over = None, True
            return "rest_over"
        return None

    def next_set(self):
        """The patient resumes: the next set starts (even before the end of the rest)."""
        if not self.waiting:
            return False
        self.current_set += 1
        self.reps_in_set, self.rest_until, self.rest_over = 0, None, False
        return True
