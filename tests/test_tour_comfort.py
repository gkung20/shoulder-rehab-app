"""Phase 9.4: the express tour first, step dots in the bubble, and Back in the screen tour."""
from src.willy_tour import EXPRESS_TOUR, FULL_TOUR, SCREEN_TOUR, ZONES
from tests.test_willy_tour import Harness


def to_offer(h):
    h.director.open()
    h.until("S1.02")
    h.press("lang_fr")
    h.until("S1.06")


def test_the_express_tour_is_safety_the_arm_the_camera_and_start(tmp_path):
    h = Harness(tmp_path)
    d = h.director
    to_offer(h)
    assert h.text == "La visite complète prend environ 7 minutes. Vous pourrez la revoir depuis Aide."
    h.press("express_tour")
    assert h.line == "S1.08"
    seen = []
    for _ in range(4000):
        if h.line and (not seen or seen[-1] != h.line):
            seen.append(h.line)
        if h.line == "S2.06":
            h.press("understand")
        elif h.line == "S3.04":
            assert d.overlay.progress == (2, 4)
            h.press("next")
        elif h.line in ("S4.04", "S4.11"):
            assert d.overlay.progress == (3, 4)
            h.press("next")
        elif h.line == "S4.10":
            h.press("next")
        elif h.line == "S7.01":
            assert d.overlay.progress == (4, len(EXPRESS_TOUR)) == (4, 4)
            assert d.current.spotlight == ZONES["main_button"]
            break
        h.frame()
    assert seen[-1] == "S7.01"
    assert not any(line.startswith(("S3.02", "S3.06", "S5.", "S6.")) for line in seen)  # no name, coach, screen, demo
    assert {"S2.01", "S2.06", "S3.04", "S4.01", "S4.04"} <= set(seen)
    h.press("start")
    assert h.profile.tour_done  # the full tour stays in Help


def test_the_full_tour_shows_six_stages(tmp_path):
    h = Harness(tmp_path)
    d = h.director
    to_offer(h)
    h.press("start_tour")
    h.until("S2.01")
    assert d.overlay.progress == (1, len(FULL_TOUR)) == (1, 6)
    h.until("S2.06")
    h.press("understand")
    h.until("S3.02")
    assert d.overlay.progress == (2, 6)


def test_back_shows_the_previous_zone_again(tmp_path):
    h = Harness(tmp_path, tour_done=True, language="fr")
    d = h.director
    d.screen = "dashboard"
    d._start(d._screen_tour())
    h.frame()
    first, second, third = SCREEN_TOUR[0][0], SCREEN_TOUR[1][0], SCREEN_TOUR[2][0]
    assert h.line == first and [b.action for b in d.current.buttons] == ["next"]  # nothing before the first
    h.press("next")
    h.press("next")
    assert h.line == third and [b.action for b in d.current.buttons] == ["back", "next"]
    h.press("back")
    assert h.line == second and d.current.spotlight == ZONES[SCREEN_TOUR[1][1]]
    h.press("next")
    assert h.line == third
    assert not d.permits("back")  # a tour button, never a session action


def test_no_dots_outside_the_tour(tmp_path):
    h = Harness(tmp_path, tour_done=True, language="fr")
    h.director.open()
    h.frame()
    assert h.director.overlay.progress is None


def test_help_replays_the_full_tour_without_old_dots(tmp_path):
    h = Harness(tmp_path, tour_done=True, language="fr")
    d = h.director
    d.tour_progress = (6, 6)  # left from the first tour
    d.replay_tour()
    h.frame()
    assert h.line == "S1.01" and d.overlay.progress is None
    h.until("S2.01")
    assert d.overlay.progress == (1, len(FULL_TOUR))
