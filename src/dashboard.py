"""Minimal patient interface, painted directly at the display's pixel resolution."""
from functools import lru_cache
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.audio_feedback import spoken_french
from src.patient_controls import patient_buttons
from src.state_machine import ExercisePhase
from src.visualizer import draw_skeleton
from src.window_viewport import canvas_viewport

CANVAS_SIZE=(1280,840)  # Logical layout coordinates, not a fixed-resolution bitmap.
BG=(250,250,249)
TEXT=(26,29,32)
MUTED=(112,117,122)
FAINT=(170,175,179)
LINE=(222,225,227)


@lru_cache(maxsize=128)
def _font(size,bold=False):
    candidates=(["C:/Windows/Fonts/segoeuib.ttf","/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"] if bold else
                ["C:/Windows/Fonts/segoeui.ttf","/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"])
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path,max(1,size))
    return ImageFont.load_default(size=max(1,size))


class _Painter:
    """Scale coordinates and font sizes before rasterizing; never enlarge UI pixels."""
    def __init__(self,image,viewport):
        self.image=image
        self.draw=ImageDraw.Draw(image)
        self.v=viewport
        self.sx=viewport.content_width/viewport.source_width
        self.sy=viewport.content_height/viewport.source_height
        self.scale=min(self.sx,self.sy)

    def point(self,x,y):
        return round(self.v.left+x*self.sx),round(self.v.top+y*self.sy)

    def box(self,bounds):
        return (*self.point(*bounds[:2]),*self.point(*bounds[2:]))

    def font(self,size,bold=False):
        return _font(round(size*self.scale),bold)

    def text(self,xy,value,size=18,color=TEXT,bold=False):
        self.draw.text(self.point(*xy),str(value),font=self.font(size,bold),fill=color)

    def wrap(self,xy,value,width,size=18,color=TEXT,bold=False,max_lines=3):
        x,y=xy
        font=self.font(size,bold)
        lines=[]
        line=""
        for word in str(value).split():
            candidate=f"{line} {word}".strip()
            if self.draw.textlength(candidate,font=font)>width*self.sx and line:
                lines.append(line)
                line=word
            else:
                line=candidate
        if line:
            lines.append(line)
        if len(lines)>max_lines:
            lines=lines[:max_lines]
            while lines[-1] and self.draw.textlength(lines[-1]+"…",font=font)>width*self.sx:
                lines[-1]=lines[-1][:-1]
            lines[-1]+="…"
        for line in lines:
            self.text((x,y),line,size,color,bold)
            y+=size*1.4
        return y

    def rect(self,bounds,fill=None,outline=None,radius=0):
        if radius:
            self.draw.rounded_rectangle(self.box(bounds),radius=max(1,round(radius*self.scale)),
                fill=fill,outline=outline,width=max(1,round(self.scale)))
        else:
            self.draw.rectangle(self.box(bounds),fill=fill,outline=outline,width=max(1,round(self.scale)))

    def rule(self,x1,y1,x2,y2,color=LINE,width=1):
        self.draw.line((*self.point(x1,y1),*self.point(x2,y2)),fill=color,width=max(1,round(width*self.scale)))


