"""The desktop app: window, camera, analysis, Willy and drawing, in small steps.

`App.run()` is the whole program after the command line has been read (`app_live_cv.py`).
Each frame, `step()` handles queued actions, reads the camera (`tick`), draws the current
screen (`draw`) and reads the keyboard (`on_key`). Every screen is a small class with
`draw`, `action_at`, `on_action` and `on_key`, so a new screen doesn't grow one function.
The OpenCV window sits behind `Window`, which tests replace with a fake.
"""
from __future__ import annotations

import datetime
import os
import sys
import time
from dataclasses import asdict
from time import perf_counter
from collections import deque
from contextlib import ExitStack

import cv2

from src.audio_feedback import AudioCoach
from src.avatar_stage import AvatarStage
from src.capture import VideoCaptureManager
from src.dashboard import CANVAS_SIZE, render_dashboard
from src.exercises import get_exercise
from src.gesture import HandRaise
from src.hand_detector import HandDetector, MODEL_PATH as HAND_MODEL_PATH
from src.home_screen import render_home
from src.patient_controls import PatientControls, dashboard_action_at
from src import physio_settings as physio
from src import app_log
from src.notice_screen import render_notice
from src.pain_screen import QUESTIONS as PAIN_QUESTIONS, PainCheck, render_pain
from src.person_lock import PersonLock
from src.pose_detector import PoseDetector
from src.pose_worker import PoseWorker
from src.timings import StageTimer
from src.results_screen import render_history, render_results, results_lines
from src.rules_engine import FeedbackLevel
from src import history_export, session_store
from src.user_profile import data_dir
from src.safety import SafetyMonitor
from src.session_plan import SetTracker
from src.session_processor import FrameAnalysis, SessionProcessor
from src.silhouette import patient_alignment
from src.willy import exercise_screen_side, shared_guide
from src.willy_lines import shared_script
from src.willy_tour import Moment, TOUR_ACTIONS, WillyDirector
from src.window_viewport import canvas_viewport, enable_high_dpi, native_window_size

__all__ = ["App", "Window", "show_startup_error", "window_size", "HAND_MODEL_PATH"]

WINDOW_NAME = "Mouvement - Coach epaule"
ESCAPE, ENTER, SPACE, NO_KEY = 27, 13, 32, 255
PRIMARY_BY_MODE = {"ready": "start", "running": "pause", "paused": "resume", "finished": "restart"}
SHORTCUTS = {ord('l'): "arm_left", ord('r'): "arm_right", ord('a'): "audio", ord('s'): "finish",
             ord('m'): "mirror", ord('h'): "help", ord('d'): "details", ord('v'): "avatars", ord('g'): "silhouette",
             ord('p'): "hurt"}


def show_startup_error(error):
    print(f"[DÉMARRAGE] {error}")
    if sys.stdout is None or not getattr(sys.stdout, "has_console", True):
        # Double-click launcher: show errors instead of losing them in a hidden console.
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

    def pump(self):
        """Let the window paint while the app is still loading (keys are ignored then)."""
        cv2.waitKey(1)

    def is_open(self):
        return cv2.getWindowProperty(self.name, cv2.WND_PROP_VISIBLE) >= 1

    def close(self):
        cv2.destroyAllWindows()


def draw_ring(image, viewport, canvas_point, progress):
    """A ring filling clockwise, drawn on the final BGR image (canvas coordinates)."""
    scale = viewport.content_width / viewport.source_width
    x = round(viewport.left + canvas_point[0] * scale)
    y = round(viewport.top + canvas_point[1] * (viewport.content_height / viewport.source_height))
    radius, thick = max(8, round(34 * scale)), max(2, round(6 * scale))
    cv2.circle(image, (x, y), radius, (235, 238, 236), thick, cv2.LINE_AA)
    cv2.ellipse(image, (x, y), (radius, radius), -90, 0, 360 * progress, (32, 29, 26), thick, cv2.LINE_AA)


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
        return render_home(app.director, app.guide, output_size, speaking=app.audio.mouth())


