"""Physio settings: a PIN pad, then the patient's plan with big − and + buttons.

The PIN is 4 digits. Until the physio changes it, it is 0000 (see README). A changed PIN is
stored as a salt and a PBKDF2-HMAC-SHA256 hash in the profile, never in clear. Five wrong
tries lock the pad for a minute. Everything here is drawn on the 1280x840 logical canvas
with the dashboard's painter, so it scales with the window and translates to English.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field, replace

import cv2
import numpy as np

from src import chattiness
from src.dashboard import CANVAS_SIZE, MUTED, TEXT, _Painter
from src.home_screen import _background
from src.user_profile import PLAN_BOUNDS, SILHOUETTE_BODIES, Plan
from src.willy_overlay import draw_button
from src.window_viewport import canvas_viewport

DEFAULT_PIN = "0000"
PIN_LENGTH = 4
PIN_ITERATIONS = 200_000
MAX_TRIES = 5
LOCK_SECONDS = 60.


# --------------------------------------------------------------------------- PIN
def hash_pin(pin, salt_hex, iterations=PIN_ITERATIONS):
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(salt_hex), iterations).hex()


def set_pin(profile, pin):
    """Store a new PIN as a salt and a hash (never the PIN itself)."""
    if len(pin) != PIN_LENGTH or not pin.isdigit():
        raise ValueError("The PIN is 4 digits")
    profile.pin_salt = secrets.token_hex(16)
    profile.pin_hash = hash_pin(pin, profile.pin_salt)


def check_pin(profile, pin):
    if not profile.pin_hash:
        return hmac.compare_digest(pin, DEFAULT_PIN)
    try:
        return hmac.compare_digest(hash_pin(pin, profile.pin_salt), profile.pin_hash)
    except ValueError:  # a damaged salt: only the default PIN can open settings again
        return hmac.compare_digest(pin, DEFAULT_PIN)


@dataclass
class PinPad:
    """Typing a PIN. mode: "check" (open settings), "new" then "confirm" (change the PIN)."""

    mode: str = "check"
    digits: str = ""
    failures: int = 0
    locked_until: float = 0.
    message: str = ""
    first: str = ""

    def locked(self, now):
        return now < self.locked_until

    def press(self, key, profile, now):
        """A digit, "back", "ok" or "cancel". Returns "open", "changed", "cancel" or None."""
        if key == "cancel":
            return "cancel"
        if self.locked(now):
            return None
        if key == "back":
            self.digits = self.digits[:-1]
            return None
        if key.isdigit() and len(key) == 1:
            if len(self.digits) < PIN_LENGTH:
                self.digits += key
                self.message = ""
            return self.press("ok", profile, now) if len(self.digits) == PIN_LENGTH else None
        if key != "ok" or len(self.digits) < PIN_LENGTH:
            return None
        typed, self.digits = self.digits, ""
        if self.mode == "check":
            if check_pin(profile, typed):
                self.failures = 0
                return "open"
            self.failures += 1
            if self.failures >= MAX_TRIES:
                self.failures, self.locked_until = 0, now + LOCK_SECONDS
                self.message = "Trop d'essais. Réessayez dans une minute."
            else:
                self.message = "Code incorrect."
            return None
        if self.mode == "new":
            self.first, self.mode, self.message = typed, "confirm", ""
            return None
        if typed != self.first:  # confirm
            self.mode, self.first, self.message = "new", "", "Les deux codes sont différents. Recommencez."
            return None
        set_pin(profile, typed)
        return "changed"

    def title(self):
        return {"check": "Code kiné", "new": "Nouveau code (4 chiffres)", "confirm": "Confirmez le nouveau code"}[self.mode]


# --------------------------------------------------------------------------- the plan form
REST_WARNING = ("Le repos mesuré est proche de la cible : le plan garde ses valeurs. "
                "Baissez la cible minimale ou relevez le repos maximal.")


def short_date(iso):
    """2026-11-25 -> 25/11/2026 (empty when unknown)."""
    parts = str(iso or "").split("-")
    return "/".join(reversed(parts)) if len(parts) == 3 else ""


# (key, French label, unit). The exercise, arm, seated and yes/no rows are choices; the rest are numbers.
# Two pages (Phase 10.2): the patient's plan, then the screen and the voice.
PLAN_FIELDS = (
    ("exercise", "Exercice", ""),
    ("arm", "Bras", ""),
    ("target_min_deg", "Cible minimale", "°"),
    ("target_max_deg", "Cible maximale", "°"),
    ("rest_max_deg", "Repos maximal", "°"),
    ("hold_sec", "Maintien", "s"),
    ("reps_per_set", "Répétitions par série", ""),
    ("sets", "Séries", ""),
    ("rest_between_sets_sec", "Repos entre les séries", "s"),
    ("sessions_per_week", "Séances par semaine", ""),
    ("max_session_min", "Durée maximale d'une séance", "min"),
    ("pain_go_max", "Douleur : séance normale jusqu'à", "/10"),
    ("pain_gentle_max", "Douleur : séance douce jusqu'à", "/10"),
    ("seated", "Exercice assis", ""),
)
DEVICE_FIELDS = (
    ("camera", "Caméra (numéro)", ""),
    ("model", "Modèle de suivi", ""),
    ("chattiness", "Willy parle", ""),
    ("large_text", "Grand texte", ""),
    ("high_contrast", "Contraste élevé", ""),
    ("slow_speech", "Voix plus lente", ""),
    ("subtitles", "Sous-titres toujours", ""),
    ("silhouette_body", "Corps de la silhouette", ""),
)
PAGES = (("plan", "Plan du patient", PLAN_FIELDS), ("device", "Écran et voix", DEVICE_FIELDS))
FIELDS = PLAN_FIELDS + DEVICE_FIELDS
ACCESSIBILITY = ("large_text", "high_contrast", "slow_speech", "subtitles")
MODEL_CHOICES = (None, "full", "lite")
MODEL_LABELS = {None: "Automatique", "full": "Précis", "lite": "Rapide"}
FAST_MODEL_NOTE = "Modèle rapide utilisé (ce PC est lent pour le modèle précis)"
CAMERA_RANGE = (0, 5)
ARM_CHOICES = (None, "right", "left")
ARM_LABELS = {None: "Au choix du patient", "right": "Droit", "left": "Gauche"}
BOTH_ARMS_LABEL = "Les deux"
# Phase 11: the CC0 bodies are offered here; the first frames' body stays the default.
SILHOUETTE_LABELS = {"classic": "Actuelle", "makehuman-female": "Nouvelle, femme", "makehuman-male": "Nouvelle, homme"}


@dataclass
class SettingsForm:
    plan: Plan
    original: Plan = field(default=None)
    resting_angle: float | None = None   # measured at calibration (2.3)
    resting_date: str = ""
    warning: str = ""
    message: str = ""
    camera: int = 0
    model: str | None = None      # forced pose model; None = automatic
    chattiness: str = "normal"    # how much Willy talks (src.chattiness)
    auto_lite: bool = False       # shown as "Modèle rapide utilisé" when automatic chose lite
    # Phase 10.1: one plan per exercise. `plans` holds every exercise's plan ({id: Plan}),
    # `names` their short names ({id: {"fr": ..., "en": ...}}), `both` the both-arm exercises.
    plans: dict = field(default_factory=dict)
    names: dict = field(default_factory=dict)
    both: tuple = ()
    page: str = "plan"            # "plan" or "device" (Phase 10.2)
    large_text: bool = False      # accessibility (src.accessibility)
    high_contrast: bool = False
    slow_speech: bool = False
    subtitles: bool = False
    silhouette_body: str = "classic"   # body of the guide silhouette (Phase 11)

    def __post_init__(self):
        self.original = self.original or self.plan
        self.plans = {**self.plans, self.plan.exercise: self.plan}
        self.originals = dict(self.plans)

    def all_plans(self):
        """Every exercise's plan, with the one on screen as edited."""
        return {**self.plans, self.plan.exercise: self.plan}

    @property
    def changed(self):
        return self.plan.exercise != self.original.exercise or self.all_plans() != self.originals

    def step(self, key, direction):
        """Change one setting by one step (direction +1 or -1), inside its bounds."""
        if key == "exercise":
            ids = list(self.plans)
            self.plans[self.plan.exercise] = self.plan
            self.plan = self.plans[ids[(ids.index(self.plan.exercise) + direction) % len(ids)]]
        elif key == "arm":
            if self.plan.exercise in self.both:
                return  # both arms: nothing to choose
            index = (ARM_CHOICES.index(self.plan.arm) + direction) % len(ARM_CHOICES)
            self.plan = replace(self.plan, arm=ARM_CHOICES[index])
        elif key == "seated":
            self.plan = replace(self.plan, seated=not self.plan.seated)
        elif key in ACCESSIBILITY:
            setattr(self, key, not getattr(self, key))
        elif key == "camera":
            self.camera = min(CAMERA_RANGE[1], max(CAMERA_RANGE[0], self.camera + direction))
        elif key == "model":
            self.model = MODEL_CHOICES[(MODEL_CHOICES.index(self.model) + direction) % len(MODEL_CHOICES)]
        elif key == "chattiness":
            levels = chattiness.LEVELS
            self.chattiness = levels[(levels.index(chattiness.level_of(self.chattiness)) + direction) % len(levels)]
        elif key == "silhouette_body":
            index = SILHOUETTE_BODIES.index(self.silhouette_body) if self.silhouette_body in SILHOUETTE_BODIES else 0
            self.silhouette_body = SILHOUETTE_BODIES[(index + direction) % len(SILHOUETTE_BODIES)]
        else:
            low, high, step = PLAN_BOUNDS[key]
            value = getattr(self.plan, key) + direction * step
            self.plan = replace(self.plan, **{key: type(getattr(self.plan, key))(min(high, max(low, value)))})
            self.plan = self.plan.clamped()
        self.message = ""

    def value_text(self, key, unit, language):
        value = getattr(self.plan, key, None)
        if key == "exercise":
            return (self.names.get(value) or {}).get(language) or (self.names.get(value) or {}).get("fr") or value
        if key == "arm":
            return BOTH_ARMS_LABEL if self.plan.exercise in self.both else ARM_LABELS[value]
        if key == "seated":
            return "Oui" if value else "Non"
        if key in ACCESSIBILITY:
            return "Oui" if getattr(self, key) else "Non"
        if key == "camera":
            return str(self.camera)
        if key == "model":
            if self.model is None and self.auto_lite:
                return "Auto (rapide)"
            return MODEL_LABELS[self.model]
        if key == "chattiness":
            return chattiness.LABELS[chattiness.level_of(self.chattiness)]
        if key == "silhouette_body":
            return SILHOUETTE_LABELS.get(self.silhouette_body, SILHOUETTE_LABELS["classic"])
        text = f"{value:g}"
        if language == "fr":
            text = text.replace(".", ",")
        return f"{text} {unit}" if unit in ("s", "min") else f"{text}{unit}"


