"""Phase 1: Real-time active shoulder abduction tracking application.

Uses OpenCV for ultra-low-latency display and MediaPipe Tasks PoseLandmarker
for 33-point skeletal landmark detection.
"""

import sys
import cv2
import yaml
from pathlib import Path

from src.capture import VideoCaptureManager
from src.geometry import (
    Point2D,
    calculate_abduction_angle,
    are_landmarks_visible,
)
from src.pose_detector import PoseDetector
from src.visualizer import draw_hud, draw_skeleton


def load_config() -> dict:
    """Load placeholder configuration parameters."""
    config_path = Path(__file__).resolve().parent / "config" / "exercise_config.yaml"
    if not config_path.exists():
        return {
            "thresholds": {"abduction": {"target_min_deg": 80.0, "target_max_deg": 100.0}},
            "filtering": {"min_landmark_visibility": 0.6},
        }
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    print("=" * 65)
    print("  KINESITHERAPIE VIRTUELLE - ABDUCTION ACTIVE DE L'EPAULE")
    print("  Prototype educatif (Phase 1)")
    print("=" * 65)
    print("Controles clavier:")
    print("  [L] : Suivre le bras GAUCHE")
    print("  [R] : Suivre le bras DROIT")
    print("  [M] : Activer / Desactiver l'effet miroir de la camera")
    print("  [Q] ou [ESC] : Quitter l'application")
    print("=" * 65)

    config = load_config()
    target_min = config.get("thresholds", {}).get("abduction", {}).get("target_min_deg", 80.0)
    target_max = config.get("thresholds", {}).get("abduction", {}).get("target_max_deg", 100.0)
    min_vis = config.get("filtering", {}).get("min_landmark_visibility", 0.6)

    selected_arm = "right"
    mirror_mode = True

    try:
        with VideoCaptureManager(camera_index=0, width=640, height=480, mirror=mirror_mode) as cap, \
             PoseDetector() as detector:

            window_name = "Rehabilitation Epaule - Phase 1"
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window_name, 960, 720)

            while True:
                success, frame, timestamp_ms, fps = cap.read_frame()
                if not success or frame is None:
                    print("[AVERTISSEMENT] Erreur de lecture de flux camera.")
                    break

                # 1. Pose detection via MediaPipe Tasks
                landmarks = detector.detect(frame, timestamp_ms=timestamp_ms)

                abduction_angle = None
                status = "Patient detecte"

                if landmarks is not None and len(landmarks) >= 33:
                    # Extract joints for the selected arm
                    shoulder, hip, elbow, wrist, ear = detector.get_arm_landmarks(landmarks, arm=selected_arm)

                    # Gating: check if key joints for abduction are visible enough
                    if are_landmarks_visible([shoulder, hip, elbow], min_visibility=min_vis):
                        abduction_angle = calculate_abduction_angle(shoulder=shoulder, hip=hip, elbow=elbow)
                    else:
                        status = "Visibilite articulaire faible"

                    # 2. Draw Skeleton
                    frame = draw_skeleton(
                        frame=frame,
                        landmarks=landmarks,
                        selected_arm=selected_arm,
                        abduction_angle=abduction_angle,
                    )
                else:
                    status = "Recherche patient..."

                # 3. Draw HUD Banner
                frame = draw_hud(
                    frame=frame,
                    selected_arm=selected_arm,
                    abduction_angle=abduction_angle,
                    fps=fps,
                    status_text=status,
                    target_range=(target_min, target_max),
                )

                cv2.imshow(window_name, frame)

                key = cv2.waitKey(1) & 0xFF
                if key in [ord("q"), ord("Q"), 27]:  # 'q' or ESC
                    print("\nArret demande par l'utilisateur.")
                    break
                elif key in [ord("l"), ord("L")]:
                    selected_arm = "left"
                    print("[INFO] Bras actif selectionne : GAUCHE")
                elif key in [ord("r"), ord("R")]:
                    selected_arm = "right"
                    print("[INFO] Bras actif selectionne : DROIT")
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
