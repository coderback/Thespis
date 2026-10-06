"""#39: live persona editing. An NPC's next model line follows the edit; other sessions and the demo cache don't change."""

import pytest

from tests.test_model_voice import FakeModel
from tools.warm_cache import ROUTE

SWORN = "A sellsword who speaks only in rhyming couplets."


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from games.crypt_road.app import app
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    with TestClient(app) as client:
        app.state.gateway = FakeModel()
        yield app, client


def new_session(client) -> dict:
    return {"X-Session": client.post("/session", json={}).json()["session"]}


def kael(client, headers) -> dict:
    return next(n for n in client.get("/state", headers=headers).json()["npcs"] if n["id"] == "kael")


def test_an_edit_shows_in_the_state_and_survives_a_restart(app_client, tmp_path):
    from fastapi.testclient import TestClient

    from games.crypt_road.app import app
    _, client = app_client
    headers = new_session(client)
    assert kael(client, headers)["persona_edited"] is False
    r = client.post("/dev/persona", json={"npc": "kael", "persona": SWORN}, headers=headers).json()
    assert r == {"npc": "kael", "persona": SWORN, "default": False}
    assert (kael(client, headers)["persona"], kael(client, headers)["persona_edited"]) == (SWORN, True)
    with TestClient(app) as restarted:  # a new app lifespan on the same database
        assert kael(restarted, headers)["persona"] == SWORN
    r = client.post("/dev/persona", json={"npc": "kael", "persona": ""}, headers=headers).json()
    assert r["default"] is True and kael(client, headers)["persona_edited"] is False


def test_the_next_line_is_voiced_with_the_new_persona(app_client):
    app, client = app_client
    model = app.state.gateway
    prompts = []
    original = model.complete

    def capture(call_type, messages, schema=None):
        prompts.append(messages[0]["content"])
        return original(call_type, messages, schema)

    model.complete = capture
    headers = new_session(client)
    client.post("/dev/persona", json={"npc": "kael", "persona": SWORN}, headers=headers)
    client.post("/act", json={"verb": "insult", "target": "kael"}, headers=headers)
    assert any(SWORN in p for p in prompts)  # Kael's reaction was asked with the edited persona


def test_an_edit_leaves_the_demo_seeds_cache_alone(app_client):
    """#39's done-when: a fresh session still plays the demo route from the cache after someone edits a persona."""
    app, client = app_client
    model = app.state.gateway

    def play(headers):
        for step in ROUTE:
            assert client.post("/act", json=step, headers=headers).status_code == 200

    play(new_session(client))  # warm the cache with the default personas
    edited = new_session(client)
    client.post("/dev/persona", json={"npc": "kael", "persona": SWORN}, headers=edited)
    calls = len(model.calls)
    client.post("/act", json={"verb": "insult", "target": "kael"}, headers=edited)
    assert len(model.calls) > calls  # the edited persona is a new cache key, so Kael is asked afresh
    calls = len(model.calls)
    play(new_session(client))  # a fresh session, default personas
    assert len(model.calls) == calls


@pytest.mark.parametrize("body, reason", [
    ({"npc": "nobody", "persona": "Hi."}, "no one called"),
    ({"npc": "kael", "persona": "x" * 301}, "300 characters"),
])
def test_bad_edits_are_refused(app_client, body, reason):
    _, client = app_client
    r = client.post("/dev/persona", json=body, headers=new_session(client))
    assert r.status_code == 400 and reason in r.json()["reason"]
