"""Quick Turnkey Demo Script for Shoulder Rehabilitation Assistant.

Provides:
1. Automated simulation mode (runs headless without camera, generating telemetry,
   state machine transitions, and clinical diagnostic feedback).
2. Live interactive mode (launches webcam tracking).
"""

import argparse
import sys
import time

from src.config import ExerciseConfig
from src.rules_engine import RulesEngine
from src.state_machine import ExercisePhase, RepetitionStateMachine


def run_simulation():
    """Run an automated synthetic simulation of correct and compensatory repetitions."""
    print("=" * 70)
    print("  DEMONSTRATION SIMULEE : KINESITHERAPIE VIRTUELLE")
    print("  Evaluation de l'Abduction Active de l'Epaule sans webcam")
    print("=" * 70)

    config = ExerciseConfig.from_yaml()
    rules_engine = RulesEngine(config=config)
    sm = RepetitionStateMachine(
        rest_threshold_deg=config.abduction.rest_threshold_deg,
        rising_start_deg=config.abduction.rising_start_deg,
        target_min_deg=config.abduction.target_min_deg,
        target_max_deg=config.abduction.target_max_deg,
        min_hold_time_sec=config.timing.min_hold_time_sec,
        arm="right",
    )

    scenarios = [
        {
            "name": "Scenario 1 : Repetition Parfaite (Bonne forme)",
            "angles": [10, 15, 20, 35, 55, 75, 88, 90, 90, 90, 88, 70, 55, 40, 28, 18],
            "lean": 2.5,
            "shrug": 0.03,
            "elbow": 176.0,
            "step_dt": 0.35,
        },
        {
            "name": "Scenario 2 : Compensation Posturale (Haussement d'epaule & Tronc incline)",
            "angles": [10, 25, 40, 60, 80, 86, 86, 85, 60, 40, 18],
            "lean": 15.2,  # > 10.0 deg
            "shrug": 0.22,  # > 12%
            "elbow": 170.0,
            "step_dt": 0.35,
        },
        {
            "name": "Scenario 3 : Mouvement Trop Rapide & Coude Plie",
            "angles": [10, 35, 85, 85, 45, 15],
            "lean": 2.0,
            "shrug": 0.02,
            "elbow": 140.0,  # < 155.0 deg
            "drift": 0.0,
            "step_dt": 0.15,  # Too fast
        },
        {
            "name": "Scenario 4 : Compensation 3D (Projection du bras vers l'avant - Antepulsion)",
            "angles": [12, 28, 48, 68, 88, 88, 86, 62, 42, 16],
            "lean": 2.0,
            "shrug": 0.03,
            "elbow": 175.0,
            "drift": 34.0,  # > 25.0 deg (hors plan 3D)
            "step_dt": 0.35,
        },
    ]

    sim_time = 0.0

    for sc in scenarios:
        print(f"\n--- {sc['name']} ---")
        last_eval = None

        for angle in sc["angles"]:
            sim_time += sc["step_dt"]

            # 1. State machine update
            rep_result = sm.update(
                current_angle=float(angle),
                timestamp_sec=sim_time,
                current_lean=sc["lean"],
                current_shrug=sc["shrug"],
                current_elbow=sc["elbow"],
                current_drift=sc.get("drift", 0.0),
            )

            # 2. Live coaching cue
            cue = rules_engine.evaluate_live_frame(
                current_angle=float(angle),
                current_lean=sc["lean"],
                current_shrug=sc["shrug"],
                current_elbow=sc["elbow"],
                current_phase=sm.current_phase,
                current_drift=sc.get("drift", 0.0),
            )

            print(f"  [t={sim_time:4.2f}s | Phase: {sm.current_phase.value:<8} | Angle: {angle:3.0f} deg] -> Retransmission : {cue.message}")

            if rep_result is not None:
                last_eval = rules_engine.evaluate_repetition(rep_result)

        if last_eval is not None:
            verdict = "VALIDE" if last_eval.is_correct else "INVALIDE"
            print(f"\n  >> VERDICT CLINIQUE : Repetition #{last_eval.rep_index} [{last_eval.status_label}] ({verdict})")
            if last_eval.is_correct:
                print("     Aucune compensation detectee. Mouvement fluide et controle !")
            else:
                print("     Anomalies detectees :")
                for r in last_eval.reasons:
                    print(f"       * {r}")

    # Session Summary Report
    print("\n" + "=" * 70)
    print("  SYNTHESE DE FIN DE SEANCE (REPORT CARD)")
    print("=" * 70)
    session = rules_engine.session
    print(f"Total repetitions executees : {session.total_repetitions}")
    print(f"Repetitions correctes       : {session.correct_repetitions}")
    print(f"Taux d'accord clinique      : {session.success_rate_percent:.1f} %")
    print("Compensations les plus frequentes :")
    for err, count in session.get_most_frequent_errors():
        print(f"  - {err} ({count} occurrence(s))")
    print("=" * 70)
    print("\n[OK] Demonstration simulee terminee avec succes !")


def main():
    parser = argparse.ArgumentParser(description="Demonstrateur pour l'application de reeducation de l'epaule.")
    parser.add_argument("--live", action="store_true", help="Lancer directement la camera en direct")
    args = parser.parse_args()

    if args.live:
        from app_live_cv import main as live_main
        live_main()
    else:
        run_simulation()
        print("\nPour lancer la camera en direct : python demo.py --live")
        print("Pour lancer l'interface web     : streamlit run app_streamlit.py")


if __name__ == "__main__":
    main()
