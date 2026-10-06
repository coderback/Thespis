"""#17: with the model on, NPCs speak through it; code makes every choice, anything invalid falls back, and the model
never sees truth."""

import json

import pytest

from games.crypt_road import rules
from games.crypt_road.content import new_world
from tests.test_voice import check_cites
from thespis import expression
from thespis.gateway import ModelReply

LIE = {"pred": "robbed", "a": "kael", "b": "odo"}


class FakeModel:
    """A scripted model. By default it says a short line citing the first reference in its state pack, which is what
    a well-behaved model does. Asked to extract a line's claims (thespis.claims), it answers `extract(request)`:
    by default, that the line claims nothing."""

    providers = ("fake/model",)
    models = ("model",)

    def __init__(self, reply=None, extract=None):
        self.reply = reply or self.good
        self.extract = extract or (lambda request: {"claims": []})
        self.calls = []  # (call_type, state pack as sent)
        self.schemas = []

    @staticmethod
    def good(call_type, pack):
        first = (pack["beliefs"] + pack["events"])[0]["id"]
        return {"cites": [first], "line": "So be it."}

    def complete(self, call_type, messages, schema=None):
        pack = json.loads(messages[1]["content"])
        self.calls.append((call_type, pack))
        self.schemas.append(schema)
        data = self.extract(pack) if call_type == "extract" else self.reply(call_type, pack)
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
    assert calls.count("act") == 4 and 10 <= len(calls) <= 25  # about the design's budget for the route


def test_with_the_model_on_every_route_ends_as_with_it_off():
    """Code makes every choice, so the model can change what NPCs say, but never what happens."""
    from rehearsal.scenarios import Stage
    from tools.routes import ROUTES, seed_for
    from tools.routes import play as play_route

    for name in ROUTES:
        worlds = []
        for gateway in (None, FakeModel()):
            s = Stage(gateway, brain="model" if gateway else "fallback").crypt_road(seed_for(name, 1))
            play_route(s, name)
            worlds.append(s.w)
        off, on = worlds
        assert on.ledger.to_json() == off.ledger.to_json(), name
        assert [(d.npc, d.chosen) for d in on.decisions] == [(d.npc, d.chosen) for d in off.decisions], name


def test_default_plans_make_no_model_call():
    model = FakeModel()
    w = new_world(1)
    rules.act(w, "move", gateway=model)  # Kael walks on with nothing new on his mind
    assert model.calls == []
    assert w.decisions.tail(1)[0].source == "fallback"


def test_the_model_only_words_what_code_chose():
    """The pack says what the NPC is doing, with no other options and no pulls; a reply can't change it."""
    def picky(call_type, pack):
        return {**FakeModel.good(call_type, pack), "action": "wait"}  # a stray field is ignored

    model = FakeModel(picky)
    w = new_world(1)
    for verb in ("insult", "challenge", "humiliate"):
        rules.act(w, verb, "kael", gateway=model)
    d = next(d for d in w.decisions if d.npc == "kael" and d.kind == "decide")
    assert (d.chosen, d.source) == ("go_to", "llm") and d.allowed == ["go_to", "wait"]
    acting = next(p for c, p in model.calls if c == "act")
    assert acting["DOING"] == {"does": "walk on towards the relic, to the market"} and "ALLOWED" not in acting
    assert "pull" not in json.dumps(acting)


def test_a_clear_grudge_is_acted_on_and_voiced():
    model = FakeModel()
    play_demo(model)
    accuse = next(p for c, p in model.calls if c == "act" and "tell the Captain" in p["DOING"]["does"])
    assert accuse["DOING"] == {"does": "tell the Captain what the player did to you; she trusts you and will stop "
                                       "them at the gate"}
    assert accuse["situation"] == "You are at the guard post."


def test_every_call_may_cite_exactly_its_packs_references():
    model = FakeModel()
    play_demo(model)
    assert model.schemas
    for (_, pack), schema in zip(model.calls, model.schemas):
        refs = [b["id"] for b in pack["beliefs"]] + [e["id"] for e in pack["events"]]
        assert schema == expression.schema_for(refs)


