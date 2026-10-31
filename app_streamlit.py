"""Phase 5: Interactive Streamlit Rehabilitation Dashboard for Active Shoulder Abduction.

Features:
- Prominent medical & educational disclaimer with acute pain warning.
- Left / Right arm selector.
- Adjustable clinical threshold sliders with clearly marked placeholder values.
- Real-time video streaming with skeletal tracking, angle telemetry, and French feedback.
- Comprehensive session report dashboard with KPI metrics, error charts, and CSV export.
"""

import io
import time
from typing import Optional
import cv2
import numpy as np
import pandas as pd
import streamlit as st

from src.calibration import CalibrationManager
from src.config import (
    ExerciseConfig,
    AbductionThresholds,
    CompensationThresholds,
    TimingThresholds,
    FilteringConfig,
    CalibrationConfig,
)
from src.geometry import (
    Point2D,
    PoseLandmarkIndex,
    calculate_abduction_angle,
    calculate_trunk_lean,
    calculate_shoulder_shrug,
    calculate_elbow_angle,
    calculate_anterior_drift_angle,
    are_landmarks_visible,
)
from src.pose_detector import PoseDetector
from src.rules_engine import RulesEngine, RepetitionEvaluation, FeedbackLevel
from src.smoothing import MultiMetricSmoother
from src.state_machine import RepetitionStateMachine, ExercisePhase
from src.audio_feedback import AudioCoach
from src.visualizer import (
    draw_hud,
    draw_skeleton,
    draw_compensations_panel,
    draw_live_feedback,
)

# Page configuration
st.set_page_config(
    page_title="Kinésithérapie Virtuelle - Abduction Épaule",
    page_icon="🦾",
    layout="wide",
    initial_sidebar_state="expanded",
)


def initialize_session_state():
    """Initialize persistent Streamlit session variables."""
    if "rules_engine" not in st.session_state:
        st.session_state.rules_engine = RulesEngine(ExerciseConfig.from_yaml())
    if "repetition_logs" not in st.session_state:
        st.session_state.repetition_logs = []
    if "is_running" not in st.session_state:
        st.session_state.is_running = False
    if "audio_coach" not in st.session_state:
        st.session_state.audio_coach = AudioCoach(enabled=True)


initialize_session_state()

