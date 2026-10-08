"""Run the Godot spike's round trip headless: a scripted model, `thespis serve` speaking through it, then Godot.

    python sdk/godot/spike/test/run.py --godot <path to Godot 4's console build>

The scripted model is a stand-in for any OpenAI-compatible endpoint (llama.cpp, vLLM, a cloud provider). It answers
after a delay, so the scene sees a line arrive provisional and settle when the model's words come. Exits with
Godot's code: 0 when every check passed.
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
    args = parser.parse_args()
    if not args.godot:
        parser.error("say where Godot is: --godot <path> or GODOT=<path>")

    model = ThreadingHTTPServer(("127.0.0.1", free_port()), ScriptedModel)
    threading.Thread(target=model.serve_forever, daemon=True).start()
    port = free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith("LLM_")}  # only the scripted model
    env |= {"LLM_BASE_URL": f"http://127.0.0.1:{model.server_port}/v1", "LLM_API_KEY": "scripted",
            "LLM_MODEL": "scripted"}
    server = subprocess.Popen([sys.executable, "-m", "thespis", "serve", "--game", str(GAME), "--port", str(port)],
                              cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{url}/v1/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            print("thespis serve didn't start:", server.stderr.read().decode() if server.stderr else "")
            return 3
        godot = subprocess.run([args.godot, "--headless", "--path", str(SPIKE), "--script", "res://test/round_trip.gd"],
                               env={**env, "THESPIS_URL": url}, timeout=120)
        return godot.returncode
    finally:
        server.terminate()
        server.wait(10)
        model.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
