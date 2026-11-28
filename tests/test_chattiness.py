"""Phase 9.5: "Willy parle : beaucoup / normalement / peu" changes which everyday lines play."""
import pytest

from src import chattiness
from src.audio_feedback import AudioCoach
from src.config import ExerciseConfig
from src.rules_engine import ClinicalError, RepetitionEvaluation
from src.state_machine import ExercisePhase
from tests.test_willy_tour import Harness, _analysis


def lines_of_a_session(tmp_path, level, results, idle=0.):
    """Lines Willy says during and after a session at a level (the first session, so tips are due)."""
    h = Harness(tmp_path / level, tour_done=True, language="fr", chattiness=level)
    h.director.screen = "dashboard"
    said = []

    def note():
        if h.line and (not said or said[-1] != h.line):
            said.append(h.line)

    h.mode = "running"
    h.frame(_analysis(h.t))
    if idle:  # the patient stands still at rest
        for _ in range(int(idle / .1)):
            h.frame(_analysis(h.t, phase=ExercisePhase.REST))
            note()
    for index, (correct, label) in enumerate(results, 1):
        evaluation = RepetitionEvaluation(index, "right", correct, label, [],
                                          errors=[] if correct or label == "INDETERMINE"
                                          else [ClinicalError("Haussement d'epaule excessif", "x")])
        h.session.evaluations.append(evaluation)
        h.frame(_analysis(h.t, evaluation=evaluation))
        note()
        for _ in range(40):
            h.frame(_analysis(h.t))
            note()
    h.mode = "finished"
    h.frame()
    for _ in range(400):
        note()
        h.frame()
    return said


RESULTS = [(True, "CORRECT")] * 3 + [(False, "A CORRIGER")] * 2 + [(False, "INDETERMINE")] * 3


@pytest.mark.parametrize("level, everyday", [
    ("lots", {"E6.02", "S8.01", "S8.04", "S8.07", "S8.09"}),
    ("normal", {"E6.02", "S8.01", "S8.04", "S8.07", "S8.09"}),
    ("little", set()),
])
def test_everyday_lines_at_each_level(tmp_path, level, everyday):
    said = set(lines_of_a_session(tmp_path, level, RESULTS))
    optional = {"E6.02", "S8.01", "S8.04", "S8.07", "S8.09", "E7.02"}
    assert said & optional == everyday
    assert {"S8.05", "S8.06", "S8.08"} <= said  # the end of the session is always said


@pytest.mark.parametrize("level, asks", [("lots", True), ("normal", False), ("little", False)])
def test_still_there_comes_sooner_or_never(tmp_path, level, asks):
    said = lines_of_a_session(tmp_path, level, [(True, "CORRECT")], idle=25.)
    assert ("E6.04" in said) is asks  # after 20 s a lot, 30 s normally, never with "peu"
    if level == "normal":
        assert "E6.04" in lines_of_a_session(tmp_path / "longer", level, [(True, "CORRECT")], idle=35.)


def test_safety_and_pain_lines_always_play():
    for level in chattiness.LEVELS:
        for line_id in ("E2.05", "E2.07", "E9.04", "E9.07", "E9.09", "E9.10", "E9.11", "E6.08", "E6.07",
                        "E3.02", "S8.05", "S8.14"):
            assert chattiness.plays(line_id, level), (line_id, level)
    assert not chattiness.plays("E6.02", "little") and chattiness.plays("E6.02", "lots")
    assert chattiness.level_of("bavard") == "normal"


def test_the_coach_talks_more_or_less_but_always_warns():
    base = ExerciseConfig.from_yaml().audio
    coach = AudioCoach(enabled=False)
    coach.set_chattiness("little", base)
    assert coach.min_interval_sec == 2 * base.min_interval_sec and coach.announce_every_reps == 10
    assert coach.repeat_cooldown_sec > base.repeat_cooldown_sec and coach.guidance_mode == "essential"
    coach.set_chattiness("lots", base)
    assert coach.min_interval_sec < base.min_interval_sec and coach.announce_every_reps == 3
    assert coach.guidance_mode == "complete"
    coach.set_chattiness("normal", base)
    assert (coach.min_interval_sec, coach.repeat_cooldown_sec, coach.announce_every_reps, coach.guidance_mode) == (
        base.min_interval_sec, base.repeat_cooldown_sec, base.announce_every_reps, base.guidance_mode)


def test_the_setting_is_in_the_physio_page_and_kept(tmp_path, monkeypatch):
    from src import physio_settings as physio
    from src.i18n import tr
    from src.user_profile import Plan, Profile
    form = physio.SettingsForm(Plan.from_config(ExerciseConfig.from_yaml()))
    assert form.value_text("chattiness", "", "fr") == "Normalement"
    form.step("chattiness", +1)
    assert form.chattiness == "little" and tr(form.value_text("chattiness", "", "en"), "en") == "A little"
    form.step("chattiness", +1)
    assert form.chattiness == "lots"
    form.page = "device"  # the screen-and-voice page (Phase 10.2)
    image, boxes = physio.render_settings(form)
    assert "set:+:chattiness" in dict(boxes)
    monkeypatch.setenv("MOUVEMENT_DATA_DIR", str(tmp_path))
    profile = Profile.load()
    profile.chattiness = "little"
    profile.save()
    assert Profile.load().chattiness == "little"
