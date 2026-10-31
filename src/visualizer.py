"""Visualizer for skeletal joints, angle telemetry, compensation metrics, HUD, and live French feedback."""

from typing import List, Optional, Tuple
import cv2
import numpy as np

from src.geometry import Point2D, PoseLandmarkIndex
from src.rules_engine import LiveFeedback, FeedbackLevel, RepetitionEvaluation, SessionSummary
from src.state_machine import ExercisePhase, RepetitionMetrics

# Standard colors in BGR format
COLOR_ACTIVE_ARM = (0, 230, 115)       # Vibrant Spring Green
COLOR_INACTIVE_ARM = (180, 180, 180)   # Subtle Gray
COLOR_TRUNK_LINE = (255, 178, 102)     # Sky Blue / Cyan
COLOR_JOINT = (255, 255, 255)          # White Joint dots
COLOR_HUD_BG = (28, 28, 28)            # Dark Slate
COLOR_WARNING = (30, 70, 255)          # Bright Red/Orange
COLOR_ALERT = (0, 165, 255)            # Amber
COLOR_SUCCESS = (0, 230, 115)          # Green
COLOR_TEXT = (245, 245, 245)           # Off-white

PHASE_FRENCH = {
    ExercisePhase.REST: "REPOS",
    ExercisePhase.RISING: "MONTEE (CONCENTRIQUE)",
    ExercisePhase.HOLD: "MAINTIEN (ISOMETRIQUE)",
    ExercisePhase.LOWERING: "DESCENTE (ECCENTRIQUE)",
}

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
    is_calibrated: bool = False,
    calibration_progress: Optional[Tuple[float, float]] = None,
    rep_count: int = 0,
    current_phase: ExercisePhase = ExercisePhase.REST,
    last_evaluation: Optional[RepetitionEvaluation] = None,
) -> np.ndarray:
    """Draw the top HUD banner with real-time status, rep counters, and phase indicators."""
    h, w = frame.shape[:2]
    hud_height = 85

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, hud_height), COLOR_HUD_BG, -1)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)

    disclaimer = "PROTOTYPE EDUCATIF - Ne pas utiliser a des fins de diagnostic. Arretez en cas de douleur vive."
    cv2.putText(frame, disclaimer, (15, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (120, 120, 230), 1, cv2.LINE_AA)

    # 1. Active Arm Indicator & Controls
    arm_label = f"BRAS : {selected_arm.upper()}"
    cv2.putText(frame, arm_label, (20, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 200), 2, cv2.LINE_AA)
    calib_badge = "[CALIBRE]" if is_calibrated else "[NON CALIBRE]"
    badge_color = (0, 230, 115) if is_calibrated else (0, 140, 255)
    cv2.putText(frame, calib_badge, (170, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.45, badge_color, 2, cv2.LINE_AA)

    phase_label = PHASE_FRENCH.get(current_phase, current_phase.value)
    phase_color = (0, 220, 255) if current_phase != ExercisePhase.REST else (180, 180, 180)
    cv2.putText(frame, f"PHASE : {phase_label}", (20, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.48, phase_color, 1, cv2.LINE_AA)

    cv2.putText(
        frame,
        "[L] Gauche | [R] Droite | [C] Calibrer | [S] Bilan | [M] Miroir | [Q] Quitter",
        (20, 74),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.36,
        (160, 160, 160),
        1,
        cv2.LINE_AA,
    )

    # 2. Angle Display
    if abduction_angle is not None:
        angle_str = f"{abduction_angle:5.1f} deg"
        in_target = target_range[0] <= abduction_angle <= target_range[1]
        angle_color = (0, 255, 120) if in_target else (255, 255, 255)

        cv2.putText(frame, "ABDUCTION :", (w // 2 - 120, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1, cv2.LINE_AA)
        cv2.putText(frame, angle_str, (w // 2 + 10, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.85, angle_color, 2, cv2.LINE_AA)

        target_str = f"Cible: [{int(target_range[0])} deg - {int(target_range[1])} deg]"
        cv2.putText(frame, target_str, (w // 2 - 120, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (160, 160, 160), 1, cv2.LINE_AA)
    else:
        cv2.putText(frame, "RECHERCHE DU PATIENT...", (w // 2 - 120, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (50, 100, 255), 2, cv2.LINE_AA)

    # 3. Repetition Counter Badge
    rep_badge_x = w - 180
    cv2.putText(frame, f"REPETITIONS : {rep_count}", (rep_badge_x, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(frame, f"FPS: {fps:4.1f}", (w - 90, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)
    cv2.putText(frame, status_text, (rep_badge_x, 74), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (100, 220, 100), 1, cv2.LINE_AA)

    # 4. Calibration Progress Bar overlay
    if calibration_progress is not None:
        ratio, remaining = calibration_progress
        bar_w = 320
        bar_h = 22
        bx = (w - bar_w) // 2
        by = hud_height + 15

        cv2.rectangle(frame, (bx - 5, by - 5), (bx + bar_w + 5, by + bar_h + 25), (30, 30, 30), -1)
        cv2.rectangle(frame, (bx, by), (bx + bar_w, by + bar_h), (80, 80, 80), -1)
        fill_w = int(bar_w * ratio)
        cv2.rectangle(frame, (bx, by), (bx + fill_w, by + bar_h), (0, 220, 255), -1)

        calib_txt = f"CALIBRATION : restez immobile... {remaining:3.1f}s"
        cv2.putText(frame, calib_txt, (bx, by + bar_h + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)

    # 5. Last Repetition Result Banner
    if last_evaluation is not None:
        last_box_y = h - 60
        cv2.rectangle(frame, (15, last_box_y), (w - 15, last_box_y + 38), (25, 25, 25), -1)
        box_border_color = (0, 230, 115) if last_evaluation.is_correct else (0, 140, 255)
        cv2.rectangle(frame, (15, last_box_y), (w - 15, last_box_y + 38), box_border_color, 2)

        verdict_color = (0, 255, 120) if last_evaluation.is_correct else (0, 165, 255)
        verdict_txt = f"REP #{last_evaluation.rep_index} [{last_evaluation.status_label}]"
        cv2.putText(frame, verdict_txt, (25, last_box_y + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, verdict_color, 2, cv2.LINE_AA)

        if last_evaluation.is_correct:
            reasons_txt = f"Execution parfaite ! (Angle max : {last_evaluation.metrics.peak_abduction_deg:.1f} deg)"
        else:
            reasons_txt = " | ".join(last_evaluation.reasons[:2])
        cv2.putText(frame, reasons_txt, (240, last_box_y + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (230, 230, 230), 1, cv2.LINE_AA)

    return frame


def draw_live_feedback(frame: np.ndarray, feedback: Optional[LiveFeedback]) -> np.ndarray:
    """Draw a centered live coaching cue banner in French."""
    if feedback is None or not feedback.message:
        return frame

    h, w = frame.shape[:2]
    banner_w = 480
    banner_h = 36
    bx = (w - banner_w) // 2
    by = 95

    bg_color = (30, 30, 30)
    text_color = (255, 255, 255)

    if feedback.level == FeedbackLevel.WARNING:
        bg_color = (20, 20, 160)       # Dark Red/Crimson
        text_color = (0, 255, 255)      # Yellow
    elif feedback.level == FeedbackLevel.SUCCESS:
        bg_color = (20, 100, 20)       # Dark Green
        text_color = (0, 255, 120)     # Bright Green

    overlay = frame.copy()
    cv2.rectangle(overlay, (bx, by), (bx + banner_w, by + banner_h), bg_color, -1)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
    cv2.rectangle(frame, (bx, by), (bx + banner_w, by + banner_h), text_color, 1)

    cv2.putText(frame, feedback.message, (bx + 15, by + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, text_color, 2, cv2.LINE_AA)
    return frame


def draw_compensations_panel(
    frame: np.ndarray,
    trunk_lean_deg: Optional[float],
    shrug_ratio: Optional[float],
    elbow_angle_deg: Optional[float],
    drift_angle_deg: Optional[float] = None,
    max_lean: float = 10.0,
    max_shrug: float = 0.12,
    min_elbow: float = 155.0,
    max_drift: float = 25.0,
) -> np.ndarray:
    """Draw a side panel displaying the four key compensatory movement metrics."""
    h, w = frame.shape[:2]
    panel_x = 20
    panel_y = 100
    panel_w = 265
    panel_h = 130

    overlay = frame.copy()
    cv2.rectangle(overlay, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), (25, 25, 25), -1)
    cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)
    cv2.rectangle(frame, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), (60, 60, 60), 1)

    cv2.putText(frame, "CONTROLE POSTURAL", (panel_x + 10, panel_y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 255), 1, cv2.LINE_AA)

    # 1. Trunk Lean
    if trunk_lean_deg is not None:
        lean_flag = trunk_lean_deg > max_lean
        lean_color = COLOR_WARNING if lean_flag else (120, 255, 120)
        lean_str = f"Inclinaison tronc : {trunk_lean_deg:4.1f} deg"
        if lean_flag:
            lean_str += " [!]"
        cv2.putText(frame, lean_str, (panel_x + 10, panel_y + 45), cv2.FONT_HERSHEY_SIMPLEX, 0.40, lean_color, 1, cv2.LINE_AA)

    # 2. Shoulder Shrug
    if shrug_ratio is not None:
        shrug_flag = shrug_ratio > max_shrug
        shrug_color = COLOR_WARNING if shrug_flag else (120, 255, 120)
        shrug_str = f"Haussement epaule : {shrug_ratio * 100:4.1f} %"
        if shrug_flag:
            shrug_str += " [!]"
        cv2.putText(frame, shrug_str, (panel_x + 10, panel_y + 68), cv2.FONT_HERSHEY_SIMPLEX, 0.40, shrug_color, 1, cv2.LINE_AA)

    # 3. Elbow Extension
    if elbow_angle_deg is not None:
        elbow_flag = elbow_angle_deg < min_elbow
        elbow_color = COLOR_WARNING if elbow_flag else (120, 255, 120)
        elbow_str = f"Extension coude   : {elbow_angle_deg:4.1f} deg"
        if elbow_flag:
            elbow_str += " [!]"
        cv2.putText(frame, elbow_str, (panel_x + 10, panel_y + 92), cv2.FONT_HERSHEY_SIMPLEX, 0.40, elbow_color, 1, cv2.LINE_AA)

    # 4. Out-of-Plane Forward Drift
    if drift_angle_deg is not None:
        drift_flag = drift_angle_deg > max_drift
        drift_color = COLOR_WARNING if drift_flag else (120, 255, 120)
        drift_str = f"Derive vers l'avant: {drift_angle_deg:4.1f} deg"
        if drift_flag:
            drift_str += " [!]"
        cv2.putText(frame, drift_str, (panel_x + 10, panel_y + 116), cv2.FONT_HERSHEY_SIMPLEX, 0.40, drift_color, 1, cv2.LINE_AA)

    return frame


def draw_session_summary_modal(frame: np.ndarray, summary: SessionSummary) -> np.ndarray:
    """Render a semi-transparent session report overlay card."""
    h, w = frame.shape[:2]
    card_w = 540
    card_h = 320
    cx = (w - card_w) // 2
    cy = (h - card_h) // 2

    overlay = frame.copy()
    cv2.rectangle(overlay, (cx, cy), (cx + card_w, cy + card_h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.92, frame, 0.08, 0, frame)
    cv2.rectangle(frame, (cx, cy), (cx + card_w, cy + card_h), (0, 220, 255), 2)

    cv2.putText(frame, "BILAN DE LA SEANCE DE REHABILITATION", (cx + 30, cy + 35), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 220, 255), 2, cv2.LINE_AA)
    cv2.line(frame, (cx + 30, cy + 48), (cx + card_w - 30, cy + 48), (80, 80, 80), 1)

    cv2.putText(frame, f"Repetitions effectuees : {summary.total_repetitions}", (cx + 35, cy + 85), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, f"Repetitions correctes  : {summary.correct_repetitions}", (cx + 35, cy + 115), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 255, 100), 1, cv2.LINE_AA)
    cv2.putText(frame, f"Taux de reussite       : {summary.success_rate_percent:.1f} %", (cx + 35, cy + 145), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 2, cv2.LINE_AA)

    cv2.putText(frame, "Compensations les plus frequentes :", (cx + 35, cy + 185), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (200, 200, 200), 1, cv2.LINE_AA)
    errors = summary.get_most_frequent_errors(top_n=3)
    if not errors:
        cv2.putText(frame, "  Aucune erreur detectee. Excellente posture !", (cx + 45, cy + 215), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 120), 1, cv2.LINE_AA)
    else:
        y_err = cy + 215
        for err_msg, count in errors:
            cv2.putText(frame, f"  - {err_msg[:45]} ({count}x)", (cx + 35, y_err), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 180, 255), 1, cv2.LINE_AA)
            y_err += 25

    cv2.putText(frame, "[Appuyez sur S pour fermer le bilan]", (cx + 120, cy + card_h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (150, 150, 150), 1, cv2.LINE_AA)
    return frame


def draw_skeleton(
    frame: np.ndarray,
    landmarks: List[Point2D],
    selected_arm: str = "right",
    abduction_angle: Optional[float] = None,
) -> np.ndarray:
    """Render skeleton lines, joint circles, and abduction angle callout."""
    h, w = frame.shape[:2]
    pixels = [lm.to_pixel(w, h) for lm in landmarks]

    # 1. Torso Core
    for idx1, idx2 in UPPER_BODY_CONNECTIONS:
        if landmarks[idx1].visibility > 0.5 and landmarks[idx2].visibility > 0.5:
            cv2.line(frame, pixels[idx1], pixels[idx2], COLOR_TRUNK_LINE, 2, cv2.LINE_AA)

    # 2. Left Arm
    left_color = COLOR_ACTIVE_ARM if selected_arm.lower() == "left" else COLOR_INACTIVE_ARM
    left_thick = 4 if selected_arm.lower() == "left" else 2
    if landmarks[PoseLandmarkIndex.LEFT_SHOULDER].visibility > 0.5 and landmarks[PoseLandmarkIndex.LEFT_ELBOW].visibility > 0.5:
        cv2.line(frame, pixels[PoseLandmarkIndex.LEFT_SHOULDER], pixels[PoseLandmarkIndex.LEFT_ELBOW], left_color, left_thick, cv2.LINE_AA)
    if landmarks[PoseLandmarkIndex.LEFT_ELBOW].visibility > 0.5 and landmarks[PoseLandmarkIndex.LEFT_WRIST].visibility > 0.5:
        cv2.line(frame, pixels[PoseLandmarkIndex.LEFT_ELBOW], pixels[PoseLandmarkIndex.LEFT_WRIST], left_color, left_thick, cv2.LINE_AA)

    # 3. Right Arm
    right_color = COLOR_ACTIVE_ARM if selected_arm.lower() == "right" else COLOR_INACTIVE_ARM
    right_thick = 4 if selected_arm.lower() == "right" else 2
    if landmarks[PoseLandmarkIndex.RIGHT_SHOULDER].visibility > 0.5 and landmarks[PoseLandmarkIndex.RIGHT_ELBOW].visibility > 0.5:
        cv2.line(frame, pixels[PoseLandmarkIndex.RIGHT_SHOULDER], pixels[PoseLandmarkIndex.RIGHT_ELBOW], right_color, right_thick, cv2.LINE_AA)
    if landmarks[PoseLandmarkIndex.RIGHT_ELBOW].visibility > 0.5 and landmarks[PoseLandmarkIndex.RIGHT_WRIST].visibility > 0.5:
        cv2.line(frame, pixels[PoseLandmarkIndex.RIGHT_ELBOW], pixels[PoseLandmarkIndex.RIGHT_WRIST], right_color, right_thick, cv2.LINE_AA)

    # 4. Joint Nodes
    active_indices = (
        [PoseLandmarkIndex.LEFT_SHOULDER, PoseLandmarkIndex.LEFT_ELBOW, PoseLandmarkIndex.LEFT_WRIST, PoseLandmarkIndex.LEFT_HIP]
        if selected_arm.lower() == "left"
        else [PoseLandmarkIndex.RIGHT_SHOULDER, PoseLandmarkIndex.RIGHT_ELBOW, PoseLandmarkIndex.RIGHT_WRIST, PoseLandmarkIndex.RIGHT_HIP]
    )

    for i in active_indices:
        if landmarks[i].visibility > 0.5:
            cv2.circle(frame, pixels[i], 6, (0, 0, 0), -1, cv2.LINE_AA)
            cv2.circle(frame, pixels[i], 4, (0, 255, 255), -1, cv2.LINE_AA)

    # 5. Abduction Angle Text
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
