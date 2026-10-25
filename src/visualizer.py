"""Visualizer for skeletal joints, angle telemetry, and user feedback overlays."""

from typing import List, Optional, Tuple
import cv2
import numpy as np

from src.geometry import Point2D, PoseLandmarkIndex

# Standard colors in BGR format
COLOR_ACTIVE_ARM = (0, 230, 115)       # Vibrant Spring Green
COLOR_INACTIVE_ARM = (180, 180, 180)   # Subtle Gray
COLOR_TRUNK_LINE = (255, 178, 102)     # Sky Blue / Cyan
COLOR_JOINT = (255, 255, 255)          # White Joint dots
COLOR_HUD_BG = (28, 28, 28)            # Dark Slate
COLOR_WARNING = (30, 70, 255)          # Bright Red/Orange
COLOR_TEXT = (245, 245, 245)           # Off-white


# Key skeletal connections for upper body visualization
UPPER_BODY_CONNECTIONS = [
    (PoseLandmarkIndex.LEFT_SHOULDER, PoseLandmarkIndex.RIGHT_SHOULDER),
    (PoseLandmarkIndex.LEFT_SHOULDER, PoseLandmarkIndex.LEFT_HIP),
    (PoseLandmarkIndex.RIGHT_SHOULDER, PoseLandmarkIndex.RIGHT_HIP),
    (PoseLandmarkIndex.LEFT_HIP, PoseLandmarkIndex.RIGHT_HIP),
]


