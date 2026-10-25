"""Phase 4: Real-time active shoulder abduction tracking with clinical rules engine & French feedback.

Features:
- Config-driven threshold evaluation (no hardcoded numbers).
- Real-time live coaching cues in French ("Gardez l'epaule basse", "Gardez le tronc droit", etc.).
- Post-repetition clinical evaluation ('CORRECT' vs 'A CORRIGER' with diagnostic reasons).
- Interactive session summary card (toggle with [S]).
"""

import sys
import time
import cv2
from pathlib import Path

from src.capture import VideoCaptureManager
from src.calibration import CalibrationManager
from src.config import ExerciseConfig
from src.geometry import (
    Point2D,
    PoseLandmarkIndex,
    calculate_abduction_angle,
    calculate_trunk_lean,
    calculate_shoulder_shrug,
    calculate_elbow_angle,
    are_landmarks_visible,
)
from src.pose_detector import PoseDetector
from src.rules_engine import RulesEngine, LiveFeedback, RepetitionEvaluation
from src.smoothing import MultiMetricSmoother
from src.state_machine import RepetitionStateMachine, ExercisePhase
from src.visualizer import (
    draw_hud,
    draw_skeleton,
    draw_compensations_panel,
    draw_live_feedback,
    draw_session_summary_modal,
)


