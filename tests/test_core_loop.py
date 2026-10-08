"""The mind loop's core pieces, on their own: content, perception, verbs, and the Voice that builds state packs."""

import pytest

from games.crypt_road import voice as cr_voice
from games.crypt_road.content import CAST, new_world
from games.manor import voice as mn_voice
from games.manor.content import new_world as manor_world
from thespis.beliefs import credence
from thespis.ledger import Claim
from thespis.perception import knows, latest, witness
from thespis.play import NotAllowed, Verbs, check


def test_a_line_needs_a_template_and_something_to_cite():
    assert CAST.line("mags", "talk", ["e0001", None, "e0001"]) == ("What'll it be, love?", ["e0001"])
    assert CAST.line("mags", "talk", [None]) is None  # no line without a source
    assert CAST.line("mags", "no_such_line", ["e0001"]) is None
    assert CAST.line("brenna", "bribe", ["e0002"], amount=20)[0] == "For 20 coins, I was looking the other way."


def test_content_comes_from_the_cast_file():
    assert CAST.text("words.events", "spare", a="You", t="Kael") == "You spared Kael."
    assert CAST.has("words.events", "spare") and not CAST.has("words.events", "fly")
    assert not CAST.has("no.such.table", "spare")


def test_perception_is_the_games_rule_applied_to_every_event():
    w = new_world(1)
    e = w.ledger.append(0, "insult", "player", "kael", "tavern", Claim("insulted", "player", "kael"))
    assert knows(w, "kael", e.id) and knows(w, "mags", e.id)  # the target, and someone at the scene
    assert not knows(w, "brenna", e.id)  # at the guard post
    assert not knows(w, "mags", e.id, sees=lambda w, npc, e: False)  # a game whose NPCs see nothing
    assert latest(w, "brenna") is None and latest(w, "odo") == e.id


def test_witnesses_see_it_and_the_two_involved_know_it():
    w, given = new_world(1), []
    claim = Claim("insulted", "player", "kael")
    e = w.ledger.append(0, "insult", "player", "kael", "tavern", claim)
    witness(w, claim, "player", "kael", e, "tavern", lambda w, npc, c, conf, src, ev: given.append((npc, src)))
    assert given == [("mags", "witnessed"), ("odo", "witnessed"), ("kael", "self")]


def test_a_lock_disables_every_verb_without_its_own_reason():
    verbs = Verbs("The race is over")
    verbs.add("wait", None, "Wait", {}, True)
    verbs.add("spare", "kael", "Spare Kael", {}, True, reason="Win a duel first")
    assert [(o["enabled"], o["reason"]) for o in verbs.options] == [(False, "The race is over"),
                                                                    (False, "Win a duel first")]
    open_ = Verbs()
    open_.add("move", None, "Move on", {}, True, ok=False, why="Blocked")
    open_.add("wait", None, "Wait", {}, True)
    assert check(open_.options, "wait", None)["label"] == "Wait"
    with pytest.raises(NotAllowed, match="Blocked"):
        check(open_.options, "move", None)
    with pytest.raises(NotAllowed, match="You can't take relic here"):
        check(open_.options, "take_relic", None)


def test_credence_is_one_ladder_for_every_game():
    assert [credence(t) for t in (-5, -1, 0, 1, 2, 5)] == [0.2, 0.2, 0.4, 0.4, 0.9, 0.9]


def test_a_voice_names_what_the_pack_mentions_or_the_whole_household():
    w = new_world(1)
    pack = cr_voice.VOICE.pack(w, "mags", 'The player says to you: "Where is Brenna?"')
    assert "brenna" in pack.names and "crypt" in pack.names and "player" not in pack.names
    assert cr_voice.VOICE.pack(w, "mags", "Hello.").names == {"mags", "kael", "odo", *cr_voice.C.STOPS}
    manor = manor_world()
    assert mn_voice.VOICE.pack(manor, "pell", "Hello.").names == {"hall", "study", "kitchen", "vane", "pell", "sable"}


def test_an_action_that_states_a_claim_shows_what_it_says():
    w = manor_world()
    pack = mn_voice.VOICE.pack(w, "sable", "Where were you?", "deceive:alibi", mn_voice.C.THE_ALIBI)
    assert pack.action == {"id": "deceive:alibi", "does": mn_voice.DOES["deceive:alibi"],
                           "asserts": {"id": "said", "claim": "Sable was in the kitchen at mid-morning"}}
    assert pack.asserted == mn_voice.C.THE_ALIBI and pack.stakes
