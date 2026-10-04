"""The HTTP API in docs/api.md: every endpoint, its errors, and a restart mid-route."""

import pytest
from fastapi.testclient import TestClient

from games.crypt_road import app as app_module


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "thespis.sqlite"
    monkeypatch.setenv("DB_PATH", str(path))
    return path


@pytest.fixture
def client(db):
    with TestClient(app_module.app) as c:
        yield c


def start(client, **body):
    r = client.post("/session", json=body)
    assert r.status_code == 200
    data = r.json()
    return {"X-Session": data["session"]}, data["state"]


def test_new_session_uses_the_demo_seed(client):
    headers, state = start(client)
    assert (state["seed"], state["phase"], state["status"], state["player"]) == \
        (1, 0, "playing", {"loc": "tavern", "coins": 10})
    assert client.get("/state", headers=headers).json() == state
    _, other = start(client, seed=7)
    assert other["seed"] == 7


def test_act_returns_events_tick_and_state(client):
    headers, _ = start(client)
    free = client.post("/act", json={"verb": "insult", "target": "kael"}, headers=headers).json()
    assert free["tick"] is None and [e["verb"] for e in free["events"]] == ["insult"]
    client.post("/act", json={"verb": "challenge", "target": "kael"}, headers=headers)
    ends = client.post("/act", json={"verb": "humiliate", "target": "kael"}, headers=headers).json()
    assert ends["state"]["phase"] == 1 and ends["state"]["player"]["coins"] == 40
    assert {m["who"] for m in ends["tick"]["moves"]} == {"kael", "odo"}
    assert [d["chosen"] for d in ends["tick"]["decisions"]] == ["go_to"]


def test_errors(client):
    headers, _ = start(client)
    missing = client.get("/state")
    assert missing.status_code == 400 and missing.json()["error"] == "bad_request"
    unknown = client.get("/state", headers={"X-Session": "nope"})
    assert unknown.status_code == 404 and unknown.json()["error"] == "unknown_session"
    refused = client.post("/act", json={"verb": "bribe", "target": "brenna"}, headers=headers)
    assert refused.status_code == 409 and refused.json()["error"] == "not_allowed" and refused.json()["reason"]
    malformed = client.post("/act", json={"target": "kael"}, headers=headers)
    assert malformed.status_code == 400 and "verb" in malformed.json()["reason"]
    too_long = client.post("/act", json={"verb": "talk", "target": "mags", "text": "x" * 201}, headers=headers)
    assert too_long.status_code == 409


def test_reset_reload_and_brain(client):
    headers, _ = start(client, seed=3)
    client.post("/act", json={"verb": "insult", "target": "kael"}, headers=headers)
    assert client.post("/reload", headers=headers).json()["state"]["npcs"][0]["drives"]["grudge"] == 1
    reset = client.post("/reset", headers=headers).json()["state"]
    assert (reset["seed"], reset["npcs"][0]["drives"]["grudge"], reset["ledger_tail"]) == (3, 0, [])
    assert client.post("/dev/brain", json={"mode": "fallback"}, headers=headers).json() == {"mode": "fallback"}
    assert client.get("/state", headers=headers).json()["brain"] == "fallback"
    assert client.post("/dev/brain", json={"mode": "off"}, headers=headers).status_code == 400


def test_digest(client):
    headers, _ = start(client)
    for body in ({"verb": "insult", "target": "kael"}, {"verb": "challenge", "target": "kael"},
                 {"verb": "humiliate", "target": "kael"}, {"verb": "move"}, {"verb": "move"}):
        client.post("/act", json=body, headers=headers)
    digest = client.get("/digest?since=2", headers=headers).json()
    assert "Kael told Brenna that you robbed him." in digest["text"]
    assert digest["cites"] and digest["epilogue"] is None and set(digest) == {"text", "hook", "cites", "epilogue", "source", "epilogue_source"}


def test_restart_mid_route_resumes_identically(db):
    """The demo's restart beat: kill the server after the offscreen accusation, start it again, nothing lost."""
    with TestClient(app_module.app) as client:
        headers, _ = start(client)
        for body in ({"verb": "insult", "target": "kael"}, {"verb": "challenge", "target": "kael"},
                     {"verb": "humiliate", "target": "kael"}, {"verb": "move"}, {"verb": "move"}):
            client.post("/act", json=body, headers=headers)
        before = client.get("/state", headers=headers).json()
        allowed_before = client.get("/allowed", headers=headers).json()
    with TestClient(app_module.app) as restarted:  # a new app lifespan on the same database
        assert restarted.get("/state", headers=headers).json() == before
        assert restarted.get("/allowed", headers=headers).json() == allowed_before
        assert before["phase"] == 3 and any(d["chosen"] == "accuse:player" for d in before["decisions_tail"])
