"""Phase 6: Batch offline video evaluation script.

Processes recorded video files, generates per-repetition CSV diagnostics,
and computes clinical statistical agreement with ground-truth human annotations
(Accuracy, Sensitivity, Specificity, F1-Score, and Confusion Matrix).
"""

import csv
import math
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Dict, List, Optional, Tuple
import cv2
from src.config import ExerciseConfig
from src.pose_detector import PoseDetector
from src.rules_engine import RepetitionEvaluation
from src.state_machine import ExercisePhase

DATA_DIR = Path(__file__).resolve().parent / "data"
CLIPS_DIR = DATA_DIR / "recorded_clips"
ANNOTATIONS_DIR = DATA_DIR / "annotations"
GROUND_TRUTH_CSV = ANNOTATIONS_DIR / "ground_truth.csv"
OUTPUT_DETAILS_CSV = ANNOTATIONS_DIR / "evaluation_details.csv"
OUTPUT_METRICS_CSV = ANNOTATIONS_DIR / "evaluation_metrics.csv"
OUTPUT_GROUPS_CSV = ANNOTATIONS_DIR / "evaluation_groups.csv"


@dataclass
class ConfusionMatrix:
    """Binary confusion matrix container for clinical agreement analysis."""
    true_positive: int = 0   # GT: CORRECT,      Pred: CORRECT
    false_negative: int = 0  # GT: CORRECT,      Pred: A CORRIGER
    true_negative: int = 0   # GT: A CORRIGER,   Pred: A CORRIGER
    false_positive: int = 0
    unassessed: int = 0

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

    from src.session_processor import SessionProcessor
    processor = SessionProcessor(config, arm)
    cap = cv2.VideoCapture(str(video_path))
    try:
        if not cap.isOpened():
            return [], "ERREUR_FICHIER"
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(fps) or fps <= 0:
            return [], "ERREUR_FPS"
        with PoseDetector(model_variant=config.pose.model) as detector:
            processor.model_info = getattr(detector, "model_info", {}).copy()
            frame_idx = 0
            while True:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                timestamp_sec = frame_idx / fps
                frame_idx += 1
                landmarks = detector.detect(frame, int(timestamp_sec * 1000))
                h, w = frame.shape[:2]
                processor.process(landmarks, detector.last_world_landmarks, w, h, timestamp_sec)
    finally:
        cap.release()
    evaluations = processor.rules_engine.session.evaluations
    if (not evaluations or any(e.status_label == "INDETERMINE" for e in evaluations)
            or processor.interrupted_attempts or processor.state_machine.current_phase != ExercisePhase.REST):
        return evaluations, "INDETERMINE"
    return evaluations, "CORRECT" if all(e.is_correct for e in evaluations) else "A CORRIGER"


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
        # An annotation may name a clip, never escape the private clips directory.
        if not video_path.resolve().is_relative_to(CLIPS_DIR.resolve()):
            cm.unassessed += 1
            detailed_records.append({"video_file": filename, "arm": arm,
                "ground_truth_label": gt_label, "predicted_label": "ERREUR_CHEMIN",
                "agreement": "", "nb_reps": 0, "reasons": "Chemin de clip invalide"})
            continue
        if not video_path.exists():
            print(f"[MANQUANT] {filename} introuvable dans {CLIPS_DIR}")
            cm.unassessed += 1
            detailed_records.append({"video_file": filename, "arm": arm,
                "ground_truth_label": gt_label, "predicted_label": "ERREUR_FICHIER",
                "agreement": "", "nb_reps": 0, "reasons": "Fichier manquant"})
            continue

        if gt_label not in ("CORRECT", "A CORRIGER") or arm not in ("left", "right"):
            cm.unassessed += 1
            detailed_records.append({"video_file": filename, "arm": arm,
                "ground_truth_label": gt_label, "predicted_label": "ERREUR_ANNOTATION",
                "agreement": "", "nb_reps": 0, "reasons": "Annotation invalide"})
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
            cm.unassessed += 1

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
            "agreement": (gt_label == pred_label) if pred_label in ("CORRECT", "A CORRIGER") else "",
            "nb_reps": len(evals),
            "reasons": reasons_combined,
        })

    # Each annotation has a record, including missing files and invalid labels.
    for record, row in zip(detailed_records, rows):
        for key in ("participant_id", "lighting", "camera_view", "clothing", "compensation_type"):
            record[key] = row.get(key, "").strip()
    # Save detailed CSV
    if detailed_records:
        with open(OUTPUT_DETAILS_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=detailed_records[0].keys())
            writer.writeheader()
            writer.writerows(detailed_records)
        with open(OUTPUT_GROUPS_CSV, "w", newline="", encoding="utf-8") as f:
            grouped = summarize_groups(detailed_records)
            writer = csv.DictWriter(f, fieldnames=grouped[0].keys())
            writer.writeheader()
            writer.writerows(grouped)

    return cm


