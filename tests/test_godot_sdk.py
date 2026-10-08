"""The Godot addon (sdk/godot): its generated layer matches the /v1 contract, its example plays the tavern game, and,
when Godot is here to run it (GODOT set to Godot 4's console build), the example plays against a sidecar and a server.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "sdk" / "godot"


def test_the_generated_api_matches_the_contract():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "sdk_gen.py"), "godot", "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_every_route_in_the_contract_is_in_the_generated_table():
    import json
    import re
    spec = json.loads((ROOT / "docs" / "openapi-v1.json").read_text(encoding="utf-8"))
    api = (GODOT / "addons" / "thespis" / "api.gd").read_text(encoding="utf-8")
    routes = set(re.findall(r'^\t"(\w+)": \["(?:GET|POST|PUT|DELETE)", "([^"]+)"', api, re.M))
    paths = {(m, p) for p, ops in spec["paths"].items() for m in ops}
    assert {p for _, p in routes} == {p for _, p in paths}


def test_the_example_plays_the_tavern_game():
    # A copy, because an exported Godot game can only read files inside its own project.
    example = (GODOT / "example" / "tavern.toml").read_bytes().replace(b"\r\n", b"\n")
    assert example == (ROOT / "examples" / "tavern" / "game.toml").read_bytes().replace(b"\r\n", b"\n")


@pytest.mark.skipif(not os.environ.get("GODOT"), reason="set GODOT to Godot 4's console build to play the example")
def test_the_example_plays_against_a_sidecar_and_a_server():
    r = subprocess.run([sys.executable, str(GODOT / "test" / "run.py")], capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
