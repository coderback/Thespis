"""Sessions: one playthrough of a game whose world an engine owns, through the calls every runtime shares.

The engine owns the world; Thespis owns the minds. The engine reports what happened and who saw it (`observe`), where
people are and how they feel when its own rules change that (`update`), and asks what an NPC does (`decide`) or says
(`react`), and for the story so far (`narrate`). `tick` runs the minds' own time: scheduled walks, gossip, and drives
settling back towards rest. `snapshot` and `restore` carry the minds in and out of the engine's own save files.

A game is one TOML file (examples/tavern/game.toml): its cast, places, choices (thespis.considerations), lines and
words. Everything in it is checked when it loads. What a game declares there, it gets; nothing more:
  - `[players.<id>]`: more players than the one, each with a name and a place, or the engine `join`s them. Each is
    an actor, a target and a witness like any character; NPCs hold beliefs about each by id; `narrate(to=...)` tells
    one of them only what they saw or took part in.
  - `[npc.<id>.feels]`: how an NPC's drives move when it comes to believe something was done to it (it is the
    claim's `b`: `insulted = { grudge = 4 }`, scaled by how sure it is), so the engine reports only the event.
  - `[npc.<id>.decay]`: drives that fade towards a baseline with a half-life, keeping a share of their peak.
  - `[[tie]]` and `[gossip] along`: gossip travels along ties wherever the two are, each report discounted by the
    listener's trust in the teller and by the kind of tie, so a story weakens as it passes from mouth to mouth.
A statement that denies a claim (`neg`) is evidence against the claim for everyone who hears it, as far as each
trusts the one denying it.

Every call that speaks returns its line at once. With no model, or when the caller waits, the line is final.
Otherwise it is the template line, `provisional`, and the model's follows: `line(id)` returns it `final` once the
model has answered (its words, or the template's when its reply failed a check), or `withdrawn` if the session closed
first. A line needs something to cite, as everywhere in Thespis: an NPC that knows nothing yet says nothing.

The library calls these methods; the HTTP API (thespis.http) calls the same ones.
"""

from __future__ import annotations

import contextvars
import hashlib
import math
import threading
import time
import tomllib
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from functools import cached_property, partial
from pathlib import Path

from thespis.beliefs import credence
from thespis.brain import Brain, UtilityBrain
from thespis.cast import Cast
from thespis.claims import ClaimVocabulary, EventPred, Facts
from thespis.considerations import DefinitionError, declared
from thespis.deception import SAID, log_statement
from thespis.decisions import DECIDE, REACT, Decision
from thespis.expression import Mind, StatePack, Utterance, Validator
from thespis.gateway import ModelGateway
from thespis.ledger import Claim, Event
from thespis.minds import NPC
from thespis.perception import at_the_scene, reported
from thespis.tick import Tick, gossip, run_tick, spread, walks
from thespis.voice import View, Voice
from thespis.world import World

SNAPSHOT_VERSION = 1
PROVISIONAL, FINAL, WITHDRAWN = "provisional", "final", "withdrawn"
DRIVES, TRUST = (0, 10), (-5, 5)
WORKERS = 4  # model calls one session has in flight at once


class Unknown(LookupError):
    """A call named an NPC, moment or line the game or session doesn't have."""


