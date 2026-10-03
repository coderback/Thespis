"""The game-agnostic core: ledger, beliefs, decisions, and the seams future work plugs into."""

import pytest

from thespis import director
from thespis.beliefs import RETRACTED, BeliefStore
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


def test_beliefs_keep_every_piece_of_evidence_and_take_the_max():
    store = BeliefStore()
    belief, is_new = store.add_evidence("brenna", ROBBED, 0.9, "kael", "e0011", 2)
    again, is_new_again = store.add_evidence("brenna", ROBBED, 0.8, "odo", "e0012", 2)
    assert (is_new, is_new_again) == (True, False) and again is belief
    assert belief.id == "b0001"
    assert [e.source for e in belief.evidence] == ["kael", "odo"]  # provenance kept, not overwritten
    assert belief.conf == store.conf("brenna", ROBBED) == 0.9


def test_retracted_belief_ignores_new_evidence():
    store = BeliefStore()
    belief, _ = store.add_evidence("brenna", LIE, 0.9, "player", "e0014", 3)
    store.retract(belief)
    store.add_evidence("brenna", LIE, 1.0, "mags", "e0020", 6)
    assert belief.status == RETRACTED and len(belief.evidence) == 1
    assert store.conf("brenna", LIE) == 0.0 and store.conf("nobody", LIE) == 0.0


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
    gone, _ = store.add_evidence("brenna", LIE, 1.0, "player", "e0004", 3)
    store.retract(gone)
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
