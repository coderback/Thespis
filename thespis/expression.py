"""Expression: the model voices an NPC from its state pack, and code checks every word before it counts.

The state pack is the only thing the model sees: persona, goal, drives and trust, the five strongest beliefs and
the last five events the NPC knows (each with its id), who is here, what just happened and, for a decision, the
allowed actions. Whether a belief is true is never included.

The validator rejects a reply, and the NPC falls back to its code line, when any of these fail:
  - for a decision, the action is one of the allowed ids;
  - the line is a non-empty string of at most 160 characters;
  - it cites at least one id, and every cited id is in the state pack;
  - it names no character or place that is absent from the pack.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from thespis.gateway import ModelGateway

PROMPT_VERSION = 1  # part of #18's cache key: bump it whenever the prompts below change
LINE_MAX = 160

_RULES = ("You know only what is listed below. Never state a fact that is not listed.\n"
          "In \"cites\", list the ids of the beliefs or events your line relies on.\n")
DECIDE_PROMPT = ("You are {name}. {persona}\n" + _RULES +
                 "Pick exactly one action id from ALLOWED. They are listed from what your drives favour most to least.\n"
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
    allowed: list[dict] = field(default_factory=list)  # {"id", "does"}; empty for a reply with no action
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


@dataclass(frozen=True)
class Utterance:
    action: str | None
    line: str | None
    cites: list[str]
    source: str  # "llm", "cache" or "fallback"
    note: str = ""  # why the fallback was used, or which model spoke


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
    """Asks the model when there is one, and keeps only replies that pass the validator."""

    def __init__(self, gateway: ModelGateway | None, validator: Validator):
        self.gateway = gateway if gateway is not None and getattr(gateway, "providers", None) else None
        self.validator = validator

    @property
    def active(self) -> bool:
        return self.gateway is not None

    def decide(self, pack: StatePack, fallback: Utterance) -> Utterance:
        if not self.active:
            return fallback
        return self._accept(self.gateway.complete("decide", pack.messages("decide")), pack, "decide", fallback)

    def react_many(self, items: list[tuple[StatePack, Utterance]]) -> list[Utterance]:
        """Several reply lines at once: the calls run in parallel."""
        if not self.active or not items:
            return [fallback for _, fallback in items]
        replies = self.gateway.complete_many([("react", pack.messages("react")) for pack, _ in items])
        return [self._accept(r, pack, "react", fallback) for r, (pack, fallback) in zip(replies, items)]

    def _accept(self, reply, pack: StatePack, kind: str, fallback: Utterance) -> Utterance:
        if reply is None:
            return Utterance(fallback.action, fallback.line, fallback.cites, "fallback", "model unavailable")
        problem = self.validator.problem(reply.data, pack, kind)
        if problem:
            return Utterance(fallback.action, fallback.line, fallback.cites, "fallback", f"model reply rejected: {problem}")
        action = reply.data.get("action") if kind == "decide" else fallback.action
        cites = list(dict.fromkeys(reply.data["cites"]))
        return Utterance(action, reply.data["line"].strip(), cites, "llm", reply.provider)
