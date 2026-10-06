"""The model gateway: the one way the core calls a language model.

Each call uses JSON mode, max_tokens 150 and temperature 0.6, with thinking switched off through provider-specific
`extra` fields. It has a 4-second timeout and no retries: if the primary provider fails it tries the backup, and if
that fails it returns None so the caller uses its code fallback. It never raises, so a model problem never reaches
the player.

Azure OpenAI and Azure AI Foundry work too: their hosts get the `api-key` header, and `api_version` adds the
`api-version` query older deployment URLs need. In `extra`, a null value removes that field from the request,
e.g. {"max_tokens": null, "max_completion_tokens": 300} for a model that refuses max_tokens.

A provider that answers 401, 402 or 403 (a dead key or no credit) is skipped for 10 minutes, and one that answers
429 for 30 seconds, so later calls go straight to the backup. A provider's own content filter (Azure's) refusing the
prompt or the reply counts as a failed call, logged as "content_filter", with no cooldown: the next call is a new
text. Every call is logged in `calls` for the harness, with
its latency and token usage; `total` counts every call ever made, so the harness can ask for just the new ones.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlparse

import httpx

log = logging.getLogger("thespis.gateway")

TIMEOUT = 4.0  # the whole call's budget. httpx times each phase separately, so it is split:
CONNECT_TIMEOUT = 1.0  # 1 s to connect, and the rest to send the request and read the reply
MAX_TOKENS = 150
TEMPERATURE = 0.6
MAX_CONCURRENT = 4  # model calls in flight at once, across every session
COOLDOWN = {401: 600.0, 402: 600.0, 403: 600.0, 429: 30.0}  # seconds to skip a provider after these answers


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    api_key: str = field(repr=False)
    model: str
    extra: dict = field(default_factory=dict)  # merged into the request body, e.g. {"enable_thinking": false}
    api_version: str = ""  # Azure's api-version query, for deployment-style URLs

    @property
    def azure(self) -> bool:
        host = urlparse(self.base_url).hostname or ""
        return host.endswith((".azure.com", ".azure-api.net"))

    def headers(self) -> dict:
        # Azure wants the key as api-key; as a Bearer token it would be read as an Entra login and refused.
        return {"api-key": self.api_key} if self.azure else {"Authorization": f"Bearer {self.api_key}"}

    def url(self) -> str:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        return f"{url}?api-version={self.api_version}" if self.api_version else url

    def body(self, messages: list[dict]) -> dict:
        body = {"model": self.model, "messages": messages, "max_tokens": MAX_TOKENS, "temperature": TEMPERATURE,
                "response_format": {"type": "json_object"}, **self.extra}
        return {k: v for k, v in body.items() if v is not None}  # null in extra removes a field


@dataclass(frozen=True)
class ModelReply:
    data: dict  # the model's JSON reply, already parsed
    provider: str
    model: str
    latency: float  # seconds


@dataclass(frozen=True)
class CallRecord:
    call_type: str
    provider: str
    ok: bool
    latency: float
    error: str | None = None
    prompt_tokens: int | None = None  # from the reply's usage, when the provider reports it
    completion_tokens: int | None = None


class ModelGateway(Protocol):
    models: tuple[str, ...]  # the configured models, primary first: what a cached reply is keyed under

    def complete(self, call_type: str, messages: list[dict]) -> ModelReply | None:
        """Return the model's parsed JSON reply, or None to make the caller use its fallback."""
        ...

    def complete_many(self, calls: list[tuple[str, list[dict]]]) -> list[ModelReply | None]:
        """Several independent calls at once, e.g. different NPCs' decisions in one tick."""
        ...


class NoModel:
    """The gateway when no provider is configured: every call falls back."""

    providers: tuple = ()
    models: tuple = ()
    calls: deque = deque(maxlen=0)
    total: int = 0

    def complete(self, call_type: str, messages: list[dict]) -> ModelReply | None:
        return None

    def complete_many(self, calls: list[tuple[str, list[dict]]]) -> list[ModelReply | None]:
        return [None for _ in calls]

    def close(self) -> None:
        pass