def main():
    print("=" * 70)
    print("  KINESITHERAPIE VIRTUELLE - ABDUCTION ACTIVE DE L'EPAULE")
    print("  Phase 4 : Moteur de Regles Cliniques & Retours en Francais")
    print("=" * 70)
    print("Controles clavier:")
    print("  [L] : Suivre le bras GAUCHE")
    print("  [R] : Suivre le bras DROIT")
    print("  [C] : Lancer la CALIBRATION (restez immobile 3 secondes)")
    print("  [S] : Afficher / Masquer le BILAN DE LA SEANCE")
    print("  [M] : Activer / Desactiver le mode miroir")
    print("  [Q] ou [ESC] : Quitter l'application")
    print("=" * 70)

    # 1. Load configuration from YAML
    config = ExerciseConfig.from_yaml()
    rules_engine = RulesEngine(config=config)

    selected_arm = "right"
    mirror_mode = True
    show_summary_modal = False

    smoother = MultiMetricSmoother(alpha=config.filtering.ema_alpha)
    calibrator = CalibrationManager(
        duration_sec=config.calibration.duration_sec,
        max_variance_ratio=config.calibration.max_variance_ratio,
    )
    state_machine = RepetitionStateMachine(
        rest_threshold_deg=config.abduction.rest_threshold_deg,
        rising_start_deg=config.abduction.rising_start_deg,
        target_min_deg=config.abduction.target_min_deg,
        target_max_deg=config.abduction.target_max_deg,
        min_hold_time_sec=config.timing.min_hold_time_sec,
        arm=selected_arm,
    )

    last_eval: Optional[RepetitionEvaluation] = None

    try:
        with VideoCaptureManager(camera_index=0, width=640, height=480, mirror=mirror_mode) as cap, \
             PoseDetector() as detector:

            window_name = "Rehabilitation Epaule - Phase 4"
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window_name, 1024, 768)

            # Auto-trigger baseline calibration
            calibrator.start(arm=selected_arm)

            while True:
                success, frame, timestamp_ms, fps = cap.read_frame()
                if not success or frame is None:
                    print("[AVERTISSEMENT] Perte de capture video.")
                    break

                now_sec = timestamp_ms / 1000.0

                landmarks = detector.detect(frame, timestamp_ms=timestamp_ms)

                abduction_raw = None
                lean_raw = None
                shrug_raw = None
                elbow_raw = None
                status = "Pret"
                calib_progress = None
                live_cue = None

                if landmarks is not None and len(landmarks) >= 33:
                    shoulder, hip, elbow, wrist, ear = detector.get_arm_landmarks(landmarks, arm=selected_arm)
                    left_sh = landmarks[PoseLandmarkIndex.LEFT_SHOULDER]
                    right_sh = landmarks[PoseLandmarkIndex.RIGHT_SHOULDER]
                    left_hip = landmarks[PoseLandmarkIndex.LEFT_HIP]
                    right_hip = landmarks[PoseLandmarkIndex.RIGHT_HIP]

                    # 1. Calibration update
                    if calibrator.is_calibrating:
                        completed, msg = calibrator.update(landmarks, arm=selected_arm)
                        calib_progress = calibrator.get_progress()
                        status = msg
                    else:
                        status = "Suivi actif"

                    # 2. Raw Angle Calculations
                    min_v = config.filtering.min_landmark_visibility
                    vis_ok = are_landmarks_visible([shoulder, hip, elbow], min_visibility=min_v)
                    if vis_ok:
                        abduction_raw = calculate_abduction_angle(shoulder, hip, elbow)

                    elbow_vis = are_landmarks_visible([shoulder, elbow, wrist], min_visibility=min_v)
                    if elbow_vis:
                        elbow_raw = calculate_elbow_angle(shoulder, elbow, wrist)

                    trunk_vis = are_landmarks_visible([left_sh, right_sh, left_hip, right_hip], min_visibility=min_v)
                    if trunk_vis:
                        lean_raw = calculate_trunk_lean(left_sh, right_sh, left_hip, right_hip)

                    if calibrator.calibrated_data.is_calibrated and are_landmarks_visible([ear, shoulder], min_visibility=min_v):
                        shrug_raw = calculate_shoulder_shrug(
                            ear=ear,
                            shoulder=shoulder,
                            baseline_ear_shoulder_dist=calibrator.calibrated_data.baseline_ear_shoulder_dist,
                            baseline_shoulder_width=calibrator.calibrated_data.baseline_shoulder_width,
                        )

                    # 3. Apply EMA Smoothing
                    abduction_smooth = smoother.update("abduction", abduction_raw, is_valid=vis_ok)
                    lean_smooth = smoother.update("lean", lean_raw, is_valid=trunk_vis)
                    shrug_smooth = smoother.update("shrug", shrug_raw, is_valid=(shrug_raw is not None))
                    elbow_smooth = smoother.update("elbow", elbow_raw, is_valid=elbow_vis)

                    # 4. State Machine & Rules Evaluation (if calibrated)
                    if calibrator.calibrated_data.is_calibrated:
                        new_rep = state_machine.update(
                            current_angle=abduction_smooth,
                            timestamp_sec=now_sec,
                            current_lean=lean_smooth,
                            current_shrug=shrug_smooth,
                            current_elbow=elbow_smooth,
                        )

                        # Generate real-time French coaching cue
                        live_cue = rules_engine.evaluate_live_frame(
                            current_angle=abduction_smooth,
                            current_lean=lean_smooth,
                            current_shrug=shrug_smooth,
                            current_elbow=elbow_smooth,
                            current_phase=state_machine.current_phase,
                        )

                        # Evaluate completed repetition
                        if new_rep is not None:
                            last_eval = rules_engine.evaluate_repetition(new_rep)
                            print("\n" + "=" * 55)
                            print(f"[REPETITION #{last_eval.rep_index}] Statut : {last_eval.status_label}")
                            print(f"  Bras : {last_eval.arm.upper()} | Angle Max : {last_eval.metrics.peak_abduction_deg:.1f} deg")
                            print(f"  Chronometrage : Montee={last_eval.metrics.concentric_duration_sec:.1f}s | "
                                  f"Maintien={last_eval.metrics.hold_duration_sec:.1f}s | "
                                  f"Descente={last_eval.metrics.eccentric_duration_sec:.1f}s")
                            if last_eval.is_correct:
                                print("  Diagnostic : Execution parfaite !")
                            else:
                                print("  Remarques / Corrections :")
                                for r in last_eval.reasons:
                                    print(f"    - {r}")
                            print(f"  Progression de la seance : {rules_engine.session.correct_repetitions}/{rules_engine.session.total_repetitions} correctes ({rules_engine.session.success_rate_percent:.1f}%)")
                            print("=" * 55)

                    # 5. Render Skeleton
                    frame = draw_skeleton(
                        frame=frame,
                        landmarks=landmarks,
                        selected_arm=selected_arm,
                        abduction_angle=abduction_smooth,
                    )

                    # 6. Render Compensations Panel
                    frame = draw_compensations_panel(
                        frame=frame,
                        trunk_lean_deg=lean_smooth,
                        shrug_ratio=shrug_smooth,
                        elbow_angle_deg=elbow_smooth,
                        max_lean=config.compensation.max_trunk_lean_deg,
                        max_shrug=config.compensation.max_shrug_ratio,
                        min_elbow=config.compensation.min_elbow_angle_deg,
                    )

                    # 7. Render Live Coaching Cue Banner
                    frame = draw_live_feedback(frame=frame, feedback=live_cue)

                else:
                    status = "Recherche patient..."
                    smoother.reset_all()

                # 8. Render HUD
                frame = draw_hud(
                    frame=frame,
                    selected_arm=selected_arm,
                    abduction_angle=smoother.get_smoother("abduction").value,
                    fps=fps,
                    status_text=status,
                    target_range=(config.abduction.target_min_deg, config.abduction.target_max_deg),
                    is_calibrated=calibrator.calibrated_data.is_calibrated,
                    calibration_progress=calib_progress,
                    rep_count=state_machine.rep_count,
                    current_phase=state_machine.current_phase,
                    last_evaluation=last_eval,
                )

                # 9. Session Summary Card (if toggled)
                if show_summary_modal:
                    frame = draw_session_summary_modal(frame, rules_engine.session)

                cv2.imshow(window_name, frame)

                key = cv2.waitKey(1) & 0xFF
                if key in [ord("q"), ord("Q"), 27]:
                    print("\nArret demande par l'utilisateur.")
                    break
                elif key in [ord("l"), ord("L")]:
                    selected_arm = "left"
                    smoother.reset_all()
                    state_machine.set_arm("left")
                    calibrator.start(arm=selected_arm)
                    print("[INFO] Bras actif : GAUCHE (recalibration lancee)")
                elif key in [ord("r"), ord("R")]:
                    selected_arm = "right"
                    smoother.reset_all()
                    state_machine.set_arm("right")
                    calibrator.start(arm=selected_arm)
                    print("[INFO] Bras actif : DROIT (recalibration lancee)")
                elif key in [ord("c"), ord("C")]:
                    calibrator.start(arm=selected_arm)
                    print("[INFO] Recalibration demarree...")
                elif key in [ord("s"), ord("S")]:
                    show_summary_modal = not show_summary_modal
                    print(f"[INFO] Bilan de seance : {'Affiche' if show_summary_modal else 'Masque'}")
                elif key in [ord("m"), ord("M")]:
                    cap.mirror = not cap.mirror
                    print(f"[INFO] Mode miroir : {'Active' if cap.mirror else 'Desactive'}")

            cv2.destroyAllWindows()

            # Print terminal end-of-session summary
            print("\n" + "=" * 55)
            print("  BILAN FINAL DE LA SEANCE DE REHABILITATION")
            print("=" * 55)
            print(f"Total repetitions  : {rules_engine.session.total_repetitions}")
            print(f"Repetitions valides : {rules_engine.session.correct_repetitions}")
            print(f"Taux de reussite   : {rules_engine.session.success_rate_percent:.1f} %")
            errs = rules_engine.session.get_most_frequent_errors()
            if errs:
                print("Compensations posturales les plus frequentes :")
                for err, count in errs:
                    print(f"  - {err} ({count}x)")
            else:
                print("Excellente posture globale !")
            print("=" * 55)

    except RuntimeError as e:
        print(f"[ERREUR MATERIELLE] {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERREUR INATTENDUE] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
