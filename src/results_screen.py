"""Results of a session ("Mon bilan") and the last 30 days ("Historique"), drawn like the dashboard.

Both read saved session records (src.session_store), so they work after a session and from
Willy's home. Text is French and translated by the painter; Willy's words come from his script.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter

import cv2
import numpy as np
from PIL import Image

from src.dashboard import CANVAS_SIZE, LINE, MUTED, TEXT, _Painter
from src.home_screen import _background
from src.willy_lines import shared_script
from src.willy_overlay import draw_button
from src.window_viewport import canvas_viewport

QUALITY_COLOURS = {"correct": (52, 140, 94), "to_fix": (214, 141, 38), "unknown": (160, 166, 170)}
BAND = (222, 238, 230)
PAIN = (190, 72, 60)
HISTORY_DAYS = 30
PERIODS = (("7", 7), ("30", 30), ("all", None))


def _canvas(output_size, language):
    width, height = output_size or CANVAS_SIZE
    if width <= 0 or height <= 0:
        width, height = CANVAS_SIZE
    canvas = _background(width, height)
    return canvas, _Painter(canvas, canvas_viewport(CANVAS_SIZE, width, height), language)


def _finish(canvas):
    return cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR)


def _date(record):
    try:
        return dt.datetime.fromisoformat(record["started_at"])
    except (KeyError, ValueError):
        return None


def _duration(seconds, language):
    minutes, secs = divmod(int(round(seconds or 0)), 60)
    return f"{minutes} min {secs:02d} s"


def most_frequent_tip(record):
    tips = Counter(r.get("tip") for r in record.get("reps", []) if r.get("tip") and r.get("quality") == "to_fix")
    return tips.most_common(1)[0][0] if tips else None


def results_lines(record, language):
    """What Willy says about a session (his S8 result lines)."""
    script = shared_script()
    totals = record.get("totals", {})
    total, correct = totals.get("reps", 0), totals.get("correct", 0)
    if not total:
        return [script.text("E7.01", language)]
    lines = [script.text("S8.06", language, n=total)]
    if correct:
        lines.append(script.text("S8.08", language, c=correct))
    tip = most_frequent_tip(record)
    if tip:
        lines.append(script.text("S8.09", language, tip=script.text(tip, language)))
    return lines


def _willy(canvas, p, guide, box):
    if guide is None:
        return
    x1, y1, x2, y2 = p.box(box)
    sprite = guide.render(x2 - x1, y2 - y1)
    canvas.paste(Image.fromarray(sprite, "RGBA"), (x1, y1), Image.fromarray(sprite[..., 3]))


def _bubble(p, lines, box):
    left, top, right, _ = box
    p.rect(box, fill=(255, 255, 255), outline=(190, 200, 198), radius=18)
    y = top + 16
    for line in lines:
        y = p.wrap((left + 18, y), line, right - left - 36, 17, TEXT, max_lines=4) + 6


def _kpi(p, x, label, value):
    p.text((x, 128), label, 12, MUTED)
    p.text((x, 148), value, 30, TEXT, True)


def render_results(record, output_size=None, language="fr", guide=None):
    """One session's results as a BGR image, and its hit boxes."""
    canvas, p = _canvas(output_size, language)
    p.text((48, 30), "Mon bilan", 34)
    started = _date(record)
    if started:
        p.text((50, 78), started.strftime("%d/%m/%Y · %H:%M"), 16, MUTED)
    totals = record.get("totals", {})
    goal = totals.get("goal")
    reps = totals.get("reps", 0)
    _kpi(p, 48, "MOUVEMENTS", f"{reps}/{goal}" if goal else str(reps))
    _kpi(p, 250, "MEILLEUR ANGLE", f"{totals['best_peak_deg']:.0f}°" if totals.get("best_peak_deg") is not None else "—")
    _kpi(p, 452, "ANGLE MOYEN", f"{totals['mean_peak_deg']:.0f}°" if totals.get("mean_peak_deg") is not None else "—")
    _kpi(p, 654, "DURÉE", _duration(record.get("duration_s"), language))

    # One bar per movement: height = peak angle, target band shaded, colour = quality.
    chart = (48, 230, 860, 560)
    p.rect(chart, fill=(255, 255, 255), outline=LINE, radius=10)
    plan = record.get("plan") or {}
    low, high = plan.get("target_min_deg", 80), plan.get("target_max_deg", 100)
    top, bottom, scale_max = chart[1] + 20, chart[3] - 34, 160.

    def y_of(angle):
        return bottom - (bottom - top) * min(angle, scale_max) / scale_max

    p.rect((chart[0] + 46, y_of(high), chart[2] - 14, y_of(low)), fill=BAND)
    for angle in (0, 40, 80, 120, 160):
        p.rule(chart[0] + 46, y_of(angle), chart[2] - 14, y_of(angle), LINE)
        p.text((chart[0] + 10, y_of(angle) - 9), f"{angle}°", 11, MUTED)
    rows = record.get("reps", [])
    if rows:
        width = (chart[2] - chart[0] - 70) / len(rows)
        for i, row in enumerate(rows):
            x = chart[0] + 54 + i * width
            peak = row.get("peak_deg") or 0
            p.rect((x, y_of(peak), x + max(3, width * .7), bottom), fill=QUALITY_COLOURS.get(row.get("quality"), MUTED))
            if len(rows) <= 15 or i % 5 == 4:
                p.text((x, bottom + 8), str(row.get("n", i + 1)), 11, MUTED)
    else:
        p.text((chart[0] + 60, (top + bottom) / 2), "Aucun mouvement compté.", 18, MUTED)
    legend = (("correct", "Correct"), ("to_fix", "À corriger"), ("unknown", "Non mesuré"))
    for i, (quality, label) in enumerate(legend):
        x = 60 + i * 190
        p.rect((x, 578, x + 16, 594), fill=QUALITY_COLOURS[quality], radius=3)
        p.text((x + 24, 576), label, 14, MUTED)
    p.rect((640, 578, 656, 594), fill=BAND, radius=3)
    p.text((664, 576), "Zone cible", 14, MUTED)

    y = 622
    tip = most_frequent_tip(record)
    if tip:
        p.wrap((48, y), "Conseil : " + shared_script().text(tip, language), 800, 17, TEXT, max_lines=2)
        y += 52
    pain_before, pain_after = record.get("pain_before"), record.get("pain_after")
    if pain_before is not None:
        after = f" → {pain_after}/10" if pain_after is not None else ""
        p.text((48, y), f"Douleur : {pain_before}/10{after}", 17, PAIN if (pain_after or 0) - pain_before >= 2 else TEXT)
    _bubble(p, results_lines(record, language), (894, 128, 1232, 400))
    _willy(canvas, p, guide, (980, 430, 1180, 700))
    buttons = (("results_back", "Retour", (48, 760, 248, 816), False),
               ("results_history", "Historique", (1030, 760, 1232, 816), True))
    hit_boxes = []
    for action, label, bounds, primary in buttons:
        draw_button(p, bounds, label, primary=primary, size=19)
        hit_boxes.append((action, bounds))
    return _finish(canvas), hit_boxes


