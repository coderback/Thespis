"""#35: the manor mystery, a second game on the same core, solved by script and lost three ways."""

import ast
import pathlib

import pytest

from games.manor import content as C
from games.manor import rules, views, voice
from games.manor.content import new_world
from tests.test_model_voice import FakeModel
from thespis.deception import SAID
from tools.manor_solve import SOLVE


def play(w, steps, **kw):
    return [rules.act(w, verb, target, topic, **kw) for verb, target, topic in steps]


def last(w, npc):
    return [d for d in w.decisions if d.npc == npc][-1]


def test_the_morning_is_in_the_ledger_before_you_arrive():
    w = new_world()
    assert [(e.verb, e.truth) for e in w.ledger] == [("take", True), ("leave", True), ("tell", False), ("arrive", True)]
    assert (w.phase, w.player["loc"]) == (C.ARRIVAL, "hall")
    assert w.beliefs.conf("vane", C.THE_ALIBI) == 0.9 and w.beliefs.conf("pell", C.THE_TRUTH) == 1.0
    assert not w.ledger.happened(C.THE_ALIBI) and w.ledger.happened(C.THE_TRUTH)
    # No one saw the theft, though it happened in Pell's study: only Sable can cite it.
    assert [n for n in w.npcs if voice.knows(w, n, "e0001")] == ["sable"]
    assert [n for n in w.npcs if voice.knows(w, n, "e0002")] == ["pell", "sable"]


def test_the_scripted_solve_wins():
    w = new_world()
    play(w, SOLVE)
    assert (w.status, w.ended_at, w.player["outcome"]) == ("won", 5, rules.OUTCOMES["won"])
    assert w.beliefs.get("vane", C.THE_ALIBI).status == "retracted"  # Pell's word beat Sable's
    assert w.npcs["vane"].trust_in["sable"] == 2 - C.CONTRADICTED


def test_sables_lie_is_a_validated_action_logged_false():
    w = new_world()
    play(w, SOLVE[:2])
    d = last(w, "sable")
    assert (d.kind, d.allowed, d.chosen) == ("decide", ["deceive:alibi", "deflect"], "deceive:alibi")
    lie = w.ledger.get(d.asserted)
    assert (lie.verb, lie.actor, lie.target, lie.truth) == ("tell", "sable", "player", False)
    assert d.asserted in d.cites and SAID not in d.cites  # the line points at the statement it made
    shown = next(x for x in views.state_view(w)["decisions"] if x["id"] == d.id)
    assert shown["knew"] == [w.beliefs.get("sable", C.THE_TRUTH).id]  # she knew she was in the study: a lie


@pytest.mark.parametrize("steps, why", [
    ([("accuse", "sable", None)], "lost_alibi"),  # too early: Lady Vane still believes the alibi
    (SOLVE[:-1] + [("accuse", "pell", None)], "lost_innocent"),
    ([("move", r, None) for r in ("kitchen", "study", "kitchen", "study", "kitchen")], "constable"),
])
def test_wrong_turns_lose(steps, why):
    w = new_world()
    play(w, steps)
    assert (w.status, w.player["outcome"]) == ("lost", rules.OUTCOMES[why])


def test_questioning_needs_a_lead_and_the_rules_hold():
    w = new_world()
    q = next(v for v in rules.allowed(w) if v["verb"] == "request_questioning" and v["target"] == "pell")
    assert not q["enabled"] and q["reason"] == "Ask Pell about this morning first"
    for verb, target, topic in [("request_questioning", "pell", None), ("ask", "sable", "morning"),
                                ("ask", "vane", "the weather")]:
        with pytest.raises(rules.NotAllowed):
            rules.act(w, verb, target, topic)


def liar(line, action="deceive:alibi", cite_said=True):
    """A model that answers Sable's question with `action` and `line`, and everything else as a good model would."""
    def reply(call_type, pack):
        if call_type == "decide":
            return {"action": action, "line": line, "cites": [SAID] if cite_said else [pack["events"][-1]["id"]]}
        return FakeModel.good(call_type, pack)
    return FakeModel(reply)


def asked_sable(model):
    w = new_world()
    rules.act(w, "move", "kitchen")
    rules.act(w, "ask", "sable", "morning", gateway=model)
    return w, last(w, "sable")


def test_the_model_tells_the_lie_and_must_cite_it():
    w, d = asked_sable(liar("The kitchen, all morning. I swear it."))
    assert (d.source, d.line) == ("llm", "The kitchen, all morning. I swear it.")
    assert w.ledger.get(d.asserted).truth is False and d.cites == [d.asserted]
    w, d = asked_sable(liar("The kitchen, all morning.", cite_said=False))
    assert d.source == "fallback" and "without citing" in d.reason
    assert w.ledger.get(d.asserted).truth is False  # the utility brain still lies; the template line cites it


def test_the_model_may_deflect_instead():
    w, d = asked_sable(liar("Busy day. I couldn't say.", action="deflect", cite_said=False))
    assert (d.chosen, d.source, d.asserted) == ("deflect", "llm", None)
    assert not any(e.verb == "tell" and e.actor == "sable" and e.phase > 1 for e in w.ledger)


def test_the_manor_never_imports_the_crypt_road():
    for path in pathlib.Path(C.__file__).parent.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not any(n.startswith("games.crypt_road") for n in names), path


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from games.crypt_road.app import app
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    with TestClient(app) as c:
        app.state.gateway = FakeModel()
        yield app, c


def test_the_api_solves_it_and_serves_the_page(client):
    app, c = client
    page = c.get("/manor/")
    assert page.status_code == 200 and "The Manor Mystery" in page.text
    h = {"X-Session": c.post("/manor/session").json()["session"]}
    refused = c.post("/manor/act", json={"verb": "ask", "target": "sable", "topic": "morning"}, headers=h)
    assert refused.status_code == 409  # she's in the kitchen, not the hall
    for verb, target, topic in SOLVE:
        out = c.post("/manor/act", json={"verb": verb, "target": target, "topic": topic}, headers=h)
        assert out.status_code == 200, out.text
    state = out.json()["state"]
    assert state["status"] == "won" and state["outcome"] == rules.OUTCOMES["won"]
    alibi = next(b for b in state["beliefs"] if b["npc"] == "vane" and "kitchen" in b["claim"])
    assert (alibi["status"], alibi["truth"]) == ("retracted", False)
    assert app.state.store.calls_made() > 0  # counted with The Crypt Road's calls, against the global cap
    assert c.get("/state", headers=h).status_code == 404  # a manor session is invisible to The Crypt Road
