"""The `thespis serve` process: offline unless told otherwise, a trace per line, a port the launcher can ask for,
a life tied to the game that started it, and the commands that run a server's projects."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.test_host import INSULT, TAVERN, Gated
from thespis import offline
from thespis.__main__ import main
from thespis.gateway import OpenAICompatGateway, Provider
from thespis.host import Host
from thespis.runtime.local import watch_parent
from thespis.server import create_app

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "examples" / "tavern" / "game.toml"


# ---------------------------------------------------------------- offline
@pytest.fixture
def guarded():
    offline.refused.clear()
    offline.guard()
    yield
    offline.release()


def test_offline_refuses_everything_off_this_machine(guarded):
    with pytest.raises(OSError):
        socket.getaddrinfo("example.com", 443)
    with socket.socket() as s, pytest.raises(OSError):
        s.connect(("93.184.215.14", 443))
    assert socket.getaddrinfo("localhost", 80)  # this machine is fine
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        with socket.socket() as s:
            s.connect(server.getsockname())
    assert offline.refused == ["looking up example.com", "connecting to 93.184.215.14"]


def test_offline_a_cloud_model_falls_back_at_once(guarded):
    gateway = OpenAICompatGateway([Provider("cloud", "https://api.openai.com/v1", "k", "gpt-x")])
    started = time.perf_counter()
    assert gateway.complete("react", [{"role": "user", "content": "hi"}]) is None
    assert time.perf_counter() - started < 1.0
    assert offline.refused and "api.openai.com" in offline.refused[0]
    assert offline.local("127.0.0.1") and offline.local("::1") and offline.local("[::1]")
    assert not offline.local("10.0.0.1") and not offline.local("api.openai.com")


# ---------------------------------------------------------------- traces
def test_a_lines_spans_join_the_request_that_asked_for_it():
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("thespis")
    real = trace.get_tracer
    trace.get_tracer = lambda *a, **k: tracer  # type: ignore[assignment]
    try:
        model = Gated()
        client = TestClient(create_app({"tavern": TAVERN}, model))
        sid = client.post("/v1/sessions", json={"game": "tavern"}).json()["session"]
        client.post(f"/v1/sessions/{sid}/observe", json=INSULT)
        line = client.post(f"/v1/sessions/{sid}/decide", json={"npc": "garrick", "moment": "turn"}).json()
        client.get(f"/v1/sessions/{sid}/lines/{line['id']}?wait=5")
    finally:
        trace.get_tracer = real  # type: ignore[assignment]
    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert "thespis.mind.act" in spans
    decide = next(s for s in exporter.get_finished_spans() if s.name == "thespis.http"
                  and s.attributes.get("http.route") == "/v1/sessions/{sid}/decide")
    act = spans["thespis.mind.act"]
    assert act.context.trace_id == decide.context.trace_id  # answered after the request, still in its trace
    assert act.attributes["sources"] == "llm"


# ---------------------------------------------------------------- the process
def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def started(args: list[str], env: dict | None = None) -> tuple[subprocess.Popen, str]:
    proc = subprocess.Popen([sys.executable, "-m", "thespis", "serve", *args], cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env)
    assert proc.stdout is not None
    first = proc.stdout.readline().strip()
    assert first.startswith("THESPIS_URL="), (first, proc.stderr.read() if proc.poll() is not None else "")
    url = first.removeprefix("THESPIS_URL=")
    for _ in range(100):
        try:
            if httpx.get(f"{url}/v1/health", timeout=1).status_code == 200:
                return proc, url
        except httpx.HTTPError:
            time.sleep(0.1)
    proc.kill()
    raise AssertionError("never answered")


def test_a_sidecar_on_a_port_of_its_choosing_stops_with_its_parent(tmp_path):
    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    proc, url = started(["--game", str(GAME), "--port", "0", "--db", str(tmp_path / "s.sqlite"),
                         "--parent", str(parent.pid)])
    try:
        sid = httpx.post(f"{url}/v1/sessions", json={"game": "tavern"}).json()["session"]
        assert httpx.post(f"{url}/v1/sessions/{sid}/observe", json=INSULT).status_code == 201
        parent.kill()
        parent.wait()  # reaped, as the game's own parent would: until then POSIX still lists it
        proc.wait(timeout=15)
    finally:
        parent.kill()
        proc.kill()
    assert proc.returncode == 0


def test_a_sidecar_listens_on_this_machine_only():
    r = subprocess.run([sys.executable, "-m", "thespis", "serve", "--host", "0.0.0.0", "--db", ":memory:"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 2 and "use --server" in r.stderr


def test_the_parent_watch_sees_its_process_end():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    gone = []
    t = watch_parent(child.pid, lambda: gone.append(True))
    child.kill()
    child.wait()
    t.join(timeout=10)
    assert gone == [True]


# ---------------------------------------------------------------- running a server's projects
def test_projects_and_usage_from_the_command_line(tmp_path, capsys):
    db = str(tmp_path / "server.sqlite")
    assert main(["projects", "create", "studio", "--calls-per-day", "500", "--db", db]) == 0
    key = capsys.readouterr().out.strip().splitlines()[-1]
    assert key.startswith("tsk_")
    assert main(["projects", "caps", "studio", "--max-sessions", "8", "--db", db]) == 0
    assert "'max_sessions': 8, 'calls_per_day': 500" in capsys.readouterr().out
    assert main(["projects", "list", "--db", db]) == 0
    assert "studio" in capsys.readouterr().out
    assert main(["projects", "secret"]) == 0
    secret = capsys.readouterr().out.strip().partition("=")[2]
    os.environ["THESPIS_SECRET_KEY"] = secret
    os.environ["STUDIO_KEY"] = "sk-from-env"
    assert main(["projects", "model", "studio", "--profile", "openai", "--model", "gpt-x", "--key-env", "STUDIO_KEY",
                 "--db", db]) == 0
    assert "kept, sealed" in capsys.readouterr().out
    from thespis.host import SERVER
    from thespis.storage import SqliteStorage
    from thespis.vault import Vault
    host = Host(SqliteStorage(db), mode=SERVER, vault=Vault(secret))
    assert host.authenticate(f"Bearer {key}").name == "studio"
    assert host.model_settings(host.storage.project("studio"))["primary"]["api_key_set"] is True
    assert main(["usage", "studio", "--db", db, "--out", str(tmp_path / "u.csv")]) == 0
    assert (tmp_path / "u.csv").read_text().startswith("project,session,kind")
    assert main(["projects", "key", "studio", "--db", db]) == 0
    assert host.storage.project_by_key(key) is None
