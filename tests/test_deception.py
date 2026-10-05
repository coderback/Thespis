"""#35: NPC deception as a validated action, in the core alone: no game is imported here."""

from thespis.deception import SAID, asserting, log_statement
from thespis.decisions import DECIDE, DecisionLog
from thespis.expression import StatePack, Validator
from thespis.ledger import Claim
from thespis.minds import NPC
from thespis.world import World


def kitchen() -> World:
    w = World(seed=1, player={}, npcs={"ann": NPC("ann", "kitchen"), "bo": NPC("bo", "kitchen")})
    w.ledger.append(0, "bake", "ann", None, "kitchen", Claim("baked", "ann", "pie"))
    return w


def test_a_statement_is_logged_with_its_real_truth():
    w = kitchen()
    lie, cites = log_statement(w, "tell", "bo", "ann", "kitchen", Claim("baked", "bo", "pie"), [SAID, "e0001"])
    assert lie.truth is False and cites == [lie.id, "e0001"]  # the line now cites the statement itself
    truth, _ = log_statement(w, "tell", "ann", "bo", "kitchen", Claim("baked", "ann", "pie"), [])
    assert truth.truth is True


def pack(allowed: list[dict]) -> StatePack:
    return StatePack(npc="bo", name="Bo", persona="", goal="", situation="", here=[], drives={}, trust_in={},
                     beliefs=[], events=[{"id": "e0001", "what": "Ann baked a pie."}], allowed=allowed)


def test_a_lie_must_cite_the_claim_it_asserts():
    v = Validator({})
    p = pack([asserting({"id": "lie", "does": "say you baked it", "pull": 5}, "Bo baked the pie"),
              {"id": "shrug", "does": "shrug", "pull": 3}])
    assert SAID in p.ids
    assert "without citing" in v.problem({"action": "lie", "line": "I baked it.", "cites": ["e0001"]}, p, "decide")
    assert v.problem({"action": "lie", "line": "I baked it.", "cites": [SAID]}, p, "decide") is None
    assert "doesn't state" in v.problem({"action": "shrug", "line": "Who knows?", "cites": [SAID]}, p, "decide")
    assert v.problem({"action": "shrug", "line": "Who knows?", "cites": ["e0001"]}, p, "decide") is None


def test_without_an_assertion_nothing_changes():
    assert pack([{"id": "shrug", "does": "shrug", "pull": 3}]).ids == {"e0001"}


def test_a_decision_names_its_statement_only_when_it_made_one():
    log = DecisionLog()
    plain = log.record(DECIDE, "bo", 0, "asked", allowed=["shrug"], chosen="shrug")
    lie = log.record(DECIDE, "bo", 0, "asked", allowed=["lie"], chosen="lie", asserted="e0002")
    assert "asserted" not in plain.to_json() and lie.to_json()["asserted"] == "e0002"
    assert DecisionLog.from_json(log.to_json()).to_json() == log.to_json()
