"""Warm the model cache on a host by playing the client's autoplay route, and check that it replays.

    python tools/warm_cache.py https://thespis-production.up.railway.app            # two runs
    python tools/warm_cache.py https://thespis-production.up.railway.app --runs 1   # e.g. after setting REPLAY=1

Each run starts a fresh session on the demo seed with the brain on, and plays the same steps as the client's
"Watch" button. It reports how many model calls the run made (a line from the model, or a fallback the model
caused), where every line came from, and whether it said exactly what the run before it said. A warm cache shows
0 calls and the same lines. Re-run it after any change to what the model is shown: a persona, a prompt, the state
pack, or the autoplay steps.

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

from tools.routes import fresh_session  # noqa: E402

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
    started = time.perf_counter()
    for step in ROUTE:
        client.post("/act", json=step, headers=headers).raise_for_status()
    elapsed = time.perf_counter() - started
    state = client.get("/state", headers=headers).json()
    decisions = state["decisions_tail"]
    assert decisions[0]["id"] == "d0001", "the route made more decisions than the state's tail holds"
    return {
        "outcome": f"{state['status']}@{state['ended_at']}",
        "calls": model_calls(decisions),
        "misses": sum(REPLAY_MISS in d["reason"] for d in decisions),
        "sources": dict(Counter(d["source"] for d in decisions if d["line"])),
        "said": [(d["npc"], d["chosen"], d["line"]) for d in decisions],
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
    with httpx.Client(base_url=args.host, timeout=60) as client:
        for n in range(1, args.runs + 1):
            run = play(client)
            same = runs and run["said"] == runs[-1]["said"]
            print(f"run {n}: {run['outcome']}, {run['calls']} model calls, {run['misses']} replay misses, "
                  f"lines {run['sources']}, {run['seconds']} s"
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