class _Fill(dict):
    """Template values; a placeholder nothing fills stays as written instead of failing mid-game."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _clamp(v: int, bounds: tuple[int, int]) -> int:
    return max(bounds[0], min(bounds[1], v))


def _numbers(world: dict) -> dict:
    """A saved world with its numbers as Thespis wrote them: whole numbers are ints, except evidence confidences."""
    def whole(x):
        if isinstance(x, float) and x.is_integer():
            return int(x)
        if isinstance(x, dict):
            return {k: whole(v) for k, v in x.items()}
        return [whole(v) for v in x] if isinstance(x, list) else x

    world = whole(world)
    for b in world.get("beliefs", []):
        for e in b.get("evidence", []):
            e["conf"] = float(e["conf"])
    return world


class Game:
    """A game definition, compiled and checked: load once, play many sessions."""

    def __init__(self, cast: Cast):
        self.cast = cast
        d = cast.data
        self.id = str(d.get("game", {}).get("id") or cast.path.stem)
        self.name = str(d.get("game", {}).get("name", self.id))
        self.places: dict[str, str] = dict(d.get("places", {}))
        self.players: dict[str, dict] = {k: dict(v) for k, v in d.get("players", {}).items()}
        self.choices = declared(d)
        self._check()
        self.ties: dict[str, list[tuple[str, str]]] = {}  # npc -> [(the other, kind)], in the order declared
        for t in d.get("tie", []):
            a, b = t["between"]
            self.ties.setdefault(a, []).append((b, t["kind"]))
            self.ties.setdefault(b, []).append((a, t["kind"]))
        vocabulary = {**{k.lower(): k for k in self.places}, **{v.lower(): k for k, v in self.places.items()}}
        for npc, t in d["npc"].items():
            vocabulary |= {npc.lower(): npc, str(t["name"]).lower(): npc,
                           **{str(a).lower(): npc for a in t.get("aliases", [])}}
        vocabulary |= {str(p["name"]).lower(): pid for pid, p in self.players.items()}
        stakes = {c.do.partition(":")[0] for cs in self.choices.values() for c in cs.choices if c.asserts}
        self.voice = Voice(cast=cast, validator=Validator(vocabulary), claim_text=self.claim_text,
                           sentence=self.sentence, who=self.who, setting=self.setting, describe=self.describe,
                           places=tuple(self.places), stakes=stakes)

    @classmethod
    def load(cls, path: str | Path) -> Game:
        return cls(Cast(Path(path)))

    @classmethod
    def parse(cls, text: str, name: str = "game") -> Game:
        """A game from its TOML text; `name` is its id unless [game] gives one."""
        try:
            return cls(Cast(Path(f"{name}.toml"), text))
        except tomllib.TOMLDecodeError as e:
            raise DefinitionError(f"not TOML: {e}") from e

    @cached_property
    def digest(self) -> str:
        """A fingerprint of the definition, saved in snapshots so a restore can tell the game changed under it."""
        return hashlib.sha256(self.cast.source).hexdigest()[:16]

    def _check(self) -> None:
        d = self.cast.data
        npcs = d.get("npc")
        if not isinstance(npcs, dict) or not npcs:
            raise DefinitionError("a game needs at least one [npc.<id>]")
        for npc, t in npcs.items():
            for key in ("name", "persona", "goal", "start"):
                if not isinstance(t.get(key), str):
                    raise DefinitionError(f"npc.{npc}: needs {key} = \"...\"")
            for place in (t["start"], *t.get("walk", [])):
                if self.places and place not in self.places:
                    raise DefinitionError(f"npc.{npc}: {place!r} is not in [places]")
        for who in d.get("gossip", {}).get("gossips", []):
            if who not in npcs:
                raise DefinitionError(f"gossip.gossips: {who!r} is not an npc")
        start = d.get("player", {}).get("start")
        if self.places and start is not None and start not in self.places:
            raise DefinitionError(f"player.start: {start!r} is not in [places]")
        for pid, p in d.get("players", {}).items():
            if pid in npcs or pid == "player" or not isinstance(p, dict) or not isinstance(p.get("name"), str):
                raise DefinitionError(f"players.{pid}: needs name = \"...\", and an id no NPC has")
            if self.places and p.get("start") is not None and p["start"] not in self.places:
                raise DefinitionError(f"players.{pid}.start: {p['start']!r} is not in [places]")
        along = d.get("gossip", {}).get("along", {})
        for i, t in enumerate(d.get("tie", [])):
            pair = t.get("between")
            if not (isinstance(pair, list) and len(pair) == 2 and all(x in npcs for x in pair) and pair[0] != pair[1]):
                raise DefinitionError(f"tie[{i}]: between = [two different npcs]")
            if t.get("kind") not in along:
                raise DefinitionError(f"tie[{i}]: kind {t.get('kind')!r} is not in [gossip] along")
        for kind, carry in along.items():
            if not isinstance(carry, int | float) or not 0 <= carry <= 1:
                raise DefinitionError(f"gossip.along.{kind}: how much carries, 0 to 1")
        for npc, t in npcs.items():
            for pred, moves in t.get("feels", {}).items():
                if not isinstance(moves, dict) or not all(isinstance(v, int) for v in moves.values()):
                    raise DefinitionError(f"npc.{npc}.feels.{pred}: {{drive = steps, ...}}, whole numbers")
            for drive, c in t.get("decay", {}).items():
                if not isinstance(c, dict) or not isinstance(c.get("half_life"), int | float) or c["half_life"] <= 0:
                    raise DefinitionError(f"npc.{npc}.decay.{drive}: needs half_life > 0 (ticks)")
                if not 0 <= c.get("keep", 0) <= 1:
                    raise DefinitionError(f"npc.{npc}.decay.{drive}: keep is a share of the peak, 0 to 1")

    # ------------------------------------------------------------ words, as the model reads them
    def who(self, x: str | None, names: Mapping[str, str] | None = None) -> str:
        """Who or where `x` is, in words. `names` are a session's players, by id."""
        if not x:
            return ""
        if names and x in names:
            return names[x]
        if x == "player":
            return "the player"
        if x in self.cast.data["npc"]:
            return self.cast.npc(x)["name"]
        if x in self.players:
            return self.players[x]["name"]
        return self.places.get(x, x)

    def claim_text(self, c: Claim, names: Mapping[str, str] | None = None) -> str:
        who = partial(self.who, names=names)
        template = self.cast.data.get("words", {}).get("claims", {}).get(c.pred)
        fmt = _Fill(a=who(c.a), b=who(c.b), place=who(c.place), at=c.at)
        text = template.format_map(fmt) if template else " ".join(
            x for x in (who(c.a), c.pred.replace("_", " "), who(c.b)) if x)
        return f"it is not true that {text}" if c.neg else text

    def sentence(self, e: Event, names: Mapping[str, str] | None = None) -> str:
        who = partial(self.who, names=names)
        template = self.cast.data.get("words", {}).get("events", {}).get(e.verb)
        fmt = _Fill(a=who(e.actor), t=who(e.target), where=who(e.loc), to=who(e.target),
                    claim=self.claim_text(e.claim, names) if e.claim else "", amount=e.amount)
        text = template.format_map(fmt) if template else " ".join(
            x for x in (fmt["a"], e.verb.replace("_", " "), fmt["t"]) if x) + "."
        return text[:1].upper() + text[1:]

    def setting(self, w: World, npc: str) -> str:
        here = f"You are at {self.who(w.npcs[npc].loc)}."
        setting = self.cast.data.get("game", {}).get("setting")
        return f"{setting} {here}" if setting else here

    def describe(self, w: World, npc: str, action: str, names: Mapping[str, str] | None = None) -> str:
        kind, _, arg = action.partition(":")
        template = self.cast.data.get("actions", {}).get(kind)
        return template.format_map(_Fill(who=self.who(arg, names))) if template else kind.replace("_", " ")

    def vocabulary(self) -> ClaimVocabulary:
        """What a claim extractor may say this game's lines assert (thespis.claims), from the game file: its
        `[claims] description` if it has one, else one built from `[words.claims]`, its NPCs and its places."""
        d = self.cast.data
        preds = dict(d.get("words", {}).get("claims", {}))
        npcs = list(d["npc"])
        if self.players:  # several players, by id: "you" is whichever of them is being spoken to
            people = (", ".join(f"{pid} ({p['name']})" for pid, p in self.players.items())
                      + " (players; \"you\" is whichever player is being spoken to, as the situation says)")
        else:
            people = "player (the one being spoken to, \"you\")"
        description = d.get("claims", {}).get("description") or "\n".join([
            "Predicates (a and b are ids):",
            *[f"- {p}(a, b): " + t.format(a="a", b="b") for p, t in preds.items()],
            "- went_to(a, place); at(a, place): a is at place now; told(a, b): a told b something",
            "- other: any other assertion about what happened, with b set to a short paraphrase",
            "Characters: " + people + ", " + ", ".join(npcs) + ". Places: " + ", ".join(self.places) + "."])
        aliases = {"you": "player", "the player": "player",
                   **{str(t["name"]).lower(): n for n, t in d["npc"].items()},
                   **{str(p["name"]).lower(): pid for pid, p in self.players.items()},
                   **{name.lower(): p for p, name in self.places.items()}}
        return ClaimVocabulary(game=self.id, description=description,
                               characters=("player", *self.players, *npcs),
                               places=tuple(self.places), ledger_preds=frozenset(preds),
                               event_preds={"went_to": EventPred(("move",), "target"),
                                            "told": EventPred(("tell", "gossip"), "target")},
                               place_preds=frozenset({"went_to", "at"}), aliases=aliases)

    def situation(self, key: str, fill: Mapping) -> str:
        template = self.cast.data.get("situations", {}).get(key)
        return template.format_map(_Fill(fill)) if template else ""


