"""Tool for recording and labeling local shoulder rehabilitation test clips with consent.

Ensures ethical data capture: verifies informed consent, tags ground-truth
movement quality (correct vs compensations), saves the MP4 video locally,
and appends metadata to data/annotations/ground_truth.csv.
"""

import csv
from datetime import datetime
from pathlib import Path
import sys
import time
import cv2

DATA_DIR = Path(__file__).resolve().parent / "data"
CLIPS_DIR = DATA_DIR / "recorded_clips"
ANNOTATIONS_DIR = DATA_DIR / "annotations"
GROUND_TRUTH_CSV = ANNOTATIONS_DIR / "ground_truth.csv"


def ensure_storage():
    """Ensure data directories and CSV header exist."""
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)

    if not GROUND_TRUTH_CSV.exists():
        with open(GROUND_TRUTH_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "video_file",
                "timestamp",
                "participant_id",
                "arm",
                "ground_truth_label",
                "compensation_type",
                "notes",
            ])


def main():
    ensure_storage()

    print("=" * 65)
    print("  COLLECTE ET ANNOTATION DE CLIPS VIDEOS DE TEST")
    print("  Ethique : Le consentement eclaire du participant est obligatoire.")
    print("=" * 65)

    consent = input("\n[ETHIQUE] Le participant a-t-il donne son consentement eclaire ? [o/N] : ").strip().lower()
    if consent not in ["o", "oui", "y", "yes"]:
        print("[ANNULATION] Collecte annulee : le consentement eclaire est requis.")
        sys.exit(0)

    participant_id = input("Identifiant anonyme du participant (ex: participant_01) : ").strip() or "anon_01"

    arm = ""
    while arm not in ["left", "right"]:
        arm_in = input("Bras actif [d = droit / g = gauche] : ").strip().lower()
        if arm_in in ["d", "droit", "r", "right"]:
            arm = "right"
        elif arm_in in ["g", "gauche", "l", "left"]:
            arm = "left"

    label_choice = input("Qualite de l'exercice [1 = CORRECT, 2 = A CORRIGER] : ").strip()
    ground_truth = "CORRECT" if label_choice == "1" else "A CORRIGER"

    compensation = "AUCUNE"
    if ground_truth == "A CORRIGER":
        print("\nType de compensation simulee :")
        print("  1 = Haussement d'epaule (Shrug)")
        print("  2 = Inclinaison du tronc (Trunk Lean)")
        print("  3 = Coude plie (Bent Elbow)")
        print("  4 = Vitesse excessive / Mouvement brusque")
        print("  5 = Amplitude insuffisante (< 80 deg)")
        comp_choice = input("Votre choix [1-5] : ").strip()
        comp_map = {
            "1": "HAUSSEMENT_EPAULE",
            "2": "INCLINAISON_TRONC",
            "3": "COUDE_PLIE",
            "4": "VITESSE_EXCESSIVE",
            "5": "AMPLITUDE_INSUFFISANTE",
        }
        compensation = comp_map.get(comp_choice, "AUTRE")

    notes = input("Commentaires / Notes cliniques additionnelles (optionnel) : ").strip()

    # Setup capture
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW if cv2.CAP_DSHOW else cv2.CAP_ANY)
    if not cap.isOpened():
        print("[ERREUR] Impossible d'acceder a la webcam.")
        sys.exit(1)

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
    fps = 30.0

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{participant_id}_{arm}_{ground_truth.replace(' ', '_').lower()}_{timestamp_str}.mp4"
    output_path = CLIPS_DIR / filename

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    print(f"\n[ENREGISTREMENT] Destination : {output_path.name}")
    print("Controles :")
    print("  - Appuyez sur [ESPACE] pour demarrer l'enregistrement.")
    print("  - Appuyez sur [ESPACE] ou [Q] pour terminer et sauvegarder.")

    is_recording = False
    start_time = None

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            display_frame = frame.copy()

            if not is_recording:
                cv2.putText(
                    display_frame,
                    "APPUYEZ SUR [ESPACE] POUR COMMENCER L'ENREGISTREMENT",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
            else:
                elapsed = time.time() - start_time
                cv2.circle(display_frame, (30, 35), 10, (0, 0, 255), -1)
                cv2.putText(
                    display_frame,
                    f"REC [{elapsed:4.1f}s] - Appuyez sur [ESPACE] pour arreter",
                    (55, 42),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 0, 255),
                    2,
                    cv2.LINE_AA,
                )
                out.write(frame)

            cv2.imshow("Enregistrement Clip Test", display_frame)
            key = cv2.waitKey(1) & 0xFF

            if key == 32:  # Spacebar
                if not is_recording:
                    is_recording = True
                    start_time = time.time()
                    print("[INFO] Enregistrement en cours...")
                else:
                    print("[INFO] Fin de l'enregistrement.")
                    break
            elif key in [ord("q"), ord("Q"), 27]:
                break

    finally:
        cap.release()
        out.release()
        cv2.destroyAllWindows()

    if output_path.exists() and output_path.stat().st_size > 5000:
        # Append ground truth entry
        with open(GROUND_TRUTH_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                filename,
                datetime.now().isoformat(),
                participant_id,
                arm,
                ground_truth,
                compensation,
                notes,
            ])
        print(f"\n[SUCCES] Clip enregistre avec succes : {output_path.name}")
        print(f"[METADONNEES] Ajoutees a {GROUND_TRUTH_CSV.name}")
    else:
        if output_path.exists():
            output_path.unlink()
        print("\n[ANNULATION] Fichier video vide ou non cree.")


if __name__ == "__main__":
    main()
