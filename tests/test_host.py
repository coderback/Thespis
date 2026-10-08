"""`thespis serve` as a sidecar and as a server (thespis.host, through /v1): keys and projects, games sent over the
wire, model keys sealed, caps, usage, and sessions that outlive the process that opened them."""

import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_model_voice import FakeModel
from thespis.gateway import ModelReply
from thespis.host import MEMORY, SERVER, SIDECAR, Host, HostError, check_model_url, provider_env
from thespis.server import create_app
from thespis.session import Game
from thespis.storage import Caps, SqliteStorage
from thespis.vault import Vault, new_secret

ROOT = Path(__file__).resolve().parents[1]
TAVERN_TOML = (ROOT / "examples" / "tavern" / "game.toml").read_text(encoding="utf-8")
TAVERN = Game.load(ROOT / "examples" / "tavern" / "game.toml")
INSULT = {"verb": "insult", "actor": "player", "target": "garrick",
          "claim": {"pred": "insulted", "a": "player", "b": "garrick"}, "witnesses": ["wren"]}


class Gated(FakeModel):
    """A model that answers only when the test lets it, and reports token use."""

    def __init__(self):
        super().__init__()
        self.go = threading.Event()
        self.go.set()

    def complete(self, call_type, messages, schema=None):
        self.go.wait(5)
        r = super().complete(call_type, messages, schema)
        return r and ModelReply(r.data, r.provider, r.model, r.latency, 120, 30)


def server(tmp_path, gateway=None, **kw) -> tuple[Host, TestClient]:
    host = Host(SqliteStorage(tmp_path / "server.sqlite"), {"tavern": TAVERN}, gateway, mode=SERVER,
                vault=Vault(new_secret()), **kw)
    return host, TestClient(create_app(host=host))


def project(host: Host, name: str = "studio", **caps) -> dict:
    _, key = host.storage.create_project(name, Caps(**caps))
    return {"Authorization": f"Bearer {key}"}


