"""The physio export: a PDF, a CSV with one row per movement, and copies of the session files."""
import csv
import datetime as dt

import pytest

from src.history_export import export_history, select
from src.user_profile import Plan
from tests.test_results_history import record

NOW = dt.datetime(2026, 11, 25, 17, 12)


def records():
    rows = [record(NOW.date() - dt.timedelta(days=d), best=80 + d, reps=3, pain=2) for d in (40, 10, 2, 0)]
    rows[-1]["pain_after"] = 5  # pain went up by 3: flagged in the PDF
    for i, r in enumerate(rows):
        r["_file"] = f"s{i}.json"
    return rows


def test_periods():
    assert len(select(records(), "7", NOW.date())) == 2
    assert len(select(records(), "30", NOW.date())) == 3
    assert len(select(records(), "all", NOW.date())) == 4


@pytest.mark.parametrize("language", ["fr", "en"])
def test_export_writes_pdf_csv_and_sessions(tmp_path, language):
    plan = Plan().__dict__
    folder = export_history(records(), "30", language, plan, "Amina", "right", root=tmp_path, now=NOW)
    assert folder.name == "bilan_2026-11-25_171200"
    pdf = (folder / "bilan.pdf").read_bytes()
    assert pdf.startswith(b"%PDF") and b"/Type /Page" in pdf and len(pdf) > 5000
    with open(folder / "mouvements.csv", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle, delimiter=";"))
    assert rows[0][0] == "date" and rows[0][4] == ("peak_angle_deg" if language == "en" else "angle_max_deg")
    assert len(rows) == 1 + 3 * 3
    assert sorted(p.name for p in (folder / "seances").iterdir()) == ["s1.json", "s2.json", "s3.json"]
    assert "_file" not in (folder / "seances" / "s1.json").read_text(encoding="utf-8")


def test_export_with_no_session_still_writes_a_pdf(tmp_path):
    folder = export_history([], "7", "fr", None, root=tmp_path, now=NOW)
    assert (folder / "bilan.pdf").read_bytes().startswith(b"%PDF")