# --------------------------------------------------------------------------- drawing
PAD_KEYS = (("1", "2", "3"), ("4", "5", "6"), ("7", "8", "9"), ("back", "0", "ok"))
PAD_LABELS = {"back": "Effacer", "ok": "OK"}


def _canvas(output_size, language):
    width, height = output_size or CANVAS_SIZE
    if width <= 0 or height <= 0:
        width, height = CANVAS_SIZE
    canvas = _background(width, height)
    return canvas, _Painter(canvas, canvas_viewport(CANVAS_SIZE, width, height), language)


def _finish(canvas):
    return cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR)


def render_pin(pad, output_size=None, language="fr", now=0.):
    """The PIN pad as a BGR image, and its hit boxes [(action, bounds)]."""
    canvas, p = _canvas(output_size, language)
    p.text((48, 30), "mouvement", 34)
    p.text((50, 78), "Réglages kiné", 16, MUTED)
    p.text((440, 140), pad.title(), 30, TEXT, True)
    for i in range(PIN_LENGTH):
        x = 540 + i * 56
        filled = i < len(pad.digits)
        p.rect((x, 200, x + 36, 236), fill=TEXT if filled else (255, 255, 255), outline=(150, 156, 161), radius=18)
    hit_boxes = []
    for row, keys in enumerate(PAD_KEYS):
        for col, key in enumerate(keys):
            bounds = (470 + col * 116, 270 + row * 98, 576 + col * 116, 354 + row * 98)
            draw_button(p, bounds, PAD_LABELS.get(key, key), primary=key == "ok", size=26 if key.isdigit() else 19)
            hit_boxes.append((f"pin:{key}", bounds))
    cancel = (540, 680, 740, 740)
    draw_button(p, cancel, "Annuler", size=19)
    hit_boxes.append(("pin:cancel", cancel))
    message = pad.message
    if pad.locked(now):
        message = f"Trop d'essais. Réessayez dans {max(1, round(pad.locked_until - now))} s."
    if message:
        p.text((440, 772), message, 18, (176, 58, 46), True)
    return _finish(canvas), hit_boxes


