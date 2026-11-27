"""Willy's speech bubble, the tour's spotlight and its buttons, drawn over a screen.

Drawing goes through the screen's painter (logical 1280 x 840 coordinates scaled to the
window), so the text stays sharp at any size. Button boxes are recorded in `overlay.hit_boxes`
while drawing: the mouse uses exactly what was drawn.
"""
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

TEXT = (26, 29, 32)
MUTED = (112, 117, 122)
LINE = (222, 225, 227)
ACCENT = (38, 132, 120)      # Willy's teal
GLOW = (255, 196, 61)        # spotlight ring
BUBBLE = (255, 255, 255)
SHADOW = (0, 0, 0)


@dataclass
class TourButton:
    action: str
    label: str
    primary: bool = False


@dataclass
class Overlay:
    """What Willy shows on top of a screen this frame."""
    bubble: list = field(default_factory=list)   # paragraphs of the current line(s)
    buttons: list = field(default_factory=list)  # TourButton, inside the bubble
    spotlight: tuple | None = None                # logical rect left bright; the rest dims
    willy_big: bool = False                       # the exercise demo: Willy in the large panel
    highlight: str | None = None                  # body point circled on the big Willy
    text_field: tuple | None = None               # (value, hint) while the patient types a name
    sample_button: str | None = None              # a glowing button drawn for show (Scenario 2)
    compact: bool = False                         # an everyday line: small bubble, no buttons
    dim: bool = True                              # False during exercise: ring the zone, keep the screen bright
    hit_boxes: list = field(default_factory=list)

    def action_at(self, x, y):
        for action, (left, top, right, bottom) in self.hit_boxes:
            if left <= x < right and top <= y < bottom:
                return action
        return None


def _intersects(a, b, margin=10):
    return not (a[2] + margin <= b[0] or b[2] + margin <= a[0] or a[3] + margin <= b[1] or b[3] + margin <= a[1])


def dim_outside(canvas, p, rect, strength=.58, keep=()):
    """Darken the whole screen except `rect` (and the `keep` areas, such as Willy), then ring `rect`."""
    arr = np.asarray(canvas).astype(np.float32)
    mask = np.zeros(arr.shape[:2], np.float32)
    for area, grow in [(rect, 6)] + [(k, 0) for k in keep]:
        if area is None:
            continue
        x1, y1, x2, y2 = p.box((area[0] - grow, area[1] - grow, area[2] + grow, area[3] + grow))
        mask[max(0, y1):y2, max(0, x1):x2] = 1.
    keep = 1. - strength * (1. - mask)
    arr = arr * keep[..., None] + np.array((18, 24, 28), np.float32) * (1. - keep[..., None])
    canvas.paste(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)))
    if rect is not None:
        p.rect((rect[0] - 6, rect[1] - 6, rect[2] + 6, rect[3] + 6), outline=GLOW, radius=10)
        p.rect((rect[0] - 8, rect[1] - 8, rect[2] + 8, rect[3] + 8), outline=GLOW, radius=12)


def _wrap(p, text, width, size, bold=False):
    font = p.font(size, bold)
    lines, line = [], ""
    for word in str(text).split():
        candidate = f"{line} {word}".strip()
        if line and p.draw.textlength(candidate, font=font) > width * p.sx:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def _button_width(p, label, size=17):
    return p.draw.textlength(label, font=p.font(size, True)) / p.sx + 40


def draw_button(p, bounds, label, primary=False, size=17):
    if primary:
        p.rect(bounds, fill=TEXT, radius=8)
        color = (255, 255, 255)
    else:
        p.rect(bounds, fill=(255, 255, 255), outline=(150, 156, 161), radius=8)
        color = TEXT
    from src.i18n import tr
    width = p.draw.textlength(tr(str(label), getattr(p, "lang", "fr")), font=p.font(size, True)) / p.sx  # as drawn
    left, top, right, bottom = bounds
    p.text((left + (right - left - width) / 2, top + (bottom - top - size) / 2 - 3), label, size, color, True)


