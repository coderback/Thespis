"""The Unity package (sdk/unity): its generated layer matches the /v1 contract, its example plays the tavern game, and,
with the tools here to run them, the example plays against a sidecar and a server: under .NET (the .NET SDK on PATH,
or THESPIS_DOTNET=1) and in the Unity editor (UNITY set to Unity.exe).
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UNITY = ROOT / "sdk" / "unity"
RUN = UNITY / "test" / "run.py"


def test_the_generated_api_matches_the_contract():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "sdk_gen.py"), "unity", "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_every_route_in_the_contract_is_in_the_generated_table():
    spec = json.loads((ROOT / "docs" / "openapi-v1.json").read_text(encoding="utf-8"))
    api = (UNITY / "com.thespis.client" / "Runtime" / "Core" / "Api.g.cs").read_text(encoding="utf-8")
    routes = set(re.findall(r'new Route\("(GET|POST|PUT|DELETE)", "([^"]+)"', api))
    assert routes == {(m.upper(), p) for p, ops in spec["paths"].items() for m in ops}


def test_the_core_touches_no_unity_engine():
    # It builds under plain .NET too (sdk/unity/dotnet), which is how CI tests it.
    for cs in (UNITY / "com.thespis.client" / "Runtime" / "Core").glob("*.cs"):
        assert not re.search(r"^using UnityEngine|UnityEngine\.\w", cs.read_text(encoding="utf-8"), re.M), cs.name


def test_the_example_plays_the_tavern_game():
    # A copy, because a Unity build can only ship what's inside its project.
    example = (UNITY / "Lantern" / "Assets" / "Lantern" / "tavern.toml").read_bytes().replace(b"\r\n", b"\n")
    assert example == (ROOT / "examples" / "tavern" / "game.toml").read_bytes().replace(b"\r\n", b"\n")


@pytest.mark.skipif(not (shutil.which("dotnet") or os.environ.get("THESPIS_DOTNET")),
                    reason="the .NET SDK isn't on PATH")
def test_the_example_plays_under_dotnet():
    r = subprocess.run([sys.executable, str(RUN), "--runner", "dotnet"], capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]


@pytest.mark.skipif(not os.environ.get("UNITY"), reason="set UNITY to the Unity editor to play the scene")
def test_the_example_scene_plays_in_unity():
    r = subprocess.run([sys.executable, str(RUN), "--runner", "unity"], capture_output=True, text=True, timeout=3600)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
