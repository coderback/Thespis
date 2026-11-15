"""Saves made by Thespis 0.5.0 load in this one. They were made by `tests/saves/make_saves.py` from the v0.5.0 tag,
when a world still carried the demo games' race (`status`, `pending`, `ended_at`) in fields of its own."""

import json
import sqlite3
from pathlib import Path

import pytest

from games import race
from games.crypt_road import rules, views
from games.manor import views as manor_views
from games.store import Store
from thespis.api import SNAPSHOT_VERSION, DefinitionError, Game, Session
from thespis.world import World

SAVES = Path(__file__).parent / "saves" / "0.5.0"
TAVERN = Path(__file__).resolve().parents[1] / "examples" / "tavern" / "game.toml"
RACE = ("status", "pending", "ended_at")


def old(name: str) -> dict:
    return json.loads((SAVES / f"{name}.json").read_text(encoding="utf-8"))


def same_but_the_race(was: dict, now: dict) -> bool:
    """Everything a 0.5.0 save held is still there; only the race moved, into `custom`."""
    return {k: v for k, v in was.items() if k not in RACE} == {k: v for k, v in now.items() if k != "custom"}


def test_a_pending_duel_survives():
    was = old("crypt_road_duel_won")
    w = World.from_json(was)
    assert (race.status(w), race.pending(w), race.ended_at(w)) == ("playing", "duel_won", None)
    now = w.to_json()
    assert now["custom"] == {"pending": "duel_won"} and not set(RACE) & set(now) and same_but_the_race(was, now)
    assert {o["verb"] for o in rules.allowed(w) if o["enabled"]} == {"humiliate", "spare"}
    rules.act(w, "humiliate", "kael")  # and the game goes on from it
    assert race.pending(w) is None and "pending" not in w.custom


def test_a_won_race_survives():
    was = old("crypt_road_won")
    w = World.from_json(was)
    state = views.state_view(w)
    assert (state["status"], state["pending"], state["ended_at"]) == ("won", None, 5)  # the client sees what it saw
    assert w.custom == {"status": "won", "ended_at": 5} and same_but_the_race(was, w.to_json())
    assert World.from_json(w.to_json()).to_json() == w.to_json()


def test_a_closed_case_survives():
    was = old("manor")
    w = World.from_json(was)
    assert (manor_views.state_view(w)["status"], race.ended_at(w)) == ("won", was["ended_at"])
    assert same_but_the_race(was, w.to_json())


def test_a_world_without_a_race_saves_none():
    """A sidecar's world never had a race: it loads with nothing in `custom`, and saves without the old fields."""
    w = World.from_json(old("tavern_snapshot")["world"])
    assert w.custom == {} and not {"custom", *RACE} & set(w.to_json())


def test_a_version_1_snapshot_restores():
    game = Game.load(TAVERN)
    was = old("tavern_snapshot")
    assert was["thespis"] == 1
    s = Session.restore(game, was)
    assert s.patched == [] and s.inspect("garrick")["beliefs"]  # the game file is the same, and he remembers
    now = s.snapshot()
    assert now["thespis"] == SNAPSHOT_VERSION == 2 and same_but_the_race(was["world"], now["world"])
    assert Session.restore(game, now).snapshot() == now
    with pytest.raises(DefinitionError, match="reads 1 and 2"):
        Session.restore(game, {**now, "thespis": 3})


def test_the_game_keeps_its_own_state():
    """`custom` is the game's: any JSON goes in, and it comes back out of a save as it went in."""
    w = World.from_json(old("tavern_snapshot")["world"])
    w.custom["quest"] = {"stage": 2, "found": ["key", "map"], "done": False}
    assert World.from_json(json.loads(json.dumps(w.to_json()))).custom == w.custom
    w.custom["bad"] = {1, 2}
    with pytest.raises(TypeError):
        w.to_json()


def test_the_hosted_demo_loads_an_old_save(tmp_path):
    """A session the hosted demo saved before the upgrade: its snapshot row is in the old form."""
    was = old("crypt_road_won")
    store = Store(tmp_path / "demo.sqlite")
    sid = store.create_session(was["seed"])
    store.save(sid, World.from_json(was))  # the ledger rows
    with sqlite3.connect(tmp_path / "demo.sqlite") as db:
        db.execute("UPDATE sessions SET snapshot = ? WHERE id = ?", (json.dumps(was), sid))
    w = store.load(sid)
    assert (race.status(w), race.ended_at(w)) == ("won", 5)
    store.save(sid, w)  # saved again, in the new form
    assert store.load(sid).to_json() == w.to_json()
