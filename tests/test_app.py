"""The hosted app: /health answers, and the database it writes survives a restart."""

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from games.crypt_road import app as app_module
from thespis.store import Store


def test_health(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "thespis.sqlite"))
    with TestClient(app_module.app) as client:
        assert client.get("/health").json() == {"ok": True}


def test_boot_count_persists_across_restarts(tmp_path, monkeypatch):
    db = tmp_path / "nested" / "thespis.sqlite"
    monkeypatch.setenv("DB_PATH", str(db))
    for _ in range(3):
        with TestClient(app_module.app):  # each start-up runs the lifespan, which records a boot
            pass
    assert Store(db).record_boot() == 4  # three app starts, then this call


def test_the_database_stays_on_the_volume(tmp_path, monkeypatch):
    """A DB_PATH off the attached volume (e.g. ./data copied from .env.example) would lose everything on a deploy."""
    volume = tmp_path / "volume"
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(volume))
    monkeypatch.setenv("DB_PATH", "./data/thespis.sqlite")
    assert app_module.db_path() == volume / "thespis.sqlite"
    monkeypatch.setenv("DB_PATH", str(volume / "other.sqlite"))
    assert app_module.db_path() == volume / "other.sqlite"  # on the volume: kept
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH")
    monkeypatch.setenv("DB_PATH", "./data/thespis.sqlite")
    assert app_module.db_path() == Path("./data/thespis.sqlite")  # no volume, e.g. locally: as given


def test_boot_count_carries_over_from_the_first_deploy(tmp_path):
    """The first deploy counted boots in their own table; the host's count must keep rising, not restart at 1."""
    db = tmp_path / "thespis.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE boots (id INTEGER PRIMARY KEY, at REAL NOT NULL)")
        conn.executemany("INSERT INTO boots (at) VALUES (?)", [(1.0,), (2.0,)])
    assert Store(db).record_boot() == 3
