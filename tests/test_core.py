"""The game-agnostic core: ledger, beliefs, decisions, and the seams future work plugs into."""

import pytest

from thespis import director
from thespis.beliefs import ACTIVE, RETRACTED, VACUOUS, Belief, BeliefStore, Evidence, Opinion, fuse
from thespis.brain import UtilityBrain
from thespis.decisions import DECIDE, DecisionLog
from thespis.ledger import Claim, Event, Ledger
from thespis.retriever import TopKRetriever

ROBBED = Claim("robbed", "player", "kael")
LIE = Claim("robbed", "kael", "odo")


def test_ledger_ids_are_sequential_and_events_immutable():
    ledger = Ledger()
    first = ledger.append(0, "insult", "player", "kael", "tavern", Claim("insulted", "player", "kael"))
    second = ledger.append(0, "challenge", "player", "kael", "tavern")
    assert [first.id, second.id] == ["e0001", "e0002"]
    assert first.schema_version == 1 and second.claim is None
    with pytest.raises(AttributeError):
        first.truth = False  # frozen: the ledger is append-only
    assert not any(hasattr(ledger, name) for name in ("remove", "update", "pop", "__setitem__", "__delitem__"))


def test_happened_ignores_false_reports():
    ledger = Ledger()
    ledger.append(0, "humiliate", "player", "kael", "tavern", ROBBED)
    ledger.append(3, "tell_claim", "player", "brenna", "guard_post", LIE, truth=False)
    assert ledger.happened(ROBBED)
    assert not ledger.happened(LIE)
    assert [e.id for e in ledger.since(3)] == ["e0002"] and ledger.tail(1)[0].id == "e0002"


def test_event_round_trip():
    event = Event("e0007", 2, "accuse", "kael", "brenna", "guard_post", ROBBED)
    assert Event.from_json(event.to_json()) == event


def test_a_claim_with_only_two_names_serialises_as_it_always_has():
    assert ROBBED.to_json() == {"pred": "robbed", "a": "player", "b": "kael"}
    assert Claim.from_json({"pred": "robbed", "a": "player", "b": "kael"}) == ROBBED


def test_typed_claims_carry_a_place_a_time_and_a_denial():
    alibi = Claim("was_in", "sable", place="kitchen", at=1)
    assert alibi.to_json() == {"pred": "was_in", "a": "sable", "place": "kitchen", "at": 1}
    assert Claim.from_json(alibi.to_json()) == alibi and alibi.label() == "was_in(sable, kitchen@1)"
    denial = ROBBED.negated()
    assert denial.to_json() == {**ROBBED.to_json(), "neg": True} and Claim.from_json(denial.to_json()) == denial
    assert denial != ROBBED and denial.same_fact(ROBBED) and denial.affirmed() == ROBBED
    assert denial.label() == "not robbed(player, kael)"


def test_a_denial_is_true_when_what_it_denies_never_happened():
    ledger = Ledger()
    ledger.append(0, "humiliate", "player", "kael", "tavern", ROBBED)
    ledger.append(3, "tell_claim", "player", "brenna", "guard_post", LIE, truth=False)
    assert not ledger.happened(ROBBED.negated())
    assert ledger.happened(LIE.negated())  # told, but it never happened


def test_one_report_gives_its_own_confidence():
    store = BeliefStore()
    belief, is_new = store.add_evidence("brenna", ROBBED, 0.9, "kael", "e0011", 2)
    assert is_new and belief.id == "b0001"
    assert belief.opinion == Opinion(0.9, 0.0, 0.1) and belief.conf == store.conf("brenna", ROBBED) == 0.9


def test_independent_sources_add_up_and_a_source_repeating_itself_does_not():
    store = BeliefStore()
    belief, _ = store.add_evidence("brenna", ROBBED, 0.9, "kael", "e0011", 2)
    again, is_new = store.add_evidence("brenna", ROBBED, 0.8, "kael", "e0012", 2)
    assert again is belief and not is_new and belief.conf == 0.9  # the same source twice: its strongest word
    store.add_evidence("brenna", ROBBED, 0.8, "odo", "e0013", 2)
    assert [e.source for e in belief.evidence] == ["kael", "kael", "odo"]  # provenance kept, not overwritten
    # Cumulative fusion of (0.9, 0, 0.1) and (0.8, 0, 0.2): u = 0.02 / 0.28, b = (0.18 + 0.08) / 0.28.
    assert belief.opinion == Opinion(0.9286, 0.0, 0.0714)


