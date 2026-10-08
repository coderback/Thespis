"""Checks that need no judge: what a line says about who spoke, held to the ledger as the line's speaker knew it.

- **Words in the player's mouth:** a line that says the player said something ("you told me", "you swore") when the
  speaker knows of nothing the player said. Ember Table's review found NPCs quoting players who never spoke; a judge
  that extracts claims can miss it, since "you told me X" often reads as X.
- **Who spoke, in narration:** the narrator says someone spoke ("Kael told the Captain...") when none of the events it
  was given has that person speaking.

Both run on every model line, not a sample, so their rates have no judge in them. They're pattern checks: they catch
the common phrasings, not every way of putting it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from thespis.world import World

# Verbs that put words in someone's mouth, as the line says them about the player ("you") or about a character.
_SAID = r"(?:said|told|tell|claimed|asked|promised|swore|admitted|confessed|insisted|accused|offered|lied|testified)"
YOU_SAID = re.compile(rf"\byou(?:'ve| have)? {_SAID}\b|\byour (?:words|claim|story|promise|offer)\b", re.I)
NAMED_SAID = re.compile(rf"\b([A-Z][a-z]+(?: [A-Z][a-z]+)?) (?:had |has )?{_SAID}\b")
# Ledger verbs where the actor speaks: what the player or a character said, offered, asked or accused.
SPEECH = frozenset({"tell", "tell_claim", "talk", "ask", "offer", "accuse", "testify", "gossip", "counter", "refuse",
                    "bribe", "question", "insult"})


def _spoke(w: World, who: str, event_ids: set[str] | None = None) -> bool:
    """Did `who` say anything, among `event_ids` (or anywhere in the ledger)?"""
    return any(e.actor == who and (e.verb in SPEECH or e.claim is not None)
               for e in w.ledger if event_ids is None or e.id in event_ids)


def player_words(line: str, w: World, known: set[str]) -> bool:
    """The line says the player said something, and the speaker knows of nothing the player said."""
    return bool(YOU_SAID.search(line)) and not _spoke(w, "player", known)


def misattributed(line: str, w: World, told: set[str], names: Mapping[str, str]) -> list[str]:
    """The characters the narration says spoke, though none of the events it was told has them speaking."""
    out = []
    for m in NAMED_SAID.finditer(line):
        who = names.get(m.group(1).lower())
        if who and not _spoke(w, who, told):
            out.append(who)
    return out


def known_events(sample: dict, w: World, knows) -> set[str]:
    return {e.id for e in w.ledger if knows(e.id)}


def flags(sample: dict, w: World, knows, names: Mapping[str, str]) -> list[str]:
    """Which of these checks the line fails."""
    line = sample.get("line") or ""
    out = []
    if sample["npc"] == "narrator":
        told = set(sample["ids"])
        if player_words(line, w, told):
            out.append("player_words")
        if misattributed(line, w, told, names):
            out.append("attribution")
    elif player_words(line, w, known_events(sample, w, knows)):
        out.append("player_words")
    return out
