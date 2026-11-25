"""One code for every live message, so no module has to recognise French sentences.

The rules engine, the calibrator and the session processor attach a `Cue` to each
`LiveFeedback`. The French text below is what the screen shows (ASCII, as before);
Willy's spoken and English wording comes from `assets/willy/lines.yaml` through `LINES`.
"""
from __future__ import annotations

import logging
import unicodedata
from enum import Enum

LOGGER = logging.getLogger(__name__)


class Cue(str, Enum):
    # Rules engine: framing and compensations (highest priority first)
    FACE_CAMERA = "face_camera"
    KEEP_SHOULDER_LOW = "keep_shoulder_low"
    KEEP_TRUNK_STRAIGHT = "keep_trunk_straight"
    KEEP_ARM_STRAIGHT = "keep_arm_straight"
    KEEP_ARM_IN_PLANE = "keep_arm_in_plane"
    # Rules engine: phases of the movement
    READY_RAISE = "ready_raise"
    RISE_SLOWLY = "rise_slowly"
    ALMOST_TARGET = "almost_target"
    LOWER_A_LITTLE = "lower_a_little"
    HOLD_TARGET = "hold_target"
    CONTROL_DESCENT = "control_descent"
    CONTINUE = "continue"
    # Session processor
    PLACE_FACING = "place_facing"
    NO_SKELETON = "no_skeleton"
    SHOULDERS_READY_SHOW_ELBOW = "shoulders_ready_show_elbow"
    SHOW_SHOULDERS_AND_ELBOW = "show_shoulders_and_elbow"
    LOWER_BEFORE_REP = "lower_before_rep"
    HOLD_DONE_LOWER = "hold_done_lower"
    # Calibrator
    CAL_REQUIRED = "cal_required"
    CAL_SHOW_SHOULDERS_REST = "cal_show_shoulders_rest"
    CAL_SHOW_SHOULDERS = "cal_show_shoulders"
    CAL_SHOULDERS_LOW_VISIBILITY = "cal_shoulders_low_visibility"
    CAL_SHOULDERS_APART = "cal_shoulders_apart"
    CAL_LOWER_ARM = "cal_lower_arm"
    CAL_STRAIGHTEN = "cal_straighten"
    CAL_HOLD_STILL = "cal_hold_still"
    CAL_SAMPLES = "cal_samples"
    CAL_MOVED = "cal_moved"
    CAL_DONE = "cal_done"
    CAL_DONE_TIGHT = "cal_done_tight"


# Screen wording (unchanged from before the codes existed). `{...}` fields are filled by `text()`.
TEXT = {
    Cue.FACE_CAMERA: "Positionnez-vous face a la camera",
    Cue.KEEP_SHOULDER_LOW: "Gardez l'epaule basse !",
    Cue.KEEP_TRUNK_STRAIGHT: "Gardez le tronc droit !",
    Cue.KEEP_ARM_STRAIGHT: "Gardez le bras tendu !",
    Cue.KEEP_ARM_IN_PLANE: "Gardez le bras dans le plan du corps !",
    Cue.READY_RAISE: "Pret : levez le bras sur le cote",
    Cue.RISE_SLOWLY: "Montez lentement le bras...",
    Cue.ALMOST_TARGET: "Presque ! Rejoignez votre zone cible",
    Cue.LOWER_A_LITTLE: "Un peu moins haut : revenez dans la zone cible",
    Cue.HOLD_TARGET: "Maintenez dans la zone cible, puis redescendez",
    Cue.CONTROL_DESCENT: "Controlez la descente lentement",
    Cue.CONTINUE: "Continuez le mouvement",
    Cue.PLACE_FACING: "Placez-vous face a la camera",
    Cue.NO_SKELETON: "Aucun squelette detecte : ajustez le cadrage des epaules",
    Cue.SHOULDERS_READY_SHOW_ELBOW: "Epaules pretes : montrez le coude du bras actif pour compter",
    Cue.SHOW_SHOULDERS_AND_ELBOW: "Montrez les deux epaules et le coude du bras actif",
    Cue.LOWER_BEFORE_REP: "Baissez le bras avant de commencer une repetition",
    Cue.HOLD_DONE_LOWER: "Bien ! Redescendez doucement jusqu'au repos",
    Cue.CAL_REQUIRED: "Calibration requise : appuyez sur C",
    Cue.CAL_SHOW_SHOULDERS_REST: "Montrez les deux epaules, gardez le bras au repos",
    Cue.CAL_SHOW_SHOULDERS: "Montrez les deux epaules pour commencer",
    Cue.CAL_SHOULDERS_LOW_VISIBILITY: "Calibration en attente : deux epaules peu visibles",
    Cue.CAL_SHOULDERS_APART: "Montrez les deux epaules bien separees dans l'image",
    Cue.CAL_LOWER_ARM: "Baissez le bras pour terminer la calibration",
    Cue.CAL_STRAIGHTEN: "Redressez le buste pour la calibration",
    Cue.CAL_HOLD_STILL: "Restez au repos encore {remaining:.1f} s",
    Cue.CAL_SAMPLES: "Images valides : {count}/15, restez au repos",
    Cue.CAL_MOVED: "Mouvement detecte : restez au repos, nouvel essai",
    Cue.CAL_DONE: "Calibration reussie",
    Cue.CAL_DONE_TIGHT: "Calibration reussie : cadrage serre",
}

