"""The manor's vocabulary for claims (thespis.claims). Where someone was, and when, shares the claim's second slot as
"room@time" until typed claims arrive (docs/cast-review.md, Phase 3)."""

from __future__ import annotations

from games.manor import content as C
from thespis.claims import ClaimVocabulary, EventPred, Facts
from thespis.world import World

VOCABULARY = ClaimVocabulary(
    game="manor",
    description=(
        "Predicates (a and b are ids):\n"
        "- took(a, ring): a took the signet ring; was_in(a, ROOM@TIME): a was in a room at a time, with TIME a "
        "number: 0 early morning, 1 mid-morning (also \"this morning\" or \"all morning\"), 2 noon, 3 early "
        "afternoon, 4 mid-afternoon, 5 late afternoon, 6 teatime, 7 evening; e.g. kitchen@1\n"
        "- left(a, room); at(a, room): a is in that room now; told(a, b); questioned(a, b); accused(a, b)\n"
        "- other: any other assertion about what happened, with b set to a short paraphrase\n"
        "Characters: player (the one being spoken to, \"you\"), vane (Lady Vane, her ladyship), pell, sable. "
        "Rooms: hall, study, kitchen."),
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
