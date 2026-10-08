"""The Crypt Road's vocabulary for claims (thespis.claims): what an extractor may say a line asserts, and the facts
each claim is checked against."""

from __future__ import annotations

from games.crypt_road import content as C
from thespis.claims import ClaimCheck, ClaimChecking, ClaimVocabulary, EventPred, Facts, check_for
from thespis.expression import StatePack
from thespis.gateway import ModelGateway
from thespis.world import World

VOCABULARY = ClaimVocabulary(
    game="crypt_road",
    description=C.CAST.data["claims"]["description"],
    characters=("player", "kael", "brenna", "mags", "odo"),
    places=tuple(C.STOPS),
    ledger_preds=frozenset({"insulted", "beat", "robbed", "spared", "lied"}),
    event_preds={"went_to": EventPred(("move",), "target"),
                 "told": EventPred(("accuse", "gossip", "testify", "tell_claim"), "target"),
                 "detained": EventPred(("detain",), "target"), "paid": EventPred(("bribe",), "target"),
                 "took_relic": EventPred(("take_relic",), None)},
    place_preds=frozenset({"went_to", "at"}),
    fixed_b={"took_relic": "relic"},
    aliases={"you": "player", "the player": "player", "captain": "brenna", "the captain": "brenna",
             "guard post": "guard_post", "the guard post": "guard_post"},
)


def facts(w: World, speaker: str) -> Facts:
    """What `speaker` could know of `w`, by the game's own rule (voice.knows)."""
    from games.crypt_road import rules, voice  # rules will use this module, so not at import

    return Facts(w, speaker, rules.happened, lambda event_id: voice.knows(w, speaker, event_id))


def narrator_facts(w: World) -> Facts:
    """The narrator holds no beliefs and may tell anything that happened, seen or not: it can't leak, only get things
    wrong. (Rehearsal's measure still holds it to the events it was given, as the paper did.)"""
    from games.crypt_road import rules

    return Facts(w, "narrator", rules.happened, lambda event_id: True)


def check(w: World, checking: ClaimChecking, gateway: ModelGateway) -> ClaimCheck:
    """The claim check for lines said in `w`, through the checking's own gateway or the one the lines came from."""
    def facts_for(pack: StatePack) -> Facts:
        return narrator_facts(w) if pack.npc == "narrator" else facts(w, pack.npc)

    return check_for(checking, gateway, VOCABULARY, facts_for)
