"""Patient session with a quiet voice and optional professional settings."""
import json
from dataclasses import replace
import cv2
import pandas as pd
import streamlit as st
from src.config import ExerciseConfig
from src.rules_engine import RulesEngine
from src.live_session import LiveSession
from src.dashboard import render_dashboard
from src.session_processor import repetition_log
from src.report_generator import generate_clinical_pdf_report

st.set_page_config(page_title="Mouvement — ma séance",page_icon="🦾",layout="wide")
if "rules_engine" not in st.session_state:
    st.session_state.rules_engine=RulesEngine(ExerciseConfig.from_yaml())
    st.session_state.repetition_logs=[]
    st.session_state.runtime=None
    st.session_state.is_running=False
    st.session_state.runtime_error=""


def stop_session():
    runtime=st.session_state.runtime
    try:
        if runtime is not None:
            runtime.close()
    finally:
        st.session_state.runtime=None
        st.session_state.is_running=False


base=ExerciseConfig.from_yaml()
running=st.session_state.is_running
st.title("Séance d’épaule")
st.caption("Choisissez un bras, puis commencez. Prototype éducatif : arrêtez en cas de douleur.")
st.sidebar.title("Ma séance")
arm_label=st.sidebar.radio("Quel bras souhaitez-vous travailler ?",["Bras droit","Bras gauche"],disabled=running)
arm="right" if arm_label == "Bras droit" else "left"
voice_choice=st.sidebar.selectbox("Accompagnement vocal",["Voix discrète","Sans voix","Guidage complet"],disabled=running)
audio_enabled=voice_choice != "Sans voix"
paces={"Très lente":1.5,"Lente":1.3,"Normale":1.05}
pace_label=st.sidebar.select_slider("Vitesse de la voix",options=list(paces),
    value=min(paces,key=lambda k: abs(paces[k]-base.audio.length_scale)),disabled=running)
voice_volume=st.sidebar.slider("Volume de la voix",0,100,round(base.audio.volume*100),5,disabled=running)
st.sidebar.caption("En mode discret, le texte vous guide. La voix intervient peu et laisse le temps de bouger.")


def slider(label,low,high,value,step):
    return st.slider(label,float(low),float(high),float(value),float(step),disabled=running)


with st.sidebar.expander("Réglages avancés",expanded=False):
    st.caption("Ces réglages servent à l’installation ou à l’adaptation de l’exercice avec un professionnel.")
    mirror=st.checkbox("Image en miroir",value=True)
    show_details=st.checkbox("Afficher les mesures",value=False)
    camera_index=st.number_input("Index camera (USB/externe : 1, 2...)",min_value=0,value=base.camera.index,step=1,disabled=running)
    resolutions=list(dict.fromkeys([(640,480),(1280,720),(1920,1080),(base.camera.width,base.camera.height)]))
    resolution=st.selectbox("Resolution demandee",resolutions,
        index=resolutions.index((base.camera.width,base.camera.height)),format_func=lambda size:f"{size[0]} x {size[1]}",disabled=running)
    model=st.selectbox("Modele pose",["full","lite","heavy"],index=["full","lite","heavy"].index(base.pose.model),disabled=running)
    use_zoom=st.checkbox("Régler le zoom du pilote",value=base.camera.zoom is not None,disabled=running)
    zoom=(st.number_input("Zoom du pilote",min_value=0.,value=float(base.camera.zoom or 0.),step=1.,disabled=running) if use_zoom else None)
    st.caption("Une webcam grand-angle peut utiliser un autre index. La résolution ne change pas forcément le champ optique.")
    st.divider()
    target_min=slider("Cible min (deg)",base.abduction.rising_start_deg+1,150,base.abduction.target_min_deg,1)
    target_max=slider("Cible max (deg)",40,175,base.abduction.target_max_deg,1)
    overshoot=slider("Alerte haute (deg)",40,180,base.abduction.overshoot_warn_deg,1)
    lean=slider("Inclinaison max (deg)",1,45,base.compensation.max_trunk_lean_deg,1)
    shrug=slider("Haussement max (%)",1,50,base.compensation.max_shrug_ratio*100,1)
    elbow=slider("Extension coude min (deg)",90,180,base.compensation.min_elbow_angle_deg,1)
    drift=slider("Écart hors plan max (deg)",5,90,base.compensation.max_anterior_drift_deg,1)
    rise=slider("Montée min (s)",.25,base.timing.max_concentric_time_sec,base.timing.min_concentric_time_sec,.25)
    hold=slider("Maintien min (s)",0,3,base.timing.min_hold_time_sec,.25)
    lower=slider("Descente min (s)",.25,base.timing.max_eccentric_time_sec,base.timing.min_eccentric_time_sec,.25)

config_error=""
try:
    config=replace(base,
        audio=replace(base.audio,length_scale=paces[pace_label],volume=voice_volume/100,
            guidance_mode="complete" if voice_choice == "Guidage complet" else "essential"),
        camera=replace(base.camera,index=camera_index,width=resolution[0],height=resolution[1],zoom=zoom),
        pose=replace(base.pose,model=model),
        abduction=replace(base.abduction,target_min_deg=target_min,target_max_deg=target_max,overshoot_warn_deg=overshoot),
        compensation=replace(base.compensation,max_trunk_lean_deg=lean,max_shrug_ratio=shrug/100,
            min_elbow_angle_deg=elbow,max_anterior_drift_deg=drift),
        timing=replace(base.timing,min_concentric_time_sec=rise,min_hold_time_sec=hold,min_eccentric_time_sec=lower))
