"""A simple full-screen notice with Willy: loading, camera lost, something went wrong.

Drawn like Willy's home (same background and painter), so it scales with the window and
translates to English. Buttons are optional; their boxes are returned for clicks.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from src.dashboard import CANVAS_SIZE, MUTED, TEXT, _Painter
from src.home_screen import _background
from src.i18n import tr
from src.willy_overlay import draw_button
from src.window_viewport import canvas_viewport


def render_notice(title, body="", output_size=None, language="fr", guide=None, buttons=(), detail=""):
    """BGR image and hit boxes [(action, bounds)] for (action, label, primary) buttons."""
    width, height = output_size or CANVAS_SIZE
    if width <= 0 or height <= 0:
        width, height = CANVAS_SIZE
    canvas = _background(width, height)
    p = _Painter(canvas, canvas_viewport(CANVAS_SIZE, width, height), language)
    p.text((48, 30), "mouvement", 34)
    if guide is not None:
        x1, y1, x2, y2 = p.box((90, 160, 520, 760))
        sprite = guide.render(x2 - x1, y2 - y1)
        canvas.paste(Image.fromarray(sprite, "RGBA"), (x1, y1), Image.fromarray(sprite[..., 3]))
    p.rect((600, 200, 1220, 520), fill=(255, 255, 255), outline=(190, 200, 198), radius=26)
    end = p.wrap((636, 236), title, 548, 32, TEXT, True, max_lines=3)
    if body:
        end = p.wrap((636, end + 14), body, 548, 20, TEXT, max_lines=5)
    if detail:
        p.wrap((636, 540), detail, 560, 13, MUTED, max_lines=4)
    hit_boxes = []
    x = 600
    for action, label, primary in buttons:
        w = max(200, p.draw.textlength(tr(label, language), font=p.font(20, True)) / p.sx + 64)  # as drawn
        bounds = (x, 640, x + w, 706)
        draw_button(p, bounds, label, primary=primary, size=20)
        hit_boxes.append((action, bounds))
        x += w + 20
    return cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR), hit_boxes