def parse_json(content: str) -> dict:
    """The reply as a JSON object. Tolerates a markdown fence, which some models add even in JSON mode."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("reply is not a JSON object")
    return data


class OpenAICompatGateway:
    def __init__(self, providers: list[Provider], *, timeout: float = TIMEOUT,
                 transport: httpx.BaseTransport | None = None, clock: Callable[[], float] = time.monotonic):
        self.providers = list(providers)
        self.calls: deque[CallRecord] = deque(maxlen=1000)
        self.total = 0  # calls ever made; `calls` keeps only the latest 1000
        self._client = httpx.Client(timeout=httpx.Timeout(timeout - CONNECT_TIMEOUT, connect=CONNECT_TIMEOUT),
                                    transport=transport)
        self._clock = clock
        self._skip_until: dict[str, float] = {}
        self._lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(MAX_CONCURRENT)

    @property
    def models(self) -> tuple[str, ...]:
        return tuple(p.model for p in self.providers)

    def complete(self, call_type: str, messages: list[dict]) -> ModelReply | None:
        for provider in self.providers:
            with self._lock:
                skipped = self._clock() < self._skip_until.get(provider.name, 0.0)
            if skipped:
                continue
            reply = self._call(provider, call_type, messages)
            if reply is not None:
                return reply
        return None

    def complete_many(self, calls: list[tuple[str, list[dict]]]) -> list[ModelReply | None]:
        if not calls:
            return []
        with ThreadPoolExecutor(max_workers=min(MAX_CONCURRENT, len(calls))) as pool:
            return list(pool.map(lambda call: self.complete(*call), calls))

    def close(self) -> None:
        self._client.close()

    def _call(self, p: Provider, call_type: str, messages: list[dict]) -> ModelReply | None:
        started = time.perf_counter()
        reply, error, usage = None, None, {}
        try:
            with self._slots:
                r = self._client.post(p.url(), json=p.body(messages), headers=p.headers())
            if r.status_code == 200:
                body = r.json()
                usage = body.get("usage") or {}
                choice = body["choices"][0]
                content = choice["message"]["content"]
                if choice.get("finish_reason") == "content_filter":
                    error = "content_filter: reply"
                elif not isinstance(content, str):
                    error = "no content in the reply"
                else:
                    reply = ModelReply(parse_json(content), p.name, p.model, time.perf_counter() - started)
            else:
                error = "content_filter: prompt" if _filtered(r) else f"HTTP {r.status_code}"
                if r.status_code in COOLDOWN:
                    with self._lock:
                        self._skip_until[p.name] = self._clock() + COOLDOWN[r.status_code]
        except httpx.TimeoutException:
            error = "timeout"
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as e:
            error = f"{type(e).__name__}: {e}"[:200]
        record = CallRecord(call_type, p.name, reply is not None, time.perf_counter() - started, error,
                            usage.get("prompt_tokens"), usage.get("completion_tokens"))
        with self._lock:
            self.calls.append(record)
            self.total += 1
        log.info("model call: %s %s", call_type, "ok" if reply else error,
                 extra={"call_type": call_type, "provider": p.name, "ok": reply is not None,
                        "latency_ms": round(record.latency * 1000), "prompt_tokens": record.prompt_tokens,
                        "completion_tokens": record.completion_tokens, "error": error})
        return reply


def _filtered(r: httpx.Response) -> bool:
    """Did the provider's content filter refuse the prompt? Azure answers 400 with the error code "content_filter"."""
    if r.status_code != 400:
        return False
    try:
        return r.json()["error"]["code"] == "content_filter"
    except (ValueError, KeyError, TypeError):
        return False


def _provider(env: Mapping[str, str], prefix: str) -> Provider | None:
    base, key, model = (env.get(f"{prefix}{k}", "").strip() for k in ("BASE_URL", "API_KEY", "MODEL"))
    if not (base and key and model):
        return None
    extra = env.get(f"{prefix}EXTRA", "").strip()
    return Provider(name=f"{urlparse(base).hostname or base}/{model}", base_url=base, api_key=key, model=model,
                    extra=json.loads(extra) if extra else {}, api_version=env.get(f"{prefix}API_VERSION", "").strip())


def gateway_from_env(env: Mapping[str, str] | None = None) -> OpenAICompatGateway | NoModel:
    """The primary (LLM_*) and backup (LLM_BACKUP_*) providers from the environment, or NoModel if neither is set."""
    env = os.environ if env is None else env
    providers = [p for p in (_provider(env, "LLM_"), _provider(env, "LLM_BACKUP_")) if p]
    return OpenAICompatGateway(providers) if providers else NoModel()
