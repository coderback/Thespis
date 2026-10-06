"""Expression: the model voices an NPC from its state pack, and code checks every word before it counts.

The state pack is the only thing the model sees: persona, goal, drives and trust, the five strongest beliefs and
the last five events the NPC knows (each with its id), who is here, what just happened and, for a decision, the
allowed actions. Whether a belief is true is never included.

The validator rejects a reply, and the NPC falls back to its code line, when any of these fail:
  - for a decision, the action is one of the allowed ids;
  - the line is a non-empty string of at most 160 characters;
  - it cites at least one id, and every cited id is in the state pack;
  - it names no character or place that is absent from the pack;
  - for a decision whose action asserts a claim (thespis.deception), it cites that claim.

A reply that passes, and passes moderation (thespis.moderation), is cached, keyed by the model, the prompt version,
the call type and everything in the pack, so the same moment on the same route says the same thing again without a
model call. In replay mode the Mind only reads the cache: a miss falls back and the network is never touched.

Moderation runs both ways. Text a player wrote that the pack carries (`untrusted`) is checked before any model reads
it, and a flagged pack gets no model call. A model's line is checked after the validator passes it and before it is
cached or heard. Cache hits get only the moderator's offline part.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from thespis.gateway import ModelGateway, ModelReply
from thespis.moderation import Moderator, NoModeration

log = logging.getLogger("thespis.moderation")

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
NARRATE_PROMPT = ("You are {name}. {persona}\n" + _RULES +
                  "Tell the player what happened, including what they couldn't see, in 2 or 3 short sentences: speak "
                  "to the player as \"you\", in the past tense, mentioning only the events listed.\n"
                  'Reply with JSON only: {{"line": "...", "cites": ["..."]}}')
PROMPTS = {"decide": DECIDE_PROMPT, "react": REACT_PROMPT, "narrate": NARRATE_PROMPT}
LIMITS = {"decide": LINE_MAX, "react": LINE_MAX, "narrate": 400}  # characters per line, by call type


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
    untrusted: list[str] = field(default_factory=list)  # text a player wrote that the pack carries, for moderation

    @property
    def ids(self) -> set[str]:
        asserted = {a["asserts"]["id"] for a in self.allowed if "asserts" in a}
        return {b["id"] for b in self.beliefs} | {e["id"] for e in self.events} | asserted

    def payload(self) -> dict:
        data = {"you": self.name, "goal": self.goal, "setting": self.setting, "situation": self.situation,
                "here": self.here,
                "drives": self.drives, "trust": self.trust_in, "beliefs": self.beliefs, "events": self.events}
        if self.allowed:
            data["ALLOWED"] = self.allowed
        return data

    def messages(self, kind: str) -> list[dict]:
        prompt = PROMPTS[kind]
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
        limit = LIMITS.get(kind, LINE_MAX)
        if len(line) > limit:
            return f"line is {len(line)} characters, over {limit}"
        cites = data.get("cites")
        if not isinstance(cites, list) or not cites or not all(isinstance(c, str) for c in cites):
            return "no cites"
        unknown = [c for c in cites if c not in pack.ids]
        if unknown:
            return f"cites {', '.join(unknown)}, not in its state pack"
        if kind == "decide":
            chosen = next(a for a in pack.allowed if a["id"] == data["action"])
            said = chosen["asserts"]["id"] if "asserts" in chosen else None
            if said is not None and said not in cites:
                return f"states something without citing {said!r}, the claim its action asserts"
            other = {a["asserts"]["id"] for a in pack.allowed if "asserts" in a} - {said}
            if other & set(cites):
                return f"cites {', '.join(sorted(other & set(cites)))}, a claim its action doesn't state"
        absent = self.named(line) - pack.names
        if absent:
            return f"names {', '.join(sorted(absent))}, absent from its state pack"
        return None


Observer = Callable[[str, StatePack, ModelReply | None, Utterance], None]


class Mind:
    """Asks the model when there is one, and keeps only replies that pass the validator and the moderator.

    With a cache it looks there first, under each configured model in turn, and stores every reply it accepts. With
    `replay` on it never calls the model: a cache miss falls back. With a `budget`, it makes at most that many model
    calls and falls back once they're spent; cache hits are free. `asked` counts the calls it made.

    An `observer`, if given, sees every line the Mind settles while the model is on: the call type, the state pack,
    the model's reply if it made a call (None for a cache hit or a line it never asked for), and what was used.
    Rehearsal measures the model through it.
    """

    def __init__(self, gateway: ModelGateway | None, validator: Validator, cache: ReplyCache | None = None,
                 replay: bool = False, budget: int | None = None, moderator: Moderator | None = None,
                 observer: Observer | None = None):
        self.gateway = gateway if gateway is not None and getattr(gateway, "providers", None) else None
        self.validator = validator
        self.cache = cache
        self.replay = replay
        self.budget = budget
        self.moderator = moderator or NoModeration()
        self.observer = observer
        self.asked = 0
        self.models = tuple(getattr(self.gateway, "models", ())) if self.gateway else ()

    @property
    def active(self) -> bool:
        return self.gateway is not None

    def decide(self, pack: StatePack, fallback: Utterance) -> Utterance:
        return self._speak("decide", [(pack, fallback)])[0]

    def narrate(self, pack: StatePack, fallback: Utterance) -> Utterance:
        """The narrator's telling of the events in the pack: 2 or 3 sentences that cite them."""
        return self._speak("narrate", [(pack, fallback)])[0]

    def react_many(self, items: list[tuple[StatePack, Utterance]]) -> list[Utterance]:
        """Several reply lines at once: the calls the cache can't answer run in parallel."""
        return self._speak("react", items)

    def _speak(self, kind: str, items: list[tuple[StatePack, Utterance]]) -> list[Utterance]:
        if self.gateway is None:
            return [fallback for _, fallback in items]
        replies: dict[int, ModelReply | None] = {}
        spoken = self._settle(kind, items, replies)
        if self.observer is not None:
            for i, (pack, _) in enumerate(items):
                self.observer(kind, pack, replies.get(i), spoken[i])
        return spoken

    def _settle(self, kind: str, items: list[tuple[StatePack, Utterance]],
                replies: dict[int, ModelReply | None]) -> list[Utterance]:
        """Every item's line, from the cache, the model or the fallback. `replies` gets each model call's reply."""
        gateway = self.gateway
        assert gateway is not None
        spoken: list = [self._cached(pack, kind, fallback) for pack, fallback in items]
        self._moderate_hits(items, spoken)
        missing = [i for i, u in enumerate(spoken) if u is None]
        if self.replay:
            for i in missing:
                spoken[i] = _fell_back(items[i][1], "replay: not in the cache")
            return spoken
        missing = self._screen(items, missing, spoken)
        if self.budget is not None:
            allowed = max(0, self.budget - self.asked)
            for i in missing[allowed:]:
                spoken[i] = _fell_back(items[i][1], "model call cap reached")
            missing = missing[:allowed]
        if not missing:
            return spoken
        calls = [(kind, items[i][0].messages(kind)) for i in missing]
        self.asked += len(calls)
        answers = [gateway.complete(*calls[0])] if len(calls) == 1 else gateway.complete_many(calls)
        for i, reply in zip(missing, answers):
            replies[i] = reply
            spoken[i] = self._accept(reply, *items[i], kind)
        self._keep(kind, items, list(zip(missing, answers)), spoken)
        return spoken

    def _screen(self, items: list[tuple[StatePack, Utterance]], missing: list[int], spoken: list) -> list[int]:
        """Moderation in: a pack carrying player text the moderator flags falls back without a model call."""
        asking = [i for i in missing if items[i][0].untrusted]
        verdicts = iter(self.moderator.check([t for i in asking for t in items[i][0].untrusted]))
        for i in asking:
            flagged = [v for v in [next(verdicts) for _ in items[i][0].untrusted] if v.flagged]
            if flagged:
                log.info("player text flagged", extra={"stage": "in", "npc": items[i][0].npc, "why": flagged[0].why})
                spoken[i] = _fell_back(items[i][1], f"player text flagged: {flagged[0].why}")
        return [i for i in missing if spoken[i] is None]

    def _keep(self, kind: str, items: list[tuple[StatePack, Utterance]],
              answered: list[tuple[int, ModelReply | None]], spoken: list) -> None:
        """Moderation out: the lines that passed the validator, checked before anyone hears them. Only the ones that
        pass are cached."""
        passed = [(i, reply) for i, reply in answered if reply is not None and spoken[i].source == "llm"]
        verdicts = self.moderator.check([spoken[i].line for i, _ in passed])
        for (i, reply), verdict in zip(passed, verdicts):
            if verdict.flagged:
                log.info("model line flagged", extra={"stage": "out", "npc": items[i][0].npc, "why": verdict.why})
                spoken[i] = _fell_back(items[i][1], f"model reply rejected: moderation ({verdict.why})")
            elif self.cache is not None:
                self.cache.put_reply(items[i][0].cache_key(reply.model, kind), kind, reply.data, reply.provider)

    def _moderate_hits(self, items: list[tuple[StatePack, Utterance]], spoken: list) -> None:
        """Cached lines passed the full check when they were stored; here only the offline part runs."""
        hits = [i for i, u in enumerate(spoken) if u is not None]
        for i, verdict in zip(hits, self.moderator.local().check([spoken[i].line for i in hits])):
            if verdict.flagged:
                log.info("cached line flagged", extra={"stage": "cache", "npc": items[i][0].npc, "why": verdict.why})
                spoken[i] = _fell_back(items[i][1], f"cached reply rejected: moderation ({verdict.why})")

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
        return _spoken(reply.data, kind, fallback, "llm", reply.provider)  # _keep caches it, once moderated


def _spoken(data: dict, kind: str, fallback: Utterance, source: str, provider: str) -> Utterance:
    action = data.get("action") if kind == "decide" else fallback.action
    return Utterance(action, data["line"].strip(), list(dict.fromkeys(data["cites"])), source, provider)


def _fell_back(fallback: Utterance, why: str) -> Utterance:
    return Utterance(fallback.action, fallback.line, fallback.cites, "fallback", why)
