"""Probing a model endpoint: what it is, what it enforces and how fast it answers, written down as a profile.

    python -m thespis models probe http://127.0.0.1:8080/v1 --out llamacpp-laptop.json
    LLM_PROFILE=llamacpp-laptop.json ...

The probe works out the kind of server: llama.cpp answers /props, Ollama /api/version, vLLM names itself in
/models, and the cloud providers are known by host. Then it measures rather than trusts:
- **Schema:** asked to cite a reference its schema leaves out, does the reply keep to the schema's enum? If not, or
  if the provider refuses schemas, the profile uses JSON mode, since a schema it ignores only costs time.
- **minItems and maxLength:** asked for no citations, or for a long line under a short limit, does the reply keep to
  them? Only what is enforced goes into the profile (thespis.profiles.Profile.adapt).
- **Latency:** five typical calls give p50 and p95, and the time budget is set from p95 with room to spare.
- **First token:** a streamed call's time to its first words, which is what a player would wait for if lines
  streamed.

A probe costs about ten small calls.
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import replace
from urllib.parse import urlparse

import httpx

from thespis.gateway import Provider
from thespis.profiles import PROFILES, Profile

LATENCY_CALLS = 5
SYSTEM = 'You are a test. Reply with JSON only: {"cites": ["..."], "line": "..."}'
_HOSTS = {"openai.com": "openai", "azure.com": "azure", "azure-api.net": "azure", "openrouter.ai": "openrouter",
          "groq.com": "groq", "together.xyz": "together", "googleapis.com": "gemini", "anthropic.com": "anthropic"}


def _schema(refs: list[str]) -> dict:
    return {"type": "object", "additionalProperties": False, "required": ["cites", "line"],
            "properties": {"cites": {"type": "array", "items": {"type": "string", "enum": refs}},
                           "line": {"type": "string"}}}


def kind(url: str, client: httpx.Client) -> tuple[str, dict]:
    """Which built-in profile the endpoint is, and what it said about itself."""
    host = urlparse(url).hostname or ""
    for suffix, name in _HOSTS.items():
        if host.endswith(suffix):
            return name, {}
    root = url.rstrip("/").removesuffix("/v1")
    for path, name in (("/props", "llamacpp"), ("/api/version", "ollama")):
        try:
            r = client.get(root + path, timeout=5)
            if r.status_code == 200 and isinstance(r.json(), dict):
                return name, r.json()
        except (httpx.HTTPError, ValueError):
            pass
    try:
        models = client.get(url.rstrip("/") + "/models", timeout=5).json().get("data", [])
        if any(m.get("owned_by") == "vllm" for m in models):
            return "vllm", {}
    except (httpx.HTTPError, ValueError, AttributeError):
        pass
    return "openai", {}


def first_model(url: str, key: str, client: httpx.Client) -> str:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        data = client.get(url.rstrip("/") + "/models", headers=headers, timeout=10).json().get("data", [])
        return data[0]["id"] if data else ""
    except (httpx.HTTPError, ValueError, AttributeError, KeyError, IndexError):
        return ""


class Prober:
    def __init__(self, url: str, key: str = "", model: str = "", client: httpx.Client | None = None,
                 clock=time.perf_counter):
        self.url, self.key = url.rstrip("/"), key
        self.client = client or httpx.Client(timeout=60)
        self.clock = clock
        self.kind, self.about = kind(self.url, self.client)
        self.base = PROFILES[self.kind]
        self.model = model or first_model(self.url, key, self.client)
        if not self.model:
            raise ValueError("couldn't tell which model to probe; name it with --model")

    def _ask(self, profile: Profile, prompt: str, schema: dict | None,
             call_type: str = "act") -> tuple[dict | None, str | None, float]:
        """One call: the reply's JSON or why there's none, and how long it took."""
        p = Provider("probe", self.url, self.key, self.model, profile=profile)
        started = self.clock()
        try:
            r = self.client.post(p.url(), json=p.body([{"role": "system", "content": SYSTEM},
                                                       {"role": "user", "content": prompt}], schema, call_type),
                                 headers=p.headers(), timeout=60)
            took = self.clock() - started
            if r.status_code != 200:
                return None, f"HTTP {r.status_code}: {r.text[:120]}", took
            data, error, _ = p.read(r.json())
            return data, error, took
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as e:
            return None, f"{type(e).__name__}: {e}"[:200], self.clock() - started

    def schema_mode(self) -> tuple[str, str]:
        """strict/grammar/tool if the endpoint keeps to a schema's enum, else json; and what was seen."""
        if self.base.schema == "tool":
            data, error, _ = self._ask(self.base, 'Cite "e7" and say hello.', _schema(["e1", "e2"]))
            return ("tool", "tool input kept to the schema") if data is not None else ("json", error or "no reply")
        data, error, _ = self._ask(self.base, 'Cite "e7" (not e1 or e2) and say hello.', _schema(["e1", "e2"]))
        if data is None:
            return "json", f"schema call failed: {error}"
        cites = data.get("cites")
        if isinstance(cites, list) and all(c in ("e1", "e2") for c in cites):
            mode = self.base.schema if self.base.schema in ("strict", "grammar") else "strict"
            return mode, f"kept to the enum when asked to break it (cited {cites})"
        return "json", f"cited {cites} outside the enum: the schema isn't enforced"

    def enforced(self, mode: str) -> tuple[frozenset[str], dict]:
        """Which of minItems and maxLength the endpoint holds a reply to."""
        found, seen = set(), {}
        trial = replace(self.base, schema=mode, enforces=frozenset({"minItems", "maxLength"}))
        schema = _schema(["e1", "e2"])
        data, error, _ = self._ask(trial, "Cite nothing: cites must be the empty list []. Say hello.", schema)
        seen["minItems"] = error or f"cites {data.get('cites') if data else None}"
        if data is not None and isinstance(data.get("cites"), list) and len(data["cites"]) >= 1:
            found.add("minItems")
        long = "Say a line of at least 60 words about the weather, citing e1."
        data, error, _ = self._ask(trial, long, schema, call_type="act")
        line = data.get("line") if data else None
        seen["maxLength"] = error or f"line of {len(line) if isinstance(line, str) else None} characters"
        if isinstance(line, str) and len(line) <= trial.adapt(schema, "act")["properties"]["line"]["maxLength"]:
            found.add("maxLength")
        return frozenset(found), seen

    def latency(self, profile: Profile) -> list[float]:
        prompt = ("You are Garrick, a proud sellsword in a tavern. Events: e1: the player insulted you; e2: Wren "
                  "watched. Say one line, at most 25 words, citing what you rely on.")
        return [self._ask(profile, prompt, _schema(["e1", "e2"]) if profile.schema != "json" else None)[2]
                for _ in range(LATENCY_CALLS)]

    def first_token(self) -> float | None:
        """Seconds to the first streamed words (OpenAI-style servers only)."""
        if self.base.api != "openai":
            return None
        p = Provider("probe", self.url, self.key, self.model, profile=self.base)
        body = {**p.body([{"role": "user", "content": "Say hello in five words."}], None, "react"), "stream": True}
        body.pop("response_format", None)
        started = self.clock()
        try:
            with self.client.stream("POST", p.url(), json=body, headers=p.headers(), timeout=60) as r:
                for raw in r.iter_lines():
                    if raw.startswith("data:") and raw[5:].strip() not in ("", "[DONE]"):
                        delta = json.loads(raw[5:])["choices"][0].get("delta", {})
                        if delta.get("content"):
                            return self.clock() - started
        except (httpx.HTTPError, ValueError, KeyError, IndexError):
            return None
        return None

    def run(self, name: str = "") -> Profile:
        mode, schema_seen = self.schema_mode()
        enforces, enforce_seen = self.enforced(mode) if mode in ("grammar", "strict") else (frozenset(), {})
        profile = replace(self.base, name=name or f"{self.kind}-probed", base_url=self.url, schema=mode,
                          enforces=enforces)
        times = sorted(self.latency(profile))
        p50, p95 = statistics.median(times), times[min(len(times) - 1, round(0.95 * (len(times) - 1)))]
        ttft = self.first_token()
        slots = self.about.get("total_slots")
        return replace(profile, timeout=max(4.0, round(p95 * 2.5, 1)),
                       concurrency=int(slots) if isinstance(slots, int) and slots > 0 else profile.concurrency,
                       measured={"model": self.model, "kind": self.kind, "schema": schema_seen, **enforce_seen,
                                 "p50_s": round(p50, 3), "p95_s": round(p95, 3),
                                 "first_token_s": None if ttft is None else round(ttft, 3),
                                 "probed": time.strftime("%Y-%m-%d")})