def opened(client: TestClient, auth: dict) -> str:
    r = client.post("/v1/sessions", json={"game": "tavern"}, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()["session"]


# ---------------------------------------------------------------- projects and keys
def test_a_server_wants_a_projects_key_and_keeps_projects_apart(tmp_path):
    host, client = server(tmp_path)
    a, b = project(host, "a"), project(host, "b")
    assert client.get("/v1/games").status_code == 401
    assert client.get("/v1/games", headers={"Authorization": "Bearer tsk_nope"}).json()["error"] == "unauthorized"
    assert client.get("/v1/health").status_code == 200  # the one open route
    sid = opened(client, a)
    assert client.post(f"/v1/sessions/{sid}/observe", json=INSULT, headers=a).status_code == 201
    for r in (client.post(f"/v1/sessions/{sid}/observe", json=INSULT, headers=b),
              client.get(f"/v1/sessions/{sid}/snapshot", headers=b), client.delete(f"/v1/sessions/{sid}", headers=b)):
        assert r.status_code == 404  # another project's session doesn't exist, as far as b can tell
    assert client.get("/v1/project", headers=a).json()["sessions"] == 1
    assert client.get("/v1/project", headers=b).json()["sessions"] == 0


def test_a_sidecar_serves_its_one_project_with_or_without_a_token(tmp_path):
    open_client = TestClient(create_app(host=Host(SqliteStorage(tmp_path / "a.sqlite"), {"tavern": TAVERN},
                                                  mode=SIDECAR)))
    assert open_client.get("/v1/project").json()["name"] == "local"
    locked = TestClient(create_app(host=Host(SqliteStorage(tmp_path / "b.sqlite"), {"tavern": TAVERN},
                                             mode=SIDECAR, token="t0k")))
    assert locked.get("/v1/games").status_code == 401
    assert locked.get("/v1/games", headers={"Authorization": "Bearer t0k"}).status_code == 200
    r = locked.put("/v1/project/model", json={"primary": {"model": "m", "base_url": "https://x.example"}},
                   headers={"Authorization": "Bearer t0k"})
    assert (r.status_code, r.json()["error"]) == (409, "not_allowed")


# ---------------------------------------------------------------- games sent over the wire
def test_a_project_sends_its_own_game_which_shadows_the_hosts(tmp_path):
    host, client = server(tmp_path)
    a, b = project(host, "a"), project(host, "b")
    renamed = TAVERN_TOML.replace('name = "The Lantern"', 'name = "Our Lantern"')
    assert renamed != TAVERN_TOML
    r = client.put("/v1/games/tavern", json={"toml": renamed}, headers=a)
    assert r.status_code == 200 and r.json()["name"] == "Our Lantern"
    assert [g["name"] for g in client.get("/v1/games", headers=a).json()] == ["Our Lantern"]
    assert [g["name"] for g in client.get("/v1/games", headers=b).json()] == ["The Lantern"]
    bad = client.put("/v1/games/tavern", json={"toml": "[npc.x]\nname = 3"}, headers=a)
    assert (bad.status_code, bad.json()["error"]) == (400, "bad_definition")
    assert client.put("/v1/games/inn", json={"toml": "not = [toml"}, headers=a).status_code == 400
    assert client.put("/v1/games/inn", json={"toml": TAVERN_TOML}, headers=a).json()["reason"] == \
        "the game says its id is 'tavern', not 'inn'"
    assert client.delete("/v1/games/tavern", headers=a).status_code == 204
    assert client.delete("/v1/games/tavern", headers=a).status_code == 404  # the host's own can't be deleted
    assert client.put("/v1/games/x", json={"toml": "#" * 300_000}, headers=a).status_code == 413


# ---------------------------------------------------------------- model keys
def test_model_keys_are_sealed_at_rest_and_never_sent_back(tmp_path):
    host, client = server(tmp_path)
    a = project(host, "a")
    body = {"primary": {"profile": "openai", "model": "gpt-x", "api_key": "sk-very-secret"}}
    assert client.put("/v1/project/model", json=body, headers=a).status_code == 204
    raw = (tmp_path / "server.sqlite").read_bytes()
    assert b"sk-very-secret" not in raw and b"gpt-x" not in raw  # the whole of it is sealed
    shown = client.get("/v1/project", headers=a).json()["model"]
    assert shown["primary"]["model"] == "gpt-x" and shown["primary"]["api_key_set"] is True
    assert "sk-very-secret" not in json.dumps(shown)
    gateway = host.project_gateway(host.storage.project("a"))
    assert [p.api_key for p in gateway.providers] == ["sk-very-secret"]  # type: ignore[attr-defined]
    assert client.delete("/v1/project/model", headers=a).status_code == 204
    assert client.get("/v1/project", headers=a).json()["model"] is None


def test_a_server_wont_call_into_its_own_network_for_a_project():
    for url in ("http://api.openai.com/v1", "https://127.0.0.1:8080/v1", "https://10.0.0.5/v1",
                "https://169.254.169.254/latest", "https://localhost/v1", "file:///etc/passwd"):
        with pytest.raises(HostError):
            check_model_url(url)
    check_model_url("http://10.0.0.5:8000/v1", allow_private=True)  # a server beside its own vLLM, when told
    assert provider_env({"primary": {"model": "m", "extra": {"a": 1}, "structured": False}, "backup": None}) == \
        {"LLM_MODEL": "m", "LLM_EXTRA": '{"a": 1}', "LLM_STRUCTURED": "0"}


def test_a_server_without_a_secret_wont_take_model_keys(tmp_path):
    host = Host(SqliteStorage(tmp_path / "s.sqlite"), {"tavern": TAVERN}, mode=SERVER)
    client = TestClient(create_app(host=host))
    r = client.put("/v1/project/model", json={"primary": {"profile": "openai", "model": "m", "api_key": "k"}},
                   headers=project(host))
    assert (r.status_code, r.json()["error"]) == (503, "no_vault")


# ---------------------------------------------------------------- caps and usage
def test_over_its_daily_cap_a_project_gets_template_lines(tmp_path):
    model = Gated()
    host, client = server(tmp_path, model, cache=False)
    a = project(host, "a", calls_per_day=1)
    sid = opened(client, a)
    client.post(f"/v1/sessions/{sid}/observe", json=INSULT, headers=a)
    first = client.post(f"/v1/sessions/{sid}/react", json={"npc": "garrick", "trigger": "insulted", "wait": True},
                        headers=a).json()
    second = client.post(f"/v1/sessions/{sid}/react", json={"npc": "wren", "trigger": "talk", "wait": True},
                         headers=a).json()
    assert (first["source"], second["source"]) == ("llm", "fallback")
    assert len(model.calls) == 1
    kinds = [(e["kind"], e["source"]) for e in client.get("/v1/usage", headers=a).json()]
    assert kinds == [("call", None), ("line", "llm"), ("capped", "calls_per_day"), ("line", "fallback")]
    assert client.get("/v1/project", headers=a).json()["today"] == {"calls": 1, "tokens": 150}


def test_a_project_holds_at_most_its_sessions(tmp_path):
    host, client = server(tmp_path)
    a = project(host, "a", max_sessions=1)
    sid = opened(client, a)
    assert client.post("/v1/sessions", json={"game": "tavern"}, headers=a).status_code == 503
    client.delete(f"/v1/sessions/{sid}", headers=a)
    opened(client, a)


def test_usage_exports_as_csv_and_cache_hits_are_free(tmp_path):
    host, client = server(tmp_path, Gated())
    a = project(host, "a")
    for _ in range(2):  # the same moment twice: the second is answered from the project's cache
        sid = opened(client, a)
        client.post(f"/v1/sessions/{sid}/observe", json=INSULT, headers=a)
        client.post(f"/v1/sessions/{sid}/react", json={"npc": "garrick", "trigger": "insulted", "wait": True},
                    headers=a)
    r = client.get("/v1/usage?format=csv", headers=a)
    assert r.headers["content-type"].startswith("text/csv")
    rows = r.text.splitlines()
    assert rows[0].startswith("project,session,kind,call_type,ok")
    assert [row.split(",")[2] for row in rows[1:]] == ["call", "line", "line"]
    assert rows[3].split(",")[6] == "cache"
    assert client.get("/v1/project", headers=a).json()["today"]["calls"] == 1


# ---------------------------------------------------------------- sessions outlive the process
def test_a_session_survives_a_restart_and_a_settling_line_is_saved(tmp_path):
    model = Gated()
    model.go.clear()
    host, client = server(tmp_path, model)
    a = project(host, "a")
    sid = opened(client, a)
    client.post(f"/v1/sessions/{sid}/observe", json=INSULT, headers=a)
    line = client.post(f"/v1/sessions/{sid}/decide", json={"npc": "garrick", "moment": "turn"}, headers=a).json()
    assert line["status"] == "provisional"
    model.go.set()
    final = client.get(f"/v1/sessions/{sid}/lines/{line['id']}?wait=5", headers=a).json()
    assert final["status"] == "final" and final["text"] == "So be it."
    before = client.get(f"/v1/sessions/{sid}/snapshot", headers=a).json()
    host.shutdown()

    host2, client2 = server(tmp_path, Gated())  # a new process on the same database
    assert client2.get(f"/v1/sessions/{sid}/snapshot", headers=a).json() == before
    assert before["world"]["decisions"][0]["line"] == "So be it."  # saved when it settled, not only per call
    r = client2.post(f"/v1/sessions/{sid}/tick", json={"steps": 1}, headers=a)
    assert r.status_code == 200 and r.json()["phase"] == before["world"]["phase"] + 1


def test_two_instances_on_one_database_stay_in_step(tmp_path):
    db = tmp_path / "shared.sqlite"
    one = Host(SqliteStorage(db), {"tavern": TAVERN}, mode=SERVER)
    two = Host(SqliteStorage(db), {"tavern": TAVERN}, mode=SERVER)
    c1, c2 = TestClient(create_app(host=one)), TestClient(create_app(host=two))
    a = project(one, "a")
    sid = opened(c1, a)
    c2.post(f"/v1/sessions/{sid}/observe", json=INSULT, headers=a)  # instance two loads it and moves it on
    c1.post(f"/v1/sessions/{sid}/tick", json={"steps": 1}, headers=a)  # one sees it moved, reloads, plays on
    snap = c2.get(f"/v1/sessions/{sid}/snapshot", headers=a).json()
    assert len(snap["world"]["ledger"]) >= 1 and snap["world"]["phase"] == 1
    assert c1.get(f"/v1/sessions/{sid}/snapshot", headers=a).json() == snap
    c1.delete(f"/v1/sessions/{sid}", headers=a)
    assert c2.get(f"/v1/sessions/{sid}/snapshot", headers=a).status_code == 404


def test_idle_sessions_leave_memory_and_come_back_from_storage(tmp_path):
    host = Host(SqliteStorage(tmp_path / "s.sqlite"), {"tavern": TAVERN}, mode=SERVER, live=2)
    client = TestClient(create_app(host=host))
    a = project(host, "a")
    sids = [opened(client, a) for _ in range(4)]
    assert host.held() == 2
    r = client.post(f"/v1/sessions/{sids[0]}/observe", json=INSULT, headers=a)
    assert r.status_code == 201 and host.held() == 2


def test_memory_mode_is_the_libraryish_default():
    host = Host(games={"tavern": TAVERN})
    assert host.mode == MEMORY and host.authenticate(None).name == "local"
