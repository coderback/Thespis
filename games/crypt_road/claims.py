"""The Crypt Road's vocabulary for claims (thespis.claims): what an extractor may say a line asserts, and the facts
each claim is checked against."""

from __future__ import annotations

from games.crypt_road import content as C
from thespis.claims import ClaimCheck, ClaimChecking, ClaimVocabulary, EventPred, Facts
from thespis.expression import StatePack
from thespis.gateway import ModelGateway
from thespis.world import World

VOCABULARY = ClaimVocabulary(
    game="crypt_road",
    description=(
        "Predicates (a and b are ids):\n"
        "- insulted(a, b); beat(a, b): a beat b in a duel; robbed(a, b): a robbed b or took b's purse; spared(a, b); "
        "lied(a, b): a lied about b\n"
        "- went_to(a, place); at(a, place): a is at place now; told(a, b): a told b something (a report, gossip or "
        "testimony); detained(a, b); paid(a, b): a paid b a fine or a bribe; took_relic(a, relic)\n"
        "- other: any other assertion about what happened, with b set to a short paraphrase\n"
        "Characters: player (the one being spoken to, \"you\"), kael, brenna (the Captain), mags, odo. "
        "Places: tavern, market, guard_post, bridge, crypt."),
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


def narrator_facts(w: World, event_ids: set[str]) -> Facts:
    """The narrator holds no beliefs and knows exactly the events it was given to tell."""
    from games.crypt_road import rules

    return Facts(w, "narrator", rules.happened, lambda event_id: event_id in event_ids)


def check(w: World, checking: ClaimChecking, gateway: ModelGateway) -> ClaimCheck:
    """The claim check for lines said in `w`, through the checking's own gateway or the one the lines came from."""
    def facts_for(pack: StatePack) -> Facts:
        return narrator_facts(w, pack.ids) if pack.npc == "narrator" else facts(w, pack.npc)

    return ClaimCheck(checking.gateway or gateway, VOCABULARY, facts_for, every=checking.mode == "all")
