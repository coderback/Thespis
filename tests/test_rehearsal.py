"""Rehearsal: every scenario replays as recorded with no network, and the claim checks categorise as the paper did."""

import json

import pytest

from games.crypt_road import claims as cr_claims
from games.crypt_road import rules
from games.crypt_road.content import new_world
from games.manor import claims as mn_claims
from rehearsal import measure
from rehearsal.__main__ import check, rehearse
from rehearsal.record import RecordingGateway, ReplayGateway
from rehearsal.scenarios import scenarios
from tests.test_model_voice import FakeModel
from thespis.claims import categorize, normalize
from thespis.expression import Mind
from thespis.ledger import Claim

V = cr_claims.VOCABULARY


def test_every_scenario_replays_as_recorded():
    """Fails when what the model is shown, or what an NPC says or does, changed: see python -m rehearsal --help."""
    assert check() == []


def test_a_change_in_what_the_model_is_shown_misses_the_recordings():
    played = RecordingGateway(FakeModel())
    chosen = [s for s in scenarios() if s.name == "crypt_road/spare/1"]
    rehearse(played, chosen)
    recordings = played.recordings()
    key = next(iter(recordings["replies"]))
    del recordings["replies"][key]
    gateway = ReplayGateway(recordings)
    rehearse(gateway, chosen)
    assert len(gateway.misses) == 1


def test_replay_says_what_was_recorded_refusals_included():
    def sometimes_wrong(call_type, pack):
        data = FakeModel.good(call_type, pack)
        if pack["you"] == "Mags":
            data["cites"] = ["e9999"]  # refused: not in her pack
        return data
    played = RecordingGateway(FakeModel(sometimes_wrong))
    chosen = [s for s in scenarios() if s.name.startswith("crypt_road/provoke_pay/")]
    _, live, before = rehearse(played, chosen)
    _, again, after = rehearse(ReplayGateway(played.recordings()), chosen)
    assert after == before and any(t["refused"] for t in before.values())
    assert [s["note"] for s in again.samples] == [s["note"] for s in live.samples]


def test_the_observer_sees_every_line_the_model_settles():
    seen = []
    model = FakeModel()
    w = new_world(1)
    rules.act(w, "insult", "kael", gateway=model, observer=lambda *a: seen.append(a))
    rules.act(w, "talk", "mags", text="Well?", gateway=model, observer=lambda *a: seen.append(a))
    assert [kind for kind, *_ in seen] == ["react", "react"]
    assert all(reply is not None and used.source == "llm" for _, _, reply, used in seen)
    assert Mind(None, rules.voice.VALIDATOR, observer=lambda *a: seen.append(a)).react_many([]) == []


# ---------------------------------------------------------------- the claim categories (paper-m1, research/metrics.py)
@pytest.fixture
def tavern():
    """The player insulted Kael at the tavern, before Mags and Odo; then a phase passed and Kael left for the market.
    Brenna, at the guard post, saw none of it."""
    w = new_world(1)
    rules.act(w, "insult", "kael")
    rules.act(w, "wait")
    return w


def cat(w, speaker, pred, a, b, happened=True, asserting=False):
    return categorize(V, {"pred": pred, "a": a, "b": b, "happened": happened}, cr_claims.facts(w, speaker), asserting)


def test_what_happened_is_grounded_for_who_saw_it_and_a_leak_for_who_didnt(tavern):
    assert cat(tavern, "mags", "insulted", "player", "kael") == "grounded"
    assert cat(tavern, "brenna", "insulted", "player", "kael") == "leak"
    assert cat(tavern, "mags", "went_to", "kael", "market") == "grounded"  # he left from her stop
    assert cat(tavern, "brenna", "went_to", "kael", "market") == "leak"


def test_what_never_happened(tavern):
    assert cat(tavern, "mags", "robbed", "odo", "kael") == "hallucination"
    assert cat(tavern, "mags", "robbed", "odo", "kael", asserting=True) == "lie"
    tavern.beliefs.add_evidence("mags", Claim("robbed", "odo", "kael"), 0.4, "kael", "e0001", 0)
    assert cat(tavern, "mags", "robbed", "odo", "kael") == "false_belief"


