"""How the minds hold up at town size: a few hundred people made in play, a couple of thousand events, and the
grapevine running the whole time.

  python tools/town_bench.py                       # 300 people, 2,000 events, 200 ticks
  python tools/town_bench.py --people 1000 --events 5000
  python tools/town_bench.py --check               # fail if a budget is missed (CI)

It plays examples/town/game.toml with more places: people are added, tied to kin and friends, robbed, threatened and
lied about; some die. Every tenth event the town's time moves on a tick. It reports what one of each call costs, and
what the save has grown to. No model is asked: this measures the minds' own work.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from thespis.api import Game, Session  # noqa: E402

TOWN = ROOT / "examples" / "town" / "game.toml"
HOUSEHOLD = 5  # people to a place
# What one call may cost on a CI runner, in milliseconds (p95), and the save in megabytes, at the default size.
# Set from this laptop's numbers with room for a slower machine; a change that misses one has made something scan.
BUDGET = {"add": 2.0, "observe": 5.0, "decide": 5.0, "tick": 150.0, "snapshot": 500.0, "restore": 900.0,
          "save_mb": 8.0}


def town(people: int) -> Game:
    """The example town, with enough places to house everyone."""
    places = "".join(f'p{i:03d} = "place {i}"\n' for i in range(max(1, people // HOUSEHOLD)))
    text = re.sub(r"\[places\]\n(?:.+\n)+", "[places]\n" + places, TOWN.read_text(encoding="utf-8"), count=1)
    return Game.parse(text, "town")


def play(people: int, events: int, ticks: int, seed: int = 0) -> tuple[dict[str, list[float]], Session]:
    """Play the town and time every call, in milliseconds, by kind of call. Returns the times (and the save's size
    in megabytes, as `save_mb`), and the town as it ended."""
    rng = random.Random(seed)
    game = town(people)
    places = list(game.places)
    s = Session.new(game, seed)
    took: dict[str, list[float]] = {k: [] for k in ("add", "observe", "decide", "tick", "snapshot", "restore")}

    def timed(kind: str, fn):
        t0 = time.perf_counter()
        out = fn()
        took[kind].append((time.perf_counter() - t0) * 1000)
        return out

    ids = [f"n{i:04d}" for i in range(people)]
    for i, npc in enumerate(ids):
        timed("add", lambda: s.add(npc, "guard" if i % 20 == 0 else "townsfolk", f"Person {i}", places[i % len(places)]))
    for i, npc in enumerate(ids):  # a household is kin; everyone has two friends elsewhere
        if (i + len(places)) < people:
            s.tie(npc, ids[i + len(places)], "kin")
        for other in rng.sample(ids, 2):
            if other != npc and not any({a, b} == {npc, other} for a, b, _ in s.world.ties[-4:]):
                try:
                    s.tie(npc, other, "friend")
                except Exception:
                    pass
        s.update(npc, trust_in={o: 3 for o, _ in s._ties().get(npc, [])})  # noqa: SLF001  (a bench may look inside)

    every = max(1, events // max(1, ticks))
    for n in range(events):
        living = [i for i in ids if i not in s.world.gone]
        target = rng.choice(living)
        at = s.world.npcs[target].loc
        here = [x.id for x in s.world.npcs_at(at) if x.id != target]
        roll = rng.random()
        if roll < 0.5:  # the player wrongs someone, in front of whoever is there
            pred, verb = rng.choice((("robbed", "rob"), ("threatened", "threaten")))
            s.update("player", loc=at)
            timed("observe", lambda: s.observe(verb, "player", target, at=at, claim={"pred": pred, "a": "player",
                                                                                     "b": target}, witnesses=here))
        elif roll < 0.8:  # the player blames someone else for a robbery, to whoever is there
            victim, blamed = rng.sample(living, 2)
            claim = {"pred": "robbed", "a": blamed, "b": victim}
            timed("observe", lambda: s.observe("tell", "player", target, at=at, claim=claim, said=True,
                                               witnesses=here))
        elif roll < 0.97:  # someone meets the player
            s.update("player", loc=at)
            timed("decide", lambda: s.decide(target, "meet", {"who": "player"}))
        else:  # someone dies
            timed("observe", lambda: s.observe("kill", "player", target, at=at, claim={"pred": "killed", "a": "player",
                                                                                       "b": target}, witnesses=here))
            s.retire(target)
        if n % every == every - 1:
            timed("tick", s.tick)
    snap = ""
    for _ in range(5):  # as an engine saves and loads: to text and back
        snap = timed("snapshot", lambda: json.dumps(s.snapshot()))
        timed("restore", lambda: Session.restore(game, json.loads(snap)))
    took["save_mb"] = [len(snap) / 1e6]
    return took, s


def p95(xs: list[float]) -> float:
    return sorted(xs)[min(len(xs) - 1, int(len(xs) * 0.95))]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--people", type=int, default=300)
    ap.add_argument("--events", type=int, default=2000)
    ap.add_argument("--ticks", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--check", action="store_true", help="fail if a budget is missed")
    args = ap.parse_args()
    t0 = time.perf_counter()
    took, s = play(args.people, args.events, args.ticks, args.seed)
    ledger, beliefs = len(s.world.ledger), len(s.world.beliefs.all())
    print(f"{args.people} people, {args.events} events, {len(took['tick'])} ticks: {ledger} ledger events, "
          f"{beliefs} beliefs, {time.perf_counter() - t0:.1f} s in all")
    print(f"{'call':<10}{'n':>7}{'p50 ms':>10}{'p95 ms':>10}{'budget':>10}")
    missed = []
    for kind, xs in took.items():
        if not xs:
            continue
        worst = p95(xs)
        budget = BUDGET[kind]
        if kind == "save_mb":
            print(f"{'save':<10}{'':>7}{'':>10}{worst:>8.2f}MB{budget:>8.1f}MB")
        else:
            print(f"{kind:<10}{len(xs):>7}{statistics.median(xs):>10.2f}{worst:>10.2f}{budget:>10.1f}")
        if worst > budget:
            missed.append(kind)
    if missed:
        print("over budget: " + ", ".join(missed))
    return 1 if args.check and missed else 0


if __name__ == "__main__":
    raise SystemExit(main())
