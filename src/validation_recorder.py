"""Validation recorder (Phase 7.2): `python record_clip.py angles`.

A plain OpenCV window, without Willy, for the study in docs/validation-protocol.md. For each
trial it counts down, records every frame (the app's own angle and the landmarks) to a CSV,
then asks the operator for the reference: the goniometer reading for a held position, or the
observer's count for a set of repetitions. Video is saved only with --save-video once the
volunteer's video consent is confirmed. It uses whichever pose model is installed.

Keys: SPACE start (and end a set of repetitions) · N / B next / previous trial · A arm ·
P position · T trial number · K calibrate again · Enter save the reading · R redo · S skip ·
Esc quit.
"""
from __future__ import annotations

import argparse
import random
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from src import validation_data as vd
from src.config import ExerciseConfig
from src.dashboard import _font
from src.session_processor import SessionProcessor

ARMS = ("right", "left")
ARM_FR = {"right": "droit", "left": "gauche"}
CHOICES = tuple(("hold", p) for p in vd.POSITIONS) + (("reps", None),)
YES = ("o", "oui", "y", "yes")
ENTER, BACKSPACE, ESC, SPACE = (10, 13), (8, 127), 27, 32
INK, MUTED, ACCENT, RECORD = (25, 25, 25), (102, 102, 102), (37, 125, 224), (220, 60, 61)  # RGB


@dataclass(frozen=True)
class Item:
    arm: str
    kind: str              # "hold" (a position held still) or "reps" (a set of repetitions)
    target: int | None     # degrees, for a hold
    trial: int

    def id(self, subject):
        return vd.trial_id(subject, self.arm, self.kind, self.target, self.trial)

    def label(self, trials, reps_sets):
        if self.kind == "hold":
            return f"bras {ARM_FR[self.arm]} · position {self.target}° · essai {self.trial}/{trials}"
        return f"bras {ARM_FR[self.arm]} · série de répétitions {self.trial}/{reps_sets}"


def protocol(arms=ARMS, trials=3, reps_sets=1, shuffle=False, seed=""):
    """Each arm in turn: every position once per round (3 rounds), then the sets of repetitions."""
    items = []
    for arm in arms:
        for trial in range(1, trials + 1):
            order = list(vd.POSITIONS)
            if shuffle:  # the same order every time for this volunteer, so a session can resume
                random.Random(f"{seed}-{arm}-{trial}").shuffle(order)
            items += [Item(arm, "hold", target, trial) for target in order]
        items += [Item(arm, "reps", None, trial) for trial in range(1, reps_sets + 1)]
    return items


def decimal(value, digits=1):
    return f"{value:.{digits}f}".replace(".", ",")


class Window:
    """The OpenCV window (the tests use a scripted one)."""
    name = "Mouvement - mesures de validation"

    def __init__(self):
        self.opened = False

    def show(self, image):
        if not self.opened:
            cv2.namedWindow(self.name, cv2.WINDOW_NORMAL)
            self.opened = True
        cv2.imshow(self.name, image)

    def key(self):
        return cv2.waitKeyEx(1)

    def is_open(self):
        return not self.opened or cv2.getWindowProperty(self.name, cv2.WND_PROP_VISIBLE) >= 1

    def close(self):
        if self.opened:
            cv2.destroyWindow(self.name)
            self.opened = False


