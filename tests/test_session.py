"""The engine-facing calls (thespis.session), in the library and over /v1 (thespis.server): a world the engine owns,
minds Thespis owns, lines that arrive provisional, and saves that restore exactly."""

import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_model_voice import FakeModel
from thespis.__main__ import openapi
from thespis.api import FINAL, PROVISIONAL, WITHDRAWN, DefinitionError, Game, Session, Unknown
from thespis.server import create_app

ROOT = Path(__file__).resolve().parents[1]
TAVERN = Game.load(ROOT / "examples" / "tavern" / "game.toml")
INSULT = {"pred": "insulted", "a": "player", "b": "garrick"}


def insulted(s: Session) -> None:
    s.observe("insult", "player", "garrick", claim=INSULT, witnesses=["wren"])


def test_a_deed_is_believed_by_who_saw_it_and_who_took_part():
    s = Session.new(TAVERN)
    insulted(s)
    held = {n: [b["status"] for b in s.inspect(n)["beliefs"]] for n in ("garrick", "wren", "pip")}
    assert held == {"garrick": ["active"], "wren": ["active"], "pip": []}  # pip is in the yard
    assert s.world.beliefs.conf("wren", s.world.ledger.get("e0001").claimed) == 1.0


def test_what_is_said_is_believed_as_far_as_the_hearer_trusts_the_speaker():
    s = Session.new(TAVERN)
    lie = {"pred": "insulted", "a": "garrick", "b": "wren"}
    e = s.observe("tell", "player", "wren", claim=lie, said=True)
    assert e.truth is False  # the ledger shows no such thing
    assert [b["opinion"]["b"] for b in s.inspect("wren")["beliefs"]] == [0.4]  # trust 0: credence 0.4
    s.update("wren", trust_in={"player": 3})
    s.observe("tell", "player", "wren", claim=lie, said=True)
    assert s.inspect("wren")["beliefs"][0]["opinion"]["b"] == 0.9  # one teller counts once, at its most trusted


def test_an_npc_cites_only_what_it_saw():
    s = Session.new(TAVERN)
    assert s.react("garrick", "talk").text is None  # nothing has happened that he knows of
    insulted(s)
    talk = s.react("garrick", "talk")
    assert (talk.text, talk.cites, talk.status) == ("Speak quickly. I have a road to run.", ["e0001"], FINAL)
    assert s.react("pip", "talk").id is None  # in the yard: he saw nothing


def test_choices_are_the_games_and_follow_the_engines_changes():
    s = Session.new(TAVERN)
    insulted(s)
    first = s.decide("garrick", "turn")
    assert (first.action, first.reason, first.cites) == ("leave", "leave scores 5", ["e0001"])
    s.update("garrick", nudge={"grudge": 4})
    second = s.decide("garrick", "turn")
    assert (second.action, second.text) == ("confront:player", "You. Say it again, to my face.")
    s.update("player", loc="yard")  # out of reach: he can't confront someone who isn't there
    assert s.decide("garrick", "turn").action == "leave"
    assert [d.chosen for d in s.world.decisions] == ["leave", "confront:player", "leave"]


def test_drives_stay_in_range_and_flags_clear():
    s = Session.new(TAVERN)
    assert s.update("garrick", nudge={"grudge": 40}, flags={"gone": True})["drives"]["grudge"] == 10
    assert s.update("garrick", flags={"gone": None})["flags"] == {}
    assert s.update("garrick", trust_in={"player": -9})["trust_in"]["player"] == -5


def test_the_tick_walks_gossips_and_settles():
    s = Session.new(TAVERN)
    insulted(s)
    s.update("garrick", nudge={"grudge": 3})
    t = s.tick()
    assert t.moves == [{"who": "pip", "from": "yard", "to": "taproom"}]
    assert [(e.verb, e.actor, e.target) for e in t.events] == [("move", "pip", "taproom"), ("gossip", "wren", "pip")]
    assert s.inspect("pip")["beliefs"][0]["opinion"]["b"] == 0.8  # wren's certainty times the decay
    assert s.world.npcs["garrick"].drives["grudge"] == 2 and s.world.phase == 1  # one step back towards rest
    assert s.react("pip", "told").cites == ["e0003"]  # he heard it, so he knows it


def test_a_snapshot_restores_the_same_minds_and_plays_on_the_same():
    a = Session.new(TAVERN)
    insulted(a)
    a.tick(2)
    snap = json.loads(json.dumps(a.snapshot()))  # through a save file
    b = Session.restore(TAVERN, snap)
    assert b.snapshot() == a.snapshot()
    for s in (a, b):
        s.update("garrick", nudge={"grudge": 5})
        s.decide("garrick", "turn")
        s.tick()
    assert b.snapshot() == a.snapshot()


