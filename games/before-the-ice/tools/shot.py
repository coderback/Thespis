"""Import the project and save what the game draws, to compare with the Blender renders.

    python games/before-the-ice/tools/shot.py --godot <Godot 4.7 console build> [--out shots/town.png]
    python games/before-the-ice/tools/shot.py --godot <...> --out shots/walk.png --walk=dest --at=0.55

Writes the 960x540 pixel picture and, beside it, the full window (-screen.png). Godot opens a window for a moment:
the picture needs a real renderer (Forward+), which --headless doesn't have.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--godot", default=os.environ.get("GODOT"), help="path to Godot 4.7's console build")
    ap.add_argument("--out", default=str(PROJECT / "shots" / "town.png"))
    a, extra = ap.parse_known_args()  # the rest goes to the game: --walk=<place> --at=<0..1>
    if not a.godot:
        ap.error("give --godot or set GODOT")
    out = Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    imp = subprocess.run([a.godot, "--headless", "--path", str(PROJECT), "--import"], capture_output=True, text=True,
                         timeout=600)
    if imp.returncode != 0:
        print(imp.stdout[-2000:], imp.stderr[-2000:])
        return imp.returncode
    run = subprocess.run([a.godot, "--path", str(PROJECT), "--quit-after", "2000", "--", f"--shot={out}", *extra],
                         capture_output=True, text=True, timeout=300)
    errors = [ln for ln in (run.stdout + run.stderr).splitlines() if "ERROR" in ln or "SCRIPT ERROR" in ln]
    for ln in errors[:30]:
        print(ln)
    if not out.exists():
        print("no picture written")
        return 1
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
