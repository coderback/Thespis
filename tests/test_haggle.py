"""#36: Brenna haggles over her fine. Code sets her price and what she may do; the model chooses and words it."""

import pytest

from games.crypt_road import content as C
from games.crypt_road import rules
from games.crypt_road.content import new_world
from games.crypt_road.voice import numbers
from tests.test_model_voice import FakeModel
from thespis.ledger import Event


def at_the_gate():
    """The demo route to the guard post: Kael has reported you, so Brenna's trust in you is -2 and her price 20."""
    w = new_world(C.DEMO_SEED)
    for verb in ("insult", "challenge", "humiliate"):
        rules.act(w, verb, "kael")
    rules.act(w, "move")
    rules.act(w, "move")
    assert (w.player, w.npcs["brenna"].trust_in["player"]) == ({"loc": "guard_post", "coins": 40}, -2)
    return w


def option(w, verb, target=None):
    return next(o for o in rules.allowed(w) if o["verb"] == verb and o["target"] == target)


def test_her_price_stays_in_bounds():
    for trust in range(-5, 6):
        price = C.asking_price(trust)
        assert C.PRICE_MIN <= price <= C.PRICE_MAX
        if trust < 0:
            assert price >= C.FINE
    assert [C.asking_price(t) for t in (2, 0, -1, -2, -3, -4, -5)] == [15, 15, 20, 20, 25, 30, 30]


def test_an_offer_of_10_gets_a_counter_and_paying_it_opens_the_gate():
    w = at_the_gate()
    res = rules.act(w, "bribe", "brenna", amount=10)
    assert [(e.verb, e.amount) for e in res.events] == [("offer", 10), ("counter", 20)]
    assert w.player["coins"] == 40 and w.npcs["brenna"].trust_in["player"] == -2  # nothing paid, nothing gained
    assert not option(w, "move")["enabled"]
    [reply] = res.replies
    assert (reply["npc"], reply["line"], reply["source"]) == ("brenna", "10 coins? Make it 20, and I never saw you.",
                                                              "fallback")
    assert reply["cites"] == [res.events[0].id]
    assert option(w, "bribe", "brenna")["args"] == {"amount": 20, "min": 1, "max": 40}  # her counter, suggested

    res = rules.act(w, "bribe", "brenna", amount=20)
    assert [(e.verb, e.amount) for e in res.events] == [("bribe", 20)]
    assert w.player["coins"] == 20 and w.npcs["brenna"].trust_in["player"] == 0
    assert option(w, "move")["enabled"]
    assert res.replies[0]["line"] == "For 20 coins, I was looking the other way."


def test_a_lowball_is_refused_and_she_hears_no_more_offers_this_phase():
    w = at_the_gate()
    res = rules.act(w, "bribe", "brenna", amount=5)
    assert [e.verb for e in res.events] == ["offer", "refuse"]
    assert res.replies[0]["line"] == "Keep your 5 coins, before I add bribery to the charge."
    bribe = option(w, "bribe", "brenna")
    assert not bribe["enabled"] and bribe["reason"] == "Brenna won't hear another offer until the next phase"
    with pytest.raises(rules.NotAllowed):
        rules.act(w, "bribe", "brenna", amount=20)
    rules.act(w, "wait")
    assert option(w, "bribe", "brenna")["enabled"]


@pytest.mark.parametrize("amount", [0, -5, 41, 2.5, True, "20"])
def test_an_offer_must_be_whole_coins_the_player_has(amount):
    w = at_the_gate()
    before = len(w.ledger)
    with pytest.raises(rules.NotAllowed, match="Offer between 1 and 40 coins"):
        rules.act(w, "bribe", "brenna", amount=amount)
    assert len(w.ledger) == before and w.player["coins"] == 40