# --------------------------------------------------------------------------- history
def daily(records, today=None, days=HISTORY_DAYS):
    """{date: {"best": deg, "reps": n, "pain": mean pain before}} for the last `days` days."""
    today = today or dt.date.today()
    first = today - dt.timedelta(days=days - 1)
    out = {}
    for record in records:
        started = _date(record)
        if started is None or not first <= started.date() <= today:
            continue
        day = out.setdefault(started.date(), {"best": None, "reps": 0, "pains": []})
        best = (record.get("totals") or {}).get("best_peak_deg")
        if best is not None:
            day["best"] = best if day["best"] is None else max(day["best"], best)
        day["reps"] += (record.get("totals") or {}).get("reps", 0)
        if record.get("pain_before") is not None:
            day["pains"].append(record["pain_before"])
    for day in out.values():
        pains = day.pop("pains")
        day["pain"] = sum(pains) / len(pains) if pains else None
    return out


def trend(days):
    """"improving", "steady", "lower" (best angle, last 3 days vs the 3 before) or None."""
    best = [days[d]["best"] for d in sorted(days) if days[d]["best"] is not None]
    if len(best) < 4:
        return None
    recent = best[-3:]
    before = best[-6:-3]
    diff = sum(recent) / len(recent) - sum(before) / len(before)
    return "improving" if diff > 5 else "lower" if diff < -5 else "steady"


TREND_LINES = {"improving": "E7.04", "steady": "E7.05", "lower": "E7.06", None: "E7.07"}


