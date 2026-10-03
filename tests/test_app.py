"""The hosted app: /health answers, and the database it writes survives a restart."""

from fastapi.testclient import TestClient

from games.crypt_road import app as app_module


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
    assert app_module.record_boot(db) == 4  # three app starts, then this call
