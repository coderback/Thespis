"""The Crypt Road's story hooks (#19): arcs the director sifts from the ledger, for the Dungeon Master to end on.

Importing this module registers them with the core's registry (thespis/director.py).
"""

from __future__ import annotations

from games.crypt_road import content as C
from games.crypt_road.words import claim_text, who
from thespis.director import Hook, register
from thespis.ledger import Event
from thespis.world import World

GRUDGE = 5  # Kael's grudge from here on is a story worth telling


def _lies(w: World) -> list[Event]:
    return [e for e in w.ledger if e.verb == "tell_claim" and e.actor == "player" and not e.truth]


@register("revenge_brewing")
def revenge_brewing(w: World) -> Hook | None:
    if w.npcs[C.RIVAL].drives.get("grudge", 0) < GRUDGE:
        return None
    offences = [e.id for e in w.ledger if e.claim and e.truth and e.claim.a == "player" and e.claim.b == C.RIVAL]
    accused = [e.id for e in w.ledger if e.verb == "accuse" and e.actor == C.RIVAL]
    rival = C.short_name(C.RIVAL)
    text = (f"Revenge is brewing: {rival} took his grudge to the Captain." if accused
            else f"Revenge is brewing: {rival} won't forget what you did.")
    return Hook("revenge_brewing", text, tuple(offences + accused))


@register("lie_told")
def lie_told(w: World) -> Hook | None:
    lies = _lies(w)
    if not lies:
        return None
    lie = lies[-1]
    return Hook("lie_told", f"A lie is loose: you told {who(lie.target)} that {claim_text(lie.claim)}, and it never "
                            "happened.", (lie.id,))


@register("lie_exposed")
def lie_exposed(w: World) -> Hook | None:
    lies = {e.claim: e for e in _lies(w)}
    for e in w.ledger:
        if e.verb == "testify" and e.claim in lies:
            told = claim_text(e.claim, speaker=e.actor, negate=True)
            return Hook("lie_exposed", f"The lie is out: {who(e.actor, start=True)} told {who(e.target)} that "
                                       f"{told}.", (lies[e.claim].id, e.id))
    return None


PRIORITY = ("lie_exposed", "lie_told", "revenge_brewing")  # the strongest thread wins when several are live
