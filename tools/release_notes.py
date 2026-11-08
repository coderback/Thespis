"""A release's notes, from its section of CHANGELOG.md: what the release workflow publishes on GitHub.

    python tools/release_notes.py 0.3.1         # prints the section; fails if there is none
    python tools/release_notes.py --check v0.3.1  # also fails unless thespis.__version__ is that number
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def notes(version: str, changelog: str) -> str | None:
    """The body of the `## <version>` section (a date may follow the number), or None."""
    m = re.search(rf"^## {re.escape(version)}(?: \(.*\))?\n(.*?)(?=^## |\Z)", changelog, re.M | re.S)
    return m.group(1).strip() if m else None


def version() -> str:
    m = re.search(r'^__version__ = "([^"]+)"', (ROOT / "thespis" / "__init__.py").read_text(encoding="utf-8"), re.M)
    assert m, "thespis/__init__.py has no __version__"
    return m.group(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("version", help="the release's number, with or without a leading v")
    ap.add_argument("--check", action="store_true", help="fail unless the package's own version is this one")
    o = ap.parse_args()
    want = o.version.removeprefix("v")
    if o.check and version() != want:
        print(f"thespis.__version__ is {version()}, not {want}", file=sys.stderr)
        return 1
    body = notes(want, (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    if not body:
        print(f"CHANGELOG.md has no section for {want}", file=sys.stderr)
        return 1
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