class Recorder:
    def __init__(self, subject, folder, capture, detector, window, config=None, *, items=None, trials=3,
                 reps_sets=1, hold_sec=3., countdown_sec=3., reps_max_sec=180., save_video=False,
                 writer_factory=None, model="", camera="", mirror=False, blind=False):
        self.subject, self.folder = subject, Path(folder)
        self.capture, self.detector, self.window = capture, detector, window
        self.config = config or ExerciseConfig.from_yaml()
        self.trials, self.reps_sets = trials, reps_sets
        self.items = list(items or protocol(trials=trials, reps_sets=reps_sets))
        self.hold_sec, self.countdown_sec, self.reps_max_sec = hold_sec, countdown_sec, reps_max_sec
        self.save_video, self.writer_factory = save_video, writer_factory or self._video_writer
        self.model, self.camera, self.mirror = model, camera, mirror
        self.blind = blind  # hide the app's angle, so whoever reads the goniometer can't be swayed by it
        self.done = vd.done_ids(self.folder, subject)
        self.skipped = set()
        self.processors = {}
        self.state, self.since, self.message = "ready", 0., ""
        self.rows, self.typed, self.video, self.video_path = [], "", None, None
        self.started, self.reps_start, self.app_value, self.frames_path = 0., 0, None, None
        self.valid_frames = self.window_frames = 0
        self.last, self.landmarks, self.now = None, None, 0.
        self.saved = 0
        self._camera_retry = 0.
        first = self.next_index(-1)
        self.index = 0 if first is None else first
        self.item = self.items[self.index]
        if first is None:
            self.state = "finished"

    # -------------------------------------------------------------- the trial list
    def next_index(self, after):
        """The next trial still to do after `after`, wrapping around; None when all are done."""
        order = list(range(after + 1, len(self.items))) + list(range(0, after + 1))
        for i in order:
            key = self.items[i].id(self.subject)
            if key not in self.done and key not in self.skipped:
                return i
        return None

    def go(self, index):
        self.index = index % len(self.items)
        self.item = self.items[self.index]
        self.message = ""

    @property
    def processor(self):
        arm = self.item.arm
        if arm not in self.processors:
            processor = SessionProcessor(self.config, arm)
            processor.model_info = dict(getattr(self.detector, "model_info", {}) or {})
            self.processors[arm] = processor
        return self.processors[arm]

    def calibrated(self):
        return self.processor.calibrator.calibrated_data.is_calibrated

    # -------------------------------------------------------------- the loop
    def run(self):
        while self.state != "done" and self.window.is_open():
            self.step()
        self.abort_recording()

    def step(self):
        ok, frame, timestamp_ms, _ = self.capture.read_frame()
        if not ok or frame is None:
            self.message = "Caméra indisponible : vérifiez son branchement (nouvel essai toutes les 2 s)."
            self.last = self.landmarks = None
            if hasattr(self.capture, "reconnect") and self._camera_retry <= 0:
                self.capture.reconnect()
                self._camera_retry = 60
            self._camera_retry -= 1
            self.window.show(self.draw(None))
            self.handle(self.window.key())
            return
        self.now = timestamp_ms / 1000
        landmarks = self.detector.detect(frame, timestamp_ms)
        world = getattr(self.detector, "last_world_landmarks", None)
        height, width = frame.shape[:2]
        processor = self.processor
        self.last = processor.process(landmarks, world, width, height, self.now)
        self.landmarks = landmarks
        if self.message.startswith("Caméra"):
            self.message = ""
        reps = processor.rules_engine.session.total_repetitions
        if self.state == "countdown" and self.now - self.since >= self.countdown_sec:
            self.begin_recording(width, height, reps)
        if self.state == "recording":
            self.rows.append(vd.frame_row(len(self.rows), self.now - self.started, self.last, landmarks, world, reps))
            if self.video is not None:
                self.video.write(frame)
            limit = self.hold_sec if self.item.kind == "hold" else self.reps_max_sec
            if self.now - self.started >= limit - 1e-6:
                self.end_recording(reps)
        self.window.show(self.draw(frame))
        self.handle(self.window.key())

    # -------------------------------------------------------------- recording
    @staticmethod
    def _video_writer(path, fps, size):
        return cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)

    def base_name(self):
        return f"{self.item.id(self.subject)}_{datetime.now():%Y%m%d-%H%M%S}"

    def begin_recording(self, width, height, reps):
        self.state, self.started, self.rows, self.reps_start = "recording", self.now, [], reps
        name = self.base_name()
        self.frames_path = self.folder / self.subject / f"{name}.csv"
        self.video_path = None
        if self.save_video:
            self.video_path = self.folder / self.subject / f"{name}.mp4"
            self.video_path.parent.mkdir(parents=True, exist_ok=True)
            self.video = self.writer_factory(self.video_path, 30., (width, height))

    def end_recording(self, reps):
        if self.video is not None:
            self.video.release()
            self.video = None
        vd.write_frames(self.frames_path, self.rows)
        if self.item.kind == "hold":
            self.app_value, valid, total = vd.trial_app_angle(self.rows)
        else:
            self.app_value = reps - self.reps_start
            valid = sum(int(r["angle_valid"]) for r in self.rows)
            total = len(self.rows)
        self.valid_frames, self.window_frames = valid, total
        self.state, self.typed, self.message = "reading", "", ""

    def abort_recording(self):
        """Esc while recording, or the window closed: nothing of this attempt is kept."""
        if self.video is not None:
            self.video.release()
            self.video = None
            if self.video_path is not None and self.video_path.exists():
                self.video_path.unlink()
        if self.state in ("countdown", "recording"):
            self.state, self.rows = "ready", []

    def save(self, status, reference=None):
        item = self.item
        relative = lambda path: path.relative_to(self.folder).as_posix() if path is not None else ""  # noqa: E731
        vd.append_trial(self.folder, {
            "trial_id": item.id(self.subject), "subject": self.subject, "arm": item.arm, "kind": item.kind,
            "target_deg": "" if item.target is None else item.target, "trial": item.trial,
            "reference_deg": reference if item.kind == "hold" and reference is not None else "",
            "observer_reps": int(reference) if item.kind == "reps" and reference is not None else "",
            "app_deg": "" if item.kind != "hold" or self.app_value is None else self.app_value,
            "app_reps": self.app_value if item.kind == "reps" else "",
            "valid_frames": self.valid_frames, "frames": len(self.rows), "status": status,
            "model": self.model, "camera": self.camera, "recorded_at": datetime.now().isoformat(timespec="seconds"),
            "frames_file": relative(self.frames_path), "video_file": relative(self.video_path),
        })
        self.rows = []
        self.state = "ready"
        if status == "redo":
            self.message = "Essai à refaire : il reste dans la liste."
            return
        if status == "ok":
            self.done.add(item.id(self.subject))
            self.saved += 1
        else:
            self.skipped.add(item.id(self.subject))
        following = self.next_index(self.index)
        if following is None:
            self.state = "finished"
        else:
            self.go(following)

    # -------------------------------------------------------------- keys
    def handle(self, key):
        if key is None or key < 0:
            return
        char = chr(key).lower() if 0 <= key < 0x110000 and chr(key).isprintable() else ""
        if self.state == "reading":
            self.reading_key(key, char)
        elif self.state == "recording":
            if key == ESC:
                self.abort_recording()
                self.message = "Essai annulé."
            elif key == SPACE and self.item.kind == "reps":
                self.end_recording(self.processor.rules_engine.session.total_repetitions)
        elif self.state == "countdown":
            if key == ESC:
                self.state, self.message = "ready", "Essai annulé."
        elif self.state == "finished":
            if key == ESC or char == "q":
                self.state = "done"
            elif char in ("b", "n"):
                self.state = "ready"
                self.go(self.index + (1 if char == "n" else -1))
        else:
            self.ready_key(key, char)

    def ready_key(self, key, char):
        item = self.item
        if key == ESC or char == "q":
            self.state = "done"
        elif key == SPACE:
            if self.last is None or not self.landmarks:
                self.message = "Personne non détectée : placez le volontaire face à la caméra."
            elif not self.calibrated():
                self.message = "Calibration d'abord : bras le long du corps, sans bouger."
            else:
                self.state, self.since, self.message = "countdown", self.now, ""
        elif char == "n":
            self.go(self.index + 1)
        elif char == "b":
            self.go(self.index - 1)
        elif char == "a":
            self.item = replace(item, arm="left" if item.arm == "right" else "right")
        elif char == "p":
            kinds = list(CHOICES)
            kind, target = kinds[(kinds.index((item.kind, item.target)) + 1) % len(kinds)]
            limit = self.trials if kind == "hold" else self.reps_sets
            self.item = replace(item, kind=kind, target=target, trial=min(item.trial, limit))
        elif char == "t":
            limit = self.trials if item.kind == "hold" else self.reps_sets
            self.item = replace(item, trial=item.trial % max(1, limit) + 1)
        elif char == "k":
            self.processor.recalibrate(timestamp_sec=self.now)
            self.message = "Nouvelle calibration : bras le long du corps, sans bouger."

    def reading_key(self, key, char):
        if key in ENTER:
            value = self.parse(self.typed)
            if value is None:
                self.message = ("Lecture invalide : un angle entre -20 et 200°." if self.item.kind == "hold"
                                else "Nombre invalide : de 0 à 200 répétitions.")
            else:
                self.save("ok", value)
        elif key in BACKSPACE:
            self.typed = self.typed[:-1]
        elif key == ESC or char == "r":
            self.save("redo")
        elif char == "s":
            self.save("skipped")
        elif char.isdigit() or (char in ".," and self.item.kind == "hold") or (char == "-" and not self.typed):
            if len(self.typed) < 6:
                self.typed += "." if char == "," else char

    def parse(self, text):
        try:
            value = float(text)
        except ValueError:
            return None
        if self.item.kind == "hold":
            return round(value, 1) if -20 <= value <= 200 else None
        return int(value) if value == int(value) and 0 <= value <= 200 else None

    # -------------------------------------------------------------- drawing
    def status_line(self):
        if self.message:
            return self.message, RECORD if self.message.startswith(("Personne", "Caméra", "Lecture", "Nombre")) else INK
        if self.state == "finished":
            return "Toutes les mesures de ce volontaire sont faites. Échap pour fermer.", INK
        if self.state == "reading":
            return "Essai enregistré : saisissez la valeur de référence.", INK
        if self.last is None or not self.landmarks:
            return "Personne non détectée : placez le volontaire face à la caméra.", RECORD
        if self.state == "ready" and not self.calibrated():
            progress = self.last.calibration_progress
            share = f" ({int(100 * progress[0] / max(progress[1], 1))} %)" if progress else ""
            return f"Calibration : bras le long du corps, sans bouger{share}.", ACCENT
        if self.last.metrics.get("abduction") is None:
            return "Angle indisponible : volontaire de face, épaules et coude visibles.", RECORD
        if self.state == "countdown":
            return "Tenez la position…", INK
        if self.state == "recording":
            if self.item.kind == "hold":
                return f"Enregistrement {decimal(self.now - self.started)} / {decimal(self.hold_sec)} s", RECORD
            reps = self.processor.rules_engine.session.total_repetitions - self.reps_start
            return f"Enregistrement : {reps} répétition(s) comptée(s). ESPACE pour finir la série.", RECORD
        return "Prêt : ESPACE pour lancer l'essai.", INK

    def keys_line(self):
        if self.state == "reading":
            return "Entrée = enregistrer · R = refaire l'essai · S = passer"
        if self.state in ("countdown", "recording"):
            return "Échap = annuler cet essai" + (" · ESPACE = fin de la série" if self.item.kind == "reps" else "")
        if self.state == "finished":
            return "B / N = revoir un essai · Échap = fermer"
        return "ESPACE lancer · N / B essai suivant / précédent · A bras · P position · T n° d'essai · K recalibrer · Échap quitter"

    def draw(self, frame):
        if frame is None:
            frame = np.full((720, 1280, 3), 40, np.uint8)
        image = frame.copy()
        height, width = image.shape[:2]
        if self.landmarks:
            self.draw_skeleton(image)
        if self.mirror:
            image = cv2.flip(image, 1)
        canvas = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(canvas, "RGBA")
        scale = max(.6, width / 1280)
        size = lambda value: max(10, int(value * scale))  # noqa: E731
        bar = size(132)
        draw.rectangle((0, 0, width, bar), fill=(255, 255, 255, 235))
        title = f"{self.subject} · {self.item.label(self.trials, self.reps_sets)}"
        draw.text((size(20), size(14)), title, font=_font(size(26), True), fill=INK)
        text, colour = self.status_line()
        draw.text((size(20), size(56)), text, font=_font(size(20)), fill=colour)
        draw.text((size(20), size(94)), self.keys_line(), font=_font(size(15)), fill=MUTED)
        shown, caption = self.angle_text()
        draw.text((width - size(20), size(12)), shown, font=_font(size(50), True), fill=INK, anchor="ra")
        draw.text((width - size(20), size(76)), caption, font=_font(size(15)), fill=MUTED, anchor="ra")
        done = sum(1 for item in self.items if item.id(self.subject) in self.done)
        draw.text((size(20), height - size(34)), f"Mesures faites : {done} / {len(self.items)}",
                  font=_font(size(18), True), fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
        if self.state == "recording":
            r = size(12)
            draw.ellipse((width - size(260) - r, size(30) - r, width - size(260) + r, size(30) + r), fill=RECORD)
        if self.state == "countdown":
            left = max(1, int(np.ceil(self.countdown_sec - (self.now - self.since))))
            box = (width // 2 - size(110), height // 2 - size(110), width // 2 + size(110), height // 2 + size(110))
            draw.rounded_rectangle(box, size(24), fill=(255, 255, 255, 220))
            draw.text((width // 2, height // 2), str(left), font=_font(size(150), True), fill=INK, anchor="mm")
        if self.state == "reading":
            self.draw_reading(draw, width, height, size)
        return cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR)

    def angle_text(self):
        """The live angle shown top right, and its caption (in blind mode only whether there is one)."""
        angle = self.last.metrics.get("abduction") if self.last is not None else None
        if self.blind:
            return ("✓" if angle is not None else "—"), "angle masqué (--blind)"
        return ("—" if angle is None else f"{decimal(angle)}°"), "angle de l'application"

    def reading_text(self):
        """The question of the reading box and the app's own value (hidden in blind mode)."""
        if self.item.kind == "hold":
            question = "Lecture du goniomètre (en degrés)"
            app = "angle non mesurable (trop peu d'images)" if self.app_value is None else f"{decimal(self.app_value)}°"
            detail = f"Application : {app}"
        else:
            question = "Répétitions comptées par l'observateur"
            detail = f"Application : {self.app_value} répétition(s)"
        return question, "Valeur de l'application masquée (--blind)." if self.blind else detail

    def draw_reading(self, draw, width, height, size):
        box = (width // 2 - size(330), height // 2 - size(150), width // 2 + size(330), height // 2 + size(150))
        draw.rounded_rectangle(box, size(24), fill=(255, 255, 255, 245))
        x, y = box[0] + size(36), box[1] + size(30)
        question, detail = self.reading_text()
        draw.text((x, y), question, font=_font(size(26), True), fill=INK)
        draw.text((x, y + size(56)), (self.typed.replace(".", ",") or " ") + "▏", font=_font(size(64), True), fill=ACCENT)
        draw.text((x, y + size(150)), detail, font=_font(size(18)), fill=MUTED)
        draw.text((x, y + size(184)), "Saisissez la valeur au clavier, puis Entrée.", font=_font(size(16)), fill=MUTED)

    def draw_skeleton(self, image):
        height, width = image.shape[:2]
        points = self.landmarks
        measured = (12, 14, 16) if self.item.arm == "right" else (11, 13, 15)

        def at(i):
            return int(points[i].x * width), int(points[i].y * height)

        def seen(i):
            return i < len(points) and (points[i].visibility or 0) >= .5

        for a, b in ((11, 12), (11, 23), (12, 24), (23, 24), (11, 13), (13, 15), (12, 14), (14, 16)):
            if seen(a) and seen(b):
                strong = a in measured and b in measured
                cv2.line(image, at(a), at(b), (224, 125, 37) if strong else (235, 235, 235), 5 if strong else 2, cv2.LINE_AA)
        for i in (11, 12, 13, 14, 15, 16, 23, 24):
            if seen(i):
                cv2.circle(image, at(i), 6 if i in measured else 4, (255, 255, 255), -1, cv2.LINE_AA)


# ------------------------------------------------------------------ command line
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python record_clip.py angles",
        description="Mesures de l'étude de validation (docs/validation-protocol.md).")
    parser.add_argument("--subject", help="identifiant anonyme du volontaire (ex. V01) ; demandé sinon")
    parser.add_argument("--out", type=Path, help="dossier de l'étude (par défaut %%APPDATA%%\\Mouvement\\validation)")
    parser.add_argument("--camera", type=int, help="numéro de la caméra (par défaut celui de la configuration)")
    parser.add_argument("--arms", choices=("both", "right", "left"), default="both", help="bras mesurés")
    parser.add_argument("--trials", type=int, default=3, help="essais par position (3)")
    parser.add_argument("--reps-sets", type=int, default=1, help="séries de répétitions par bras (1)")
    parser.add_argument("--hold", type=float, default=3., help="durée d'un maintien enregistré, en secondes (3)")
    parser.add_argument("--countdown", type=float, default=3., help="compte à rebours, en secondes (3)")
    parser.add_argument("--shuffle", action="store_true", help="ordre des positions mélangé à chaque tour")
    parser.add_argument("--save-video", action="store_true", help="vidéo aussi, après consentement vidéo")
    parser.add_argument("--mirror", action="store_true", help="image en miroir (par défaut : vue de l'opérateur)")
    parser.add_argument("--blind", action="store_true",
                        help="masquer l'angle de l'application à l'écran (lecture du goniomètre en aveugle)")
    parser.add_argument("--model", choices=("lite", "full", "heavy"), help="modèle de pose (par défaut : l'installé)")
    return parser.parse_args(argv)


def _open_camera(config, index):
    from src.capture import VideoCaptureManager
    c = config.camera
    capture = VideoCaptureManager(camera_index=c.index if index is None else index, width=c.width, height=c.height,
                                  target_fps=c.fps, zoom=c.zoom, mirror=False)
    return capture if capture.open() else None


def _open_detector(config, variant):
    from src.person_lock import PersonLock
    from src.pose_detector import PoseDetector
    detector = PoseDetector(model_variant=variant, num_poses=config.pose.num_poses)
    detector.choose = PersonLock().choose  # the volunteer, not someone walking behind
    return detector


def main(argv=None, ask=input, open_camera=_open_camera, open_detector=_open_detector, window=None):
    args = parse_args(argv)
    print("=" * 70)
    print("  ÉTUDE DE VALIDATION : angle de l'application et goniomètre")
    print("  Protocole : docs/validation-protocol.md")
    print("=" * 70)
    if ask("Le volontaire a-t-il signé le formulaire de consentement à l'étude ? [o/N] ").strip().lower() not in YES:
        print("Arrêt : le consentement écrit est obligatoire.")
        return 1
    subject = vd.safe_subject(args.subject or ask("Identifiant anonyme du volontaire (ex. V01) : "))
    if not subject:
        print("Arrêt : identifiant vide (lettres, chiffres, - et _ seulement).")
        return 1
    save_video = False
    if args.save_video:
        save_video = ask("Le volontaire a-t-il coché « j'accepte la vidéo » sur le formulaire ? [o/N] ").strip().lower() in YES
        print("Vidéo enregistrée pour chaque essai." if save_video else
              "Pas de consentement vidéo : seuls les points du corps et les angles sont enregistrés.")
    config = ExerciseConfig.from_yaml()
    from src.pose_detector import installed_pose_model
    variant = args.model or installed_pose_model(config.pose.model)
    folder = args.out or vd.validation_dir()
    capture = open_camera(config, args.camera)
    if capture is None:
        print("Caméra introuvable : vérifiez son branchement ou essayez --camera 1.")
        return 1
    detector = open_detector(config, variant)
    window = window or Window()
    arms = ARMS if args.arms == "both" else (args.arms,)
    items = protocol(arms, args.trials, args.reps_sets, args.shuffle, subject)
    camera_name = f"{args.camera if args.camera is not None else config.camera.index}"
    recorder = Recorder(subject, folder, capture, detector, window, config, items=items, trials=args.trials,
                        reps_sets=args.reps_sets, hold_sec=args.hold, countdown_sec=args.countdown,
                        save_video=save_video, model=f"pose_landmarker_{variant}", camera=camera_name,
                        mirror=args.mirror, blind=args.blind)
    try:
        recorder.run()
    finally:
        for thing in (detector, capture):
            close = getattr(thing, "close", None) or getattr(thing, "release", None)
            if close is not None:
                close()
        window.close()
    print(f"{recorder.saved} mesure(s) enregistrée(s) dans {folder}")
    print("Analyse : python evaluate_dataset.py angles")
    return 0
