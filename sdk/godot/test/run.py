"""Play the Godot addon's example scene headless, once per way of running Thespis, with the scene unchanged.

    python sdk/godot/test/run.py --godot <path to Godot 4's console build>          # sidecar, then server
    python sdk/godot/test/run.py --godot <...> --mode sidecar --local gemma4-e4b    # the offline gate
    python sdk/godot/test/run.py --godot <...> --mode sidecar --exe dist/thespis/thespis.exe

- **sidecar:** the addon starts `thespis serve` itself, on this machine and offline, as a shipped game would.
- **server:** a hosted-mode server (`thespis serve --server`) with a project and its key. The scene finds it through
  THESPIS_URL and THESPIS_KEY, and sends it the game, which a server doesn't have until a project sends it.

By default the model is scripted: a stand-in for any OpenAI-compatible endpoint that answers after a delay, so the
scene sees each line arrive provisional and settle when the model's words come. With `--local`, the sidecar speaks
through a local model instead (thespis.runtime), and the run passes only if the sidecar refused nothing off this
machine. `--exe` has the addon start the packaged runtime (tools/package.py) instead of Python. Exits 0 when every
run passed.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
PROJECT = ROOT / "sdk" / "godot"
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


def godot(exe: str, env: dict[str, str], timeout: float) -> int:
    """Import the project (so the addon's classes are known), then play the example under the test script."""
    subprocess.run([exe, "--headless", "--path", str(PROJECT), "--import"], env=env, capture_output=True,
                   timeout=300)
    run = subprocess.run([exe, "--headless", "--path", str(PROJECT), "--script", "res://test/example_test.gd"],
                         env=env | {"THESPIS_TEST_TIMEOUT": str(timeout)}, cwd=ROOT, timeout=timeout + 60)
    return run.returncode


def sidecar(args: argparse.Namespace, env: dict[str, str]) -> int:
    print("== sidecar: the addon starts the runtime itself")
    command = [str(Path(args.exe).resolve())] if args.exe else [sys.executable, "-m", "thespis"]
    env = env | {"THESPIS_EXPECT": "sidecar", "THESPIS_SIDECAR": json.dumps(command)}
    if args.local:
        env |= {"THESPIS_TEST_MODEL": args.local}
    return godot(args.godot, env, 240.0 if args.local else 60.0)


def server(args: argparse.Namespace, env: dict[str, str]) -> int:
    print("== server: hosted mode, with a project and its key")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:  # Windows: the venv launcher's child lingers
        db = str(Path(tmp) / "server.sqlite")
        made = subprocess.run([sys.executable, "-m", "thespis", "projects", "create", "godot", "--db", db],
                              cwd=ROOT, env=env, capture_output=True, text=True, check=True)
        key = made.stdout.strip().splitlines()[-1]
        serve = subprocess.Popen([sys.executable, "-m", "thespis", "serve", "--server", "--db", db, "--port", "0",
                                  "--parent", str(os.getpid())], cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        try:
            assert serve.stdout is not None and serve.stderr is not None
            url = serve.stdout.readline().strip().partition("=")[2]
            if not url:
                print("thespis serve --server didn't start:", serve.stderr.read())
                return 3
            for _ in range(100):
                try:
                    if httpx.get(f"{url}/v1/health", timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    time.sleep(0.1)
            return godot(args.godot, env | {"THESPIS_EXPECT": "server", "THESPIS_URL": url, "THESPIS_KEY": key},
                         60.0)
        finally:
            serve.terminate()
            serve.wait(30)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--godot", default=os.environ.get("GODOT", ""), help="Godot 4's console build ($GODOT)")
    parser.add_argument("--mode", choices=["both", "sidecar", "server"], default="both")
    parser.add_argument("--local", help="the sidecar speaks through this local model, offline (e.g. gemma4-e4b)")
    parser.add_argument("--exe", help="the packaged runtime for the addon to start instead of python -m thespis")
    args = parser.parse_args()
    if not args.godot:
        parser.error("say where Godot is: --godot <path> or GODOT=<path>")
    if args.local and args.mode != "sidecar":
        parser.error("--local is for the sidecar: add --mode sidecar")

    env = {k: v for k, v in os.environ.items() if not k.startswith(("LLM_", "THESPIS_"))}  # only what's given here
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT), env.get("PYTHONPATH", "")]))
    model = None
    if not args.local:
        model = ThreadingHTTPServer(("127.0.0.1", free_port()), ScriptedModel)
        threading.Thread(target=model.serve_forever, daemon=True).start()
        env |= {"LLM_BASE_URL": f"http://127.0.0.1:{model.server_port}/v1", "LLM_API_KEY": "scripted",
                "LLM_MODEL": "scripted"}
    try:
        codes = []
        if args.mode in ("both", "sidecar"):
            codes.append(sidecar(args, env))
        if args.mode in ("both", "server"):
            codes.append(server(args, env))
        return next((c for c in codes if c), 0)
    finally:
        if model:
            model.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
