"""The inspector: read-only routes for a runtime's sessions (list them, see one at a glance, explain a choice), and a
page `thespis serve` serves that shows them through those routes, with the caller's token, loading nothing from
anywhere else. A designer asking "what does everyone believe now, and why didn't she act?" opens it beside the game."""

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from tests.test_host import INSULT, TAVERN, opened, project, server
from thespis.host import SIDECAR, Host
from thespis.server import INSPECTOR, INSPECTOR_DIR, create_app
from thespis.session import Session
from thespis.storage import SqliteStorage

ROOT = Path(__file__).resolve().parents[1]


def sidecar(tmp_path, token: str | None = "t0k") -> TestClient:
    host = Host(SqliteStorage(tmp_path / "side.sqlite"), {"tavern": TAVERN}, mode=SIDECAR, token=token)
    return TestClient(create_app(host=host), base_url="http://127.0.0.1:7878")


AUTH = {"Authorization": "Bearer t0k"}


# ---------------------------------------------------------------- the library
def test_overview_shows_the_cast_its_ties_and_how_many_beliefs_each_holds():
    s = Session.new(TAVERN)
    s.observe(**INSULT)
    o = s.overview()
    assert (o["game"], o["name"], o["phase"], o["events"]) == ("tavern", "The Lantern", 0, 1)
    garrick = next(n for n in o["npcs"] if n["id"] == "garrick")
    assert garrick["name"] == "Garrick" and garrick["moments"] == ["turn"] and garrick["loc"] == "taproom"
    assert (garrick["beliefs"], garrick["retracted"]) == (1, 0)
    assert garrick["drives"] == s.inspect("garrick")["npc"]["drives"]
    assert [p["id"] for p in o["players"]] == ["player"]
    assert o["places"]["yard"] == "the stable yard"


def test_overview_lists_the_game_files_ties_once_and_those_made_in_play():
    toml = (ROOT / "examples" / "tavern" / "game.toml").read_text(encoding="utf-8") + '''
[gossip.along]
friend = 0.9

[[tie]]
between = ["garrick", "wren"]
kind = "friend"
'''
    from thespis.session import Game
    s = Session.new(Game.parse(toml, "tavern"))
    s.tie("wren", "pip", "friend")
    assert s.overview()["ties"] == [{"between": ["garrick", "wren"], "kind": "friend", "made": "game"},
                                    {"between": ["wren", "pip"], "kind": "friend", "made": "play"}]


# ---------------------------------------------------------------- the routes
def test_sessions_are_listed_newest_first_and_only_the_projects_own(tmp_path):
    host, client = server(tmp_path)
    a, b = project(host, "a"), project(host, "b")
    first, second = opened(client, a), opened(client, a)
    theirs = opened(client, b)
    client.post(f"/v1/sessions/{first}/observe", json=INSULT, headers=a)  # saved last, so listed first
    rows = client.get("/v1/sessions", headers=a).json()
    assert [r["session"] for r in rows] == [first, second]
    assert all(r["game"] == "tavern" and r["held"] and r["updated"] >= r["created"] for r in rows)
    assert [r["session"] for r in client.get("/v1/sessions", headers=b).json()] == [theirs]
    assert len(client.get("/v1/sessions?limit=1", headers=a).json()) == 1


def test_a_session_at_a_glance_and_why_over_http_change_nothing(tmp_path):
    client = sidecar(tmp_path)
    sid = client.post("/v1/sessions", json={"game": "tavern"}, headers=AUTH).json()["session"]
    client.post(f"/v1/sessions/{sid}/observe", json=INSULT, headers=AUTH)
    before = client.get(f"/v1/sessions/{sid}/snapshot", headers=AUTH).json()
    o = client.get(f"/v1/sessions/{sid}", headers=AUTH)
    assert o.status_code == 200, o.text
    assert [n["id"] for n in o.json()["npcs"]] == ["garrick", "wren", "pip"]
    why = client.post(f"/v1/sessions/{sid}/explain", json={"npc": "garrick", "moment": "turn"}, headers=AUTH)
    assert why.status_code == 200, why.text
    rows = why.json()
    assert [r["do"] for r in rows if r["chosen"]] == ["confront:player"]
    shut = next(r for r in rows if r["do"] == "share_drink:player")
    assert not shut["open"] and shut["blocked"] == "respect is 1, needs >= 4" and shut["terms"]
    assert client.get(f"/v1/sessions/{sid}/snapshot", headers=AUTH).json() == before
    assert client.post(f"/v1/sessions/{sid}/explain", json={"npc": "garrick", "moment": "nope"},
                       headers=AUTH).status_code == 404
    assert client.get("/v1/sessions/nope", headers=AUTH).status_code == 404


def test_the_routes_want_the_token_and_the_page_does_not(tmp_path):
    client = sidecar(tmp_path)
    assert client.get("/v1/sessions").status_code == 401
    assert client.get("/inspector/").status_code == 200  # a page with no data in it: the data wants the token


# ---------------------------------------------------------------- the page
def test_the_page_is_served_with_a_policy_that_loads_nothing_from_elsewhere(tmp_path):
    client = sidecar(tmp_path)
    page = client.get("/inspector/")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert "Thespis inspector" in page.text
    csp = page.headers["content-security-policy"]
    assert "default-src 'none'" in csp and "script-src 'self'" in csp and "connect-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert page.headers["referrer-policy"] == "no-referrer"
    for name in ("inspector.js", "inspector.css"):
        r = client.get(f"/inspector/{name}")
        assert r.status_code == 200 and r.headers["content-security-policy"] == csp
    assert client.get("/inspector", follow_redirects=False).headers["location"] == "/inspector/"
    assert client.get("/inspector/server.py").status_code == 404
    assert client.get("/inspector/..%2Fserver.py").status_code == 404


def test_the_page_needs_only_its_own_files_and_is_not_in_the_contract():
    html = (INSPECTOR_DIR / "index.html").read_text(encoding="utf-8")
    wanted = set(re.findall(r'(?:src|href)="([^"]+)"', html))
    assert wanted == {"inspector.js", "inspector.css"} and wanted <= set(INSPECTOR)
    assert all((INSPECTOR_DIR / f).is_file() for f, _ in INSPECTOR.values())
    spec = json.loads((ROOT / "docs" / "openapi-v1.json").read_text(encoding="utf-8"))
    assert all(p.startswith("/v1/") for p in spec["paths"])  # the SDKs' contract is the API, not the page


def test_the_page_sets_what_a_game_wrote_as_text_and_only_reads():
    js = (INSPECTOR_DIR / "inspector.js").read_text(encoding="utf-8")
    assert "innerHTML" not in js and "outerHTML" not in js and "insertAdjacentHTML" not in js
    assert "eval(" not in js and "new Function" not in js
    # Only the routes that change nothing: GETs, and the POSTs explain and trace.
    posts = set(re.findall(r'api\(`sessions/\$\{[^}]+\}/(\w+)`,', js))
    assert posts == {"explain", "trace"}
    assert not re.search(r'method:\s*"(PUT|DELETE|PATCH)"', js)
