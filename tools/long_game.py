"""How the minds hold up over a long game: a small town, tens of thousands of events, the same few deeds and lies told
again and again. A call should cost the same at the end of a long game as at the start.

  python tools/long_game.py                   # 30 people, 20,000 events
  python tools/long_game.py --events 50000
  python tools/long_game.py --check           # fail unless the last block's observe is within 1.5x the first's

It prints, for each block of 2,000 events, the median time of an observe and of a tick, the most evidence any one
belief holds, and how many beliefs there are; then the save's size. No model is asked.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from thespis.api import Session  # noqa: E402
from tools.town_bench import town  # noqa: E402

BLOCK = 2000
STEADY = 1.5  # the last block's observe may cost at most this much more than the first's


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--people", type=int, default=30)
    ap.add_argument("--events", type=int, default=20_000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--check", action="store_true", help="fail unless the time per observe holds steady")
    o = ap.parse_args()
    rng = random.Random(o.seed)
    game = town(o.people)
    places = list(game.places)
    s = Session.new(game, o.seed)
    ids = [f"n{i:03d}" for i in range(o.people)]
    for i, npc in enumerate(ids):
        s.add(npc, "guard" if i % 10 == 0 else "townsfolk", f"Person {i}", places[i % len(places)])
    for i, npc in enumerate(ids):  # a ring of friends, each trusting both neighbours
        s.tie(npc, ids[(i + 1) % o.people], "friend")
        s.update(npc, trust_in={ids[(i + 1) % o.people]: 3, ids[(i - 1) % o.people]: 3})
    few = ids[:8]  # the same few lies, told again and again
    obs: list[float] = []
    ticks: list[float] = []
    blocks: list[float] = []
    print(f"{'events':>7} {'observe ms':>11} {'tick ms':>8} {'max evidence':>13} {'beliefs':>8}")
    for n in range(1, o.events + 1):
        target = rng.choice(ids)
        at = s.world.npcs[target].loc
        here = [x.id for x in s.world.npcs_at(at) if x.id != target]
        t0 = time.perf_counter()
        if rng.random() < 0.6:
            s.update("player", loc=at)
            s.observe("rob", "player", target, at=at, claim={"pred": "robbed", "a": "player", "b": target},
                      witnesses=here)
        else:
            victim, blamed = rng.sample(few, 2)
            s.observe("tell", "player", target, at=at, claim={"pred": "robbed", "a": blamed, "b": victim}, said=True,
                      witnesses=here)
        obs.append((time.perf_counter() - t0) * 1000)
        if n % 10 == 0:
            t0 = time.perf_counter()
            s.tick()
            ticks.append((time.perf_counter() - t0) * 1000)
        if n % BLOCK == 0:
            bs = s.world.beliefs.all()
            blocks.append(statistics.median(obs))
            print(f"{n:>7} {blocks[-1]:>11.3f} {statistics.median(ticks):>8.2f} "
                  f"{max(len(b.evidence) for b in bs):>13} {len(bs):>8}", flush=True)
            obs, ticks = [], []
    print(f"save {len(json.dumps(s.snapshot())) / 1e6:.1f} MB, ledger {len(s.world.ledger)} events")
    if o.check and len(blocks) >= 2 and blocks[-1] > STEADY * blocks[0]:
        print(f"observe went from {blocks[0]:.3f} ms to {blocks[-1]:.3f} ms: not steady", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
