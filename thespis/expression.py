"""Expression: the model voices an NPC from its state pack, and code checks every word before it counts.

The state pack is the only thing the model sees: persona, goal, drives and trust, the five strongest beliefs and
the last five events the NPC knows (each with its id), who is here, what just happened and, for a decision, the
allowed actions. Whether a belief is true is never included.

The validator rejects a reply, and the NPC falls back to its code line, when any of these fail:
  - for a decision, the action is one of the allowed ids;
  - the line is a non-empty string of at most 160 characters;
  - it cites at least one id, and every cited id is in the state pack;
  - it names no character or place that is absent from the pack.

A reply that passes is cached, keyed by the model, the prompt version, the call type and everything in the pack, so
the same moment on the same route says the same thing again without a model call. In replay mode the Mind only
reads the cache: a miss falls back and the network is never touched.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Protocol

from thespis.gateway import ModelGateway

PROMPT_VERSION = 3  # part of #18's cache key: bump it whenever the prompts below change
LINE_MAX = 160

_RULES = ("You know only what is listed below. Never state a fact that is not listed.\n"
          "In \"cites\", list the ids of the beliefs or events your line relies on. Always cite at least one: if none "
          "bears on what you say, cite the most recent event you know.\n")
DECIDE_PROMPT = ("You are {name}. {persona}\n" + _RULES +
                 "Pick exactly one action id from ALLOWED. Each action's \"pull\" is how strongly your drives push you "
                 "towards it: follow the strongest pull unless your persona clearly says otherwise.\n"
                 "Write one line of dialogue, at most 25 words, in character.\n"
                 'Reply with JSON only: {{"action": "...", "line": "...", "cites": ["..."]}}')
REACT_PROMPT = ("You are {name}. {persona}\n" + _RULES +
                "Say one line of dialogue in reply to what just happened, at most 25 words, in character.\n"
                'Reply with JSON only: {{"line": "...", "cites": ["..."]}}')


@dataclass
class StatePack:
    npc: str
    name: str
    persona: str
    goal: str
    situation: str  # what just happened, from the NPC's point of view
    here: list[str]  # who shares its stop
    drives: dict
    trust_in: dict
    beliefs: list[dict]  # {"id", "claim", "conf", "from"}
    events: list[dict]  # {"id", "what"}
    allowed: list[dict] = field(default_factory=list)  # {"id", "does", "pull"}; empty for a reply with no action
    names: set[str] = field(default_factory=set)  # every character and place the pack mentions, as game ids
    setting: str = ""  # where the NPC is and the lie of the land, as the game describes it

    @property
    def ids(self) -> set[str]:
        return {b["id"] for b in self.beliefs} | {e["id"] for e in self.events}

    def payload(self) -> dict:
        data = {"you": self.name, "goal": self.goal, "setting": self.setting, "situation": self.situation,
                "here": self.here,
                "drives": self.drives, "trust": self.trust_in, "beliefs": self.beliefs, "events": self.events}
        if self.allowed:
            data["ALLOWED"] = self.allowed
        return data

    def messages(self, kind: str) -> list[dict]:
        prompt = DECIDE_PROMPT if kind == "decide" else REACT_PROMPT
        return [{"role": "system", "content": prompt.format(name=self.name, persona=self.persona)},
                {"role": "user", "content": json.dumps(self.payload(), ensure_ascii=False)}]

    def cache_key(self, model: str, kind: str) -> str:
        """sha256 of the model, the prompt version, the call type and everything the model is shown, canonically."""
        canonical = json.dumps({"model": model, "prompt_version": PROMPT_VERSION, "call": kind, "name": self.name,
                                "persona": self.persona, "pack": self.payload()},
                               sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Utterance:
    action: str | None
    line: str | None
    cites: list[str]
    source: str  # "llm", "cache" or "fallback"
    note: str = ""  # why the fallback was used, or which model spoke


class ReplyCache(Protocol):
    def get_reply(self, key: str) -> tuple[dict, str] | None:
        """The cached reply's JSON and the provider that gave it, or None."""
        ...

    def put_reply(self, key: str, call_type: str, data: dict, provider: str) -> None:
        """Keep a reply that passed the validator. The first one stored for a key is never replaced."""
        ...


