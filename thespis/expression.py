"""Expression: code decides what an NPC does, the model voices it from its state pack, and code checks every word
before it counts.

The model makes no choices. It took the strongest drive pull in 86 of 86 decisions it was offered (paper-m1,
docs/cast-review.md), so code chooses every action and the model only words it: what the NPC says as it does what
code decided (`act`), a line in reply to something (`react`), or the narrator's telling (`narrate`).

The state pack is the only thing the model sees: persona, goal, drives and trust, the five strongest beliefs and
the last five events the NPC knows, who is here, what just happened and, for an action, what the NPC is doing.
Whether a belief is true is never included. Beliefs and events appear under short references in pack order (b1, b2,
... e1, e2, ...), which the model cites and the Mind maps back to belief and ledger ids. Each call's JSON schema
lists exactly the references its pack holds, so a provider that constrains its output to it (structured outputs)
can't cite anything else. Schemas differ only in how many beliefs and events a pack shows; measured on Azure, a
schema the provider hadn't seen cost no more than one it had (docs/cast-review.md).

The validator rejects a reply, and the NPC falls back to its code line, when any of these fail:
  - the line is a non-empty string, no longer than the call type allows;
  - it cites at least one reference, and every one is in the state pack;
  - it names no character or place that is absent from the pack.
An action that states a claim (thespis.deception) always cites it: the Mind adds "said" if the model leaves it out,
since the action, which code chose, is what states it.

The validator checks form. A line with consequences (an accusation, testimony, a deal, a lie, the narrator: the
game marks its pack's `stakes`) also meets the claim check (thespis.claims.ClaimCheck), which checks meaning: what
the line claims, against what its speaker could know. A line that fails it falls back too.

A reply that passes, the claim check if due, and moderation (thespis.moderation), is cached, keyed by the model, PROMPT_HASH (the
prompts and schemas), the call type and everything in the pack, so the same moment says the same thing again
without a model call. In replay mode the Mind only reads the cache: a miss falls back and the network is never
touched.

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

from thespis.deception import SAID
from thespis.gateway import ModelGateway, ModelReply
from thespis.ledger import Claim
from thespis.moderation import Moderator, NoModeration
from thespis.profiles import LINE_LIMITS

log = logging.getLogger("thespis.moderation")

LINE_MAX = LINE_LIMITS["act"]

_RULES = ("You know only what is listed below. Never state a fact that is not listed.\n"
          "In \"cites\", list the ids of the beliefs or events your line relies on. Always cite at least one: if none "
          "bears on what you say, cite the most recent event you know.\n")
_REPLY = 'Reply with JSON only: {{"cites": ["..."], "line": "..."}}'  # the evidence first, then the words
ACT_PROMPT = ("You are {name}. {persona}\n" + _RULES +
              "DOING is what you have decided to do. Say one line of dialogue to go with it, at most 25 words, in "
              "character: what you say, not a description of what you do. If DOING says something, your line says "
              "it, and cites \"said\".\n" + _REPLY)
REACT_PROMPT = ("You are {name}. {persona}\n" + _RULES +
                "Say one line of dialogue in reply to what just happened, at most 25 words, in character.\n" + _REPLY)
NARRATE_PROMPT = ("You are {name}. {persona}\n" + _RULES +
                  "Tell the player what happened, including what they couldn't see, in 2 or 3 short sentences: speak "
                  "to the player as \"you\", in the past tense, mentioning only the events listed.\n" + _REPLY)
PROMPTS = {"act": ACT_PROMPT, "react": REACT_PROMPT, "narrate": NARRATE_PROMPT}
LIMITS = dict(LINE_LIMITS)  # characters per line, by call type


def schema_for(refs: list[str]) -> dict:
    """A reply's JSON schema: cites from `refs`, then the line. In the subset strict structured outputs accept, which
    has no minItems or maxLength, so the validator still checks that it cites something and how long the line is."""
    return {"type": "object", "additionalProperties": False, "required": ["cites", "line"],
            "properties": {"cites": {"type": "array", "items": {"type": "string", "enum": refs}},
                           "line": {"type": "string"}}}


# Part of every cache key (#18): any change to the prompts, the schemas' shape or the limits gives new keys.
PROMPT_HASH = hashlib.sha256(json.dumps({"prompts": PROMPTS, "schema": schema_for(["<ref>"]), "limits": LIMITS},
                                        sort_keys=True).encode("utf-8")).hexdigest()[:12]


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
    beliefs: list[dict]  # {"id", "claim", "conf", "from"}, strongest first
    events: list[dict]  # {"id", "what"}, oldest first
    action: dict | None = None  # what code decided the NPC does: {"id", "does"}, and "asserts" if it states a claim
    names: set[str] = field(default_factory=set)  # every character and place the pack mentions, as game ids
    setting: str = ""  # where the NPC is and the lie of the land, as the game describes it
    untrusted: list[str] = field(default_factory=list)  # text a player wrote that the pack carries, for moderation
    stakes: bool = False  # a line with consequences, so it meets the claim check; not shown to the model
    asserted: Claim | None = None  # the claim its action states, typed, for the claim check; not shown either

    @property
    def asserts(self) -> bool:
        return bool(self.action and "asserts" in self.action)

    @property
    def refs(self) -> dict[str, str]:
        """Each reference the model may cite, mapped to the belief or ledger id it stands for."""
        out = {f"b{i}": b["id"] for i, b in enumerate(self.beliefs, 1)}
        out |= {f"e{i}": e["id"] for i, e in enumerate(self.events, 1)}
        if self.asserts:
            out[SAID] = SAID
        return out

    @property
    def ids(self) -> set[str]:
        """The belief and ledger ids the pack holds, and "said" if its action states a claim."""
        return set(self.refs.values())

    def payload(self) -> dict:
        data = {"you": self.name, "goal": self.goal, "setting": self.setting, "situation": self.situation,
                "here": self.here, "drives": self.drives, "trust": self.trust_in,
                "beliefs": [{**b, "id": f"b{i}"} for i, b in enumerate(self.beliefs, 1)],
                "events": [{**e, "id": f"e{i}"} for i, e in enumerate(self.events, 1)]}
        if self.action:
            data["DOING"] = {"does": self.action["does"]}
            if self.asserts:
                data["DOING"]["says"] = self.action["asserts"]["claim"]
        return data

    def messages(self, kind: str) -> list[dict]:
        return [{"role": "system", "content": PROMPTS[kind].format(name=self.name, persona=self.persona)},
                {"role": "user", "content": json.dumps(self.payload(), ensure_ascii=False)}]

    def schema(self) -> dict:
        """The reply's JSON schema: it may cite exactly the references this pack holds."""
        return schema_for(list(self.refs))

    def cache_key(self, model: str, kind: str, checked: bool = False) -> str:
        """sha256 of the model, the prompts' hash, the call type and everything the model is shown, canonically. A
        line that met the claim check is kept under its own key, so turning the check on never serves an unchecked
        line from the cache."""
        key = {"model": model, "prompts": PROMPT_HASH, "call": kind, "name": self.name, "persona": self.persona,
               "pack": self.payload()}
        if checked:
            key["checked"] = True
        canonical = json.dumps(key, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Utterance:
    action: str | None
    line: str | None
    cites: list[str]  # belief and ledger ids, and "said" for the claim an action states
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
        """Why a model reply (citing the pack's references) can't be used, or None if it passes."""
        line = data.get("line")
        if not isinstance(line, str) or not line.strip():
            return "no line"
        limit = LIMITS.get(kind, LINE_MAX)
        if len(line) > limit:
            return f"line is {len(line)} characters, over {limit}"
        cites = data.get("cites")
        if not isinstance(cites, list) or not cites or not all(isinstance(c, str) for c in cites):
            return "no cites"
        unknown = [c for c in cites if c not in pack.refs]
        if unknown:
            return f"cites {', '.join(unknown)}, not in its state pack"
        absent = self.named(line) - pack.names
        if absent:
            return f"names {', '.join(sorted(absent))}, absent from its state pack"
        return None


Observer = Callable[[str, StatePack, ModelReply | None, Utterance], None]


class Checker(Protocol):
    """Checks what lines mean before anyone hears them (thespis.claims.ClaimCheck)."""

    def wants(self, pack: StatePack) -> bool:
        """Should this pack's line be checked?"""
        ...

    def problems(self, items: list[tuple[StatePack, str]]) -> list[str | None]:
        """Why each line can't be heard, or None; one model call each."""
        ...


class Mind:
    """Asks the model when there is one, and keeps only replies that pass the validator and the moderator.

    With a cache it looks there first, under each configured model in turn, and stores every reply it accepts. With
    `replay` on it never calls the model: a cache miss falls back. With a `budget`, it makes at most that many model
    calls and falls back once they're spent; cache hits are free. `asked` counts the calls it made.

    An `observer`, if given, sees every line the Mind settles while the model is on: the call type, the state pack,
    the model's reply if it made a call (None for a cache hit or a line it never asked for), and what was used.
    Rehearsal measures the model through it. A `checker` checks the meaning of the lines it wants (the ones with
    stakes) once the validator passes them; each check is a model call, counted in `asked` and against the budget.
    """

    def __init__(self, gateway: ModelGateway | None, validator: Validator, cache: ReplyCache | None = None,
                 replay: bool = False, budget: int | None = None, moderator: Moderator | None = None,
                 observer: Observer | None = None, checker: Checker | None = None):
        self.gateway = gateway if gateway is not None and getattr(gateway, "providers", None) else None
        self.validator = validator
        self.cache = cache
        self.replay = replay
        self.budget = budget
        self.moderator = moderator or NoModeration()
        self.observer = observer
        self.checker = checker
        self.asked = 0
        self.models = tuple(getattr(self.gateway, "models", ())) if self.gateway else ()

    @property
    def active(self) -> bool:
        return self.gateway is not None

    def act(self, pack: StatePack, fallback: Utterance) -> Utterance:
        """The NPC's line as it does what code decided (`fallback.action`, which the pack's action describes)."""
        return self._speak("act", [(pack, fallback)])[0]

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
        calls = [(kind, items[i][0].messages(kind), items[i][0].schema()) for i in missing]
        self.asked += len(calls)
        answers = [gateway.complete(*calls[0])] if len(calls) == 1 else gateway.complete_many(calls)
        for i, reply in zip(missing, answers):
            replies[i] = reply
            spoken[i] = self._accept(reply, *items[i], kind)
        self._check(items, missing, spoken)
        self._keep(kind, items, list(zip(missing, answers)), spoken)
        return spoken

    def _check(self, items: list[tuple[StatePack, Utterance]], answered: list[int], spoken: list) -> None:
        """The claim check on the lines that want it, once the validator has passed them."""
        if self.checker is None:
            return
        due = [i for i in answered if spoken[i].source == "llm" and self.checker.wants(items[i][0])]
        if self.budget is not None:
            allowed = max(0, self.budget - self.asked)
            for i in due[allowed:]:
                spoken[i] = _fell_back(items[i][1], "model call cap reached: no claim check")
            due = due[:allowed]
        if not due:
            return
        self.asked += len(due)
        for i, problem in zip(due, self.checker.problems([(items[i][0], spoken[i].line) for i in due])):
            if problem:
                log.info("claim check refused a line", extra={"npc": items[i][0].npc, "why": problem})
                spoken[i] = _fell_back(items[i][1], f"model reply rejected: claim check ({problem})")

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
                self.cache.put_reply(self._key(items[i][0], reply.model, kind), kind, reply.data, reply.provider)

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
            hit = self.cache.get_reply(self._key(pack, model, kind))
            if hit and not self.validator.problem(hit[0], pack, kind):  # one the validator now rejects is a miss
                return _spoken(hit[0], pack, fallback, "cache", hit[1])
        return None

    def _key(self, pack: StatePack, model: str, kind: str) -> str:
        return pack.cache_key(model, kind, checked=self.checker is not None and self.checker.wants(pack))

    def _accept(self, reply, pack: StatePack, fallback: Utterance, kind: str) -> Utterance:
        if reply is None:
            return _fell_back(fallback, "model unavailable")
        problem = self.validator.problem(reply.data, pack, kind)
        if problem:
            return _fell_back(fallback, f"model reply rejected: {problem}")
        return _spoken(reply.data, pack, fallback, "llm", reply.provider)  # _keep caches it, once moderated


def _spoken(data: dict, pack: StatePack, fallback: Utterance, source: str, provider: str) -> Utterance:
    """A reply the validator passed, its references mapped to ids. The action is always code's."""
    refs = pack.refs
    cites = [refs[c] for c in dict.fromkeys(data["cites"])]
    if pack.asserts and SAID not in cites:
        cites.append(SAID)
    return Utterance(fallback.action, data["line"].strip(), cites, source, provider)


def _fell_back(fallback: Utterance, why: str) -> Utterance:
    return Utterance(fallback.action, fallback.line, fallback.cites, "fallback", why)
