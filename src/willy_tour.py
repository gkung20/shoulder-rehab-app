"""Willy's director: the home screen, the first-use tour and the lines around each session.

The tour follows the doc "Willy: onboarding scenarios and lines (EN/FR)". Each scenario is a
generator that yields what it waits for (a button, the end of a sentence, an action in the app,
the next frame), so the script reads in the same order as the doc. Live cues and movement
results stay with AudioCoach; the director adds the moments around them (pause, finish,
milestones) and keeps Willy's bubble, spotlight and gestures in step with what he says.
"""
from dataclasses import dataclass, field
import datetime as dt
import math
import time

from src.cues import Cue, code_of
from src import layout as L
from src.i18n import ui
from src.willy import exercise_screen_side
from src.willy_lines import Line, most_frequent_tip, reading_seconds, result_line, shared_script
from src.willy_overlay import Overlay, TourButton

# Dashboard zones (logical 1280 x 840 coordinates) that the tour lights up.
ZONES = dict(L.TOUR_ZONES)  # spotlight rectangles, from src.layout

SCREEN_TOUR = (("S5.01", None), ("S5.02", "top_bar"), ("S5.03", "arm_buttons"), ("S5.04", "coach_panel"),
               ("S5.05", "patient_panel"), ("S5.06", "camera_thumbnail"), ("S5.07", "view_button"),
               ("S5.08", "guidance"), ("S5.09", "counter"), ("S5.10", "progress"), ("S5.11", "steps"),
               ("S5.12", "result_line"), ("S5.13", "main_button"), ("S5.14", "finish_button"),
               ("S5.15", "details_button"), ("S5.16", "help_button"), ("S5.17", "close_button"),
               ("S5.18", "willy"), ("S5.19", None))
AVATAR_ONLY = ("S5.04", "S5.05", "S5.06")

# The silhouette's placement advice -> Scenario 4 line and option.
PLACEMENT_LINES = {
    "Approchez-vous un peu": ("S4.05", 0), "Reculez un peu": ("S4.06", 0),
    "Décalez-vous vers la gauche": ("S4.07", 0), "Décalez-vous vers la droite": ("S4.07", 1),
    "Montez un peu la caméra": ("S4.08", 0), "Baissez un peu la caméra": ("S4.08", 1),
}

# Tour actions that never reach the session controls.
TOUR_ACTIONS = ("next", "skip", "start_tour", "understand", "watch_again", "lang_en", "lang_fr",
                "name_ok", "skip_name", "home_start")
ALWAYS_ALLOWED = ("quit", "language")
TRACKED = ("SUIVI ACTIF", "MESURES PARTIELLES", "CADRAGE SERRE")


@dataclass
class Moment:
    """What the director needs to know about this frame."""
    now: float
    mode: str = "ready"
    analysis: object = None
    processor: object = None
    alignment: tuple | None = None
    mirror: bool = True
    audio_enabled: bool = True


@dataclass
class _Speech:
    gap: float = .45


@dataclass
class _Choice:
    actions: tuple


@dataclass
class _Frame:
    pass


@dataclass
class _Sleep:
    seconds: float
    since: float = None


@dataclass
class _Said:
    """The line in Willy's bubble."""
    line_id: str
    texts: list
    anim: str
    started: float
    spoken: bool
    buttons: list = field(default_factory=list)
    spotlight: tuple | None = None
    highlight: str | None = None
    text_field: bool = False
    sample: str | None = None
    compact: bool = False
    expires: float | None = None
    values: dict = field(default_factory=dict)
    bilingual: bool = False


def part_of_day(now=None):
    hour = (now or dt.datetime.now()).hour
    return 0 if hour < 12 else 1 if hour < 18 else 2


def _demo_curve(t, hold=1.):
    """The demo movement at the tempo Willy teaches: 2 s up, a short hold, 2 s down, 1 s rest."""
    up, down, rest = 2., 2., 1.
    t %= up + hold + down + rest
    if t < up:
        return 90. * (.5 - .5 * math.cos(math.pi * t / up))
    if t < up + hold:
        return 90.
    if t < up + hold + down:
        return 90. * (.5 + .5 * math.cos(math.pi * (t - up - hold) / down))
    return 0.