@pytest.mark.parametrize("bad,why", [
    ({"cites": ["e9"]}, "cites e9, not in its state pack"),
    ({"cites": ["e0001"]}, "cites e0001, not in its state pack"),  # a ledger id, not one of the pack's references
    ({"cites": []}, "no cites"),
    ({"line": "x" * 161}, "line is 161 characters, over 160"),
    ({"line": "Brenna will hear of this."}, "names brenna, absent from its state pack"),
    ({"line": "   "}, "no line"),
])
def test_invalid_replies_fall_back(bad, why):
    def broken(call_type, pack):
        data = FakeModel.good(call_type, pack)
        if call_type == "act":
            data.update(bad)
        return data
    w = new_world(1)
    for verb in ("insult", "challenge", "humiliate"):
        rules.act(w, verb, "kael", gateway=FakeModel(broken))
    d = next(d for d in w.decisions if d.npc == "kael" and d.kind == "decide")
    assert (d.chosen, d.source) == ("go_to", "fallback")  # the utility brain's choice and template line
    assert f"model reply rejected: {why}" in d.reason
    assert d.line == "Out of my way." and d.cites


def test_cites_come_back_as_ledger_and_belief_ids():
    model = FakeModel(lambda call_type, pack: {"cites": [pack["events"][-1]["id"], pack["beliefs"][0]["id"]],
                                               "line": "Mind yourself."})
    w = new_world(1)
    rules.act(w, "insult", "kael", gateway=model)
    d = w.decisions.tail(1)[0]
    assert (d.source, d.cites) == ("llm", ["e0001", "b0003"])  # e1 and b1 in Kael's pack


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
    detain = next(p for c, p in model.calls if c == "act" and p["DOING"]["does"].startswith("have the sergeant"))
    assert "truth" not in json.dumps(detain)  # the model never learns which beliefs are false
    assert any(b["claim"] == "Kael robbed Odo" for b in detain["beliefs"])  # the lie, held as a belief
    assert len(detain["beliefs"]) <= 5 and len(detain["events"]) <= 5
    assert [b["id"] for b in detain["beliefs"]] == [f"b{i}" for i in range(1, len(detain["beliefs"]) + 1)]
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
    acts = [p for c, p in model.calls if c == "act"]
    accuse = next(p for p in acts if "tell the Captain" in p["DOING"]["does"])  # tick 2: you are still on the road
    assert accuse["here"] == ["Brenna", "Odo"]
    assert not any("The player walked" in e["what"] for e in accuse["events"])
    detain = next(p for p in acts if p["DOING"]["does"].startswith("have the sergeant"))  # tick 3: at her gate
    assert "the player" in detain["here"]
    assert not any("to the bridge" in e["what"] for e in detain["events"])  # but she can't see you leave yet
    move_ids = {e.id for e in w.ledger if e.verb == "move" and e.actor == "player"}
    assert not any(set(d.cites) & move_ids for d in w.decisions if d.kind == "decide")


def test_a_reply_may_name_whoever_the_player_mentioned():
    """Asked "Is the Captain fair?", Mags may answer about the Captain, though Brenna isn't otherwise in her pack."""
    from games.crypt_road import voice
    w = new_world(1)
    rules.act(w, "insult", "kael")
    asked = voice.pack_for(w, "mags", 'The player says to you: "Is the Captain fair?"')
    unasked = voice.pack_for(w, "mags", 'The player says to you: "Nice night."')
    reply = {"line": "The Captain? Fair enough, if you pay your fines.", "cites": ["e1"]}
    assert voice.VALIDATOR.problem(reply, asked, "react") is None
    assert "brenna" in voice.VALIDATOR.problem(reply, unasked, "react")


def test_the_witness_knows_who_is_asking():
    """#70: Odo was told only "The Captain asks", so he called her Brenna as if she weren't there."""
    model = FakeModel()
    play_demo(model)
    testify = next(p for c, p in model.calls if c == "react" and p["you"] == "Odo" and "never happened" in p["situation"])
    assert testify["situation"].startswith("Captain Brenna asks you whether")