def draw_hud(
    frame: np.ndarray,
    selected_arm: str,
    abduction_angle: Optional[float],
    fps: float,
    status_text: str = "Pret",
    target_range: Tuple[float, float] = (80.0, 100.0),
) -> np.ndarray:
    """Draw a clean, medical-tech style HUD banner at the top of the frame.

    Args:
        frame: OpenCV image in BGR format.
        selected_arm: 'left' or 'right'.
        abduction_angle: Current abduction angle in degrees (or None).
        fps: Current measured frames per second.
        status_text: Current status message.
        target_range: (min_deg, max_deg) target abduction range.

    Returns:
        Frame with rendered HUD banner.
    """
    h, w = frame.shape[:2]
    hud_height = 80

    # Semi-transparent dark overlay banner
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, hud_height), COLOR_HUD_BG, -1)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)

    # Educational prototype disclaimer bar at bottom
    disclaimer = "PROTOTYPE EDUCATIF - Arretez en cas de douleur vive"
    cv2.putText(frame, disclaimer, (15, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 100, 220), 1, cv2.LINE_AA)

    # 1. Active Arm Indicator
    arm_label = f"BRAS ACTIF : {selected_arm.upper()}"
    cv2.putText(frame, arm_label, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 200), 2, cv2.LINE_AA)
    cv2.putText(frame, "[L] Gauche  |  [R] Droite  |  [M] Miroir  |  [Q] Quitter", (20, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 180, 180), 1, cv2.LINE_AA)

    # 2. Angle Display
    if abduction_angle is not None:
        angle_str = f"{abduction_angle:5.1f} deg"
        # Green if in target range, otherwise white/amber
        in_target = target_range[0] <= abduction_angle <= target_range[1]
        angle_color = (0, 255, 120) if in_target else (255, 255, 255)

        cv2.putText(frame, "ABDUCTION :", (w // 2 - 140, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA)
        cv2.putText(frame, angle_str, (w // 2, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.9, angle_color, 2, cv2.LINE_AA)

        target_str = f"Cible: [{int(target_range[0])} deg - {int(target_range[1])} deg]"
        cv2.putText(frame, target_str, (w // 2 - 140, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 160), 1, cv2.LINE_AA)
    else:
        cv2.putText(frame, "RECHERCHE DU PATIENT...", (w // 2 - 120, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (50, 100, 255), 2, cv2.LINE_AA)

    # 3. Telemetry (FPS & Status)
    cv2.putText(frame, f"FPS: {fps:4.1f}", (w - 110, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(frame, status_text, (w - 180, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 220, 100), 1, cv2.LINE_AA)

    return frame


def draw_skeleton(
    frame: np.ndarray,
    landmarks: List[Point2D],
    selected_arm: str = "right",
    abduction_angle: Optional[float] = None,
) -> np.ndarray:
    """Render skeleton lines, joint circles, and abduction angle callout.

    Args:
        frame: BGR image frame.
        landmarks: 33 Point2D landmarks.
        selected_arm: 'left' or 'right'.
        abduction_angle: Optional calculated abduction angle to draw near shoulder.

    Returns:
        Frame with rendered skeleton.
    """
    h, w = frame.shape[:2]

    # Convert all normalized points to pixel tuples
    pixels = [lm.to_pixel(w, h) for lm in landmarks]

    # 1. Draw Torso Core
    for idx1, idx2 in UPPER_BODY_CONNECTIONS:
        if landmarks[idx1].visibility > 0.5 and landmarks[idx2].visibility > 0.5:
            cv2.line(frame, pixels[idx1], pixels[idx2], COLOR_TRUNK_LINE, 2, cv2.LINE_AA)

    # 2. Draw Left Arm
    left_color = COLOR_ACTIVE_ARM if selected_arm.lower() == "left" else COLOR_INACTIVE_ARM
    left_thick = 4 if selected_arm.lower() == "left" else 2
    if landmarks[PoseLandmarkIndex.LEFT_SHOULDER].visibility > 0.5 and landmarks[PoseLandmarkIndex.LEFT_ELBOW].visibility > 0.5:
        cv2.line(frame, pixels[PoseLandmarkIndex.LEFT_SHOULDER], pixels[PoseLandmarkIndex.LEFT_ELBOW], left_color, left_thick, cv2.LINE_AA)
    if landmarks[PoseLandmarkIndex.LEFT_ELBOW].visibility > 0.5 and landmarks[PoseLandmarkIndex.LEFT_WRIST].visibility > 0.5:
        cv2.line(frame, pixels[PoseLandmarkIndex.LEFT_ELBOW], pixels[PoseLandmarkIndex.LEFT_WRIST], left_color, left_thick, cv2.LINE_AA)

    # 3. Draw Right Arm
    right_color = COLOR_ACTIVE_ARM if selected_arm.lower() == "right" else COLOR_INACTIVE_ARM
    right_thick = 4 if selected_arm.lower() == "right" else 2
    if landmarks[PoseLandmarkIndex.RIGHT_SHOULDER].visibility > 0.5 and landmarks[PoseLandmarkIndex.RIGHT_ELBOW].visibility > 0.5:
        cv2.line(frame, pixels[PoseLandmarkIndex.RIGHT_SHOULDER], pixels[PoseLandmarkIndex.RIGHT_ELBOW], right_color, right_thick, cv2.LINE_AA)
    if landmarks[PoseLandmarkIndex.RIGHT_ELBOW].visibility > 0.5 and landmarks[PoseLandmarkIndex.RIGHT_WRIST].visibility > 0.5:
        cv2.line(frame, pixels[PoseLandmarkIndex.RIGHT_ELBOW], pixels[PoseLandmarkIndex.RIGHT_WRIST], right_color, right_thick, cv2.LINE_AA)

    # 4. Draw Joint Nodes
    active_indices = (
        [PoseLandmarkIndex.LEFT_SHOULDER, PoseLandmarkIndex.LEFT_ELBOW, PoseLandmarkIndex.LEFT_WRIST, PoseLandmarkIndex.LEFT_HIP]
        if selected_arm.lower() == "left"
        else [PoseLandmarkIndex.RIGHT_SHOULDER, PoseLandmarkIndex.RIGHT_ELBOW, PoseLandmarkIndex.RIGHT_WRIST, PoseLandmarkIndex.RIGHT_HIP]
    )

    for i in active_indices:
        if landmarks[i].visibility > 0.5:
            cv2.circle(frame, pixels[i], 6, (0, 0, 0), -1, cv2.LINE_AA)
            cv2.circle(frame, pixels[i], 4, (0, 255, 255), -1, cv2.LINE_AA)

    # 5. Draw Abduction Angle Arc and Text near the Shoulder
    if abduction_angle is not None:
        active_shoulder_idx = (
            PoseLandmarkIndex.LEFT_SHOULDER if selected_arm.lower() == "left" else PoseLandmarkIndex.RIGHT_SHOULDER
        )
        sx, sy = pixels[active_shoulder_idx]
        offset_x = 25 if selected_arm.lower() == "right" else -75
        cv2.putText(
            frame,
            f"{int(round(abduction_angle))} deg",
            (sx + offset_x, sy - 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )

    return frame