def test_a_snapshot_read_as_floats_restores_the_same():
    """GDScript reads every JSON number as a float; a save that went through Godot must still restore exactly."""
    def floats(x):
        if isinstance(x, dict):
            return {k: floats(v) for k, v in x.items()}
        if isinstance(x, list):
            return [floats(v) for v in x]
        return float(x) if isinstance(x, int) and not isinstance(x, bool) else x

    a = Session.new(TAVERN)
    insulted(a)
    a.tick()
    b = Session.restore(TAVERN, floats(a.snapshot()))
    assert b.snapshot() == a.snapshot()
    assert b.decide("garrick", "turn").reason == "leave scores 5"


def test_the_model_is_not_asked_when_there_is_nothing_to_cite():
    model = FakeModel()
    s = Session.new(TAVERN, gateway=model)
    line = s.decide("garrick", "turn", wait=False)  # he knows nothing yet
    assert (line.status, line.text, line.action) == (FINAL, None, "leave") and model.calls == []


def test_a_snapshot_of_another_game_or_version_is_refused():
    snap = Session.new(TAVERN).snapshot()
    with pytest.raises(DefinitionError, match="not 'tavern'"):
        Session.restore(TAVERN, {**snap, "game": "manor"})
    with pytest.raises(DefinitionError, match="version"):
        Session.restore(TAVERN, {**snap, "thespis": 99})


def test_unknown_names_are_errors_not_silence():
    s = Session.new(TAVERN)
    for call in (lambda: s.decide("nobody", "turn"), lambda: s.decide("wren", "turn"),
                 lambda: s.observe("insult", "player", "wren", witnesses=["ghost"]), lambda: s.line("d0099")):
        with pytest.raises(Unknown):
            call()


@pytest.mark.parametrize("change, message", [
    ({"npc": {}}, "at least one"),
    ({"npc": {"x": {"name": "X", "persona": "p", "goal": "g"}}}, "needs start"),
    ({"npc": {"x": {"name": "X", "persona": "p", "goal": "g", "start": "moon"}}}, "not in \\[places\\]"),
    ({"gossip": {"gossips": ["ghost"]}}, "not an npc"),
])
def test_a_broken_game_fails_when_it_loads(tmp_path, change, message):
    import tomllib
    data = {**tomllib.loads((ROOT / "examples" / "tavern" / "game.toml").read_text(encoding="utf-8")), **change}
    path = tmp_path / "game.toml"
    path.write_text(toml_dump(data), encoding="utf-8")
    with pytest.raises(DefinitionError, match=message):
        Game.load(path)


def toml_dump(d: dict, prefix: str = "") -> str:
    """Just enough TOML for these tests: tables of strings, numbers and lists, written with JSON's quoting."""
    flat = {k: v for k, v in d.items() if not isinstance(v, dict)}
    out = [f"[{prefix}]"] if prefix and flat else []
    out += [f"{k} = {json.dumps(v)}" for k, v in flat.items() if not (isinstance(v, list) and v and
                                                                      isinstance(v[0], dict))]
    for k, v in d.items():
        if isinstance(v, dict):
            out.append(toml_dump(v, f"{prefix}.{k}" if prefix else k))
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- provisional lines
class SlowModel(FakeModel):
    """A model that answers only when the test lets it."""

    def __init__(self):
        super().__init__(reply=lambda call_type, pack: {"cites": [pack["events"][0]["id"]], "line": "Watch it."})
        self.go = threading.Event()

    def complete(self, call_type, messages, schema=None):
        self.go.wait(5)
        return super().complete(call_type, messages, schema)


def test_a_line_arrives_provisional_and_the_models_words_follow():
    model = SlowModel()
    s = Session.new(TAVERN, gateway=model)
    insulted(s)
    line = s.react("garrick", "insulted", wait=False)
    assert (line.status, line.text, line.source) == (PROVISIONAL, "Careful, stranger.", "fallback")
    model.go.set()
    done = s.line(line.id, wait=5)
    assert (done.status, done.text, done.source, done.cites) == (FINAL, "Watch it.", "llm", ["e0001"])
    assert [d.line for d in s.world.decisions] == ["Watch it."]  # the record holds what was finally said


