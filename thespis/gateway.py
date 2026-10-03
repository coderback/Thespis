"""The model gateway: the one way the core calls a language model.

Each call uses JSON mode, max_tokens 150 and temperature 0.6, with thinking switched off through provider-specific
`extra` fields. It has a 4-second timeout and no retries: if the primary provider fails it tries the backup, and if
that fails it returns None so the caller uses its code fallback. It never raises, so a model problem never reaches
the player.

A provider that answers 401, 402 or 403 (a dead key or no credit) is skipped for 10 minutes, and one that answers
429 for 30 seconds, so later calls go straight to the backup. Every call is logged in `calls` for the harness.
"""

from __future__ import annotations

import json
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


class ModelGateway(Protocol):
    def complete(self, call_type: str, messages: list[dict]) -> ModelReply | None:
        """Return the model's parsed JSON reply, or None to make the caller use its fallback."""
        ...

    def complete_many(self, calls: list[tuple[str, list[dict]]]) -> list[ModelReply | None]:
        """Several independent calls at once, e.g. different NPCs' decisions in one tick."""
        ...


class NoModel:
    """The gateway when no provider is configured: every call falls back."""

    providers: tuple = ()
    calls: deque = deque(maxlen=0)

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
        self._client = httpx.Client(timeout=httpx.Timeout(timeout - CONNECT_TIMEOUT, connect=CONNECT_TIMEOUT),
                                    transport=transport)
        self._clock = clock
        self._skip_until: dict[str, float] = {}
        self._lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(MAX_CONCURRENT)

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
        body = {"model": p.model, "messages": messages, "max_tokens": MAX_TOKENS, "temperature": TEMPERATURE,
                "response_format": {"type": "json_object"}, **p.extra}
        started = time.perf_counter()
        reply, error = None, None
        try:
            with self._slots:
                r = self._client.post(f"{p.base_url.rstrip('/')}/chat/completions", json=body,
                                      headers={"Authorization": f"Bearer {p.api_key}"})
            if r.status_code == 200:
                data = parse_json(r.json()["choices"][0]["message"]["content"])
                reply = ModelReply(data, p.name, p.model, time.perf_counter() - started)
            else:
                error = f"HTTP {r.status_code}"
                if r.status_code in COOLDOWN:
                    with self._lock:
                        self._skip_until[p.name] = self._clock() + COOLDOWN[r.status_code]
        except httpx.TimeoutException:
            error = "timeout"
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as e:
            error = f"{type(e).__name__}: {e}"[:200]
        self.calls.append(CallRecord(call_type, p.name, reply is not None, time.perf_counter() - started, error))
        return reply


def _provider(env: Mapping[str, str], prefix: str) -> Provider | None:
    base, key, model = (env.get(f"{prefix}{k}", "").strip() for k in ("BASE_URL", "API_KEY", "MODEL"))
    if not (base and key and model):
        return None
    extra = env.get(f"{prefix}EXTRA", "").strip()
    return Provider(name=f"{urlparse(base).hostname or base}/{model}", base_url=base, api_key=key, model=model,
                    extra=json.loads(extra) if extra else {})


def gateway_from_env(env: Mapping[str, str] | None = None) -> OpenAICompatGateway | NoModel:
    """The primary (LLM_*) and backup (LLM_BACKUP_*) providers from the environment, or NoModel if neither is set."""
    env = os.environ if env is None else env
    providers = [p for p in (_provider(env, "LLM_"), _provider(env, "LLM_BACKUP_")) if p]
    return OpenAICompatGateway(providers) if providers else NoModel()
