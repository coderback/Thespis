"""Recall by meaning: what an NPC remembers when it speaks, chosen for the moment rather than by confidence alone.

The usual pack shows an NPC's five surest beliefs and the last five events it knows (thespis.retriever, perception).
A game that declares `[memory] recall = "meaning"` gets them chosen instead by how well each bears on the moment:

    score = meaning x cosine(situation, memory) + recency x 0.5^(ticks ago / half_life)
            + salience x the claim's weight + confidence x how sure the NPC is

**Filtered first.** The candidates are only what the NPC knows: its own beliefs, active ones, and the events
perception says it took part in, learned of or saw. So nothing it never knew can be recalled, however close in
meaning. Within those, the scores rank, and the pack still shows events oldest first.

**Deterministic and cached.** Texts are embedded once each (`CachedEmbedder`), and the same texts always embed the
same, so a moment recalls the same memories every time and its pack, and its cache key, are stable. Ties break by id.

**Without an embedder** (none configured, or the call fails) it recalls as the usual pack does, unchanged. Any
OpenAI-compatible /embeddings endpoint serves (EMBED_BASE_URL, EMBED_MODEL, EMBED_API_KEY): the local runtime's
BGE small (`thespis models serve bge-small`), Ollama, or a cloud provider.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import threading
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from thespis.beliefs import Belief
from thespis.ledger import Claim, Event
from thespis.perception import Sees, known
from thespis.world import World

log = logging.getLogger("thespis.recall")

CACHE = 20_000  # embeddings kept in memory, by text
TIMEOUT = 5.0


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """A vector for each text, in order. Raises if it can't."""
        ...


class HttpEmbedder:
    """An OpenAI-compatible /embeddings endpoint."""

    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = TIMEOUT,
                 transport: httpx.BaseTransport | None = None):
        self.url = base_url.rstrip("/") + "/embeddings"
        self.model, self.timeout = model, timeout
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(transport=transport)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        r = self._client.post(self.url, json={"model": self.model, "input": list(texts)}, headers=self.headers,
                              timeout=self.timeout)
        r.raise_for_status()
        rows = sorted(r.json()["data"], key=lambda d: d["index"])
        return [list(map(float, d["embedding"])) for d in rows]


class CachedEmbedder:
    """Each distinct text embedded once; the most recently used CACHE of them kept."""

    def __init__(self, inner: Embedder, size: int = CACHE):
        self.inner, self.size = inner, size
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        keys = [self._key(t) for t in texts]
        with self._lock:
            missing = list(dict.fromkeys(t for t, k in zip(texts, keys) if k not in self._cache))
        if missing:
            vectors = self.inner.embed(missing)
            with self._lock:
                for t, v in zip(missing, vectors):
                    self._cache[self._key(t)] = v
                while len(self._cache) > self.size:
                    self._cache.popitem(last=False)
        with self._lock:
            out = []
            for k in keys:
                self._cache.move_to_end(k)
                out.append(self._cache[k])
            return out


def embedder_from_env(env: Mapping[str, str] | None = None) -> CachedEmbedder | None:
    env = os.environ if env is None else env
    base, model = env.get("EMBED_BASE_URL", "").strip(), env.get("EMBED_MODEL", "").strip()
    if not (base and model):
        return None
    return CachedEmbedder(HttpEmbedder(base, model, env.get("EMBED_API_KEY", "").strip()))


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


@dataclass(frozen=True)
class Weights:
    """How much each part of a memory's score counts (`[memory]` in the game file)."""
    meaning: float = 1.0
    recency: float = 0.3
    half_life: float = 3.0  # ticks for recency to halve
    salience: float = 0.3
    confidence: float = 0.2
    salient: Mapping[str, float] = field(default_factory=dict)  # a claim's weight, by predicate (0 to 1)

    @classmethod
    def from_toml(cls, d: Mapping) -> Weights:
        fields = {k: float(d[k]) for k in ("meaning", "recency", "half_life", "salience", "confidence") if k in d}
        return cls(**fields, salient={k: float(v) for k, v in d.get("salient", {}).items()})


class MeaningRetriever:
    """Chooses an NPC's beliefs and events for a pack by how well each bears on the moment (the module's
    docstring). `text_of` puts a claim, and `sentence` an event, into the words that are embedded."""

    def __init__(self, embedder: Embedder, text_of: Callable[[Claim], str], sentence: Callable[[Event], str],
                 weights: Weights | None = None, k: int = 5, events: int = 5):
        self.embedder, self.text_of, self.sentence = embedder, text_of, sentence
        self.weights, self.k, self.n_events = weights or Weights(), k, events

    def recall(self, w: World, npc: str, situation: str, sees: Sees,
               hidden: frozenset[str] = frozenset()) -> tuple[list[Belief], list[Event]] | None:
        """The beliefs (best first) and events (oldest first) to show, or None to recall as usual."""
        beliefs = [b for b in w.beliefs.for_npc(npc) if b.active]  # filtered first: what the NPC holds
        events = known(w, npc, len(w.ledger), sees, hidden)  # and what it knows happened
        if not situation.strip() or not (beliefs or events):
            return None
        texts = [situation] + [self.text_of(b.claim) for b in beliefs] + [self.sentence(e) for e in events]
        try:
            vectors = self.embedder.embed(texts)
        except Exception as e:  # recall must never cost a line: fall back to the usual pack
            log.warning("recall by meaning unavailable (%s); recalling as usual", type(e).__name__)
            return None
        here, rest = vectors[0], vectors[1:]
        wt = self.weights

        def score(vector: list[float], phase: int, pred: str | None, conf: float) -> float:
            recency = 0.5 ** (max(0, w.phase - phase) / wt.half_life)
            return round(wt.meaning * cosine(here, vector) + wt.recency * recency
                         + wt.salience * wt.salient.get(pred or "", 0.0) + wt.confidence * conf, 6)

        scored_b = [(score(v, max(e.phase for e in b.evidence), b.claim.pred, b.conf), b.id, b)
                    for b, v in zip(beliefs, rest[:len(beliefs)])]
        scored_e = [(score(v, e.phase, e.claim.pred if e.claim else None, 1.0), e.id, e)
                    for e, v in zip(events, rest[len(beliefs):])]
        chosen_b = [b for _, _, b in sorted(scored_b, key=lambda x: (-x[0], x[1]))[:self.k]]
        chosen_e = sorted((e for _, _, e in sorted(scored_e, key=lambda x: (-x[0], x[1]))[:self.n_events]),
                          key=lambda e: e.id)
        return chosen_b, chosen_e
