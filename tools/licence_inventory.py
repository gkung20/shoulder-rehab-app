"""Licences of the Python packages Mouvement uses (Phase 8.1), for docs/licences.md.

    python tools/licence_inventory.py            # installed packages (offline, like `pip show`)
    python tools/licence_inventory.py --pypi     # the versions pinned in constraints-windows-py313.txt,
                                                 # from PyPI's metadata (needs the internet)

Prints one Markdown table row per package: name, version, licence, project page. The licence
comes from the package's own metadata (License-Expression, then the "License ::" classifiers,
then the License field); check the project's LICENSE file when it says "see project".
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSTRAINTS = ROOT / "constraints-windows-py313.txt"


def pinned(path=CONSTRAINTS):
    pins = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s#]+)", line.strip())
        if match:
            pins.append((match.group(1), match.group(2)))
    return pins


def licence_of(expression, classifiers, text):
    """One short licence name from the three places packages put it."""
    if expression:
        return expression.strip()
    names = [c.split("::")[-1].strip() for c in classifiers or () if c.startswith("License ::")]
    names = [n for n in names if n not in ("OSI Approved", "")]
    if names:
        return " / ".join(dict.fromkeys(names))
    first = (text or "").strip().splitlines()[0].strip() if (text or "").strip() else ""
    if not first or len(first) > 60:
        return "see project" if not first else first[:57] + "..."
    return first


def from_pypi(name, version):
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as response:
        info = json.load(response)["info"]
    urls = info.get("project_urls") or {}
    page = (urls.get("Source") or urls.get("Source Code") or urls.get("Homepage") or urls.get("homepage")
            or info.get("home_page") or info.get("project_url") or "")
    return licence_of(info.get("license_expression"), info.get("classifiers"), info.get("license")), page


def installed(name):
    meta = metadata.metadata(name)
    page = ""
    for entry in meta.get_all("Project-URL") or ():
        label, _, url = entry.partition(",")
        if label.strip().lower() in ("source", "source code", "homepage", "repository"):
            page = url.strip()
            break
    page = page or meta.get("Home-page") or ""
    return metadata.version(name), licence_of(meta.get("License-Expression"), meta.get_all("Classifier"),
                                              meta.get("License")), page


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--pypi", action="store_true", help="pinned versions, from PyPI")
    args = parser.parse_args(argv)
    print("| Package | Version | Licence | Project |")
    print("|---|---|---|---|")
    for name, version in pinned():
        try:
            if args.pypi:
                licence, page = from_pypi(name, version)
            else:
                version, licence, page = installed(name)
        except Exception as error:  # not installed here (Windows-only), or offline
            licence, page = f"? ({type(error).__name__})", ""
        print(f"| {name} | {version} | {licence} | {page} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
