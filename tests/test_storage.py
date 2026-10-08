"""What `thespis serve` keeps (thespis.storage), on SQLite and, when THESPIS_TEST_POSTGRES names a database to use
up, on Postgres: the same statements must behave the same on both."""

import os
import time

import pytest

from thespis.storage import Caps, Conflict, PostgresStorage, SqliteStorage, Usage, day, hash_key
from thespis.vault import Vault, VaultError, new_secret

POSTGRES = os.environ.get("THESPIS_TEST_POSTGRES", "")
TABLES = ("projects", "games", "sessions", "usage", "usage_daily", "replies")


def fresh_postgres(dsn: str) -> PostgresStorage:
    import psycopg
    with psycopg.connect(dsn, autocommit=True) as db:
        for t in TABLES:
            db.execute(f"DROP TABLE IF EXISTS {t}")
    return PostgresStorage(dsn, size=4)


@pytest.fixture(params=["sqlite", "postgres"])
def store(request, tmp_path):
    if request.param == "sqlite":
        s = SqliteStorage(tmp_path / "t.sqlite")
    elif not POSTGRES:
        pytest.skip("set THESPIS_TEST_POSTGRES to a database these tests may empty")
    else:
        s = fresh_postgres(POSTGRES)
    yield s
    s.close()


def test_a_project_is_found_by_its_key_which_is_kept_only_as_a_hash(store):
    p, key = store.create_project("tavern-studio", Caps(calls_per_day=100))
    assert key and key.startswith("tsk_")
    assert store.project_by_key(key) == p
    assert store.project("tavern-studio") == p == store.project(p.id)
    assert store.project_by_key("tsk_wrong") is None and store.project_by_key("no prefix") is None
    new = store.rotate_key(p.id)
    assert store.project_by_key(key) is None and store.project_by_key(new) == p
    rows = store._all("SELECT key_hash FROM projects")
    assert rows == [(hash_key(new),)]  # the key itself is nowhere


def test_caps_and_sealed_model_settings_are_kept(store):
    p, _ = store.create_project("a")
    store.set_caps(p.id, Caps(max_sessions=3, tokens_per_day=5000))
    assert store.project(p.id).caps == Caps(max_sessions=3, tokens_per_day=5000)
    store.set_model(p.id, "v1:sealed")
    assert store.model(p.id) == "v1:sealed"
    store.set_model(p.id, None)
    assert store.model(p.id) is None


def test_games_are_per_project(store):
    a, _ = store.create_project("a")
    b, _ = store.create_project("b")
    store.put_game(a.id, "tavern", "one")
    store.put_game(a.id, "tavern", "two")
    assert store.games(a.id) == {"tavern": "two"} and store.games(b.id) == {}
    assert not store.delete_game(b.id, "tavern") and store.delete_game(a.id, "tavern")


def test_a_save_that_finds_the_session_moved_on_is_refused(store):
    p, _ = store.create_project("a")
    store.create_session(p.id, "s1", "tavern", {"n": 0})
    assert store.load_session(p.id, "s1") == ("tavern", {"n": 0}, 1)
    assert store.save_session("s1", {"n": 1}, 1) == 2
    with pytest.raises(Conflict):
        store.save_session("s1", {"n": "stale"}, 1)  # another instance saved version 2 first
    assert store.load_session(p.id, "s1") == ("tavern", {"n": 1}, 2)
    assert store.load_session("someone-else", "s1") is None
    assert store.open_sessions(p.id) == 1
    assert store.delete_session(p.id, "s1") and store.session_version("s1") is None
    with pytest.raises(Conflict):
        store.save_session("s1", {}, 2)


def test_usage_is_kept_as_events_and_totalled_by_day(store):
    p, _ = store.create_project("a")
    now = time.time()
    store.record([Usage(p.id, "s1", "call", "react", True, "fake/model", latency_ms=40, prompt_tokens=100,
                        completion_tokens=20, at=now),
                  Usage(p.id, "s1", "line", "react", True, source="cache", at=now + 1),
                  Usage(p.id, "s1", "call", "act", False, latency_ms=4000, at=now + 2)])
    assert store.today(p.id) == (2, 120)
    events = store.usage(p.id)
    assert [(e.kind, e.ok, e.source) for e in events] == [("call", True, None), ("line", True, "cache"),
                                                          ("call", False, None)]
    assert store.usage(p.id, since=now + 0.5, until=now + 1.5)[0].source == "cache"
    assert store.usage("other") == []
    assert day(now) == time.strftime("%Y-%m-%d", time.gmtime())


def test_the_reply_cache_is_per_project_and_keeps_the_first_reply(store):
    a, _ = store.create_project("a")
    b, _ = store.create_project("b")
    store.put_reply(a.id, "k", "react", {"line": "first"}, "p")
    store.put_reply(a.id, "k", "react", {"line": "second"}, "p")
    assert store.get_reply(a.id, "k") == ({"line": "first"}, "p")
    assert store.get_reply(b.id, "k") is None


def test_sealed_settings_open_only_with_the_key_and_for_their_project():
    vault = Vault(new_secret())
    sealed = vault.seal("p_a", {"primary": {"api_key": "sk-secret"}})
    assert "sk-secret" not in sealed
    assert vault.open("p_a", sealed) == {"primary": {"api_key": "sk-secret"}}
    with pytest.raises(VaultError):
        vault.open("p_b", sealed)  # copied to another project's row
    with pytest.raises(VaultError):
        Vault(new_secret()).open("p_a", sealed)
    with pytest.raises(VaultError):
        Vault("dG9vIHNob3J0")
