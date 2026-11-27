"""Willy's home screen: the first thing the patient sees when the app opens.

Willy stands large on the left and talks in his bubble on the right; the buttons of the
current step sit under the bubble. Everything is drawn at the window's real pixel size.
"""
from types import SimpleNamespace

import cv2
import numpy as np
from PIL import Image

from src import layout as L

from src.dashboard import CANVAS_SIZE, MUTED, TEXT, _Painter
from src.i18n import ui
from src.window_viewport import canvas_viewport
from src.willy_overlay import GLOW, _wrap, draw_button, draw_dots

HOME_WILLY_BOX = L.HOME_WILLY_BOX
BUBBLE_LEFT, BUBBLE_TOP, BUBBLE_RIGHT = L.HOME_BUBBLE.x0, L.HOME_BUBBLE.y0, L.HOME_BUBBLE.x1
LANGUAGE_BOX = L.HOME_LANGUAGE_BUTTON
REPLAY_BOX = L.HOME_REPLAY_BUTTON


def home_buttons(director):
    """Buttons always on the home screen (besides the current step's): language, tour replay."""
    buttons = []
    if director.profile.language is not None and director.current is not None and not director.current.bilingual:
        other = "Français" if director.language == "en" else "English"
        buttons.append(("language", other, LANGUAGE_BOX))
        if director.profile.tour_done and not director.in_tour:
            buttons.append(("replay_tour", ui("replay_tour", director.language), REPLAY_BOX))
            buttons.append(("open_settings", "Réglages kiné", L.HOME_SETTINGS_BUTTON))
            if getattr(director, "results_available", False):
                buttons.append(("open_results", "Mes résultats", L.HOME_RESULTS_BUTTON))
    return buttons


def _background(width, height):
    top = np.array((247, 250, 249), np.float32)
    bottom = np.array((222, 238, 234), np.float32)
    t = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
    image = top * (1 - t) + bottom * t
    return Image.fromarray(np.repeat(image, width, axis=1).astype(np.uint8))


def render_home(director, guide=None, output_size=None, speaking=False):
    """The home screen as a BGR image; button boxes go to director.overlay.hit_boxes."""
    width, height = output_size or CANVAS_SIZE
    if width <= 0 or height <= 0:
        width, height = CANVAS_SIZE
    viewport = canvas_viewport(CANVAS_SIZE, width, height)
    canvas = _background(width, height)
    p = _Painter(canvas, viewport, director.language)
    p.text((48, 30), "mouvement", 34)
    p.text((50, 78), ui("tagline", director.language), 16, MUTED)
    hit_boxes = []
    for action, label, bounds in home_buttons(director):
        draw_button(p, bounds, label, primary=False, size=17)
        hit_boxes.append((action, bounds))

    # Willy, large, standing on the floor of the screen.
    mouth = (420, 330)
    if guide is not None:
        state = SimpleNamespace(status="", metrics={}, phase=None, cue=None)
        guide.point_side = "R"  # toward the bubble
        guide.update(state, "ready", SimpleNamespace(arm="right"), speaking=speaking)
        x1, y1, x2, y2 = p.box(HOME_WILLY_BOX)
        sprite = guide.render(x2 - x1, y2 - y1)
        canvas.paste(Image.fromarray(sprite, "RGBA"), (x1, y1), Image.fromarray(sprite[..., 3]))
        mx, my = guide.anchor("mouth", HOME_WILLY_BOX[2] - HOME_WILLY_BOX[0], HOME_WILLY_BOX[3] - HOME_WILLY_BOX[1])
        mouth = (HOME_WILLY_BOX[0] + mx, HOME_WILLY_BOX[1] + my)

    overlay = director.overlay
    bottom = BUBBLE_TOP
    if overlay.bubble:
        bottom = _bubble(p, overlay.bubble, mouth)
    if overlay.progress:  # the tour's stages, under the bubble
        draw_dots(p, BUBBLE_LEFT + 8, bottom + 22, overlay.progress, radius=6, gap=8)
        bottom += 22
    y = bottom + 34
    if overlay.sample_button:
        label = ui("pause_sample", director.language)
        w = p.draw.textlength(label, font=p.font(19, True)) / p.sx + 56
        bounds = (BUBBLE_LEFT, y, BUBBLE_LEFT + w, y + 58)
        for grow in (10, 6):
            p.rect((bounds[0] - grow, bounds[1] - grow, bounds[2] + grow, bounds[3] + grow), outline=GLOW, radius=12 + grow)
        draw_button(p, bounds, label, primary=True, size=19)
        y += 92
    # The buttons in one row under the bubble; smaller when three of them would not fit.
    available = 1240 - BUBBLE_LEFT
    for size, least, gap in ((21, 190, 18), (19, 150, 14), (17, 120, 12)):
        widths = [max(least, p.draw.textlength(b.label, font=p.font(size, True)) / p.sx + 2.6 * size)
                  for b in overlay.buttons]
        if sum(widths) + gap * max(0, len(widths) - 1) <= available:
            break
    x = BUBBLE_LEFT
    for button, w in zip(overlay.buttons, widths):
        bounds = (x, y, x + w, y + 66)
        draw_button(p, bounds, button.label, button.primary, size=size)
        hit_boxes.append((button.action, bounds))
        x += w + gap
    overlay.hit_boxes = hit_boxes
    p.text((48, 812), "Prototype éducatif · Mesures estimées. Arrêtez en cas de douleur.", 12, MUTED)
    return cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR)


def _bubble(p, paragraphs, mouth):
    size, small = 30, 25
    width = BUBBLE_RIGHT - BUBBLE_LEFT
    wrapped = [(_wrap(p, text, width - 64, size if i == 0 else small), size if i == 0 else small)
               for i, text in enumerate(paragraphs)]
    height = 44 + sum(len(lines) * s * 1.35 for lines, s in wrapped) + 18 * (len(wrapped) - 1)
    rect = (BUBBLE_LEFT, BUBBLE_TOP, BUBBLE_RIGHT, BUBBLE_TOP + height)
    p.rect((rect[0] + 4, rect[1] + 6, rect[2] + 4, rect[3] + 6), fill=(200, 212, 209), radius=28)
    p.rect(rect, fill=(255, 255, 255), outline=(190, 200, 198), radius=28)
    # Tail toward Willy's mouth, on the bubble's left edge.
    ty = min(max(mouth[1], rect[1] + 44), rect[3] - 44)
    tail = [p.point(rect[0] + 1, ty - 20), p.point(rect[0] - 40, mouth[1] if abs(mouth[1] - ty) < 60 else ty + 10),
            p.point(rect[0] + 1, ty + 20)]
    p.draw.polygon(tail, fill=(255, 255, 255))
    p.draw.line(tail, fill=(190, 200, 198), width=max(1, round(p.scale)))
    y = rect[1] + 24
    for index, (lines, s) in enumerate(wrapped):
        for line in lines:
            p.text((rect[0] + 32, y), line, s, TEXT if index == 0 else MUTED)
            y += s * 1.35
        y += 18
    return rect[3]
