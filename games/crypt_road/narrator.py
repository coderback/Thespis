"""The Dungeon Master (#19): the model tells what happened from the ledger, and the code-built telling is the fallback.

The narrator speaks through the same Mind as the NPCs, so its tellings are cached, capped, replayed and validated the
same way: every telling must cite the events it uses and may name only who and where those events mention.
"""

from __future__ import annotations

from games.crypt_road import content as C
from games.crypt_road import words
from thespis.expression import Mind, StatePack, Utterance
from thespis.ledger import Event


def code_telling(events: list[Event]) -> str:
    return " ".join(words.sentence(e) for e in events)


def narrate(mind: Mind | None, events: list[Event]) -> tuple[str, list[str], str]:
    """The telling of `events`, the ids it cites, and where it came from: llm, cache or fallback.

    The story hook is not handed to the model (#83). The client shows it under every telling; given it as a thread
    to end on, the model repeated it, or, when the events behind it were outside the window, said it never happened.
    """
    text, ids = code_telling(events), [e.id for e in events]
    if not events or mind is None or not mind.active:
        return text, ids, "fallback"
    cast = C.load_cast()["narrator"]
    names = set(C.STOPS)
    for e in events:
        names |= {e.actor, e.target}
        if e.claim:
            names |= {e.claim.a, e.claim.b}
    situation = "Tell the player what happened since they last looked."
    pack = StatePack(
        npc="narrator", name=cast["name"], persona=cast["persona"], goal="Tell the story so far, truthfully",
        situation=situation, here=[], drives={}, trust_in={}, beliefs=[],
        events=[{"id": e.id, "what": words.sentence(e)} for e in events],
        names={x for x in names if x and x != "player"},
        setting="The road runs east: " + ", ".join(C.STOP_NAMES[s] for s in C.STOPS) + ".")
    u = mind.narrate(pack, Utterance(None, text, ids, "fallback"))
    return u.line, u.cites, u.source
