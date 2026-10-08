"""The Dungeon Master (#19): the model tells what happened from the ledger, and the code-built telling is the fallback.

The narrator speaks through the same Mind as the NPCs (thespis.voice.Voice.narrate), so its tellings are cached,
capped, replayed and validated the same way. The story hook is not handed to the model (#83): the client shows it
under every telling, and given it as a thread to end on, the model repeated it, or, when the events behind it were
outside the window, said it never happened.
"""

from __future__ import annotations

from games.crypt_road import content as C
from games.crypt_road import voice, words
from thespis.expression import Mind
from thespis.ledger import Event


def code_telling(events: list[Event]) -> str:
    return " ".join(words.sentence(e) for e in events)


def narrate(mind: Mind | None, events: list[Event]) -> tuple[str, list[str], str]:
    """The telling of `events`, the ids it cites, and where it came from: llm, cache or fallback."""
    setting = "The road runs east: " + ", ".join(C.STOP_NAMES[s] for s in C.STOPS) + "."
    return voice.VOICE.narrate(mind, events, setting, code_telling)