def test_waiting_gives_the_final_line_at_once():
    s = Session.new(TAVERN, gateway=FakeModel())
    insulted(s)
    line = s.decide("garrick", "turn")
    assert (line.status, line.source, line.text) == (FINAL, "llm", "So be it.")


def test_closing_withdraws_what_is_still_on_its_way():
    model = SlowModel()
    s = Session.new(TAVERN, gateway=model)
    insulted(s)
    line = s.react("garrick", "insulted", wait=False)
    s.close()
    model.go.set()
    assert s.line(line.id).status == WITHDRAWN


# ---------------------------------------------------------------- /v1
def play(call) -> list:
    """One scene, through `call(name, **body)`: the library's methods or the HTTP routes, which must agree."""
    return [
        call("observe", verb="insult", actor="player", target="garrick", claim=INSULT, witnesses=["wren"]),
        call("update", npc="garrick", nudge={"grudge": 4}),
        call("decide", npc="garrick", moment="turn"),
        call("react", npc="wren", trigger="talk"),
        call("tick", steps=2),
        call("narrate", since=0),
        call("inspect", npc="pip"),
    ]


def test_the_http_api_mirrors_the_library():
    lib = Session.new(TAVERN)

    def library(name, **body):
        if name == "inspect":
            return lib.inspect(**body)
        out = getattr(lib, name)(**body)
        if name == "observe":
            return {**out.to_json(), "claim": out.claim.to_json() if out.claim else None}
        if name == "tick":
            return {"phase": lib.world.phase, "moves": out.moves, "events": [e.to_json() for e in out.events]}
        return out if isinstance(out, dict) else out.to_json()

    client = TestClient(create_app({"tavern": TAVERN}))
    sid = client.post("/v1/sessions", json={"game": "tavern"}).json()["session"]

    def http(name, **body):
        if name == "inspect":
            r = client.get(f"/v1/sessions/{sid}/npcs/{body['npc']}")
        else:
            r = client.post(f"/v1/sessions/{sid}/{name}", json=body)
        assert r.status_code in (200, 201), r.text
        return r.json()

    def same(x):  # the HTTP reply lists every field; the library's JSON leaves defaults out
        if isinstance(x, dict):
            return {k: same(v) for k, v in x.items()
                    if v is not None and k != "schema_version" and not (k == "neg" and v is False)}
        return [same(v) for v in x] if isinstance(x, list) else x

    assert same(play(http)) == same(play(library))
    assert client.get(f"/v1/sessions/{sid}/snapshot").json() == lib.snapshot()


def test_http_errors_say_what_went_wrong():
    client = TestClient(create_app({"tavern": TAVERN}, max_sessions=1))
    assert client.post("/v1/sessions", json={"game": "chess"}).json() == {"error": "unknown",
                                                                          "reason": "no game 'chess'"}
    sid = client.post("/v1/sessions", json={"game": "tavern"}).json()["session"]
    assert client.post("/v1/sessions", json={"game": "tavern"}).status_code == 503
    r = client.post(f"/v1/sessions/{sid}/decide", json={"npc": "garrick"})
    assert (r.status_code, r.json()["error"]) == (400, "bad_request")
    r = client.post(f"/v1/sessions/{sid}/decide", json={"npc": "wren", "moment": "turn"})
    assert (r.status_code, r.json()["reason"]) == (404, "wren has no choices for 'turn'")
    assert client.delete(f"/v1/sessions/{sid}").status_code == 204
    assert client.get(f"/v1/sessions/{sid}/snapshot").status_code == 404


def test_a_session_restores_over_http():
    client = TestClient(create_app({"tavern": TAVERN}))
    sid = client.post("/v1/sessions", json={"game": "tavern"}).json()["session"]
    client.post(f"/v1/sessions/{sid}/observe", json={"verb": "insult", "actor": "player", "target": "garrick",
                                                     "claim": INSULT, "witnesses": ["wren"]})
    snap = client.get(f"/v1/sessions/{sid}/snapshot").json()
    again = client.post("/v1/sessions", json={"game": "tavern", "snapshot": snap}).json()["session"]
    assert client.get(f"/v1/sessions/{again}/snapshot").json() == snap
    assert client.get("/v1/games").json()[0]["choices"] == {"garrick": ["turn"]}


def test_the_committed_spec_is_the_api():
    """docs/openapi-v1.json is the SDKs' contract. Regenerate it with `python -m thespis openapi --out ...` and
    review the diff when this fails."""
    assert (ROOT / "docs" / "openapi-v1.json").read_text(encoding="utf-8") == openapi()
