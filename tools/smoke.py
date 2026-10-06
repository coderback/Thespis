"""Smoke test the hosted game in about a minute: run it at 07:00 and 12:45 on Sunday, and after any deploy.

    python tools/smoke.py https://thespis-production.up.railway.app

Checks, in order:
  1. The engine answers /health, and the client page and its scripts load.
  2. The Watch route plays from the cache alone: no model calls, no misses, a win on phase 5. If not, run
     tools/warm_cache.py (with REPLAY=0 on the host).
  3. Every line in that run cites ids that exist, and every decision chose from its allowed list.
  4. Every scripted route, with the brain off, ends as the rules model predicts.
  5. A session reloaded from disk is identical.
  6. The model answers a question it has never been asked: one live call. Under REPLAY=1 this is skipped.

Exits 1 if any check fails. A failed model check alone is a warning: the game still plays on the cache and templates.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from games.crypt_road.content import DEMO_SEED  # noqa: E402
from tools import warm_cache  # noqa: E402
from tools.routes import EXPECTED, ROUTES, Session, admin_headers, outcome, play, seed_for  # noqa: E402

PROBE = "Smoke test at {when}: what's the news on the road?"


def check_client(client) -> tuple[bool, str]:
    page = client.get("/")
    if page.status_code != 200 or "The Crypt Road" not in page.text:
        return False, f"GET / answered {page.status_code}; the client isn't being served"
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', page.text)
    broken = [src for src in scripts if client.get(src).status_code != 200]
    if not scripts or broken:
        return False, f"scripts not loading: {broken or 'none found'}"
    return True, f"page and {len(scripts)} script(s) load"


def check_cites(state: dict) -> tuple[bool, str]:
    ids = {e["id"] for e in state["ledger_tail"]} | {b["id"] for b in state["beliefs"]}
    bad = []
    for d in state["decisions_tail"]:
        if d["line"] and (not d["cites"] or any(c not in ids for c in d["cites"])):
            bad.append(f"{d['id']} cites {d['cites']}")
        if d["kind"] == "decide" and d["chosen"] not in d["allowed"]:
            bad.append(f"{d['id']} chose {d['chosen']}")
    lines = sum(1 for d in state["decisions_tail"] if d["line"])
    return not bad, f"{lines} lines, all cite real ids" if not bad else "; ".join(bad)


def check_reload(client, session: str) -> tuple[bool, str]:
    headers = {"X-Session": session}
    before = client.get("/state", headers=headers).json()
    after = client.post("/reload", headers=headers).json()["state"]
    return after == before, "identical after a reload from disk" if after == before else "state changed on reload"


def check_model(client, when: str) -> tuple[bool, str]:
    s = Session(client)
    s.start(DEMO_SEED, "model")
    s.act("insult", "kael")  # something to talk about
    before = client.get("/dev/calls", params={"since": 10**12}).json()["total"]
    started = time.perf_counter()
    s.act("talk", "mags", text=PROBE.format(when=when))
    took = time.perf_counter() - started
    calls = client.get("/dev/calls", params={"since": before}).json()["calls"]
    d = s.state()["decisions_tail"][-1]
    if "replay: not in the cache" in d["reason"]:
        return True, "skipped: the host has REPLAY=1"
    if d["source"] == "llm":
        return True, f"answered by {calls[-1]['provider'].rsplit('/', 1)[-1] if calls else 'the model'} in {took:.1f} s"
    return False, f"fell back ({d['reason']}); calls: {[c['error'] for c in calls] or 'none'}"


def run(client, when: str) -> list[tuple[str, bool, str]]:
    results = []

    def check(name, fn, *args):
        try:
            ok, detail = fn(*args)
        except Exception as e:  # a smoke test reports everything, then fails at the end
            ok, detail = False, f"{type(e).__name__}: {e}"
        results.append((name, ok, detail))
        return ok

    check("engine up", lambda: (client.get("/health").json() == {"ok": True}, "/health ok"))
    check("client loads", check_client, client)
    demo = {}

    def watch_route():
        demo.update(warm_cache.play(client))
        warm = demo["calls"] == 0 and demo["misses"] == 0 and demo["outcome"] == "won@5"
        return warm, (f"{demo['outcome']}, 0 model calls, lines {demo['sources']}, {demo['seconds']} s" if warm else
                      f"{demo['outcome']}, {demo['calls']} model calls, {demo['misses']} misses: run tools/warm_cache.py")
    check("Watch route from the cache", watch_route)

    def cites():
        s = Session(client)
        s.start(DEMO_SEED, "model")
        for step in warm_cache.ROUTE:
            s.act(**step)
        demo["session"] = s.session
        return check_cites(s.state())
    check("lines cite real ids", cites)

    def routes():
        wrong = []
        for name in ROUTES:
            s = Session(client)
            s.start(seed_for(name, DEMO_SEED), "fallback")
            got = outcome(play(s, name))
            if got != EXPECTED[name]:
                wrong.append(f"{name}: {got}, expected {EXPECTED[name]}")
        return not wrong, f"all {len(ROUTES)} as predicted" if not wrong else "; ".join(wrong)
    check("route outcomes", routes)
    check("reload from disk", lambda: check_reload(client, demo["session"]))
    check("model answers", check_model, client, when)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("host")
    args = parser.parse_args(argv)
    when = datetime.now(UTC).strftime("%H:%M UTC")
    with httpx.Client(base_url=args.host, timeout=60, headers=admin_headers()) as client:
        results = run(client, when)
    print(f"Smoke test of {args.host} at {when}")
    for name, ok, detail in results:
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}: {detail}")
    failed = [name for name, ok, _ in results if not ok]
    hard = [name for name in failed if name != "model answers"]
    print("PASS" if not failed else ("PASS, but the model isn't answering: the game runs on the cache and templates"
                                     if not hard else f"FAIL: {', '.join(failed)}"))
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
