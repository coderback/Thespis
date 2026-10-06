"""Warm the model cache on a host by playing the client's autoplay route, and check that it replays.

    python tools/warm_cache.py https://thespis-production.up.railway.app            # two runs
    python tools/warm_cache.py https://thespis-production.up.railway.app --runs 1   # e.g. after setting REPLAY=1

Each run starts a fresh session on the demo seed with the brain on, and plays the same steps as the client's
"Watch" button, fetching the Dungeon Master's digests when the client does. It reports how many model calls the run
made (a line or a digest from the model, or a fallback the model caused), where every line came from, and whether it
said exactly what the run before it said. A warm cache shows 0 calls and the same lines. Re-run it after any change to
what the model is shown: a persona, a prompt, the state pack, or the autoplay steps.

Exits 1 unless the last run made no model calls, missed the cache nowhere (under REPLAY=1 a miss falls back without
a call, so it looks free), won on phase 5, and said what the run before it said.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.routes import admin_headers, fresh_session  # noqa: E402

DEMO_SEED = 1
# client/src/autoplay.js's steps, in order. tests/test_warm_cache.py fails if the two drift apart.
ROUTE = [
    {"verb": "insult", "target": "kael"},
    {"verb": "challenge", "target": "kael"},
    {"verb": "humiliate", "target": "kael"},
    {"verb": "talk", "target": "mags", "text": "Where did Kael go?"},
    {"verb": "move"},
    {"verb": "move"},
    {"verb": "bribe", "target": "brenna", "amount": 20},
    {"verb": "bribe", "target": "brenna", "amount": 20},
    {"verb": "tell_claim", "target": "brenna", "claim": {"pred": "robbed", "a": "kael", "b": "odo"}},
    {"verb": "move"},
    {"verb": "move"},
    {"verb": "take_relic"},
]
MODEL_FAULTS = ("model unavailable", "model reply rejected")  # fallbacks that cost a model call
REPLAY_MISS = "replay: not in the cache"


def model_calls(decisions: list[dict]) -> int:
    return sum(d["source"] == "llm" or (d["source"] == "fallback" and any(f in d["reason"] for f in MODEL_FAULTS))
               for d in decisions)


def play(client) -> dict:
    """One run of the route on a new session. `client` is an httpx.Client, or a TestClient, for the host."""
    headers = {"X-Session": fresh_session(client, DEMO_SEED)}
    logged = client.get("/dev/calls", params={"since": 10**12}).json()["total"]  # the host's own count of model calls
    started = time.perf_counter()
    digests, phase = [], 0
    for step in ROUTE:
        r = client.post("/act", json=step, headers=headers)
        r.raise_for_status()
        if r.json()["tick"] is not None:  # as the client does: ask the Dungeon Master after every tick
            digests.append(client.get("/digest", params={"since": phase}, headers=headers).json())
        phase = r.json()["state"]["phase"]
    state = client.get("/state", headers=headers).json()
    if state["ended_at"] is not None:  # and once more for the end card
        digests.append(client.get("/digest", params={"since": state["ended_at"]}, headers=headers).json())
    elapsed = time.perf_counter() - started
    decisions = state["decisions_tail"]
    assert decisions[0]["id"] == "d0001", "the route made more decisions than the state's tail holds"
    tellings = [(d["source"], d["text"]) for d in digests] + \
        [(d["epilogue_source"], d["epilogue"]) for d in digests if d["epilogue"] is not None]
    model_on = any(d["source"] in ("llm", "cache") for d in decisions if d["line"])
    return {
        "outcome": f"{state['status']}@{state['ended_at']}",
        # The host's log also catches calls whose reply was rejected, which look free from the sources alone.
        "calls": max(model_calls(decisions) + sum(source == "llm" for source, _ in tellings),
                     client.get("/dev/calls", params={"since": 10**12}).json()["total"] - logged),
        "misses": sum(REPLAY_MISS in d["reason"] for d in decisions)
                  + (sum(source == "fallback" for source, _ in tellings) if model_on else 0),
        "sources": dict(Counter(d["source"] for d in decisions if d["line"])),
        "tellings": dict(Counter(source for source, _ in tellings)),
        "said": [(d["npc"], d["chosen"], d["line"]) for d in decisions] + [text for _, text in tellings],
        "faults": [f"{d['id']} {d['npc']}: {d['reason']}" for d in decisions
                   if d["source"] == "fallback" and any(f in d["reason"] for f in (*MODEL_FAULTS, REPLAY_MISS))],
        "seconds": round(elapsed, 1),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("host")
    parser.add_argument("--runs", type=int, default=2)
    args = parser.parse_args(argv)
    runs = []
    with httpx.Client(base_url=args.host, timeout=60, headers=admin_headers()) as client:
        for n in range(1, args.runs + 1):
            run = play(client)
            same = runs and run["said"] == runs[-1]["said"]
            print(f"run {n}: {run['outcome']}, {run['calls']} model calls, {run['misses']} replay misses, "
                  f"lines {run['sources']}, digests {run['tellings']}, {run['seconds']} s"
                  + ("" if not runs else ", same lines as the run before" if same else ", DIFFERENT lines"))
            for fault in run["faults"]:
                print("   ", fault)
            run["same"] = same
            runs.append(run)
    last = runs[-1]
    ok = last["calls"] == 0 and last["misses"] == 0 and last["outcome"] == "won@5" and (len(runs) == 1 or last["same"])
    print("warm: the last run made no model calls and missed the cache nowhere" if ok else "NOT warm yet")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