class ExerciseScreen(Screen):
    """The session screen: camera or avatars, guidance, counter and the patient buttons."""

    name = "dashboard"

    def draw(self, app, output_size):
        c = app.controls
        return render_dashboard(app.frame, app.analysis, app.processor, app.fps, app.mirror,
                                app.audio.enabled, app.audio.status_message, mode=c.mode, details=c.details,
                                help_visible=c.help_visible, output_size=output_size,
                                avatar_stage=app.avatar_stage, avatars=c.avatars, avatar_gender=c.avatar_gender,
                                speaking=app.audio.mouth(), silhouette=c.silhouette, willy=app.guide,
                                lang=app.director.language, overlay=app.director.overlay,
                                sets=app.sets, now=time.monotonic(), results=app.last_record is not None,
                                guidance=app.pain_rest_guidance())

    def action_at(self, app, point):
        c = app.controls
        return dashboard_action_at(*point, mode=c.mode, arm=app.processor.arm, audio_enabled=app.audio.enabled,
                                   details=c.details, help_visible=c.help_visible, avatars=c.avatars,
                                   avatar_gender=c.avatar_gender, silhouette=c.silhouette,
                                   language=app.director.language, results=app.last_record is not None)

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
            app.person_lock.reset()  # lock on the patient in front of the camera now
            app.processor.recalibrate(timestamp_sec=app.now_sec)
            app.sets = SetTracker.from_plan(app.plan, gentle=app.session_plan is not app.plan)
            app.safety = SafetyMonitor.from_config(app.config.safety, app.session_plan)
            app.active_sec = 0.
            app.begin_log()
            audio.begin_session()
        elif action in ("pause", "finish") or (action == "help" and old_mode == "running"):
            app.processor.finish()
            audio.silence()
            if action == "finish":
                app.after_session()
        elif action == "resume" and app.pain_rest_until is not None:
            app.pain_rest_until = None
            app.director.rest_done()
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
            app.session_plan = app.plan
            app.new_processor()
            app.sets = app.safety = None
            audio.silence()
        elif action in ("arm_left", "arm_right"):
            app.person_lock.reset()
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
            app.person_lock.reset()
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


class PainScreen(Screen):
    """The pain check (0-10), before and after a session and after "J'ai mal"."""

    name = "pain"

    def __init__(self):
        self.check = PainCheck()
        self.hit_boxes = []

    def draw(self, app, output_size):
        line = "E9.08" if self.check.choices and self.check.can_continue else PAIN_QUESTIONS[self.check.moment]
        if self.check.choices and not self.check.can_continue:
            line = "E9.11" if app.safety and app.safety.pain_stops >= app.safety.max_pain_stops else "E9.04"
        question = shared_script().text(line, app.director.language)
        image, self.hit_boxes = render_pain(self.check, question, output_size, app.director.language, app.guide)
        return image

    def action_at(self, app, point):
        return physio.action_at(self.hit_boxes, *point)

    def on_action(self, app, action):
        if action.startswith("pain:"):
            app.pain_answer(int(action.split(":", 1)[1]))
        elif action in ("hurt_rest", "hurt_end"):
            app.hurt_choice(action)

    def on_key(self, app, key):
        if ord('0') <= key <= ord('9') and not self.check.choices:
            app.pain_answer(key - ord('0'))
        elif key == ESCAPE:
            app.pain_escape()
        return True


class ResultsScreen(Screen):
    """One session's results ("Mon bilan")."""

    name = "results"

    def __init__(self):
        self.record = None
        self.hit_boxes = []

    def draw(self, app, output_size):
        image, self.hit_boxes = render_results(self.record, output_size, app.director.language, app.guide)
        return image

    def action_at(self, app, point):
        return physio.action_at(self.hit_boxes, *point)

    def on_action(self, app, action):
        if action == "results_back":
            app.close_modal()
        elif action == "results_history":
            app.open_modal("history")

    def on_key(self, app, key):
        if key == ESCAPE:
            app.close_modal()
        return True


