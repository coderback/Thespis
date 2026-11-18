"""Before the Ice in the browser (games/ice/api.py): the web build at /ice/, its own Thespis at /thespis, the week's
records at /ice/record. A stand-in build (an index.html) is enough: the real one is Godot's, made by the Dockerfile."""

import json

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from games.hosting import ApiError
from games.ice import api as ice

ADMIN = "test-admin"


@pytest.fixture
def client(tmp_path, monkeypatch):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<canvas id='canvas'></canvas>", encoding="utf-8")
    monkeypatch.setattr(ice, "WEB", web)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "thespis.sqlite"))
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    monkeypatch.delenv("ICE_PLAYTEST", raising=False)
    app = FastAPI()
    app.state.admin_token = ADMIN

    @app.exception_handler(ApiError)
    async def api_error(request, exc: ApiError):
        return JSONResponse({"error": exc.error, "reason": exc.reason}, status_code=exc.status)

    ice.install(app)
    return TestClient(app)


def record(name="2026-11-18_20-21-19-seed19-0042", md="# a week", data=None):
    return {"name": name, "md": md, "json": json.dumps(data or {"seed": 19, "journal": []})}


def test_the_build_is_served_and_a_link_keeps_its_seed(client):
    assert "<canvas" in client.get("/ice/").text
    r = client.get("/ice?seed=19", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/ice/?seed=19"


def test_thespis_plays_coldwater_and_nothing_else(client):
    assert client.get("/thespis/v1/health").json()["ok"]
    opened = client.post("/thespis/v1/sessions", json={"game": "coldwater", "seed": 19})
    assert opened.status_code == 201 and opened.json()["game"] == "coldwater"
    # the game's own PUT of coldwater is answered as done; any other game, or a model, is refused
    assert client.put("/thespis/v1/games/coldwater", json={"toml": "anything"}).status_code == 200
    assert client.put("/thespis/v1/games/mine", json={"toml": "[game]\nid = \"mine\""}).status_code == 403
    assert client.delete("/thespis/v1/games/coldwater").status_code == 403
    assert client.put("/thespis/v1/project/model", json={}).status_code == 403


def test_a_record_is_kept_replaced_and_read_only_by_the_admin(client, tmp_path):
    assert client.post("/ice/record", json=record(md="# day 1")).status_code == 200
    assert client.post("/ice/record", json=record(md="# day 2")).status_code == 200  # the same week, sent again
    kept = tmp_path / "data" / "playtest" / "2026-11-18_20-21-19-seed19-0042.md"
    assert kept.read_text(encoding="utf-8") == "# day 2"
    assert client.get("/ice/records").status_code == 401
    admin = {"Authorization": f"Bearer {ADMIN}"}
    listed = client.get("/ice/records", headers=admin).json()
    assert [r["name"] for r in listed] == ["2026-11-18_20-21-19-seed19-0042"]
    page = client.get("/ice/records/2026-11-18_20-21-19-seed19-0042.md", headers=admin)
    assert page.status_code == 200 and page.text == "# day 2"
    assert client.get("/ice/records/..%2Fthespis.sqlite", headers=admin).status_code == 404


def test_a_bad_record_is_refused(client):
    assert client.post("/ice/record", json=record(name="../escape")).status_code == 400
    assert client.post("/ice/record", json={**record(), "json": "not json"}).status_code == 400
    assert client.post("/ice/record", json=record(md="x" * (ice.RECORD_MAX + 1))).status_code == 413


def test_off_without_a_build_or_when_turned_off(tmp_path, monkeypatch):
    monkeypatch.setattr(ice, "WEB", tmp_path / "nothing")
    assert not ice.enabled()
    monkeypatch.setattr(ice, "WEB", tmp_path)
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    assert ice.enabled()
    monkeypatch.setenv("ICE_PLAYTEST", "0")
    assert not ice.enabled()
