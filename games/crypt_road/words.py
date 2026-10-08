"""The Crypt Road in words: ledger events and claims as English, for the digest and for NPCs' state packs.

The digest speaks to the player ("You insulted Kael"); a state pack speaks about them ("The player insulted Kael").
"""

from __future__ import annotations

from games.crypt_road import content as C
from thespis.ledger import Claim, Event

TO_PLAYER = ("You", "you")  # the digest, addressed to the player
ABOUT_PLAYER = ("The player", "the player")  # an NPC's state pack

PRONOUNS = {"kael": ("he", "him"), "brenna": ("she", "her"), "odo": ("he", "him"), "mags": ("she", "her")}
VERBS = {"robbed": "robbed", "beat": "beat", "insulted": "insulted", "spared": "spared", "lied": "lied to"}


def who(name: str | None, start: bool = False, player: tuple[str, str] = TO_PLAYER) -> str:
    if name == "player":
        return player[0] if start else player[1]
    return C.short_name(name) if name else ""


def claim_text(c: Claim, speaker: str | None = None, negate: bool = False,
               player: tuple[str, str] = TO_PLAYER) -> str:
    """A claim as words. Whoever is telling it becomes he/him or she/her: "Kael told Brenna that you robbed him"."""
    def name(x: str, subject: bool) -> str:
        if x == speaker and x in PRONOUNS:
            return PRONOUNS[x][0 if subject else 1]
        return who(x, player=player)
    verb = VERBS.get(c.pred, c.pred)
    return f"{name(c.a, True)} {'never ' if negate else ''}{verb} {name(c.b, False)}"


def sentence(e: Event, player: tuple[str, str] = TO_PLAYER) -> str:
    """An event in words, from cast.toml's [words.events]."""
    a, t = who(e.actor, start=True, player=player), who(e.target, player=player)
    key = "bribe_fine" if e.verb == "bribe" and not e.amount else e.verb
    if not C.CAST.has("words.events", key):
        if e.claim is None:
            return f"{a} {e.verb.replace('_', ' ')} {t}.".replace("  ", " ")
        key = "told"
    if e.target == "player":
        purse = "your" if player == TO_PLAYER else "the player's"
    else:
        purse = PRONOUNS.get(e.target or "", ("", "his"))[1].replace("him", "his")
    return C.CAST.text(
        "words.events", key, a=a, t=t, where=C.STOP_NAMES.get(e.loc, e.loc), amount=e.amount, purse=purse,
        to=C.STOP_NAMES.get(e.target or "", e.target), whose="your" if t == "you" else t + "'s",
        guard=who(C.GUARD, start=True), actor=who(e.actor, player=player),
        claim=claim_text(e.claim, e.actor, player=player) if e.claim else "",
        denied=claim_text(e.claim, e.actor, negate=True, player=player) if e.claim else "")
