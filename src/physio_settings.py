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

from src.dashboard import CANVAS_SIZE, MUTED, TEXT, _Painter
from src.home_screen import _background
from src.user_profile import PLAN_BOUNDS, Plan
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


# (key, French label, unit). The arm and seated rows are choices; the rest are numbers.
FIELDS = (
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
ARM_CHOICES = (None, "right", "left")
ARM_LABELS = {None: "Au choix du patient", "right": "Droit", "left": "Gauche"}


@dataclass
class SettingsForm:
    plan: Plan
    original: Plan = field(default=None)
    resting_angle: float | None = None   # measured at calibration (2.3)
    resting_date: str = ""
    warning: str = ""
    message: str = ""

    def __post_init__(self):
        self.original = self.original or self.plan

    @property
    def changed(self):
        return self.plan != self.original

    def step(self, key, direction):
        """Change one setting by one step (direction +1 or -1), inside its bounds."""
        if key == "arm":
            index = (ARM_CHOICES.index(self.plan.arm) + direction) % len(ARM_CHOICES)
            self.plan = replace(self.plan, arm=ARM_CHOICES[index])
        elif key == "seated":
            self.plan = replace(self.plan, seated=not self.plan.seated)
        else:
            low, high, step = PLAN_BOUNDS[key]
            value = getattr(self.plan, key) + direction * step
            self.plan = replace(self.plan, **{key: type(getattr(self.plan, key))(min(high, max(low, value)))})
            self.plan = self.plan.clamped()
        self.message = ""

    def value_text(self, key, unit, language):
        value = getattr(self.plan, key)
        if key == "arm":
            return ARM_LABELS[value]
        if key == "seated":
            return "Oui" if value else "Non"
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
    rows_per_column = 7
    for index, (key, label, unit) in enumerate(FIELDS):
        column, row = divmod(index, rows_per_column)
        x, y = 48 + column * 612, 124 + row * 84
        p.rect((x, y, x + 584, y + 72), fill=(255, 255, 255), outline=(214, 220, 219), radius=12)
        p.wrap((x + 20, y + 12), label, 260, 17, TEXT, max_lines=2)
        p.text((x + 300, y + 20), form.value_text(key, unit, language), 22, TEXT, True)
        minus, plus = (x + 444, y + 10, x + 504, y + 62), (x + 514, y + 10, x + 574, y + 62)
        draw_button(p, minus, "−", size=26)
        draw_button(p, plus, "+", size=26)
        hit_boxes += [(f"set:-:{key}", minus), (f"set:+:{key}", plus)]
    info_y = 124 + 6 * 84
    if form.resting_angle is not None:
        p.text((672, info_y + 12), f"Angle de repos mesuré : {form.resting_angle:.0f}°", 17, TEXT, True)
        if form.resting_date:
            p.text((672, info_y + 40), f"Mesuré le {form.resting_date}", 14, MUTED)
    if form.warning:
        p.wrap((48, 718), form.warning, 760, 15, (176, 58, 46), max_lines=2)
    if form.message:
        p.text((48, 718), form.message, 16, (30, 120, 80), True)
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
