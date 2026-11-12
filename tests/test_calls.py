"""A call is checked against the game before it changes anything: a slip in a name is refused, saying what was
probably meant, instead of being taken as new or failing with a Python KeyError. Each of these used to be accepted,
or to fail as a KeyError, for a newcomer building a game from the docs."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from thespis.api import Game, Session
from thespis.considerations import DefinitionError
from thespis.server import create_app
from thespis.session import Unknown

ROOT = Path(__file__).resolve().parents[1]
QUICKSTART = (ROOT / "examples" / "quickstart" / "game.toml").read_text(encoding="utf-8")
GAME = Game.parse(QUICKSTART, "quickstart")
THEFT = {"pred": "stole_from", "a": "player", "b": "mara"}
# A moment whose choices bind who they're about, as a guard's would.
BOUND = Game.parse(QUICKSTART.replace("[[npc.mara.choices.counter]]\ndo = \"serve:player\"",
                                      "[[npc.mara.choices.greet]]\ndo = \"serve:{who}\"\nutility = 1\n"
                                      "when = [{ with = \"{who}\" }]\n\n[[npc.mara.choices.counter]]\n"
                                      "do = \"serve:player\"", 1), "quickstart")


def session(game: Game = GAME) -> Session:
    return Session.new(game)


@pytest.mark.parametrize("call, error, says", [
    (lambda s: s.observe("steal", "playr", at="bakery"), Unknown, "actor: no npc or player 'playr'; did you mean "
                                                                  "player?"),
    (lambda s: s.observe("steal", "player", "marra"), Unknown, "target: no npc, player or place 'marra'; did you mean "
                                                               "mara?"),
    (lambda s: s.observe("steal", "player", at="bakry"), Unknown, "at: no place 'bakry' in [places]; did you mean "
                                                                  "bakery?"),
    (lambda s: s.observe("steal", "player", witnesses="wat"), DefinitionError, "witnesses: a list of ids, not one "
                                                                               "string"),
    (lambda s: s.observe("steal", "player", witnesses=["watt"]), Unknown, "witnesses: no npc or player 'watt'; did "
                                                                          "you mean wat?"),
    (lambda s: s.observe("tell", "player", "mara", claim={"predicate": "stole_from", "a": "wat"}, said=True),
     DefinitionError, "claim: needs pred and a"),
    (lambda s: s.observe("tell", "player", "mara", claim={**THEFT, "nag": True}, said=True), DefinitionError,
     "claim: unknown key 'nag'; did you mean neg?"),
    (lambda s: s.observe("tell", "player", "mara", claim={**THEFT, "pred": "murdered"}, said=True), Unknown,
     "claim.pred: no predicate 'murdered' in [words.claims]"),
    (lambda s: s.observe("tell", "player", "mara", claim={**THEFT, "a": "bob"}, said=True), Unknown,
     "claim.a: no npc or player 'bob'"),
    (lambda s: s.update("player", loc="moon"), Unknown, "loc: no place 'moon' in [places]"),
    (lambda s: s.update("mara", nudge={"angr": 3}), Unknown, "nudge.angr: no NPC has a drive 'angr'; did you mean "
                                                             "anger?"),
    (lambda s: s.update("mara", trust_in={"eda": 1}), Unknown, "trust_in.eda: no npc or player 'eda'; did you mean "
                                                               "edda?"),
    (lambda s: s.update("player", drives={"anger": 3}), DefinitionError, "a player has only a place"),
    (lambda s: s.decide("mara", "countr"), Unknown, "mara has no choices for 'countr'; it has 'counter'; did you mean "
                                                    "counter?"),
    (lambda s: s.react("mara", "sneezed"), Unknown, "no NPC has a line for 'sneezed'"),
    (lambda s: s.react("mara", "refuze"), Unknown, "no NPC has a line for 'refuze'; did you mean refuse?"),
    (lambda s: s.tick(-3), DefinitionError, "steps: how many ticks, a whole number from 0, got -3"),
])
def test_a_slip_in_a_call_says_what_was_meant(call, error, says):
    s = session()
    before = s.snapshot()
    with pytest.raises(error) as e:
        call(s)
    assert says in str(e.value)
    assert s.snapshot() == before  # refused before anything changed


def test_a_decision_names_the_bindings_it_needs():
    s = session(BOUND)
    with pytest.raises(DefinitionError, match=r"mara's choices for 'greet' need bindings: 'who' \(decide\(\.\.\., "
                                              r"bindings=\{'who': \.\.\.\}\)\)"):
        s.decide("mara", "greet")
    with pytest.raises(Unknown, match="bindings.who: no npc or player 'bob'"):
        s.decide("mara", "greet", bindings={"who": "bob"})
    s.update("player", loc="bakery")
    s.observe("steal", "player", at="bakery", claim=THEFT, witnesses=["wat"])  # something for her line to cite
    assert s.decide("mara", "greet", bindings={"who": "player"}).action == "serve:player"


def test_an_npc_with_no_line_for_a_trigger_others_have_stays_silent():
    s = session()
    s.observe("steal", "player", at="bakery", claim=THEFT, witnesses=["wat"])
    assert s.react("wat", "refuse").text is None  # Mara has a refuse line; Wat hasn't


def test_a_damaged_snapshot_is_refused_by_name(tmp_path):
    s = session()
    snap = s.snapshot()
    for bad, says in (({}, "not a Thespis save"), ([1, 2], "not a Thespis save"),
                      ({**snap, "world": {"seed": 0}}, "a damaged snapshot: KeyError")):
        with pytest.raises(DefinitionError, match=says):
            Session.restore(GAME, bad)  # type: ignore[arg-type]


def test_over_http_a_slip_is_a_4xx_with_its_reason():
    client = TestClient(create_app({"quickstart": GAME}))
    sid = client.post("/v1/sessions", json={"game": "quickstart"}).json()["session"]
    r = client.post(f"/v1/sessions/{sid}/observe", json={"verb": "steal", "actor": "player", "at": "bakry"})
    assert (r.status_code, r.json()["reason"]) == (404, "at: no place 'bakry' in [places]; did you mean bakery?")
    snap = client.get(f"/v1/sessions/{sid}/snapshot").json()
    r = client.post("/v1/sessions", json={"game": "quickstart", "snapshot": {**snap, "world": {"seed": 0}}})
    assert r.status_code == 400 and r.json()["reason"].startswith("a damaged snapshot")
