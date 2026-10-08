"""The Godot spike's round trip (sdk/godot/spike), when Godot is here to run it: set GODOT to Godot 4's console build.

CI has no Godot, so there it's skipped; run it locally before changing /v1.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

RUN = Path(__file__).resolve().parents[1] / "sdk" / "godot" / "spike" / "test" / "run.py"


@pytest.mark.skipif(not os.environ.get("GODOT"), reason="set GODOT to Godot 4's console build to run the spike")
def test_the_tavern_plays_through_v1_from_godot():
    r = subprocess.run([sys.executable, str(RUN)], capture_output=True, text=True, timeout=240)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
