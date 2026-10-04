"""#19: the Dungeon Master. Code-sifted story hooks, and a model-told digest with the code-built one as the fallback."""

import pytest

from games.crypt_road import rules, views, voice
from games.crypt_road.content import new_world
from tests.test_model_voice import FakeModel
from thespis.expression import StatePack
from tools.warm_cache import ROUTE


def act(w, step):
    rules.act(w, step["verb"], step.get("target"), step.get("claim"), step.get("amount"), step.get("text"))


def test_hooks_follow_the_demo_story():
    """#19's done-when: after tick 2 the digest names Kael's accusation and Odo's gossip; after the win the epilogue
    reports the exposed lie. The hooks name each thread as it happens."""
    w = new_world(1)
    for step in ROUTE[:6]:  # to the guard post: tick 2 has run
        act(w, step)
    d = views.digest_view(w, 2)
    assert "Kael told Brenna that you robbed him." in d["text"] and "Odo told Brenna that you beat Kael." in d["text"]
    assert d["hook"] == "Revenge is brewing: Kael took his grudge to the Captain."
    assert (d["source"], d["epilogue"], d["epilogue_source"]) == ("fallback", None, None)

    for step in ROUTE[6:10]:  # bribe, bribe, the lie, move: tick 3
        act(w, step)
    assert views.digest_view(w, 3)["hook"] == ("A lie is loose: you told Brenna that Kael robbed Odo, and it never "
                                               "happened.")
    act(w, ROUTE[10])  # to the crypt
    assert views.digest_view(w, 4)["hook"] is None  # a window with no thread in it
    act(w, ROUTE[11])  # take the relic; the epilogue plays out
    end = views.digest_view(w, w.ended_at)
    assert "Odo told Brenna that Kael never robbed him." in end["epilogue"]
    assert end["hook"] == "The lie is out: Odo told Brenna that Kael never robbed him."


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from games.crypt_road.app import app
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    with TestClient(app) as client:
        app.state.gateway = FakeModel()
        yield app, client


def to_guard_post(client) -> dict:
    headers = {"X-Session": client.post("/session", json={}).json()["session"]}
    for step in ROUTE[:6]:
        assert client.post("/act", json=step, headers=headers).status_code == 200
    return headers


def test_the_model_tells_the_digest_and_the_cache_retells_it(app_client):
    app, client = app_client
    headers = to_guard_post(client)
    calls = len(app.state.gateway.calls)
    d = client.get("/digest", params={"since": 2}, headers=headers).json()
    assert (d["source"], d["text"]) == ("llm", "So be it.")  # FakeModel's telling
    window = {e["id"] for e in client.get("/state", headers=headers).json()["ledger_tail"] if e["phase"] >= 2}
    assert d["cites"] and set(d["cites"]) <= window
    assert d["hook"] == "Revenge is brewing: Kael took his grudge to the Captain."  # code-sifted, model or not
    narrations = [c for c, _ in app.state.gateway.calls[calls:] if c == "narrate"]
    assert len(narrations) == 1
    assert app.state.store.load(headers["X-Session"]).counters["model_calls"] >= 1  # counted against the caps

    again = client.get("/digest", params={"since": 2}, headers=to_guard_post(client)).json()
    assert (again["source"], again["text"]) == ("cache", "So be it.")


def test_a_bad_telling_falls_back_to_the_code_built_digest(app_client):
    app, client = app_client

    def bad_narrator(call_type, pack):
        if call_type == "narrate":
            return {"line": "Kael vanished into the night.", "cites": ["e9999"]}
        return FakeModel.good(call_type, pack)

    app.state.gateway = FakeModel(bad_narrator)
    d = client.get("/digest", params={"since": 2}, headers=to_guard_post(client)).json()
    assert d["source"] == "fallback" and "Kael told Brenna that you robbed him." in d["text"]


def test_no_model_call_with_the_brain_off_or_no_budget(app_client):
    app, client = app_client
    headers = to_guard_post(client)
    client.post("/dev/brain", json={"mode": "fallback"}, headers=headers)
    calls = len(app.state.gateway.calls)
    assert client.get("/digest", params={"since": 2}, headers=headers).json()["source"] == "fallback"
    client.post("/dev/brain", json={"mode": "model"}, headers=headers)
    app.state.global_cap = app.state.store.calls_made()  # nothing left in the global budget
    assert client.get("/digest", params={"since": 2}, headers=headers).json()["source"] == "fallback"
    assert len(app.state.gateway.calls) == calls


def test_a_telling_may_run_longer_than_a_spoken_line():
    w = new_world(1)
    act(w, ROUTE[0])
    pack: StatePack = voice.pack_for(w, "mags", 'The player says to you: "Hello."')
    long = {"line": "A" * 300, "cites": [pack.events[-1]["id"]]}
    assert voice.VALIDATOR.problem(long, pack, "narrate") is None
    assert "over 160" in voice.VALIDATOR.problem(long, pack, "react")
