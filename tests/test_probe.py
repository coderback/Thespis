"""The endpoint probe (thespis.probe): it measures what an endpoint enforces rather than trusting its kind."""

import json

import httpx

from thespis.probe import Prober


def fake(enforcing: bool, llamacpp: bool = True):
    """A server that keeps to schemas (as a llama.cpp grammar does) or ignores them."""
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/props":
            return httpx.Response(200, json={"total_slots": 3}) if llamacpp else httpx.Response(404)
        if path == "/api/version":
            return httpx.Response(404)
        if path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "local-model", "owned_by": "llamacpp"}]})
        body = json.loads(request.content)
        if body.get("stream"):
            return httpx.Response(200, text='data: {"choices": [{"delta": {"role": "assistant"}}]}\n\n'
                                            'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\ndata: [DONE]\n\n')
        prompt = body["messages"][-1]["content"]
        schema = (body.get("response_format") or {}).get("json_schema", {}).get("schema")
        cites, line = ["e7"] if "e7" in prompt else [] if "Cite nothing" in prompt else ["e1"], "word " * 60
        if enforcing and schema:
            props = schema["properties"]
            cites = [c for c in cites if c in props["cites"]["items"]["enum"]] or \
                (["e1"] if props["cites"].get("minItems") else [])
            line = line[:props["line"].get("maxLength", len(line))]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"cites": cites,
                                                                                         "line": line})}}]})
    return httpx.Client(transport=httpx.MockTransport(handler))


def ticks():
    t = [0.0]

    def clock():
        t[0] += 0.5
        return t[0]
    return clock


def test_a_server_that_enforces_its_schema_gets_a_grammar_profile():
    p = Prober("http://127.0.0.1:8080/v1", client=fake(enforcing=True), clock=ticks()).run("laptop")
    assert (p.name, p.schema, p.enforces, p.concurrency) == ("laptop", "grammar", frozenset({"minItems", "maxLength"}),
                                                            3)
    assert p.measured["kind"] == "llamacpp" and p.measured["model"] == "local-model"
    assert p.measured["p50_s"] == 0.5 and p.measured["first_token_s"] == 0.5
    assert p.timeout == 4.0  # at least the cloud's budget; more when p95 asks for it


def test_a_server_that_ignores_its_schema_is_held_to_json_mode():
    p = Prober("http://models.test/v1", client=fake(enforcing=False, llamacpp=False), clock=ticks()).run()
    assert (p.schema, p.enforces) == ("json", frozenset())
    assert "outside the enum" in p.measured["schema"]
