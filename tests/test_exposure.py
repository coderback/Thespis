"""Phase 1's gate: tools/exposure.py finds every edge shut on the app as it runs, with or without an admin token."""

import pytest
from fastapi.testclient import TestClient

from games.crypt_road import app as app_module
from tools import exposure


@pytest.mark.parametrize("token", [None, "s3cret"])
def test_a_stranger_finds_every_edge_shut(tmp_path, monkeypatch, token):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    if token:
        monkeypatch.setenv("ADMIN_TOKEN", token)
    else:
        monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    with TestClient(app_module.app) as client:
        failed = [(what, detail) for what, passed, detail in exposure.checks(client) if not passed]
    assert failed == []


def test_the_check_notices_an_open_edge(tmp_path, monkeypatch):
    """Turned on, the API docs are exactly what the check is there to catch."""
    from fastapi import FastAPI

    from games.hosting import Guard

    def server(guarded: bool) -> FastAPI:
        app = FastAPI()  # docs on: what the server was before Phase 1
        app.get("/health")(lambda: {"ok": True})
        if guarded:
            app.add_middleware(Guard)
        return app

    failed = {what for what, passed, _ in exposure.checks(TestClient(server(False))) if not passed}
    assert {"/docs isn't served", "/openapi.json isn't served", "pages are sent nosniff",
            "a 100 KiB body is refused"} <= failed
    failed = {what for what, passed, _ in exposure.checks(TestClient(server(True))) if not passed}
    assert "pages are sent nosniff" not in failed and "/docs isn't served" in failed
