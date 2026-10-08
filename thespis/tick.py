"""The tick: one phase of the world, as a pipeline of steps the game composes.

A game lists its steps in order (the player's action, decisions, gossip, moves, upkeep); `run_tick` runs them and
collects what the phase did: who moved, the events it wrote and the decisions it recorded. The core supplies the
steps every game with a map and a grapevine needs: walking, scheduled walks, and gossip.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field

from thespis.decisions import Decision
from thespis.ledger import Claim, Event
from thespis.world import World


@dataclass
class Tick:
    moves: list[dict] = field(default_factory=list)  # {"who", "from", "to"}
    decisions: list[Decision] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)


Step = Callable[[Tick], None]


def run_tick(w: World, steps: Sequence[Step]) -> Tick:
    """Run one phase's steps in order, and collect what they did."""
    start_events, start_decisions = len(w.ledger), len(w.decisions)
    tick = Tick()
    for step in steps:
        step(tick)
    tick.events = list(w.ledger)[start_events:]
    tick.decisions = list(w.decisions)[start_decisions:]
    return tick


def walk(w: World, tick: Tick, who: str, to: str) -> Event:
    """An NPC walks to `to`: the move goes in the ledger and the tick."""
    npc = w.npcs[who]
    frm, npc.loc = npc.loc, to
    tick.moves.append({"who": who, "from": frm, "to": to})
    return w.ledger.append(w.phase, "move", who, to, frm)


def walks(w: World, tick: Tick, route_of: Callable[[str], Sequence[str] | None]) -> None:
    """Everyone on a fixed route by phase of day walks to where the next phase puts them."""
    for npc in w.npcs.values():
        route = route_of(npc.id)
        if route and route[(w.phase + 1) % len(route)] != npc.loc:
            walk(w, tick, npc.id, route[(w.phase + 1) % len(route)])


def gossip(w: World, gossips: Sequence[str], about: Collection[str], priority: Mapping[str, int], threshold: float,
           decay: float, happened: Callable[[World, Claim], bool],
           hear: Callable[[World, str, Claim, float, str, Event], None]) -> None:
    """Each gossip tells each listener at its stop one thing that listener hasn't heard: the worst news it holds about
    any of `about`, then the surest. The listener believes it at the gossip's confidence times `decay`."""
    for g in gossips:
        teller = w.npcs[g]
        mine = [b for b in w.beliefs.for_npc(g)
                if b.active and b.conf >= threshold and any(b.claim.mentions(x) for x in about)]
        mine.sort(key=lambda b: (priority.get(b.claim.pred, 0), b.conf, (b.claim.pred, b.claim.a, b.claim.b)),
                  reverse=True)
        for listener in w.npcs_at(teller.loc):
            if listener.id == g:
                continue
            for b in mine:
                if w.beliefs.get(listener.id, b.claim) is None:
                    e = w.ledger.append(w.phase, "gossip", g, listener.id, teller.loc, b.claim,
                                        happened(w, b.claim))
                    hear(w, listener.id, b.claim, round(b.conf * decay, 2), g, e)
                    break
