"""Provider profiles (thespis.profiles) in the gateway: any endpoint, the schema it can enforce, its own time budget,
Anthropic's Messages API, and player-facing calls first."""

import json
import threading
import time

import httpx
import pytest

from thespis.expression import schema_for
from thespis.gateway import OpenAICompatGateway, PrioritySlots, Provider, gateway_from_env, provider_from_env
from thespis.profiles import PROFILES, profile

MESSAGES = [{"role": "system", "content": "You are Garrick."}, {"role": "user", "content": "{}"}]
SCHEMA = schema_for(["b1", "e1"])


def test_the_schema_follows_what_the_provider_enforces():
    local = PROFILES["llamacpp"].adapt(SCHEMA, "act")["properties"]
    assert local["cites"]["minItems"] == 1 and local["line"]["maxLength"] == 160
    assert PROFILES["llamacpp"].adapt(SCHEMA, "narrate")["properties"]["line"]["maxLength"] == 400
    assert PROFILES["openai"].adapt(SCHEMA, "act") == SCHEMA  # strict refuses both keywords
    claims = {"type": "object", "properties": {"claims": {"type": "array"}}}
    assert PROFILES["llamacpp"].adapt(claims, "extract") == claims  # only Thespis's reply schema is touched


def test_a_local_profile_needs_no_key_and_has_a_longer_budget():
    p = provider_from_env({"LLM_PROFILE": "llamacpp", "LLM_MODEL": "qwen3.5-4b"}, "LLM_")
    assert p is not None and p.base_url == "http://127.0.0.1:8080/v1" and p.headers() == {}
    assert p.profile.timeout == 15.0
    assert provider_from_env({"LLM_MODEL": "m", "LLM_BASE_URL": "https://x.test/v1"}, "LLM_") is None  # cloud: key
    tuned = provider_from_env({"LLM_PROFILE": "ollama", "LLM_MODEL": "m", "LLM_TIMEOUT": "30"}, "LLM_")
    assert tuned is not None and tuned.profile.timeout == 30.0


def test_an_unknown_profile_fails_loudly():
    with pytest.raises(ValueError, match="no profile 'llama'"):
        profile("llama")


def test_a_probed_profile_loads_from_its_file(tmp_path):
    path = tmp_path / "laptop.json"
    path.write_text(json.dumps({**PROFILES["llamacpp"].to_json(), "name": "laptop", "timeout": 9.5}))
    p = profile(str(path))
    assert (p.name, p.timeout, p.enforces) == ("laptop", 9.5, frozenset({"minItems", "maxLength"}))


def gateway(provider: Provider, handler) -> OpenAICompatGateway:
    return OpenAICompatGateway([provider], transport=httpx.MockTransport(handler))


def test_each_provider_has_its_own_time_budget():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"]["read"])
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"cites": ["e1"], "line": "Hm."}'}}]})

    local = provider_from_env({"LLM_PROFILE": "llamacpp", "LLM_MODEL": "m"}, "LLM_")
    assert local is not None
    gateway(local, handler).complete("act", MESSAGES, SCHEMA)
    cloud = Provider("cloud", "https://api.openai.com/v1", "k", "m")
    gateway(cloud, handler).complete("act", MESSAGES, SCHEMA)
    assert seen == [14.0, 3.0]  # each budget less the second allowed for connecting


def test_a_grammar_provider_gets_the_constraints_in_its_request():
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"cites": ["e1"], "line": "Hm."}'}}]})

    local = provider_from_env({"LLM_PROFILE": "llamacpp", "LLM_MODEL": "m"}, "LLM_")
    assert local is not None
    reply = gateway(local, handler).complete("act", MESSAGES, SCHEMA)
    assert reply is not None and reply.data["line"] == "Hm."
    schema = bodies[0]["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["cites"]["minItems"] == 1
    assert bodies[0]["chat_template_kwargs"] == {"enable_thinking": False}


def test_anthropic_speaks_through_a_tool_call():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={
            "content": [{"type": "tool_use", "name": "act", "input": {"cites": ["e1"], "line": "Careful."}}],
            "stop_reason": "tool_use", "usage": {"input_tokens": 300, "output_tokens": 20}})

    p = provider_from_env({"LLM_PROFILE": "anthropic", "LLM_API_KEY": "sk-test", "LLM_MODEL": "claude-haiku-5-5"},
                          "LLM_")
    assert p is not None
    g = gateway(p, handler)
    reply = g.complete("act", MESSAGES, SCHEMA)
    assert reply is not None and reply.data == {"cites": ["e1"], "line": "Careful."}
    r = requests[0]
    body = json.loads(r.content)
    assert str(r.url) == "https://api.anthropic.com/v1/messages"
    assert r.headers["x-api-key"] == "sk-test" and r.headers["anthropic-version"] == "2023-06-01"
    assert body["system"] == "You are Garrick." and [m["role"] for m in body["messages"]] == ["user"]
    assert body["tool_choice"] == {"type": "tool", "name": "act"} and body["tools"][0]["input_schema"] == SCHEMA
    assert (g.calls[-1].prompt_tokens, g.calls[-1].completion_tokens) == (300, 20)


def test_an_anthropic_refusal_is_a_failed_call():
    p = Provider("a", "https://api.anthropic.com/v1", "k", "m", profile=PROFILES["anthropic"])
    g = gateway(p, lambda r: httpx.Response(200, json={"content": [], "stop_reason": "refusal"}))
    assert g.complete("act", MESSAGES, SCHEMA) is None and g.calls[-1].error == "refusal"


def test_a_json_mode_provider_is_never_sent_a_schema():
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"cites": ["e1"], "line": "Hm."}'}}]})

    p = provider_from_env({"LLM_PROFILE": "groq", "LLM_API_KEY": "k", "LLM_MODEL": "m"}, "LLM_")
    assert p is not None
    gateway(p, handler).complete("act", MESSAGES, SCHEMA)
    assert bodies[0]["response_format"] == {"type": "json_object"}


def test_player_facing_calls_go_before_background_work():
    slots, order = PrioritySlots(1), []
    slots.acquire(0)  # a call in flight

    def wait(priority: int, name: str) -> None:
        slots.acquire(priority)
        order.append(name)
        slots.release()

    background = threading.Thread(target=wait, args=(1, "warm-up"))
    background.start()
    time.sleep(0.05)
    player = threading.Thread(target=wait, args=(0, "act"))
    player.start()
    time.sleep(0.05)
    slots.release()
    background.join(2)
    player.join(2)
    assert order == ["act", "warm-up"]  # it arrived second and went first


def test_with_no_provider_there_is_no_model():
    assert gateway_from_env({"LLM_PROFILE": "openai", "LLM_MODEL": "m"}).providers == ()
