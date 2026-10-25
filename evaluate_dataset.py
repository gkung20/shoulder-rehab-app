"""Phase 6: Batch offline video evaluation script.

Processes recorded video files, generates per-repetition CSV diagnostics,
and computes clinical statistical agreement with ground-truth human annotations
(Accuracy, Sensitivity, Specificity, F1-Score, and Confusion Matrix).
"""

import csv
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np

from src.calibration import CalibrationManager
from src.config import ExerciseConfig
from src.geometry import (
    PoseLandmarkIndex,
    calculate_abduction_angle,
    calculate_trunk_lean,
    calculate_shoulder_shrug,
    calculate_elbow_angle,
    are_landmarks_visible,
)
from src.pose_detector import PoseDetector
from src.rules_engine import RulesEngine, RepetitionEvaluation
from src.smoothing import MultiMetricSmoother
from src.state_machine import RepetitionStateMachine

DATA_DIR = Path(__file__).resolve().parent / "data"
CLIPS_DIR = DATA_DIR / "recorded_clips"
ANNOTATIONS_DIR = DATA_DIR / "annotations"
GROUND_TRUTH_CSV = ANNOTATIONS_DIR / "ground_truth.csv"
OUTPUT_DETAILS_CSV = ANNOTATIONS_DIR / "evaluation_details.csv"
OUTPUT_METRICS_CSV = ANNOTATIONS_DIR / "evaluation_metrics.csv"


@dataclass
class ConfusionMatrix:
    """Binary confusion matrix container for clinical agreement analysis."""
    true_positive: int = 0   # GT: CORRECT,      Pred: CORRECT
    false_negative: int = 0  # GT: CORRECT,      Pred: A CORRIGER
    true_negative: int = 0   # GT: A CORRIGER,   Pred: A CORRIGER
    false_positive: int = 0  # GT: A CORRIGER,   Pred: CORRECT

    @property
    def total(self) -> int:
        return self.true_positive + self.false_negative + self.true_negative + self.false_positive

    @property
    def accuracy(self) -> float:
        return (self.true_positive + self.true_negative) / max(1, self.total)

    @property
    def sensitivity(self) -> float:
        """Recall / True Positive Rate."""
        denom = self.true_positive + self.false_negative
        return self.true_positive / max(1, denom)

    @property
    def specificity(self) -> float:
        """True Negative Rate."""
        denom = self.true_negative + self.false_positive
        return self.true_negative / max(1, denom)

    @property
    def precision(self) -> float:
        """Positive Predictive Value."""
        denom = self.true_positive + self.false_positive
        return self.true_positive / max(1, denom)

    @property
    def f1_score(self) -> float:
        p, r = self.precision, self.sensitivity
        if (p + r) == 0:
            return 0.0
        return 2 * (p * r) / (p + r)