def render_history(records, output_size=None, language="fr", streak=0, period="30", today=None, message="",
                   can_open=False):
    """The last 30 days as a BGR image, and its hit boxes (back, export period, export)."""
    today = today or dt.date.today()
    canvas, p = _canvas(output_size, language)
    p.text((48, 30), "Historique", 34)
    p.text((50, 78), "Les 30 derniers jours", 16, MUTED)
    days = daily(records, today)
    p.text((900, 40), f"{streak} jour(s) d'affilée" if streak else "Pas de série en cours", 18, TEXT, True)
    # Calendar strip: one cell per day, a dot when there was a session.
    for i in range(HISTORY_DAYS):
        day = today - dt.timedelta(days=HISTORY_DAYS - 1 - i)
        x = 48 + i * 39.5
        is_today = day == today
        p.rect((x, 118, x + 34, 168), fill=(255, 255, 255), outline=TEXT if is_today else LINE, radius=6)
        p.text((x + 9 if day.day < 10 else x + 5, 122), str(day.day), 12, MUTED)
        if day in days:
            p.draw.ellipse(p.box((x + 11, 146, x + 23, 158)), fill=QUALITY_COLOURS["correct"])

    def x_of(day):
        return 70 + (HISTORY_DAYS - 1 - (today - day).days) * (1140 / (HISTORY_DAYS - 1))

    # Best angle per day.
    chart = (48, 196, 1232, 448)
    p.rect(chart, fill=(255, 255, 255), outline=LINE, radius=10)
    p.text((chart[0] + 16, chart[1] + 10), "MEILLEUR ANGLE PAR JOUR", 12, MUTED)
    top, bottom = chart[1] + 36, chart[3] - 16

    def y_angle(angle):
        return bottom - (bottom - top) * min(max(angle, 0), 160) / 160

    for angle in (40, 80, 120):
        p.rule(chart[0] + 16, y_angle(angle), chart[2] - 16, y_angle(angle), LINE)
        p.text((chart[2] - 52, y_angle(angle) - 16), f"{angle}°", 11, MUTED)
    points = [(x_of(d), y_angle(v["best"])) for d, v in sorted(days.items()) if v["best"] is not None]
    if len(points) > 1:
        p.draw.line([p.point(*xy) for xy in points], fill=TEXT, width=max(1, round(2 * p.scale)))
    for x, y in points:
        p.draw.ellipse(p.box((x - 5, y - 5, x + 5, y + 5)), fill=TEXT)
    if not points:
        p.text((chart[0] + 40, (top + bottom) / 2), "Pas encore de séance enregistrée.", 18, MUTED)

    # Movements per day, and pain before the session.
    reps_chart, pain_chart = (48, 468, 628, 668), (652, 468, 1232, 668)
    for box, title in ((reps_chart, "MOUVEMENTS PAR JOUR"), (pain_chart, "DOULEUR AVANT LA SÉANCE (0-10)")):
        p.rect(box, fill=(255, 255, 255), outline=LINE, radius=10)
        p.text((box[0] + 16, box[1] + 10), title, 12, MUTED)
    most = max([v["reps"] for v in days.values()] + [1])
    span = (reps_chart[2] - reps_chart[0] - 40) / HISTORY_DAYS
    for day, values in days.items():
        x = reps_chart[0] + 20 + (HISTORY_DAYS - 1 - (today - day).days) * span
        height = (reps_chart[3] - reps_chart[1] - 56) * values["reps"] / most
        p.rect((x, reps_chart[3] - 16 - height, x + span * .7, reps_chart[3] - 16), fill=QUALITY_COLOURS["correct"])
    pspan = (pain_chart[2] - pain_chart[0] - 40) / HISTORY_DAYS
    pains = [(pain_chart[0] + 20 + (HISTORY_DAYS - 1 - (today - d).days) * pspan,
              pain_chart[3] - 16 - (pain_chart[3] - pain_chart[1] - 56) * v["pain"] / 10)
             for d, v in sorted(days.items()) if v["pain"] is not None]
    if len(pains) > 1:
        p.draw.line([p.point(*xy) for xy in pains], fill=PAIN, width=max(1, round(2 * p.scale)))
    for x, y in pains:
        p.draw.ellipse(p.box((x - 4, y - 4, x + 4, y + 4)), fill=PAIN)

    line_id = TREND_LINES[trend(days)]
    p.wrap((48, 688), shared_script().text(line_id, language), 1180, 18, TEXT, max_lines=2)
    if message:
        p.text((48, 742), message, 15, QUALITY_COLOURS["correct"], True)
    hit_boxes = []
    draw_button(p, (48, 772, 228, 820), "Retour", size=18)
    hit_boxes.append(("history_back", (48, 772, 228, 820)))
    labels = {"7": "7 jours", "30": "30 jours", "all": "Tout"}
    for i, (key, _) in enumerate(PERIODS):
        bounds = (560 + i * 136, 772, 684 + i * 136, 820)
        draw_button(p, bounds, labels[key], primary=key == period, size=17)
        hit_boxes.append((f"period:{key}", bounds))
    if can_open:
        draw_button(p, (244, 772, 520, 820), "Ouvrir le dossier", size=17)
        hit_boxes.append(("history_open_folder", (244, 772, 520, 820)))
    draw_button(p, (1000, 772, 1232, 820), "Exporter", primary=True, size=18)
    hit_boxes.append(("history_export", (1000, 772, 1232, 820)))
    return _finish(canvas), hit_boxes, line_id
