"""Persistence: a session reloaded after a restart is identical, and the ledger is never rewritten."""

import json
import sqlite3

import pytest

from games.crypt_road.content import new_world
from thespis.decisions import REACT
from thespis.ledger import Claim
from thespis.store import LedgerMismatch, SessionNotFound, Store

ROBBED = Claim("robbed", "player", "kael")


def played(world):
    """A few demo beats' worth of state: events, beliefs, a decision, drive and position changes."""
    e = world.ledger.append(0, "humiliate", "player", "kael", "tavern", ROBBED)
    for npc in ("mags", "odo"):
        world.beliefs.add_evidence(npc, ROBBED, 1.0, "witnessed", e.id, 0)
    world.decisions.record(REACT, "kael", 0, "robbed", line="Laugh now. The road is long.", cites=[e.id])
    world.npcs["kael"].drives["grudge"] = 6
    world.npcs["kael"].loc = "market"
    world.npcs["kael"].flags["accused"] = False
    world.player["coins"] = 40
    world.phase = 1
    world.counters["challenges"] = 1
    return world


def ledger_rows(path):
    with sqlite3.connect(path) as db:
        return db.execute("SELECT run, seq, id FROM ledger ORDER BY run, seq").fetchall()


def test_restart_reloads_identical_state(tmp_path):
    path = tmp_path / "thespis.sqlite"
    store = Store(path)
    session = store.create_session(seed=1)
    world = played(new_world(1))
    store.save(session, world)

    reloaded = Store(path).load(session)  # a fresh Store on the same file: what a server restart does
    assert reloaded.to_json() == world.to_json()
    assert reloaded.beliefs.conf("mags", ROBBED) == 1.0 and reloaded.ledger.happened(ROBBED)


def test_saving_again_appends_only_new_events(tmp_path):
    path = tmp_path / "thespis.sqlite"
    store = Store(path)
    session = store.create_session(seed=1)
    world = played(new_world(1))
    store.save(session, world)
    store.save(session, world)
    world.ledger.append(1, "move", "player", "market", "tavern")
    store.save(session, world)
    assert ledger_rows(path) == [(1, 1, "e0001"), (1, 2, "e0002")]
    assert store.load(session).to_json() == world.to_json()


def test_tampered_snapshot_is_detected(tmp_path):
    path = tmp_path / "thespis.sqlite"
    store = Store(path)
    session = store.create_session(seed=1)
    store.save(session, played(new_world(1)))
    with sqlite3.connect(path) as db:
        snapshot = json.loads(db.execute("SELECT snapshot FROM sessions").fetchone()[0])
        snapshot["ledger"][0]["truth"] = False
        db.execute("UPDATE sessions SET snapshot = ?", (json.dumps(snapshot),))
    with pytest.raises(LedgerMismatch):
        store.load(session)


def test_reset_starts_a_new_run_and_keeps_the_old_ledger(tmp_path):
    path = tmp_path / "thespis.sqlite"
    store = Store(path)
    session = store.create_session(seed=7)
    store.save(session, played(new_world(7)))
    fresh = new_world(store.seed_of(session))
    store.reset(session, fresh)
    assert store.load(session).to_json() == fresh.to_json()
    assert ledger_rows(path) == [(1, 1, "e0001")]  # run 1's event is still there
    fresh.ledger.append(0, "insult", "player", "kael", "tavern")
    store.save(session, fresh)
    assert ledger_rows(path) == [(1, 1, "e0001"), (2, 1, "e0001")]


def test_unknown_or_unsaved_sessions(tmp_path):
    store = Store(tmp_path / "thespis.sqlite")
    with pytest.raises(SessionNotFound):
        store.load("nope")
    with pytest.raises(SessionNotFound):
        store.load(store.create_session(seed=1))  # created, but nothing saved yet


def test_a_manor_session_saved_before_typed_claims_still_loads(tmp_path):
    """Before typed claims the manor kept a room and a phase in one slot ("study@1"). Old rows stay as saved; the
    loader reads both them and the snapshot through the upgrade, and saving again keeps them consistent."""
    from games.manor import content as manor

    def old_form(d):
        if d.get("place") is not None:
            return {k: v for k, v in d.items() if k not in ("place", "at")} | {"b": f"{d['place']}@{d['at']}"}
        return d

    path = tmp_path / "manor.sqlite"
    store, world = Store(path), manor.new_world()
    session = store.create_session(seed=1)
    store.save(session, world)
    with sqlite3.connect(path) as db:  # rewrite what was saved into the old form
        for rowid, event in db.execute("SELECT rowid, event FROM ledger").fetchall():
            e = json.loads(event)
            if e["claim"]:
                db.execute("UPDATE ledger SET event = ? WHERE rowid = ?",
                           (json.dumps({**e, "claim": old_form(e["claim"])}), rowid))
        snap = json.loads(db.execute("SELECT snapshot FROM sessions").fetchone()[0])
        snap["ledger"] = [{**e, "claim": old_form(e["claim"])} if e["claim"] else e for e in snap["ledger"]]
        snap["beliefs"] = [{**b, "claim": old_form(b["claim"])} for b in snap["beliefs"]]
        db.execute("UPDATE sessions SET snapshot = ?", (json.dumps(snap),))
    assert "study@1" in json.dumps(snap)

    loaded = store.load(session, manor.upgrade_claim)
    assert loaded.to_json() == world.to_json()
    assert loaded.beliefs.get(manor.BUTLER, manor.THE_TRUTH) is not None
    loaded.ledger.append(loaded.phase, "move", "player", "kitchen", "hall")
    store.save(session, loaded)  # new rows in the new form beside old rows in the old one
    assert store.load(session, manor.upgrade_claim).to_json() == loaded.to_json()

