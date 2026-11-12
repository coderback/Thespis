"""What every /v1 request passes before a route (thespis.server._Guarded): a body over its limit is refused before it
is read whole, and a sidecar answers only requests addressed to this machine, so a web page an attacker points at
127.0.0.1 (DNS rebinding) can't play with a game's sidecar from the player's browser."""

import json

import pytest
from fastapi.testclient import TestClient

from tests.test_host import TAVERN, opened, project, server
from thespis.host import SIDECAR, Host
from thespis.server import MAX_BODY_BYTES, _hostname, create_app
from thespis.storage import SqliteStorage


def sidecar(tmp_path, base_url: str, token: str | None = None) -> TestClient:
    host = Host(SqliteStorage(tmp_path / "s.sqlite"), {"tavern": TAVERN}, mode=SIDECAR, token=token)
    return TestClient(create_app(host=host), base_url=base_url)


@pytest.mark.parametrize("url", ["http://localhost", "http://127.0.0.1:8123", "http://[::1]:8123",
                                 "http://game.localhost:9000"])
def test_a_sidecar_answers_this_machine(tmp_path, url):
    assert sidecar(tmp_path, url).get("/v1/games").status_code == 200


@pytest.mark.parametrize("url", ["http://evil.example", "http://evil.example:8123", "http://192.168.1.4:8123",
                                 "http://localhost.evil.example"])
def test_a_sidecar_refuses_a_request_addressed_elsewhere_even_with_its_token(tmp_path, url):
    r = sidecar(tmp_path, url, token="t0k").get("/v1/games", headers={"Authorization": "Bearer t0k"})
    assert (r.status_code, r.json()["error"]) == (403, "forbidden")


def test_a_server_answers_whatever_name_it_is_reached_by(tmp_path):
    host, client = server(tmp_path)  # TestClient's Host is "testserver"
    assert client.get("/v1/games", headers=project(host)).status_code == 200


def test_a_body_over_the_limit_is_refused_whether_or_not_it_says_its_length(tmp_path):
    host, client = server(tmp_path)
    auth = project(host)
    sid = opened(client, auth)
    big = json.dumps({"npc": "garrick", "situation": "x" * MAX_BODY_BYTES}).encode()
    r = client.post(f"/v1/sessions/{sid}/decide", content=big, headers={**auth, "content-type": "application/json"})
    assert (r.status_code, r.json()["error"]) == (413, "too_large")

    def chunks():  # no Content-Length: counted as it comes
        yield big[:1000]
        yield big[1000:]
    r = client.post(f"/v1/sessions/{sid}/decide", content=chunks(), headers={**auth, "content-type": "application/json"})
    assert (r.status_code, r.json()["error"]) == (413, "too_large")
    assert client.post(f"/v1/sessions/{sid}/observe", json={"verb": "insult", "actor": "player", "target": "garrick",
                                                            "witnesses": ["wren"]}, headers=auth).status_code == 201


def test_a_session_opened_from_a_snapshot_may_be_larger(tmp_path):
    host, client = server(tmp_path)
    auth = project(host)
    r = client.post("/v1/sessions", json={"game": "tavern", "snapshot": {"padding": "x" * 2 * MAX_BODY_BYTES}},
                    headers=auth)
    assert (r.status_code, r.json()["error"]) == (400, "bad_definition")  # read whole, and refused as no save


def test_a_bad_content_length_is_a_bad_request(tmp_path):
    host, client = server(tmp_path)
    r = client.post("/v1/sessions", content=b"{}", headers={**project(host), "content-length": "lots",
                                                            "content-type": "application/json"})
    assert r.status_code == 400


@pytest.mark.parametrize("given, name", [("localhost:8123", "localhost"), ("[::1]:80", "::1"), ("[::1]", "::1"),
                                         ("127.0.0.1", "127.0.0.1"), ("", "")])
def test_the_name_in_a_host_header(given, name):
    assert _hostname(given) == name