except ValueError:
    config_error="Les limites de l’exercice ne sont pas cohérentes. Vérifiez les réglages avancés avec votre accompagnant."
    config=base
if config_error:
    st.sidebar.error(config_error)

live_tab,summary_tab=st.tabs(["Ma séance","Mon bilan"])
with live_tab:
    primary,pause_col,voice_col=st.columns([2,1,1])
    if primary.button("Terminer ma séance" if running else "Commencer ma séance",disabled=bool(config_error),type="primary",use_container_width=True):
        if running:
            stop_session()
        else:
            try:
                st.session_state.runtime=LiveSession(config,arm,audio_enabled,st.session_state.rules_engine)
                st.session_state.is_running=True
                st.session_state.runtime_error=""
            except Exception as exc:
                st.session_state.runtime_error="Le suivi ne peut pas démarrer. Vérifiez la caméra ou demandez de l’aide pour l’installation."
                st.session_state.runtime_error_details=str(exc)
        st.rerun()
    runtime=st.session_state.runtime
    paused=bool(getattr(runtime,"paused",False))
    if pause_col.button("Reprendre" if paused else "Faire une pause",disabled=not running,use_container_width=True):
        if paused:
            runtime.resume()
        else:
            runtime.pause()
        st.rerun()
    active_audio=getattr(runtime,"audio",None)
    if voice_col.button("Couper la voix" if active_audio and active_audio.enabled else "Activer la voix",disabled=active_audio is None,use_container_width=True):
        active_audio.toggle()
        st.rerun()
    if st.session_state.runtime_error:
        st.error(st.session_state.runtime_error)
        with st.expander("Informations pour la personne qui vous accompagne"):
            st.text(st.session_state.get("runtime_error_details",""))
    with st.expander("Comment faire ?"):
        st.write("1. Choisissez le bras droit ou gauche, puis commencez la séance.")
        st.write("2. Montrez vos deux épaules et le coude du bras suivi. Gardez le bras baissé quelques instants.")
        st.write("3. Levez doucement, marquez une pause, puis redescendez. Le compteur avance au retour au repos.")
        st.write("Vous pouvez faire une pause à tout moment. Les réglages se font avant de commencer.")
    with st.expander("Si la position n’est pas bien repérée"):
        st.write("Montrez les deux épaules et le coude. Évitez une fenêtre lumineuse derrière vous.")
        if st.button("Recommencer le réglage",disabled=not running):
            processor=runtime.processor
            processor.recalibrate(timestamp_sec=processor._last_frame_time)
            if active_audio:
                active_audio.silence()

    @st.fragment(run_every=.06 if st.session_state.is_running else None)
    def video_tick():
        runtime=st.session_state.runtime
        if runtime is None:
            st.info("Prêt ? Cliquez sur « Commencer ma séance ». Votre caméra s’ouvrira à ce moment-là.")
            return
        try:
            image,analysis,fps=runtime.read()
            audio=getattr(runtime,"audio",None)
            display=render_dashboard(image,analysis,runtime.processor,fps,mirror,
                audio.enabled if audio else audio_enabled,audio.status_message if audio else "",
                mode="paused" if getattr(runtime,"paused",False) else "running",details=show_details,show_controls=False)
            st.image(cv2.cvtColor(display,cv2.COLOR_BGR2RGB),channels="RGB",use_container_width=True)
            if analysis.new_evaluation:
                st.session_state.repetition_logs.append(repetition_log(analysis.new_evaluation))
                st.rerun()
        except Exception as exc:
            stop_session()
            st.session_state.runtime_error="La caméra ou le suivi a été interrompu. Vérifiez le branchement, puis recommencez."
            st.session_state.runtime_error_details=str(exc)
            st.rerun()
    video_tick()

with summary_tab:
    session=st.session_state.rules_engine.session
    st.subheader("Votre séance")
    first,second=st.columns(2)
    first.metric("Mouvements effectués",session.total_repetitions)
    second.metric("Avec des mesures complètes",session.assessed_repetitions)
    st.caption("Un mouvement peut être compté même si le cadrage ne permet pas tous les contrôles de posture.")
    logs=st.session_state.repetition_logs
    if logs:
        df=pd.DataFrame(logs)
        first_metric=session.evaluations[0].metrics
        target=first_metric.config_snapshot.get("abduction",{})
        arms={e.arm for e in session.evaluations}
        pdf=generate_clinical_pdf_report(session,arm=next(iter(arms)) if len(arms)==1 else "mixed",
            target_min=target.get("target_min_deg",target_min),target_max=target.get("target_max_deg",target_max),patient_id="Session locale")
        st.download_button("Enregistrer mon bilan PDF",pdf,"bilan_epaule.pdf","application/pdf",type="primary")
        with st.expander("Mesures détaillées pour un professionnel"):
            st.write(f"{session.correct_repetitions} mouvements dans les seuils ; {session.total_repetitions-session.assessed_repetitions} avec des mesures incomplètes.")
            st.write(f"{session.interrupted_attempts} tentatives interrompues. Fluidité : indicateur expérimental.")
            st.dataframe(df.drop(columns=["configuration","calibration"],errors="ignore"),hide_index=True,use_container_width=True)
            st.download_button("Exporter CSV",df.to_csv(index=False),"seance_epaule.csv","text/csv")
            st.download_button("Exporter JSON",json.dumps(logs,ensure_ascii=False,indent=2),"seance_epaule.json","application/json")
    else:
        st.info("Votre bilan apparaîtra après le premier mouvement terminé.")
    if st.button("Commencer une nouvelle séance",disabled=running):
        stop_session()
        st.session_state.rules_engine.session.reset()
        st.session_state.repetition_logs.clear()
        st.rerun()
