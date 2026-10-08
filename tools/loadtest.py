"""Load-test `thespis serve --server`: many engines playing at once against one server, through /v1 with a project
key, over a scripted model that answers after a set delay.

    python tools/loadtest.py --players 100 --db postgresql://localhost/thespis_load [--rounds 3] [--delay 0.4]
    python tools/loadtest.py --players 100 --db server.sqlite

Each player is an engine playing the tavern: it opens a session, reports an insult, moves a drive, asks Garrick to
decide (a provisional line), long-polls that line until it is final, asks Wren to react, ticks, asks for the
narration, saves a snapshot, and closes; then plays again, `--rounds` times. Between calls it waits `--think`
seconds on average, as a player takes their turn; with `--think 0` it calls as fast as it can, which measures what
one server process can take at most. Every request's latency is kept per route, and every line's time from asked to
final.

The gate (docs/serve.md): no errors, and the engine's calls (everything but the long poll, which waits for the model
by design) answer within P95_MS at the 95th percentile. Lines settle as fast as the model and its concurrency allow:
their times are reported, not gated, since they measure the scripted model, not the server.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import multiprocessing
import os
import random
import statistics
import subprocess
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "examples" / "tavern" / "game.toml"
P95_MS = 250.0
INSULT = {"verb": "insult", "actor": "player", "target": "garrick", "witnesses": ["wren"],
          "claim": {"pred": "insulted", "a": "player", "b": "garrick"}}


def scripted(delay: float, ports=None) -> ThreadingHTTPServer:
    """An OpenAI-compatible endpoint that cites the first thing in the state pack after `delay` seconds. Given
    `ports` (a queue), it runs in this process until killed, after putting its port there."""
    class Model(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            pack = json.loads(body["messages"][1]["content"])
            refs = [x["id"] for x in pack.get("events", []) + pack.get("beliefs", [])]
            time.sleep(delay)
            content = json.dumps({"cites": refs[:1], "line": "Mind yourself, stranger."})
            reply = json.dumps({"choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                                "usage": {"prompt_tokens": 400, "completion_tokens": 20}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Model)
    server.daemon_threads = True
    server.request_queue_size = 256
    if ports is not None:
        ports.put(server.server_port)
        server.serve_forever()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class Stats:
    """What the players saw. Each client process keeps its own, and they are added up at the end."""

    def __init__(self, think: float = 0.0):
        self.think = think  # seconds an engine waits between its calls, on average: a player taking their turn
        self.ms: dict[str, list[float]] = defaultdict(list)
        self.errors: list[str] = []
        self.settle_ms: list[float] = []
        self.sources: dict[str, int] = defaultdict(int)

    def add(self, other: Stats) -> None:
        for route, xs in other.ms.items():
            self.ms[route] += xs
        self.errors += other.errors
        self.settle_ms += other.settle_ms
        for k, v in other.sources.items():
            self.sources[k] += v

    async def call(self, client: httpx.AsyncClient, route: str, method: str, url: str, **kw) -> dict:
        if self.think and route != "line (long poll)":
            await asyncio.sleep(self.think * random.uniform(0.5, 1.5))
        started = time.perf_counter()
        try:
            r = await client.request(method, url, **kw)
        except httpx.HTTPError as e:
            self.errors.append(f"{route}: {type(e).__name__}")
            return {}
        self.ms[route].append((time.perf_counter() - started) * 1000)
        if r.status_code >= 400:
            self.errors.append(f"{route}: {r.status_code} {r.text[:120]}")
            return {}
        return r.json() if r.content else {}


async def player(client: httpx.AsyncClient, stats: Stats, rounds: int) -> None:
    for _ in range(rounds):
        s = await stats.call(client, "open", "POST", "/v1/sessions", json={"game": "tavern"})
        if not s:
            return
        base = f"/v1/sessions/{s['session']}"
        await stats.call(client, "observe", "POST", f"{base}/observe", json=INSULT)
        await stats.call(client, "update", "POST", f"{base}/update", json={"npc": "garrick", "nudge": {"grudge": 4}})
        line = await stats.call(client, "decide", "POST", f"{base}/decide", json={"npc": "garrick", "moment": "turn"})
        asked = time.perf_counter() - stats.ms["decide"][-1] / 1000 if line else time.perf_counter()
        while line.get("status") == "provisional":
            line = await stats.call(client, "line (long poll)", "GET", f"{base}/lines/{line['id']}?wait=2")
        if line.get("id"):
            stats.settle_ms.append((time.perf_counter() - asked) * 1000)
            stats.sources[line["source"]] += 1
        await stats.call(client, "react", "POST", f"{base}/react", json={"npc": "wren", "trigger": "talk"})
        await stats.call(client, "tick", "POST", f"{base}/tick", json={"steps": 1})
        await stats.call(client, "narrate", "POST", f"{base}/narrate", json={"since": 0})
        await stats.call(client, "snapshot", "GET", f"{base}/snapshot")
        await stats.call(client, "close", "DELETE", base)


def pct(xs: list[float], q: int) -> float:
    return statistics.quantiles(xs, n=100, method="inclusive")[q - 1] if len(xs) > 1 else (xs[0] if xs else 0.0)


async def play(url: str, key: str, players: int, rounds: int, think: float) -> Stats:
    stats = Stats(think)
    limits = httpx.Limits(max_connections=players + 10, max_keepalive_connections=players + 10)
    async with httpx.AsyncClient(base_url=url, headers={"Authorization": f"Bearer {key}"}, limits=limits,
                                 timeout=30, trust_env=False) as client:
        await asyncio.gather(*(player(client, stats, rounds) for _ in range(players)))
    return stats


def client_process(url: str, key: str, players: int, rounds: int, think: float, start_at: float) -> Stats:
    time.sleep(max(0.0, start_at - time.time()))
    return asyncio.run(play(url, key, players, rounds, think))


def run(url: str, key: str, players: int, rounds: int, clients: int, think: float = 0.0) -> tuple[Stats, float]:
    """`players` engines, spread over `clients` processes so the load generator isn't what's measured."""
    shares = [players // clients + (i < players % clients) for i in range(clients)]
    stats = Stats()
    with ProcessPoolExecutor(clients) as pool:
        start_at = time.time() + 3  # every process starts together, once they're all up
        futures = [pool.submit(client_process, url, key, n, rounds, think, start_at) for n in shares if n]
        for f in futures:
            stats.add(f.result())
    return stats, time.time() - start_at


def report(stats: Stats, seconds: float, args: argparse.Namespace, db_kind: str) -> tuple[str, bool]:
    engine = [ms for route, xs in stats.ms.items() if route != "line (long poll)" for ms in xs]
    requests = sum(len(xs) for xs in stats.ms.values())
    p95 = pct(engine, 95)
    ok = not stats.errors and p95 <= P95_MS
    pace = (f"each engine waits {args.think * 0.5:g} to {args.think * 1.5:g} s between its calls" if args.think
            else "each engine calls as fast as it can")
    lines = [f"# Load test: {args.players} engines at once, {db_kind}", "",
             f"{args.rounds} rounds each, a scripted model answering in {args.delay * 1000:.0f} ms with "
             f"{args.concurrency} calls at once; {pace}. One server process, the engines in {args.clients} client "
             f"processes. {requests} requests in {seconds:.1f} s ({requests / seconds:.0f} a second); "
             f"{len(stats.errors)} errors.", "",
             "| Route | Calls | p50 ms | p95 ms | p99 ms |", "| --- | --- | --- | --- | --- |"]
    for route, xs in stats.ms.items():
        lines.append(f"| {route} | {len(xs)} | {pct(xs, 50):.0f} | {pct(xs, 95):.0f} | {pct(xs, 99):.0f} |")
    lines += [f"| **engine calls (all but the long poll)** | {len(engine)} | {pct(engine, 50):.0f} | **{p95:.0f}** | "
              f"{pct(engine, 99):.0f} |", "",
              f"Garrick's line, asked to final: p50 {pct(stats.settle_ms, 50):.0f} ms, p95 "
              f"{pct(stats.settle_ms, 95):.0f} ms over {len(stats.settle_ms)} lines; sources {dict(stats.sources)}.",
              "", f"Gate: no errors and engine calls p95 at most {P95_MS:.0f} ms: **{'pass' if ok else 'FAIL'}**."
              if args.think else "With no time between calls this measures what one process can take, its "
              f"capacity: {requests / seconds:.0f} requests a second. It isn't the gate."]
    ok = ok or not args.think
    if stats.errors:
        lines += ["", "Errors (first 10):", ""] + [f"- {e}" for e in stats.errors[:10]]
    return "\n".join(lines) + "\n", ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--players", type=int, default=100)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--delay", type=float, default=0.4, help="the scripted model's seconds per reply")
    parser.add_argument("--concurrency", type=int, default=32, help="model calls the server makes at once")
    parser.add_argument("--clients", type=int, default=4, help="processes the engines are spread over")
    parser.add_argument("--think", type=float, default=2.0,
                        help="seconds each engine waits between calls, on average (0: as fast as it can)")
    parser.add_argument("--db", required=True, help="the server's database: a SQLite file or postgres://...")
    parser.add_argument("--out", help="write the report here too")
    args = parser.parse_args()

    ports: multiprocessing.Queue = multiprocessing.Queue()
    model = multiprocessing.Process(target=scripted, args=(args.delay, ports), daemon=True)
    model.start()
    env = {k: v for k, v in os.environ.items() if not k.startswith("LLM_")}
    env |= {"LLM_BASE_URL": f"http://127.0.0.1:{ports.get(timeout=30)}/v1", "LLM_API_KEY": "scripted",
            "LLM_MODEL": "scripted", "LLM_PROFILE": "vllm", "LLM_CONCURRENCY": str(args.concurrency),
            "LLM_TIMEOUT": "30"}
    name = f"load-{int(time.time())}"
    made = subprocess.run([sys.executable, "-m", "thespis", "projects", "create", name, "--db", args.db],
                          cwd=ROOT, capture_output=True, text=True, check=True)
    key = made.stdout.strip().splitlines()[-1]
    server = subprocess.Popen([sys.executable, "-m", "thespis", "serve", "--server", "--db", args.db, "--port", "0",
                               "--game", str(GAME), "--no-cache"], cwd=ROOT, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
    try:
        assert server.stdout is not None
        url = server.stdout.readline().strip().partition("=")[2]
        if not url:
            raise SystemExit(server.stderr.read() if server.stderr else "the server didn't start")
        stats, seconds = run(url, key, args.players, args.rounds, args.clients, args.think)
    finally:
        server.terminate()
        server.wait(timeout=20)
        model.kill()
    text, ok = report(stats, seconds, args, "Postgres" if args.db.startswith("postgres") else "SQLite")
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
