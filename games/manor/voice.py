"""How the manor's people speak through the core (thespis.voice): their Voice, the validator's vocabulary, and their
lines.

The pack follows the same rule as every Thespis game: the model sees only what the NPC knows, never whether a belief
is true. Sable knows she took the ring; Lady Vane only knows what she has been told.
"""

from __future__ import annotations

from collections.abc import Sequence

from games.manor import content as C
from games.manor import words
from thespis.expression import StatePack, Validator
from thespis.ledger import Claim, Event
from thespis.perception import at_the_scene
from thespis.voice import Speech, Voice, reply
from thespis.world import World

__all__ = ["Speech", "reply"]

VOCABULARY = {"lady vane": C.OWNER, "vane": C.OWNER, "her ladyship": C.OWNER, "pell": C.BUTLER, "sable": C.MAID,
              **{r: r for r in C.ROOMS}}
VALIDATOR = Validator(VOCABULARY)
KNOWN_EVENTS = 5
# Lines with consequences, which meet the claim check (thespis.claims): Sable's answer about the morning, Pell's
# account of it, and what Lady Vane says of the case.
STAKES_ACTIONS = ("deceive:alibi", "deflect")
STAKES_TRIGGERS = ("asked_morning", "testify", "questioned", "questioned_sable", "accused_pell", "accused_sable")
DOES = {
    "deceive:alibi": "say you were in the kitchen at mid-morning. It isn't true: you were in the study",
    "deflect": "avoid the question without saying where you were",
}


def sees(w: World, npc: str, e: Event) -> bool:
    """Once the player is here, everyone sees what happens in their room. Before that, no one saw what they weren't
    told they saw: Pell missed the theft in his own study."""
    return e.phase >= C.ARRIVAL and at_the_scene(w, npc, e)


VOICE = Voice(
    cast=C.CAST, validator=VALIDATOR, claim_text=lambda c: words.claim_text(c, about=True),
    sentence=lambda e: words.sentence(e, about=True), who=lambda x: words.who(x, about=True),
    setting=lambda w, npc: f"You are in {C.ROOM_NAMES[w.npcs[npc].loc]} of Lady Vane's manor, which has a hall, a "
                           f"study and a kitchen. It is {C.PHASES[min(w.phase, len(C.PHASES) - 1)]}.",
    describe=lambda w, npc, action: DOES.get(action, action.replace("_", " ")), places=C.ROOMS, sees=sees,
    household=True, stakes={*STAKES_ACTIONS, *STAKES_TRIGGERS}, events=KNOWN_EVENTS)


def line(npc: str, key: str, cites: Sequence[str | None]) -> tuple[str, list[str]] | None:
    """A template line and what it cites, or None when there is no template or nothing to cite."""
    return C.CAST.line(npc, key, cites)


def knows(w: World, npc: str, event_id: str) -> bool:
    """Can this NPC cite the event? It took part, it learned of it, or it saw it (`sees`)."""
    return VOICE.knows(w, npc, event_id)


def pack_for(w: World, npc_id: str, situation: str, action: str | None = None,
             asserts: Claim | None = None, stakes: bool = False) -> StatePack:
    """Everything the model may know when it speaks for this NPC (thespis.voice.Voice.pack)."""
    return VOICE.pack(w, npc_id, situation, action, asserts, stakes=stakes)


deliver = VOICE.deliver
