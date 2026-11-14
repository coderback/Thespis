"""Catching a liar, trusting someone, and what a bribe is worth, in the game file's own words:
- a `caught` event when an NPC's story from someone loses to a truer one, which the game finds with `events(after=)`
  and choices with `{caught = "{who}"}`;
- `{trust = who, gte = n}`, a condition on the NPC's trust in someone;
- `{bound = name, weight = w}`, a utility term counting a number the game passed, such as a bribe's size."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from thespis.api import Game, Session
from thespis.considerations import DefinitionError
from thespis.ledger import CAUGHT
from thespis.server import create_app
from thespis.session import Unknown

ROOT = Path(__file__).resolve().parents[1]
QUICKSTART = (ROOT / "examples" / "quickstart" / "game.toml").read_text(encoding="utf-8")
THEFT = {"pred": "stole_from", "a": "player", "b": "mara"}
LIE = {**THEFT, "a": "wat"}  # the player blames Wat
EXTRA = '''
[[npc.mara.choices.counter2]]
do = "throw_out:{who}"
utility = 9
when = [{ caught = "{who}" }]

[[npc.mara.choices.counter2]]
do = "serve:{who}"
utility = 1

[[npc.mara.choices.offer]]
do = "accept:{who}"
utility = [{ bound = "amount", weight = 0.5 }, { drive = "anger", weight = -1 }]
when = [{ trust = "{who}", gte = 0 }]

[[npc.mara.choices.offer]]
do = "refuse:{who}"
utility = 4
'''


def caught_in_a_lie() -> tuple[Session, str]:
    s = Session.new(Game.parse(QUICKSTART + EXTRA, "quickstart"))
    s.observe("steal", "player", at="bakery", claim=THEFT, witnesses=["wat"])
    s.tick(2)  # the truth reaches Mara through Edda, whom she trusts
    told = s.observe("tell", "player", "mara", claim=LIE, said=True)
    return s, told.id


def test_a_liar_caught_is_an_event_the_game_can_find():
    s, told = caught_in_a_lie()
    [e] = s.events(after=told)
    assert (e.verb, e.actor, e.target, e.claim and e.claim.label(), e.truth) == \
        (CAUGHT, "mara", "player", "stole_from(wat, mara)", False)
    assert s.sentence(e) == "Mara caught the player in a lie: that Wat stole from Mara."
    assert s.events(verb=CAUGHT) == [e] and s.events(after=e.id) == []


def test_a_game_may_word_it_itself():
    s = Session.new(Game.parse(QUICKSTART.replace('steal = "', 'caught = "{a} saw through {t}."\nsteal = "'),
                               "quickstart"))
    s.observe("steal", "player", at="bakery", claim=THEFT, witnesses=["wat"])
    s.tick(2)
    s.observe("tell", "player", "mara", claim=LIE, said=True)
    assert s.sentence(s.events(verb=CAUGHT)[0]) == "Mara saw through the player."


def test_a_choice_can_turn_on_who_was_caught_and_says_why_not():
    s = Session.new(Game.parse(QUICKSTART + EXTRA, "quickstart"))
    s.update("player", loc="bakery")
    assert s.decide("mara", "counter2", {"who": "player"}).action == "serve:player"
    assert s.explain("mara", "counter2", {"who": "player"})[0]["blocked"] == "hasn't caught player in a lie"
    s, _ = caught_in_a_lie()
    assert s.decide("mara", "counter2", {"who": "player"}).action == "throw_out:player"


def test_caught_survives_a_save():
    s, _ = caught_in_a_lie()
    back = Session.restore(s.game, s.snapshot())
    assert back.world.ledger.caught("mara") == {"player"}
    assert back.decide("mara", "counter2", {"who": "player"}).action == "throw_out:player"


def test_a_bribe_counts_by_its_size_and_trust_gates_it():
    s = Session.new(Game.parse(QUICKSTART + EXTRA, "quickstart"))
    assert s.decide("mara", "offer", {"who": "player", "amount": 4}).action == "refuse:player"  # 2 < 4
    line = s.decide("mara", "offer", {"who": "player", "amount": 20}, explain=True)
    assert line.action == "accept:player"
    assert line.explain is not None and line.explain[0]["terms"] == ["amount 20 x 0.5 = 10", "anger 0 x -1 = 0"]
    s.update("mara", trust_in={"player": -2})
    e = s.explain("mara", "offer", {"who": "player", "amount": 20})
    assert e[0]["blocked"] == "trust in player is -2, needs >= 0"


def test_a_term_counts_a_drive_or_a_bound_value_not_both():
    bad = EXTRA.replace('{ bound = "amount", weight = 0.5 }', '{ bound = "amount", drive = "anger" }')
    with pytest.raises(DefinitionError, match="a drive or a bound value, not both"):
        Game.parse(QUICKSTART + bad, "quickstart")


def test_the_file_is_checked_for_whom_trust_and_caught_name():
    bad = EXTRA.replace('{ trust = "{who}", gte = 0 }', '{ trust = "edd", gte = 0 }')
    with pytest.raises(DefinitionError, match=r"trust: .*'edd'.*did you mean edda"):
        Game.parse(QUICKSTART + bad, "quickstart")
    with pytest.raises(DefinitionError, match="a trust condition needs one of"):
        Game.parse(QUICKSTART + EXTRA.replace('{ trust = "{who}", gte = 0 }', '{ trust = "{who}" }'), "quickstart")


def test_events_after_an_id_it_doesnt_have():
    s = Session.new(Game.parse(QUICKSTART, "quickstart"))
    with pytest.raises(Unknown, match="no event 'e0099'"):
        s.events(after="e0099")


def test_over_http():
    client = TestClient(create_app({"quickstart": Game.parse(QUICKSTART, "quickstart")}))
    sid = client.post("/v1/sessions", json={"game": "quickstart"}).json()["session"]
    client.post(f"/v1/sessions/{sid}/observe", json={"verb": "steal", "actor": "player", "at": "bakery",
                                                      "claim": THEFT, "witnesses": ["wat"]})
    client.post(f"/v1/sessions/{sid}/tick", json={"steps": 2})
    told = client.post(f"/v1/sessions/{sid}/observe", json={"verb": "tell", "actor": "player", "target": "mara",
                                                             "claim": LIE, "said": True}).json()["id"]
    r = client.get(f"/v1/sessions/{sid}/events", params={"after": told})
    assert r.status_code == 200 and [(e["verb"], e["actor"], e["target"]) for e in r.json()] == \
        [("caught", "mara", "player")]
    assert len(client.get(f"/v1/sessions/{sid}/events", params={"verb": "caught"}).json()) == 1
    assert client.get(f"/v1/sessions/{sid}/events", params={"after": "e0099"}).status_code == 404


def test_the_editors_schema_knows_them():
    import tomllib

    import jsonschema

    from thespis.gameschema import schema
    errors = list(jsonschema.Draft7Validator(schema()).iter_errors(tomllib.loads(QUICKSTART + EXTRA)))
    assert errors == []
