"""Perception: who knows which events, and who witnesses a claim as it happens.

A game supplies one rule, `sees(world, npc, event)`: whether an NPC saw an event it took no part in. The core
applies it to every event. An NPC knows an event when it took part (actor or target), when it learned of it (an
event that delivered evidence it holds), or when it saw it.
"""

from __future__ import annotations

from collections.abc import Callable, Collection

from thespis.ledger import Claim, Event
from thespis.world import World

Sees = Callable[[World, str, Event], bool]
Give = Callable[[World, str, Claim, float, str, Event], None]  # (world, npc, claim, conf, source, event)


def at_the_scene(w: World, npc: str, e: Event) -> bool:
    """The usual rule: an NPC sees what happens where it stands, and arrivals where it stands."""
    return w.npcs[npc].loc in (e.loc, e.target)


def knows(w: World, npc: str, event_id: str, sees: Sees = at_the_scene) -> bool:
    """Can this NPC cite the event? It took part, it learned of it, or it saw it."""
    e = w.ledger.get(event_id)
    if npc in (e.actor, e.target):
        return True
    if any(ev.event == event_id for b in w.beliefs.for_npc(npc) for ev in b.evidence):
        return True
    return sees(w, npc, e)


def known(w: World, npc: str, n: int, sees: Sees = at_the_scene, hidden: Collection[str] = ()) -> list[Event]:
    """The last `n` events the NPC knows, oldest first, leaving out any still `hidden` from it."""
    return [e for e in reversed(list(w.ledger)) if e.id not in hidden and knows(w, npc, e.id, sees)][:n][::-1]


def latest(w: World, npc: str, sees: Sees = at_the_scene) -> str | None:
    """The most recent event the NPC knows, for a line with nothing better to cite."""
    return next((e.id for e in reversed(list(w.ledger)) if knows(w, npc, e.id, sees)), None)


def witness(w: World, claim: Claim, actor: str, target: str, event: Event, at: str, give: Give) -> None:
    """Everyone at `at` sees the claim happen, certain of it; the actor and target know it first-hand."""
    for npc in w.npcs_at(at):
        if npc.id not in (actor, target):
            give(w, npc.id, claim, 1.0, "witnessed", event)
    for who in (actor, target):
        if who in w.npcs:
            give(w, who, claim, 1.0, "self", event)
