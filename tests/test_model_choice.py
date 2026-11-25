"""Phase 6.4-6.5: the fast pose model on a slow PC, the physio's model choice, the hand model off."""
import src.pose_detector as pose_detector
from src import physio_settings as physio
from src.i18n import tr
from src.user_profile import Profile
from src import layout as L
from tests.app_fakes import FakeDetector, ScriptedWindow, make_app


def installed(*variants):
    return lambda preferred="full", models_dir=None: preferred if preferred in variants else variants[0]


def run_until(app, condition, limit=400):
    app.start()
    try:
        for _ in range(limit):
            app.step()
            if condition():
                return True
        return False
    finally:
        app.close()


def start_session(window):
    """The patient presses Start (the pain check answers 1): the pose model starts tracking."""
    if window.app.director is not None and window.app.controls.mode == "ready":
        window.click(L.MAIN_BUTTON)


def patient():
    return ScriptedWindow(start_session)


def test_a_slow_pc_switches_to_the_fast_model_and_remembers_it(monkeypatch, tmp_path):
    monkeypatch.setattr(pose_detector, "installed_pose_model", installed("full", "lite"))
    app = make_app(monkeypatch, tmp_path, patient(), args=("--no-avatars", "--skip-home"), language="fr",
                   tour_done=True)
    switched = []

    def slow():  # the full model takes 90 ms a frame here: 11 images/s, under the 15 limit
        if app.worker is not None and app.pose_model == "full":
            app.worker.pose_ms = 90.
        return app.pose_model == "lite" and switched.append(app.detector) is None

    assert run_until(app, slow)
    assert app.detector.variant == "lite" and app.processor.model_info == FakeDetector.model_info
    profile = Profile.load()
    assert profile.auto_lite and profile.pose_model is None
    # next start: straight to the fast model, and the physio sees why
    again = make_app(monkeypatch, tmp_path, patient(), args=("--no-avatars", "--skip-home"))
    assert again.chosen_pose_model() == "lite"
    form = physio.SettingsForm(again.plan)
    form.model, form.auto_lite = None, True
    assert form.value_text("model", "", "fr") == "Auto (rapide)"
    assert tr(form.value_text("model", "", "en"), "en") == "Auto (fast)"  # the page translates


def test_a_fast_pc_keeps_the_accurate_model(monkeypatch, tmp_path):
    monkeypatch.setattr(pose_detector, "installed_pose_model", installed("full", "lite"))
    app = make_app(monkeypatch, tmp_path, patient(), args=("--no-avatars", "--skip-home"), tour_done=True)

    def fast():
        if app.worker is not None:
            app.worker.pose_ms = 25.  # 40 images/s
        return "pose_fps_full" in app.timings

    assert run_until(app, fast)
    assert app.pose_model == "full" and not Profile.load().auto_lite


def test_the_model_given_on_the_command_line_or_by_the_physio_is_never_changed(monkeypatch, tmp_path):
    monkeypatch.setattr(pose_detector, "installed_pose_model", installed("full", "lite"))
    for args, fields in ((("--no-avatars", "--skip-home", "--model", "full"), {}),
                         (("--no-avatars", "--skip-home"), {"pose_model": "full"})):
        app = make_app(monkeypatch, tmp_path, patient(), args=args, tour_done=True, **fields)
        steps = []

        def slow():
            if app.worker is not None:
                app.worker.pose_ms = 90.
            steps.append(1)
            return len(steps) > 200

        run_until(app, slow)
        assert app.pose_model == "full" and not Profile.load().auto_lite


def test_without_the_fast_model_installed_nothing_changes(monkeypatch, tmp_path):
    monkeypatch.setattr(pose_detector, "installed_pose_model", installed("full"))
    app = make_app(monkeypatch, tmp_path, patient(), args=("--no-avatars", "--skip-home"), tour_done=True)

    def slow():
        if app.worker is not None:
            app.worker.pose_ms = 90.
        return "pose_fps_full" in app.timings

    assert run_until(app, slow)
    assert app.pose_model == "full" and not Profile.load().auto_lite


def test_the_physio_can_force_a_model_in_the_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(pose_detector, "installed_pose_model", installed("full", "lite"))
    app = make_app(monkeypatch, tmp_path, patient(), args=("--no-avatars", "--skip-home"), tour_done=True)
    app.start()
    try:
        first = app.detector
        form = app.new_form()
        assert form.value_text("model", "", "fr") == "Automatique"
        form.step("model", +1)
        assert form.model == "full"
        form.step("model", +1)
        assert form.model == "lite" and tr(form.value_text("model", "", "en"), "en") == "Fast"
        app.screens["settings"].form = form
        app.save_plan(app.plan)
        assert app.pose_model == "lite" and app.detector is not first and first.closed
        assert Profile.load().pose_model == "lite"
        for _ in range(5):  # the camera thread was restarted with the new model
            app.step()
        assert app.detector.calls > 0
    finally:
        app.close()
    assert app.detector.closed


def test_the_settings_page_shows_the_model_row_and_the_fast_model_note():
    form = physio.SettingsForm(physio_plan())
    form.model, form.auto_lite = None, True
    image, boxes = physio.render_settings(form)
    assert ("set:+:model" in dict(boxes)) and image.shape == (840, 1280, 3)
    bounds = [box for _, box in boxes]
    for i, a in enumerate(bounds):  # no button overlaps another
        for b in bounds[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


def physio_plan():
    from src.config import ExerciseConfig
    from src.user_profile import Plan
    return Plan.from_config(ExerciseConfig.from_yaml())