# Willy's everyday line for each code (assets/willy/lines.yaml). Codes missing here
# have nothing to add in Willy's voice: they stay on screen only.
LINES = {
    Cue.READY_RAISE: "E4.01",
    Cue.RISE_SLOWLY: "E4.02",
    Cue.ALMOST_TARGET: "E4.03",
    Cue.HOLD_TARGET: "E4.04",
    Cue.HOLD_DONE_LOWER: "E4.05",
    Cue.CONTROL_DESCENT: "E4.06",
    Cue.KEEP_SHOULDER_LOW: "E4.07",
    Cue.KEEP_TRUNK_STRAIGHT: "E4.08",
    Cue.KEEP_ARM_STRAIGHT: "E4.09",
    Cue.KEEP_ARM_IN_PLANE: "E4.10",
    Cue.LOWER_A_LITTLE: "E4.11",
    Cue.SHOULDERS_READY_SHOW_ELBOW: "E3.04",
    Cue.LOWER_BEFORE_REP: "E3.06",
    Cue.CAL_LOWER_ARM: "E3.05",
    Cue.CAL_SHOW_SHOULDERS_REST: "E3.02",
    Cue.SHOW_SHOULDERS_AND_ELBOW: "E3.08",
    Cue.FACE_CAMERA: "E3.09",
    Cue.PLACE_FACING: "E3.09",
    Cue.CAL_SHOW_SHOULDERS: "E3.02",
    Cue.CAL_SHOULDERS_APART: "E3.03",
    Cue.CAL_SHOULDERS_LOW_VISIBILITY: "E3.03",
    Cue.CAL_STRAIGHTEN: "E4.08",
    Cue.CAL_MOVED: "E3.05",
    Cue.CAL_HOLD_STILL: "E3.05",
    Cue.CAL_SAMPLES: "E3.05",
    Cue.NO_SKELETON: "E3.07",
}

# Screen-only codes, listed so a test can check that every code was considered.
SCREEN_ONLY = frozenset({Cue.CONTINUE, Cue.CAL_REQUIRED, Cue.CAL_DONE, Cue.CAL_DONE_TIGHT})

# Setting up in front of the camera: essential mode says one setup line per session the
# first time one of these shows (the same messages the old text test caught).
SETUP = frozenset({
    Cue.CAL_REQUIRED, Cue.CAL_SHOW_SHOULDERS_REST, Cue.CAL_SHOW_SHOULDERS,
    Cue.CAL_SHOULDERS_LOW_VISIBILITY, Cue.CAL_SHOULDERS_APART, Cue.CAL_LOWER_ARM, Cue.CAL_STRAIGHTEN,
    Cue.CAL_HOLD_STILL, Cue.CAL_SAMPLES, Cue.CAL_DONE, Cue.CAL_DONE_TIGHT, Cue.NO_SKELETON,
    Cue.SHOULDERS_READY_SHOW_ELBOW, Cue.SHOW_SHOULDERS_AND_ELBOW,
})


def text(code: Cue, **values) -> str:
    """The screen text of a code, with its fields filled in."""
    template = TEXT[Cue(code)]
    return template.format(**values) if values else template


def _key(message) -> str:
    return unicodedata.normalize("NFKD", str(message)).encode("ascii", "ignore").decode().strip().lower()


def _fixed_part(template: str) -> str:
    return _key(template.split("{", 1)[0])


_EXACT = {_key(template): code for code, template in TEXT.items() if "{" not in template}
_PREFIX = sorted(((_fixed_part(t), c) for c, t in TEXT.items() if "{" in t), key=lambda item: -len(item[0]))
_WARNED: set[str] = set()


def code_of(cue) -> Cue | None:
    """The code of a `LiveFeedback`, a `Cue` or (for old callers only) a screen message.

    Plain text is matched against the screen wording above as a fallback, with a one-time
    warning when nothing matches, so a new message without a code is noticed.
    """
    if cue is None:
        return None
    if isinstance(cue, Cue):
        return cue
    code = getattr(cue, "code", None)
    if code is not None:
        return Cue(code)
    message = getattr(cue, "message", cue)
    key = _key(message)
    if not key:
        return None
    if key in _EXACT:
        return _EXACT[key]
    for prefix, candidate in _PREFIX:
        if key.startswith(prefix):
            return candidate
    if key not in _WARNED:
        _WARNED.add(key)
        LOGGER.warning("Live message without a cue code: %r", message)
    return None


def line_id(cue) -> str | None:
    """Willy's everyday line for a cue, or None when he has nothing to add."""
    code = code_of(cue)
    return LINES.get(code) if code is not None else None
