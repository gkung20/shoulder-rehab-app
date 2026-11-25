"""The desktop app: window, camera, analysis, Willy and drawing, in small steps.

`App.run()` is the whole program after the command line has been read (`app_live_cv.py`).
Each frame, `step()` handles queued actions, reads the camera (`tick`), draws the current
screen (`draw`) and reads the keyboard (`on_key`). Every screen is a small class with
`draw`, `action_at`, `on_action` and `on_key`, so a new screen doesn't grow one function.
The OpenCV window sits behind `Window`, which tests replace with a fake.
"""
from __future__ import annotations

import datetime
import sys
import time
from collections import deque
from contextlib import ExitStack

import cv2

from src.audio_feedback import AudioCoach
from src.avatar_stage import AvatarStage
from src.capture import VideoCaptureManager
from src.dashboard import CANVAS_SIZE, render_dashboard
from src.exercises import get_exercise
from src.hand_detector import HandDetector, MODEL_PATH as HAND_MODEL_PATH
from src.home_screen import render_home
from src.patient_controls import PatientControls, dashboard_action_at
from src import physio_settings as physio
from src.pose_detector import PoseDetector
from src.rules_engine import FeedbackLevel
from src import session_store
from src.session_plan import SetTracker
from src.session_processor import FrameAnalysis, SessionProcessor
from src.silhouette import patient_alignment
from src.willy import shared_guide
from src.willy_lines import shared_script
from src.willy_tour import Moment, TOUR_ACTIONS, WillyDirector
from src.window_viewport import canvas_viewport, enable_high_dpi, native_window_size

__all__ = ["App", "Window", "show_startup_error", "window_size", "HAND_MODEL_PATH"]

WINDOW_NAME = "Mouvement - Coach epaule"
ESCAPE, ENTER, SPACE, NO_KEY = 27, 13, 32, 255
PRIMARY_BY_MODE = {"ready": "start", "running": "pause", "paused": "resume", "finished": "restart"}
SHORTCUTS = {ord('l'): "arm_left", ord('r'): "arm_right", ord('a'): "audio", ord('s'): "finish",
             ord('m'): "mirror", ord('h'): "help", ord('d'): "details", ord('v'): "avatars", ord('g'): "silhouette"}


def show_startup_error(error):
    print(f"[DÉMARRAGE] {error}")
    if sys.stdout is None:  # Double-click launcher: show errors instead of losing them in a hidden console.
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Mouvement — besoin d’aide", f"Le suivi n’a pas pu démarrer.\nVérifiez la caméra ou demandez de l’aide pour l’installation.\n\n{error}", parent=root)
        root.destroy()


def window_size():
    width, height = CANVAS_SIZE
    if sys.platform == "win32":
        import ctypes
        screen_width = ctypes.windll.user32.GetSystemMetrics(0)
        screen_height = ctypes.windll.user32.GetSystemMetrics(1)
        scale = min(1, max(640, screen_width - 80) / width, max(480, screen_height - 100) / height)
        width, height = round(width * scale), round(height * scale)
    return width, height


class Window:
    """The OpenCV window. Paints at the client area's actual pixels (no Win32 upscaling)."""

    def __init__(self, name=WINDOW_NAME):
        self.name = name

    def open(self, size, on_mouse):
        cv2.namedWindow(self.name, cv2.WINDOW_NORMAL | cv2.WINDOW_FREERATIO)
        cv2.resizeWindow(self.name, *size)
        cv2.setMouseCallback(self.name, on_mouse)

    def output_size(self):
        return native_window_size(self.name, CANVAS_SIZE)

    def show(self, image):
        cv2.imshow(self.name, image)

    def read_key(self):
        return cv2.waitKey(1) & 0xFF

    def is_open(self):
        return cv2.getWindowProperty(self.name, cv2.WND_PROP_VISIBLE) >= 1

    def close(self):
        cv2.destroyAllWindows()


# --------------------------------------------------------------------------- screens
class Screen:
    """One screen of the app. `app` is passed in so screens hold no state of their own."""

    name = ""

    def draw(self, app, output_size):
        raise NotImplementedError

    def action_at(self, app, point):
        """The action of a click at a canvas point, besides Willy's own buttons."""
        return None

    def on_action(self, app, action):
        app.director.notify(action)

    def on_key(self, app, key):
        """Handle a key; return False to close the app."""
        return True


class HomeScreen(Screen):
    """Willy's home screen: his buttons are in his overlay, so the screen adds none."""

    name = "home"

    def draw(self, app, output_size):
        return render_home(app.director, app.guide, output_size, speaking=app.audio.speaking is True)