class Validator:
    def __init__(self, vocabulary: dict[str, str]):
        """`vocabulary` maps every way of naming a character or place (lower case) to its game id."""
        self.vocabulary = vocabulary
        terms = sorted(vocabulary, key=len, reverse=True)
        self._pattern = re.compile(r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b", re.IGNORECASE) \
            if terms else None

    def named(self, line: str) -> set[str]:
        """The game ids of every character or place a line names."""
        if not self._pattern:
            return set()
        return {self.vocabulary[m.group(1).lower()] for m in self._pattern.finditer(line)}

    def problem(self, data: dict, pack: StatePack, kind: str) -> str | None:
        """Why a model reply can't be used, or None if it passes."""
        if kind == "decide" and data.get("action") not in {a["id"] for a in pack.allowed}:
            return f"action {data.get('action')!r} is not allowed"
        line = data.get("line")
        if not isinstance(line, str) or not line.strip():
            return "no line"
        if len(line) > LINE_MAX:
            return f"line is {len(line)} characters, over {LINE_MAX}"
        cites = data.get("cites")
        if not isinstance(cites, list) or not cites or not all(isinstance(c, str) for c in cites):
            return "no cites"
        unknown = [c for c in cites if c not in pack.ids]
        if unknown:
            return f"cites {', '.join(unknown)}, not in its state pack"
        absent = self.named(line) - pack.names
        if absent:
            return f"names {', '.join(sorted(absent))}, absent from its state pack"
        return None


class Mind:
    """Asks the model when there is one, and keeps only replies that pass the validator.

    With a cache it looks there first, under each configured model in turn, and stores every reply it accepts. With
    `replay` on it never calls the model: a cache miss falls back. With a `budget`, it makes at most that many model
    calls and falls back once they're spent; cache hits are free. `asked` counts the calls it made.
    """

    def __init__(self, gateway: ModelGateway | None, validator: Validator, cache: ReplyCache | None = None,
                 replay: bool = False, budget: int | None = None):
        self.gateway = gateway if gateway is not None and getattr(gateway, "providers", None) else None
        self.validator = validator
        self.cache = cache
        self.replay = replay
        self.budget = budget
        self.asked = 0
        self.models = tuple(getattr(self.gateway, "models", ())) if self.gateway else ()

    @property
    def active(self) -> bool:
        return self.gateway is not None

    def decide(self, pack: StatePack, fallback: Utterance) -> Utterance:
        return self._speak("decide", [(pack, fallback)])[0]

    def react_many(self, items: list[tuple[StatePack, Utterance]]) -> list[Utterance]:
        """Several reply lines at once: the calls the cache can't answer run in parallel."""
        return self._speak("react", items)

    def _speak(self, kind: str, items: list[tuple[StatePack, Utterance]]) -> list[Utterance]:
        if not self.active:
            return [fallback for _, fallback in items]
        spoken = [self._cached(pack, kind, fallback) for pack, fallback in items]
        missing = [i for i, u in enumerate(spoken) if u is None]
        if self.replay:
            for i in missing:
                spoken[i] = _fell_back(items[i][1], "replay: not in the cache")
            return spoken
        if self.budget is not None:
            allowed = max(0, self.budget - self.asked)
            for i in missing[allowed:]:
                spoken[i] = _fell_back(items[i][1], "model call cap reached")
            missing = missing[:allowed]
        if not missing:
            return spoken
        calls = [(kind, items[i][0].messages(kind)) for i in missing]
        self.asked += len(calls)
        replies = [self.gateway.complete(*calls[0])] if len(calls) == 1 else self.gateway.complete_many(calls)
        for i, reply in zip(missing, replies):
            spoken[i] = self._accept(reply, *items[i], kind)
        return spoken

    def _cached(self, pack: StatePack, kind: str, fallback: Utterance) -> Utterance | None:
        if self.cache is None:
            return None
        for model in self.models:
            hit = self.cache.get_reply(pack.cache_key(model, kind))
            if hit and not self.validator.problem(hit[0], pack, kind):  # one the validator now rejects is a miss
                return _spoken(hit[0], kind, fallback, "cache", hit[1])
        return None

    def _accept(self, reply, pack: StatePack, fallback: Utterance, kind: str) -> Utterance:
        if reply is None:
            return _fell_back(fallback, "model unavailable")
        problem = self.validator.problem(reply.data, pack, kind)
        if problem:
            return _fell_back(fallback, f"model reply rejected: {problem}")
        if self.cache is not None:
            self.cache.put_reply(pack.cache_key(reply.model, kind), kind, reply.data, reply.provider)
        return _spoken(reply.data, kind, fallback, "llm", reply.provider)


def _spoken(data: dict, kind: str, fallback: Utterance, source: str, provider: str) -> Utterance:
    action = data.get("action") if kind == "decide" else fallback.action
    return Utterance(action, data["line"].strip(), list(dict.fromkeys(data["cites"])), source, provider)


def _fell_back(fallback: Utterance, why: str) -> Utterance:
    return Utterance(fallback.action, fallback.line, fallback.cites, "fallback", why)