def haggler(line):
    """A model that words Brenna's answer to an offer with `line`, and everything else as a good model would."""
    def reply(call_type, pack):
        if call_type == "act" and "coins to forget" in pack["situation"]:
            return {"cites": [(pack["beliefs"] + pack["events"])[0]["id"]], "line": line}
        return FakeModel.good(call_type, pack)
    return FakeModel(reply)


def haggle(model, amount=10):
    w = at_the_gate()
    res = rules.act(w, "bribe", "brenna", amount=amount, gateway=model)
    return w, res, [d for d in w.decisions if d.trigger == "bribe_offer"][-1]


def test_code_counters_or_refuses_and_the_model_words_it():
    """Under her price of 20, she refuses a lowball (under half of it) and counters anything else."""
    w, res, d = haggle(haggler("Ten? Make it twenty, or turn back."))
    assert (d.chosen, d.source, d.allowed) == ("counter:20", "llm", ["counter:20", "refuse"])
    assert res.events[-1].verb == "counter"
    assert res.replies[0] == {"decision": d.id, "npc": "brenna", "line": "Ten? Make it twenty, or turn back.",
                              "cites": d.cites, "source": "llm"}
    w, res, d = haggle(haggler("Five coins? I'd sooner arrest you."), amount=5)
    assert (d.chosen, d.source) == ("refuse", "llm") and res.events[-1].verb == "refuse"


def test_the_model_can_never_accept_under_her_price():
    w, res, d = haggle(haggler("Fine, ten will do."))
    assert d.chosen == "counter:20"  # whatever it says, code chose the counter
    assert w.player["coins"] == 40 and res.events[-1].verb == "counter"


def test_a_counter_naming_another_price_is_refused():
    w, res, d = haggle(haggler("Make it 25 and we'll talk."))
    assert d.source == "fallback" and "neither the offer nor the price" in d.reason
    assert res.replies[0]["line"] == "10 coins? Make it 20, and I never saw you."
    w, res, d = haggle(haggler("Ten? Make it twenty-five, or turn back."))  # in words too
    assert d.source == "fallback"
    w, res, d = haggle(haggler("Ten? Make it twenty, or turn back."))
    assert (d.source, res.replies[0]["line"]) == ("llm", "Ten? Make it twenty, or turn back.")


def test_numbers_in_words_and_digits():
    assert numbers("Twenty coins, not 15. Thirty-five? Ten!") == {20, 15, 35, 10}
    assert numbers("No one crosses, often or twentyish.") == set()  # small words and look-alikes aren't sums


def test_events_without_an_amount_serialise_as_before():
    e = Event("e0001", 0, "insult", "player", "kael", "tavern")
    assert "amount" not in e.to_json()
    paid = Event("e0002", 3, "bribe", "player", "brenna", "guard_post", amount=20)
    assert paid.to_json()["amount"] == 20 and Event.from_json(paid.to_json()) == paid
    assert Event.from_json(e.to_json()) == e


def test_the_api_offers_and_refuses_bad_amounts(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from games.crypt_road.app import app
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    with TestClient(app) as client:
        h = {"X-Session": client.post("/session", json={}).json()["session"]}
        for step in ({"verb": "insult", "target": "kael"}, {"verb": "challenge", "target": "kael"},
                     {"verb": "humiliate", "target": "kael"}, {"verb": "move"}, {"verb": "move"}):
            assert client.post("/act", json=step, headers=h).status_code == 200
        bribe = next(v for v in client.get("/allowed", headers=h).json()["verbs"] if v["verb"] == "bribe")
        assert (bribe["label"], bribe["args"]) == ("Bribe Brenna...", {"amount": 20, "min": 1, "max": 40})
        assert client.post("/act", json={"verb": "bribe", "target": "brenna", "amount": 99}, headers=h).status_code == 409
        out = client.post("/act", json={"verb": "bribe", "target": "brenna", "amount": 10}, headers=h).json()
        assert [(e["verb"], e.get("amount")) for e in out["events"]] == [("offer", 10), ("counter", 20)]
