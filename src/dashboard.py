"""Minimal patient interface, painted directly at the display's pixel resolution."""
from functools import lru_cache
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.audio_feedback import spoken_french
from src.i18n import tr
from src.patient_controls import patient_buttons
from src.state_machine import ExercisePhase
from src.visualizer import draw_skeleton
from src.window_viewport import canvas_viewport
from src.willy import shared_guide
from src.silhouette import SilhouetteGuide, silhouette_frame
from src.willy_lines import cue_line_id, shared_script
from src.willy_overlay import bubble_layout, dim_outside, draw_bubble, ring, ring_zone

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
    """Scale coordinates and font sizes before rasterizing; never enlarge UI pixels.

    Text is written in French; with lang="en" every string is drawn in English (src.i18n).
    """
    def __init__(self,image,viewport,lang="fr"):
        self.lang=lang
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
        self.draw.text(self.point(*xy),tr(str(value),self.lang),font=self.font(size,bold),fill=color)

    def wrap(self,xy,value,width,size=18,color=TEXT,bold=False,max_lines=3):
        x,y=xy
        value=tr(str(value),self.lang)
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


def patient_guidance(analysis,mode,processor,lang="fr"):
    """(title, body, status) for the guidance column; French, translated when drawn in English."""
    if mode == "ready":
        return "Installez-vous", "Gardez les deux épaules et le coude visibles. Choisissez votre bras, puis commencez.", "AVANT DE COMMENCER"
    if mode == "paused":
        return "En pause", "Le comptage est arrêté. Reprenez quand vous voulez.", "SÉANCE EN PAUSE"
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
        line_id=cue_line_id(analysis.cue.message)
        title=(shared_script().text(line_id,lang) if line_id and lang == "en" else spoken_french(analysis.cue.message))
        return title.split(".")[0], "Ajustez doucement la position, sans forcer.", "AJUSTEMENT"
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
    label=tr(button.label,p.lang)
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
    text_width=p.draw.textlength(label,font=font)/p.sx
    p.text((left+(right-left-text_width)/2,top+(bottom-top-size)/2-3),label,size,color,button.primary)


WILLY_BOX=(1040,440,1248,716)  # Right column, beside the repetition count: visible in every view.
WILLY_STAGE_BOX=(470,142,836,600)  # The exercise demo: Willy steps into the large panel.


def _draw_willy(canvas,p,willy,analysis,mode,processor,mirror,speaking,box=WILLY_BOX):
    """Willy, the guide, is always on screen; he only reflects state already computed."""
    guide=willy if willy is not None else shared_guide()
    if guide is None:
        return None
    guide.point_side="R" if box == WILLY_STAGE_BOX else "L"  # point toward the bubble / the screen
    guide.update(analysis,mode,processor,mirror=mirror,speaking=speaking)
    x1,y1,x2,y2=p.box(box)
    sprite=guide.render(x2-x1,y2-y1)
    _paste_willy(canvas,sprite,(x1,y1))
    return guide


def _paste_willy(canvas,sprite,xy):
    canvas.paste(Image.fromarray(sprite,"RGBA"),xy,Image.fromarray(sprite[...,3]))


def willy_point(guide,name,box=WILLY_BOX):
    """A body point of Willy drawn in `box`, in logical screen coordinates."""
    if guide is None:
        return (box[0]+box[2])/2,box[1]+40
    x,y=guide.anchor(name,box[2]-box[0],box[3]-box[1])
    return box[0]+x,box[1]+y


GUIDANCE_COLUMN=(894,104,1262,442)


def _draw_overlay(canvas,p,overlay,guide,box):
    """The tour's spotlight, then Willy's bubble on top."""
    if overlay.compact:
        # An everyday line: over the lower right of the large panel, clear of the count and of Willy.
        candidates,width,size=[(870,596,"bottom-right"),(870,150,"top-right")],340,19
    elif overlay.willy_big:
        candidates,width,size=[(1250,432,"bottom-right"),(1250,140,"top-right")],372,20
    else:
        candidates=[(1250,432,"bottom-right"),(1010,600,"bottom-right"),(1010,144,"top-right"),(40,600,"bottom-left")]
        width,size=372,20
    if overlay.bubble and not overlay.compact:
        rect,_,_=bubble_layout(p,overlay,candidates,width,size)
        if rect[0] >= 860:
            p.rect(GUIDANCE_COLUMN,fill=BG)  # Willy talks here: the guidance text steps aside
    if overlay.spotlight is not None and not overlay.dim:
        ring_zone(p,overlay.spotlight)  # during exercise: point at the button without darkening the screen
    elif overlay.spotlight is not None:
        dim_outside(canvas,p,overlay.spotlight)
        if guide is not None:  # Willy stays bright: he is the one talking
            x1,y1,x2,y2=p.box(box)
            _paste_willy(canvas,guide.render(x2-x1,y2-y1),(x1,y1))
    if overlay.highlight and guide is not None:
        ring(p,willy_point(guide,overlay.highlight,box),radius=30 if overlay.highlight == "trunk" else 26)
    draw_bubble(canvas,p,overlay,candidates,willy_point(guide,"mouth",box),width=width,size=size)