# ------------------------------------------------------------------------------
# Medical & Educational Disclaimer Banner
# ------------------------------------------------------------------------------
st.markdown(
    """
    <div style="background-color: #ffebee; border-left: 6px solid #d32f2f; padding: 14px 18px; border-radius: 4px; margin-bottom: 20px;">
        <h4 style="color: #b71c1c; margin: 0 0 6px 0;">⚠️ AVERTISSEMENT MÉDICAL & PROTOTYPE ÉDUCATIF</h4>
        <p style="color: #333333; margin: 0; font-size: 0.92rem;">
            Cette application est un <strong>prototype universitaire expérimental</strong> à visée purement pédagogique.
            Elle <strong>ne constitue en aucun cas un dispositif médical certifié</strong> ni un outil d'autodiagnostic.<br>
            <strong style="color: #c62828;">ARRÊTEZ IMMÉDIATEMENT L'EXERCICE si vous ressentez une douleur vive ou une sensation d'accrochage articulaire.</strong>
            Consultez toujours votre kinésithérapeute ou votre médecin rééducateur avant d'ajuster les seuils angulaires.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------------------
# Sidebar: Patient Selection & Physiotherapist Sliders
# ------------------------------------------------------------------------------
st.sidebar.title("Paramètres Cliniques")
st.sidebar.caption("Prototype éducatif - Valeurs indicatives à confirmer par un praticien")

# 1. Arm Selection
selected_arm_label = st.sidebar.radio(
    "Bras à rééduquer :",
    options=["Bras Droit", "Bras Gauche"],
    index=0,
)
selected_arm = "right" if selected_arm_label == "Bras Droit" else "left"

# Audio Coach Toggle
enable_tts = st.sidebar.checkbox("🔊 Coaching vocal français (TTS)", value=True)
if "audio_coach" in st.session_state and st.session_state.audio_coach is not None:
    st.session_state.audio_coach.enabled = enable_tts

# 2. Target Range Sliders
st.sidebar.subheader("Amplitude Cible (Abduction)")
col_s1, col_s2 = st.sidebar.columns(2)
with col_s1:
    target_min_deg = st.slider("Cible Min (°)", min_value=45.0, max_value=120.0, value=80.0, step=5.0)
with col_s2:
    target_max_deg = st.slider("Cible Max (°)", min_value=70.0, max_value=150.0, value=100.0, step=5.0)

overshoot_deg = st.sidebar.slider("Alerte dépassement haut (°)", 90.0, 160.0, 110.0, 5.0)

# 3. Postural Compensation Limits
st.sidebar.subheader("Seuils de Compensation")
max_shrug_pct = st.sidebar.slider("Haussement d'épaule max (% largeur)", 5, 25, 12, 1)
max_shrug_ratio = max_shrug_pct / 100.0

max_lean_deg = st.sidebar.slider("Inclinaison max du tronc (°)", 3.0, 25.0, 10.0, 1.0)
min_elbow_deg = st.sidebar.slider("Extension coude min (°)", 130.0, 180.0, 155.0, 5.0)
max_drift_deg = st.sidebar.slider("Dérive max vers l'avant (hors plan 3D) (°)", 10.0, 45.0, 25.0, 1.0)

# 4. Phase Speeds
st.sidebar.subheader("Chronométrie (Contrôle moteur)")
min_concentric_s = st.sidebar.slider("Temps de montée min (s)", 0.5, 3.0, 1.0, 0.25)
min_hold_s = st.sidebar.slider("Temps de maintien min (s)", 0.0, 3.0, 0.5, 0.25)
min_eccentric_s = st.sidebar.slider("Temps de descente min (s)", 0.5, 3.0, 1.0, 0.25)

# Build dynamic config from sidebar values
current_config = ExerciseConfig(
    abduction=AbductionThresholds(
        target_min_deg=target_min_deg,
        target_max_deg=target_max_deg,
        overshoot_warn_deg=overshoot_deg,
    ),
    compensation=CompensationThresholds(
        max_trunk_lean_deg=max_lean_deg,
        max_shrug_ratio=max_shrug_ratio,
        min_elbow_angle_deg=min_elbow_deg,
        max_anterior_drift_deg=max_drift_deg,
    ),
    timing=TimingThresholds(
        min_concentric_time_sec=min_concentric_s,
        min_hold_time_sec=min_hold_s,
        min_eccentric_time_sec=min_eccentric_s,
    ),
    filtering=FilteringConfig(ema_alpha=0.35, min_landmark_visibility=0.60),
    calibration=CalibrationConfig(duration_sec=3.0, max_variance_ratio=0.05),
)
st.session_state.rules_engine.config = current_config

# Reset button in sidebar
if st.sidebar.button("🔄 Réinitialiser la séance", use_container_width=True):
    st.session_state.rules_engine.session.reset()
    st.session_state.repetition_logs.clear()
    st.rerun()

# ------------------------------------------------------------------------------
# Main Tabs: 1. Live Session  |  2. Session Summary Dashboard
# ------------------------------------------------------------------------------
tab_live, tab_summary = st.tabs(["🎥 Séance en Direct", "📊 Bilan & Statistiques de Séance"])

with tab_live:
    col_video, col_telemetry = st.columns([3, 1])

    with col_video:
        start_button = st.button(
            "▶️ Démarrer la séance vidéo" if not st.session_state.is_running else "⏹️ Arrêter la séance vidéo",
            type="primary" if not st.session_state.is_running else "secondary",
            use_container_width=True,
        )

        if start_button:
            st.session_state.is_running = not st.session_state.is_running
            st.rerun()

        video_placeholder = st.empty()
        live_alert_placeholder = st.empty()

    with col_telemetry:
        st.subheader("Indicateurs Clés")
        metric_reps = st.metric("Répétitions totales", len(st.session_state.repetition_logs))
        correct_count = sum(1 for r in st.session_state.repetition_logs if r["statut"] == "CORRECT")
        metric_correct = st.metric("Répétitions correctes", correct_count)
        rate = (correct_count / len(st.session_state.repetition_logs) * 100) if st.session_state.repetition_logs else 0.0
        metric_rate = st.metric("Taux de réussite", f"{rate:.1f} %")

        st.markdown("---")
        phase_badge_placeholder = st.empty()
        angle_metric_placeholder = st.empty()

    # Video Capture Loop
    if st.session_state.is_running:
        smoother = MultiMetricSmoother(alpha=current_config.filtering.ema_alpha)
        calibrator = CalibrationManager(
            duration_sec=current_config.calibration.duration_sec,
            max_variance_ratio=current_config.calibration.max_variance_ratio,
        )
        state_machine = RepetitionStateMachine(
            rest_threshold_deg=current_config.abduction.rest_threshold_deg,
            rising_start_deg=current_config.abduction.rising_start_deg,
            target_min_deg=current_config.abduction.target_min_deg,
            target_max_deg=current_config.abduction.target_max_deg,
            min_hold_time_sec=current_config.timing.min_hold_time_sec,
            arm=selected_arm,
        )

        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW if cv2.CAP_DSHOW else cv2.CAP_ANY)
        if not cap.isOpened():
            st.error("Impossible d'accéder à la webcam locale (index 0). Vérifiez la connexion de votre caméra.")
            st.session_state.is_running = False
        else:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

            detector = PoseDetector()
            calibrator.start(arm=selected_arm)
            start_epoch = time.perf_counter()
            prev_t = time.perf_counter()

            last_eval: Optional[RepetitionEvaluation] = None

            try:
                while st.session_state.is_running:
                    success, frame = cap.read()
                    if not success or frame is None:
                        break

                    now = time.perf_counter()
                    dt = max(1e-4, now - prev_t)
                    prev_t = now
                    fps = 1.0 / dt
                    timestamp_ms = int((now - start_epoch) * 1000)
                    now_sec = timestamp_ms / 1000.0

                    # Mirror view for intuitive patient feedback
                    frame = cv2.flip(frame, 1)

                    landmarks = detector.detect(frame, timestamp_ms=timestamp_ms)

                    abduction_raw = None
                    lean_raw = None
                    shrug_raw = None
                    elbow_raw = None
                    drift_raw = None
                    calib_progress = None
                    live_cue = None

                    if landmarks and len(landmarks) >= 33:
                        shoulder, hip, elbow, wrist, ear = detector.get_arm_landmarks(landmarks, arm=selected_arm)
                        left_sh = landmarks[PoseLandmarkIndex.LEFT_SHOULDER]
                        right_sh = landmarks[PoseLandmarkIndex.RIGHT_SHOULDER]
                        left_hip = landmarks[PoseLandmarkIndex.LEFT_HIP]
                        right_hip = landmarks[PoseLandmarkIndex.RIGHT_HIP]

                        # 1. Calibration update
                        if calibrator.is_calibrating:
                            completed, msg = calibrator.update(landmarks, arm=selected_arm)
                            calib_progress = calibrator.get_progress()
                        else:
                            status = "Suivi actif"

                        # 2. Geometry calculations
                        min_v = current_config.filtering.min_landmark_visibility
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

                        # 3D Out-of-Plane Anterior Drift (world landmarks)
                        drift_vis = False
                        if detector.last_world_landmarks is not None and len(detector.last_world_landmarks) >= 33:
                            act_sh_3d, oth_sh_3d, act_hip_3d, oth_hip_3d, act_el_3d = detector.get_drift_landmarks(
                                detector.last_world_landmarks, arm=selected_arm
                            )
                            drift_vis = are_landmarks_visible(
                                [act_sh_3d, oth_sh_3d, act_hip_3d, oth_hip_3d, act_el_3d], min_visibility=min_v
                            )
                            if drift_vis:
                                drift_raw = calculate_anterior_drift_angle(
                                    active_shoulder=act_sh_3d,
                                    other_shoulder=oth_sh_3d,
                                    active_hip=act_hip_3d,
                                    other_hip=oth_hip_3d,
                                    active_elbow=act_el_3d,
                                )

                        # 3. Smoothing
                        abduction_smooth = smoother.update("abduction", abduction_raw, is_valid=vis_ok)
                        lean_smooth = smoother.update("lean", lean_raw, is_valid=trunk_vis)
                        shrug_smooth = smoother.update("shrug", shrug_raw, is_valid=(shrug_raw is not None))
                        elbow_smooth = smoother.update("elbow", elbow_raw, is_valid=elbow_vis)
                        drift_smooth = smoother.update("drift", drift_raw, is_valid=drift_vis)

                        # 4. State Machine & Rules Evaluation
                        if calibrator.calibrated_data.is_calibrated:
                            new_rep = state_machine.update(
                                current_angle=abduction_smooth,
                                timestamp_sec=now_sec,
                                current_lean=lean_smooth,
                                current_shrug=shrug_smooth,
                                current_elbow=elbow_smooth,
                                current_drift=drift_smooth,
                            )

                            live_cue = st.session_state.rules_engine.evaluate_live_frame(
                                current_angle=abduction_smooth,
                                current_lean=lean_smooth,
                                current_shrug=shrug_smooth,
                                current_elbow=elbow_smooth,
                                current_phase=state_machine.current_phase,
                                current_drift=drift_smooth,
                            )
                            if "audio_coach" in st.session_state and st.session_state.audio_coach:
                                st.session_state.audio_coach.speak_cue(live_cue)

                            if new_rep is not None:
                                last_eval = st.session_state.rules_engine.evaluate_repetition(new_rep)
                                if "audio_coach" in st.session_state and st.session_state.audio_coach:
                                    st.session_state.audio_coach.speak_evaluation(last_eval)
                                # Append to persistent log
                                st.session_state.repetition_logs.append({
                                    "rep_index": last_eval.rep_index,
                                    "bras": last_eval.arm.upper(),
                                    "statut": last_eval.status_label,
                                    "angle_max_deg": round(last_eval.metrics.peak_abduction_deg, 1),
                                    "montee_s": round(last_eval.metrics.concentric_duration_sec, 2),
                                    "maintien_s": round(last_eval.metrics.hold_duration_sec, 2),
                                    "descente_s": round(last_eval.metrics.eccentric_duration_sec, 2),
                                    "inclinaison_max_deg": round(last_eval.metrics.max_trunk_lean_deg, 1),
                                    "haussement_max_pct": round(last_eval.metrics.max_shrug_ratio * 100, 1),
                                    "coude_min_deg": round(last_eval.metrics.min_elbow_angle_deg, 1),
                                    "derive_max_deg": round(last_eval.metrics.max_drift_deg, 1),
                                    "remarques": "; ".join(last_eval.reasons) if last_eval.reasons else "Parfait",
                                })

                        # 5. Overlays
                        frame = draw_skeleton(frame, landmarks, selected_arm=selected_arm, abduction_angle=abduction_smooth)
                        frame = draw_compensations_panel(
                            frame,
                            trunk_lean_deg=lean_smooth,
                            shrug_ratio=shrug_smooth,
                            elbow_angle_deg=elbow_smooth,
                            drift_angle_deg=drift_smooth,
                            max_lean=current_config.compensation.max_trunk_lean_deg,
                            max_shrug=current_config.compensation.max_shrug_ratio,
                            min_elbow=current_config.compensation.min_elbow_angle_deg,
                            max_drift=current_config.compensation.max_anterior_drift_deg,
                        )
                        frame = draw_live_feedback(frame, live_cue)

                    # 6. Top HUD
                    frame = draw_hud(
                        frame=frame,
                        selected_arm=selected_arm,
                        abduction_angle=smoother.get_smoother("abduction").value,
                        fps=fps,
                        status_text="Suivi actif" if calibrator.calibrated_data.is_calibrated else "Calibration...",
                        target_range=(current_config.abduction.target_min_deg, current_config.abduction.target_max_deg),
                        is_calibrated=calibrator.calibrated_data.is_calibrated,
                        calibration_progress=calib_progress,
                        rep_count=state_machine.rep_count,
                        current_phase=state_machine.current_phase,
                        last_evaluation=last_eval,
                        audio_enabled=enable_tts,
                    )

                    # Render frame in Streamlit
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    video_placeholder.image(frame_rgb, channels="RGB", use_container_width=True)

                    # Live French feedback banner in UI
                    if live_cue:
                        if live_cue.level == FeedbackLevel.WARNING:
                            live_alert_placeholder.warning(f"⚠️ {live_cue.message}")
                        elif live_cue.level == FeedbackLevel.SUCCESS:
                            live_alert_placeholder.success(f"✅ {live_cue.message}")
                        else:
                            live_alert_placeholder.info(f"ℹ️ {live_cue.message}")

            finally:
                cap.release()
                detector.close()

# ------------------------------------------------------------------------------
# Tab 2: Session Summary Dashboard
# ------------------------------------------------------------------------------
with tab_summary:
    st.header("Bilan de la Séance de Réhabilitation")
    session = st.session_state.rules_engine.session

    if not st.session_state.repetition_logs:
        st.info("Aucune répétition n'a encore été enregistrée. Démarrez la séance vidéo pour commencer l'exercice.")
    else:
        # KPI Row
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Total Répétitions", session.total_repetitions)
        kpi2.metric("Répétitions Correctes", session.correct_repetitions)
        kpi3.metric("Taux de Réussite", f"{session.success_rate_percent:.1f} %")
        avg_angle = np.mean([r["angle_max_deg"] for r in st.session_state.repetition_logs])
        kpi4.metric("Amplitude Moyenne", f"{avg_angle:.1f} °")

        st.markdown("---")

        # Visual Chart of Compensations
        col_chart, col_distrib = st.columns([2, 1])

        with col_chart:
            st.subheader("Distribution des Compensations Posturales")
            frequent_errors = session.get_most_frequent_errors()
            if frequent_errors:
                err_df = pd.DataFrame(frequent_errors, columns=["Type d'erreur", "Nombre d'occurrences"])
                st.bar_chart(err_df.set_index("Type d'erreur"))
            else:
                st.success("🎉 Aucune compensation posturale observée sur l'ensemble de la séance !")

        with col_distrib:
            st.subheader("Répartition Qualité")
            correct_cnt = session.correct_repetitions
            incorrect_cnt = session.total_repetitions - correct_cnt
            distrib_df = pd.DataFrame({
                "Statut": ["Correctes", "À corriger"],
                "Nombre": [correct_cnt, incorrect_cnt],
            })
            st.dataframe(distrib_df, hide_index=True, use_container_width=True)

        st.markdown("---")

        # Detailed Table
        st.subheader("Journal Détaillé Répétition par Répétition")
        df_logs = pd.DataFrame(st.session_state.repetition_logs)
        st.dataframe(df_logs, use_container_width=True, hide_index=True)

        # CSV Download Button
        csv_buffer = io.StringIO()
        df_logs.to_csv(csv_buffer, index=False)
        st.download_button(
            label="📥 Télécharger le rapport de séance (CSV)",
            data=csv_buffer.getvalue(),
            file_name=f"bilan_abduction_epaule_{time.strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
        )