class HistoryScreen(Screen):
    """The last 30 days, and the export for the physio."""

    name = "history"

    def __init__(self):
        self.records = []
        self.period = "30"
        self.message = ""
        self.hit_boxes = []
        self.said = False
        self.folder = None   # the last export, for "Ouvrir le dossier"

    def draw(self, app, output_size):
        image, self.hit_boxes, line_id = render_history(self.records, output_size, app.director.language,
                                                        app.profile.streak(), self.period, message=self.message,
                                                        can_open=self.folder is not None)
        if not self.said:
            self.said = True
            app.say_line(line_id)
        return image

    def action_at(self, app, point):
        return physio.action_at(self.hit_boxes, *point)

    def on_action(self, app, action):
        if action == "history_back":
            app.open_modal("results") if app.screens["results"].record is not None else app.close_modal()
        elif action.startswith("period:"):
            self.period = action.split(":", 1)[1]
        elif action == "history_export":
            app.export_history(self.period)
        elif action == "history_open_folder" and self.folder is not None and hasattr(os, "startfile"):
            os.startfile(self.folder)  # Windows Explorer

    def on_key(self, app, key):
        if key == ESCAPE:
            app.close_modal()
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
        self.screens = {screen.name: screen for screen in (HomeScreen(), ExerciseScreen(), PinScreen(),
                                                           SettingsScreen(), ResultsScreen(), HistoryScreen(),
                                                           PainScreen())}
        self.modal = None  # a screen shown over Willy's flow (PIN pad, settings); Willy waits meanwhile
        self._calibrations_seen = 0
        self.timings = {}  # startup: seconds to the first window and until ready
        self.worker = None
        self.detector = None
        self.pose_model = config.pose.model
        self._pose_check_since = None
        self._pose_checked = False
        self._closing = []  # pose models to close at the end
        self._last_seq = 0
        self.timer = StageTimer(getattr(args, "debug", False), data_dir() / "timings.csv")
        self.sets = None   # sets of the plan, from Start to the end of the session
        self.session_plan = self.plan  # the plan of this session (gentle when pain is in the middle band)
        self.safety = None  # gentle stop rules of this session (src.safety)
        self.active_sec = 0.
        self.pain_rest_until = None  # the minute of rest after "J'ai mal"
        self.gesture = HandRaise()   # free hand above the head: pause/resume, Next/OK
        self.hands_free = False      # the current pause was made from a distance: watch for "resume"
        self.person_lock = PersonLock()
        self.camera_lost_since = None
        self.log = None    # the session being recorded (src.session_store.SessionLog)
        self.last_record = None
        self._session_t0 = 0.
        self._devices = ExitStack()
        self.crash_boxes = None  # buttons of the error screen while it is shown (Phase 8.3)

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
        elif name == "results":
            screen.record = self.last_record or session_store.last_session()
            if screen.record is None:
                return
            if self.modal is None:
                for line in results_lines(screen.record, self.director.language):
                    self.audio.say(line, self.director.language, interrupt=False)
        elif name == "history":
            screen.records = session_store.load_sessions(since=datetime.date.today() - datetime.timedelta(days=29))
            screen.said, screen.message, screen.folder = False, "", None
        self.modal = name

    def close_modal(self):
        self.modal = None
        self.screens["settings"].form = None

    def new_form(self):
        form = physio.SettingsForm(self.plan)
        form.camera = self.capture.camera_index if self.capture is not None else 0
        form.model, form.auto_lite = self.profile.pose_model, self.profile.auto_lite
        if self.profile.resting_angle is not None:
            form.resting_angle = self.profile.resting_angle
            form.resting_date = physio.short_date(self.profile.resting_date)
        if self.profile.rest_warning:
            form.warning = physio.REST_WARNING
        return form

    def save_plan(self, plan):
        """Keep the physio's plan, rebuild the session with it, and let Willy confirm."""
        form = self.screens["settings"].form
        if form is not None and self.capture is not None and form.camera != self.capture.camera_index:
            if not self.use_camera(form.camera):
                form.message = f"Caméra n° {form.camera} introuvable."
                return
            self.profile.save()
        if form is not None and form.model != self.profile.pose_model:
            wanted = form.model or self.config.pose.model
            if not self.pose_model_installed(wanted):
                form.message = f"Modèle « {physio.MODEL_LABELS[form.model]} » non installé."
                return
            self.profile.pose_model, self.profile.auto_lite = form.model, False
            self.profile.save()
            self._pose_checked = form.model is not None  # back to automatic: measure again
            if wanted != self.pose_model and self.detector is not None:
                self.pose_model = wanted
                self.open_pose_model(wanted)
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
            try:
                self.start()
            except (RuntimeError, ValueError, FileNotFoundError, ImportError, cv2.error) as exc:
                app_log.logger().error("Démarrage impossible", exc_info=exc)
                show_startup_error(exc)
                return 1
            try:
                while self.step():
                    pass
            except Exception as exc:  # anything unexpected: keep the results, explain calmly, log it
                self.crashed(exc)
                return 2
        finally:
            try:
                self.close()
            except Exception:
                app_log.logger().exception("Fermeture incomplète")
        session = self.processor.rules_engine.session
        print(f"Seance : {session.total_repetitions} tentatives terminees, {session.correct_repetitions} conformes, "
              f"{session.total_repetitions - session.assessed_repetitions} indeterminees.")
        return 0

    # ----------------------------------------------------------------- something went wrong
    def crashed(self, error):
        """An unexpected error: the traceback goes to the journal, the session is saved as
        partial, and Willy, calm, says so with "Open the log folder" and "Close"."""
        log = app_log.logger()
        log.critical("Erreur inattendue pendant la séance", exc_info=error)
        try:
            if self.worker is not None:
                self.worker.stop()
        except Exception:
            log.exception("Arrêt du fil caméra")
        saved = True
        try:
            if self.log is not None and not self.log.saved and self.log.worth_saving:
                saved = self.save_session(partial=True) is not None
        except Exception:
            log.exception("Séance non enregistrée")
            saved = False
        self.error_screen(saved)

    def error_screen(self, saved):
        language = (self.director.language if self.director is not None else self.profile.language) or "fr"
        title = "Un problème est survenu."
        body = ("Vos résultats sont enregistrés." if saved else
                "Vos résultats n'ont pas pu être enregistrés.") + \
            " Fermez l'application puis relancez-la. Si cela recommence, montrez le journal à votre kiné."
        buttons = (("open_logs", "Ouvrir le dossier du journal", False), ("close", "Fermer", True))
        journal = app_log.log_dir() / "mouvement.log"
        self.actions.clear()
        self.crash_boxes = []
        self.crash_text = (title, body)
        while self.window.is_open():
            output_size = self.window.output_size()
            self.viewport = canvas_viewport(CANVAS_SIZE, *output_size)
            try:
                image, self.crash_boxes = render_notice(title, body, output_size, language, self.guide, buttons,
                                                        str(journal))
            except Exception:  # even Willy failed: the same screen without him
                image, self.crash_boxes = render_notice(title, body, output_size, language, None, buttons,
                                                        str(journal))
            self.window.show(image)
            key = self.window.read_key()
            actions = [self.actions.popleft() for _ in range(len(self.actions))]
            if "open_logs" in actions:
                app_log.open_folder(app_log.log_dir())
            if "close" in actions or key in (ord('q'), ord('Q'), ESCAPE):
                break
        self.crash_boxes = None

    def start(self):
        """Open the window at once with Willy ("Je me prépare…"), then load the camera, the pose
        model, the voices and the 3D stage, refreshing the window between steps. Loading stays
        on the main thread: Panda3D, the OpenCV window and the Windows library order need it."""
        started = perf_counter()
        enable_high_dpi()
        args, config = self.args, self.config
        self.guide = shared_guide()
        self.window.open(window_size(), self.on_mouse)
        self.show_loading("")
        self.timings["first_window"] = perf_counter() - started
        # AvatarStage preloads the voice runtime, then initializes graphics before
        # the audio worker starts. Windows native library order matters here.
        if not args.no_avatars:
            self.show_loading("Préparation des avatars 3D…")
            self.avatar_stage = AvatarStage()
        # The hand model only adds palms and fingers to the avatars and costs time on every frame,
        # so it is off unless asked for (performance.hand_model: true, or --hands).
        wants_hands = not args.no_hands and (config.performance.hand_model or getattr(args, "hands", False))
        if wants_hands and HAND_MODEL_PATH.exists():
            self.hand_detector = HandDetector()
            print("[MAINS] Suivi detaille des paumes et doigts actif.")
        elif wants_hands:
            print("[MAINS] Modele optionnel absent : python models/download_models.py hand_landmarker.task")
        self.show_loading("Démarrage de la caméra…")
        c = config.camera
        index = c.index if args.camera is not None or self.profile.camera_index is None else self.profile.camera_index
        self.capture = self._devices.enter_context(VideoCaptureManager(
            camera_index=index, width=c.width, height=c.height, target_fps=c.fps, zoom=c.zoom, mirror=False))
        self.show_loading("Chargement du suivi du mouvement…")
        self.pose_model = self.chosen_pose_model()
        self.open_pose_model(self.pose_model)
        self.show_loading("Préparation de ma voix…")
        self.audio = self._devices.enter_context(AudioCoach.from_config(
            config.audio, enabled=self.profile.audio_enabled, language=self.profile.language or "fr"))
        print(self.capture.status_message)
        self.processor.model_info = self.detector.model_info.copy()
        self.director = WillyDirector(self.profile, self.audio, self.guide, has_avatars=not args.no_avatars)
        self.director.results_available = bool(session_store.session_files())
        if args.skip_home:
            self.director.screen = "dashboard"
        elif args.tour:
            self.director.replay_tour()
        else:
            self.director.open()
        self.timings["ready"] = perf_counter() - started
        print(f"[DÉMARRAGE] Fenêtre en {self.timings['first_window']:.2f} s, prêt en {self.timings['ready']:.2f} s")

    # ----------------------------------------------------------------- pose model choice
    @staticmethod
    def pose_model_installed(variant):
        from src.pose_detector import installed_pose_model
        return installed_pose_model(variant) == variant

    def chosen_pose_model(self):
        """--model, else the physio's choice, else lite if the app chose it before, else the config."""
        if self.args.model is None:
            wanted = self.profile.pose_model or ("lite" if self.profile.auto_lite else None)
            if wanted is not None and self.pose_model_installed(wanted):
                return wanted
        return self.config.pose.model

    def open_pose_model(self, variant):
        """(Re)open the pose model and the camera thread that uses it (Phase 6.4)."""
        old_worker, old_detector = self.worker, self.detector
        if old_worker is not None:
            old_worker.stop()
        self.detector = PoseDetector(model_variant=variant, num_poses=self.config.pose.num_poses)
        self.detector.choose = self.person_lock.choose  # follow only the patient (Phase 5.3)
        if old_detector is not None:
            old_detector.close()
            self._closing.remove(old_detector.close)
        self._closing.append(self.detector.close)
        self.processor.model_info = self.detector.model_info.copy()
        self.worker = PoseWorker(self.capture, self.detector, threaded=self.config.performance.pose_thread,
                                 clock=lambda: time.monotonic())
        if old_worker is not None:  # carry on the frame numbers: the last frame is not analysed twice
            self.worker._seq, self.worker._latest = old_worker._seq, old_worker._latest
            self.worker.want_pose = old_worker.want_pose
        self.worker.start()
        self._pose_check_since = None

    def check_pose_speed(self):
        """In the first 3 seconds of tracking with the full model, switch to lite if the PC is too slow."""
        limit = self.config.performance.auto_lite_fps
        if (self._pose_checked or self.pose_model != "full" or self.profile.pose_model is not None
                or not limit or self.args.model is not None or self.worker.pose_ms <= 0):
            return
        now = time.monotonic()
        if self._pose_check_since is None:
            self._pose_check_since = now
            return
        if now - self._pose_check_since < 3.:
            return
        self._pose_checked = True
        rate = 1000. / self.worker.pose_ms
        self.timings["pose_fps_full"] = round(rate, 1)
        if rate >= limit:
            return
        if not self.pose_model_installed("lite"):
            print(f"[MODELE] {rate:.0f} images/s avec le modele full. Un modele plus rapide existe : "
                  "python models/download_models.py pose_landmarker_lite.task")
            return
        print(f"[MODELE] {rate:.0f} images/s avec le modele full : passage au modele lite (plus rapide).")
        self.pose_model, self.profile.auto_lite = "lite", True
        self.profile.save()
        self.open_pose_model("lite")

    def show_loading(self, step):
        """Willy and "Je me prépare…" while the app loads (no clicks yet)."""
        language = self.profile.language or "fr"
        output_size = self.window.output_size()
        image, _ = render_notice("Je me prépare…", step, output_size, language, self.guide)
        self.window.show(image)
        self.window.pump()

    def close(self):
        self.save_session(partial=self.controls.mode in ("running", "paused"))
        if self.worker is not None:
            self.worker.stop()
        for close in self._closing:
            close()
        self._devices.close()  # audio, camera
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
        timer = self.timer
        timer.begin_frame()
        self.handle_actions()
        if self.quitting and self.director.ready_to_close(time.monotonic()):
            return False
        self.worker.want_pose = self.needs_pose()
        with timer.stage("capture"):
            result = self.worker.poll()
        if result is None:  # the camera thread has no frame yet
            self.show_loading("Démarrage de la caméra…")
            return True
        if not result.ok:
            return self.camera_lost_step()
        if self.camera_lost_since is not None:
            self.camera_lost_since = None  # the camera is back: the session goes on where it was
        new = result.seq != self._last_seq
        self._last_seq = result.seq
        timer.record("pose", self.worker.pose_ms)
        if result.detected and new:
            timer.pose_fps = 1000 / max(1., self.worker.pose_ms + self.worker.capture_ms)
        if self.modal is None:
            self.tick(result, new)
        else:
            self.frame, self.fps = result.frame, result.fps  # Willy's flow waits while modal screens are open
            if new:
                self.check_gesture(result)
        with timer.stage("draw"):
            image = self.draw()
        timer.overlay(image)
        with timer.stage("display"):
            self.window.show(image)
            key = self.window.read_key()
        if not self.window.is_open():
            return False
        return self.on_key(key)

    def needs_pose(self):
        """Run the pose model only while counting, while the tour checks the framing, or for a gesture."""
        director = self.director
        return ((director.screen == "dashboard" and self.controls.mode == "running" and self.modal is None)
                or director.wants_tracking or self.gesture_action() is not None)

    def handle_actions(self):
        while self.actions:
            action = self.actions.popleft()
            if self.modal is not None:
                self.screen.on_action(self, action)
                continue
            if action == "open_settings":
                self.open_modal("pin")
                continue
            if action in ("open_results", "results"):
                self.open_modal("results")
                continue
            if (action == "start" and self.director.screen == "dashboard" and self.controls.mode == "ready"
                    and self.director.permits(action)):
                self.ask_pain("before")  # the session starts once the pain is known
                continue
            if action == "hurt":
                self.hurt()
                continue
            if action in TOUR_ACTIONS or self.director.screen == "home" or action in ("language", "quit"):
                self.director.notify(action)
                self.quitting = self.quitting or action == "quit"
                continue
            if not self.director.permits(action):
                continue
            self.screen.on_action(self, action)

    def tick(self, result, new=True):
        """Analyse the newest camera frame (only while a session runs, or while the tour checks the
        framing). The screen may tick faster than the camera: a frame is analysed once."""
        frame, timestamp_ms = result.frame, result.timestamp_ms
        self.frame, self.fps = frame, result.fps
        previous, self.now_sec = self.now_sec, timestamp_ms / 1000.
        if self.controls.mode == "running" and self.director.screen == "dashboard":
            self.active_sec += min(.5, max(0., self.now_sec - previous))
            if self.safety is not None and self.safety.time_up(self.active_sec):
                self.director.say("E9.09")
                self.screens["dashboard"].on_action(self, "finish")
        height, width = frame.shape[:2]
        director, controls = self.director, self.controls
        alignment = None
        landmarks = result.landmarks if result.detected else None
        if director.screen == "dashboard" and controls.mode == "running":
            if new and result.detected:
                with self.timer.stage("analysis"):
                    analysis = self.processor.process(landmarks, result.world, width, height, self.now_sec)
                self.after_analysis(analysis, frame, timestamp_ms, landmarks)
                self.check_pose_speed()
            else:
                analysis = self.analysis if self.analysis is not None else FrameAnalysis(self.now_sec, metrics={})
                analysis.new_evaluation = None
        elif director.wants_tracking:
            # Camera setup of the tour: find the shoulders to check the placement, count nothing.
            analysis = FrameAnalysis(self.now_sec, landmarks=landmarks or [], metrics={}, status=controls.mode.upper())
            alignment = patient_alignment(analysis.landmarks, width, height, self.mirror,
                                          side=exercise_screen_side(self.processor.arm, self.mirror))
        else:
            analysis = FrameAnalysis(self.now_sec, metrics={}, status=controls.mode.upper())
        if controls.mode != "paused":
            self.hands_free = False
        if new:
            self.check_gesture(result)
        if self.sets is not None and self.sets.tick(time.monotonic()) == "rest_over":
            director.rest_over(self.sets.current_set + 1)
        self.analysis = analysis
        with self.timer.stage("director"):
            director.update(Moment(time.monotonic(), controls.mode, analysis, self.processor, alignment, self.mirror,
                                   self.audio.enabled is not False))
        self.follow_tour_view()
        if self.audio.status_message != self._last_audio_status:
            print(f"[AUDIO] {self.audio.status_message}")
            self._last_audio_status = self.audio.status_message

    def after_analysis(self, analysis, frame, timestamp_ms, landmarks):
        """Everything that follows a newly analysed frame during a session."""
        director = self.director
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
        if analysis.new_evaluation and self.safety is not None:
            self.check_fatigue(analysis.new_evaluation)
        if analysis.new_evaluation and self.sets is not None:
            self.count_for_plan()

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
        if self.gesture.progress > 0:
            draw_ring(display, self.viewport, self.gesture_ring_point(), self.gesture.progress)
        return display

    # ----------------------------------------------------------------- camera
    def camera_lost_step(self):
        """The camera stopped: keep the window, show it, and try again every 2 seconds."""
        if self.camera_lost_since is None:  # the camera thread retries every 2 seconds
            self.camera_lost_since = time.monotonic()
            self.say_line("E6.08")
        output_size = self.window.output_size()
        language = self.director.language
        image, _ = render_notice("Caméra déconnectée, reconnexion…", shared_script().text("E6.08", language),
                                 output_size, language, self.guide)
        self.viewport = canvas_viewport(CANVAS_SIZE, *output_size)
        self.window.show(image)
        key = self.window.read_key()
        return self.window.is_open() and key not in (ord('q'), ord('Q'), ESCAPE)

    def use_camera(self, index):
        """Switch to another camera (physio settings); back to the previous one if it can't open."""
        previous = self.capture.camera_index
        if index == previous:
            return True
        self.worker.stop()  # nobody else reads the camera while it is reopened
        try:
            self.capture.camera_index = index
            if self.capture.reconnect():
                self.profile.camera_index = index
                return True
            self.capture.camera_index = previous
            self.capture.reconnect()
            return False
        finally:
            self.worker.start()

    # ----------------------------------------------------------------- hands-free
    def gesture_action(self):
        """What the free hand held up means right now (None: no gesture here).

        Only on the session screen: pause while counting, and resume after a pause the patient
        made from a distance (gesture, or the rest between sets). Nothing is tracked on Willy's
        home or after a pause clicked at the computer, so the camera model only runs when needed.
        """
        if self.modal is not None or self.director is None or self.director.screen != "dashboard":
            return None
        mode = self.controls.mode
        if mode == "running":
            return "pause"
        if mode == "paused" and self.hands_free:
            return "resume"
        return None

    def check_gesture(self, result):
        action = self.gesture_action()
        landmarks = result.landmarks if result.detected else None
        if action is None or landmarks is None:
            self.gesture.update(None, self.processor.arm, time.monotonic())
            return
        if self.gesture.update(landmarks, self.processor.arm, time.monotonic()):
            self.actions.append(action)
            if action == "pause":
                self.hands_free = True
            self.say_line("E3.10")

    def gesture_ring_point(self):
        """Around the free wrist in the camera view; otherwise in the top-right corner."""
        wrist, frame = self.gesture.wrist, self.frame
        if (wrist is not None and frame is not None and self.modal is None and self.director.screen == "dashboard"
                and not self.controls.avatars):
            from src import layout
            stage = layout.STAGE
            height, width = frame.shape[:2]
            scale = min(stage.width / width, stage.height / height)
            x0 = stage.x0 + (stage.width - width * scale) / 2
            y0 = stage.y0 + (stage.height - height * scale) / 2
            x = 1 - wrist[0] if self.mirror else wrist[0]
            return x0 + x * width * scale, y0 + wrist[1] * height * scale
        return 1180., 120.

    # ----------------------------------------------------------------- input
    def on_mouse(self, event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONUP or self.viewport is None:
            return
        point = self.viewport.canvas_point(x, y)
        if point is None:
            return
        if self.crash_boxes is not None:  # the error screen: only its two buttons
            for action, (x1, y1, x2, y2) in self.crash_boxes:
                if x1 <= point[0] <= x2 and y1 <= point[1] <= y2:
                    self.actions.append(action)
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
        self.log = session_store.SessionLog.start(self.exercise.id, self.processor.arm, self.session_plan)
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
        self.director.results_available = True
        return path

    def say_line(self, line_id, **values):
        """Willy's voice for a line while a modal screen is shown (his flow is paused)."""
        if line_id:
            self.audio.say(shared_script().text(line_id, self.director.language, **values), self.director.language)

    def export_history(self, period):
        """PDF, CSV and session files for the physio, in Documents\\Mouvement; Willy confirms."""
        screen = self.screens["history"]
        try:
            folder = history_export.export_history(session_store.load_sessions(), period, self.director.language,
                                                   asdict(self.plan), self.profile.name, self.processor.arm)
        except (OSError, ValueError) as error:
            print(f"[EXPORT] {error}")
            screen.message = "L'export n'a pas pu être enregistré."
            return None
        screen.folder = folder
        screen.message = f"Fichiers enregistrés dans {folder.parent.name}{os.sep}{folder.name}"
        self.say_line("E8.02")
        return folder

    # ----------------------------------------------------------------- pain and safety
    def ask_pain(self, moment):
        self.screens["pain"].check = PainCheck(moment)
        self.modal = "pain"
        self.say_line(PAIN_QUESTIONS[moment])

    def pain_answer(self, value):
        check = self.screens["pain"].check
        if check.choices:
            return
        check.value = value
        if check.moment == "before":
            self.close_modal()
            self.start_session(value)
        elif check.moment == "after":
            self.close_modal()
            self.finish_with_pain(value)
        else:
            self.hurt_answer(value)

    def pain_escape(self):
        """Esc on the pain check: before, no session; after, save without it; after 'J'ai mal', end."""
        check = self.screens["pain"].check
        if check.moment == "hurt":
            self.hurt_choice("hurt_end")
            return
        self.close_modal()
        if check.moment == "after":
            self.save_session()

    def start_session(self, pain):
        """Pain 0-3: the plan; 4-6: a gentle session; 7-10: no session today (bands from the plan)."""
        band = self.plan.pain_band(pain)
        if band == "stop":
            self.log = session_store.SessionLog.start(self.exercise.id, self.processor.arm, self.plan)
            self.log.pain_before = pain
            self.save_session()
            self.say_line("E9.04")
            return
        self.session_plan = self.plan.gentle() if band == "gentle" else self.plan
        self.processor.set_plan(self.session_plan)
        self.screens["dashboard"].on_action(self, "start")
        self.log.pain_before, self.log.gentle = pain, band == "gentle"
        if band == "gentle":
            self.say_line("E9.03")
        if self.session_plan.seated:
            self.say_line("E9.12")

    def after_session(self):
        """End of a session: ask the pain again (when it was asked before), then save."""
        log = self.log
        if log is not None and not log.saved and log.pain_before is not None and log.pain_after is None:
            self.ask_pain("after")
        else:
            self.save_session()

    def finish_with_pain(self, value):
        log = self.log
        if log is not None and not log.saved:
            log.pain_after = value
            if log.pain_before is not None and value - log.pain_before >= 2:
                self.director.pain_rose = True  # Willy adds E9.06 to the end-of-session lines
        self.save_session()

    def hurt(self):
        """'J'ai mal': stop counting at once, then ask the pain level."""
        if self.controls.mode not in ("running", "paused") or self.log is None or self.modal is not None:
            return
        self.director.hurt_pressed()
        if self.controls.mode == "running":
            self.screens["dashboard"].on_action(self, "pause")
        self.log.add_stop("pain", self.now_sec - self._session_t0)
        must_end = self.safety is not None and self.safety.on_pain_stop() == "end"
        self.screens["pain"].check = PainCheck("hurt", can_continue=not must_end)
        self.modal = "pain"
        self.say_line("E9.07")
        self.say_line("E9.01")

    def hurt_answer(self, value):
        check = self.screens["pain"].check
        check.value, check.choices = value, True
        if self.log is not None and self.log.stops:
            self.log.stops[-1]["pain"] = value
        if self.session_plan.pain_band(value) == "stop":
            check.can_continue = False
            self.say_line("E9.04")
        elif not check.can_continue:
            self.say_line("E9.11")
        else:
            self.say_line("E9.08")

    def hurt_choice(self, action):
        check = self.screens["pain"].check
        self.close_modal()
        if action == "hurt_rest" and check.can_continue:
            self.session_plan = self.plan.gentle()
            self.processor.set_plan(self.session_plan)
            if self.log is not None:
                self.log.gentle = True
            self.pain_rest_until = time.monotonic() + 60.
            return
        if self.log is not None and check.value is not None:
            self.log.pain_after = check.value
        self.pain_rest_until = None
        self.director.rest_done()
        self.screens["dashboard"].on_action(self, "finish")

    def pain_rest_guidance(self):
        """The guidance column during the minute of rest after 'J'ai mal'."""
        if self.pain_rest_until is None or self.controls.mode != "paused":
            return None
        left = self.pain_rest_until - time.monotonic()
        if left > 0:
            return ("Pause après la douleur",
                    f"Reprise possible dans {max(1, round(left))} s. Relâchez l'épaule et respirez.", "PAUSE")
        return "Quand vous voulez", "Appuyez sur Reprendre pour continuer en douceur.", "PRÊT À REPRENDRE"

    def check_fatigue(self, evaluation):
        metrics = evaluation.metrics
        quality = ("unknown" if evaluation.status_label == "INDETERMINE"
                   else "correct" if evaluation.is_correct else "to_fix")
        event = self.safety.on_rep(metrics.peak_abduction_deg if metrics else None, quality,
                                   [e.category for e in evaluation.errors], time.monotonic())
        if event == "fatigue":
            self.director.say("E9.10", compact=True, interrupt=False)
            if self.log is not None:
                self.log.add_stop("fatigue", self.now_sec - self._session_t0)

    def count_for_plan(self):
        """A counted movement: at the end of a set, rest; at the end of the plan, finish."""
        event = self.sets.add_rep(time.monotonic())
        if event == "set_done":
            self.director.set_done(self.sets.current_set)
            self.screens["dashboard"].on_action(self, "pause")
            self.hands_free = True  # the patient is away from the computer: resume by gesture too
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
