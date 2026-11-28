"""Accessibility settings (Phase 10.2): large text, high contrast, slower speech, subtitles.

The physio sets them in the settings' second page ("Écran et voix"); they are kept in the
profile and applied to every screen through the dashboard's painter (src.dashboard._Painter):

- large text: every font is 1.25 times bigger, and labels that would overflow their button
  shrink back just enough;
- high contrast: every text is drawn at least 7:1 against what is behind it (WCAG 2 contrast
  ratio, the AAA level), and outlines at least 3:1;
- slower speech: Piper's length_scale x1.2, the Windows voice's rate x0.8;
- subtitles: every line Willy says also shows in his bubble, sound on or off.
"""
from __future__ import annotations

from dataclasses import dataclass

TEXT_SCALE = 1.25
SLOW_LENGTH_SCALE = 1.2   # Piper: a greater length_scale is slower speech
SLOW_RATE = .8            # Windows voice: words per minute x0.8
TEXT_CONTRAST = 7.        # high contrast: text against its background (WCAG AAA; AA is 4.5)
OUTLINE_CONTRAST = 3.     # high contrast: borders of buttons and boxes (WCAG 1.4.11)


@dataclass
class Accessibility:
    large_text: bool = False
    high_contrast: bool = False
    slow_speech: bool = False
    subtitles: bool = False

    @property
    def text_scale(self):
        return TEXT_SCALE if self.large_text else 1.

    def key(self):
        """For caches of drawn screens: they change with these settings."""
        return (self.large_text, self.high_contrast)


CURRENT = Accessibility()  # this computer's settings, set by the app from the profile


def set_current(settings):
    global CURRENT
    CURRENT = settings
    return CURRENT


def current():
    return CURRENT


# --------------------------------------------------------------------------- contrast
def _channel(value):
    value /= 255.
    return value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4


def luminance(rgb):
    """WCAG 2 relative luminance of an sRGB colour (0 black to 1 white)."""
    r, g, b = (_channel(float(c)) for c in rgb[:3])
    return .2126 * r + .7152 * g + .0722 * b


def contrast(a, b):
    """WCAG 2 contrast ratio between two colours, from 1 to 21."""
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + .05) / (min(la, lb) + .05)


def readable(color, background, ratio=TEXT_CONTRAST):
    """`color`, made darker (on a light background) or lighter (on a dark one) until it reaches
    `ratio` against `background`; unchanged when it already does. Keeps the colour's hue."""
    color = tuple(int(c) for c in color[:3])
    if contrast(color, background) >= ratio:
        return color
    target = (0, 0, 0) if luminance(background) > .18 else (255, 255, 255)
    low, high = 0., 1.
    for _ in range(18):  # the smallest step toward black or white that is enough
        mid = (low + high) / 2
        mixed = tuple(round(c + (t - c) * mid) for c, t in zip(color, target))
        if contrast(mixed, background) >= ratio:
            high = mid
        else:
            low = mid
    return tuple(round(c + (t - c) * high) for c, t in zip(color, target))