def patient_guidance(analysis,mode,processor):
    if mode == "ready":
        return "Installez-vous", "Gardez les deux épaules et le coude visibles. Choisissez votre bras, puis commencez.", "AVANT DE COMMENCER"
    if mode == "paused":
        return "En pause", "Le comptage est arrêté. Reprenez lorsque vous êtes prêt.", "SÉANCE EN PAUSE"
    if mode == "finished":
        return "Séance terminée", "Consultez les mesures ou commencez une nouvelle séance.", "BILAN"
    if analysis.status == "CALIBRATION":
        return "Gardez le bras baissé", "Restez au repos quelques instants pendant le réglage.", "PRÉPARATION"
    if analysis.status in ("SUIVI PERDU","POSITION A AJUSTER"):
        return "Ajustez le cadrage", "Replacez les deux épaules et le coude du bras suivi dans l’image.", "SUIVI INTERROMPU"
    if analysis.status == "EPAULES PRETES":
        return "Montrez le coude", "Vos épaules sont repérées. Le coude du bras suivi doit aussi rester visible.", "CADRAGE"
    if analysis.status == "REPOS REQUIS":
        return "Baissez le bras", "Repartez de la position de repos.", "POSITION DE DÉPART"
    if analysis.cue.level.value == "WARNING":
        return spoken_french(analysis.cue.message).split(".")[0], "Ajustez doucement la position, sans forcer.", "AJUSTEMENT"
    if analysis.phase == ExercisePhase.RISING:
        return "Levez le bras", "Montez doucement sur le côté, vers votre zone de mouvement.", "EN COURS"
    if analysis.phase == ExercisePhase.HOLD:
        if analysis.hold_seconds >= processor.config.timing.min_hold_time_sec:
            return "Redescendez", "Ramenez doucement le bras au repos.", "EN COURS"
        return "Maintenez", "Gardez la position un instant, puis redescendez.", "EN COURS"
    if analysis.phase == ExercisePhase.LOWERING:
        return "Redescendez", "Le mouvement sera compté au retour au repos.", "EN COURS"
    return "À votre rythme", "Levez doucement le bras sur le côté pour commencer le mouvement.", "EN COURS"


def _button(p,button):
    left,top,right,bottom=button.bounds
    size=17 if button.primary else 16
    color=TEXT if button.enabled or button.selected else FAINT
    if button.primary:
        p.rect(button.bounds,fill=TEXT,radius=5)
        color=(255,255,255)
    else:
        fill=(239,241,242) if button.selected else (255,255,255)
        outline=TEXT if button.selected else (190,195,199) if button.enabled else LINE
        if not button.enabled:
            fill=BG
        p.rect(button.bounds,fill=fill,outline=outline,radius=4)
    font=p.font(size,button.primary)
    text_width=p.draw.textlength(button.label,font=font)/p.sx
    p.text((left+(right-left-text_width)/2,top+(bottom-top-size)/2-3),button.label,size,color,button.primary)


