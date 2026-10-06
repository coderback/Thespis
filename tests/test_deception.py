"""#35: NPC deception as a validated action, in the core alone: no game is imported here."""

from thespis.deception import SAID, asserting, log_statement
from thespis.decisions import DECIDE, DecisionLog
from thespis.expression import Mind, StatePack, Utterance, Validator
from thespis.gateway import ModelReply
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


def pack(action: dict) -> StatePack:
    return StatePack(npc="bo", name="Bo", persona="", goal="", situation="", here=[], drives={}, trust_in={},
                     beliefs=[], events=[{"id": "e0001", "what": "Ann baked a pie."}], action=action)


class Says:
    """A model that says one line, citing the given references."""

    providers = models = ("m",)

    def __init__(self, *cites):
        self.cites, self.payloads = list(cites), []

    def complete(self, call_type, messages, schema=None):
        self.payloads.append(messages[1]["content"])
        return ModelReply({"cites": self.cites, "line": "I baked it."}, "m", "m", 0.0)


def test_a_lie_always_cites_the_claim_it_asserts():
    """The action, which code chose, states the claim, so its line cites it whether the model did or not."""
    lie = pack(asserting({"id": "lie", "does": "say you baked it"}, "Bo baked the pie"))
    assert SAID in lie.ids and lie.payload()["DOING"] == {"does": "say you baked it", "says": "Bo baked the pie"}
    assert lie.schema()["properties"]["cites"]["items"]["enum"] == ["e1", SAID]
    fallback = Utterance("lie", "Me. I baked it.", [SAID], "fallback")
    for model in (Says("e1"), Says("e1", SAID)):
        u = Mind(model, Validator({})).act(lie, fallback)
        assert (u.action, u.source, u.cites) == ("lie", "llm", ["e0001", SAID])


def test_without_an_assertion_nothing_changes():
    shrug = pack({"id": "shrug", "does": "shrug"})
    assert shrug.ids == {"e0001"} and "says" not in shrug.payload()["DOING"]
    assert "cites said, not in its state pack" in Validator({}).problem(
        {"line": "Who knows?", "cites": [SAID]}, shrug, "act")


def test_a_decision_names_its_statement_only_when_it_made_one():
    log = DecisionLog()
    plain = log.record(DECIDE, "bo", 0, "asked", allowed=["shrug"], chosen="shrug")
    lie = log.record(DECIDE, "bo", 0, "asked", allowed=["lie"], chosen="lie", asserted="e0002")
    assert "asserted" not in plain.to_json() and lie.to_json()["asserted"] == "e0002"
    assert DecisionLog.from_json(log.to_json()).to_json() == log.to_json()