class ExerciseScreen(Screen):
    """The session screen: camera or avatars, guidance, counter and the patient buttons."""

    name = "dashboard"

    def draw(self, app, output_size):
        c = app.controls
        return render_dashboard(app.frame, app.analysis, app.processor, app.fps, app.mirror,
                                app.audio.enabled, app.audio.status_message, mode=c.mode, details=c.details,
                                help_visible=c.help_visible, output_size=output_size,
                                avatar_stage=app.avatar_stage, avatars=c.avatars, avatar_gender=c.avatar_gender,
                                speaking=app.audio.speaking, silhouette=c.silhouette, willy=app.guide,
                                lang=app.director.language, overlay=app.director.overlay,
                                sets=app.sets, now=time.monotonic())

    def action_at(self, app, point):
        c = app.controls
        return dashboard_action_at(*point, mode=c.mode, arm=app.processor.arm, audio_enabled=app.audio.enabled,
                                   details=c.details, help_visible=c.help_visible, avatars=c.avatars,
                                   avatar_gender=c.avatar_gender, silhouette=c.silhouette,
                                   language=app.director.language)

    def on_action(self, app, action):
        controls, audio = app.controls, app.audio
        old_mode = controls.mode
        if not controls.apply(action):
            return
        if action == "replay_tour":
            app.save_session(partial=old_mode in ("running", "paused"))
            app.director.session_recorded(app.processor.rules_engine.session)
            app.processor.finish()
            app.new_processor()
            controls.mode = "ready"
            audio.silence()
        elif action == "start":
            app.processor.recalibrate(timestamp_sec=app.now_sec)
            app.sets = SetTracker.from_plan(app.plan)
            app.begin_log()
            audio.begin_session()
        elif action in ("pause", "finish") or (action == "help" and old_mode == "running"):
            app.processor.finish()
            audio.silence()
            if action == "finish":
                app.save_session()
        elif action == "resume" and app.sets is not None and app.sets.waiting:
            app.sets.next_set()
            app.director.set_started(app.sets.current_set, app.sets.is_last_set)
            if app.processor.calibrator.is_calibrating:
                app.processor.recalibrate(timestamp_sec=app.now_sec)
        elif action == "resume" and app.processor.calibrator.is_calibrating:
            app.processor.recalibrate(timestamp_sec=app.now_sec)
        elif action == "restart":
            app.save_session()
            app.director.session_recorded(app.processor.rules_engine.session)
            app.new_processor()
            app.sets = None
            audio.silence()
        elif action in ("arm_left", "arm_right"):
            app.processor.recalibrate("left" if action == "arm_left" else "right", app.now_sec)
            audio.silence()
        elif action == "audio":
            audio.toggle()
            app.profile.audio_enabled = audio.enabled is not False
            app.profile.save()
        elif action == "avatars" and controls.avatars:
            app.ensure_avatar_stage()
        elif action in ("avatar_male", "avatar_female") and app.avatar_stage is not None:
            app.avatar_stage.set_user_gender(controls.avatar_gender)
        elif action == "mirror":
            app.mirror = not app.mirror
        app.director.notify(action)

    def on_key(self, app, key):
        if 65 <= key <= 90:
            key += 32
        if key == ord('c') and app.controls.mode == "running" and app.director.permits("calibrate"):
            app.processor.recalibrate(timestamp_sec=app.now_sec)
            app.audio.silence()
        elif key == SPACE:
            app.actions.append(PRIMARY_BY_MODE[app.controls.mode])
        elif key in SHORTCUTS:
            app.actions.append(SHORTCUTS[key])
        return True


class PinScreen(Screen):
    """The physio PIN pad (before the settings, or to change the PIN)."""

    name = "pin"

    def __init__(self):
        self.pad = physio.PinPad()
        self.hit_boxes = []

    def draw(self, app, output_size):
        image, self.hit_boxes = physio.render_pin(self.pad, output_size, app.director.language, time.monotonic())
        return image

    def action_at(self, app, point):
        return physio.action_at(self.hit_boxes, *point)

    def on_action(self, app, action):
        if not action.startswith("pin:"):
            return
        result = self.pad.press(action[4:], app.profile, time.monotonic())
        changing = self.pad.mode in ("new", "confirm")
        if result == "open":
            app.open_modal("settings")
        elif result == "changed":
            app.profile.save()
            app.open_modal("settings", message="Code modifié.")
        elif result == "cancel":
            app.open_modal("settings") if changing else app.close_modal()

    def on_key(self, app, key):
        names = {8: "back", ENTER: "ok", ESCAPE: "cancel"}
        if ord('0') <= key <= ord('9'):
            self.on_action(app, f"pin:{chr(key)}")
        elif key in names:
            self.on_action(app, f"pin:{names[key]}")
        return True


