"""The pain check: 0 to 10, before and after a session, and after "J'ai mal".

Eleven big buttons from green (0) to red (10); keys 0 to 9 work too. After "J'ai mal", two
choices follow: rest a minute and continue gently, or end the session (only the second when
the pain is in the plan's stop band, or "J'ai mal" was pressed too often).
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from src.dashboard import CANVAS_SIZE, MUTED, TEXT, _Painter
from src.home_screen import _background
from src.willy_overlay import draw_button
from src.window_viewport import canvas_viewport

GREEN, AMBER, RED = (52, 140, 94), (214, 141, 38), (190, 72, 60)
QUESTIONS = {"before": "E9.01", "after": "E9.05", "hurt": "E9.01"}


@dataclass
class PainCheck:
    moment: str = "before"      # "before", "after" or "hurt"
    value: int | None = None
    choices: bool = False       # hurt: the number is in, now rest-and-continue or end
    can_continue: bool = True   # hurt: False when the session must end


def pain_colour(value):
    """Green at 0, amber at 5, red at 10."""
    a, b, t = (GREEN, AMBER, value / 5) if value <= 5 else (AMBER, RED, (value - 5) / 5)
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def render_pain(check, question, output_size=None, language="fr", guide=None, note=""):
    """The pain check as a BGR image, and its hit boxes: pain:0..10, hurt_rest, hurt_end."""
    width, height = output_size or CANVAS_SIZE
    if width <= 0 or height <= 0:
        width, height = CANVAS_SIZE
    canvas = _background(width, height)
    p = _Painter(canvas, canvas_viewport(CANVAS_SIZE, width, height), language)
    p.text((48, 30), "mouvement", 34)
    p.rect((380, 110, 1232, 250), fill=(255, 255, 255), outline=(190, 200, 198), radius=24)
    p.wrap((410, 136), question, 790, 30, TEXT, True, max_lines=2)
    hit_boxes = []
    if not check.choices:
        for value in range(11):
            x = 48 + value * 107
            bounds = (x, 330, x + 95, 440)
            selected = check.value == value
            p.rect(bounds, fill=pain_colour(value), outline=TEXT if selected else None, radius=14)
            label = str(value)
            size = 40
            text_width = p.draw.textlength(label, font=p.font(size, True)) / p.sx
            p.text((x + (95 - text_width) / 2, 358), label, size, (255, 255, 255), True)
            hit_boxes.append((f"pain:{value}", bounds))
        p.text((48, 456), "Aucune douleur", 16, MUTED)
        p.text((1100, 456), "Douleur maximale", 16, MUTED)
    else:
        p.text((48, 330), f"Douleur : {check.value}/10", 26, pain_colour(check.value), True)
        if check.can_continue:
            draw_button(p, (48, 400, 600, 480), "Repos 1 minute, puis en douceur", size=21)
            hit_boxes.append(("hurt_rest", (48, 400, 600, 480)))
        draw_button(p, (632, 400, 1100, 480), "Terminer la séance", primary=True, size=21)
        hit_boxes.append(("hurt_end", (632, 400, 1100, 480)))
    if note:
        p.wrap((48, 520), note, 1100, 19, TEXT, max_lines=3)
    if guide is not None:
        x1, y1, x2, y2 = p.box((60, 100, 340, 300))
        sprite = guide.render(x2 - x1, y2 - y1)
        canvas.paste(Image.fromarray(sprite, "RGBA"), (x1, y1), Image.fromarray(sprite[..., 3]))
    p.text((48, 812), "Arrêtez l'exercice si la douleur augmente.", 13, MUTED)
    return cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR), hit_boxes