def render_settings(form, output_size=None, language="fr"):
    """The physio settings as a BGR image, and its hit boxes [(action, bounds)]."""
    canvas, p = _canvas(output_size, language)
    p.text((48, 30), "Réglages kiné", 34)
    p.text((50, 78), "Le plan du patient. Chaque valeur reste dans des limites sûres.", 16, MUTED)
    hit_boxes = []
    for index, (page, title, _) in enumerate(PAGES):  # the two pages, as tabs
        bounds = (48 + index * 262, 104, 298 + index * 262, 150)
        draw_button(p, bounds, title, primary=page == form.page, size=17)
        hit_boxes.append((f"page:{page}", bounds))
    fields = dict((page, rows) for page, _, rows in PAGES)[form.page]
    rows_per_column = 7
    for index, (key, label, unit) in enumerate(fields):
        column, row = divmod(index, rows_per_column)
        x, y = 48 + column * 612, 166 + row * 66
        p.rect((x, y, x + 584, y + 58), fill=(255, 255, 255), outline=(214, 220, 219), radius=12)
        p.wrap((x + 20, y + 8), label, 260, 17, TEXT, max_lines=2)
        p.fit((x + 300, y + 13), form.value_text(key, unit, language), 136, 22, TEXT, True)
        minus, plus = (x + 444, y + 6, x + 504, y + 52), (x + 514, y + 6, x + 574, y + 52)
        draw_button(p, minus, "−", size=26)
        draw_button(p, plus, "+", size=26)
        hit_boxes += [(f"set:-:{key}", minus), (f"set:+:{key}", plus)]
    if form.resting_angle is not None and form.page == "plan":
        p.text((760, 34), f"Angle de repos mesuré : {form.resting_angle:.0f}°", 17, TEXT, True)
        if form.resting_date:
            p.text((760, 62), f"Mesuré le {form.resting_date}", 14, MUTED)
    if form.model is None and form.auto_lite and form.page == "device":  # the app chose the fast model (Phase 6.4)
        p.text((48, 640), FAST_MODEL_NOTE, 14, MUTED)
    if form.warning and form.page == "plan":
        p.wrap((48, 640), form.warning, 1180, 15, (176, 58, 46), max_lines=2)
    if form.message:
        p.text((48, 704), form.message, 16, (30, 120, 80), True)
    buttons = (("settings_pin", "Changer le code", (48, 760, 288, 816), False),
               ("settings_cancel", "Annuler", (820, 760, 1010, 816), False),
               ("settings_save", "Enregistrer", (1030, 760, 1232, 816), True))
    for action, label, bounds, primary in buttons:
        draw_button(p, bounds, label, primary=primary, size=19)
        hit_boxes.append((action, bounds))
    return _finish(canvas), hit_boxes


def action_at(hit_boxes, x, y):
    for action, (left, top, right, bottom) in hit_boxes:
        if left <= x < right and top <= y < bottom:
            return action
    return None
