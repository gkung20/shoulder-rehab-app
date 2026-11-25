"""One source of screen geometry: buttons, panels and the tour's spotlight zones agree."""
import itertools

from src import layout as L
from src.patient_controls import patient_buttons
from src.willy_tour import ZONES

ALL_RECTS = {name: value for name, value in vars(L).items() if isinstance(value, L.Rect)}


def test_every_rectangle_fits_the_canvas():
    assert ALL_RECTS
    for name, rect in ALL_RECTS.items():
        assert rect.width > 0 and rect.height > 0, name
        assert L.CANVAS.encloses(rect), name
    for name, rect in L.TOUR_ZONES.items():
        assert L.CANVAS.encloses(rect), name


def test_tour_zones_come_from_the_layout_and_contain_their_buttons():
    assert ZONES == L.TOUR_ZONES
    groups = {
        "avatar_buttons": ("avatar_male", "avatar_female"),
        "arm_buttons": ("arm_right", "arm_left"),
        "sound_button": ("audio",),
        "top_bar": ("avatar_male", "avatar_female", "arm_right", "arm_left", "audio"),
        "main_button": ("pause",),
        "finish_button": ("finish",),
        "view_button": ("avatars",),
        "details_button": ("details",),
        "help_button": ("help",),
        "close_button": ("quit",),
    }
    buttons = {b.action: b.bounds for b in patient_buttons(mode="running")}
    for zone, actions in groups.items():
        for action in actions:
            assert L.Rect(*ZONES[zone]).encloses(buttons[action]), (zone, action)
    for silhouette in (False, True):
        toggle = {b.action: b.bounds for b in patient_buttons(avatars=False, silhouette=silhouette)}["silhouette"]
        assert L.Rect(*ZONES["silhouette_button"]).encloses(toggle)


def test_clickable_buttons_never_overlap_on_any_screen_state():
    states = itertools.product(("ready", "running", "paused", "finished"), (False, True), (False, True),
                               (False, True), ("fr", "en"))
    for mode, help_visible, avatars, silhouette, language in states:
        buttons = patient_buttons(mode=mode, help_visible=help_visible, avatars=avatars,
                                  silhouette=silhouette, language=language)
        for a, b in itertools.combinations(buttons, 2):
            assert not L.Rect(*a.bounds).overlaps(b.bounds), (mode, a.action, b.action)


def test_home_buttons_do_not_overlap_and_rect_helpers_work():
    assert not L.HOME_LANGUAGE_BUTTON.overlaps(L.HOME_REPLAY_BUTTON)
    assert not L.HOME_WILLY_BOX.overlaps(L.HOME_LANGUAGE_BUTTON)
    r = L.Rect(10, 20, 30, 60)
    assert r.contains(10, 20) and not r.contains(30, 20)
    assert r.inset(2) == (12, 22, 28, 58) and r.inset(-1).width == 22
    assert r.center == (20, 40) and tuple(r) == (10, 20, 30, 60)