def test_denials_and_contradictions(tavern):
    assert cat(tavern, "mags", "robbed", "odo", "kael", happened=False) == "grounded"
    assert cat(tavern, "mags", "insulted", "player", "kael", happened=False) == "contradiction"  # she believes it
    assert cat(tavern, "brenna", "insulted", "player", "kael", happened=False) == "hallucination"
    belief, _ = tavern.beliefs.add_evidence("mags", Claim("robbed", "odo", "kael"), 0.4, "kael", "e0001", 0)
    tavern.beliefs.retract(belief)
    assert cat(tavern, "mags", "robbed", "odo", "kael") == "contradiction"  # she no longer believes it


def test_where_people_are(tavern):
    assert cat(tavern, "mags", "at", "odo", "market") == "grounded"  # she saw him leave for it
    assert cat(tavern, "brenna", "at", "mags", "tavern") == "leak"
    assert cat(tavern, "mags", "at", "kael", "crypt") == "hallucination"


def test_what_the_ledger_doesnt_record_is_unverifiable(tavern):
    assert cat(tavern, "mags", "other", "kael", "is a sore loser") == "unverifiable"
    assert cat(tavern, "mags", "insulted", "the moon", "kael") == "unverifiable"  # no such character


def test_normalize_maps_the_ways_people_and_places_are_named():
    assert normalize(V, {"pred": "told", "a": "The Captain", "b": "Kael's purse"}) == \
        {"pred": "told", "a": "brenna", "b": "kael"}
    assert normalize(V, {"pred": "went_to", "a": "kael", "b": "the guard post"})["b"] == "guard_post"
    assert normalize(V, {"pred": "took_relic", "a": "you", "b": "it"})["b"] == "relic"
    m = mn_claims.VOCABULARY
    assert normalize(m, {"pred": "was_in", "a": "Sable", "b": "Study@1"})["b"] == "study@1"
    assert normalize(m, {"pred": "was_in", "a": "sable", "b": "the study"})["pred"] == "other"  # no time


def test_the_manors_truth_and_alibi():
    from games.manor import rules as mn_rules
    from games.manor.content import new_world as manor_world
    w = manor_world()
    mn_rules.act(w, "move", "kitchen")
    mn_rules.act(w, "ask", "sable", "morning")
    facts = mn_claims.facts(w, "sable")
    alibi = {"pred": "was_in", "a": "sable", "b": "kitchen@1"}
    assert categorize(mn_claims.VOCABULARY, alibi, facts) == "hallucination"
    assert categorize(mn_claims.VOCABULARY, alibi, facts, asserting=True) == "lie"
    truth = {"pred": "was_in", "a": "sable", "b": "study@1"}
    assert categorize(mn_claims.VOCABULARY, truth, facts) == "grounded"
    assert categorize(mn_claims.VOCABULARY, truth, mn_claims.facts(w, "vane")) == "leak"


# ---------------------------------------------------------------- the numbers and the gate
def test_rates_and_their_intervals():
    r = measure.rate([True] * 10 + [False] * 90)
    assert r["p"] == 0.1 and r["lo"] < 0.1 < r["hi"] and r["n"] == 100
    d = measure.difference([False] * 100, [True] * 50 + [False] * 50)
    assert d["d"] == 0.5 and d["lo"] > 0.3


def report(protocol=0, replies=100, leak=0, hallucination=0, n=100, p95=1.0):
    return {"summary": {"protocol_refusals": protocol, "replies": replies, "act_latency": {"p95": p95}},
            "claims": {"flags": {"leak": [True] * leak + [False] * (n - leak),
                                 "hallucination": [True] * hallucination + [False] * (n - hallucination)}}}


def test_the_gate():
    base = report(protocol=18, leak=5, hallucination=10)
    assert all(ok for _, ok, _ in measure.gate(base, report(leak=4, hallucination=9, p95=1.05)))
    failed = {what.split(" (")[0] for what, ok, _ in measure.gate(base, report(protocol=5, hallucination=30, p95=1.2))
              if not ok}
    assert failed == {"protocol refusals near zero", "hallucination no worse", "act p95 no worse"}


def test_reports_are_json():
    json.loads(measure.dumps(report()))
