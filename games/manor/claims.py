"""The manor's vocabulary for claims (thespis.claims). The extractor writes where someone was, and when, as
ROOM@TIME; thespis.claims.as_claim types it into the claim's place and at."""

from __future__ import annotations

from games.manor import content as C
from thespis.claims import ClaimCheck, ClaimChecking, ClaimVocabulary, EventPred, Facts, check_for
from thespis.gateway import ModelGateway
from thespis.world import World

VOCABULARY = ClaimVocabulary(
    game="manor",
    description=C.CAST.data["claims"]["description"],
    characters=("player", C.OWNER, C.BUTLER, C.MAID),
    places=tuple(C.ROOMS),
    ledger_preds=frozenset({"took", "was_in"}),
    event_preds={"left": EventPred(("leave",), "loc"), "told": EventPred(("tell", "testify"), "target"),
                 "questioned": EventPred(("question",), "target"), "accused": EventPred(("accuse",), "target")},
    place_preds=frozenset({"left", "at"}),
    fixed_b={"took": C.ITEM},
    timed_preds=frozenset({"was_in"}),
    aliases={"you": "player", "the player": "player", "lady vane": C.OWNER, "her ladyship": C.OWNER,
             "my lady": C.OWNER},
)


def facts(w: World, speaker: str) -> Facts:
    """What `speaker` could know of `w`, by the game's own rule (voice.knows)."""
    from games.manor import voice

    return Facts(w, speaker, lambda world, claim: world.ledger.happened(claim),
                 lambda event_id: voice.knows(w, speaker, event_id))


def check(w: World, checking: ClaimChecking, gateway: ModelGateway) -> ClaimCheck:
    """The claim check for lines said in `w`, through the checking's own gateway or the one the lines came from."""
    return check_for(checking, gateway, VOCABULARY, lambda pack: facts(w, pack.npc))
