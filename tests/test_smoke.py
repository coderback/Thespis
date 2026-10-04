"""#30: the smoke test passes on a warm host and says what to do when the cache is cold."""

import pytest

from tests.test_model_voice import FakeModel
from tools import smoke, warm_cache


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from games.crypt_road.app import app
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    with TestClient(app) as c:
        app.state.gateway = FakeModel()
        yield c


def by_name(results):
    return {name: (ok, detail) for name, ok, detail in results}


def test_a_warm_host_passes(client):
    warm_cache.play(client)  # warm the cache, as tools/warm_cache.py does on the host
    results = by_name(smoke.run(client, "07:00 UTC"))
    for name, (ok, detail) in results.items():
        if name != "client loads":  # depends on whether client/dist has been built here
            assert ok, f"{name}: {detail}"
    assert results["model answers"][1].startswith("answered by")


def test_a_cold_cache_fails_and_says_how_to_warm_it(client):
    ok, detail = by_name(smoke.run(client, "07:00 UTC"))["Watch route from the cache"]
    assert not ok and "tools/warm_cache.py" in detail