def analyze_video_file(
    video_path: Path,
    arm: str = "right",
    config: Optional[ExerciseConfig] = None,
) -> Tuple[List[RepetitionEvaluation], str]:
    """Run full offline pose and quality evaluation on a single recorded video clip.

    Args:
        video_path: Absolute path to video file.
        arm: 'left' or 'right'.
        config: Exercise configuration thresholds.

    Returns:
        Tuple of (list_of_repetition_evaluations, overall_predicted_label)
    """
    if config is None:
        config = ExerciseConfig.from_yaml()

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return [], "ERREUR_FICHIER"

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_duration_ms = 1000.0 / fps

    smoother = MultiMetricSmoother(alpha=config.filtering.ema_alpha)
    calibrator = CalibrationManager(
        duration_sec=min(2.0, config.calibration.duration_sec),
        max_variance_ratio=config.calibration.max_variance_ratio,
    )
    state_machine = RepetitionStateMachine(
        rest_threshold_deg=config.abduction.rest_threshold_deg,
        rising_start_deg=config.abduction.rising_start_deg,
        target_min_deg=config.abduction.target_min_deg,
        target_max_deg=config.abduction.target_max_deg,
        min_hold_time_sec=config.timing.min_hold_time_sec,
        arm=arm,
    )
    rules_engine = RulesEngine(config=config)

    evaluations: List[RepetitionEvaluation] = []

    with PoseDetector() as detector:
        calibrator.start(arm=arm)
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            timestamp_ms = int(frame_idx * frame_duration_ms)
            now_sec = timestamp_ms / 1000.0
            frame_idx += 1

            landmarks = detector.detect(frame, timestamp_ms=timestamp_ms)
            if not landmarks or len(landmarks) < 33:
                continue

            shoulder, hip, elbow, wrist, ear = detector.get_arm_landmarks(landmarks, arm=arm)
            left_sh = landmarks[PoseLandmarkIndex.LEFT_SHOULDER]
            right_sh = landmarks[PoseLandmarkIndex.RIGHT_SHOULDER]
            left_hip = landmarks[PoseLandmarkIndex.LEFT_HIP]
            right_hip = landmarks[PoseLandmarkIndex.RIGHT_HIP]

            # Calibration during initial rest phase
            if calibrator.is_calibrating:
                calibrator.update(landmarks, arm=arm)

            min_v = config.filtering.min_landmark_visibility
            vis_ok = are_landmarks_visible([shoulder, hip, elbow], min_visibility=min_v)
            elbow_vis = are_landmarks_visible([shoulder, elbow, wrist], min_visibility=min_v)
            trunk_vis = are_landmarks_visible([left_sh, right_sh, left_hip, right_hip], min_visibility=min_v)

            abduction_raw = calculate_abduction_angle(shoulder, hip, elbow) if vis_ok else None
            elbow_raw = calculate_elbow_angle(shoulder, elbow, wrist) if elbow_vis else None
            lean_raw = calculate_trunk_lean(left_sh, right_sh, left_hip, right_hip) if trunk_vis else None

            shrug_raw = None
            if calibrator.calibrated_data.is_calibrated and are_landmarks_visible([ear, shoulder], min_visibility=min_v):
                shrug_raw = calculate_shoulder_shrug(
                    ear=ear,
                    shoulder=shoulder,
                    baseline_ear_shoulder_dist=calibrator.calibrated_data.baseline_ear_shoulder_dist,
                    baseline_shoulder_width=calibrator.calibrated_data.baseline_shoulder_width,
                )

            abduction_smooth = smoother.update("abduction", abduction_raw, is_valid=vis_ok)
            lean_smooth = smoother.update("lean", lean_raw, is_valid=trunk_vis)
            shrug_smooth = smoother.update("shrug", shrug_raw, is_valid=(shrug_raw is not None))
            elbow_smooth = smoother.update("elbow", elbow_raw, is_valid=elbow_vis)

            # State Machine & Repetition Evaluation
            if calibrator.calibrated_data.is_calibrated:
                new_rep = state_machine.update(
                    current_angle=abduction_smooth,
                    timestamp_sec=now_sec,
                    current_lean=lean_smooth,
                    current_shrug=shrug_smooth,
                    current_elbow=elbow_smooth,
                )
                if new_rep is not None:
                    eval_result = rules_engine.evaluate_repetition(new_rep)
                    evaluations.append(eval_result)

    cap.release()

    # Determine overall video predicted label
    if not evaluations:
        predicted_label = "A CORRIGER"  # Incomplete / no valid repetition completed
    elif all(e.is_correct for e in evaluations):
        predicted_label = "CORRECT"
    else:
        predicted_label = "A CORRIGER"

    return evaluations, predicted_label


