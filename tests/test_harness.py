"""#25: the harness plays every route, reads the host's call log, and counts what results.md reports."""

import json

import httpx
import pytest

from tests.test_model_voice import FakeModel
from thespis.gateway import OpenAICompatGateway, Provider
from tools import harness
from tools.routes import EXPECTED


def azure_like(bad_every: int = 0):
    """A model endpoint that answers like FakeModel, with token usage; every `bad_every`-th reply cites a bad id."""
    count = {"n": 0}

    def answer(request):
        count["n"] += 1
        pack = json.loads(json.loads(request.content)["messages"][1]["content"])
        data = FakeModel.good("decide" if "ALLOWED" in pack else "react", pack)
        if bad_every and count["n"] % bad_every == 0:
            data["cites"] = ["e9999"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(data)}}],
                                         "usage": {"prompt_tokens": 900, "completion_tokens": 30}})
    return httpx.MockTransport(answer)


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from games.crypt_road.app import app
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin")  # the tools read the host's call log, which needs it
    with TestClient(app, headers={"Authorization": "Bearer test-admin"}) as c:
        yield app, c


def test_the_harness_measures_every_route(client):
    app, c = client
    app.state.gateway = OpenAICompatGateway([Provider("azure/gpt-6-luna", "https://primary.test/v1", "k", "gpt-6-luna")],
                                            transport=azure_like(bad_every=7))
    results = harness.measure(c, [1])
    assert [r["outcome"] for r in results["rules"]] == [EXPECTED[r["route"]] for r in results["rules"]]
    assert all(not r["calls"] for r in results["rules"])  # the brain off makes no model calls
    s = harness.summarise(results)
    assert s["runs"] == len(EXPECTED) and s["calls"] == s["ok"] > 0
    assert s["tokens"]["gpt-6-luna"] == [900 * s["ok"], 30 * s["ok"]]
    assert s["cost"] == pytest.approx(s["ok"] * (900 * 0.10 + 30 * 0.50) / 1e6)
    assert s["blocked"] and set(s["blocked"]) == {"cites ids not in its state pack"}
    assert 0 < s["code_only"] < 1 and s["asked"] > 0
    assert s["with_call"] > 0 and s["no_call"] > 0 and s["with_call"] + s["no_call"] == s["acts"]
    assert s["live_per_run"] >= s["calls_per_run"] and s["live_cost_per_run"] >= s["cost_per_run"]
    assert all(r["talked"] > 0 for r in results["model"])  # each model run asks a question of its own
    assert all(r["talked"] == 0 for r in results["rules"])
    text = harness.report(results, "http://test", "abc1234")
    assert text.startswith("# Results") and "| frame | 1 |" in text and "✗" not in text


def test_blocked_reasons_are_grouped():
    assert harness.why_blocked("go_to scores 5; model reply rejected: action 'fly' is not allowed") == "action not allowed"
    assert harness.why_blocked("talk; model reply rejected: cites e0099, not in its state pack") == \
        "cites ids not in its state pack"
    assert harness.why_blocked("talk; model reply rejected: names odo, absent from its state pack") == \
        "names someone absent from its state pack"
    assert harness.why_blocked("talk; model reply rejected: line is 200 characters, over 160") == "line too long"


def test_percentiles():
    assert harness.percentile([], 50) is None
    assert harness.percentile([3.0], 95) == 3.0
    values = [float(i) for i in range(1, 101)]
    assert (harness.percentile(values, 50), harness.percentile(values, 95)) == (50.0, 95.0)