class SettingsScreen(Screen):
    """The patient's plan, changed with big − and + buttons."""

    name = "settings"

    def __init__(self):
        self.form = None
        self.hit_boxes = []

    def draw(self, app, output_size):
        image, self.hit_boxes = physio.render_settings(self.form, output_size, app.director.language)
        return image

    def action_at(self, app, point):
        return physio.action_at(self.hit_boxes, *point)

    def on_action(self, app, action):
        if action.startswith("set:"):
            _, sign, key = action.split(":", 2)
            self.form.step(key, 1 if sign == "+" else -1)
        elif action == "settings_save":
            app.save_plan(self.form.plan)
        elif action == "settings_cancel":
            app.close_modal()
        elif action == "settings_pin":
            app.open_modal("pin", mode="new")

    def on_key(self, app, key):
        if key == ESCAPE:
            app.close_modal()
        elif key == ENTER:
            app.save_plan(self.form.plan)
        return True


# --------------------------------------------------------------------------- the app
class App:
    """The running program. `args` are the parsed command-line options."""

    def __init__(self, args, config, profile, window=None):
        self.args, self.config, self.profile = args, config, profile
        self.window = window or Window()
        self.exercise = get_exercise()
        self.plan = profile.current_plan(self.exercise.apply(config), self.exercise.id)
        self.processor = SessionProcessor(config, self.plan.arm or profile.arm or "right",
                                          exercise=self.exercise, plan=self.plan)
        self.controls = PatientControls(avatars=not args.no_avatars, avatar_gender=profile.avatar_gender or "male")
        self.mirror = True
        self.actions = deque()
        self.now_sec = 0.
        self.avatar_stage = self.hand_detector = None
        self.capture = self.detector = self.audio = self.director = self.guide = None
        self.frame = self.analysis = None
        self.fps = 0.
        self.viewport = None
        self.quitting = False
        self._last_audio_status = None
        self.screens = {screen.name: screen for screen in (HomeScreen(), ExerciseScreen(), PinScreen(), SettingsScreen())}
        self.modal = None  # a screen shown over Willy's flow (PIN pad, settings); Willy waits meanwhile
        self._calibrations_seen = 0
        self.sets = None   # sets of the plan, from Start to the end of the session
        self.log = None    # the session being recorded (src.session_store.SessionLog)
        self.last_record = None
        self._session_t0 = 0.
        self._devices = ExitStack()

    @property
    def screen(self):
        return self.screens[self.modal or self.director.screen]

    # ----------------------------------------------------------------- modal screens
    def open_modal(self, name, mode=None, message=""):
        """Show the PIN pad or the settings. The settings form survives a PIN change in between."""
        screen = self.screens[name]
        if name == "pin":
            screen.pad = physio.PinPad(mode=mode or "check")
        elif name == "settings":
            if screen.form is None:
                screen.form = self.new_form()
            screen.form.message = message
        self.modal = name

    def close_modal(self):
        self.modal = None
        self.screens["settings"].form = None

    def new_form(self):
        form = physio.SettingsForm(self.plan)
        if self.profile.resting_angle is not None:
            form.resting_angle = self.profile.resting_angle
            form.resting_date = physio.short_date(self.profile.resting_date)
        if self.profile.rest_warning:
            form.warning = physio.REST_WARNING
        return form

    def save_plan(self, plan):
        """Keep the physio's plan, rebuild the session with it, and let Willy confirm."""
        if plan != self.plan:
            self.profile.set_plan(plan)
            self.profile.save()
            self.plan = self.profile.current_plan(self.exercise.apply(self.config), self.exercise.id)
            if self.plan.arm:
                self.processor.arm = self.plan.arm
            self.new_processor()
            self.close_modal()
            self.director.plan_updated()
        else:
            self.close_modal()

    # ----------------------------------------------------------------- lifecycle
    def run(self):
        print("L/R bras | C calibration | A audio | S bilan | M miroir | V avatars/camera | G silhouette | Q quitter")
        print("Deux epaules pour commencer ; coude actif visible pour compter. Visage non requis par l'application.")
        try:
            self.start()
            while self.step():
                pass
        except (RuntimeError, ValueError, FileNotFoundError, ImportError, cv2.error) as exc:
            show_startup_error(exc)
            return 1
        finally:
            self.close()
        session = self.processor.rules_engine.session
        print(f"Seance : {session.total_repetitions} tentatives terminees, {session.correct_repetitions} conformes, "
              f"{session.total_repetitions - session.assessed_repetitions} indeterminees.")
        return 0

    def start(self):
        enable_high_dpi()
        args, config = self.args, self.config
        # AvatarStage preloads the voice runtime, then initializes graphics before
        # the audio worker starts. Windows native library order matters here.
        if not args.no_avatars:
            self.avatar_stage = AvatarStage()
        if not args.no_hands and HAND_MODEL_PATH.exists():
            self.hand_detector = HandDetector()
            print("[MAINS] Suivi detaille des paumes et doigts actif.")
        elif not args.no_hands:
            print("[MAINS] Modele optionnel absent : python models/download_models.py hand_landmarker.task")
        c = config.camera
        self.capture = self._devices.enter_context(VideoCaptureManager(
            camera_index=c.index, width=c.width, height=c.height, target_fps=c.fps, zoom=c.zoom, mirror=False))
        self.detector = self._devices.enter_context(PoseDetector(model_variant=config.pose.model))
        self.audio = self._devices.enter_context(AudioCoach.from_config(
            config.audio, enabled=self.profile.audio_enabled, language=self.profile.language or "fr"))
        print(self.capture.status_message)
        self.processor.model_info = self.detector.model_info.copy()
        self.guide = shared_guide()
        self.director = WillyDirector(self.profile, self.audio, self.guide, has_avatars=not args.no_avatars)
        if args.skip_home:
            self.director.screen = "dashboard"
        elif args.tour:
            self.director.replay_tour()
        else:
            self.director.open()
        self.window.open(window_size(), self.on_mouse)

    def close(self):
        self.save_session(partial=self.controls.mode in ("running", "paused"))
        self._devices.close()  # audio, pose model, camera
        if self.director is not None:
            self.director.session_recorded(self.processor.rules_engine.session)
        if self.hand_detector is not None:
            self.hand_detector.close()
        if self.avatar_stage is not None:
            self.avatar_stage.close()
        self.processor.finish()
        self.window.close()

    # ----------------------------------------------------------------- one frame
    def step(self):
        """One frame of the app; False when it should close."""
        self.handle_actions()
        if self.quitting and self.director.ready_to_close(time.monotonic()):
            return False
        success, frame, timestamp_ms, fps = self.capture.read_frame()
        if not success or frame is None:
            show_startup_error(shared_script().text("E6.08", self.director.language))
            return False
        if self.modal is None:
            self.tick(frame, timestamp_ms, fps)
        else:
            self.frame, self.fps = frame, fps  # Willy's flow waits while the physio screens are open
        self.window.show(self.draw())
        key = self.window.read_key()
        if not self.window.is_open():
            return False
        return self.on_key(key)

    def handle_actions(self):
        while self.actions:
            action = self.actions.popleft()
            if self.modal is not None:
                self.screen.on_action(self, action)
                continue
            if action == "open_settings":
                self.open_modal("pin")
                continue
            if action in TOUR_ACTIONS or self.director.screen == "home" or action in ("language", "quit"):
                self.director.notify(action)
                self.quitting = self.quitting or action == "quit"
                continue
            if not self.director.permits(action):
                continue
            self.screen.on_action(self, action)

    def tick(self, frame, timestamp_ms, fps):
        """Analyse a camera frame (only while a session runs, or while the tour checks the framing)."""
        self.frame, self.fps = frame, fps
        self.now_sec = timestamp_ms / 1000.
        height, width = frame.shape[:2]
        director, controls = self.director, self.controls
        alignment = None
        if director.screen == "dashboard" and controls.mode == "running":
            landmarks = self.detector.detect(frame, timestamp_ms)
            analysis = self.processor.process(landmarks, self.detector.last_world_landmarks, width, height, self.now_sec)
            if self.hand_detector is not None:
                analysis.hands = self.hand_detector.detect(frame, timestamp_ms, landmarks)
            if self.processor.calibrations_done != self._calibrations_seen:
                self._calibrations_seen = self.processor.calibrations_done
                self.remember_resting_angle()
            # During the first guided movements, Willy's tour speaks the phases and results itself.
            if not director.coaching or analysis.cue.level == FeedbackLevel.WARNING:
                self.audio.speak_cue(analysis.cue)
            if analysis.new_evaluation and not director.coaching:
                self.audio.speak_evaluation(analysis.new_evaluation)
            if analysis.new_evaluation and self.log is not None:
                self.log.add_rep(analysis.new_evaluation, self.now_sec - self._session_t0)
            if analysis.new_evaluation and self.sets is not None:
                self.count_for_plan()
        elif director.wants_tracking:
            # Camera setup of the tour: find the shoulders to check the placement, count nothing.
            landmarks = self.detector.detect(frame, timestamp_ms)
            analysis = FrameAnalysis(self.now_sec, landmarks=landmarks or [], metrics={}, status=controls.mode.upper())
            alignment = patient_alignment(analysis.landmarks, width, height, self.mirror)
        else:
            analysis = FrameAnalysis(self.now_sec, metrics={}, status=controls.mode.upper())
        if self.sets is not None and self.sets.tick(time.monotonic()) == "rest_over":
            director.rest_over(self.sets.current_set + 1)
        self.analysis = analysis
        director.update(Moment(time.monotonic(), controls.mode, analysis, self.processor, alignment, self.mirror,
                               self.audio.enabled is not False))
        self.follow_tour_view()
        if self.audio.status_message != self._last_audio_status:
            print(f"[AUDIO] {self.audio.status_message}")
            self._last_audio_status = self.audio.status_message

    def follow_tour_view(self):
        """The tour shows the view it is talking about."""
        director, controls = self.director, self.controls
        if director.want_avatars is not None and controls.avatars != director.want_avatars:
            controls.apply("avatars")
            if controls.avatars:
                self.ensure_avatar_stage()
        if director.want_silhouette is not None and controls.silhouette != director.want_silhouette:
            controls.apply("silhouette")

    def draw(self):
        output_size = self.window.output_size()
        display = self.screen.draw(self, output_size)
        self.viewport = canvas_viewport(CANVAS_SIZE, *output_size)
        return display

    # ----------------------------------------------------------------- input
    def on_mouse(self, event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONUP or self.viewport is None:
            return
        point = self.viewport.canvas_point(x, y)
        if point is None:
            return
        # Willy's buttons (home screen, tour bubble) are on top of the screen's own controls.
        action = self.director.overlay.action_at(*point) if self.modal is None else None
        if action is None:
            action = self.screen.action_at(self, point)
        if action:
            self.actions.append(action)

    def on_key(self, key):
        if self.modal is not None:
            return self.screen.on_key(self, key)
        director = self.director
        if key != NO_KEY and director.type_key(key):
            return True  # the patient is typing a first name
        if key in (ord('q'), ord('Q'), ESCAPE):
            return False
        if key in (ENTER, SPACE) and (director.screen == "home" or director.primary_action()):
            primary = director.primary_action()
            if primary:
                self.actions.append(primary)
            return True
        return self.screen.on_key(self, key)

    # ----------------------------------------------------------------- helpers
    def begin_log(self):
        self.log = session_store.SessionLog.start(self.exercise.id, self.processor.arm, self.plan)
        self._session_t0 = self.now_sec

    def save_session(self, partial=False):
        """Save the session once (no images: numbers per movement). Never stops the app."""
        log = self.log
        if log is None or log.saved or not log.worth_saving:
            return None
        record = log.record(sets=self.sets, model=str(self.processor.model_info.get("file", "")), fps=self.fps,
                            resting_angle=self.processor.resting_angle, partial=partial)
        try:
            path = session_store.save_session(record)
        except OSError as error:
            print(f"[SÉANCE] Impossible d'enregistrer la séance : {error}")
            return None
        log.saved, self.last_record = True, record
        return path

    def count_for_plan(self):
        """A counted movement: at the end of a set, rest; at the end of the plan, finish."""
        event = self.sets.add_rep(time.monotonic())
        if event == "set_done":
            self.director.set_done(self.sets.current_set)
            self.screens["dashboard"].on_action(self, "pause")
        elif event == "plan_done":
            self.director.plan_done()
            self.screens["dashboard"].on_action(self, "finish")

    def remember_resting_angle(self):
        """Keep the resting angle measured at calibration, for the physio's settings screen."""
        processor, profile = self.processor, self.profile
        if processor.resting_angle is not None:
            profile.resting_angle = round(processor.resting_angle, 1)
            profile.resting_date = datetime.date.today().isoformat()
        profile.rest_warning = processor.rest_warning
        profile.save()

    def new_processor(self):
        self._calibrations_seen = 0
        self.processor = SessionProcessor(self.config, self.processor.arm, exercise=self.exercise, plan=self.plan)
        self.processor.model_info = self.detector.model_info.copy()

    def ensure_avatar_stage(self):
        if self.avatar_stage is None:
            self.avatar_stage = AvatarStage()
            self.avatar_stage.set_user_gender(self.controls.avatar_gender)
