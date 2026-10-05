"""Solve the manor mystery by script over HTTP (#35), and check that two wrong turns lose.

    python tools/manor_solve.py https://thespis-production.up.railway.app

Prints every line with its source (model, cache or fallback), marks Sable's lies, and counts the model calls made.
Exits 1 unless every route ends as expected. Run against a fresh deploy, it also warms the model cache for the solve.
"""

from __future__ import annotations

import argparse
import sys

import httpx

# Ask Sable (she lies), ask Pell (he saw her leave the study), have Lady Vane question Pell, accuse Sable.
SOLVE = [("move", "kitchen", None), ("ask", "sable", "morning"), ("move", "study", None), ("ask", "pell", "morning"),
         ("move", "hall", None), ("request_questioning", "pell", None), ("accuse", "sable", None)]
# The client's "Watch the case solved" (client/src/manor/autoplay.js): the solve, after asking Lady Vane first.
WATCH = [("ask", "vane", "ring"), ("ask", "vane", "morning")] + SOLVE
ROUTES = {
    "the solve": (SOLVE, "won"),
    "the Watch route": (WATCH, "won"),
    "accuse Sable too early": ([("accuse", "sable", None)], "lost"),
    "accuse Pell": (SOLVE[:-1] + [("accuse", "pell", None)], "lost"),
}


def play(client: httpx.Client, steps: list) -> dict:
    """Play `steps` in a new session; return the final state, printing each line on the way."""
    start = client.post("/manor/session")
    start.raise_for_status()
    headers = {"X-Session": start.json()["session"]}
    state = start.json()["state"]
    for verb, target, topic in steps:
        res = client.post("/manor/act", json={"verb": verb, "target": target, "topic": topic}, headers=headers)
        if res.status_code != 200:
            raise RuntimeError(f"{verb} {target}: {res.status_code} {res.json().get('reason')}")
        out = res.json()
        state = out["state"]
        lies = {d["id"] for d in state["decisions"] if d.get("asserted")
                and not next(e for e in state["ledger"] if e["id"] == d["asserted"])["truth"]}
        for r in out["replies"]:
            mark = " [a lie, logged false]" if r["decision"] in lies else ""
            print(f"    {r['npc']:>5} [{r['source']}]{mark}: {r['line']}")
    return state


def calls(client: httpx.Client) -> int:
    return client.get("/dev/calls", params={"since": 10**9}).json()["total"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("host")
    args = parser.parse_args()
    client = httpx.Client(base_url=args.host.rstrip("/"), timeout=120)
    before, ok = calls(client), True
    for name, (steps, want) in ROUTES.items():
        print(f"{name}:")
        state = play(client, steps)
        good = state["status"] == want
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} {state['status']} at {state['clock'].lower()}: {state['outcome']}")
    print(f"{calls(client) - before} model calls")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