def bubble_layout(p, overlay, candidates, width, size):
    """Bubble rect, wrapped paragraphs and the button row, at the first candidate clear of the spotlight."""
    paragraphs = [_wrap(p, text, width - 44, size, bold=False) for text in overlay.bubble if text]
    line_h = size * 1.38
    height = 16 + sum(len(lines) for lines in paragraphs) * line_h + max(0, len(paragraphs) - 1) * 10 + 10
    if overlay.text_field is not None:
        height += 86
    height += 58 if overlay.buttons else 6
    chosen = None
    for anchor_x, anchor_y, align in candidates:
        left = anchor_x if align.endswith("left") else anchor_x - width
        top = anchor_y - height if align.startswith("bottom") else anchor_y
        rect = (left, top, left + width, top + height)
        if overlay.spotlight is None or not _intersects(rect, overlay.spotlight):
            chosen = rect
            break
    if chosen is None:
        anchor_x, anchor_y, align = candidates[0]
        left = anchor_x if align.endswith("left") else anchor_x - width
        top = anchor_y - height if align.startswith("bottom") else anchor_y
        chosen = (left, top, left + width, top + height)
    return chosen, paragraphs, line_h


def draw_bubble(canvas, p, overlay, candidates, tail_to, width=360, size=20):
    """Draw Willy's bubble with its tail toward `tail_to` (logical point); record button boxes."""
    overlay.hit_boxes = []
    if not overlay.bubble:
        return None
    rect, paragraphs, line_h = bubble_layout(p, overlay, candidates, width, size)
    left, top, right, bottom = rect
    # Soft shadow, then the bubble and its tail.
    p.rect((left + 3, top + 5, right + 3, bottom + 5), fill=(205, 209, 212), radius=20)
    p.rect(rect, fill=BUBBLE, outline=(196, 201, 205), radius=20)
    _tail(p, rect, tail_to)
    y = top + 16
    for index, lines in enumerate(paragraphs):
        color = TEXT if index == 0 else MUTED
        for line in lines:
            p.text((left + 22, y), line, size, color)
            y += line_h
        y += 10
    if overlay.text_field is not None:
        value, hint = overlay.text_field
        box = (left + 22, y + 2, right - 22, y + 46)
        p.rect(box, fill=(255, 255, 255), outline=ACCENT, radius=8)
        caret = "|" if int(_now() * 2) % 2 == 0 else ""
        p.text((box[0] + 14, box[1] + 11), (value or "") + caret, size, TEXT)
        p.text((left + 22, y + 52), hint, 14, MUTED)
        y += 86
    if overlay.buttons:
        x = right - 18
        row_top = bottom - 56
        for button in reversed(overlay.buttons):
            w = _button_width(p, button.label)
            bounds = (x - w, row_top + 2, x, row_top + 44)
            draw_button(p, bounds, button.label, button.primary)
            overlay.hit_boxes.append((button.action, bounds))
            x -= w + 10
    return rect


def _tail(p, rect, point):
    """A small triangle from the bubble's nearest edge toward Willy, joined to the bubble."""
    if point is None:
        return
    left, top, right, bottom = rect
    px, py = point
    if py > bottom:          # Willy below
        base = min(max(px, left + 40), right - 40)
        a, b, tip = (base - 16, bottom - 1), (base + 16, bottom - 1), (base + (px - base) * .35, bottom + 26)
    elif py < top:           # Willy above
        base = min(max(px, left + 40), right - 40)
        a, b, tip = (base - 16, top + 1), (base + 16, top + 1), (base + (px - base) * .35, top - 26)
    elif px > right:         # Willy to the right
        base = min(max(py, top + 30), bottom - 30)
        a, b, tip = (right - 1, base - 16), (right - 1, base + 16), (right + 26, base + (py - base) * .35)
    else:                    # Willy to the left
        base = min(max(py, top + 30), bottom - 30)
        a, b, tip = (left + 1, base - 16), (left + 1, base + 16), (left - 26, base + (py - base) * .35)
    p.draw.polygon([p.point(*a), p.point(*tip), p.point(*b)], fill=BUBBLE)
    width = max(1, round(p.scale))
    p.draw.line([p.point(*a), p.point(*tip), p.point(*b)], fill=(196, 201, 205), width=width)


def ring_zone(p, rect):
    """The spotlight's ring alone, without dimming the screen (used while the patient exercises)."""
    p.rect((rect[0] - 6, rect[1] - 6, rect[2] + 6, rect[3] + 6), outline=GLOW, radius=10)
    p.rect((rect[0] - 8, rect[1] - 8, rect[2] + 8, rect[3] + 8), outline=GLOW, radius=12)


def ring(p, center, radius=34):
    """A glowing ring around a body point of the big Willy (shoulder, trunk, arm)."""
    cx, cy = center
    for grow, width in ((0, 4), (6, 2)):
        r = radius + grow
        x1, y1 = p.point(cx - r, cy - r)
        x2, y2 = p.point(cx + r, cy + r)
        p.draw.ellipse((x1, y1, x2, y2), outline=GLOW, width=max(1, round(width * p.scale)))


def _now():
    import time
    return time.monotonic()