def render_dashboard(camera_frame,analysis,processor,fps=0,mirror=True,audio_enabled=True,audio_status="",
                     *,mode="running",details=False,help_visible=False,show_controls=True,output_size=None):
    width,height=output_size or CANVAS_SIZE
    if width <= 0 or height <= 0:
        width,height=CANVAS_SIZE
    viewport=canvas_viewport(CANVAS_SIZE,width,height)
    canvas=Image.new("RGB",(width,height),BG)
    p=_Painter(canvas,viewport)
    p.text((32,17),"mouvement",30)
    p.text((34,60),"Épaule / séance guidée",14,MUTED)
    p.rule(32,98,1248,98)
    p.text((32,108),"CAMÉRA",11,MUTED)

    video=camera_frame.copy()
    if details and analysis.landmarks:
        draw_skeleton(video,analysis.landmarks,processor.arm,None)
    if mirror:
        video=cv2.flip(video,1)
    # Resample only the camera, directly into its final physical-pixel viewport.
    x1,y1,x2,y2=p.box((32,132,860,602))
    p.rect((32,132,860,602),fill=(33,36,39))
    vh,vw=video.shape[:2]
    scale=min((x2-x1)/vw,(y2-y1)/vh)
    video_width,video_height=max(1,round(vw*scale)),max(1,round(vh*scale))
    resized=cv2.resize(video,(video_width,video_height),interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    canvas.paste(Image.fromarray(cv2.cvtColor(resized,cv2.COLOR_BGR2RGB)),
                 (x1+(x2-x1-video_width)//2,y1+(y2-y1-video_height)//2))

    p.rule(892,132,892,706)
    title,body,status=patient_guidance(analysis,mode,processor)
    p.text((920,132),status,11,MUTED)
    end=p.wrap((916,178),title,330,37,max_lines=3)
    p.wrap((920,end+18),body,322,18,MUTED,max_lines=4)
    count=processor.rules_engine.session.total_repetitions
    p.rule(920,444,1248,444)
    p.text((920,466),"RÉPÉTITIONS",12,MUTED)
    p.text((912,484),str(count),min(100,round(260/max(1,len(str(count))))))
    p.text((920,610),"Comptées au retour au repos",14,MUTED)
    if analysis.calibration_progress and mode == "running":
        progress,_=analysis.calibration_progress
    elif analysis.phase == ExercisePhase.HOLD and mode == "running":
        hold=processor.config.timing.min_hold_time_sec
        progress=min(1,analysis.hold_seconds/hold) if hold else 1
    else:
        progress=0
    if progress:
        p.rule(920,654,1248,654,LINE,2)
        p.rule(920,654,920+328*progress,654,TEXT,2)
    if audio_enabled and "indisponible" in audio_status.lower():
        p.wrap((920,678),"Son indisponible. Suivez le texte.",320,13,MUTED,max_lines=2)

    phases=[("Repos",ExercisePhase.REST),("Lever",ExercisePhase.RISING),
            ("Maintenir",ExercisePhase.HOLD),("Redescendre",ExercisePhase.LOWERING)]
    for index,(name,phase) in enumerate(phases):
        x=32+index*207
        active=(mode == "running" and analysis.phase == phase
                and analysis.status not in ("CALIBRATION","SUIVI PERDU","POSITION A AJUSTER","EPAULES PRETES"))
        p.text((x,622),f"0{index+1}",12,FAINT)
        p.text((x+29,617),name,17,TEXT if active else MUTED,active)
        if active:
            p.rule(x,651,x+170,651,TEXT)
    result=processor.last_evaluation
    if details:
        values=[]
        for key,label,unit,mult in (("abduction","Bras","°",1),("lean","Tronc","°",1),
                                    ("shrug","Épaule","%",100),("elbow","Coude","°",1)):
            value=analysis.metrics.get(key)
            values.append(f"{label} : {'—' if value is None else f'{value*mult:.0f}{unit}'}")
        p.text((32,674),"   ·   ".join(values),16)
        reference="Estimation depuis les épaules" if analysis.angle_reference == "shoulders" else "Angle depuis le tronc"
        p.text((32,700),f"{reference} · Caméra {vw}×{vh} · Modèle {processor.config.pose.model} · {fps:.0f} images/s",12,MUTED)
    elif mode == "finished":
        p.text((32,674),f"{count} répétitions comptées. {processor.rules_engine.session.assessed_repetitions} avec des mesures complètes.",16)
    elif result:
        note=("Certaines mesures de posture ne sont pas disponibles." if result.status_label == "INDETERMINE"
              else "Mesures dans la zone prévue." if result.is_correct else "Suivez l’ajustement pour le prochain mouvement.")
        p.text((32,674),f"Répétition {result.rep_index} comptée.",16)
        p.wrap((32,701),note,825,13,MUTED,max_lines=1)
    else:
        p.text((32,674),"Levez, maintenez, puis ramenez le bras au repos.",16,MUTED)

    if help_visible:
        p.rect((52,152,840,582),fill=BG,outline=LINE)
        p.text((82,175),"Comment faire",27)
        tips=["Choisissez le bras droit ou gauche en haut de l’écran.",
              "Montrez les deux épaules et le coude du bras suivi.",
              "Commencez, puis gardez le bras baissé quelques instants.",
              "Suivez le texte : lever, maintenir, puis redescendre.",
              "Faites une pause quand vous en avez besoin. Arrêtez en cas de douleur."]
        y=235
        for index,tip in enumerate(tips,1):
            p.text((82,y),f"0{index}",13,FAINT)
            y=p.wrap((120,y-4),tip,684,19,max_lines=2)+22
    p.rule(32,732,1248,732)
    if show_controls:
        for button in patient_buttons(mode,processor.arm,audio_enabled,details,help_visible):
            _button(p,button)
    else:
        p.text((32,766),"Utilisez les commandes de la page pour mettre en pause ou terminer.",16,MUTED)
        arm="Bras droit" if processor.arm == "right" else "Bras gauche"
        p.text((920,37),f"{arm} · Son {'activé' if audio_enabled else 'coupé'}",15,MUTED)
    p.text((32,819),"Prototype éducatif · Mesures estimées. Arrêtez en cas de douleur.",11,MUTED)
    return cv2.cvtColor(np.asarray(canvas),cv2.COLOR_RGB2BGR)
