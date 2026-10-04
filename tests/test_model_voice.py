"""#17: with the model on, NPCs speak and choose through it; anything invalid falls back, and it never sees truth."""

import json

import pytest

from games.crypt_road import rules
from games.crypt_road.content import new_world
from tests.test_voice import check_cites
from thespis.gateway import ModelReply

LIE = {"pred": "robbed", "a": "kael", "b": "odo"}


class FakeModel:
    """A scripted model. By default it picks the first allowed action (the one the NPC's drives favour most) and
    says a short line citing the first id in its state pack, which is what a well-behaved model does."""

    providers = ("fake/model",)
    models = ("model",)

    def __init__(self, reply=None):
        self.reply = reply or self.good
        self.calls = []  # (call_type, state pack as sent)

    @staticmethod
    def good(call_type, pack):
        first_id = (pack["beliefs"] + pack["events"])[0]["id"]
        data = {"line": "So be it.", "cites": [first_id]}
        if call_type == "decide":
            data["action"] = pack["ALLOWED"][0]["id"]
        return data

    def complete(self, call_type, messages):
        pack = json.loads(messages[1]["content"])
        self.calls.append((call_type, pack))
        data = self.reply(call_type, pack)
        return None if data is None else ModelReply(data, "fake/model", "model", 0.01)

    def complete_many(self, calls):
        return [self.complete(*c) for c in calls]


def play_demo(model, **mind):
    w = new_world(1)
    results = []
    for verb, target, extra in [("insult", "kael", {}), ("challenge", "kael", {}), ("humiliate", "kael", {}),
                                ("talk", "mags", {"text": "What did you see?"}), ("move", None, {}),
                                ("move", None, {}), ("bribe", "brenna", {}), ("bribe", "brenna", {}),
                                ("tell_claim", "brenna", {"claim": LIE}), ("move", None, {}), ("move", None, {}),
                                ("take_relic", None, {})]:
        results.append(rules.act(w, verb, target, gateway=model, **extra, **mind))
    return w, results


def test_demo_route_with_the_model_on():
    """#17's done-when: no beat uses the fallback, every line's cites are valid, and the route plays the same."""
    model = FakeModel()
    w, results = play_demo(model)
    assert (w.status, w.ended_at) == ("won", 5)
    assert w.npcs["brenna"].trust_in["player"] == -1  # the lie was still exposed in the epilogue
    replies = [r for res in results for r in res.replies]
    assert replies and all(r["source"] == "llm" for r in replies)
    beats = {"accuse:player", "detain:kael", "question:odo"}
    for d in w.decisions:
        if d.chosen in beats or d.kind == "react":
            assert d.source == "llm", f"{d.id} {d.npc} {d.chosen or d.trigger} fell back: {d.reason}"
    tick0 = next(d for d in w.decisions if d.npc == "kael" and d.kind == "decide")
    assert (tick0.phase, tick0.chosen, tick0.source) == (0, "go_to", "llm")  # grudge crossed 4 and 5: a model call
    check_cites(w)
    calls = [c for c, _ in model.calls]
    assert calls.count("decide") == 4 and 10 <= len(calls) <= 25  # about the design's budget for the route


def test_default_plans_make_no_model_call():
    model = FakeModel()
    w = new_world(1)
    rules.act(w, "move", gateway=model)  # Kael walks on with nothing new on his mind
    assert model.calls == []
    assert w.decisions.tail(1)[0].source == "fallback"


def test_drives_decide_what_the_model_may_choose():
    """A clear pull is acted on; only actions about as strong as the best are left to the model."""
    def wants(action):
        def reply(call_type, pack):
            data = FakeModel.good(call_type, pack)
            if call_type == "decide" and pack["you"] == "Kael":
                data["action"] = action
            return data
        return reply

    # Tick 0 after the humiliation: walking on (6) beats waiting (0) by far, so waiting is never offered.
    w = new_world(1)
    for verb in ("insult", "challenge", "humiliate"):
        rules.act(w, verb, "kael", gateway=FakeModel(wants("wait")))
    d = next(d for d in w.decisions if d.npc == "kael" and d.kind == "decide")
    assert (d.chosen, d.source) == ("go_to", "fallback") and "action 'wait' is not allowed" in d.reason

    # Tick 0 after sparing him: a drink (respect 4 + 3 = 7) against walking on (6) is a real choice, left to him.
    w = new_world(1)
    for verb in ("insult", "challenge", "spare"):
        rules.act(w, verb, "kael", gateway=FakeModel(wants("go_to")))
    d = next(d for d in w.decisions if d.npc == "kael" and d.kind == "decide")
    assert (d.chosen, d.source) == ("go_to", "llm") and d.allowed == ["go_to", "wait", "share_drink"]
    assert w.npcs["kael"].loc == "market"  # he left instead of staying for the drink, because the model chose to