@dataclass
class Line:
    """What an NPC (or the narrator) says, as every runtime returns it."""
    id: str | None  # the decision it is recorded as ("d0007"), or the narration ("n0002"); None when silent
    npc: str
    text: str | None  # None: nothing to say
    cites: list[str] = field(default_factory=list)
    status: str = FINAL  # provisional, final or withdrawn
    source: str = "fallback"  # llm, cache or fallback
    action: str | None = None  # what it decided to do, for decide
    reason: str = ""
    event: str | None = None  # the statement its action logged, if it states a claim
    segments: list[dict] | None = None  # a told scene's, in order: {"speaker", "line", "cites"} (narrate)

    def to_json(self) -> dict:
        return asdict(self)


class Session:
    """One playthrough's minds: the world they live in, what each saw, and the lines still on their way."""

    def __init__(self, game: Game, world: World, witnesses: dict[str, list[str]] | None = None,
                 gateway: ModelGateway | None = None, mind: Mind | None = None, brain: Brain | None = None):
        self.game, self.world = game, world
        self.witnesses: dict[str, list[str]] = witnesses if witnesses is not None else {}
        self.voice = replace(game.voice, sees=reported(self.witnesses), who=self.who,
                             claim_text=lambda c: game.claim_text(c, self._names()),
                             sentence=self.sentence,
                             describe=lambda w, npc, action: game.describe(w, npc, action, self._names()))
        self.mind = mind or Mind(gateway, self.voice.validator)
        self.brain = brain or UtilityBrain()
        self._lines: dict[str, Line] = {}
        self._pending: dict[str, Future] = {}
        self._lock = threading.RLock()
        self._pool: ThreadPoolExecutor | None = None
        self.settled_at: dict[str, float] = {}  # when each line settled (time.monotonic), for measuring
        self.on_pack: Callable[[StatePack], None] | None = None  # sees each state pack as it's built (Rehearsal)
        self.on_settle: Callable[[Line], None] | None = None  # sees each provisional line once it settles (a store)

    @classmethod
    def new(cls, game: Game, seed: int = 0, **kw) -> Session:
        d = game.cast.data
        npcs = {i: NPC(i, t["start"], dict(t.get("drives", {})), dict(t.get("trust_in", {})))
                for i, t in d["npc"].items()}
        player = {"loc": d.get("player", {}).get("start", "")}
        players = {pid: {"name": p["name"], "loc": p.get("start", "")} for pid, p in game.players.items()}
        return cls(game, World(seed=seed, player=player, npcs=npcs, players=players), **kw)

    def join(self, player: str, name: str | None = None, at: str | None = None) -> dict:
        """A player joins (or is renamed, or moves): one more agent the NPCs can see, hear and hold beliefs about,
        by id. The one player every game has is "player"; this is for the rest."""
        with self._lock:
            w = self.world
            if player == "player" or player in w.npcs:
                raise DefinitionError(f"{player!r} is taken: a player's id must be new")
            p = w.players.setdefault(player, {"name": player, "loc": ""})
            if name is not None:
                p["name"] = name
            if at is not None:
                p["loc"] = at
            return {"id": player, **p}

    # ------------------------------------------------------------ the world, as the engine reports it
    def observe(self, verb: str, actor: str, target: str | None = None, at: str | None = None,
                claim: Claim | Mapping | None = None, witnesses: Sequence[str] = (), said: bool = False,
                true: bool | None = None, amount: int | None = None) -> Event:
        """Something happened. `witnesses` saw it; the actor and target took part. A claim it carries is believed:
        a deed (`said` false) by everyone who saw it, for certain; a statement (`said`) by everyone who heard it, as
        far as each trusts the speaker. Its truth, unless the engine says, is whether the ledger shows it happened."""
        with self._lock:
            w = self.world
            c = claim if isinstance(claim, Claim) or claim is None else Claim.from_json(dict(claim))
            unknown = [n for n in witnesses if n not in w.npcs and not w.is_player(n)]
            if unknown:
                raise Unknown(f"no npc or player {', '.join(unknown)}")
            where = at or self._where(actor)
            truth = true if true is not None else (w.ledger.happened(c) if said and c else True)
            e = w.ledger.append(w.phase, verb, actor, target, where, c, truth, amount)
            everyone = [n for n in dict.fromkeys(witnesses) if n not in (actor, target)]
            seen = [n for n in everyone if n in w.npcs]
            if everyone:
                self.witnesses[e.id] = everyone  # players too: what each saw is what they're told (narrate)
            if c is not None:
                if said:
                    for n in dict.fromkeys([target, *seen]):
                        if n in w.npcs and n != actor:
                            trust = w.npcs[n].trust_in.get(actor, 0)
                            self._believe(n, c, credence(trust), actor, e)
                else:
                    for n in seen:
                        self._believe(n, c, 1.0, "witnessed", e)
                    for n in dict.fromkeys([actor, target]):
                        if n in w.npcs:
                            self._believe(n, c, 1.0, "self", e)
            return e

    def update(self, npc: str, loc: str | None = None, drives: Mapping[str, int] | None = None,
               nudge: Mapping[str, int] | None = None, flags: Mapping | None = None,
               trust_in: Mapping[str, int] | None = None) -> dict:
        """The engine's rules changed an NPC: where it is, its drives (set, or `nudge`d by a step), its flags, its
        trust. Drives stay within 0 to 10 and trust within -5 to 5. "player" takes only `loc`."""
        with self._lock:
            if npc == "player":
                if loc is not None:
                    self.world.player["loc"] = loc
                return dict(self.world.player)
            if npc in self.world.players:
                if loc is not None:
                    self.world.players[npc]["loc"] = loc
                return {"id": npc, **self.world.players[npc]}
            n = self._npc(npc)
            if loc is not None:
                n.loc = loc
            for k, v in (drives or {}).items():
                self._drive(n, k, _clamp(int(v), DRIVES))
            for k, v in (nudge or {}).items():
                self._drive(n, k, _clamp(n.drives.get(k, 0) + int(v), DRIVES))
            for k, v in (trust_in or {}).items():
                n.trust_in[k] = _clamp(int(v), TRUST)
            for k, v in (flags or {}).items():
                if v is None:
                    n.flags.pop(k, None)
                else:
                    n.flags[k] = v
            return n.to_json()

    # ------------------------------------------------------------ the minds
    def decide(self, npc: str, moment: str, bindings: Mapping | None = None, situation: str | None = None,
               to: str | None = None, wait: bool = True) -> Line:
        """What `npc` does at `moment`, among the choices the game declares for it, and its line. The choice is
        recorded with its reason. An action that states a claim logs the statement, told `to` someone."""
        with self._lock:
            w, b = self.world, dict(bindings or {})
            self._npc(npc)
            cs = self.game.choices.get((npc, moment))
            if cs is None:
                raise Unknown(f"{npc} has no choices for {moment!r}")
            view = View(w.player["loc"])
            choices = cs.options(w, view, **b)
            if not choices:
                return Line(None, npc, None)
            choice = self.brain.choose(npc, choices)
            claim = cs.asserts(**b).get(choice)
            said = self._template(npc, choice.partition(":")[0], [SAID] if claim else [], b, choice)
            text, cites = said or (None, [])
            statement = None
            if claim is not None:
                statement, cites = log_statement(w, "tell", npc, to, w.npcs[npc].loc, claim, cites)
                self._overheard(statement)
                if to in w.npcs:
                    self._believe(to, claim, credence(w.npcs[to].trust_in.get(npc, 0)), npc, statement)
            situation = situation if situation is not None else self.game.situation(moment, b)
            pack = self._ask(self.voice.pack(w, npc, situation, choice, claim, view)) if self.mind.active else None
            d = w.decisions.record(DECIDE, npc, w.phase, moment, allowed=list(choices), chosen=choice, line=text,
                                   cites=cites, reason=f"{choice} scores {choices[choice]}", source="fallback",
                                   asserted=statement.id if statement else None)
            return self._speak("act", d, pack, Utterance(choice, text, cites, "fallback"), wait, statement)

    def react(self, npc: str, trigger: str, situation: str | None = None, cites: Sequence[str] = (),
              fill: Mapping | None = None, wait: bool = True) -> Line:
        """`npc`'s line in reply to `trigger`: its template line, voiced by the model if there is one. It cites
        `cites`, or the latest event it knows; with no template or nothing to cite it stays silent."""
        with self._lock:
            w = self.world
            self._npc(npc)
            said = self._template(npc, trigger, list(cites) or [self.voice.latest(w, npc)], dict(fill or {}))
            if said is None:
                return Line(None, npc, None)
            situation = situation if situation is not None else self.game.situation(trigger, fill or {})
            pack = self._ask(self.voice.pack(w, npc, situation, stakes=trigger in self.voice.stakes)) \
                if self.mind.active else None
            d = w.decisions.record(REACT, npc, w.phase, trigger, line=said[0], cites=said[1], reason=trigger,
                                   source="fallback")
            return self._speak("react", d, pack, Utterance(None, said[0], said[1], "fallback"), wait)

    def narrate(self, since: int = 0, wait: bool = True, to: str | None = None) -> Line:
        """The story since phase `since`, told by the narrator from the ledger, citing every event it tells. Told
        `to` one player, it tells only what they took part in or saw."""
        with self._lock:
            w = self.world
            if to is not None and not w.is_player(to):
                raise Unknown(f"no player {to!r}")
            events = [e for e in w.ledger.since(since) if to is None or self._player_knows(to, e)]
            if not events:
                return Line(None, "narrator", None)
            telling = " ".join(self.sentence(e) for e in events)
            w.counters["narrations"] = n = w.counters.get("narrations", 0) + 1
            reason = f"since phase {since}" + (f", to {to}" if to else "")
            structured = bool(self.game.cast.data.get("narrator", {}).get("structured"))
            segments = [{"speaker": "narrator", "line": self.sentence(e), "cites": [e.id]} for e in events] \
                if structured else None
            line = Line(f"n{n:04d}", "narrator", telling, [e.id for e in events], reason=reason, segments=segments)
            pack = None
            if self.mind.active and "narrator" in self.game.cast.data:
                setting = self.game.cast.data.get("game", {}).get("setting", "")
                pack = self.voice.narration(events, setting, lambda es: " ".join(self.sentence(e) for e in es),
                                            audience=self.who(to) if to and to != "player" else None,
                                            structured=structured)
            return self._voice(line, "tell" if structured else "narrate", pack,
                               Utterance(None, telling, line.cites, "fallback", segments=segments), wait)

    def tick(self, steps: int = 1) -> Tick:
        """The minds' own time, `steps` phases of it: scheduled walks, then gossip, then drives settling, then the
        next phase. Everyone at the scene of what it does sees it."""
        with self._lock:
            w, d = self.world, self.game.cast.data
            g = d.get("gossip")

            def walking(t: Tick) -> None:
                walks(w, t, lambda npc: d["npc"][npc].get("walk"))

            def hear(w: World, npc: str, c: Claim, conf: float, source: str, e: Event) -> None:
                self._believe(npc, c, conf, source, e)

            def grapevine(t: Tick) -> None:
                if g and g.get("along"):
                    tellers = g.get("gossips") or list(self.game.ties)
                    spread(w, tellers, self._listeners, g.get("about", ["player"]), g.get("priority", {}),
                           g.get("threshold", 0.5), lambda w, c: w.ledger.happened(c), hear,
                           lambda listener, teller: credence(w.npcs[listener].trust_in.get(teller, 0)))
                elif g:
                    gossip(w, g.get("gossips", []), g.get("about", ["player"]), g.get("priority", {}),
                           g.get("threshold", 0.5), g.get("decay", 0.8), lambda w, c: w.ledger.happened(c), hear)

            def settling(t: Tick) -> None:
                for npc, rest in ((n, d["npc"][n].get("settle", {})) for n in w.npcs):
                    drives = w.npcs[npc].drives
                    for k, r in rest.items():
                        v = drives.get(k, int(r))
                        drives[k] = v - 1 if v > r else v + 1 if v < r else v
                for npc in w.npcs:
                    self._decay(npc)

            def advance(t: Tick) -> None:
                w.phase += 1

            start = len(w.ledger)
            tick = run_tick(w, [step for _ in range(max(0, steps)) for step in (walking, grapevine, settling,
                                                                                advance)])
            for e in list(w.ledger)[start:]:
                self._overheard(e)
            return tick

    # ------------------------------------------------------------ lines on their way
    def line(self, line_id: str, wait: float = 0) -> Line:
        """A line by id, as it stands now. With `wait`, up to that many seconds for a provisional one to settle."""
        fut = self._pending.get(line_id)
        if fut is not None and wait > 0:
            try:
                fut.result(timeout=wait)
            except TimeoutError:
                pass
        with self._lock:
            if line_id not in self._lines:
                raise Unknown(f"no line {line_id!r}")
            return replace(self._lines[line_id])

    def pending(self, line_id: str) -> Future | None:
        """The model call a provisional line waits on, or None once it has settled: for a caller that waits on it
        its own way (the HTTP API, without holding a thread)."""
        return self._pending.get(line_id)

    def close(self) -> None:
        """Stop: every line still provisional is withdrawn, and its model call's answer is dropped."""
        with self._lock:
            for lid in list(self._pending):
                self._lines[lid].status = WITHDRAWN
            self._pending.clear()
        if self._pool:
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._pool = None

    # ------------------------------------------------------------ saves
    def snapshot(self) -> dict:
        """The minds, for the engine's save file. Lines still provisional are saved as their template words."""
        with self._lock:
            return {"thespis": SNAPSHOT_VERSION, "game": self.game.id, "digest": self.game.digest,
                    "world": self.world.to_json(), "witnesses": {k: list(v) for k, v in self.witnesses.items()}}

    @classmethod
    def restore(cls, game: Game, snapshot: Mapping, **kw) -> Session:
        """A session from a snapshot of this game. A snapshot from a newer Thespis, or of another game, is refused.
        One that went through an engine with a single number type (GDScript reads every JSON number as a float)
        restores the same."""
        if snapshot.get("thespis") != SNAPSHOT_VERSION:
            raise DefinitionError(f"snapshot version {snapshot.get('thespis')!r}; this Thespis reads "
                                  f"{SNAPSHOT_VERSION}")
        if snapshot.get("game") != game.id:
            raise DefinitionError(f"snapshot of {snapshot.get('game')!r}, not {game.id!r}")
        world = World.from_json(_numbers(dict(snapshot["world"])))
        return cls(game, world, {k: list(v) for k, v in dict(snapshot.get("witnesses", {})).items()}, **kw)

    def inspect(self, npc: str) -> dict:
        """One NPC's mind as it stands: its state and every belief, retracted ones included, with their evidence."""
        with self._lock:
            n = self._npc(npc)
            return {"npc": n.to_json(), "beliefs": [b.to_json() for b in self.world.beliefs.for_npc(npc)]}

    def sentence(self, e: Event) -> str:
        return self.game.sentence(e, self._names())

    def who(self, x: str | None) -> str:
        return self.game.who(x, self._names())

    def facts(self, npc: str) -> Facts:
        """What `npc` could know of this world, for checking what it says (thespis.claims)."""
        w = self.world
        return Facts(w, npc, lambda w, c: w.ledger.happened(c), lambda event_id: self.voice.knows(w, npc, event_id))

    # ------------------------------------------------------------ inside
    def _npc(self, npc: str) -> NPC:
        if npc not in self.world.npcs:
            raise Unknown(f"no npc {npc!r}")
        return self.world.npcs[npc]

    def _where(self, who: str) -> str:
        return self.world.where(who)

    def _names(self) -> dict[str, str]:
        return {pid: p["name"] for pid, p in self.world.players.items() if p.get("name")}

    def _overheard(self, e: Event) -> None:
        """Everyone at the scene of an event Thespis itself wrote saw it: NPCs, and the players standing there."""
        w = self.world
        if not e.loc:  # it happened nowhere anyone else stood: word passed between two people apart
            return
        seen = [n for n in w.npcs if n not in (e.actor, e.target) and at_the_scene(w, n, e)]
        seen += [p for p, v in w.players.items() if p not in (e.actor, e.target) and v.get("loc") in (e.loc, e.target)]
        if seen:
            self.witnesses[e.id] = seen

    def _player_knows(self, player: str, e: Event) -> bool:
        return player in (e.actor, e.target) or player in self.witnesses.get(e.id, ())

    def _believe(self, npc: str, c: Claim, conf: float, source: str, e: Event) -> None:
        """`npc` hears or sees `c`. A denial is also evidence against what it denies, as far as `conf`; and a claim
        that something was done to the NPC (it is the claim's `b`), newly believed, moves the drives its game
        declares it feels."""
        w = self.world
        belief, new = w.beliefs.add_evidence(npc, c, conf, source, e.id, w.phase)
        if c.neg:
            w.beliefs.add_evidence(npc, c.affirmed(), conf, source, e.id, w.phase, against=True)
            return
        feels = self.game.cast.data["npc"][npc].get("feels", {}).get(c.pred)
        if new and feels and c.b == npc and belief.active:  # done to it: `b` is whom a claim names
            n = w.npcs[npc]
            for drive, steps in feels.items():
                self._drive(n, drive, _clamp(n.drives.get(drive, 0) + math.floor(steps * belief.conf + 0.5), DRIVES))

    def _drive(self, n: NPC, drive: str, value: int) -> None:
        """Set a drive; one that decays (`[npc.<id>.decay]`) fades from this new peak, from now."""
        n.drives[drive] = value
        if drive in self.game.cast.data["npc"][n.id].get("decay", {}):
            n.flags.setdefault("decay", {})[drive] = [value, self.world.phase]

    def _decay(self, npc: str) -> None:
        """Each decaying drive, as it will stand next phase: the baseline `to` plus what's left of its last peak
        after the ticks since, halving every `half_life` ticks, but never less than `keep` of it."""
        w, n = self.world, self.world.npcs[npc]
        for drive, c in self.game.cast.data["npc"][npc].get("decay", {}).items():
            peak, since = n.flags.setdefault("decay", {}).setdefault(drive, [n.drives.get(drive, c.get("to", 0)),
                                                                             w.phase])
            left = max(0.5 ** ((w.phase + 1 - since) / c["half_life"]), c.get("keep", 0))
            n.drives[drive] = _clamp(math.floor(c.get("to", 0) + (peak - c.get("to", 0)) * left + 0.5), DRIVES)

    def _listeners(self, teller: str) -> list[tuple[str, float]]:
        """Whom `teller` passes gossip to, and how much of it carries: everyone tied to it, wherever they are, by
        the kind of tie; then anyone else standing with it, as a stranger's tale (`[gossip] in_person`)."""
        g, w = self.game.cast.data["gossip"], self.world
        out = [(other, float(g["along"][kind])) for other, kind in self.game.ties.get(teller, [])]
        tied = {o for o, _ in out}
        here = w.npcs[teller].loc
        out += [(n.id, float(g.get("in_person", 0.8))) for n in w.npcs_at(here) if n.id != teller and n.id not in tied]
        return out

    def _template(self, npc: str, key: str, cites: list[str | None], fill: dict,
                  action: str | None = None) -> tuple[str, list[str]] | None:
        """The NPC's template line for `key`, filled, and what it cites; None with no template or nothing to cite."""
        text, known = self.game.cast.template(npc, key), [c for c in cites if c]
        if text is None:
            return None
        if not any(c != SAID for c in known):
            latest = self.voice.latest(self.world, npc)
            known += [latest] if latest else []
        if not known:
            return None
        arg = action.partition(":")[2] if action else ""
        return text.format_map(_Fill({"who": self.who(arg), **fill})), list(dict.fromkeys(known))

    @staticmethod
    def _ask(pack: StatePack) -> StatePack | None:
        """The pack to voice, or None when it holds nothing to cite: every line must cite, so the model can't help."""
        return pack if pack.refs else None

    def _speak(self, kind: str, d: Decision, pack: StatePack | None, fallback: Utterance, wait: bool,
               statement: Event | None = None) -> Line:
        line = Line(d.id, d.npc, d.line, list(d.cites), action=d.chosen, reason=d.reason,
                    event=statement.id if statement else None)
        return self._voice(line, kind, pack, fallback, wait, d, statement)

    def _voice(self, line: Line, kind: str, pack: StatePack | None, fallback: Utterance, wait: bool,
               d: Decision | None = None, statement: Event | None = None) -> Line:
        """Settle the line now (no model, or the caller waits), or return it provisional and let the model follow."""
        assert line.id is not None
        self._lines[line.id] = line
        if pack is None:
            self.settled_at[line.id] = time.monotonic()
            return replace(line)
        if self.on_pack is not None:
            self.on_pack(pack)
        if wait:
            self._settle(line.id, self._call(kind, pack, fallback), d, statement)
            return replace(self._lines[line.id])
        line.status = PROVISIONAL
        if self._pool is None:
            self._pool = ThreadPoolExecutor(WORKERS, thread_name_prefix="thespis-line")
        lid = line.id

        def speak() -> None:
            # The line settles in the worker, before its future completes: whoever waits on the future (line(),
            # the HTTP long poll) then finds it settled, and close() never withdraws a line whose answer is in.
            try:
                u = self._call(kind, pack, fallback)
            except Exception:
                u = fallback
            self._settle(lid, u, d, statement)

        # The model call runs in the caller's context, so its trace span joins the request's (thespis.tracing).
        self._pending[lid] = self._pool.submit(contextvars.copy_context().run, speak)
        return replace(line)

    def _call(self, kind: str, pack: StatePack, fallback: Utterance) -> Utterance:
        if kind == "act":
            return self.mind.act(pack, fallback)
        if kind == "narrate":
            return self.mind.narrate(pack, fallback)
        if kind == "tell":
            return self.mind.tell(pack, fallback)
        return self.mind.react_many([(pack, fallback)])[0]

    def _settle(self, lid: str, u: Utterance, d: Decision | None, statement: Event | None) -> None:
        with self._lock:
            line = self._lines[lid]
            if line.status == WITHDRAWN:
                return
            self._pending.pop(lid, None)
            cites = [statement.id if c == SAID and statement else c for c in u.cites]
            line.text = u.line if u.line is not None else line.text  # the model's words, or the template's
            line.cites, line.source, line.status = cites, u.source, FINAL
            if u.segments is not None:  # a told scene: the speakers' words quoted and named in the flat text
                line.segments = u.segments
                line.text = " ".join(s["line"] if s["speaker"] == "narrator" else
                                     f"{self.who(s['speaker'])}: \"{s['line']}\"" for s in u.segments)
            self.settled_at[lid] = time.monotonic()
            if u.note:
                line.reason = f"{line.reason}; {u.note}"
            if d is not None:
                self.world.decisions.settle(d.id, line=line.text, cites=cites, reason=line.reason, source=u.source)
            settled = replace(line)
        if self.on_settle is not None:
            self.on_settle(settled)
