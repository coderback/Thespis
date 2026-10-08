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
    a, t = who(e.actor, about, start=True), who(e.target, about)
    room = C.ROOM_NAMES.get(e.loc, e.loc)
    match e.verb:
        case "take":
            return f"{a} took the signet ring from {room}."
        case "leave":
            return f"{a} left {room}."
        case "tell" | "testify":
            return f"{a} told {t} that {claim_text(e.claimed, about, speaker=e.actor, start=False)}."
        case "arrive":
            return f"{a} arrived at the manor."
        case "move":
            return f"{a} walked from {room} to {C.ROOM_NAMES.get(e.target or '', e.target)}."
        case "question":
            return f"{a} questioned {t} in {room}."
        case "accuse":
            return f"{a} accused {t} before Lady Vane."
        case "constable":
            return f"{a} sent for the constable."
    return f"{a} {e.verb.replace('_', ' ')} {t}".strip() + "."