class WillyDirector:
    def __init__(self, profile, audio, guide=None, script=None, has_avatars=True, clock=time.monotonic):
        self.profile = profile
        self.audio = audio
        self.guide = guide
        self.script = script or shared_script()
        self.has_avatars = has_avatars
        self.clock = clock
        self.language = profile.language or "fr"
        self.screen = "home"
        self.overlay = Overlay()
        self.current = None
        self.name_buffer = ""
        self.typing = False
        self.wants_tracking = False      # Scenario 4: the app runs the pose model for placement only
        self.want_avatars = None         # True/False: the view the tour needs; None: the patient's choice
        self.want_silhouette = None
        self.allowed = None              # session actions allowed during a tour step (None: all)
        self.coaching = False            # Scenario 7: the tour speaks the first movements itself
        self.in_tour = False
        self.results_available = False  # a saved session exists: "Mes résultats" on the home screen
        self.closing_until = None
        self._gen = None
        self._wait = None
        self._pressed = None
        self._demo = None                # (start time, kind) of Willy's demo movement
        self._episode = None             # a sequence of everyday lines (end of session)
        self._last_mode = None
        self._last_reps = 0
        self._correct_run = 0
        self._paused_at = None
        self._idle_since = None
        self._idle_said = False
        self._audio_seen_at = float("-inf")
        self._voice_warned = False
        self._session_recorded = False
        self.ctx = Moment(clock())

    # ------------------------------------------------------------------ opening
    def open(self):
        """The first screen: Willy's home. First use starts the tour; afterwards a greeting."""
        self.screen = "home"
        if not self.profile.tour_done:
            self._start(self._first_use(replay=False))
        else:
            self._start(self._returning_home())

    # ------------------------------------------------------------------ sets of the plan
    def set_done(self, number):
        """A set ended: Willy calms down for the rest between sets (no pause lines meanwhile)."""
        self._set_rest = True
        self.say("E6.09", n=number, compact=True)

    def rest_over(self, next_number):
        self.say("E6.10", n=next_number, spotlight="main_button", compact=True)

    def set_started(self, number, last):
        self._set_rest = False
        if last:
            self.say("E6.11", compact=True)

    def hurt_pressed(self):
        """'J'ai mal': the pause that follows is not an ordinary pause (no pause lines)."""
        self._set_rest = True

    def rest_done(self):
        self._set_rest = False

    def plan_done(self):
        """The last set is done: the session-end lines start with E6.03 (goal reached)."""
        self._goal_reached = True

    def plan_updated(self):
        """Back from the physio settings after a change: Willy confirms, then his Start button."""
        self.screen = "home"
        self._stop_episode()
        self._start(self._plan_updated())

    def _plan_updated(self):
        self.in_tour = False
        self.allowed = None
        self.say("E8.01")
        yield _Speech()
        self.current.buttons = [TourButton("home_start", ui("start", self.language), True)]
        yield _Choice(("home_start",))
        self.screen = "dashboard"
        self.current = None

    def replay_tour(self):
        self.screen = "home"
        self._stop_episode()
        self._start(self._first_use(replay=True))

    # ------------------------------------------------------------------ actions
    def permits(self, action):
        """May the session controls apply this action now? Tour buttons never reach them."""
        if action in TOUR_ACTIONS:
            return False
        if action in ALWAYS_ALLOWED or self.allowed is None:
            return True
        return action in self.allowed

    def notify(self, action):
        """A button was pressed (tour button, or a session action already applied by the app)."""
        now = self.clock()
        if action == "language":
            self.set_language("fr" if self.language == "en" else "en", announce=True)
            return
        if action == "replay_tour":
            self.replay_tour()
            return
        if action == "quit":
            self._goodbye(now)
            return
        if action == "audio":
            self._sound_toggled()
        if action in ("arm_left", "arm_right"):
            self.profile.arm = "left" if action == "arm_left" else "right"
            self.profile.save()
        if action in ("avatar_male", "avatar_female"):
            self.profile.avatar_gender = action.removeprefix("avatar_")
            self.profile.save()
        if isinstance(self._wait, (_Choice, _Frame)):
            self._pressed = action

    def type_key(self, key):
        """A key while the name field is open: letters, space, hyphen, apostrophe, Backspace, Enter, Esc."""
        if not self.typing:
            return False
        if key in (13, 10):
            self.notify("name_ok")
        elif key == 27:
            self.notify("skip_name")
        elif key == 8:
            self.name_buffer = self.name_buffer[:-1]
        elif 32 <= key < 127 or 192 <= key < 255:
            char = chr(key)
            if (char.isalpha() or char in " -'") and len(self.name_buffer) < 20:
                self.name_buffer += char
        return True

    def primary_action(self):
        """Enter or Space: the main button of the current step, if any."""
        if self.current is None:
            return None
        primary = [button.action for button in self.current.buttons if button.primary]
        return primary[0] if len(primary) == 1 else None  # two equal choices (the languages): no default

    # ------------------------------------------------------------------ language
    def set_language(self, language, announce=False):
        if language not in ("en", "fr"):
            return
        changed = language != self.language
        self.language = language
        self.profile.language = language
        self.profile.save()
        if hasattr(self.audio, "set_language"):
            self.audio.set_language(language)
        if not (announce and changed):
            return
        current = self.current
        if current is not None and not current.compact and not current.bilingual:
            # Say the line again in the new language, so the patient never loses the thread.
            self.say(current.line_id, buttons=current.buttons, spotlight=current.spotlight,
                     highlight=current.highlight, text_field=current.text_field, sample=current.sample,
                     **current.values)
        elif current is None or current.compact:
            self.say("E1.05", compact=self.screen == "dashboard")

    # ------------------------------------------------------------------ saying
    def _values(self, values):
        merged = {"name": self.profile.name}
        merged.update(values)
        return merged

    def _audio_say(self, text, language, interrupt=True):
        say = getattr(self.audio, "say", None)
        if say is None:
            return False
        try:
            return say(text, language, interrupt=interrupt) is True
        except TypeError:
            return False

    def say(self, line_id, *, buttons=None, spotlight=None, highlight=None, text_field=False, sample=None,
            compact=False, bilingual=False, interrupt=True, **values):
        """Willy says a line: bubble, voice and gesture together."""
        now = self.clock()
        values = self._values(values)
        if bilingual:
            texts = [self.script.text(line_id, "en", **values), self.script.text(line_id, "fr", **values)]
            spoken = self._audio_say(texts[0], "en", interrupt)
            spoken = self._audio_say(texts[1], "fr", False) or spoken
        else:
            texts = [self.script.text(line_id, self.language, **values)]
            spoken = self._audio_say(texts[0], self.language, interrupt)
        anim = self.script.anim(line_id)
        if isinstance(spotlight, str):
            spotlight = ZONES[spotlight]
        expires = None
        if compact or (self.coaching and not buttons):
            expires = now + sum(reading_seconds(t) for t in texts) + 1.8
        self.current = _Said(line_id, texts, anim, now, spoken, list(buttons or []), spotlight, highlight,
                             text_field, sample, compact, expires, {k: v for k, v in values.items() if k != "name"},
                             bilingual)
        if self.guide is not None:
            self.guide.perform(anim, now)
        return self.current

    def _speech_done(self, now):
        current = self.current
        if current is None:
            return True
        elapsed = now - current.started
        reading = sum(reading_seconds(text) for text in current.texts)
        busy = getattr(self.audio, "busy", False) is True
        if current.spoken:
            return (elapsed > .8 and not busy) or elapsed > reading * 2.5 + 4.
        return elapsed >= reading

    # ------------------------------------------------------------------ scenario engine
    def _start(self, generator):
        self._gen, self._wait, self._pressed = generator, None, None
        self._advance(None)

    def _advance(self, value):
        try:
            self._wait = self._gen.send(value) if self._wait is not None or value is not None else next(self._gen)
            if isinstance(self._wait, _Speech):
                self._wait.since = None
            if isinstance(self._wait, _Sleep):
                self._wait.since = self.clock()
        except StopIteration:
            self._gen, self._wait = None, None

    def _resolve(self, now):
        wait = self._wait
        if isinstance(wait, _Choice):
            if self._pressed in wait.actions:
                pressed, self._pressed = self._pressed, None
                return pressed
            return _PENDING
        if isinstance(wait, _Frame):
            pressed, self._pressed = self._pressed, None
            return pressed or self.ctx
        if isinstance(wait, _Sleep):
            return True if now - wait.since >= wait.seconds else _PENDING
        if isinstance(wait, _Speech):
            if not self._speech_done(now):
                return _PENDING
            if wait.since is None:
                wait.since = now
            return True if now - wait.since >= wait.gap else _PENDING
        return True

    def update(self, ctx):
        """Advance the tour or the everyday lines by one frame."""
        self.ctx = ctx
        now = ctx.now
        if self._gen is not None:
            for _ in range(12):
                if self._gen is None:
                    break
                frame_wait = isinstance(self._wait, _Frame)
                value = self._resolve(now)
                if value is _PENDING:
                    break
                self._advance(value)
                if frame_wait:
                    break
        if self.screen == "dashboard":
            self._everyday(ctx)
        self._tick_demo(now)
        self._build_overlay(now)

    # ------------------------------------------------------------------ Scenario 1-2: home
    def _first_use(self, replay):
        self.in_tour = True
        self.screen = "home"
        self.want_avatars = self.want_silhouette = None
        skipped = False
        if self.profile.language is None:
            self.say("S1.01", bilingual=True)
            yield _Speech()
            self.say("S1.02", bilingual=True, buttons=[TourButton("lang_en", "English", True),
                                                       TourButton("lang_fr", "Français", True)])
            choice = yield _Choice(("lang_en", "lang_fr"))
            self.set_language("en" if choice == "lang_en" else "fr")
            self.say("S1.03")
            yield _Speech()
        else:
            self.say("S1.01")
            yield _Speech()
        if replay:
            self.say("S1.08")
            yield _Speech()
        else:
            self.say("S1.04")
            yield _Speech()
            self.say("S1.05")
            yield _Speech()
            self.say("S1.06", buttons=[TourButton("skip", ui("skip", self.language)),
                                       TourButton("start_tour", ui("start_tour", self.language), True)])
            choice = yield _Choice(("start_tour", "skip"))
            skipped = choice == "skip"
            self.say("S1.07" if skipped else "S1.08")
            yield _Speech()
        yield from self._safety()
        if skipped:
            self._finish_tour()
            self.screen = "dashboard"
            self.current = None
            return
        self.screen = "dashboard"
        yield from self._profile_setup()
        yield from self._camera_setup()
        yield from self._screen_tour()
        yield from self._exercise_demo()
        yield from self._first_session()

    def _safety(self):
        self.allowed = ()
        for line_id in ("S2.01", "S2.02"):
            self.say(line_id)
            yield _Speech()
        self.say("S2.03", sample="pause")
        yield _Speech(gap=1.)
        for line_id in ("S2.04", "S2.05"):
            self.say(line_id)
            yield _Speech()
        self.say("S2.06", buttons=[TourButton("understand", ui("understand", self.language), True)])
        yield _Choice(("understand",))
        self.say("S2.07")
        yield _Speech()

    def _returning_home(self):
        self.in_tour = False
        self.allowed = None
        self.say("E1.01", choice=part_of_day())
        yield _Speech()
        extra, values = self._greeting_extra()
        if extra:
            self.say(extra, **values)
            yield _Speech()
        self.current.buttons = [TourButton("home_start", ui("start", self.language), True)]
        yield _Choice(("home_start",))
        self.screen = "dashboard"
        self.current = None

    def _greeting_extra(self):
        today = dt.date.today()
        if self.profile.done_today(today):
            return "E1.04", {}
        streak = self.profile.streak(today)
        if streak >= 3:
            return "E1.06", {"n": streak}
        since = self.profile.days_since_last(today)
        if since == 1:
            return "E1.02", {}
        if since is not None and since >= 3:
            return "E1.03", {}
        return None, {}

    # ------------------------------------------------------------------ Scenario 3: profile
    def _next(self):
        return [TourButton("next", ui("next", self.language), True)]

    def _profile_setup(self):
        self.allowed = ()
        self.want_avatars, self.want_silhouette = (True if self.has_avatars else None), False
        self.say("S3.01")
        yield _Speech()
        self.name_buffer = self.profile.name
        self.typing = True
        self.say("S3.02", text_field=True, buttons=[TourButton("skip_name", ui("skip", self.language)),
                                                    TourButton("name_ok", ui("ok", self.language), True)])
        choice = yield _Choice(("name_ok", "skip_name"))
        self.typing = False
        name = self.name_buffer.strip() if choice == "name_ok" else ""
        self.profile.name = name
        self.profile.save()
        self.say("S3.03", name=name)
        yield _Speech()
        self.allowed = ("arm_left", "arm_right")
        self.say("S3.04", spotlight="arm_buttons", buttons=self._next())
        yield _Choice(("arm_left", "arm_right", "next"))
        arm = getattr(self.ctx.processor, "arm", self.profile.arm or "right")
        self.allowed = ()
        self.say("S3.05", choice=0 if arm == "right" else 1)
        yield _Speech()
        self.allowed = ("avatar_male", "avatar_female")
        self.say("S3.06", spotlight="avatar_buttons", buttons=self._next())
        yield _Choice(("avatar_male", "avatar_female", "next"))
        self.allowed = ()
        self.say("S3.07", buttons=self._next())
        yield _Choice(("next",))
        self.allowed = ("audio",)
        self.say("S3.08", spotlight="sound_button", buttons=self._next())
        while True:
            pressed = yield _Choice(("audio", "next"))
            if pressed == "next":
                break
            if getattr(self.audio, "enabled", True) is False:
                self.say("S3.09", spotlight="sound_button", buttons=self._next())
            else:
                self.say("S3.08", spotlight="sound_button", buttons=self._next())
        self.allowed = ()
        self.say("S3.10")
        yield _Speech()

    # ------------------------------------------------------------------ Scenario 4: camera
    def _camera_setup(self):
        self.allowed = ("silhouette",)
        self.want_avatars, self.want_silhouette = False, True
        for line_id in ("S4.01", "S4.02", "S4.03"):
            self.say(line_id)
            yield _Speech()
        self.wants_tracking = True
        self.say("S4.04", buttons=self._next())
        unseen_since = self.clock()
        advice, advice_since, said_advice, said_at, warned = None, 0., None, self.clock(), False
        while True:
            ctx = yield _Frame()
            if ctx == "next":
                break
            if not isinstance(ctx, Moment):
                continue
            now, alignment = ctx.now, ctx.alignment
            if alignment is None:
                if now - unseen_since > 10 and not warned:
                    self.say("S4.11", buttons=self._next())
                    warned = True
                continue
            unseen_since = now
            if alignment[1] != advice:
                advice, advice_since = alignment[1], now
            if now - advice_since < 1.2 or not self._speech_done(now):
                continue
            if alignment[0]:
                self.say("S4.09", buttons=self._next())
                yield _Speech()
                break
            if advice in PLACEMENT_LINES and (advice != said_advice or now - said_at > 9) and now - said_at > 3.5:
                line_id, option = PLACEMENT_LINES[advice]
                self.say(line_id, choice=option, buttons=self._next())
                said_advice, said_at = advice, now
        self.wants_tracking = False
        self.say("S4.10", spotlight="silhouette_button", buttons=self._next())
        yield _Choice(("next",))

    # ------------------------------------------------------------------ Scenario 5: the screen
    def _screen_tour(self):
        self.allowed = ()
        self.want_avatars, self.want_silhouette = (True if self.has_avatars else None), False
        for line_id, zone in SCREEN_TOUR:
            if not self.has_avatars and line_id in AVATAR_ONLY:
                continue
            self.say(line_id, spotlight=zone, buttons=self._next())
            yield _Choice(("next",))

    # ------------------------------------------------------------------ Scenario 6: the movement
    def _exercise_demo(self):
        self.allowed = ()
        self._demo = (self.clock(), "rest")
        self.say("S6.01")
        yield _Speech()
        while True:
            yield from self._demo_steps()
            self.say("S6.13")
            yield _Speech()
            self.say("S6.14", spotlight="coach_panel" if self.has_avatars else None)
            yield _Speech()
            self.say("S6.15", buttons=[TourButton("watch_again", ui("watch_again", self.language)),
                                       TourButton("next", ui("next", self.language), True)])
            choice = yield _Choice(("watch_again", "next"))
            if choice == "next":
                break
        self._demo = None

    def _demo_steps(self):
        steps = (("S6.02", "rest", None), ("S6.03", "rise", None), ("S6.04", "up", "shoulder"),
                 ("S6.05", "up", "trunk"), ("S6.06", "up", "hand"), ("S6.07", "up", None), ("S6.08", "up", None),
                 ("S6.09", "lower", None), ("S6.10", "rest", None), ("S6.11", "loop", None), ("S6.12", "loop", None))
        for line_id, pose, highlight in steps:
            self._demo = (self.clock(), pose)
            side = self._demo_side()
            point = {"shoulder": f"shoulder_{side}", "hand": f"arm_{side}", "trunk": "trunk"}.get(highlight)
            self.say(line_id, highlight=point)
            yield _Speech(gap=.8 if pose == "loop" else .45)

    def _demo_side(self):
        arm = getattr(self.ctx.processor, "arm", None) or self.profile.arm or "right"
        return exercise_screen_side(arm, self.ctx.mirror)

    def _tick_demo(self, now):
        """Willy's arm during the demo: rest, a slow rise, the hold, a slow lowering, or the full loop."""
        big = self._demo is not None
        self.overlay.willy_big = big
        if self.guide is None or not big:
            return
        since, pose = self._demo
        t = now - since
        angle = {"rest": 0., "up": 90.,
                 "rise": 90. * min(1., .5 - .5 * math.cos(math.pi * min(t, 2.) / 2.)),
                 "lower": 90. * (.5 + .5 * math.cos(math.pi * min(t, 2.) / 2.)),
                 "loop": _demo_curve(t)}.get(pose, 0.)
        self.guide.demo_side = self._demo_side()
        self.guide.demo_angle = angle

    # ------------------------------------------------------------------ Scenario 7: first movements
    def _first_session(self):
        self.want_avatars = self.want_silhouette = None
        self.allowed = ("start",)
        self.say("S7.01", spotlight="main_button")
        yield _Choice(("start",))
        # The patient has seen the whole tour: closing during these first movements won't replay it.
        self.profile.tour_done = True
        self.profile.save()
        self.allowed = None
        self.coaching = True
        said, last = set(), {}
        calibrated = False

        def once(line_id, **values):
            if line_id in said:
                return False
            said.add(line_id)
            self.say(line_id, **values)
            return True

        def every(line_id, seconds, now):
            if now - last.get(line_id, -99.) < seconds:
                return False
            last[line_id] = now
            self.say(line_id)
            return True

        while True:
            ctx = yield _Frame()
            if not isinstance(ctx, Moment):
                continue
            now, analysis, processor = ctx.now, ctx.analysis, ctx.processor
            if ctx.mode == "finished":
                break
            if ctx.mode != "running" or analysis is None:
                continue
            status = getattr(analysis, "status", "")
            code = code_of(getattr(analysis, "cue", None))
            if status == "CALIBRATION":
                if code in (Cue.CAL_LOWER_ARM, Cue.CAL_MOVED):
                    every("S7.05", 8., now)
                elif once("S7.02"):
                    pass
                elif ("S7.03" not in said and self.current is not None and now - self.current.started > 3.
                      and self._speech_done(now)):
                    once("S7.03")
                continue
            if status == "EPAULES PRETES":
                every("S7.04", 8., now)
                continue
            if status in ("SUIVI PERDU", "POSITION A AJUSTER"):
                every("S7.06", 8., now)
                continue
            if status == "REPOS REQUIS":
                every("S7.05", 8., now)
                continue
            if status not in TRACKED:
                continue  # still looking for the patient: nothing to coach yet
            if not calibrated:
                calibrated = True
                once("S7.07")
                continue
            evaluation = getattr(analysis, "new_evaluation", None)
            reps = processor.rules_engine.session.total_repetitions if processor is not None else 0
            if evaluation is not None:
                index = evaluation.rep_index
                if index == 1:
                    if evaluation.status_label == "INDETERMINE":
                        self.say("S7.16")
                    elif evaluation.is_correct:
                        self.say("S7.14")
                    else:
                        tip = most_frequent_tip([evaluation]) or "E5.20"
                        self.say("S7.15", tip=self.script.text(tip, self.language))
                else:
                    line = result_line(self.script, evaluation, self.language)
                    self.say(line.id, **self._result_values(evaluation))
                if index >= 3:
                    yield _Speech()
                    self.say("S7.19")
                    self._finish_tour()
                    yield _Speech()
                    break
                continue
            if not self._speech_done(now):
                continue
            phase = getattr(getattr(analysis, "phase", None), "name", "")
            if reps == 0:
                if phase == "REST":
                    once("S7.08")
                elif phase == "RISING" and code == Cue.ALMOST_TARGET:
                    once("S7.10")
                elif phase == "RISING":
                    once("S7.09")
                elif phase == "HOLD" and code == Cue.HOLD_DONE_LOWER:
                    once("S7.12")
                elif phase == "HOLD":
                    once("S7.11")
                elif phase == "LOWERING":
                    once("S7.13")
            elif reps == 1 and phase == "RISING":
                once("S7.17")
            elif reps == 2 and phase == "RISING":
                once("S7.18")
        self.coaching = False
        self._finish_tour()

    def _result_values(self, evaluation):
        values = {"n": evaluation.rep_index}
        if not evaluation.is_correct and evaluation.status_label != "INDETERMINE":
            tip = most_frequent_tip([evaluation]) or "E5.20"
            values["tip"] = self.script.text(tip, self.language)
        return values

    def _finish_tour(self):
        self.in_tour = False
        self.allowed = None
        self.want_avatars = self.want_silhouette = None
        self.wants_tracking = False
        if not self.profile.tour_done:
            self.profile.tour_done = True
            self.profile.save()

    # ------------------------------------------------------------------ everyday lines (Scenario 8, E6, E7)
    def _once(self, line_id):
        if self.profile.has_seen(line_id):
            return False
        self.profile.mark_seen(line_id)
        self.profile.save()
        return True

    def _everyday(self, ctx):
        now, mode, processor = ctx.now, ctx.mode, ctx.processor
        previous, self._last_mode = self._last_mode, mode
        session = getattr(getattr(processor, "rules_engine", None), "session", None)
        reps = session.total_repetitions if session is not None else 0
        # A new session: forget the last one's counters.
        if mode == "ready" and previous not in (None, "ready"):
            self._last_reps, self._correct_run, self._session_recorded = 0, 0, False
            self._set_rest = self._goal_reached = self.pain_rose = False
            self._stop_episode()
        if self._episode is not None:
            self._run_episode(now)
        if self.in_tour and not self.coaching:
            return
        evaluation = getattr(ctx.analysis, "new_evaluation", None) if mode == "running" else None
        if evaluation is not None:
            self._idle_since, self._idle_said = now, False
            self._correct_run = self._correct_run + 1 if evaluation.is_correct else 0
            if not self.coaching:
                if self._correct_run == 3:
                    self.say("E6.02", compact=True, interrupt=False)
                elif evaluation.rep_index == 4 and self._once("S8.01"):
                    self.say("S8.01", spotlight="main_button", compact=True, interrupt=False)
                elif evaluation.rep_index == 8 and self._once("S8.04"):
                    self.say("S8.04", spotlight="finish_button", compact=True, interrupt=False)
        self._last_reps = reps
        # Pause, and a long pause.
        resting = getattr(self, "_set_rest", False)  # a rest between sets is not a pause
        if mode == "paused" and previous == "running" and not resting:
            self._paused_at = now
            if self._once("S8.02"):
                self.say("S8.02", compact=True)
        if (mode == "paused" and not resting and self._paused_at is not None and now - self._paused_at > 10
                and self._once("S8.03")):
            self.say("S8.03", spotlight="main_button", compact=True)
        if mode != "paused":
            self._paused_at = None
        # Still there? Once per quiet spell during a session.
        phase = getattr(getattr(ctx.analysis, "phase", None), "name", "")
        if mode == "running" and not self.coaching:
            if self._idle_since is None or phase not in ("REST", ""):
                self._idle_since, self._idle_said = now, False
            elif now - self._idle_since > 30 and not self._idle_said:
                self._idle_said = True
                self.say("E6.04", compact=True)
        else:
            self._idle_since = None
        # End of a session.
        if mode == "finished" and previous in ("running", "paused"):
            self._start_episode(self._session_end(session))
        # The voice failed: say so once, in the bubble.
        if getattr(self.audio, "available", None) is False and not self._voice_warned:
            self._voice_warned = True
            self.say("E6.07", compact=True)

    def _sound_toggled(self):
        if self.in_tour and not self.coaching:
            return  # the tour says its own lines about the sound (S3.08, S3.09)
        enabled = getattr(self.audio, "enabled", None)
        if enabled is True:
            self.say("E6.06", compact=True)
        elif enabled is False:
            self.say("E6.05", compact=True)

    def _start_episode(self, generator):
        self._episode = [generator, None]
        self._step_episode(None)

    def _stop_episode(self):
        self._episode = None

    def _step_episode(self, value):
        generator, _ = self._episode
        try:
            wait = generator.send(value) if value is not None else next(generator)
            if isinstance(wait, _Speech):
                wait.since = None
            self._episode[1] = wait
        except StopIteration:
            self._episode = None

    def _run_episode(self, now):
        for _ in range(4):
            if self._episode is None:
                return
            wait = self._episode[1]
            if isinstance(wait, _Speech):
                if not self._speech_done(now):
                    return
                if wait.since is None:
                    wait.since = now
                if now - wait.since < wait.gap:
                    return
            self._step_episode(True)

    def _session_end(self, session):
        """Every session ends with S8.05 to S8.09; the first one also shows where the results are."""
        if session is None:
            return
        if getattr(self, "_goal_reached", False):
            self._goal_reached = False
            self.say("E6.03")
            yield _Speech()
        total = session.total_repetitions
        correct = session.correct_repetitions
        unmeasured = total - session.assessed_repetitions
        first = total > 0 and self._once("S8.05")
        self.say("E7.01" if total < 5 else "S8.05", compact=not first)
        yield _Speech()
        if total == 0:
            return
        self.say("S8.06", n=total, spotlight="result_line" if first else None, compact=not first)
        yield _Speech()
        if unmeasured > 0:
            self.say("S8.07", k=unmeasured, compact=not first)
            yield _Speech()
        if correct > 0:
            self.say("S8.08", c=correct, compact=not first)
            yield _Speech()
        last = self.profile.last_correct
        if last is not None and correct > last:
            self.say("E7.02", compact=not first)
            yield _Speech()
        tip = most_frequent_tip(session.evaluations)
        if tip:
            self.say("S8.09", tip=self.script.text(tip, self.language), compact=not first)
            yield _Speech()
        if getattr(self, "pain_rose", False):
            self.pain_rose = False
            self.say("E9.06", compact=not first)
            yield _Speech()
        if not self._session_recorded and total > 0:
            self._session_recorded = True
            self.profile.record_session(correct)
            self.profile.save()
        if first:
            for line_id, zone in (("S8.10", "details_button"), ("S8.11", "main_button"), ("S8.12", None),
                                  ("S8.13", "help_button")):
                self.say(line_id, spotlight=zone)
                yield _Speech()
        self.current = None

    def _goodbye(self, now):
        if self.closing_until is not None:
            return  # already saying goodbye
        first = self._once("S8.14")
        self.say("S8.14" if first else "E7.03", compact=self.screen == "dashboard")
        spoken = self.current.spoken
        self.closing_until = now + (min(4., reading_seconds(self.current.texts[0])) if spoken else 0.)

    def ready_to_close(self, now):
        """After Close: wait for the goodbye, at most a few seconds."""
        if self.closing_until is None:
            return True
        busy = getattr(self.audio, "busy", False) is True
        return now >= self.closing_until or (now - self.current.started > 1. and not busy)

    def session_recorded(self, session):
        """Called when the app closes or restarts: keep the day in the profile if movements were counted."""
        if session is not None and session.total_repetitions > 0 and not self._session_recorded:
            self._session_recorded = True
            self.profile.record_session(session.correct_repetitions)
            self.profile.save()

    # ------------------------------------------------------------------ overlay
    def _build_overlay(self, now):
        overlay = self.overlay
        if self.screen != getattr(self, "_drawn_screen", self.screen):
            overlay.hit_boxes = []  # buttons of the previous screen are gone
        self._drawn_screen = self.screen
        current = self.current
        # A new everyday line from the live coaching (cues, results) takes the bubble when it is free.
        line = getattr(self.audio, "last_line", None)
        line_at = getattr(self.audio, "last_line_at", None)
        if (isinstance(line, Line) and isinstance(line_at, (int, float)) and line_at > self._audio_seen_at
                and self.screen == "dashboard"):
            free = current is None or current.compact or current.expires is not None
            if free:
                self._audio_seen_at = line_at
                self.current = current = _Said(line.id, [line.text], line.anim, now, True, compact=True,
                                               expires=now + reading_seconds(line.text) + 1.5)
                if self.guide is not None:
                    self.guide.perform(line.anim, now)
        if current is not None and current.expires is not None and now > current.expires and self._episode is None:
            self.current = current = None
        overlay.bubble = list(current.texts) if current else []
        overlay.buttons = list(current.buttons) if current else []
        overlay.spotlight = current.spotlight if current else None
        overlay.highlight = current.highlight if current else None
        overlay.sample_button = current.sample if current else None
        overlay.compact = bool(current and current.compact and not current.spotlight)
        overlay.dim = self.ctx.mode != "running"  # never darken the screen while the patient exercises
        overlay.text_field = ((self.name_buffer, ui("name_hint", self.language))
                              if current is not None and current.text_field else None)


_PENDING = object()