def summarize_groups(records):
    """Describe observed subgroup agreement and missingness, without inferring identity."""
    output = []
    for dimension in ("participant_id", "arm", "lighting", "camera_view", "clothing", "compensation_type"):
        values = sorted({r.get(dimension, "") for r in records if r.get(dimension, "")})
        for value in values:
            subset = [r for r in records if r.get(dimension) == value]
            cm = ConfusionMatrix()
            for row in subset:
                gt, pred = row["ground_truth_label"], row["predicted_label"]
                if gt not in ("CORRECT", "A CORRIGER") or pred not in ("CORRECT", "A CORRIGER"):
                    cm.unassessed += 1
                elif gt == "CORRECT" and pred == "CORRECT":
                    cm.true_positive += 1
                elif gt == "CORRECT":
                    cm.false_negative += 1
                elif pred == "CORRECT":
                    cm.false_positive += 1
                else:
                    cm.true_negative += 1
            output.append({"dimension": dimension, "group": value, "clips": len(subset),
                "assessed": cm.total, "unassessed": cm.unassessed,
                "coverage_percent": round(100 * cm.total / len(subset), 2),
                "accuracy_percent": round(cm.accuracy * 100, 2) if cm.total else "",
                "false_approvals": cm.false_positive, "false_corrections": cm.false_negative})
    return output or [{"dimension": "all", "group": "unknown", "clips": len(records),
        "assessed": 0, "unassessed": len(records), "coverage_percent": 0,
        "accuracy_percent": "", "false_approvals": 0, "false_corrections": 0}]


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
    print(f"Clips evaluables : {cm.total} / {cm.total + cm.unassessed}")
    print(f"Clips non evaluables (exclus des scores) : {cm.unassessed}")
    print("METRIQUES DU PROTOTYPE SUR LES CLIPS EVALUABLES :")
    metric_values = (
        ("accuracy_percent", cm.accuracy, cm.total),
        ("sensitivity_recall_percent", cm.sensitivity, cm.true_positive + cm.false_negative),
        ("specificity_percent", cm.specificity, cm.true_negative + cm.false_positive),
        ("precision_percent", cm.precision, cm.true_positive + cm.false_positive),
        ("f1_score_percent", cm.f1_score, 2 * cm.true_positive + cm.false_positive + cm.false_negative),
    )
    for name, value, denominator in metric_values:
        shown = f"{value * 100:.2f} %" if denominator else "non calculable"
        print(f"  {name}: {shown}")
    print("=" * 65)

    # Save metrics CSV
    with open(OUTPUT_METRICS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        writer.writerow(["assessed_samples", cm.total])
        writer.writerow(["unassessed_samples", cm.unassessed])
        writer.writerow(["assessment_coverage_percent", round(100 * cm.total / (cm.total + cm.unassessed), 2) if cm.total + cm.unassessed else 0])
        writer.writerow(["true_positive", cm.true_positive])
        writer.writerow(["false_negative", cm.false_negative])
        writer.writerow(["true_negative", cm.true_negative])
        writer.writerow(["false_positive", cm.false_positive])
        for name, value, denominator in metric_values:
            writer.writerow([name, round(value * 100, 2) if denominator else ""])

    print(f"[RAPPORT] Resultats detailles sauvegardes dans : {OUTPUT_DETAILS_CSV.name}")
    print(f"[RAPPORT] Metriques globales sauvegardees dans  : {OUTPUT_METRICS_CSV.name}\n")


def main():
    if not GROUND_TRUTH_CSV.exists():
        print(f"[ERREUR] Fichier d'annotations introuvable : {GROUND_TRUTH_CSV}")
        print("Utilisez 'python record_clip.py' pour enregistrer et annoter vos clips.")
        sys.exit(1)

    cm = compute_dataset_metrics(GROUND_TRUTH_CSV)
    if cm.total + cm.unassessed > 0:
        print_clinical_report(cm)


if __name__ == "__main__":
    main()
