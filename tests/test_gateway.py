"""The model gateway: primary, then backup, then fallback, and never an error for the player."""

import json
import threading
import time

import httpx
import pytest

from thespis import gateway as gw
from thespis.gateway import NoModel, OpenAICompatGateway, Provider, gateway_from_env, parse_json

PRIMARY = Provider("primary", "https://primary.test/v1", "key-p", "fast-1", {"enable_thinking": False})
BACKUP = Provider("backup", "https://backup.test/v1/", "key-b", "fast-2")
MESSAGES = [{"role": "system", "content": "You are Kael."}, {"role": "user", "content": "Pick an action."}]


def ok(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


class FakeProviders:
    """Each host answers with whatever its behaviour says; every request is recorded."""

    def __init__(self, **behaviour):
        self.behaviour = behaviour  # host prefix -> callable(request) -> Response, or an exception to raise
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        answer = self.behaviour[request.url.host.split(".")[0]]
        result = answer(request) if callable(answer) else answer
        if isinstance(result, Exception):
            raise result
        return result

    def hosts(self):
        return [r.url.host.split(".")[0] for r in self.requests]


def gateway(fake, clock=time.monotonic):
    return OpenAICompatGateway([PRIMARY, BACKUP], transport=httpx.MockTransport(fake), clock=clock)


def test_request_uses_the_design_settings():
    fake = FakeProviders(primary=ok('{"action": "go_to", "line": "Out of my way.", "cites": ["b0009"]}'))
    reply = gateway(fake).complete("act", MESSAGES)
    assert reply.data == {"action": "go_to", "line": "Out of my way.", "cites": ["b0009"]}
    assert (reply.provider, reply.model) == ("primary", "fast-1") and reply.latency >= 0
    request = fake.requests[0]
    assert str(request.url) == "https://primary.test/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer key-p"
    body = json.loads(request.content)
    assert body == {"model": "fast-1", "messages": MESSAGES, "max_tokens": 150, "temperature": 0.6,
                    "response_format": {"type": "json_object"}, "enable_thinking": False}


def test_reading_the_players_words_is_deterministic():
    fake = FakeProviders(primary=ok('{"act": "none", "sure": "certain"}'))
    for call_type in ("understand", "confirm"):
        gateway(fake).complete(call_type, MESSAGES)
    assert [json.loads(r.content)["temperature"] for r in fake.requests] == [0.0, 0.0]


@pytest.mark.parametrize("failure", [
    httpx.Response(500, text="boom"),
    httpx.ReadTimeout("slow"),
    httpx.ConnectError("down"),
    ok("not json at all"),
    ok('["a list, not an object"]'),
    httpx.Response(200, json={"unexpected": True}),
])
def test_any_primary_failure_falls_to_the_backup(failure):
    fake = FakeProviders(primary=failure, backup=ok('{"line": "Fine."}'))
    g = gateway(fake)
    reply = g.complete("react", MESSAGES)
    assert reply.provider == "backup" and reply.data == {"line": "Fine."}
    assert [(c.provider, c.ok) for c in g.calls] == [("primary", False), ("backup", True)]
    assert str(fake.requests[1].url) == "https://backup.test/v1/chat/completions"  # trailing slash handled


def test_both_failing_returns_none_never_raises():
    fake = FakeProviders(primary=httpx.ReadTimeout("slow"), backup=httpx.Response(503))
    g = gateway(fake)
    assert g.complete("act", MESSAGES) is None
    assert [c.error for c in g.calls] == ["timeout", "HTTP 503"]


def test_killing_the_primary_key_mid_run():
    """#16's done-when: primary dies -> backup, backup dies -> fallback, and dead keys stop being tried."""
    keys = {"primary": True, "backup": True}

    def answer(name):
        return lambda request: ok('{"line": "Hm."}') if keys[name] else httpx.Response(401, text="invalid key")

    now = [0.0]
    fake = FakeProviders(primary=answer("primary"), backup=answer("backup"))
    g = gateway(fake, clock=lambda: now[0])
    assert g.complete("react", MESSAGES).provider == "primary"
    keys["primary"] = False  # the key is revoked mid-run
    assert g.complete("react", MESSAGES).provider == "backup"
    assert g.complete("react", MESSAGES).provider == "backup"
    assert fake.hosts() == ["primary", "primary", "backup", "backup"]  # the dead key was tried once, then skipped
    keys["backup"] = False  # the backup's credit runs out too
    assert g.complete("react", MESSAGES) is None  # the caller uses its fallback line
    assert g.complete("react", MESSAGES) is None  # both keys are cooling down: no request is even sent
    assert fake.hosts() == ["primary", "primary", "backup", "backup", "backup"]
    now[0] += 601  # after the cooldown a fixed key would be tried again
    keys["primary"] = True
    assert g.complete("react", MESSAGES).provider == "primary"


def test_rate_limit_skips_the_provider_briefly():
    now = [0.0]
    fake = FakeProviders(primary=httpx.Response(429), backup=ok('{"line": "Fine."}'))
    g = gateway(fake, clock=lambda: now[0])
    g.complete("react", MESSAGES)
    g.complete("react", MESSAGES)
    assert fake.hosts() == ["primary", "backup", "backup"]
    now[0] += 31
    g.complete("react", MESSAGES)
    assert fake.hosts()[-2:] == ["primary", "backup"]


def test_fenced_json_is_accepted():
    assert parse_json('```json\n{"action": "wait"}\n```') == {"action": "wait"}
    with pytest.raises(ValueError):
        parse_json("[1, 2]")


def test_calls_for_different_npcs_run_in_parallel_and_at_most_four_at_once():
    in_flight, peak, lock = [0], [0], threading.Lock()

    def slow(request):
        with lock:
            in_flight[0] += 1
            peak[0] = max(peak[0], in_flight[0])
        time.sleep(0.25)
        with lock:
            in_flight[0] -= 1
        return ok('{"line": "Hm."}')

    g = OpenAICompatGateway([PRIMARY], transport=httpx.MockTransport(slow))
    started = time.perf_counter()
    replies = g.complete_many([("act", MESSAGES, None)] * 4)
    assert all(r and r.provider == "primary" for r in replies)
    assert time.perf_counter() - started < 0.75  # four 0.25 s calls in parallel, not 1 s in sequence
    g.complete_many([("act", MESSAGES, None)] * 4 + [("react", MESSAGES, None)] * 4)
    assert peak[0] <= gw.MAX_CONCURRENT


def test_configuration_from_the_environment():
    assert isinstance(gateway_from_env({}), NoModel)
    assert gateway_from_env({}).complete("act", MESSAGES) is None
    g = gateway_from_env({
        "LLM_BASE_URL": "https://api.example.com/v1", "LLM_API_KEY": "k1", "LLM_MODEL": "m1",
        "LLM_EXTRA": '{"thinking": {"type": "disabled"}}',
        "LLM_BACKUP_BASE_URL": "https://other.example.org/v1", "LLM_BACKUP_API_KEY": "k2", "LLM_BACKUP_MODEL": "m2",
    })
    assert [p.name for p in g.providers] == ["api.example.com/m1", "other.example.org/m2"]
    assert g.providers[0].extra == {"thinking": {"type": "disabled"}}
    assert "k1" not in repr(g.providers[0])  # keys never reach logs
    half = gateway_from_env({"LLM_BASE_URL": "https://api.example.com/v1", "LLM_API_KEY": "k1"})
    assert isinstance(half, NoModel)  # incomplete settings mean no model, not a crash


def test_azure_uses_the_api_key_header_and_api_version():
    fake = FakeProviders(myres=ok('{"line": "Hm."}'))
    azure = Provider("azure", "https://myres.openai.azure.com/openai/deployments/fast-mini", "az-key", "fast-mini",
                     api_version="2024-10-21")
    reply = OpenAICompatGateway([azure], transport=httpx.MockTransport(fake)).complete("react", MESSAGES)
    assert reply.provider == "azure"
    request = fake.requests[0]
    assert str(request.url) == ("https://myres.openai.azure.com/openai/deployments/fast-mini/chat/completions"
                                "?api-version=2024-10-21")
    assert request.headers["api-key"] == "az-key" and "authorization" not in request.headers
    v1 = Provider("azure-v1", "https://myres.openai.azure.com/openai/v1/", "az-key", "fast-mini")
    assert v1.url() == "https://myres.openai.azure.com/openai/v1/chat/completions" and v1.azure
    assert "Authorization" in PRIMARY.headers() and not PRIMARY.azure  # other providers keep Bearer


def test_null_in_extra_removes_a_field():
    reasoning = Provider("r", "https://x.test/v1", "k", "reasoner",
                         {"max_tokens": None, "temperature": None, "max_completion_tokens": 300})
    body = reasoning.body(MESSAGES)
    assert "max_tokens" not in body and "temperature" not in body and body["max_completion_tokens"] == 300


def test_api_version_from_the_environment():
    g = gateway_from_env({"LLM_BASE_URL": "https://r.openai.azure.com/openai/deployments/d", "LLM_API_KEY": "k",
                          "LLM_MODEL": "d", "LLM_API_VERSION": "2024-10-21"})
    assert g.providers[0].api_version == "2024-10-21" and g.providers[0].azure


def with_usage(request):
    return httpx.Response(200, json={"choices": [{"message": {"content": '{"line": "Hm.", "cites": ["e0001"]}'}}],
                                     "usage": {"prompt_tokens": 812, "completion_tokens": 21}})


def test_calls_are_logged_with_their_tokens_and_counted():
    g = gateway(FakeProviders(primary=with_usage))
    g.complete("act", MESSAGES)
    g.complete("react", MESSAGES)
    assert g.total == 2 and len(g.calls) == 2
    assert (g.calls[-1].call_type, g.calls[-1].prompt_tokens, g.calls[-1].completion_tokens) == ("react", 812, 21)


def test_dev_calls_returns_only_the_calls_since_a_total(tmp_path, monkeypatch):
    """#25's harness reads the host's call log: latency and tokens for just the calls its run made."""
    from fastapi.testclient import TestClient

    from games.crypt_road.app import app
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin")
    with TestClient(app, headers={"Authorization": "Bearer test-admin"}) as client:
        g = app.state.gateway = gateway(FakeProviders(primary=with_usage))
        assert client.get("/dev/calls").json() == {"total": 0, "calls": []}
        g.complete("act", MESSAGES)
        g.complete("react", MESSAGES)
        r = client.get("/dev/calls", params={"since": 1}).json()
        assert r["total"] == 2 and [c["call_type"] for c in r["calls"]] == ["react"]
        assert (r["calls"][0]["provider"], r["calls"][0]["ok"], r["calls"][0]["prompt_tokens"]) == ("primary", True, 812)
        assert client.get("/dev/calls", params={"since": 2}).json()["calls"] == []


def test_a_reply_with_no_content_falls_back_instead_of_raising():
    """Azure can answer 200 with a null content; that once escaped as an AttributeError and broke the request."""
    fake = FakeProviders(primary=httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
                         backup=ok('{"line": "Hm.", "cites": ["e0001"]}'))
    g = gateway(fake)
    assert g.complete("react", MESSAGES).provider == "backup"
    assert g.calls[0].error == "no content in the reply"


def test_a_filtered_reply_counts_as_a_failed_call():
    filtered = httpx.Response(200, json={"choices": [{"message": {"content": ""}, "finish_reason": "content_filter"}]})
    g = gateway(FakeProviders(primary=filtered, backup=filtered))
    assert g.complete("react", MESSAGES) is None
    assert [c.error for c in g.calls] == ["content_filter: reply", "content_filter: reply"]


def test_a_filtered_prompt_counts_as_a_failed_call_with_no_cooldown():
    refused = httpx.Response(400, json={"error": {"code": "content_filter", "message": "The prompt was filtered."}})
    fake = FakeProviders(primary=refused, backup=refused)
    g = gateway(fake)
    assert g.complete("react", MESSAGES) is None
    assert g.calls[0].error == "content_filter: prompt"
    g.complete("react", MESSAGES)
    assert fake.hosts() == ["primary", "backup", "primary", "backup"]  # the next text is tried everywhere again
    other = httpx.Response(400, json={"error": {"code": "bad_request"}})
    g = gateway(FakeProviders(primary=other, backup=other))
    g.complete("react", MESSAGES)
    assert g.calls[0].error == "HTTP 400"


SCHEMA = {"type": "object", "additionalProperties": False, "required": ["line"], "properties": {"line": {"type": "string"}}}


def test_a_call_with_a_schema_asks_for_structured_outputs():
    fake = FakeProviders(primary=ok('{"line": "Out of my way."}'))
    gateway(fake).complete("act", MESSAGES, SCHEMA)
    assert json.loads(fake.requests[0].content)["response_format"] == \
        {"type": "json_schema", "json_schema": {"name": "act", "strict": True, "schema": SCHEMA}}


def test_a_provider_set_to_json_mode_never_gets_the_schema():
    fake = FakeProviders(primary=ok('{"line": "Hm."}'))
    g = OpenAICompatGateway([gw.provider_from_env({"LLM_BASE_URL": "https://primary.test/v1", "LLM_API_KEY": "k",
                                                   "LLM_MODEL": "m", "LLM_STRUCTURED": "0"}, "LLM_")],
                            transport=httpx.MockTransport(fake))
    g.complete("act", MESSAGES, SCHEMA)
    assert json.loads(fake.requests[0].content)["response_format"] == {"type": "json_object"}


def test_a_provider_that_refuses_the_schema_is_asked_again_in_json_mode_from_then_on():
    def primary(request):
        if json.loads(request.content)["response_format"]["type"] == "json_schema":
            return httpx.Response(400, json={"error": {"message": "Invalid parameter: 'response_format' of type "
                                                                  "'json_schema' is not supported with this model.",
                                                       "param": "response_format", "code": None}})
        return ok('{"line": "Hm."}')
    fake = FakeProviders(primary=primary, backup=ok('{"line": "Backup."}'))
    g = gateway(fake)
    assert g.complete("act", MESSAGES, SCHEMA).provider == "primary"
    assert [c.error for c in g.calls] == ["schema refused", None]
    g.complete("act", MESSAGES, SCHEMA)
    formats = [json.loads(r.content)["response_format"]["type"] for r in fake.requests]
    assert formats == ["json_schema", "json_object", "json_object"] and fake.hosts() == ["primary"] * 3


def test_a_model_refusal_counts_as_a_failed_call():
    refused = httpx.Response(200, json={"choices": [{"message": {"content": None, "refusal": "I can't help with that."}}]})
    g = gateway(FakeProviders(primary=refused, backup=ok('{"line": "Hm."}')))
    assert g.complete("act", MESSAGES, SCHEMA).provider == "backup"
    assert g.calls[0].error == "refusal"
