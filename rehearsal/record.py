"""Recording what the model says in a rehearsal, and replaying it with no network.

A live rehearsal wraps the real gateway in a RecordingGateway, which keeps every reply under a key made of the call
type and the exact messages sent. Replay answers each call from those recordings instead, so the same scenarios say
exactly what they said, refusals included, and anything that changes what the model is shown misses. The Recorder is
the Mind's observer: it keeps every model line with the world as it stood when the line was said, and notes any line
that cites what its pack didn't hold.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from thespis.deception import SAID
from thespis.expression import StatePack, Utterance
from thespis.gateway import Call, ModelGateway, ModelReply
from thespis.world import World

REJECTED = "model reply rejected: "


def call_key(call_type: str, messages: list[dict], schema: dict | None = None) -> str:
    canonical = json.dumps([call_type, messages, schema], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _reply_json(reply: ModelReply | None) -> dict | None:
    if reply is None:
        return None
    return {"data": reply.data, "provider": reply.provider, "model": reply.model, "latency": round(reply.latency, 3)}


class RecordingGateway:
    """Passes every call to the real gateway and keeps each reply, in the order given, under the call's key."""

    def __init__(self, inner: ModelGateway):
        self.inner = inner
        self.providers = getattr(inner, "providers", ())
        self.replies: dict[str, list[dict | None]] = {}

    @property
    def models(self) -> tuple[str, ...]:
        return self.inner.models

    def complete(self, call_type: str, messages: list[dict], schema: dict | None = None) -> ModelReply | None:
        reply = self.inner.complete(call_type, messages, schema)
        self.replies.setdefault(call_key(call_type, messages, schema), []).append(_reply_json(reply))
        return reply

    def complete_many(self, calls: Sequence[Call]) -> list[ModelReply | None]:
        replies = self.inner.complete_many(calls)
        for call, reply in zip(calls, replies):
            self.replies.setdefault(call_key(*call), []).append(_reply_json(reply))
        return replies

    def recordings(self, claim_check: str = "consequential") -> dict:
        return {"models": list(self.models), "claim_check": claim_check, "replies": dict(sorted(self.replies.items()))}


class ReplayGateway:
    """Answers each call from recordings, in the order they were made. A call that wasn't recorded is a miss: it
    gets no answer, so its NPC falls back, and the miss is kept for the report."""

    providers = ("replay",)

    def __init__(self, recordings: dict):
        self.models = tuple(recordings["models"])
        self.claim_check = recordings.get("claim_check", "off")  # how the recorded rehearsal checked claims
        self._queue = {key: list(replies) for key, replies in recordings["replies"].items()}
        self.misses: list[str] = []

    def complete(self, call_type: str, messages: list[dict], schema: dict | None = None) -> ModelReply | None:
        queue = self._queue.get(call_key(call_type, messages, schema))
        if not queue:
            self.misses.append(call_type)
            return None
        r = queue.pop(0)
        return None if r is None else ModelReply(r["data"], r["provider"], r["model"], r["latency"])

    def complete_many(self, calls: Sequence[Call]) -> list[ModelReply | None]:
        return [self.complete(*call) for call in calls]


class DictCache:
    """The host's reply cache, in memory: the first reply kept for a key stays."""

    def __init__(self):
        self._replies: dict[str, tuple[dict, str]] = {}

    def get_reply(self, key: str) -> tuple[dict, str] | None:
        return self._replies.get(key)

    def put_reply(self, key: str, call_type: str, data: dict, provider: str) -> None:
        self._replies.setdefault(key, (data, provider))


@dataclass
class Recorder:
    """The Mind's observer during a rehearsal. `world` gives the world being played (Stage.world)."""

    world: Callable[[], World | None]
    scenario: str = ""
    game: str = ""
    samples: list[dict] = field(default_factory=list)
    snapshots: dict[str, dict] = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)
    unanswered: int = 0  # model calls that got no answer, so their NPC fell back

    def __call__(self, kind: str, pack: StatePack, reply: ModelReply | None, used: Utterance) -> None:
        if used.source != "fallback":
            stray = set(used.cites) - pack.ids - {SAID}
            if stray:
                self.violations.append(f"{self.scenario}: {pack.npc} cites {sorted(stray)}, not in its pack")
        if reply is None:
            self.unanswered += used.note == "model unavailable"
            return
        self.samples.append({
            "scenario": self.scenario, "game": self.game, "kind": kind, "npc": pack.npc, "name": pack.name,
            "situation": pack.situation, "here": list(pack.here), "ids": sorted(pack.ids),
            "reply": reply.data, "provider": reply.provider, "latency": round(reply.latency, 3),
            "source": used.source, "note": used.note, "line": used.line, "cites": list(used.cites),
            "action": used.action, "asserting": pack.asserts, "stakes": pack.stakes,
            "snapshot": self._snapshot(),
        })

    def _snapshot(self) -> str | None:
        w = self.world()
        if w is None:
            return None
        body = w.to_json()
        sid = hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        self.snapshots.setdefault(sid, body)
        return sid


def refusal(note: str) -> str | None:
    """The validator's or moderator's reason, from a fallback's note, or None if the line wasn't refused."""
    return note.split(REJECTED, 1)[1] if REJECTED in note else None


def transcript(w: World, tellings: list[tuple[str, str]]) -> dict:
    """How a scenario went, for replay to hold it to: the outcome, a fingerprint of the ledger, every line with its
    source, every digest, and every refusal."""
    story = [[e.verb, e.actor, e.target, e.claim.to_json() if e.claim else None, e.truth] for e in w.ledger]
    return {
        "outcome": f"{w.status}@{w.ended_at}",
        "story": hashlib.sha256(json.dumps(story, sort_keys=True).encode("utf-8")).hexdigest()[:16],
        "lines": [[d.npc, d.trigger, d.chosen, d.source, d.line] for d in w.decisions if d.line],
        "tellings": [list(t) for t in tellings],
        "refused": [r for d in w.decisions if (r := refusal(d.reason))],
    }
