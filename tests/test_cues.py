"""Every live message carries a cue code; Willy and the voice go by the code, not the French text."""
import itertools
from dataclasses import replace
from pathlib import Path

from src.calibration import CalibrationManager
from src.config import ExerciseConfig
from src.cues import LINES, SCREEN_ONLY, SETUP, TEXT, Cue, code_of, line_id, text
from src.rules_engine import RulesEngine
from src.session_processor import FrameAnalysis, SessionProcessor
from src.state_machine import ExercisePhase
from src.synthetic_pose import body, rep_angles
from src.willy_lines import cue_line_id, shared_script

ROOT = Path(__file__).resolve().parents[1]


def test_every_code_has_screen_text_and_a_decision_about_willy():
    for code in Cue:
        assert code in TEXT
        assert (code in LINES) != (code in SCREEN_ONLY), code
    script = shared_script()
    for line in LINES.values():
        assert script.text(line, "fr") and script.text(line, "en")
    assert SETUP <= set(Cue)


def test_text_round_trips_to_its_code_even_with_values():
    for code in Cue:
        values = {"remaining": 1.2} if code == Cue.CAL_HOLD_STILL else {"count": 7} if code == Cue.CAL_SAMPLES else {}
        assert code_of(text(code, **values)) == code


def test_rules_engine_messages_all_have_codes():
    engine = RulesEngine(ExerciseConfig.from_yaml())
    seen = set()
    values = (None, 5., 40., 85., 95., 150.)
    for angle, lean, shrug, elbow, drift, phase in itertools.product(
            values, (None, 2., 30.), (None, .01, .9), (None, 120., 179.), (None, 1., 60.), list(ExercisePhase)):
        feedback = engine.evaluate_live_frame(angle, lean, shrug, elbow, phase, drift)
        assert feedback.code is not None and feedback.message == text(feedback.code)
        seen.add(feedback.code)
    assert {Cue.FACE_CAMERA, Cue.KEEP_SHOULDER_LOW, Cue.KEEP_TRUNK_STRAIGHT, Cue.KEEP_ARM_STRAIGHT,
            Cue.KEEP_ARM_IN_PLANE, Cue.READY_RAISE, Cue.RISE_SLOWLY, Cue.ALMOST_TARGET, Cue.HOLD_TARGET,
            Cue.LOWER_A_LITTLE, Cue.CONTROL_DESCENT} <= seen


def test_calibrator_and_processor_cues_have_codes():
    calibrator = CalibrationManager()
    assert calibrator.status_code == Cue.CAL_REQUIRED
    calibrator.start("right", 0.)
    assert calibrator.status_code == Cue.CAL_SHOW_SHOULDERS_REST
    calibrator.update([], "right", .1)
    assert calibrator.status_code == Cue.CAL_SHOW_SHOULDERS
    raised, _ = body(60)
    calibrator.update(raised, "right", .2)
    assert calibrator.status_code == Cue.CAL_LOWER_ARM

    config = ExerciseConfig.from_yaml()
    config = replace(config, calibration=replace(config.calibration, duration_sec=.6),
                     filtering=replace(config.filtering, ema_alpha=1))
    processor = SessionProcessor(config, "right")
    codes = []
    for i, angle in enumerate(rep_angles(hold=45) * 2):
        pts, world = body(angle)
        frame = processor.process(pts, world, 640, 480, i / 30)
        assert frame.cue.code is not None, frame.cue.message
        assert frame.cue.message.startswith(TEXT[frame.cue.code].split("{")[0])
        codes.append(frame.cue.code)
    assert Cue.CAL_HOLD_STILL in codes and Cue.HOLD_DONE_LOWER in codes
    assert FrameAnalysis(0.).cue.code == Cue.PLACE_FACING


def test_willy_goes_by_the_code_not_the_wording():
    feedback = RulesEngine(ExerciseConfig.from_yaml()).evaluate_live_frame(50., 30., None, None, ExercisePhase.RISING)
    assert cue_line_id(feedback) == "E4.08" == line_id(Cue.KEEP_TRUNK_STRAIGHT)
    feedback.message = "Some reworded text"  # the code still decides
    assert cue_line_id(feedback) == "E4.08"
    assert cue_line_id("Un message inconnu") is None


def test_no_module_matches_french_cue_sentences_any_more():
    fragments = ('"baissez le bras" in', '"mouvement detect" in', '"presque" in', '"redescendez" in',
                 '"au repos encore"', '"images valides', "_CUE_LINES")
    for name in ("willy_tour.py", "audio_feedback.py", "willy_lines.py", "dashboard.py"):
        source = (ROOT / "src" / name).read_text(encoding="utf-8").lower()
        for fragment in fragments:
            assert fragment.lower() not in source, (name, fragment)
