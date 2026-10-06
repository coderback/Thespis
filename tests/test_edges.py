"""The server's edges: the admin token, API docs, CORS, request body size and security headers."""

import pytest
from fastapi.testclient import TestClient

from games import hosting
from games.crypt_road import app as app_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    with TestClient(app_module.app) as c:
        yield c


def test_the_call_log_does_not_exist_without_an_admin_token(client):
    assert client.get("/dev/calls").status_code == 404
    assert client.get("/dev/calls", headers={"Authorization": "Bearer guess"}).status_code == 404


def test_the_call_log_answers_only_to_the_admin_token(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    with TestClient(app_module.app) as c:
        assert c.get("/dev/calls").status_code == 401
        assert c.get("/dev/calls", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert c.get("/dev/calls", headers={"Authorization": "Basic s3cret"}).status_code == 401
        r = c.get("/dev/calls", headers={"Authorization": "Bearer s3cret"})
        assert r.status_code == 200 and r.json() == {"total": 0, "calls": []}


def test_the_session_endpoints_stay_open_to_their_own_player(client):
    """The dev panel and the Minds tab use these; each touches only the caller's session."""
    headers = {"X-Session": client.post("/session", json={}).json()["session"]}
    assert client.post("/dev/brain", json={"mode": "fallback"}, headers=headers).status_code == 200
    assert client.post("/reload", headers=headers).status_code == 200
    assert client.post("/dev/persona", json={"npc": "kael", "persona": "Gruff."}, headers=headers).status_code == 200


def test_api_docs_are_off(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path


def test_api_docs_only_when_asked_for(monkeypatch):
    assert hosting.docs_settings() == {"docs_url": None, "redoc_url": None, "openapi_url": None}
    monkeypatch.setenv("API_DOCS", "1")
    assert hosting.docs_settings() == {}


def test_no_other_origin_may_read_the_api(client):
    r = client.options("/act", headers={"Origin": "https://elsewhere.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers
    r = client.get("/health", headers={"Origin": "https://elsewhere.example"})
    assert "access-control-allow-origin" not in r.headers


def test_cors_origins_come_from_the_environment(monkeypatch):
    assert hosting.cors_origins() == []
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example,")
    assert hosting.cors_origins() == ["https://a.example", "https://b.example"]


def test_every_answer_carries_the_security_headers(client):
    for r in (client.get("/health"), client.get("/state"), client.get("/dev/calls")):
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_an_oversized_body_is_refused(client):
    r = client.post("/act", content=b"{" + b" " * hosting.MAX_BODY + b"}", headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["error"] == "too_large"


def test_an_oversized_body_without_a_length_is_refused(client):
    def chunks():
        for _ in range(5):
            yield b" " * (hosting.MAX_BODY // 4)
    r = client.post("/act", content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_a_small_body_without_a_length_still_arrives(client):
    session = client.post("/session", json={}).json()["session"]

    def chunks():
        yield b'{"verb": "insult", '
        yield b'"target": "kael"}'
    r = client.post("/act", content=chunks(), headers={"Content-Type": "application/json", "X-Session": session})
    assert r.status_code == 200 and r.json()["events"][0]["verb"] == "insult"


def test_session_locks_are_freed_once_no_request_holds_them(client):
    from games.manor import api as manor_api

    headers = {"X-Session": client.post("/session", json={}).json()["session"]}
    client.post("/act", json={"verb": "insult", "target": "kael"}, headers=headers)
    client.post("/reset", headers=headers)
    manor = {"X-Session": client.post("/manor/session").json()["session"]}
    client.post("/manor/act", json={"verb": "ask", "target": "vane", "topic": "ring"}, headers=manor)
    assert len(app_module.LOCKS) == 0 and len(manor_api.LOCKS) == 0


def test_session_locks_still_serialise_a_session():
    import threading
    import time

    locks, order = hosting.SessionLocks(), []
    inside = threading.Event()

    def first():
        with locks.hold("s"):
            inside.set()
            time.sleep(0.05)
            order.append("first done")

    def second():
        inside.wait()
        with locks.hold("s"):
            order.append("second in")

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert order == ["first done", "second in"] and len(locks) == 0
    with locks.hold("a"), locks.hold("b"):  # different sessions never wait on each other
        assert len(locks) == 2
