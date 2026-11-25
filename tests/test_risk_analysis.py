"""Every control in the risk analysis points to a test or a document that exists."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Controls of later sprint phases; each name leaves this set when its phase lands.
PENDING = {"tests/test_face_check.py", "tests/test_person_lock.py", "tests/test_crash_screen.py",
           "tests/test_camera_reconnect.py", "docs/validation-protocol.md"}


def test_risk_analysis_references_exist():
    text = (ROOT / "docs" / "risk-analysis.md").read_text(encoding="utf-8")
    references = set(re.findall(r"`((?:tests|docs)/[\w./-]+\.(?:py|md))`", text))
    assert len(references) >= 10
    missing = {ref for ref in references if not (ROOT / ref).exists()}
    assert missing <= PENDING, missing
    assert not {ref for ref in PENDING if (ROOT / ref).exists()}, "remove landed items from PENDING"
