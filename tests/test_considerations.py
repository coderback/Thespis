"""Choices declared as data (thespis.considerations): what they compile to, and the mistakes caught at load."""

import pytest

from games.crypt_road.content import CHOICES as CRYPT
from games.manor.content import CHOICES as MANOR
from thespis.considerations import DefinitionError, compile_choices, declared
from thespis.ledger import Claim
from thespis.minds import NPC
from thespis.voice import View
from thespis.world import World

ROBBED = Claim("robbed", "player", "kael")


def world(**kael) -> World:
    return World(seed=1, player={"loc": "tavern"},
                 npcs={"kael": NPC("kael", **{"loc": "tavern", **kael}), "brenna": NPC("brenna", "guard_post")})


def test_kaels_choices_follow_his_drives_and_what_he_believes():
    tick = CRYPT["kael", "tick"]
    w = world(drives={"ambition": 6, "grudge": 5, "respect": 0})
    assert tick.options(w, View("tavern")) == {"go_to": 6, "wait": 0}  # whole numbers stay whole
    w.npcs["kael"].loc = "guard_post"
    assert "accuse:player" not in tick.options(w, View("tavern"))  # nothing to report yet
    w.beliefs.add_evidence("kael", ROBBED, 1.0, "self", "e0001", 0)
    assert tick.options(w, View("tavern"))["accuse:player"] == 8
    w.npcs["kael"].flags["accused"] = True
    assert "accuse:player" not in tick.options(w, View("tavern"))


def test_with_the_player_means_where_the_player_was_seen():
    w = world(drives={"respect": 4})
    assert CRYPT["kael", "tick"].options(w, View("tavern"))["share_drink"] == 7
    assert "share_drink" not in CRYPT["kael", "tick"].options(w, View("market"))


def test_bindings_name_the_action_and_gate_its_terms():
    offer = CRYPT["brenna", "bribe_offer"]
    w = world()
    assert offer.options(w, View("guard_post"), price=12, lowball=True) == {"counter:12": 5, "refuse": 7}
    assert offer.options(w, View("guard_post"), price=12, lowball=False) == {"counter:12": 5, "refuse": 3}
    assert list(CRYPT["brenna", "crime_belief"].options(w, View("x"), culprit="kael")) == ["detain:kael", "wait"]


def test_an_action_names_the_claim_it_states():
    assert MANOR["sable", "asked_morning"].asserts() == {
        "deceive:alibi": Claim("was_in", "sable", place="kitchen", at=1)}


def test_every_declared_choice_compiles():
    assert set(CRYPT) == {("kael", "tick"), ("brenna", "crime_belief"), ("brenna", "witness_present"),
                          ("brenna", "bribe_offer")}
    assert declared({"npc": {"x": {"name": "X"}}}) == {}


@pytest.mark.parametrize("bad, message", [
    ([], "expected a list of choices"),
    ([{"utility": 1}], r"\[0\]: a choice needs do"),
    ([{"do": "go"}], "needs a utility"),
    ([{"do": "go", "utility": "high"}], "expected a number"),
    ([{"do": "go", "utility": True}], "expected a number"),
    ([{"do": "go", "utility": 1, "when": [{"drive": "fear"}]}], "needs one of gte"),
    ([{"do": "go", "utility": 1, "when": [{"drive": "fear", "most": 3}]}], "unknown key most"),
    ([{"do": "go", "utility": 1, "when": [{"fly": True}]}], "unknown condition 'fly'"),
    ([{"do": "go", "utility": 1, "when": [{"at": "x", "flag": "y"}]}], "one condition per table"),
    ([{"do": "go", "utility": 1, "when": [{"believes": {"a": "x"}}]}], "a claim needs pred and a"),
    ([{"do": "go", "utility": 1, "when": [{"any": "at"}]}], "expected a list of conditions"),
    ([{"do": "go", "utility": [{"drive": "x", "times": 2}]}], "unknown key times"),
    ([{"do": "go", "utility": 1, "cost": 2}], "unknown key cost"),
    ([{"do": "go", "utility": 1}, {"do": "go", "utility": 2}], "declared twice"),
])
def test_a_mistake_fails_at_load_and_says_where(bad, message):
    with pytest.raises(DefinitionError, match=message):
        compile_choices("kael", "tick", bad)
