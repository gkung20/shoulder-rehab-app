"""Export for the physio: a PDF report, a CSV (one row per movement) and the raw session files.

Everything goes to a new folder in Documents\\Mouvement (MOUVEMENT_EXPORT_DIR overrides it):
    bilan_2026-11-25_1712/bilan.pdf, mouvements.csv, seances/*.json
Nothing is sent anywhere; the patient or physio copies the folder.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

from src.results_screen import daily  # noqa: E402

PERIOD_DAYS = {"7": 7, "30": 30, "all": None}

WORDS = {
    "title": ("Bilan Mouvement", "Mouvement report"),
    "subtitle": ("Rééducation de l'épaule, exercices à la maison", "Shoulder rehabilitation, home exercises"),
    "patient": ("Patient", "Patient"),
    "arm": ("Bras", "Arm"),
    "period": ("Période", "Period"),
    "plan": ("Plan", "Plan"),
    "plan_text": ("Cible {lo}-{hi}°, {reps} répétitions x {sets} séries, repos {rest} s, maintien {hold} s",
                  "Target {lo}-{hi}°, {reps} repetitions x {sets} sets, rest {rest} s, hold {hold} s"),
    "pain_bands": ("Douleur : normale jusqu'à {go}/10, douce jusqu'à {gentle}/10",
                   "Pain: normal up to {go}/10, gentle up to {gentle}/10"),
    "sessions": ("Séances", "Sessions"),
    "none": ("Aucune séance sur cette période.", "No session in this period."),
    "date": ("Date", "Date"),
    "reps": ("Mouv.", "Mov."),
    "correct": ("Corrects", "Correct"),
    "best": ("Meilleur", "Best"),
    "mean": ("Moyen", "Average"),
    "pain": ("Douleur avant / après", "Pain before / after"),
    "notes": ("Remarques", "Notes"),
    "pain_up": ("douleur en hausse", "pain went up"),
    "gentle": ("séance douce", "gentle session"),
    "partial": ("interrompue", "interrupted"),
    "chart": ("Meilleur angle par jour", "Best angle per day"),
    "target": ("Zone cible", "Target zone"),
    "right": ("droit", "right"),
    "left": ("gauche", "left"),
    "all": ("tout", "all"),
    "days": ("{n} derniers jours", "last {n} days"),
    "disclaimer": ("Prototype éducatif : angles estimés par la caméra, non validés cliniquement. "
                   "Ce document aide la discussion avec le kinésithérapeute et ne remplace pas son examen.",
                   "Educational prototype: angles estimated by the camera, not clinically validated. "
                   "This document supports the discussion with the physiotherapist and does not replace an examination."),
}
CSV_HEADERS = {
    "fr": ["date", "heure", "seance", "mouvement", "angle_max_deg", "maintien_s", "montee_s", "descente_s",
           "qualite", "problemes", "douleur_avant", "douleur_apres"],
    "en": ["date", "time", "session", "movement", "peak_angle_deg", "hold_s", "rise_s", "lower_s",
           "quality", "issues", "pain_before", "pain_after"],
}


def w(key, language, **values):
    text = WORDS[key][1 if language == "en" else 0]
    return text.format(**values) if values else text


def number(value, language):
    """12.5 -> "12,5" in French, "12.5" in English; 80.0 -> "80"."""
    text = f"{value:g}"
    return text.replace(".", ",") if language != "en" else text


def export_root():
    override = os.environ.get("MOUVEMENT_EXPORT_DIR")
    return Path(override) if override else Path.home() / "Documents" / "Mouvement"


def select(records, period, today=None):
    days = PERIOD_DAYS.get(period)
    if days is None:
        return list(records)
    first = (today or dt.date.today()) - dt.timedelta(days=days - 1)
    return [r for r in records if _start(r) and _start(r).date() >= first]


def _start(record):
    try:
        return dt.datetime.fromisoformat(record["started_at"])
    except (KeyError, ValueError):
        return None


def write_csv(records, path, language="fr"):
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:  # BOM: Excel opens accents correctly
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(CSV_HEADERS["en" if language == "en" else "fr"])
        for index, record in enumerate(records, 1):
            start = _start(record)
            for rep in record.get("reps", []):
                writer.writerow([start.date().isoformat() if start else "", start.strftime("%H:%M") if start else "",
                                 index, rep.get("n"), rep.get("peak_deg"), rep.get("hold_s"), rep.get("rise_s"),
                                 rep.get("lower_s"), rep.get("quality"), " | ".join(rep.get("issues", [])),
                                 record.get("pain_before"), record.get("pain_after")])


def _chart(records, language, plan):
    days = daily(records, max((_start(r).date() for r in records if _start(r)), default=dt.date.today()),
                 days=3650)
    points = sorted((d, v["best"]) for d, v in days.items() if v["best"] is not None)
    figure, axis = plt.subplots(figsize=(7.2, 2.4), dpi=120)
    if plan:
        axis.axhspan(plan.get("target_min_deg", 80), plan.get("target_max_deg", 100), color="#dcefe5",
                     label=w("target", language))
    if points:
        axis.plot([p[0] for p in points], [p[1] for p in points], "o-", color="#1a1d20", linewidth=1.5, markersize=4)
    axis.set_ylim(0, 170)
    axis.set_ylabel("°")
    axis.set_title(w("chart", language), fontsize=10)
    axis.grid(alpha=.3)
    figure.autofmt_xdate()
    figure.tight_layout()
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png")
    plt.close(figure)
    buffer.seek(0)
    return buffer


def write_pdf(records, path, language="fr", plan=None, patient="", arm="", period="30"):
    styles = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=styles["Title"], fontSize=18, spaceAfter=2)
    small = ParagraphStyle("s", parent=styles["Normal"], fontSize=8.5, leading=11, textColor=colors.HexColor("#555b60"))
    body = ParagraphStyle("b", parent=styles["Normal"], fontSize=10, leading=13)
    story = [Paragraph(escape(w("title", language)), title), Paragraph(escape(w("subtitle", language)), small),
             Spacer(1, 10)]
    span = w("all", language) if PERIOD_DAYS.get(period) is None else w("days", language, n=PERIOD_DAYS[period])
    meta = [(w("patient", language), patient or "-"), (w("arm", language), w(arm, language) if arm in ("right", "left") else "-"),
            (w("period", language), span)]
    if plan:
        meta.append((w("plan", language), w("plan_text", language, lo=number(plan["target_min_deg"], language),
                                            hi=number(plan["target_max_deg"], language), reps=plan["reps_per_set"],
                                            sets=plan["sets"], rest=plan["rest_between_sets_sec"],
                                            hold=number(plan["hold_sec"], language))))
        meta.append(("", w("pain_bands", language, go=plan["pain_go_max"], gentle=plan["pain_gentle_max"])))
    for label, value in meta:
        story.append(Paragraph(f"<b>{escape(label)}</b> {escape(str(value))}" if label else escape(str(value)), body))
    story.append(Spacer(1, 8))
    story.append(Image(_chart(records, language, plan), width=500, height=167))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"<b>{escape(w('sessions', language))}</b>", body))
    if not records:
        story.append(Paragraph(escape(w("none", language)), body))
    else:
        header = [w(k, language) for k in ("date", "reps", "correct", "best", "mean", "pain", "notes")]
        rows = [header]
        for record in records:
            start, totals = _start(record), record.get("totals", {})
            notes = []
            before, after = record.get("pain_before"), record.get("pain_after")
            if before is not None and after is not None and after - before >= 2:
                notes.append(w("pain_up", language))
            if record.get("gentle"):
                notes.append(w("gentle", language))
            if record.get("partial"):
                notes.append(w("partial", language))
            best, mean = totals.get("best_peak_deg"), totals.get("mean_peak_deg")
            rows.append([start.strftime("%d/%m/%Y %H:%M") if start else "-", totals.get("reps", 0),
                         totals.get("correct", 0), f"{best:.0f}°" if best is not None else "-",
                         f"{mean:.0f}°" if mean is not None else "-",
                         f"{'-' if before is None else before} / {'-' if after is None else after}", ", ".join(notes)])
        table = Table(rows, colWidths=[88, 40, 52, 52, 48, 96, 140], repeatRows=1)
        table.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f1")),
            ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#c9cfcd")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story.append(table)
    story += [Spacer(1, 12), Paragraph(escape(w("disclaimer", language)), small)]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=40, rightMargin=40, topMargin=36, bottomMargin=36,
                      title=w("title", language)).build(story)


def export_history(records, period="30", language="fr", plan=None, patient="", arm="", root=None, now=None):
    """Write the PDF, the CSV and copies of the session files; returns the new folder."""
    chosen = select(records, period, (now or dt.datetime.now()).date())
    folder = Path(root or export_root()) / f"bilan_{(now or dt.datetime.now()).strftime('%Y-%m-%d_%H%M%S')}"
    (folder / "seances").mkdir(parents=True, exist_ok=True)
    write_pdf(chosen, folder / "bilan.pdf", language, plan, patient, arm, period)
    write_csv(chosen, folder / "mouvements.csv", language)
    for record in chosen:
        clean = {k: v for k, v in record.items() if not k.startswith("_")}
        name = record.get("_file") or f"{_start(record).strftime('%Y-%m-%d_%H%M%S')}.json"
        (folder / "seances" / name).write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8")
    return folder