def test_what_an_npc_saw_itself_outweighs_any_report():
    certain, hearsay = Opinion(1.0, 0.0, 0.0), Opinion(0.0, 0.9, 0.1)
    assert certain.fuse(hearsay) == certain and hearsay.fuse(certain) == certain
    assert certain.fuse(Opinion(0.0, 1.0, 0.0)) == Opinion(0.5, 0.5, 0.0)  # two certainties that disagree: average
    assert VACUOUS.fuse(hearsay) == hearsay and fuse([]) == VACUOUS


def test_evidence_against_lowers_a_belief_until_it_is_retracted():
    store = BeliefStore()
    belief, _ = store.add_evidence("brenna", LIE, 0.4, "player", "e0014", 3)
    store.add_evidence("brenna", LIE, 0.4, "mags", "e0020", 6, against=True)
    assert belief.status == ACTIVE and belief.opinion.b == belief.opinion.d  # as sure either way: not retracted
    store.add_evidence("brenna", LIE, 0.9, "odo", "e0021", 6, against=True)
    assert belief.status == RETRACTED and store.conf("brenna", LIE) == 0.0 and store.conf("nobody", LIE) == 0.0
    store.add_evidence("brenna", LIE, 1.0, "witnessed", "e0030", 7)  # and it can come back
    assert belief.status == ACTIVE and belief.conf == 1.0


def test_discrediting_a_source_reweighs_everything_it_said():
    store = BeliefStore()
    lie, _ = store.add_evidence("brenna", LIE, 0.9, "player", "e0014", 3)
    other, _ = store.add_evidence("brenna", ROBBED, 0.9, "player", "e0015", 3)
    seen, _ = store.add_evidence("brenna", Claim("insulted", "player", "kael"), 1.0, "witnessed", "e0001", 0)
    changed = store.discredit("brenna", "player", 0.2)
    assert changed == [lie, other] and lie.conf == other.conf == 0.2 and seen.conf == 1.0
    assert store.discredit("brenna", "player", 0.4) == []  # discredit only ever lowers
    assert [e.event for e in lie.evidence] == ["e0014"]  # the justification is kept, at its new weight


def test_a_retraction_saved_before_opinions_stays_retracted():
    old = {"id": "b0007", "npc": "brenna", "claim": LIE.to_json(), "status": "retracted",
           "evidence": [{"source": "player", "event": "e0014", "phase": 3, "conf": 0.9}]}
    belief = Belief.from_json(old)
    assert belief.status == RETRACTED and belief.evidence[-1] == Evidence("revised", "e0014", 3, 1.0, against=True)
    assert Belief.from_json({**old, "status": "active"}).status == ACTIVE


def test_belief_store_round_trip():
    store = BeliefStore()
    store.add_evidence("mags", ROBBED, 1.0, "witnessed", "e0004", 0)
    store.add_evidence("brenna", ROBBED, 0.9, "kael", "e0011", 2)
    assert BeliefStore.from_json(store.to_json()).to_json() == store.to_json()


def test_retriever_ranks_by_confidence_then_recency():
    store = BeliefStore()
    store.add_evidence("brenna", Claim("insulted", "player", "kael"), 0.8, "odo", "e0001", 1)
    store.add_evidence("brenna", Claim("beat", "player", "kael"), 0.8, "odo", "e0002", 2)
    store.add_evidence("brenna", ROBBED, 0.9, "kael", "e0003", 2)
    store.add_evidence("brenna", LIE, 0.9, "player", "e0004", 3)
    store.add_evidence("brenna", LIE, 1.0, "odo", "e0005", 3, against=True)  # retracted
    ranked = TopKRetriever(k=2).beliefs(store, "brenna")
    assert [b.claim.pred for b in ranked] == ["robbed", "beat"]


def test_utility_brain_breaks_ties_like_the_rules_model():
    brain = UtilityBrain()
    assert brain.choose("kael", {"go_to": 6, "wait": 0, "accuse:player": 9}) == "accuse:player"
    assert brain.choose("kael", {"go_to": 6, "share_drink": 6}) == "go_to"  # first listed wins a tie


def test_decision_log_assigns_ids():
    log = DecisionLog()
    d = log.record(DECIDE, "kael", 0, "threshold", allowed=["go_to", "wait"], chosen="go_to")
    assert d.id == "d0001" and DecisionLog.from_json(log.to_json()).to_json() == log.to_json()


def test_director_registry(monkeypatch):
    monkeypatch.setattr(director, "_PATTERNS", {})

    @director.register("always")
    def always(world):
        return director.Hook("always", "Something stirs.")

    @director.register("never")
    def never(world):
        return None

    assert list(director.patterns()) == ["always", "never"]
    assert director.sift(None) == [director.Hook("always", "Something stirs.")]
