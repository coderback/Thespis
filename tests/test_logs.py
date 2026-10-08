"""Structured logs: one JSON object per line in the image, a line per request, a line per model call."""

import json
import logging

import httpx
from fastapi.testclient import TestClient

from games import hosting
from games.crypt_road import app as app_module
from tests.test_gateway import BACKUP, MESSAGES, PRIMARY, FakeProviders, ok
from thespis.gateway import OpenAICompatGateway


def formatted(level, msg, *args, **extra):
    record = logging.LogRecord("thespis.test", level, __file__, 1, msg, args, None)
    record.__dict__.update(extra)
    return json.loads(hosting.JsonFormatter().format(record))


def test_a_json_line_has_what_railway_reads_and_every_extra_field():
    line = formatted(logging.WARNING, "boot #%d", 3, path="/data/thespis.sqlite")
    assert (line["message"], line["level"], line["logger"], line["path"]) == \
        ("boot #3", "warn", "thespis.test", "/data/thespis.sqlite")
    assert line["time"].endswith("+00:00") and "args" not in line and "msg" not in line
    assert formatted(logging.INFO, "x")["level"] == "info" and formatted(logging.CRITICAL, "x")["level"] == "error"


def test_configuring_twice_keeps_one_handler():
    root = logging.getLogger()
    others = [h for h in root.handlers if h.get_name() != "thespis"]
    hosting.configure_logging("json")
    hosting.configure_logging("text")
    ours = [h for h in root.handlers if h.get_name() == "thespis"]
    assert len(ours) == 1 and not isinstance(ours[0].formatter, hosting.JsonFormatter)
    assert [h for h in root.handlers if h.get_name() != "thespis"] == others  # pytest's own handlers are untouched


def test_each_request_logs_one_line_with_the_session_as_a_tag(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    with TestClient(app_module.app) as client:
        session = client.post("/session", json={}).json()["session"]
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="thespis.http"):
            client.get("/state", headers={"X-Session": session})
            client.get("/assets/missing.js")
    lines = [r for r in caplog.records if r.name == "thespis.http"]
    assert len(lines) == 1  # static assets aren't logged
    r = lines[0]
    assert (r.method, r.path, r.status) == ("GET", "/state", 200) and isinstance(r.ms, int)
    assert r.session == hosting.session_tag(session) and session not in r.getMessage() + r.session


def test_each_model_call_logs_its_numbers(caplog):
    fake = FakeProviders(primary=ok('{"line": "Hm.", "cites": ["e0001"]}'))
    g = OpenAICompatGateway([PRIMARY, BACKUP], transport=httpx.MockTransport(fake))
    with caplog.at_level(logging.INFO, logger="thespis.gateway"):
        g.complete("react", MESSAGES)
    r = next(r for r in caplog.records if r.name == "thespis.gateway")
    assert (r.call_type, r.provider, r.ok, r.error) == ("react", "primary", True, None)
    assert isinstance(r.latency_ms, int)


def test_httpx_logs_only_warnings_since_the_gateway_logs_each_call():
    hosting.configure_logging("text")
    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("thespis.gateway").getEffectiveLevel() == logging.INFO
