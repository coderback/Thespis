"""Richer minds (Phase 4.5a), each only where a game declares it (examples/hamlet/game.toml): players the NPCs know
apart, feelings that move with what an NPC comes to believe and fade with a half-life, gossip along ties discounted
by trust, and denials that count against what they deny."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from thespis.api import DefinitionError, Game, Session, Unknown
from thespis.ledger import Claim
from thespis.server import create_app

ROOT = Path(__file__).resolve().parents[1]
HAMLET_TOML = (ROOT / "examples" / "hamlet" / "game.toml").read_text(encoding="utf-8")
HAMLET = Game.parse(HAMLET_TOML, "hamlet")
TAVERN = Game.load(ROOT / "examples" / "tavern" / "game.toml")
CHEAT = {"pred": "cheated", "a": "ada", "b": "osric"}


def conf(s: Session, npc: str, claim: dict) -> float | None:
    b = s.world.beliefs.get(npc, Claim.from_json(claim))
    return b.conf if b else None


# ---------------------------------------------------------------- players
def test_npcs_know_the_players_apart():
    s = Session.new(HAMLET)
    s.observe("cheat", "ada", "osric", claim=CHEAT)
    assert s.decide("osric", "meet", {"who": "ada"}).action == "refuse:ada"
    assert s.decide("osric", "meet", {"who": "bram"}).action == "trade:bram"  # Bram did nothing
    s.update("ada", loc="green")  # out of his sight, he has no one to refuse
    assert s.decide("osric", "meet", {"who": "ada"}).action == "trade:ada"
    assert s.world.players["ada"] == {"name": "Ada", "loc": "green"}


def test_each_player_is_told_only_what_they_saw():
    s = Session.new(HAMLET)
    s.observe("cheat", "ada", "osric", claim=CHEAT)
    s.observe("help", "bram", "maud", claim={"pred": "helped", "a": "bram", "b": "maud"}, witnesses=["ada"])
    assert s.narrate(to="ada").cites == ["e0001", "e0002"]  # her own deed, and Bram's, which she saw
    assert s.narrate(to="bram").cites == ["e0002"]
    assert s.narrate().cites == ["e0001", "e0002"]
    with pytest.raises(Unknown):
        s.narrate(to="cara")


def test_a_player_joins_and_is_seen_heard_and_named():
    s = Session.new(HAMLET)
    assert s.join("cara", "Cara", at="mill") == {"id": "cara", "name": "Cara", "loc": "mill"}
    assert s.voice.pack(s.world, "osric", "x").here == ["Ada", "Cara"]  # the players at the mill, by name
    s.observe("help", "cara", "osric", claim={"pred": "helped", "a": "cara", "b": "osric"})
    assert s.world.npcs["osric"].drives["warmth"] == 6  # he feels it: helped = { warmth = 3 }
    assert s.sentence(s.world.ledger.get("e0001")) == "Cara helped Osric at Osric's mill."
    for taken in ("player", "osric"):
        with pytest.raises(DefinitionError):
            s.join(taken)


def test_a_one_player_save_is_as_it_was_and_players_survive_a_save():
    tavern = Session.new(TAVERN)
    assert "players" not in tavern.snapshot()["world"]
    s = Session.new(HAMLET)
    s.join("cara", "Cara", at="green")
    s.observe("cheat", "ada", "osric", claim=CHEAT)
    again = Session.restore(HAMLET, json.loads(json.dumps(s.snapshot())))
    assert again.snapshot() == s.snapshot()
    assert again.world.players["cara"]["name"] == "Cara"


# ---------------------------------------------------------------- feelings and their decay
def test_feelings_follow_belief_and_fade_with_a_half_life():
    s = Session.new(HAMLET)
    s.observe("cheat", "ada", "osric", claim=CHEAT)
    assert s.world.npcs["osric"].drives["grudge"] == 6  # cheated = { grudge = 6 }, and he was there: certain
    seen = []
    for _ in range(5):
        s.tick()
        seen.append(s.world.npcs["osric"].drives["grudge"])
    assert seen == [4, 3, 2, 2, 2]  # halving every 2 ticks, never below a quarter of the peak


def test_hearsay_moves_feelings_as_far_as_it_is_believed():
    s = Session.new(HAMLET)
    s.observe("tell", "maud", "osric", claim=CHEAT, said=True)  # he trusts Maud 2: he believes her 0.9
    assert conf(s, "osric", CHEAT) == 0.9 and s.world.npcs["osric"].drives["grudge"] == 5  # 6 x 0.9, rounded
    s.observe("tell", "hild", "osric", claim=CHEAT, said=True)
    assert s.world.npcs["osric"].drives["grudge"] == 5  # a second telling isn't a second insult
    s.observe("tell", "maud", "osric", claim={"pred": "cheated", "a": "osric", "b": "ada"}, said=True)
    assert s.world.npcs["osric"].drives["grudge"] == 5  # done by him, not to him: no anger


def test_the_engine_setting_a_drive_starts_its_fading_again():
    s = Session.new(HAMLET)
    s.update("osric", drives={"grudge": 8})
    s.tick()
    assert s.world.npcs["osric"].drives["grudge"] == 6  # 8 x 0.71
    s.update("osric", nudge={"grudge": 2})  # 8 again, from now
    s.tick()
    assert s.world.npcs["osric"].drives["grudge"] == 6


# ---------------------------------------------------------------- ties
def test_gossip_travels_one_tie_a_tick_and_weakens_as_it_goes():
    s = Session.new(HAMLET)
    s.observe("cheat", "ada", "osric", claim=CHEAT)
    first = s.tick()
    assert [(e.actor, e.target) for e in first.events if e.verb == "gossip"] == [("osric", "hild"), ("osric", "maud")]
    assert (conf(s, "hild", CHEAT), conf(s, "maud", CHEAT), conf(s, "aldo", CHEAT)) == (0.9, 0.81, None)
    second = s.tick()
    assert [(e.actor, e.target) for e in second.events if e.verb == "gossip"] == [("hild", "aldo")]
    assert conf(s, "aldo", CHEAT) == 0.73  # 0.9 from his friend Hild, x 0.9 his trust in her, x 0.9 a friend's tie
    assert s.tick().events == []  # everyone tied has heard it


def test_told_apart_nobody_overhears_and_told_together_a_stranger_hears_less():
    s = Session.new(HAMLET)
    s.observe("cheat", "ada", "osric", claim=CHEAT)
    s.tick()
    assert all(e.loc == "" and e.id not in s.witnesses for e in s.world.ledger if e.verb == "gossip")
    assert s.narrate(to="ada").cites == ["e0001"]  # she stands in the mill, but Osric told Hild at the forge

    s = Session.new(HAMLET)
    s.update("hild", loc="mill")
    s.update("aldo", loc="mill")  # Aldo stands with Osric, with no tie between them
    s.observe("cheat", "ada", "osric", claim=CHEAT)
    told = [e for e in s.tick().events if e.verb == "gossip"]
    assert [(e.target, e.loc) for e in told] == [("hild", "mill"), ("maud", ""), ("aldo", "mill")]
    assert conf(s, "aldo", CHEAT) == 0.16  # 1.0 x 0.2 (he trusts Osric -2) x 0.8 (in person, untied)


def test_ties_are_checked_when_the_game_loads():
    for bad, message in ((("between = [\"osric\", \"nobody\"]", "kind = \"kin\""), "tie[0]: between"),
                         (("between = [\"osric\", \"hild\"]", "kind = \"enemy\""), "is not in [gossip] along")):
        text = HAMLET_TOML.replace('between = ["osric", "hild"]\nkind = "kin"', "\n".join(bad))
        with pytest.raises(DefinitionError, match=message.replace("[", r"\[")):
            Game.parse(text, "hamlet")
    with pytest.raises(DefinitionError, match="half_life"):
        Game.parse(HAMLET_TOML.replace("half_life = 2, ", ""), "hamlet")
    with pytest.raises(DefinitionError, match="players.osric"):
        Game.parse(HAMLET_TOML.replace("[players.bram]", "[players.osric]"), "hamlet")


# ---------------------------------------------------------------- denials
def test_a_denial_counts_against_the_story_as_far_as_the_denier_is_trusted():
    s = Session.new(HAMLET)
    s.observe("cheat", "ada", "osric", claim=CHEAT)
    s.tick()  # Hild hears it from her brother: 0.9
    s.observe("tell", "ada", "hild", claim={**CHEAT, "neg": True}, said=True)  # "I never cheated him"
    b = s.world.beliefs.get("hild", Claim.from_json(CHEAT))
    assert b is not None and b.active  # she trusts Ada 1 (0.4): her brother's word still stands
    assert (b.opinion.b, b.opinion.d) == (0.8438, 0.0625)
    s.observe("tell", "aldo", "hild", claim={**CHEAT, "neg": True}, said=True)  # and the priest, whom she trusts 2
    assert s.world.beliefs.get("hild", Claim.from_json(CHEAT)).opinion.d > 0.4


# ---------------------------------------------------------------- over /v1
def test_players_over_http():
    client = TestClient(create_app({"hamlet": HAMLET}))
    sid = client.post("/v1/sessions", json={"game": "hamlet"}).json()["session"]
    assert client.post(f"/v1/sessions/{sid}/players", json={"player": "cara", "name": "Cara", "at": "green"}).json() \
        == {"id": "cara", "name": "Cara", "loc": "green"}
    assert client.post(f"/v1/sessions/{sid}/players", json={"player": "osric"}).status_code == 400
    client.post(f"/v1/sessions/{sid}/observe", json={"verb": "cheat", "actor": "ada", "target": "osric",
                                                     "claim": CHEAT, "witnesses": ["cara"]})
    told = client.post(f"/v1/sessions/{sid}/narrate", json={"to": "cara"}).json()
    assert told["cites"] == ["e0001"] and told["text"] == "Ada cheated Osric at Osric's mill."
    assert client.post(f"/v1/sessions/{sid}/narrate", json={"to": "bram"}).json()["text"] is None
    assert client.post(f"/v1/sessions/{sid}/update", json={"npc": "cara", "loc": "mill"}).json()["loc"] == "mill"
