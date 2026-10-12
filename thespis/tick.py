"""The tick: one phase of the world, as a pipeline of steps the game composes.

A game lists its steps in order (the player's action, decisions, gossip, moves, upkeep); `run_tick` runs them and
collects what the phase did: who moved, the events it wrote and the decisions it recorded. The core supplies the
steps every game with a map and a grapevine needs: walking, scheduled walks, and gossip, either among whoever
shares a stop (`gossip`) or along ties between people, wherever they are (`spread`).
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


def _about(claim: Claim, about: Collection[str] | None) -> bool:
    """Is the claim news of anyone in `about`? None: any news is."""
    return about is None or any(claim.mentions(x) for x in about)


def gossip(w: World, gossips: Sequence[str], about: Collection[str] | None, priority: Mapping[str, int],
           threshold: float, decay: float, happened: Callable[[World, Claim], bool],
           hear: Callable[[World, str, Claim, float, str, Event], None]) -> None:
    """Each gossip tells each listener at its stop one thing that listener hasn't heard: the worst news it holds about
    any of `about` (None: about anyone), then the surest. The listener believes it at the gossip's confidence times
    `decay`. Nobody is told what they did themselves: they know."""
    for g in gossips:
        teller = w.npcs[g]
        mine = [b for b in w.beliefs.for_npc(g)
                if b.active and b.conf >= threshold and _about(b.claim, about)]
        mine.sort(key=lambda b: (priority.get(b.claim.pred, 0), b.conf, (b.claim.pred, b.claim.a, b.claim.b)),
                  reverse=True)
        for listener in w.npcs_at(teller.loc):
            if listener.id == g:
                continue
            for b in mine:
                if b.claim.a != listener.id and w.beliefs.get(listener.id, b.claim) is None:
                    e = w.ledger.append(w.phase, "gossip", g, listener.id, teller.loc, b.claim,
                                        happened(w, b.claim))
                    hear(w, listener.id, b.claim, round(b.conf * decay, 2), g, e)
                    break


def spread(w: World, tellers: Sequence[str], listeners: Callable[[str], Sequence[tuple[str, float]]],
           about: Collection[str] | None, priority: Mapping[str, int], threshold: float,
           happened: Callable[[World, Claim], bool], hear: Callable[[World, str, Claim, float, str, Event], None],
           trust: Callable[[str, str], float]) -> None:
    """Gossip along ties. Each teller tells each of its `listeners` (with how much of a report carries to each) one
    thing that listener hasn't heard: the worst news it holds about any of `about` (None: about anyone), then the
    surest. The listener believes it as subjective logic discounts a report (Jøsang 2016, trust discounting): the
    teller's confidence, times how far the listener trusts the teller (`trust(listener, teller)`), times what carries
    along the tie. So a story weakens with every mouth it passes through, and stops once nobody holds it surely
    enough to pass it on. Each teller tells what it knew as the tick began, so a story travels one tie per tick.
    Nobody is told what they did themselves: they know."""
    known: dict[str, list[tuple[Claim, float]]] = {}
    for g in tellers:
        mine = [b for b in w.beliefs.for_npc(g)
                if b.active and b.conf >= threshold and _about(b.claim, about)]
        mine.sort(key=lambda b: (priority.get(b.claim.pred, 0), b.conf, (b.claim.pred, b.claim.a, b.claim.b)),
                  reverse=True)
        known[g] = [(b.claim, b.conf) for b in mine]
    for g in tellers:
        teller = w.npcs[g]
        for listener, carry in listeners(g):
            for claim, conf in known[g]:
                if claim.a != listener and w.beliefs.get(listener, claim) is None:
                    # Told face to face, it happened where they stand; along a tie between people apart, nowhere
                    # anyone else could overhear it.
                    where = teller.loc if w.npcs[listener].loc == teller.loc else ""
                    e = w.ledger.append(w.phase, "gossip", g, listener, where, claim, happened(w, claim))
                    hear(w, listener, claim, round(conf * trust(listener, g) * carry, 2), g, e)
                    break
