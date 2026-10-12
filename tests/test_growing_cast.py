"""A cast that grows in play (examples/town/game.toml): the game file declares kinds of people, and the engine adds
each person as one of a kind, ties them, and retires them. And one culprit per deed: of two stories about who did
it, the one from the less trusted source loses, and so does some trust in whoever told it."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from thespis.api import DefinitionError, Game, Session, Unknown
from thespis.ledger import Claim
from thespis.server import create_app

ROOT = Path(__file__).resolve().parents[1]
TOWN_TOML = (ROOT / "examples" / "town" / "game.toml").read_text(encoding="utf-8")
TOWN = Game.parse(TOWN_TOML, "town")
TAVERN = Game.load(ROOT / "examples" / "tavern" / "game.toml")
ROBBED = {"pred": "robbed", "a": "player", "b": "mara"}
BLAMED = {"pred": "robbed", "a": "harl", "b": "mara"}


def town() -> Session:
    """Wickby with four people in it: Mara and Wat at the docks, Edda in the market, Harl at the chapel."""
    s = Session.new(TOWN)
    s.add("mara", "townsfolk", "Mara Reed", "docks")
    s.add("wat", "townsfolk", "Wat Fuller", "docks")
    s.add("edda", "townsfolk", "Edda Vane", "market")
    s.add("harl", "townsfolk", "Harl Greave", "chapel")
    return s


def conf(s: Session, npc: str, claim: dict) -> float:
    return s.world.beliefs.conf(npc, Claim.from_json(claim))


# ---------------------------------------------------------------- the game file
def test_a_game_may_name_nobody_and_declare_kinds():
    assert TOWN.cast.ids() == [] and list(TOWN.kinds) == ["townsfolk", "guard"]
    assert Session.new(TOWN).world.npcs == {}


@pytest.mark.parametrize("toml, says", [
    ('[game]\nid = "x"', "at least one [npc.<id>], or a [kind.<id>]"),
    ('[kind.k]\npersona = "p"', 'kind.k: needs goal = "..."'),
    ('[kind.k]\npersona = "p"\ngoal = "g"\nname = "Ann"', "kind.k: name is each person's own"),
    ('[places]\na = "A"\n[kind.k]\npersona = "p"\ngoal = "g"\nwalk = ["b"]', "kind.k: 'b' is not in [places]"),
    ('[kind.k]\npersona = "p"\ngoal = "g"\n[kind.k.feels]\nrobbed = { anger = 0.5 }', "kind.k.feels.robbed"),
    ('[kind.k]\npersona = "p"\ngoal = "g"\n[[kind.k.choices.meet]]\ndo = "greet"', "kind.k.choices.meet[0]"),
    ('[kind.k]\npersona = "p"\ngoal = "g"\n[claims]\none_actor = "robbed"', "claims.one_actor: a list"),
    ('[kind.k]\npersona = "p"\ngoal = "g"\n[gossip]\nabout = "all"', 'gossip.about: a list of ids, or "everyone"'),
])
def test_a_mistake_in_a_kind_names_its_entry(toml, says):
    with pytest.raises(DefinitionError) as e:
        Game.parse(toml)
    assert says in str(e.value)


# ---------------------------------------------------------------- joining
def test_someone_joins_as_one_of_a_kind():
    s = Session.new(TOWN)
    card = s.add("mara", "townsfolk", "Mara Reed", "docks")
    assert card == {"id": "mara", "loc": "docks", "drives": {"anger": 0, "fear": 0}, "trust_in": {},
                    "frozen_until": None, "last_seen": None, "flags": {}, "kind": "townsfolk", "name": "Mara Reed"}
    assert s.inspect("mara") == {"npc": card, "beliefs": []}
    assert s.who("mara") == "Mara Reed"
    pack = s.voice.pack(s.world, "mara", "x")
    assert (pack.name, pack.persona[:20], pack.goal[:11]) == ("Mara Reed", "One of the townsfolk", "Get through")


def test_their_own_persona_and_goal_replace_their_kinds():
    s = Session.new(TOWN)
    s.add("ivo", "guard", "Ivo", "market", persona="The sergeant: loud.", goal="Retire quietly")
    pack = s.voice.pack(s.world, "ivo", "x")
    assert (pack.persona, pack.goal) == ("The sergeant: loud.", "Retire quietly")
    assert s.voice.pack(s.world, s.add("una", "guard", "Una", "market")["id"], "x").goal.startswith("Keep the peace")


@pytest.mark.parametrize("npc, kind, name, at, error", [
    ("mara", "baker", "Mara", "docks", Unknown),  # no such kind
    ("player", "townsfolk", "Mara", "docks", DefinitionError),
    ("wat", "townsfolk", "Another Wat", "docks", DefinitionError),  # taken
    ("docks", "townsfolk", "Mara", "docks", DefinitionError),  # a place's id
    ("mara reed", "townsfolk", "Mara", "docks", DefinitionError),  # not an id
    ("a:b", "townsfolk", "Mara", "docks", DefinitionError),  # it would break an action's id
    ("mara", "townsfolk", " ", "docks", DefinitionError),
    ("mara", "townsfolk", "Mara", "mill", DefinitionError),  # no such place
])
def test_who_may_not_join(npc, kind, name, at, error):
    s = Session.new(TOWN)
    s.add("wat", "townsfolk", "Wat Fuller", "docks")
    with pytest.raises(error):
        s.add(npc, kind, name, at)
    assert list(s.world.npcs) == ["wat"]


def test_a_game_without_kinds_takes_nobody():
    with pytest.raises(Unknown):
        Session.new(TAVERN).add("mara", "townsfolk", "Mara", "taproom")


def test_someone_who_joined_sees_believes_feels_and_chooses_as_their_kind_does():
    s = town()
    e = s.observe("rob", "player", "mara", at="docks", claim=ROBBED, witnesses=["wat"])
    assert s.sentence(e) == "The player robbed Mara Reed at the river docks."
    assert (conf(s, "mara", ROBBED), conf(s, "wat", ROBBED), conf(s, "edda", ROBBED)) == (1.0, 1.0, 0.0)
    assert s.world.npcs["mara"].drives == {"anger": 4, "fear": 0}  # her kind's: robbed = { anger = 4 }
    assert s.world.npcs["wat"].drives == {"anger": 0, "fear": 0}  # it wasn't done to him
    assert s.decide("mara", "meet", {"who": "player"}).action == "greet:player"  # the player isn't with her
    s.update("player", loc="docks")
    line = s.decide("mara", "meet", {"who": "player"})
    assert (line.action, line.text, line.reason) == ("accuse:player", "It was you. I know it was you.",
                                                     "accuse:player scores 5")
    s.update("mara", nudge={"fear": 5})
    assert s.decide("mara", "meet", {"who": "player"}).action == "watch:player"
    assert s.decide("wat", "meet", {"who": "player"}).action == "greet:player"
    with pytest.raises(Unknown):
        s.decide("mara", "haggle")  # her kind has no such moment


def test_feelings_of_a_kind_fade_as_it_declares():
    s = town()
    s.observe("rob", "player", "mara", at="docks", claim=ROBBED)
    s.tick(4)
    assert s.world.npcs["mara"].drives["anger"] == 2  # half_life = 4
    s.tick(40)
    assert s.world.npcs["mara"].drives["anger"] == 1  # keep = 0.25


def test_a_line_may_name_someone_who_joined_and_the_games_own_validator_learns_nothing():
    s = town()
    assert s.voice.validator.named("Harl Greave met wat at the docks") == {"harl", "wat", "docks"}
    assert s.mind.validator is s.voice.validator
    assert TOWN.voice.validator.named("Harl Greave met wat") == set()
    assert Session.new(TOWN).voice.validator.named("Harl Greave") == set()  # another session never met him


# ---------------------------------------------------------------- ties, and the grapevine
def test_gossip_travels_along_a_tie_made_in_play():
    s = town()
    s.observe("rob", "player", "mara", at="docks", claim=ROBBED, witnesses=["wat"])
    assert s.tie("wat", "edda", "kin") == {"between": ["wat", "edda"], "kind": "kin"}
    s.update("edda", trust_in={"wat": 3})
    told = [s.sentence(e) for e in s.tick().events]
    assert "Wat Fuller told Edda Vane that the player robbed Mara Reed." in told
    assert conf(s, "edda", ROBBED) == 0.9  # his certainty, her trust in him (0.9), along kin (1.0)
    assert conf(s, "harl", ROBBED) == 0.0  # nobody is tied to him, and nobody stands with him


def test_news_of_anyone_travels_but_nobody_is_told_what_they_did_themselves():
    s = town()
    s.update("harl", loc="docks")
    s.tie("wat", "harl", "friend")
    s.observe("tell", "player", "wat", at="docks", claim=BLAMED, said=True)  # a lie about Harl, told to Wat
    s.update("wat", trust_in={"player": 2})
    s.observe("tell", "player", "wat", at="docks", claim=BLAMED, said=True)
    assert conf(s, "wat", BLAMED) == 0.9
    s.tick()
    assert s.world.beliefs.get("harl", Claim.from_json(BLAMED)) is None  # Wat doesn't tell Harl that Harl did it
    assert conf(s, "mara", BLAMED) > 0  # she stands with Wat, and hears who is said to have robbed her


def test_a_tie_can_be_changed_and_broken():
    s = town()
    s.tie("wat", "edda", "kin")
    assert s.tie("edda", "wat", "friend") == {"between": ["edda", "wat"], "kind": "friend"}
    assert s.world.ties == [["edda", "wat", "friend"]]
    s.untie("wat", "edda")
    assert s.world.ties == []
    s.observe("rob", "player", "mara", at="docks", claim=ROBBED, witnesses=["wat"])
    s.tick()
    assert conf(s, "edda", ROBBED) == 0.0
    with pytest.raises(Unknown):
        s.untie("wat", "edda")
    for a, b, kind in (("wat", "wat", "kin"), ("wat", "edda", "rival"), ("wat", "nobody", "kin")):
        with pytest.raises((DefinitionError, Unknown)):
            s.tie(a, b, kind)


# ---------------------------------------------------------------- leaving
def test_someone_retired_sees_says_and_decides_nothing_more():
    s = town()
    s.observe("rob", "player", "mara", at="docks", claim=ROBBED, witnesses=["wat"])
    s.tie("wat", "edda", "kin")
    s.tie("mara", "edda", "friend")
    card = s.retire("wat")
    assert card["gone"] is True and s.inspect("wat")["npc"]["gone"] is True
    assert conf(s, "wat", ROBBED) == 1.0  # what he believed is kept
    assert s.voice.pack(s.world, "mara", "x").here == []  # he is no longer someone at the docks
    s.update("player", loc="docks")
    assert s.decide("wat", "meet", {"who": "player"}).text is None and s.react("wat", "greet").text is None
    s.observe("threaten", "player", "mara", at="docks", claim={"pred": "threatened", "a": "player", "b": "mara"},
              witnesses=["wat"])
    assert conf(s, "wat", {"pred": "threatened", "a": "player", "b": "mara"}) == 0.0  # he saw nothing
    told = [(e.actor, e.target) for e in s.tick().events if e.verb == "gossip"]
    assert told and all("wat" not in pair for pair in told)  # he tells nobody, and nobody tells him
    with pytest.raises(Unknown):
        s.retire("nobody")


def test_the_town_still_talks_about_the_dead():
    s = town()
    s.observe("kill", "player", "wat", at="docks", claim={"pred": "killed", "a": "player", "b": "wat"},
              witnesses=["mara"])
    s.retire("wat")
    s.tie("mara", "edda", "kin")
    s.update("edda", trust_in={"mara": 3})
    s.tick()
    assert conf(s, "edda", {"pred": "killed", "a": "player", "b": "wat"}) == 0.9


# ---------------------------------------------------------------- one culprit
def test_a_lie_meets_a_witness_and_the_liar_is_doubted_in_everything():
    s = town()
    s.observe("rob", "player", "mara", at="docks", claim=ROBBED, witnesses=["wat"])
    helped = {"pred": "helped", "a": "player", "b": "harl"}
    s.observe("tell", "player", "edda", at="market", claim=helped, said=True)  # something else the player told her
    lie = s.observe("tell", "player", "edda", at="market", claim=BLAMED, said=True)
    assert lie.truth is False  # the ledger knows who robbed Mara
    assert (conf(s, "edda", BLAMED), conf(s, "edda", helped)) == (0.4, 0.4)
    s.tie("wat", "edda", "friend")
    s.update("edda", trust_in={"wat": 3})
    s.tick()  # Wat, who saw it, tells his friend
    beliefs = {json.dumps(b["claim"], sort_keys=True): b["status"] for b in s.inspect("edda")["beliefs"]}
    assert beliefs[json.dumps(BLAMED, sort_keys=True)] == "retracted"
    assert conf(s, "edda", ROBBED) == 0.81  # 1.0 x her trust in Wat (0.9) x along a friend (0.9)
    assert s.world.npcs["edda"].trust_in == {"wat": 3, "player": -2}  # caught = 2
    assert conf(s, "edda", helped) == 0.2  # and the other thing the player said is worth less now


def test_what_they_saw_themselves_beats_anyones_word():
    s = town()
    s.observe("rob", "player", "mara", at="docks", claim=ROBBED, witnesses=["wat"])
    s.update("wat", trust_in={"player": 5})
    s.observe("tell", "player", "wat", at="docks", claim=BLAMED, said=True)
    assert conf(s, "wat", ROBBED) == 1.0 and conf(s, "wat", BLAMED) == 0.0
    assert s.world.npcs["wat"].trust_in["player"] == 3


def test_two_stories_from_sources_trusted_alike_settle_nothing():
    s = town()
    s.observe("tell", "wat", "edda", at="market", claim=ROBBED, said=True)
    s.observe("tell", "mara", "edda", at="market", claim=BLAMED, said=True)
    assert conf(s, "edda", ROBBED) == conf(s, "edda", BLAMED) == 0.4
    assert s.world.npcs["edda"].trust_in == {"wat": 0, "mara": 0}


def test_a_game_that_declares_no_one_actor_keeps_both_stories():
    plain = Game.parse(TOWN_TOML.replace('one_actor = ["robbed", "killed"]', "one_actor = []"), "town")
    s = Session.new(plain)
    for npc, at in (("mara", "docks"), ("wat", "docks")):
        s.add(npc, "townsfolk", npc.title(), at)
    s.add("harl", "townsfolk", "Harl", "chapel")
    s.observe("rob", "player", "mara", at="docks", claim=ROBBED, witnesses=["wat"])
    s.observe("tell", "player", "wat", at="docks", claim=BLAMED, said=True)
    assert conf(s, "wat", ROBBED) == 1.0 and conf(s, "wat", BLAMED) == 0.4
    assert s.world.npcs["wat"].trust_in == {}


# ---------------------------------------------------------------- saves
def test_a_save_holds_who_joined_their_ties_and_who_has_gone():
    s = town()
    s.observe("rob", "player", "mara", at="docks", claim=ROBBED, witnesses=["wat"])
    s.tie("wat", "edda", "kin")
    s.retire("harl")
    snap = json.loads(json.dumps(s.snapshot()))
    assert snap["world"]["cast"]["mara"] == {"kind": "townsfolk", "name": "Mara Reed", "at": "docks"}
    assert snap["world"]["ties"] == [["wat", "edda", "kin"]] and snap["world"]["gone"] == ["harl"]
    back = Session.restore(TOWN, snap)
    assert back.snapshot() == s.snapshot()
    assert back.who("mara") == "Mara Reed" and back.voice.validator.named("Edda Vane") == {"edda"}
    back.update("player", loc="docks")
    assert back.decide("mara", "meet", {"who": "player"}).action == "accuse:player"
    back.update("edda", trust_in={"wat": 3})
    back.tick()
    assert conf(back, "edda", ROBBED) == 0.9


def test_a_game_whose_cast_is_its_file_saves_as_it_always_has():
    world = Session.new(TAVERN).snapshot()["world"]
    assert not {"cast", "ties", "gone"} & set(world)


# ---------------------------------------------------------------- over HTTP
def test_the_http_api_mirrors_the_library():
    client = TestClient(create_app({"town": TOWN}))
    assert client.get("/v1/games").json()[0]["kinds"] == ["townsfolk", "guard"]
    sid = client.post("/v1/sessions", json={"game": "town"}).json()["session"]
    lib = town()
    for npc, name, at in (("mara", "Mara Reed", "docks"), ("wat", "Wat Fuller", "docks"),
                          ("edda", "Edda Vane", "market"), ("harl", "Harl Greave", "chapel")):
        r = client.post(f"/v1/sessions/{sid}/npcs", json={"id": npc, "kind": "townsfolk", "name": name, "at": at})
        assert r.status_code == 201 and r.json() == lib.inspect(npc)["npc"]
    assert client.post(f"/v1/sessions/{sid}/ties", json={"a": "wat", "b": "edda", "kind": "kin"}).json() == \
        lib.tie("wat", "edda", "kin")
    assert client.delete(f"/v1/sessions/{sid}/npcs/harl").json() == lib.retire("harl")
    client.post(f"/v1/sessions/{sid}/observe", json={"verb": "rob", "actor": "player", "target": "mara",
                                                     "at": "docks", "claim": ROBBED, "witnesses": ["wat"]})
    lib.observe("rob", "player", "mara", at="docks", claim=ROBBED, witnesses=["wat"])
    client.post(f"/v1/sessions/{sid}/tick", json={})
    lib.tick()
    assert client.get(f"/v1/sessions/{sid}/snapshot").json() == json.loads(json.dumps(lib.snapshot()))
    assert client.delete(f"/v1/sessions/{sid}/ties/wat/edda").status_code == 204
    assert client.delete(f"/v1/sessions/{sid}/ties/wat/edda").status_code == 404
    for body, status in (({"id": "mara", "kind": "townsfolk", "name": "Again"}, 400),
                         ({"id": "odo", "kind": "baker", "name": "Odo"}, 404)):
        assert client.post(f"/v1/sessions/{sid}/npcs", json=body).status_code == status
