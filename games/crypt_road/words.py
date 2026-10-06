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
    a, t = who(e.actor, start=True, player=player), who(e.target, player=player)
    where = C.STOP_NAMES.get(e.loc, e.loc)
    match e.verb:
        case "insult":
            return f"{a} insulted {t} at {where}."
        case "challenge":
            return f"{a} challenged {t} to a duel."
        case "beat":
            return f"{a} beat {t} in the duel."
        case "humiliate":
            if e.target == "player":
                purse = "your" if player == TO_PLAYER else "the player's"
            else:
                purse = PRONOUNS.get(e.target or "", ("", "his"))[1].replace("him", "his")
            return f"{a} humiliated {t} and took {purse} purse."
        case "spare":
            return f"{a} spared {t}."
        case "bribe":
            return f"{a} paid {t} {e.amount} coins." if e.amount else f"{a} paid {t} a fine."
        case "offer":
            return f"{a} offered {t} {e.amount} coins."
        case "counter":
            return f"{a} asked {t} for {e.amount} coins."
        case "refuse":
            return f"{a} turned down {'your' if t == 'you' else t + chr(39) + 's'} offer."
        case "move":
            return f"{a} walked from {where} to {C.STOP_NAMES.get(e.target or '', e.target)}."
        case "block":
            return f"{who(C.GUARD, start=True)} turned {who(e.actor, player=player)} back at the gate."
        case "detain":
            return f"{a} detained {t}."
        case "release":
            return f"{a} released {t}."
        case "testify":
            return f"{a} told {t} that {claim_text(e.claimed, e.actor, negate=True, player=player)}."
        case "take_relic":
            return f"{a} took the relic."
        case _ if e.claim is not None:  # tell_claim, accuse, gossip
            return f"{a} told {t} that {claim_text(e.claim, e.actor, player=player)}."
    return f"{a} {e.verb.replace('_', ' ')} {t}.".replace("  ", " ")
