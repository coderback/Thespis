"""#24: caps on model calls and on new sessions, so judges clicking everything can't break the site or the bill."""

import pytest

from games.crypt_road import voice
from games.crypt_road.app import SessionLimiter, client_ip
from games.crypt_road.content import new_world
from tests.test_model_voice import FakeModel, play_demo
from thespis import expression
from tools.warm_cache import ROUTE

CAPPED = "model call cap reached"


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from games.crypt_road.app import app
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    with TestClient(app) as client:
        app.state.gateway = FakeModel()
        yield app, client


def play_route(client) -> tuple[dict, list[dict]]:
    """The Watch route over the API: the final state and every reply, in order."""
    session = client.post("/session", json={}).json()["session"]
    headers, replies = {"X-Session": session}, []
    for step in ROUTE:
        r = client.post("/act", json=step, headers=headers)
        assert r.status_code == 200, r.text
        replies += r.json()["replies"]
    return client.get("/state", headers=headers).json(), replies


def test_a_mind_stops_calling_once_its_budget_is_spent():
    from games.crypt_road import rules
    w = new_world(1)
    rules.act(w, "insult", "kael")
    packs = [voice.pack_for(w, npc, 'The player says to you: "Hello."') for npc in ("kael", "mags", "odo")]
    model = FakeModel()
    mind = expression.Mind(model, voice.VALIDATOR, budget=2)
    spoken = mind.react_many([(p, expression.Utterance(None, "Hm.", [], "fallback")) for p in packs])
    assert [u.source for u in spoken] == ["llm", "llm", "fallback"] and spoken[2].note == CAPPED
    assert mind.asked == 2 and len(model.calls) == 2


def test_hitting_the_session_cap_mid_route_keeps_the_game_playable(app_client):
    """#24's done-when: the route still wins, and the lines after the cap fall back, so the badge shows."""
    app, client = app_client
    app.state.session_cap = 3
    state, replies = play_route(client)
    assert (state["status"], state["ended_at"]) == ("won", 5)
    assert sum(r["source"] == "llm" for r in replies) <= 3
    assert [r["source"] for r in replies[-3:]] == ["fallback"] * 3  # the client's "offline brain" badge
    capped = [d for d in state["decisions_tail"] if d["reason"].endswith(CAPPED)]
    assert capped and len(app.state.gateway.calls) == 3
    assert app.state.store.calls_made() == 3


def test_cache_hits_dont_count_towards_the_cap(app_client):
    app, client = app_client
    play_route(client)  # warms the cache, under the default cap of 60
    app.state.session_cap = 1
    calls = len(app.state.gateway.calls)
    state, replies = play_route(client)
    assert {r["source"] for r in replies} == {"cache"} and len(app.state.gateway.calls) == calls
    assert not any(d["reason"].endswith(CAPPED) for d in state["decisions_tail"])


def test_the_global_cap_covers_every_session(app_client):
    app, client = app_client
    app.state.global_cap = 4
    play_route(client)
    assert app.state.store.calls_made() == 4 and len(app.state.gateway.calls) == 4
    state, replies = play_route(client)  # a new session, but nothing left in the global budget
    assert len(app.state.gateway.calls) == 4 and "llm" not in {r["source"] for r in replies}  # cache or fallback
    assert any(r["source"] == "fallback" for r in replies) and (state["status"], state["ended_at"]) == ("won", 5)


def test_new_sessions_are_limited_per_ip(app_client):
    app, client = app_client
    app.state.limiter = SessionLimiter(2)
    here = {"X-Real-IP": "203.0.113.7"}
    assert [client.post("/session", json={}, headers=here).status_code for _ in range(2)] == [200, 200]
    r = client.post("/session", json={}, headers=here)
    assert r.status_code == 429 and r.json()["error"] == "rate_limited" and "min" in r.json()["reason"]
    assert client.post("/session", json={}, headers={"X-Real-IP": "198.51.100.9"}).status_code == 200


def test_the_limit_is_per_hour():
    now = [0.0]
    limiter = SessionLimiter(2, clock=lambda: now[0])
    assert (limiter.wait("a"), limiter.wait("a")) == (0.0, 0.0)
    assert limiter.wait("a") == pytest.approx(3600)
    now[0] = 1800.0
    assert limiter.wait("a") == pytest.approx(1800)
    now[0] = 3600.0
    assert limiter.wait("a") == 0.0
    assert SessionLimiter(0).wait("a") == 0.0  # 0 turns it off


def test_the_client_ip_comes_from_railways_headers():
    class Req:
        def __init__(self, headers, host="100.64.0.2"):
            self.headers, self.client = headers, type("C", (), {"host": host})()

    assert client_ip(Req({"x-real-ip": "203.0.113.7", "x-forwarded-for": "198.51.100.1, 100.64.0.2"})) == "203.0.113.7"
    assert client_ip(Req({"x-forwarded-for": "198.51.100.1, 100.64.0.2"})) == "198.51.100.1"
    assert client_ip(Req({})) == "100.64.0.2"


def test_a_capped_route_plays_the_same_in_process():
    """The rules: with no budget left, every NPC falls back to the utility brain and the route still wins."""
    w, _ = play_demo(FakeModel(), budget=0)
    assert (w.status, w.ended_at) == ("won", 5) and "model_calls" not in w.counters
    assert all(d.source == "fallback" for d in w.decisions)
