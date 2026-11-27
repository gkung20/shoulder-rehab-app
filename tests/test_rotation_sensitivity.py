"""Phase 7.4: the rotation chart shows why the app stops measuring a turned body."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rotation_sensitivity", ROOT / "tools" / "rotation_sensitivity.py")
rotation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rotation)


def test_turning_the_body_changes_the_angle_until_the_app_refuses_it(tmp_path):
    rows = rotation.compute(abductions=(30, 60, 90, 120), yaws=range(0, 46, 1))
    by = {(r["abduction"], r["yaw"]): r for r in rows}
    assert all(abs(by[(a, 0)]["error"]) < .05 for a in (30, 60, 90, 120))  # facing: exact
    assert all(abs(by[(90, y)]["error"]) < .05 for y in range(46))  # arm level with the shoulder: unchanged
    errors = [by[(60, y)]["error"] for y in range(46)]
    assert all(b <= a for a, b in zip(errors, errors[1:])) and errors[-1] < -8  # grows with the turn
    assert by[(120, 45)]["error"] > 8  # above the shoulder, the other way
    depth, width = rotation.thresholds(rows)
    assert 22 <= depth <= 25 and 30 <= width <= 33  # the Phase 5.6 thresholds
    assert max(rotation.worst_accepted(rows).values()) < 2.5  # what the app accepts stays within 2.5 deg
    rotation.chart(rows, tmp_path / "chart.png", "en")
    assert (tmp_path / "chart.png").stat().st_size > 20_000


def test_the_charts_in_the_protocol_exist():
    for lang in ("fr", "en"):
        assert (ROOT / "docs" / "img" / f"rotation_sensitivity_{lang}.png").exists()
