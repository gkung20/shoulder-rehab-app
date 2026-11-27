"""Validation report (Phase 7.3): `python evaluate_dataset.py angles`.

Reads the study folder written by `record_clip.py angles` (see src/validation_data.py) and
compares the app with the references:

- angles, per target position and overall: mean absolute error, mean bias (app - goniometer),
  Bland-Altman 95% limits of agreement (corrected for repeated trials per volunteer, Bland &
  Altman 2007), ICC(2,1) (two-way random, absolute agreement, single measure), with 95%
  intervals from resampling the volunteers;
- repetitions: sets counted exactly and the share of repetitions counted correctly.

It writes validation_report.md, validation_pairs.csv and three charts (PNG): Bland-Altman, the
app against the reference, and the difference by target position. Numbers only, no judgement:
the targets are the protocol's proposals, to be confirmed with the supervisor.
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from src import validation_data as vd

TARGET_MAE_DEG = 5.     # proposed: mean absolute error of 5 deg or less
TARGET_LOA_DEG = 10.    # proposed: 95% limits of agreement within +/-10 deg
TARGET_REPS_PCT = 95.   # proposed: at least 95% of repetitions counted correctly
BOOTSTRAP_DRAWS = 2000

# Chart colours (the reference data-viz palette): one series, ink for reference lines.
SERIES, INK, MUTED, GRID, BASELINE, BAND = "#257de0", "#191919", "#666666", "#e7e7e7", "#c2c2c2", "#efefef"


@dataclass(frozen=True)
class Pair:
    subject: str
    arm: str
    target: int
    trial: int
    reference: float
    app: float

    @property
    def diff(self):
        return self.app - self.reference


# ------------------------------------------------------------------ statistics
def icc_a1(*raters):
    """ICC(2,1): two-way random effects, absolute agreement, single measure (Shrout & Fleiss).

    Each argument is one rater's values (here the app and the goniometer), in the same order.
    """
    y = np.column_stack([np.asarray(values, float) for values in raters])
    n, k = y.shape
    if n < 2:
        return None
    grand = y.mean()
    ss_rows = k * ((y.mean(axis=1) - grand) ** 2).sum()
    ss_cols = n * ((y.mean(axis=0) - grand) ** 2).sum()
    ss_error = ((y - grand) ** 2).sum() - ss_rows - ss_cols
    ms_rows, ms_cols = ss_rows / (n - 1), ss_cols / (k - 1)
    ms_error = ss_error / ((n - 1) * (k - 1))
    denominator = ms_rows + (k - 1) * ms_error + k * (ms_cols - ms_error) / n
    return None if denominator <= 0 else float((ms_rows - ms_error) / denominator)


def sd_repeated(diffs_by_subject):
    """SD of the differences with several trials per volunteer (Bland & Altman 2007).

    One-way analysis of variance of the differences by volunteer: the between-volunteer part
    is corrected for the unequal numbers of trials, then added to the within-volunteer part.
    """
    groups = [np.asarray(d, float) for d in diffs_by_subject if len(d)]
    n = len(groups)
    total = sum(len(g) for g in groups)
    if n < 2 or total <= n:
        return None
    mean = np.concatenate(groups).mean()
    ms_between = sum(len(g) * (g.mean() - mean) ** 2 for g in groups) / (n - 1)
    ms_within = sum(((g - g.mean()) ** 2).sum() for g in groups) / (total - n)
    divisor = (total ** 2 - sum(len(g) ** 2 for g in groups)) / ((n - 1) * total)
    between = max(0., (ms_between - ms_within) / divisor)
    return float(math.sqrt(between + ms_within))


def agreement(pairs):
    """Error, bias, limits of agreement and ICC of a list of pairs (None when too few)."""
    if not pairs:
        return None
    diffs = np.array([p.diff for p in pairs])
    by_subject = defaultdict(list)
    for p in pairs:
        by_subject[p.subject].append(p.diff)
    sd_simple = float(diffs.std(ddof=1)) if len(diffs) > 1 else None
    sd_rm = sd_repeated(by_subject.values())
    sd = sd_rm if sd_rm is not None else sd_simple
    bias = float(diffs.mean())
    return {
        "n": len(pairs), "subjects": len(by_subject),
        "mae": float(np.abs(diffs).mean()), "bias": bias, "sd": sd, "sd_simple": sd_simple,
        "repeated": sd_rm is not None,
        "loa": None if sd is None else (bias - 1.96 * sd, bias + 1.96 * sd),
        "icc": icc_a1([p.app for p in pairs], [p.reference for p in pairs]),
    }


def bootstrap(pairs, statistic, draws=BOOTSTRAP_DRAWS, seed=7):
    """95% interval of `statistic(pairs)` by resampling volunteers (their trials go together)."""
    by_subject = defaultdict(list)
    for p in pairs:
        by_subject[p.subject].append(p)
    groups = list(by_subject.values())
    if len(groups) < 3:
        return None
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(draws):
        sample = [p for i in rng.integers(0, len(groups), len(groups)) for p in groups[i]]
        value = statistic(sample)
        if value is not None and math.isfinite(value):
            values.append(value)
    if len(values) < draws / 2:
        return None
    low, high = np.percentile(values, [2.5, 97.5])
    return float(low), float(high)


def rep_counting(rows):
    sets = [(int(r["app_reps"]), int(r["observer_reps"])) for r in rows]
    observed = sum(o for _, o in sets)
    errors = sum(abs(a - o) for a, o in sets)
    return {
        "sets": len(sets), "exact": sum(a == o for a, o in sets), "observed": observed,
        "counted": sum(a for a, _ in sets),
        "extra": sum(max(a - o, 0) for a, o in sets), "missed": sum(max(o - a, 0) for a, o in sets),
        "correct_pct": None if observed == 0 else max(0., 100. * (1 - errors / observed)),
    }


# ------------------------------------------------------------------ reading the study
def _int(value):
    number = vd._float(value)
    return None if number is None else int(round(number))


def collect(folder):
    """The pairs to compare, the sets of repetitions, and what had to be left out."""
    folder = Path(folder)
    rows = [r for r in vd.load_trials(folder) if r.get("status") == "ok"]
    pairs, sets, left_out = [], [], defaultdict(int)
    models = sorted({r.get("model", "") for r in rows if r.get("model")})
    for r in rows:
        if r.get("kind") == "reps":
            if _int(r.get("app_reps")) is None or _int(r.get("observer_reps")) is None:
                left_out["reps_without_count"] += 1
            else:
                sets.append(r)
            continue
        reference = vd._float(r.get("reference_deg"))
        if reference is None:
            left_out["holds_without_reading"] += 1
            continue
        app = vd._float(r.get("app_deg"))
        frames = folder / r["frames_file"] if r.get("frames_file") else None
        if frames is not None and frames.exists():  # the frame file is the source: same rule as the recorder
            app = vd.trial_app_angle(vd.read_frames(frames))[0]
        if app is None:
            left_out["holds_not_assessed"] += 1
            continue
        pairs.append(Pair(r["subject"], r["arm"], _int(r["target_deg"]), _int(r["trial"]) or 1, reference, app))
    return pairs, sets, dict(left_out), models


# ------------------------------------------------------------------ text
TEXT = {
    "fr": {
        "title": "Rapport de validation : angle et comptage de Mouvement",
        "generated": "Généré le {date} · dossier : `{folder}` · modèle(s) : {models}",
        "caveat": "Prototype éducatif. Ces résultats ne valent que pour les volontaires et les conditions de "
                  "cette étude ; les cibles sont celles proposées par le protocole, à confirmer avec l'encadrant.",
        "data": "Données", "volunteers": "Volontaires", "holds": "Maintiens comparés",
        "not_assessed": "Maintiens non évaluables (moins de la moitié des images avec un angle)",
        "no_reading": "Maintiens sans lecture du goniomètre", "sets": "Séries de répétitions",
        "glance": "Résultats en bref", "criterion": "Critère", "result": "Résultat", "target": "Cible",
        "status": "Statut", "met": "✔ atteinte", "not_met": "✘ non atteinte", "na": "non calculable",
        "mae": "Erreur absolue moyenne", "bias": "Biais moyen (application − goniomètre)",
        "loa": "Limites d'accord à 95 %", "icc": "ICC(2,1)", "sd": "Écart-type des écarts",
        "reps_ok": "Répétitions bien comptées", "within": "dans ±{v}°", "at_most": "≤ {v}°", "at_least": "≥ {v} %",
        "angles": "Accord des angles", "overall": "Ensemble", "by_position": "Par position",
        "by_arm": "Par bras", "position": "Position", "arm": "Bras", "n": "n",
        "right": "droit", "left": "gauche", "ci": "IC 95 %", "to": "à", "bias_short": "biais",
        "ci_title": "Intervalles de confiance à 95 % : ",
        "charts": "Graphiques", "counting": "Comptage des répétitions",
        "exact": "Séries exactes", "observed": "Répétitions (observateur)", "counted": "Comptées par l'application",
        "extra": "En trop", "missed": "Oubliées", "method": "Méthode",
        "method_lines": [
            "Angle de l'application pour un maintien : médiane des images qui ont un angle, après les "
            "0,5 premières secondes. Un maintien est non évaluable si moins de la moitié de ces images "
            "ont un angle (personne perdue, tournée, coude caché).",
            "Biais = moyenne des écarts (application − goniomètre). Limites d'accord = biais ± 1,96 × "
            "écart-type des écarts, avec la correction de Bland & Altman (2007) pour plusieurs essais par "
            "volontaire quand elle s'applique.",
            "ICC(2,1) : deux facteurs aléatoires, accord absolu, mesure unique (Shrout & Fleiss, 1979 ; "
            "McGraw & Wong, 1996), sur tous les essais comparés. Il n'est pas donné par position : "
            "l'étendue d'une seule position est trop étroite pour qu'il ait un sens.",
            "Intervalles de confiance à 95 % : rééchantillonnage des volontaires ({draws} tirages), car "
            "les essais d'un même volontaire ne sont pas indépendants (au moins 3 volontaires).",
            "Répétitions bien comptées = 1 − Σ|application − observateur| / Σ observateur.",
            "Fichier des paires comparées : `validation_pairs.csv` (une ligne par maintien).",
        ],
        "no_data": "Aucun maintien comparable ni série de répétitions dans ce dossier.",
        "ba_title": "Bland–Altman : écart entre l'application et le goniomètre",
        "ba_x": "Moyenne de l'application et du goniomètre (°)", "ba_y": "Application − goniomètre (°)",
        "ba_bias": "biais {v}°", "ba_high": "limite haute {v}°", "ba_low": "limite basse {v}°",
        "avr_title": "Angle de l'application et lecture du goniomètre",
        "avr_x": "Goniomètre (°)", "avr_y": "Application (°)", "avr_identity": "accord parfait",
        "err_title": "Écart par position cible (chaque point : un essai)",
        "err_x": "Position cible", "err_y": "Application − goniomètre (°)",
        "err_band": "zone visée pour les limites d'accord (±{v}°)", "err_mean": "moyenne",
        "chart_ba": "Bland–Altman : écart en fonction de la valeur mesurée",
        "chart_avr": "Application et goniomètre", "chart_err": "Écart par position",
    },
    "en": {
        "title": "Validation report: Mouvement's angle and repetition count",
        "generated": "Generated on {date} · folder: `{folder}` · model(s): {models}",
        "caveat": "Educational prototype. These results only hold for this study's volunteers and conditions; "
                  "the targets are the protocol's proposals, to be confirmed with the supervisor.",
        "data": "Data", "volunteers": "Volunteers", "holds": "Holds compared",
        "not_assessed": "Holds not assessed (fewer than half the frames with an angle)",
        "no_reading": "Holds without a goniometer reading", "sets": "Sets of repetitions",
        "glance": "Results at a glance", "criterion": "Criterion", "result": "Result", "target": "Target",
        "status": "Status", "met": "✔ met", "not_met": "✘ not met", "na": "not computable",
        "mae": "Mean absolute error", "bias": "Mean bias (app − goniometer)",
        "loa": "95% limits of agreement", "icc": "ICC(2,1)", "sd": "SD of differences",
        "reps_ok": "Repetitions counted correctly", "within": "within ±{v}°", "at_most": "≤ {v}°",
        "at_least": "≥ {v}%",
        "angles": "Angle agreement", "overall": "Overall", "by_position": "By position",
        "by_arm": "By arm", "position": "Position", "arm": "Arm", "n": "n",
        "right": "right", "left": "left", "ci": "95% CI", "to": "to", "bias_short": "bias",
        "ci_title": "95% confidence intervals: ",
        "charts": "Charts", "counting": "Repetition counting",
        "exact": "Exact sets", "observed": "Repetitions (observer)", "counted": "Counted by the app",
        "extra": "Extra", "missed": "Missed", "method": "Method",
        "method_lines": [
            "The app's angle for a hold: the median of the frames with an angle, after the first 0.5 s. "
            "A hold is not assessed when fewer than half of those frames have an angle (person lost, "
            "turned, elbow hidden).",
            "Bias = mean difference (app − goniometer). Limits of agreement = bias ± 1.96 × SD of the "
            "differences, with Bland & Altman's (2007) correction for several trials per volunteer "
            "when it applies.",
            "ICC(2,1): two-way random effects, absolute agreement, single measure (Shrout & Fleiss, 1979; "
            "McGraw & Wong, 1996), over all compared trials. It isn't given per position: one position's "
            "range is too narrow for it to mean anything.",
            "95% confidence intervals: resampling the volunteers ({draws} draws), because trials of the "
            "same volunteer aren't independent (3 volunteers or more).",
            "Repetitions counted correctly = 1 − Σ|app − observer| / Σ observer.",
            "Compared pairs: `validation_pairs.csv` (one row per hold).",
        ],
        "no_data": "No comparable hold or set of repetitions in this folder.",
        "ba_title": "Bland–Altman: difference between the app and the goniometer",
        "ba_x": "Mean of the app and the goniometer (°)", "ba_y": "App − goniometer (°)",
        "ba_bias": "bias {v}°", "ba_high": "upper limit {v}°", "ba_low": "lower limit {v}°",
        "avr_title": "The app's angle and the goniometer reading",
        "avr_x": "Goniometer (°)", "avr_y": "App (°)", "avr_identity": "perfect agreement",
        "err_title": "Difference by target position (each dot: one trial)",
        "err_x": "Target position", "err_y": "App − goniometer (°)",
        "err_band": "target zone for the limits of agreement (±{v}°)", "err_mean": "mean",
        "chart_ba": "Bland–Altman: difference against the measured value",
        "chart_avr": "App and goniometer", "chart_err": "Difference by position",
    },
}


def number(value, lang, digits=1, signed=False):
    if value is None:
        return "—"
    text = f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"
    text = text.replace("-", "−")
    return text.replace(".", ",") if lang == "fr" else text


# ------------------------------------------------------------------ charts
def _axes(figure_size=(8, 5)):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(figsize=figure_size, dpi=150)
    axes.set_facecolor("white")
    figure.patch.set_facecolor("white")
    for side in ("top", "right"):
        axes.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axes.spines[side].set_color(BASELINE)
    axes.tick_params(colors=MUTED, labelsize=9)
    axes.grid(True, color=GRID, linewidth=.8)
    axes.set_axisbelow(True)
    return plt, figure, axes


def _finish(plt, figure, axes, title, xlabel, ylabel, path):
    axes.set_title(title, color=INK, fontsize=12, loc="left", pad=12)
    axes.set_xlabel(xlabel, color=MUTED, fontsize=10)
    axes.set_ylabel(ylabel, color=MUTED, fontsize=10)
    figure.tight_layout()
    figure.savefig(path)
    plt.close(figure)


def _dots(axes, x, y):
    axes.scatter(x, y, s=34, color=SERIES, alpha=.85, edgecolors="white", linewidths=1.2, zorder=3)


def chart_bland_altman(pairs, stats, path, lang):
    t = TEXT[lang]
    plt, figure, axes = _axes()
    means = [(p.app + p.reference) / 2 for p in pairs]
    _dots(axes, means, [p.diff for p in pairs])
    axes.axhline(0, color=BASELINE, linewidth=1, zorder=1)
    span = (max(means) - min(means)) or 10
    left, data_right = min(means) - span * .04, max(means) + span * .04
    lines = [(stats["bias"], t["ba_bias"], 1.6)]
    if stats["loa"] is not None:
        lines += [(stats["loa"][1], t["ba_high"], 1.), (stats["loa"][0], t["ba_low"], 1.)]
    for value, label, width in lines:
        axes.axhline(value, color=INK if label == t["ba_bias"] else MUTED, linewidth=width, zorder=2)
        # the labels sit in an empty margin right of the dots, so no dot hides them
        axes.annotate(label.format(v=number(value, lang, signed=True)), (1, value), xycoords=("axes fraction", "data"),
                      xytext=(-2, 3), textcoords="offset points", ha="right", va="bottom", fontsize=9, color=INK)
    axes.set_xlim(left, data_right + span * .3)
    _finish(plt, figure, axes, t["ba_title"], t["ba_x"], t["ba_y"], path)


def chart_app_vs_reference(pairs, stats, path, lang):
    t = TEXT[lang]
    plt, figure, axes = _axes((6.5, 6))
    values = [p.app for p in pairs] + [p.reference for p in pairs]
    low, high = min(values) - 8, max(values) + 8
    axes.plot([low, high], [low, high], color=MUTED, linewidth=1, zorder=1)
    # label the identity line in the widest gap between the clusters of trials
    marks = sorted([low] + [p.reference for p in pairs] + [high])
    gap = max(zip(marks, marks[1:]), key=lambda pair: pair[1] - pair[0])
    middle = sum(gap) / 2
    axes.annotate(t["avr_identity"], (middle, middle), xytext=(4, -4), textcoords="offset points", ha="center",
                  va="top", fontsize=9, color=MUTED, rotation=45, rotation_mode="anchor")
    _dots(axes, [p.reference for p in pairs], [p.app for p in pairs])
    axes.set_xlim(low, high)
    axes.set_ylim(low, high)
    axes.set_aspect("equal")
    subtitle = f"{t['icc']} = {number(stats['icc'], lang, 3)} · {t['mae']} {number(stats['mae'], lang)}°"
    axes.text(0, 1.01, subtitle, transform=axes.transAxes, fontsize=9, color=MUTED, va="bottom")
    _finish(plt, figure, axes, t["avr_title"] + "\n", t["avr_x"], t["avr_y"], path)


def chart_error_by_angle(pairs, path, lang):
    t = TEXT[lang]
    plt, figure, axes = _axes()
    targets = sorted({p.target for p in pairs})
    axes.axhspan(-TARGET_LOA_DEG, TARGET_LOA_DEG, color=BAND, zorder=0)
    axes.axhline(0, color=BASELINE, linewidth=1, zorder=1)
    rng = np.random.default_rng(3)
    for i, target in enumerate(targets):
        diffs = [p.diff for p in pairs if p.target == target]
        jitter = rng.uniform(-.12, .12, len(diffs))
        _dots(axes, i + jitter, diffs)
        mean = float(np.mean(diffs))
        axes.plot([i - .25, i + .25], [mean, mean], color=INK, linewidth=2, solid_capstyle="round", zorder=4)
        axes.annotate(f"{number(mean, lang, signed=True)}°", (i + .27, mean), va="center", fontsize=9, color=INK)
    axes.set_xticks(range(len(targets)), [f"{target}°" for target in targets])
    axes.set_xlim(-.6, len(targets) - .4)
    top = max(TARGET_LOA_DEG, *(abs(p.diff) for p in pairs)) + 3
    axes.set_ylim(-top, top)
    axes.text(.01, .99, t["err_band"].format(v=int(TARGET_LOA_DEG)) + " · — " + t["err_mean"],
              transform=axes.transAxes, fontsize=9, color=MUTED, va="top")
    _finish(plt, figure, axes, t["err_title"], t["err_x"], t["err_y"], path)


# ------------------------------------------------------------------ the report
def _status(ok, t):
    return t["na"] if ok is None else t["met"] if ok else t["not_met"]


def _ci(interval, lang, digits=1, unit="°", signed=False, bare=False):
    if interval is None:
        return ""
    t = TEXT[lang]
    low, high = (number(v, lang, digits, signed) + unit for v in interval)
    return f"{low} {t['to']} {high}" if bare else f" ({t['ci']} {low} {t['to']} {high})"


def _agreement_row(label, stats, lang, with_icc=False):
    if stats is None:
        return None
    loa = "—" if stats["loa"] is None else (f"{number(stats['loa'][0], lang, signed=True)}° {TEXT[lang]['to']} "
                                            f"{number(stats['loa'][1], lang, signed=True)}°")
    cells = [label, str(stats["n"]), f"{number(stats['mae'], lang)}°", f"{number(stats['bias'], lang, signed=True)}°",
             f"{number(stats['sd'], lang)}°", loa]
    if with_icc:
        cells.append(number(stats["icc"], lang, 3))
    return "| " + " | ".join(cells) + " |"


def write_pairs(pairs, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:  # opens as-is in French Excel
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["subject", "arm", "target_deg", "trial", "reference_deg", "app_deg", "difference_deg"])
        for p in pairs:
            writer.writerow([p.subject, p.arm, p.target, p.trial, p.reference, p.app, round(p.diff, 2)])


def report(folder, out_dir=None, lang="fr", now=None):
    """Write the report and its charts; returns the numbers it is made of."""
    folder = Path(folder)
    out_dir = Path(out_dir) if out_dir else folder / "report"
    out_dir.mkdir(parents=True, exist_ok=True)
    t = TEXT[lang]
    pairs, sets, left_out, models = collect(folder)
    overall = agreement(pairs)
    counting = rep_counting(sets) if sets else None
    result = {"pairs": pairs, "overall": overall, "counting": counting, "left_out": left_out,
              "by_target": {}, "by_arm": {}, "ci": {}}
    date = (now or datetime.now()).strftime("%d/%m/%Y %H:%M" if lang == "fr" else "%Y-%m-%d %H:%M")
    lines = [f"# {t['title']}", "", t["generated"].format(date=date, folder=folder, models=", ".join(models) or "—"),
             "", f"> {t['caveat']}", ""]
    subjects = sorted({p.subject for p in pairs} | {r["subject"] for r in sets})
    lines += [f"## {t['data']}", "",
              f"- {t['volunteers']} : {len(subjects)}" + (f" ({', '.join(subjects)})" if subjects else ""),
              f"- {t['holds']} : {len(pairs)}",
              f"- {t['not_assessed']} : {left_out.get('holds_not_assessed', 0)}",
              f"- {t['no_reading']} : {left_out.get('holds_without_reading', 0)}",
              f"- {t['sets']} : {len(sets)}", ""]
    if lang == "en":
        lines = [line.replace(" : ", ": ") for line in lines]
    if overall is None and counting is None:
        lines += [t["no_data"], ""]
        (out_dir / "validation_report.md").write_text("\n".join(lines), encoding="utf-8")
        return result

    if overall is not None:
        for target in sorted({p.target for p in pairs}):
            result["by_target"][target] = agreement([p for p in pairs if p.target == target])
        for arm in ("right", "left"):
            subset = [p for p in pairs if p.arm == arm]
            if subset:
                result["by_arm"][arm] = agreement(subset)
        result["ci"] = {
            "mae": bootstrap(pairs, lambda s: agreement(s)["mae"]),
            "bias": bootstrap(pairs, lambda s: agreement(s)["bias"]),
            "icc": bootstrap(pairs, lambda s: agreement(s)["icc"]),
        }
        write_pairs(pairs, out_dir / "validation_pairs.csv")
        chart_bland_altman(pairs, overall, out_dir / "bland_altman.png", lang)
        chart_app_vs_reference(pairs, overall, out_dir / "app_vs_reference.png", lang)
        chart_error_by_angle(pairs, out_dir / "error_by_angle.png", lang)

    lines += [f"## {t['glance']}", "", f"| {t['criterion']} | {t['result']} | {t['target']} | {t['status']} |",
              "|---|---|---|---|"]
    if overall is not None:
        mae_ok = overall["mae"] <= TARGET_MAE_DEG
        loa = overall["loa"]
        loa_ok = None if loa is None else (loa[0] >= -TARGET_LOA_DEG and loa[1] <= TARGET_LOA_DEG)
        lines.append(f"| {t['mae']} | {number(overall['mae'], lang)}°{_ci(result['ci']['mae'], lang)} | "
                     f"{t['at_most'].format(v=int(TARGET_MAE_DEG))} | {_status(mae_ok, t)} |")
        shown = "—" if loa is None else (f"{number(loa[0], lang, signed=True)}° {t['to']} "
                                         f"{number(loa[1], lang, signed=True)}°")
        lines.append(f"| {t['loa']} | {shown} | {t['within'].format(v=int(TARGET_LOA_DEG))} | {_status(loa_ok, t)} |")
    if counting is not None:
        pct = counting["correct_pct"]
        reps_ok = None if pct is None else pct >= TARGET_REPS_PCT
        shown = "—" if pct is None else f"{number(pct, lang)} %" if lang == "fr" else f"{number(pct, lang)}%"
        lines.append(f"| {t['reps_ok']} | {shown} | {t['at_least'].format(v=int(TARGET_REPS_PCT))} | "
                     f"{_status(reps_ok, t)} |")
    lines.append("")

    if overall is not None:
        head = f"| | {t['n']} | {t['mae']} | {t['bias']} | {t['sd']} | {t['loa']} |"
        lines += [f"## {t['angles']}", "", f"### {t['overall']}", "", head + f" {t['icc']} |",
                  "|---|---|---|---|---|---|---|", _agreement_row(t["overall"], overall, lang, True), ""]
        extras = []
        if result["ci"].get("mae"):
            extras.append(f"{t['mae'].lower()} {_ci(result['ci']['mae'], lang, bare=True)}")
        if result["ci"].get("bias"):
            extras.append(f"{t['bias_short']} {_ci(result['ci']['bias'], lang, signed=True, bare=True)}")
        if result["ci"].get("icc"):
            extras.append(f"{t['icc']} {_ci(result['ci']['icc'], lang, 3, unit='', bare=True)}")
        if extras:
            separator = " ; " if lang == "fr" else "; "
            lines += [f"{t['ci_title']}{separator.join(extras)}.", ""]
        lines += [f"### {t['by_position']}", "", head.replace("| |", f"| {t['position']} |", 1), "|---|---|---|---|---|---|"]
        lines += [_agreement_row(f"{target}°", stats, lang) for target, stats in result["by_target"].items()]
        lines += ["", f"### {t['by_arm']}", "", head.replace("| |", f"| {t['arm']} |", 1), "|---|---|---|---|---|---|"]
        lines += [_agreement_row(t[arm], stats, lang) for arm, stats in result["by_arm"].items()]
        lines += ["", f"### {t['charts']}", "", f"![{t['chart_ba']}](bland_altman.png)", "",
                  f"![{t['chart_avr']}](app_vs_reference.png)", "", f"![{t['chart_err']}](error_by_angle.png)", ""]
    if counting is not None:
        pct = counting["correct_pct"]
        lines += [f"## {t['counting']}", "",
                  f"| {t['sets']} | {t['exact']} | {t['observed']} | {t['counted']} | {t['extra']} | {t['missed']} | "
                  f"{t['reps_ok']} |", "|---|---|---|---|---|---|---|",
                  f"| {counting['sets']} | {counting['exact']} | {counting['observed']} | {counting['counted']} | "
                  f"{counting['extra']} | {counting['missed']} | {number(pct, lang)} % |".replace(" % |", "% |" if lang == "en" else " % |"),
                  ""]
    draws = f"{BOOTSTRAP_DRAWS:,}".replace(",", "\u202f" if lang == "fr" else ",")
    lines += [f"## {t['method']}", ""] + [f"- {line.format(draws=draws)}" for line in t["method_lines"]] + [""]
    (out_dir / "validation_report.md").write_text("\n".join(lines), encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python evaluate_dataset.py angles",
                                     description="Rapport de l'étude de validation (docs/validation-protocol.md).")
    parser.add_argument("--data", type=Path, help="dossier de l'étude (par défaut %%APPDATA%%\\Mouvement\\validation)")
    parser.add_argument("--out", type=Path, help="dossier du rapport (par défaut <dossier de l'étude>/report)")
    parser.add_argument("--lang", choices=("fr", "en"), default="fr", help="langue du rapport (fr)")
    args = parser.parse_args(argv)
    folder = args.data or vd.validation_dir()
    if not (folder / "trials.csv").exists():
        print(f"Aucune mesure dans {folder} : enregistrez d'abord avec python record_clip.py angles.")
        return 1
    out_dir = args.out or folder / "report"
    result = report(folder, out_dir, args.lang)
    overall, counting = result["overall"], result["counting"]
    if overall is not None:
        loa = overall["loa"]
        print(f"{overall['n']} maintiens, {overall['subjects']} volontaire(s) : erreur absolue moyenne "
              f"{overall['mae']:.1f} deg, biais {overall['bias']:+.1f} deg"
              + ("" if loa is None else f", limites d'accord {loa[0]:+.1f} a {loa[1]:+.1f} deg"))
    if counting is not None and counting["correct_pct"] is not None:
        print(f"{counting['sets']} serie(s) : {counting['correct_pct']:.1f} % des repetitions bien comptees")
    print(f"Rapport : {out_dir / 'validation_report.md'}")
    return 0
