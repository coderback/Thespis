"""Run the Godot spike's round trip headless: a sidecar (`thespis serve`) speaking through a model, then Godot.

    python sdk/godot/spike/test/run.py --godot <path to Godot 4's console build>
    python sdk/godot/spike/test/run.py --godot <...> --local gemma4-e4b [--exe dist/thespis/thespis.exe]

By default the model is scripted: a stand-in for any OpenAI-compatible endpoint (llama.cpp, vLLM, a cloud provider)
that answers after a delay, so the scene sees a line arrive provisional and settle when the model's words come.

With `--local`, the sidecar speaks through a local model (thespis.runtime) and is offline, as a shipped game's would
be: it refuses every connection off this machine. That is Phase 4.4's offline gate, and it passes only if every
check passes and the sidecar refused nothing, so the scene needed nothing but this machine. `--exe` runs the
packaged runtime (tools/package.py) instead of Python. Exits with Godot's code: 0 when every check passed.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[4]
SPIKE = ROOT / "sdk" / "godot" / "spike"
GAME = ROOT / "examples" / "tavern" / "game.toml"
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--godot", default=os.environ.get("GODOT", ""), help="Godot 4's console build ($GODOT)")
    parser.add_argument("--local", help="speak through this local model, offline (e.g. gemma4-e4b), not a script")
    parser.add_argument("--exe", help="the packaged runtime to run instead of python -m thespis")
    args = parser.parse_args()
    if not args.godot:
        parser.error("say where Godot is: --godot <path> or GODOT=<path>")

    env = {k: v for k, v in os.environ.items() if not k.startswith("LLM_")}  # only the model given here
    model = None
    serve = [str(Path(args.exe).resolve())] if args.exe else [sys.executable, "-m", "thespis"]
    serve += ["serve", "--game", str(GAME), "--port", "0", "--db", ":memory:", "--parent", str(os.getpid())]
    if args.local:
        serve += ["--local", args.local]
    else:
        model = ThreadingHTTPServer(("127.0.0.1", free_port()), ScriptedModel)
        threading.Thread(target=model.serve_forever, daemon=True).start()
        env |= {"LLM_BASE_URL": f"http://127.0.0.1:{model.server_port}/v1", "LLM_API_KEY": "scripted",
                "LLM_MODEL": "scripted"}
    server = subprocess.Popen(serve, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert server.stdout is not None and server.stderr is not None
        url = server.stdout.readline().strip().partition("=")[2]  # once the local model is up, if there is one
        if not url:
            print("thespis serve didn't start:", server.stderr.read())
            return 3
        for _ in range(100):
            try:
                if httpx.get(f"{url}/v1/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        timeout = "90" if args.local else "30"
        godot = subprocess.run([args.godot, "--headless", "--path", str(SPIKE), "--script", "res://test/round_trip.gd"],
                               env={**env, "THESPIS_URL": url, "THESPIS_TEST_TIMEOUT": timeout}, timeout=300)
        health = httpx.get(f"{url}/v1/health", timeout=5).json()
        print(f"sidecar: offline {health['offline']}, refused {health['refused']} connections off this machine")
        if args.local and (not health["offline"] or health["refused"]):
            print("FAIL: the offline scene reached for the network")
            return 1
        return godot.returncode
    finally:
        server.terminate()
        server.wait(30)
        if model:
            model.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