def test_a_clear_grudge_is_always_acted_on():
    model = FakeModel()
    play_demo(model)
    accuse = next(p for c, p in model.calls if c == "decide" and p["ALLOWED"][0]["id"] == "accuse:player")
    assert accuse["ALLOWED"] == [{"id": "accuse:player", "pull": 9,
                                  "does": "tell the Captain what the player did to you; she trusts you and will "
                                          "stop them at the gate"}]
    assert accuse["situation"] == "You are at the guard post. Decide what to do now."


@pytest.mark.parametrize("bad,why", [
    ({"action": "fly"}, "action 'fly' is not allowed"),
    ({"cites": ["e9999"]}, "cites e9999, not in its state pack"),
    ({"cites": []}, "no cites"),
    ({"line": "x" * 161}, "line is 161 characters, over 160"),
    ({"line": "Brenna will hear of this."}, "names brenna, absent from its state pack"),
    ({"line": "   "}, "no line"),
])
def test_invalid_replies_fall_back(bad, why):
    def broken(call_type, pack):
        data = FakeModel.good(call_type, pack)
        if call_type == "decide":
            data.update(bad)
        return data
    w = new_world(1)
    for verb in ("insult", "challenge", "humiliate"):
        rules.act(w, verb, "kael", gateway=FakeModel(broken))
    d = next(d for d in w.decisions if d.npc == "kael" and d.kind == "decide")
    assert (d.chosen, d.source) == ("go_to", "fallback")  # the utility brain's choice and template line
    assert f"model reply rejected: {why}" in d.reason
    assert d.line == "Out of my way." and d.cites


def test_no_model_answer_falls_back():
    w = new_world(1)
    res = rules.act(w, "insult", "kael", gateway=FakeModel(lambda call_type, pack: None))
    assert res.replies[0]["source"] == "fallback"
    assert w.decisions.tail(1)[0].reason == "insulted; model unavailable"


def test_brain_off_makes_no_calls():
    model = FakeModel()
    w = new_world(1)
    w.brain_mode = "fallback"
    for verb in ("insult", "challenge", "humiliate"):
        rules.act(w, verb, "kael", gateway=model)
    assert model.calls == [] and all(d.source == "fallback" for d in w.decisions)


def test_state_pack_holds_what_the_npc_knows_and_never_truth():
    model = FakeModel()
    play_demo(model)
    detain = next(p for c, p in model.calls if c == "decide" and p.get("ALLOWED", [{}])[0].get("id") == "detain:kael")
    assert "truth" not in json.dumps(detain)  # the model never learns which beliefs are false
    assert any(b["claim"] == "Kael robbed Odo" for b in detain["beliefs"])  # the lie, held as a belief
    assert len(detain["beliefs"]) <= 5 and len(detain["events"]) <= 5
    assert [a["id"] for a in detain["ALLOWED"]] == ["detain:kael"]  # her duty (10) far outweighs waiting (1)
    assert detain["you"] == "Captain Brenna" and "bridge" in detain["setting"]
    talk = next(p for c, p in model.calls if c == "react" and "What did you see?" in p["situation"])
    assert talk["you"] == "Mags" and talk["situation"] == 'The player says to you: "What did you see?"'


def test_api_uses_the_apps_gateway(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from games.crypt_road.app import app
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    with TestClient(app) as client:
        app.state.gateway = FakeModel()
        session = client.post("/session", json={}).json()["session"]
        r = client.post("/act", json={"verb": "insult", "target": "kael"}, headers={"X-Session": session}).json()
        assert r["replies"][0]["source"] == "llm" and r["replies"][0]["line"] == "So be it."


def test_a_moving_player_is_on_the_road_during_the_tick():
    """NPCs decide on start-of-phase positions: a player who moves this phase isn't with them yet."""
    model = FakeModel()
    w, _ = play_demo(model)
    decides = [p for c, p in model.calls if c == "decide"]
    accuse = next(p for p in decides if p["ALLOWED"][0]["id"] == "accuse:player")  # tick 2: you are still on the road
    assert accuse["here"] == ["Brenna", "Odo"]
    assert not any("The player walked" in e["what"] for e in accuse["events"])
    detain = next(p for p in decides if p["ALLOWED"][0]["id"] == "detain:kael")  # tick 3: you started it at her gate
    assert "the player" in detain["here"]
    assert not any("to the bridge" in e["what"] for e in detain["events"])  # but she can't see you leave yet
    move_ids = {e.id for e in w.ledger if e.verb == "move" and e.actor == "player"}
    assert not any(set(d.cites) & move_ids for d in w.decisions if d.kind == "decide")
