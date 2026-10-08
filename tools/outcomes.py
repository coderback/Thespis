"""Every route's outcome, so a change that should change nothing can be shown to change nothing.

Plays all 35 routes with the brain off: the crypt road's routes (tools.routes) on seeds 1, 2 and 4, and every manor
route (rehearsal.scenarios). For each it records the status and end phase, the player, every NPC's place, drives,
trust and hold, the ledger's event sequence, the decisions, and every belief's confidence and status.

tests/test_outcomes.py compares them with tests/outcomes.json. When a change means to alter what happens, see the
difference, then record the new outcomes:

    python -m tools.outcomes            # print what differs from tests/outcomes.json
    python -m tools.outcomes --update   # record the outcomes as they are now
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rehearsal.scenarios import MANOR_ROUTES, Stage
from thespis.world import World
from tools.routes import ROUTES, ApiError, play, seed_for

BASELINE = Path(__file__).resolve().parents[1] / "tests" / "outcomes.json"
SEEDS = (1, 2, 4)
OUTCOME = ("outcome", "player", "npcs", "events", "decisions")  # what may not move; "beliefs" are compared too


def fingerprint(w: World) -> dict:
    return {
        "outcome": f"{w.status}@{w.ended_at}",
        "player": {k: v for k, v in w.player.items() if k != "outcome"} | {"outcome": w.player.get("outcome")},
        "npcs": {n.id: {"loc": n.loc, "drives": n.drives, "trust": n.trust_in, "frozen_until": n.frozen_until}
                 for n in w.npcs.values()},
        "events": [[e.verb, e.actor, e.target, e.truth, e.amount] for e in w.ledger],
        "decisions": [[d.npc, d.trigger, d.chosen] for d in w.decisions],
        "beliefs": {f"{b.npc} {json.dumps(b.claim.to_json(), sort_keys=True)}": [round(b.conf, 4), b.status]
                    for b in w.beliefs.all()},
    }


def outcomes() -> dict[str, dict]:
    out = {}
    for name in ROUTES:
        for seed in SEEDS:
            s = Stage(None, brain="fallback").crypt_road(seed_for(name, seed))
            try:
                play(s, name)
            except ApiError:
                pass  # a route that ends early ends where it ends
            out[f"crypt_road/{name}/{seed}"] = fingerprint(s.w)
    for name, steps in MANOR_ROUTES.items():
        m = Stage(None, brain="fallback").manor()
        for verb, target, topic in steps:
            if m.w.status != "playing":
                break
            m.act(verb, target, topic)
        out[f"manor/{name}"] = fingerprint(m.w)
    return out


def differences(was: dict, now: dict) -> list[str]:
    """Every way `now` differs from `was`, route by route: outcomes first, then belief values."""
    out = [f"{route}: {'gone' if route in was else 'new'}" for route in sorted(set(was) ^ set(now))]
    for route in sorted(set(was) & set(now)):
        for key in OUTCOME:
            if was[route][key] != now[route][key]:
                out.append(f"{route} {key}:\n  was {was[route][key]}\n  now {now[route][key]}")
        a, b = was[route]["beliefs"], now[route]["beliefs"]
        out += [f"{route} belief {k}: was {a.get(k)}, now {b.get(k)}" for k in sorted(set(a) | set(b))
                if a.get(k) != b.get(k)]
    return out


def dump(out: dict) -> str:
    return json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--update", action="store_true", help="record the outcomes as they are now")
    args = parser.parse_args()
    now = outcomes()
    if args.update:
        BASELINE.write_bytes(dump(now).encode())
        print(f"recorded {len(now)} routes in {BASELINE.name}")
        return 0
    diff = differences(json.loads(BASELINE.read_text(encoding="utf-8")), now)
    print("\n".join(diff) if diff else f"{len(now)} routes; nothing differs")
    return 1 if diff else 0


if __name__ == "__main__":
    raise SystemExit(main())