def compute_dataset_metrics(ground_truth_path: Path) -> ConfusionMatrix:
    """Evaluate all annotated video clips in ground_truth_path and compute confusion matrix."""
    if not ground_truth_path.exists():
        raise FileNotFoundError(f"Annotation file not found at {ground_truth_path}")

    config = ExerciseConfig.from_yaml()
    cm = ConfusionMatrix()

    detailed_records = []

    with open(ground_truth_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("[INFO] Le fichier d'annotations est vide.")
        return cm

    print(f"\n[EVALUATION] Traitement de {len(rows)} clips videos annotees...")
    print("-" * 75)
    print(f"{'Fichier Video':<32} {'Bras':<6} {'Verite Terrain':<15} {'Prediction':<15} {'Resultat'}")
    print("-" * 75)

    for row in rows:
        filename = row.get("video_file", "").strip()
        arm = row.get("arm", "right").strip().lower()
        gt_label = row.get("ground_truth_label", "").strip().upper()

        video_path = CLIPS_DIR / filename
        if not video_path.exists():
            print(f"[MANQUANT] {filename} introuvable dans {CLIPS_DIR}")
            continue

        evals, pred_label = analyze_video_file(video_path, arm=arm, config=config)

        # Update Confusion Matrix
        if gt_label == "CORRECT" and pred_label == "CORRECT":
            cm.true_positive += 1
            match_status = "OK (Vrai Positif)"
        elif gt_label == "CORRECT" and pred_label == "A CORRIGER":
            cm.false_negative += 1
            match_status = "ERREUR (Faux Negatif)"
        elif gt_label == "A CORRIGER" and pred_label == "A CORRIGER":
            cm.true_negative += 1
            match_status = "OK (Vrai Negatif)"
        elif gt_label == "A CORRIGER" and pred_label == "CORRECT":
            cm.false_positive += 1
            match_status = "ERREUR (Faux Positif)"
        else:
            match_status = "INDETERMINE"

        print(f"{filename[:30]:<32} {arm.upper():<6} {gt_label:<15} {pred_label:<15} {match_status}")

        # Store detailed record
        reasons_combined = "; ".join(
            [r for e in evals for r in e.reasons]
        ) if evals else "Aucune repetition completee"

        detailed_records.append({
            "video_file": filename,
            "arm": arm,
            "ground_truth_label": gt_label,
            "predicted_label": pred_label,
            "agreement": (gt_label == pred_label),
            "nb_reps": len(evals),
            "reasons": reasons_combined,
        })

    # Save detailed CSV
    if detailed_records:
        with open(OUTPUT_DETAILS_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=detailed_records[0].keys())
            writer.writeheader()
            writer.writerows(detailed_records)

    return cm


def print_clinical_report(cm: ConfusionMatrix) -> None:
    """Print ASCII confusion matrix and statistical agreement metrics."""
    print("\n" + "=" * 65)
    print("  RAPPORT D'EVALUATION CLINIQUE & MATRICE DE CONFUSION")
    print("=" * 65)

    print("\n                  PREDICTION ALGORITHMIQUE")
    print("                  CORRECT          A CORRIGER")
    print(f"VERITE  CORRECT   TP = {cm.true_positive:<12} FN = {cm.false_negative}")
    print(f"TERRAIN A CORR.   FP = {cm.false_positive:<12} TN = {cm.true_negative}")

    print("\n" + "-" * 65)
    print("METRIQUES STATISTIQUES D'ACCORD CLINIQUE :")
    print(f"  Exactitude (Accuracy)    : {cm.accuracy * 100:6.2f} %")
    print(f"  Sensibilite (Recall)     : {cm.sensitivity * 100:6.2f} % (Taux de detection des reps correctes)")
    print(f"  Specificite              : {cm.specificity * 100:6.2f} % (Taux de detection des compensations)")
    print(f"  Precision                : {cm.precision * 100:6.2f} %")
    print(f"  F1-Score                 : {cm.f1_score * 100:6.2f} %")
    print("=" * 65)

    # Save metrics CSV
    with open(OUTPUT_METRICS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        writer.writerow(["total_samples", cm.total])
        writer.writerow(["true_positive", cm.true_positive])
        writer.writerow(["false_negative", cm.false_negative])
        writer.writerow(["true_negative", cm.true_negative])
        writer.writerow(["false_positive", cm.false_positive])
        writer.writerow(["accuracy_percent", round(cm.accuracy * 100, 2)])
        writer.writerow(["sensitivity_recall_percent", round(cm.sensitivity * 100, 2)])
        writer.writerow(["specificity_percent", round(cm.specificity * 100, 2)])
        writer.writerow(["precision_percent", round(cm.precision * 100, 2)])
        writer.writerow(["f1_score_percent", round(cm.f1_score * 100, 2)])

    print(f"[RAPPORT] Resultats detailles sauvegardes dans : {OUTPUT_DETAILS_CSV.name}")
    print(f"[RAPPORT] Metriques globales sauvegardees dans  : {OUTPUT_METRICS_CSV.name}\n")


def main():
    if not GROUND_TRUTH_CSV.exists():
        print(f"[ERREUR] Fichier d'annotations introuvable : {GROUND_TRUTH_CSV}")
        print("Utilisez 'python record_clip.py' pour enregistrer et annoter vos clips.")
        sys.exit(1)

    cm = compute_dataset_metrics(GROUND_TRUTH_CSV)
    if cm.total > 0:
        print_clinical_report(cm)


if __name__ == "__main__":
    main()
