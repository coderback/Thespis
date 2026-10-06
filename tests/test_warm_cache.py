"""#26: the cache warmer plays exactly what the client's autoplay plays, and a second run costs no model calls."""

import json
import re
from pathlib import Path

from tests.test_model_voice import FakeModel
from tools import warm_cache

AUTOPLAY = Path(__file__).resolve().parents[1] / "client" / "src" / "autoplay.js"


def autoplay_steps():
    """The `act: {...}` objects in autoplay.js, read as JSON (its keys are bare words)."""
    source = AUTOPLAY.read_text(encoding="utf-8")
    acts = []
    for match in re.finditer(r"act: \{", source):
        start = end = match.end() - 1
        depth = 0
        for end in range(start, len(source)):  # to the brace that closes this object, past any nested ones
            depth += {"{": 1, "}": -1}.get(source[end], 0)
            if depth == 0:
                break
        acts.append(json.loads(re.sub(r"(\w+):", r'"\1":', source[start:end + 1])))
    return acts


def test_the_warmer_plays_the_autoplay_route():
    assert "const DEMO_SEED = 1;" in AUTOPLAY.read_text(encoding="utf-8")
    assert autoplay_steps() == warm_cache.ROUTE


def test_a_warm_run_makes_no_model_calls(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from games.crypt_road.app import app
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin")  # the warmer reads the host's call log
    with TestClient(app, headers={"Authorization": "Bearer test-admin"}) as client:
        app.state.gateway = model = FakeModel()
        first = warm_cache.play(client)
        calls = len(model.calls)
        lines = sum(kind != "extract" for kind, _ in model.calls)  # the rest checked the lines with consequences
        second = warm_cache.play(client)
    assert first["outcome"] == second["outcome"] == "won@5"
    assert first["calls"] == lines > 0 and calls > lines  # a FakeModel keeps no call log, so lines are counted
    assert second["calls"] == 0 and len(model.calls) == calls
    assert second["said"] == first["said"] and set(second["sources"]) == {"cache"} and second["misses"] == 0


def test_an_empty_cache_under_replay_is_not_warm(tmp_path, monkeypatch):
    """Under REPLAY=1 a miss falls back without a call: free and repeatable, but not warm."""
    from fastapi.testclient import TestClient

    from games.crypt_road.app import app
    from tests.test_cache import Offline
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("REPLAY", "1")
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin")
    with TestClient(app, headers={"Authorization": "Bearer test-admin"}) as client:
        app.state.gateway = Offline()
        run = warm_cache.play(client)
    assert run["calls"] == 0 and run["misses"] > 0
