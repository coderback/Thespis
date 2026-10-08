"""The manor's events and claims in words: "you" to the player, "the player" to the model."""

from __future__ import annotations

from games.manor import content as C
from thespis.ledger import Claim, Event

PRONOUNS = {"vane": "she", "pell": "he", "sable": "she"}


def who(x: str | None, about: bool = False, start: bool = False) -> str:
    if x is None:
        return ""
    if x == "player":
        text = "the player" if about else "you"
        return text[0].upper() + text[1:] if start else text
    return C.name(x)


def claim_text(c: Claim, about: bool = False, speaker: str | None = None, start: bool = True) -> str:
    """A claim as a sentence without its full stop. With a speaker, a claim about themselves uses their pronoun."""
    if speaker is not None and c.a == speaker:
        a = PRONOUNS.get(speaker) or who(speaker, about)
        a = a[0].upper() + a[1:] if start else a
    else:
        a = who(c.a, about, start)
    plural = a.lower() == "you"
    match c.pred:
        case "took":
            return f"{a} took the signet ring"
        case "was_in":
            assert c.place is not None and c.at is not None  # content.was_in always sets both
            return f"{a} {'were' if plural else 'was'} in {C.ROOM_NAMES[c.place]} at {C.PHASES[c.at]}"
    return f"{a} {c.pred.replace('_', ' ')} {c.b}"


def sentence(e: Event, about: bool = False) -> str:
    """An event in words, from cast.toml's [words.events]."""
    a, t = who(e.actor, about, start=True), who(e.target, about)
    if not C.CAST.has("words.events", e.verb):
        return f"{a} {e.verb.replace('_', ' ')} {t}".strip() + "."
    claim = claim_text(e.claim, about, speaker=e.actor, start=False) if e.claim else ""
    return C.CAST.text("words.events", e.verb, a=a, t=t, room=C.ROOM_NAMES.get(e.loc, e.loc), claim=claim,
                       to=C.ROOM_NAMES.get(e.target or "", e.target))
