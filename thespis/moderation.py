"""Moderation: a check on what a player writes before any model reads it, and on what a model writes before any
player hears it. The Mind runs it (thespis.expression); the host chooses the moderator.

  - Blocklist: words and phrases a game rules out, matched whole and checked offline.
  - ContentSafety: Azure AI Content Safety's text analysis. A text is flagged when any category's severity (0, 2, 4
    or 6) reaches its threshold. It fails closed: if the service errs or times out, the text counts as flagged, and
    the NPC falls back to its code line, which is always available.
  - Layered: several at once; the first to flag a text decides.

Every moderator also has a `local()` part, the layers that need no network. Cache hits and replay use only that, so
REPLAY=1 never touches the network; the full check ran when the reply was first accepted.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from collections import OrderedDict
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

import httpx

log = logging.getLogger("thespis.moderation")

API_VERSION = "2024-09-01"
CATEGORIES = ("Hate", "SelfHarm", "Sexual", "Violence")
# Medium severity and up, except violence, where a duel or a threat at swordpoint is the game: only high.
THRESHOLDS = {"Hate": 4, "SelfHarm": 4, "Sexual": 4, "Violence": 6}
MAX_TEXT = 10_000  # characters per request, the service's limit; no line or persona comes near it
UNAVAILABLE = "moderation unavailable"


@dataclass(frozen=True)
class Verdict:
    flagged: bool
    why: str = ""  # which rule or category flagged it; never the text itself


PASS = Verdict(False)


class Moderator(Protocol):
    def check(self, texts: list[str]) -> list[Verdict]:
        """One verdict per text, in order."""
        ...

    def local(self) -> Moderator:
        """The part of this moderator that needs no network."""
        ...


class NoModeration:
    def check(self, texts: list[str]) -> list[Verdict]:
        return [PASS for _ in texts]

    def local(self) -> Moderator:
        return self

    def __str__(self) -> str:
        return "none"


class Blocklist:
    def __init__(self, terms: Iterable[str]):
        self.terms = sorted({t.strip().lower() for t in terms if t.strip()}, key=len, reverse=True)
        self._pattern = re.compile(r"\b(" + "|".join(re.escape(t) for t in self.terms) + r")\b", re.IGNORECASE) \
            if self.terms else None

    def check(self, texts: list[str]) -> list[Verdict]:
        return [Verdict(True, "blocklist") if self._pattern and self._pattern.search(t) else PASS for t in texts]

    def local(self) -> Moderator:
        return self

    def __str__(self) -> str:
        return f"a blocklist of {len(self.terms)} terms"


class ContentSafety:
    def __init__(self, endpoint: str, key: str, thresholds: Mapping[str, int] | None = None, *, timeout: float = 2.0,
                 transport: httpx.BaseTransport | None = None, memo: int = 4096):
        self.url = f"{endpoint.rstrip('/')}/contentsafety/text:analyze?api-version={API_VERSION}"
        self._key = key
        self.thresholds = {**THRESHOLDS, **(thresholds or {})}
        self._client = httpx.Client(timeout=timeout, transport=transport)
        self._memo: OrderedDict[str, Verdict] = OrderedDict()  # verdicts by the text's hash, latest last
        self._memo_size = memo
        self._lock = threading.Lock()

    def check(self, texts: list[str]) -> list[Verdict]:
        if len(texts) <= 1:
            return [self._one(t) for t in texts]
        with ThreadPoolExecutor(max_workers=min(4, len(texts))) as pool:
            return list(pool.map(self._one, texts))

    def local(self) -> Moderator:
        return NoModeration()

    def close(self) -> None:
        self._client.close()

    def __str__(self) -> str:
        return "Azure AI Content Safety (" + ", ".join(f"{c} {self.thresholds[c]}" for c in CATEGORIES) + ")"

    def _one(self, text: str) -> Verdict:
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        with self._lock:
            if key in self._memo:
                self._memo.move_to_end(key)
                return self._memo[key]
        verdict = self._ask(text)
        if verdict.why != UNAVAILABLE:  # an outage is not a verdict: ask again next time
            with self._lock:
                self._memo[key] = verdict
                while len(self._memo) > self._memo_size:
                    self._memo.popitem(last=False)
        return verdict

    def _ask(self, text: str) -> Verdict:
        try:
            r = self._client.post(self.url, headers={"Ocp-Apim-Subscription-Key": self._key},
                                  json={"text": text[:MAX_TEXT], "categories": list(CATEGORIES)})
            if r.status_code != 200:
                log.warning("content safety answered HTTP %d", r.status_code, extra={"status": r.status_code})
                return Verdict(True, UNAVAILABLE)
            over = [f"{a['category']} {a['severity']}" for a in r.json()["categoriesAnalysis"]
                    if a.get("severity", 0) >= self.thresholds.get(a["category"], 99)]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            log.warning("content safety failed: %s", type(e).__name__, extra={"error": type(e).__name__})
            return Verdict(True, UNAVAILABLE)
        return Verdict(True, ", ".join(over)) if over else PASS


class Layered:
    def __init__(self, *layers: Moderator | None):
        self.layers = [m for m in layers if m is not None and not isinstance(m, NoModeration)]

    def check(self, texts: list[str]) -> list[Verdict]:
        out = [PASS] * len(texts)
        pending = list(range(len(texts)))
        for layer in self.layers:  # cheap, offline layers first, as the host orders them
            if not pending:
                break
            for i, verdict in zip(pending, layer.check([texts[i] for i in pending])):
                out[i] = verdict
            pending = [i for i in pending if not out[i].flagged]
        return out

    def local(self) -> Moderator:
        return Layered(*(m.local() for m in self.layers))

    def __str__(self) -> str:
        return " and ".join(str(m) for m in self.layers) or "none"


def content_safety_from_env(env: Mapping[str, str] | None = None) -> ContentSafety | None:
    """CONTENT_SAFETY_ENDPOINT and CONTENT_SAFETY_KEY, with MODERATION_THRESHOLDS (JSON, by category) to override the
    defaults; None when either is unset."""
    env = os.environ if env is None else env
    endpoint, key = (env.get(f"CONTENT_SAFETY_{k}", "").strip() for k in ("ENDPOINT", "KEY"))
    if not (endpoint and key):
        return None
    thresholds = env.get("MODERATION_THRESHOLDS", "").strip()
    return ContentSafety(endpoint, key, json.loads(thresholds) if thresholds else None)
