"""How much does turning the body away from the camera change the app's angle? (Phase 7.4)

A synthetic body (src/synthetic_pose.py) holds a known abduction (30, 60, 90, 120 deg) and
turns from 0 to 45 deg around the vertical axis. For each rotation the tool measures the 2D
angle the app would compute and whether the app accepts it: from about 24 deg of rotation the
depth check (Phase 5.6, filtering.max_turn_depth_ratio) asks the patient to face the camera,
and from about 32 deg the width check does when there is no depth (filtering.min_facing_ratio).

    python tools/rotation_sensitivity.py            # charts in docs/img/, table in the console

The synthetic arm stays in the body's frontal plane: a real arm, often a little forward
(the scapular plane), differs, which is why the protocol measures real volunteers.
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import ExerciseConfig  # noqa: E402
from src.geometry import PoseLandmarkIndex as I  # noqa: E402
from src.geometry import calculate_abduction_angle, to_measurement_space  # noqa: E402
from src.session_processor import SessionProcessor  # noqa: E402
from src.synthetic_pose import body  # noqa: E402

ABDUCTIONS = (30, 60, 90, 120)
YAWS = tuple(range(0, 46))
WIDTH, HEIGHT = 640, 480
# Reference data-viz palette: categorical slots 1-4 in fixed order, inks and chart chrome.
SERIES = ("#257de0", "#f47230", "#00b894", "#f2a600")
INK, MUTED, GRID, BASELINE, BAND = "#191919", "#666666", "#e7e7e7", "#c2c2c2", "#efefef"

TEXT = {
    "fr": {"title": "Erreur de l'angle quand le patient tourne le buste",
           "x": "Rotation du buste par rapport à la caméra (°)", "y": "Angle de l'application − angle réel (°)",
           "series": "abduction {a}°", "refused": "l'application demande de se remettre de face",
           "depth": "avec la profondeur : à partir de {v}°", "width": "sans profondeur : à partir de {v}°",
           "note": "Trait plein : angle accepté par l'application ; pointillé : angle refusé (avec la profondeur)."},
    "en": {"title": "Angle error when the patient turns their trunk",
           "x": "Trunk rotation relative to the camera (°)", "y": "App's angle − true angle (°)",
           "series": "abduction {a}°", "refused": "the app asks the patient to face the camera",
           "depth": "with depth: from {v}°", "width": "without depth: from {v}°",
           "note": "Solid: angle accepted by the app; dotted: angle refused (with depth)."},
}


def calibrated(config):
    """A processor calibrated with the patient facing the camera, arms down."""
    processor = SessionProcessor(config)
    for i in range(40):
        pts, world = body(0)
        processor.process(pts, world, WIDTH, HEIGHT, i / 30)
    if not processor.calibrator.calibrated_data.is_calibrated:
        raise RuntimeError("calibration failed")
    return processor


def compute(abductions=ABDUCTIONS, yaws=YAWS):
    """Rows: abduction, rotation, the 2D angle, its error, accepted with depth, accepted without."""
    config = ExerciseConfig.from_yaml()
    # A short calibration and no smoothing: each frame gives its own angle at once.
    config = replace(config, calibration=replace(config.calibration, duration_sec=.6),
                     filtering=replace(config.filtering, ema_alpha=1.))
    processors = {True: calibrated(config), False: calibrated(config)}
    t = 2.
    rows = []
    for abduction in abductions:
        for yaw in yaws:
            pts, world = body(abduction, yaw=yaw)
            space = to_measurement_space(pts, WIDTH, HEIGHT)
            angle = calculate_abduction_angle(space[I.RIGHT_SHOULDER], space[I.RIGHT_HIP], space[I.RIGHT_ELBOW])
            accepted = {}
            for depth, processor in processors.items():
                t += 1 / 30
                frame = processor.process(pts, world if depth else None, WIDTH, HEIGHT, t)
                accepted[depth] = frame.metrics["abduction"] is not None
            rows.append({"abduction": abduction, "yaw": yaw, "angle": round(angle, 2),
                         "error": round(angle - abduction, 2), "accepted_depth": accepted[True],
                         "accepted_width": accepted[False]})
    return rows


def thresholds(rows):
    """First rotation refused with depth and without (None if never)."""
    def first(key):
        refused = [r["yaw"] for r in rows if not r[key]]
        return min(refused) if refused else None
    return first("accepted_depth"), first("accepted_width")


def worst_accepted(rows, key="accepted_depth"):
    """Largest error the app can still accept, by abduction."""
    out = {}
    for r in rows:
        if r[key]:
            out[r["abduction"]] = max(out.get(r["abduction"], 0.), abs(r["error"]))
    return out


def chart(rows, path, lang="fr"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t = TEXT[lang]
    depth, width = thresholds(rows)
    figure, axes = plt.subplots(figsize=(8, 5), dpi=150)
    for side in ("top", "right"):
        axes.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axes.spines[side].set_color(BASELINE)
    axes.tick_params(colors=MUTED, labelsize=9)
    axes.grid(True, color=GRID, linewidth=.8)
    axes.set_axisbelow(True)
    top = max(abs(r["error"]) for r in rows) + 2
    if depth is not None:
        axes.axvspan(depth, max(r["yaw"] for r in rows), color=BAND, zorder=0)
        axes.axvline(depth, color=MUTED, linewidth=1, zorder=1)
        axes.text(depth + .5, top - .3, t["refused"] + "\n" + t["depth"].format(v=depth), fontsize=8.5,
                  color=INK, va="top")
    if width is not None:
        axes.axvline(width, color=MUTED, linewidth=1, zorder=1)
        axes.text(width + .5, -top + .3, t["width"].format(v=width), fontsize=8.5, color=INK, va="bottom")
    axes.axhline(0, color=BASELINE, linewidth=1, zorder=1)
    for colour, abduction in zip(SERIES, sorted({r["abduction"] for r in rows})):
        series = [r for r in rows if r["abduction"] == abduction]
        accepted = [r for r in series if r["accepted_depth"]]
        refused = [r for r in series if not r["accepted_depth"]]
        if refused and accepted:
            refused = [accepted[-1]] + refused  # join the two parts
        axes.plot([r["yaw"] for r in accepted], [r["error"] for r in accepted], color=colour, linewidth=2,
                  solid_capstyle="round", label=t["series"].format(a=abduction), zorder=3)
        axes.plot([r["yaw"] for r in refused], [r["error"] for r in refused], color=colour, linewidth=2,
                  linestyle=(0, (1, 2)), dash_capstyle="round", zorder=3)
    axes.set_xlim(0, max(r["yaw"] for r in rows))
    axes.set_ylim(-top, top)
    axes.legend(loc="lower left", frameon=False, fontsize=9, labelcolor=INK)
    axes.set_title(t["title"], color=INK, fontsize=12, loc="left", pad=22)
    axes.text(0, 1.015, t["note"], transform=axes.transAxes, fontsize=8.5, color=MUTED, va="bottom")
    axes.set_xlabel(t["x"], color=MUTED, fontsize=10)
    axes.set_ylabel(t["y"], color=MUTED, fontsize=10)
    figure.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path)
    plt.close(figure)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "img", help="folder of the charts")
    parser.add_argument("--csv", action="store_true", help="also write rotation_sensitivity.csv")
    args = parser.parse_args(argv)
    rows = compute()
    for lang in ("fr", "en"):
        chart(rows, args.out / f"rotation_sensitivity_{lang}.png", lang)
    if args.csv:
        with open(args.out / "rotation_sensitivity.csv", "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    depth, width = thresholds(rows)
    print(f"Refused from {depth} deg of rotation with depth, {width} deg without.")
    print("rotation " + " ".join(f"{a:>8}" for a in ABDUCTIONS))
    for yaw in (0, 10, 15, 20, depth - 1, 25, 30, width - 1, 40, 45):
        errors = {r["abduction"]: r["error"] for r in rows if r["yaw"] == yaw}
        print(f"{yaw:>8} " + " ".join(f"{errors[a]:>+8.1f}" for a in ABDUCTIONS))
    worst = worst_accepted(rows)
    print("Largest error still accepted (with depth): "
          + ", ".join(f"{a} deg: {e:.1f}" for a, e in sorted(worst.items())))
    print(f"Charts: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
