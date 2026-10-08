"""What the SDKs' test runners share (sdk/godot/test/run.py, sdk/unity/test/run.py): a scripted model, a hosted-mode
server with a project and its key, and the environment an engine's test gets.

The model is a stand-in for any OpenAI-compatible endpoint (llama.cpp, vLLM, a cloud provider). It answers after a
delay, so a scene sees each line arrive provisional and settle when the model's words come.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
TAVERN = ROOT / "examples" / "tavern" / "game.toml"
DELAY = 1.0  # seconds the scripted model takes, well inside the gateway's 4 s budget
LINE = "Watch your tongue, stranger."


class ScriptedModel(BaseHTTPRequestHandler):
    """An OpenAI-compatible /chat/completions that cites the first event in the state pack, else the first belief."""

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        pack = json.loads(body["messages"][1]["content"])
        refs = [x["id"] for x in pack.get("events", []) + pack.get("beliefs", [])]
        time.sleep(DELAY)
        content = json.dumps({"cites": refs[:1], "line": LINE})
        reply = json.dumps({"choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                            "usage": {"prompt_tokens": 0, "completion_tokens": 0}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, *args) -> None:
        pass


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def base_env() -> dict[str, str]:
    """This process's environment without any model or Thespis settings, so only what a run gives it applies."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LLM_", "THESPIS_"))}
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT), env.get("PYTHONPATH", "")]))
    return env


@contextmanager
def scripted_model() -> Iterator[dict[str, str]]:
    """Serve the scripted model; yields the LLM_* settings that point at it."""
    model = ThreadingHTTPServer(("127.0.0.1", free_port()), ScriptedModel)
    threading.Thread(target=model.serve_forever, daemon=True).start()
    try:
        yield {"LLM_BASE_URL": f"http://127.0.0.1:{model.server_port}/v1", "LLM_API_KEY": "scripted",
               "LLM_MODEL": "scripted"}
    finally:
        model.shutdown()


@contextmanager
def hosted_server(env: dict[str, str]) -> Iterator[dict[str, str]]:
    """A hosted-mode server (`thespis serve --server`) with one project; yields THESPIS_URL and THESPIS_KEY."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:  # Windows: the venv launcher's child lingers
        db = str(Path(tmp) / "server.sqlite")
        made = subprocess.run([sys.executable, "-m", "thespis", "projects", "create", "sdk", "--db", db],
                              cwd=ROOT, env=env, capture_output=True, text=True, check=True)
        key = made.stdout.strip().splitlines()[-1]
        serve = subprocess.Popen([sys.executable, "-m", "thespis", "serve", "--server", "--db", db, "--port", "0",
                                  "--parent", str(os.getpid())], cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        try:
            assert serve.stdout is not None and serve.stderr is not None
            url = serve.stdout.readline().strip().partition("=")[2]
            if not url:
                raise RuntimeError(f"thespis serve --server didn't start: {serve.stderr.read()}")
            for _ in range(100):
                try:
                    if httpx.get(f"{url}/v1/health", timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    time.sleep(0.1)
            yield {"THESPIS_URL": url, "THESPIS_KEY": key}
        finally:
            serve.terminate()
            serve.wait(30)


def sidecar_command(exe: str | None) -> str:
    """THESPIS_SIDECAR: how an engine's client starts the runtime, the packaged one or this Python's."""
    return json.dumps([str(Path(exe).resolve())] if exe else [sys.executable, "-m", "thespis"])
