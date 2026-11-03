"""Local webcam coach with shared analysis and a readable dashboard."""
import sys
import argparse
from dataclasses import replace
from collections import deque
import cv2
from src.capture import VideoCaptureManager
from src.config import ExerciseConfig
from src.pose_detector import PoseDetector
from src.session_processor import SessionProcessor, FrameAnalysis
from src.dashboard import render_dashboard, CANVAS_SIZE
from src.audio_feedback import AudioCoach
from src.patient_controls import PatientControls, dashboard_action_at
from src.window_viewport import native_window_size, canvas_viewport, enable_high_dpi


def show_startup_error(error):
    print(f"[DÉMARRAGE] {error}")
    if sys.stdout is None:  # Double-click launcher: show errors instead of losing them in a hidden console.
        import tkinter as tk
        from tkinter import messagebox
        root=tk.Tk()
        root.withdraw()
        messagebox.showerror("Mouvement — besoin d’aide", f"Le suivi n’a pas pu démarrer.\nVérifiez la caméra ou demandez de l’aide pour l’installation.\n\n{error}",parent=root)
        root.destroy()


def window_size():
    width,height=1280,840
    if sys.platform == "win32":
        import ctypes
        screen_width=ctypes.windll.user32.GetSystemMetrics(0)
        screen_height=ctypes.windll.user32.GetSystemMetrics(1)
        scale=min(1,max(640,screen_width-80)/width,max(480,screen_height-100)/height)
        width,height=round(width*scale),round(height*scale)
    return width,height


def main(argv=None):
    enable_high_dpi()
    parser = argparse.ArgumentParser(description="Coach epaule : cadrage serre ou webcam externe large")
    parser.add_argument("--camera", type=int, help="Index camera, par exemple 1 pour une webcam USB")
    parser.add_argument("--width", type=int, help="Largeur de capture demandee, sans recadrage")
    parser.add_argument("--height", type=int, help="Hauteur de capture demandee")
    parser.add_argument("--zoom", type=float, help="Zoom du pilote, si pris en charge (unites du fabricant)")
    parser.add_argument("--model", choices=("lite", "full", "heavy"), help="Modele : full par defaut")
    args = parser.parse_args(argv)
    config = ExerciseConfig.from_yaml()
    overrides = {name: getattr(args, arg) for name,arg in (("index","camera"),("width","width"),("height","height"),("zoom","zoom")) if getattr(args,arg) is not None}
    try:
        config = replace(config, camera=replace(config.camera, **overrides),
                         pose=replace(config.pose, model=args.model or config.pose.model))
    except ValueError as exc:
        parser.error(str(exc))
    processor = SessionProcessor(config)
    mirror = True
    controls = PatientControls()
    actions = deque()
    now_sec = 0.
    window_name = "Mouvement - Coach epaule"
    print("L/R bras | C calibration | A audio | S bilan | M miroir | Q quitter")
    print("Deux epaules pour commencer ; coude actif visible pour compter. Visage non requis par l'application.")
    try:
        c = config.camera
        with VideoCaptureManager(camera_index=c.index, width=c.width, height=c.height, target_fps=c.fps,
                                 zoom=c.zoom, mirror=False) as cap, PoseDetector(model_variant=config.pose.model) as detector, AudioCoach.from_config(config.audio, enabled=True) as audio:
            print(cap.status_message)
            processor.model_info = detector.model_info.copy()
            # Paint at the client area's actual pixels; Win32 must not enlarge a UI bitmap.
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL | cv2.WINDOW_FREERATIO)
            cv2.resizeWindow(window_name, *window_size())
            viewport=None
            def on_mouse(event,x,y,flags,param):
                if event == cv2.EVENT_LBUTTONUP and viewport is not None:
                    point=viewport.canvas_point(x,y)
                    if point is None:
                        return
                    action=dashboard_action_at(*point,mode=controls.mode,arm=processor.arm,
                        audio_enabled=audio.enabled,details=controls.details,help_visible=controls.help_visible)
                    if action:
                        actions.append(action)
            cv2.setMouseCallback(window_name,on_mouse)
            last_audio_status = None
            quitting=False
            while True:
                while actions:
                    action=actions.popleft()
                    old_mode=controls.mode
                    if not controls.apply(action):
                        continue
                    if action == "quit":
                        quitting=True
                    elif action == "start":
                        processor.recalibrate(timestamp_sec=now_sec)
                        audio.begin_session()
                    elif action in ("pause","finish") or (action == "help" and old_mode == "running"):
                        processor.finish()
                        audio.silence()
                    elif action == "resume" and processor.calibrator.is_calibrating:
                        processor.recalibrate(timestamp_sec=now_sec)
                    elif action == "restart":
                        processor=SessionProcessor(config,processor.arm)
                        processor.model_info=detector.model_info.copy()
                        audio.silence()
                    elif action in ("arm_left","arm_right"):
                        processor.recalibrate("left" if action == "arm_left" else "right",now_sec)
                        audio.silence()
                    elif action == "audio":
                        audio.toggle()
                    elif action == "mirror":
                        mirror=not mirror
                if quitting:
                    break
                success, frame, timestamp_ms, fps = cap.read_frame()
                if not success or frame is None:
                    show_startup_error("La caméra ne répond plus. Vérifiez son branchement, puis ouvrez à nouveau Mouvement.")
                    break
                now_sec=timestamp_ms/1000.
                h, w = frame.shape[:2]
                if controls.mode == "running":
                    landmarks = detector.detect(frame, timestamp_ms)
                    analysis = processor.process(landmarks, detector.last_world_landmarks, w, h, now_sec)
                    audio.speak_cue(analysis.cue)
                    if analysis.new_evaluation:
                        audio.speak_evaluation(analysis.new_evaluation)
                else:
                    analysis=FrameAnalysis(now_sec,metrics={},status=controls.mode.upper())
                if audio.status_message != last_audio_status:
                    print(f"[AUDIO] {audio.status_message}")
                    last_audio_status = audio.status_message
                output_size=native_window_size(window_name,CANVAS_SIZE)
                display = render_dashboard(frame, analysis, processor, fps, mirror,
                    audio.enabled, audio.status_message,mode=controls.mode,details=controls.details,
                    help_visible=controls.help_visible,output_size=output_size)
                viewport=canvas_viewport(CANVAS_SIZE,*output_size)
                cv2.imshow(window_name, display)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord('q'), ord('Q'), 27) or cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                    break
                shortcuts={ord('l'):"arm_left",ord('r'):"arm_right",ord('a'):"audio",ord('s'):"finish",
                           ord('m'):"mirror",ord('h'):"help",ord('d'):"details"}
                if 65 <= key <= 90:
                    key+=32
                if key == ord('c') and controls.mode == "running":
                    processor.recalibrate(timestamp_sec=now_sec)
                    audio.silence()
                elif key == 32:
                    actions.append({"ready":"start","running":"pause","paused":"resume","finished":"restart"}[controls.mode])
                elif key in shortcuts:
                    actions.append(shortcuts[key])
    except (RuntimeError, FileNotFoundError, cv2.error) as exc:
        show_startup_error(exc)
        return 1
    finally:
        processor.finish()
        cv2.destroyAllWindows()
    session = processor.rules_engine.session
    print(f"Seance : {session.total_repetitions} tentatives terminees, {session.correct_repetitions} conformes, "
          f"{session.total_repetitions - session.assessed_repetitions} indeterminees.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