_SILHOUETTE=SilhouetteGuide()


def _pill(p,xy,text,size=16,dot=None,center=False):
    text=tr(text,p.lang)
    font=p.font(size,True)
    width=p.draw.textlength(text,font=font)/p.sx+(30 if dot else 0)+28
    x,y=xy
    if center:
        x-=width/2
    p.rect((x,y,x+width,y+size+20),fill=(255,255,255),radius=14)
    if dot:
        cx,cy=p.point(x+20,y+(size+20)/2)
        r=max(2,round(6*p.scale))
        p.draw.ellipse((cx-r,cy-r,cx+r,cy+r),fill=dot)
    p.text((x+14+(26 if dot else 0),y+7),text,size,TEXT,True)


def _silhouette_labels(p,guide_text):
    instruction,placement,alignment=guide_text
    dot=(70,160,214) if alignment is None else (60,170,80) if alignment[0] else (245,140,40)
    _pill(p,(46,144),placement,15,dot)
    _pill(p,(446,546),instruction,18,center=True)


def render_dashboard(camera_frame,analysis,processor,fps=0,mirror=True,audio_enabled=True,audio_status="",
                     *,mode="running",details=False,help_visible=False,show_controls=True,output_size=None,
                     avatar_stage=None,avatars=True,avatar_gender="male",willy=None,speaking=False,
                     silhouette=False,lang="fr",overlay=None):
    """The patient screen. `overlay` (src.willy_overlay.Overlay) adds Willy's bubble and the tour's spotlight."""
    width,height=output_size or CANVAS_SIZE
    if width <= 0 or height <= 0:
        width,height=CANVAS_SIZE
    viewport=canvas_viewport(CANVAS_SIZE,width,height)
    canvas=Image.new("RGB",(width,height),BG)
    p=_Painter(canvas,viewport,lang)
    p.text((32,17),"mouvement",30)
    p.text((34,60),"Épaule / séance guidée",14,MUTED)
    p.rule(32,98,1248,98)
    use_avatars=avatars and avatar_stage is not None
    p.text((32,108),"VOTRE COACH" if use_avatars else "CAMÉRA",11,MUTED)
    if use_avatars:
        p.text((468,108),"VOTRE MOUVEMENT · ESTIMATION",11,MUTED)

    video=camera_frame.copy()
    if details and analysis.landmarks:
        draw_skeleton(video,analysis.landmarks,processor.arm,None)
    if mirror:
        video=cv2.flip(video,1)
    guide_text=None
    if silhouette and not use_avatars and not help_visible:
        guide_text=silhouette_frame(video,analysis,mode,processor,mirror,_SILHOUETTE)
    # Resample only the camera, directly into its final physical-pixel viewport.
    x1,y1,x2,y2=p.box((32,132,860,602))
    p.rect((32,132,860,602),fill=(33,36,39))
    vh,vw=video.shape[:2]
    scale=min((x2-x1)/vw,(y2-y1)/vh)
    video_width,video_height=max(1,round(vw*scale)),max(1,round(vh*scale))
    resized=cv2.resize(video,(video_width,video_height),interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    canvas.paste(Image.fromarray(cv2.cvtColor(resized,cv2.COLOR_BGR2RGB)),
                 (x1+(x2-x1-video_width)//2,y1+(y2-y1-video_height)//2))
    if guide_text is not None:
        _silhouette_labels(p,guide_text)
    if use_avatars:
        scene,tracked=avatar_stage.render(analysis,processor,mode,(vw,vh),(x2-x1,y2-y1))
        canvas.paste(Image.fromarray(scene),(x1,y1))
        p.rule(446,150,446,545)
        p.text((54,150),"Démonstration",16)
        resting=getattr(avatar_stage,'resting_sides',set())
        partial=isinstance(resting,set) and len(resting)==1
        label=("Suivi partiel · bras au repos" if tracked and partial else "En direct" if tracked
               else "Au repos · aucun suivi")
        p.text((472,150),label,15)
        # A framing preview remains visible, without covering the moving arms.
        thumb_w,thumb_h=round(160*p.sx),round(90*p.sy)
        thumb_scale=min(thumb_w/vw,thumb_h/vh)
        thumb=cv2.resize(video,(max(1,round(vw*thumb_scale)),max(1,round(vh*thumb_scale))))
        canvas.paste(Image.fromarray(cv2.cvtColor(thumb,cv2.COLOR_BGR2RGB)),p.point(366,494))
        p.text((54,570),"Exemple à votre rythme",12,MUTED)
        detailed=getattr(avatar_stage,'detailed_hands',0)
        p.text((550,570),"Paume et doigts suivis" if isinstance(detailed,int) and detailed>0
               else "Main absente : bras au repos",12,MUTED)

    p.rule(892,132,892,706)
    title,body,status=patient_guidance(analysis,mode,processor,lang)
    p.text((920,132),status,11,MUTED)
    end=p.wrap((916,178),title,330,37,max_lines=3)
    p.wrap((920,end+18),body,322,18,MUTED,max_lines=4)
    count=processor.rules_engine.session.total_repetitions
    p.rule(920,444,1248,444)
    p.text((920,466),"RÉPÉTITIONS",12,MUTED)
    p.text((912,484),str(count),min(100,round(260/max(1,len(str(count))))))
    p.wrap((920,596),"Comptées au retour au repos",150,14,MUTED,max_lines=2)
    if analysis.calibration_progress and mode == "running":
        progress,_=analysis.calibration_progress
    elif analysis.phase == ExercisePhase.HOLD and mode == "running":
        hold=processor.config.timing.min_hold_time_sec
        progress=min(1,analysis.hold_seconds/hold) if hold else 1
    else:
        progress=0
    if progress:
        p.rule(920,654,1030,654,LINE,2)
        p.rule(920,654,920+110*progress,654,TEXT,2)
    if audio_enabled and "indisponible" in audio_status.lower():
        p.wrap((920,670),"Son indisponible. Suivez le texte.",115,13,MUTED,max_lines=3)

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
        tips=["Willy, votre guide, reste à droite de l’écran et bouge avec vous.",
              "Choisissez votre avatar et le bras suivi en haut de l’écran.",
              "Vue caméra : « Silhouette » (touche G) montre où vous placer et le geste à suivre.",
              "Montrez les deux épaules et le coude du bras suivi.",
              "Commencez, puis gardez le bras baissé quelques instants.",
              "Suivez le coach et le texte : lever, maintenir, redescendre.",
              "Faites une pause quand vous en avez besoin. Arrêtez en cas de douleur."]
        y=235
        for index,tip in enumerate(tips,1):
            p.text((82,y),f"0{index}",13,FAINT)
            y=p.wrap((120,y-4),tip,684,19,max_lines=2)+22
    big=overlay is not None and overlay.willy_big
    willy_box=WILLY_STAGE_BOX if big else WILLY_BOX
    if big:
        p.rect((446,132,860,602),fill=(236,244,242))
    guide=_draw_willy(canvas,p,willy,analysis,mode,processor,mirror,speaking,willy_box)
    p.rule(32,732,1248,732)
    if show_controls:
        for button in patient_buttons(mode,processor.arm,audio_enabled,details,help_visible,avatars,avatar_gender,silhouette,lang):
            _button(p,button)
    else:
        p.text((32,766),"Utilisez les commandes de la page pour mettre en pause ou terminer.",16,MUTED)
        arm="Bras droit" if processor.arm == "right" else "Bras gauche"
        p.text((920,37),f"{arm} · Son {'activé' if audio_enabled else 'coupé'}",15,MUTED)
    p.text((32,819),"Prototype éducatif · Mesures estimées. Arrêtez en cas de douleur.",11,MUTED)
    if overlay is not None:
        _draw_overlay(canvas,p,overlay,guide,willy_box)
    return cv2.cvtColor(np.asarray(canvas),cv2.COLOR_RGB2BGR)
