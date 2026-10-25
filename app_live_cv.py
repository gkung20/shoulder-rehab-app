"""Phase 3: Real-time active shoulder abduction tracking with repetition counting and FSM.

Features:
- Finite State Machine with hysteresis: REST -> RISING -> HOLD -> LOWERING.
- False repetition rejection (guards against micro-jitter and aborted motions).
- Temporal tracking: concentric (raising), isometric (hold), and eccentric (lowering) durations.
- Postural compensation capture per repetition.
"""

import sys
import time
import cv2
import yaml
from pathlib import Path

from src.capture import VideoCaptureManager
from src.calibration import CalibrationManager
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
from src.smoothing import MultiMetricSmoother
from src.state_machine import RepetitionStateMachine, ExercisePhase, RepetitionMetrics
from src.visualizer import draw_hud, draw_skeleton, draw_compensations_panel


def load_config() -> dict:
    """Load configuration parameters with fallback defaults."""
    config_path = Path(__file__).resolve().parent / "config" / "exercise_config.yaml"
    if not config_path.exists():
        return {
            "thresholds": {
                "abduction": {
                    "rest_threshold_deg": 25.0,
                    "rising_start_deg": 32.0,
                    "target_min_deg": 80.0,
                    "target_max_deg": 100.0,
                },
                "compensation": {
                    "max_trunk_lean_deg": 10.0,
                    "max_shrug_ratio": 0.12,
                    "min_elbow_angle_deg": 155.0,
                },
                "timing": {
                    "min_hold_time_sec": 0.5,
                },
            },
            "filtering": {"ema_alpha": 0.35, "min_landmark_visibility": 0.6},
            "calibration": {"duration_sec": 3.0, "max_variance_ratio": 0.05},
        }
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    print("=" * 65)
    print("  KINESITHERAPIE VIRTUELLE - ABDUCTION ACTIVE DE L'EPAULE")
    print("  Phase 3 : Machine a Etats Finis & Comptage des Repetitions")
    print("=" * 65)
    print("Controles clavier:")
    print("  [L] : Suivre le bras GAUCHE")
    print("  [R] : Suivre le bras DROIT")
    print("  [C] : Lancer la CALIBRATION (restez immobile 3 secondes)")
    print("  [M] : Activer / Desactiver le mode miroir")
    print("  [Q] ou [ESC] : Quitter l'application")
    print("=" * 65)

    config = load_config()
    abd_cfg = config.get("thresholds", {}).get("abduction", {})
    rest_thresh = abd_cfg.get("rest_threshold_deg", 25.0)
    rising_start = abd_cfg.get("rising_start_deg", 32.0)
    target_min = abd_cfg.get("target_min_deg", 80.0)
    target_max = abd_cfg.get("target_max_deg", 100.0)

    comp_cfg = config.get("thresholds", {}).get("compensation", {})
    max_lean = comp_cfg.get("max_trunk_lean_deg", 10.0)
    max_shrug = comp_cfg.get("max_shrug_ratio", 0.12)
    min_elbow = comp_cfg.get("min_elbow_angle_deg", 155.0)

    timing_cfg = config.get("thresholds", {}).get("timing", {})
    min_hold = timing_cfg.get("min_hold_time_sec", 0.5)

    ema_alpha = config.get("filtering", {}).get("ema_alpha", 0.35)
    min_vis = config.get("filtering", {}).get("min_landmark_visibility", 0.6)

    calib_duration = config.get("calibration", {}).get("duration_sec", 3.0)
    calib_variance = config.get("calibration", {}).get("max_variance_ratio", 0.05)

    selected_arm = "right"
    mirror_mode = True

    smoother = MultiMetricSmoother(alpha=ema_alpha)
    calibrator = CalibrationManager(duration_sec=calib_duration, max_variance_ratio=calib_variance)
    state_machine = RepetitionStateMachine(
        rest_threshold_deg=rest_thresh,
        rising_start_deg=rising_start,
        target_min_deg=target_min,
        target_max_deg=target_max,
        min_hold_time_sec=min_hold,
        arm=selected_arm,
    )

    last_completed_rep = None

    try:
        with VideoCaptureManager(camera_index=0, width=640, height=480, mirror=mirror_mode) as cap, \
             PoseDetector() as detector:

            window_name = "Rehabilitation Epaule - Phase 3"
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window_name, 1024, 768)

            # Auto-trigger initial calibration
            calibrator.start(arm=selected_arm)

            while True:
                success, frame, timestamp_ms, fps = cap.read_frame()
                if not success or frame is None:
                    print("[AVERTISSEMENT] Perte de capture video.")
                    break

                now_sec = timestamp_ms / 1000.0

                # Detect landmarks
                landmarks = detector.detect(frame, timestamp_ms=timestamp_ms)

                abduction_raw = None
                lean_raw = None
                shrug_raw = None
                elbow_raw = None
                status = "Pret"
                calib_progress = None

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
                    vis_ok = are_landmarks_visible([shoulder, hip, elbow], min_visibility=min_vis)
                    if vis_ok:
                        abduction_raw = calculate_abduction_angle(shoulder, hip, elbow)
                    elbow_vis = are_landmarks_visible([shoulder, elbow, wrist], min_visibility=min_vis)
                    if elbow_vis:
                        elbow_raw = calculate_elbow_angle(shoulder, elbow, wrist)

                    trunk_vis = are_landmarks_visible([left_sh, right_sh, left_hip, right_hip], min_visibility=min_vis)
                    if trunk_vis:
                        lean_raw = calculate_trunk_lean(left_sh, right_sh, left_hip, right_hip)

                    if calibrator.calibrated_data.is_calibrated and are_landmarks_visible([ear, shoulder], min_visibility=min_vis):
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

                    # 4. State Machine Repetition Tracker (only if calibration done)
                    if calibrator.calibrated_data.is_calibrated:
                        new_rep = state_machine.update(
                            current_angle=abduction_smooth,
                            timestamp_sec=now_sec,
                            current_lean=lean_smooth,
                            current_shrug=shrug_smooth,
                            current_elbow=elbow_smooth,
                        )
                        if new_rep is not None:
                            last_completed_rep = new_rep
                            print(f"[REPETITION TERMINEE] #{new_rep.rep_index} ({new_rep.arm.upper()})")
                            print(f"  Angle Max : {new_rep.peak_abduction_deg:.1f} deg | Cible atteinte : {new_rep.target_reached}")
                            print(f"  Duree montee : {new_rep.concentric_duration_sec:.2f}s | Maintien : {new_rep.hold_duration_sec:.2f}s | Descente : {new_rep.eccentric_duration_sec:.2f}s")

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
                        max_lean=max_lean,
                        max_shrug=max_shrug,
                        min_elbow=min_elbow,
                    )
                else:
                    status = "Recherche patient..."
                    smoother.reset_all()

                # 7. Render HUD
                frame = draw_hud(
                    frame=frame,
                    selected_arm=selected_arm,
                    abduction_angle=smoother.get_smoother("abduction").value,
                    fps=fps,
                    status_text=status,
                    target_range=(target_min, target_max),
                    is_calibrated=calibrator.calibrated_data.is_calibrated,
                    calibration_progress=calib_progress,
                    rep_count=state_machine.rep_count,
                    current_phase=state_machine.current_phase,
                    last_completed_rep=last_completed_rep,
                )

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
                elif key in [ord("m"), ord("M")]:
                    cap.mirror = not cap.mirror
                    print(f"[INFO] Mode miroir : {'Active' if cap.mirror else 'Desactive'}")

            cv2.destroyAllWindows()

    except RuntimeError as e:
        print(f"[ERREUR MATERIELLE] {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERREUR INATTENDUE] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
