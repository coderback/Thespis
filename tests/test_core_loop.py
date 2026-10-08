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


def test_affordances_keep_their_declared_order_and_their_tests():
    from thespis.affordances import Affordance, options
    from thespis.voice import View

    w = new_world(1)
    acts = (Affordance("go_to", lambda w, n, v: n.drives["ambition"]),
            Affordance("wait", lambda w, n, v: 0),
            Affordance("take_relic", lambda w, n, v: 100, when=lambda w, n, v: n.loc == "crypt"))
    assert options(w, "kael", acts, View("tavern")) == {"go_to": 6, "wait": 0}  # not at the crypt
    w.npcs["kael"].loc = "crypt"
    assert list(options(w, "kael", acts, View("tavern"))) == ["go_to", "wait", "take_relic"]


def test_a_decision_is_chosen_by_code_voiced_and_recorded():
    from thespis.affordances import decide
    from thespis.brain import UtilityBrain
    from thespis.expression import Mind

    w = new_world(1)
    d = decide(w, Mind(None, cr_voice.VALIDATOR), cr_voice.VOICE, UtilityBrain(), "kael", "tick",
               {"go_to": 6, "wait": 0}, lambda ch: None, "You are at the tavern.")
    assert (d.kind, d.chosen, d.allowed, d.reason, d.source) == ("decide", "go_to", ["go_to", "wait"], "go_to scores 6",
                                                                 "fallback")
    settled = decide(w, Mind(None, cr_voice.VALIDATOR), cr_voice.VOICE, UtilityBrain(), "kael", "tick", {"wait": 1},
                     lambda ch: None, "Here.", scores="pulls", settle=lambda ch, u: {"cites": ["e0001"]})
    assert settled.reason == "wait pulls 1" and settled.cites == ["e0001"]


def test_the_tick_runs_its_steps_in_order_and_collects_what_they_did():
    from thespis.tick import gossip, run_tick, walk, walks

    w, order = new_world(1), []
    tick = run_tick(w, [lambda t: order.append("first"), lambda t: walk(w, t, "mags", "market"),
                        lambda t: order.append("last")])
    assert order == ["first", "last"] and tick.moves == [{"who": "mags", "from": "tavern", "to": "market"}]
    assert [e.verb for e in tick.events] == ["move"]
    later = run_tick(w, [lambda t: walks(w, t, lambda npc: ["tavern", "tavern"] if npc == "mags" else None)])
    assert later.moves == [{"who": "mags", "from": "market", "to": "tavern"}]

    w2, heard = new_world(1), []
    robbed = Claim("robbed", "player", "kael")
    w2.beliefs.add_evidence("mags", robbed, 1.0, "witnessed", "e0001", 0)
    gossip(w2, ["mags"], ["player"], {"robbed": 3}, 0.5, 0.8, lambda w, c: True,
           lambda w, npc, c, conf, src, e: heard.append((npc, conf, src)))
    assert heard == [("kael", 0.8, "mags"), ("odo", 0.8, "mags")]  # everyone at her stop, at 1.0 x 0.8


def test_reconcile_lets_the_more_trusted_source_win_and_discredits_the_other():
    from thespis.beliefs import BeliefStore, reconcile

    here, there = Claim("was_in", "sable", place="study", at=1), Claim("was_in", "sable", place="kitchen", at=1)
    store, trust = BeliefStore(), {"pell": 3, "sable": 2}
    alibi, _ = store.add_evidence("vane", there, 0.9, "sable", "e0003", 1)
    store.add_evidence("vane", here, 0.9, "pell", "e0009", 4)
    contradicts = lambda a, b: a.at == b.at and a.place != b.place  # noqa: E731
    assert reconcile(store, "vane", here, trust, 4, contradicts, 3) == [alibi]
    assert trust == {"pell": 3, "sable": -1} and alibi.evidence[0].conf == credence(-1)
    tied, tied_trust = BeliefStore(), {"pell": 2, "sable": 2}
    tied.add_evidence("vane", there, 0.9, "sable", "e0003", 1)
    tied.add_evidence("vane", here, 0.9, "pell", "e0009", 4)
    assert reconcile(tied, "vane", here, tied_trust, 4, contradicts, 3) == [] and tied_trust["sable"] == 2
