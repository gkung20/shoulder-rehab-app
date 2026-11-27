"""Phase 8.1: every pinned package and every folder of assets is in docs/licences.md."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LICENCES = (ROOT / "docs" / "licences.md").read_text(encoding="utf-8")


def test_every_pinned_package_has_a_licence_row():
    pinned = re.findall(r"^([A-Za-z0-9_.\-]+)==", (ROOT / "constraints-windows-py313.txt").read_text(), re.M)
    assert len(pinned) > 50
    missing = [name for name in pinned if f"[{name}]" not in LICENCES]
    assert not missing, missing
    for name in re.findall(r"^([A-Za-z0-9_.\-]+)", (ROOT / "requirements.txt").read_text(), re.M):
        assert f"**[{name}]" in LICENCES, name  # the direct ones are in bold


def test_every_asset_folder_in_the_repository_is_listed():
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):  # not a git checkout (a copied folder): use the disk
        tracked = "\n".join(str(p.relative_to(ROOT)).replace("\\", "/") for p in ROOT.rglob("*") if p.is_file())
    assets = {str(Path(path).parent).replace("\\", "/") for path in tracked.splitlines()
              if Path(path).suffix.lower() in (".png", ".jpg", ".glb", ".obj", ".ttf", ".otf", ".wav", ".mp3", ".js")}
    assets = {folder for folder in assets if not folder.startswith(("tests", ".git"))}
    assert {"assets/willy", "assets/silhouette"} <= assets
    missing = [folder for folder in assets if folder not in LICENCES]
    assert not missing, missing


def test_the_known_blockers_are_stated():
    for words in ("GPL-3.0-or-later", "CC BY-NC-SA 4.0", "AGPL-3.0", "Male-low.OBJ", "Segoe UI", "no licence"):
        assert words in LICENCES, words


def test_the_readme_links_to_the_licences():
    assert "(docs/licences.md)" in (ROOT / "README.md").read_text(encoding="utf-8")
