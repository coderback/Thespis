"""Sessions: one playthrough of a game whose world an engine owns, through the calls every runtime shares.

The engine owns the world; Thespis owns the minds. The engine reports what happened and who saw it (`observe`), where
people are and how they feel when its own rules change that (`update`), and asks what an NPC does (`decide`) or says
(`react`), and for the story so far (`narrate`). `tick` runs the minds' own time: scheduled walks, gossip, and drives
settling back towards rest. `snapshot` and `restore` carry the minds in and out of the engine's own save files.

A game is one TOML file (examples/tavern/game.toml): its cast, places, choices (thespis.considerations), lines and
words. Everything in it is checked when it loads (thespis.schema). What a game declares there, it gets; nothing more:
  - `[players.<id>]`: more players than the one, each with a name and a place, or the engine `join`s them. Each is
    an actor, a target and a witness like any character; NPCs hold beliefs about each by id; `narrate(to=...)` tells
    one of them only what they saw or took part in.
  - `[npc.<id>.feels]`: how an NPC's drives move when it comes to believe something was done to it (it is the
    claim's `b`: `insulted = { grudge = 4 }`, scaled by how sure it is), so the engine reports only the event.
  - `[npc.<id>.decay]`: drives that fade towards a baseline with a half-life, keeping a share of their peak.
  - `[[tie]]` and `[gossip] along`: gossip travels along ties wherever the two are, each report discounted by the
    listener's trust in the teller and by the kind of tie, so a story weakens as it passes from mouth to mouth.
  - `[memory] recall = "meaning"`: what an NPC remembers when it speaks is chosen by how well it bears on the moment
    (thespis.recall), given an embedder; without one, as usual.
  - `[narrator] structured = true`: the narrator tells a scene, segments each its own or one speaker's.
  - `[kind.<id>]`: a kind of person, for a cast that grows in play. `add` makes someone of a kind an NPC, with its
    own name and place; `retire` takes someone out of the story (dead, or gone); `tie` and `untie` make and break
    the ties gossip travels along.
  - `[claims] one_actor`: deeds only one person can have done to another. Believing two culprits for one, an NPC
    keeps the story from the source it trusts more, and trusts whoever told it the other less. With `first_hand`,
    a teller who saw it themselves counts for that much more than one who only heard.
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
import re
import threading
import time
import tomllib
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from functools import cached_property, partial
from pathlib import Path
from typing import Any

from thespis.beliefs import FIRST_HAND, credence, origins, reconcile
from thespis.brain import Brain, UtilityBrain
from thespis.cast import Cast, LiveCast
from thespis.claims import ClaimVocabulary, EventPred, Facts
from thespis.considerations import Choices, DefinitionError, Keep, compile_keeps, declared, declared_kinds
from thespis.deception import SAID, log_statement
from thespis.decisions import DECIDE, REACT, Decision
from thespis.expression import Mind, StatePack, Utterance, Validator
from thespis.gateway import ModelGateway
from thespis.intents import (
    Arg,
    Bounds,
    ClaimDomain,
    Domain,
    Offer,
    Understander,
    Understood,
    Words,
    declared_intents,
    people,
)
from thespis.ledger import CAUGHT, SOMEONE, Claim, Event
from thespis.minds import NPC
from thespis.perception import at_the_scene, reported
from thespis.recall import Embedder, MeaningRetriever, Weights
from thespis.schema import CLAIM_KEYS, DRIVES, EVERYONE, TRUST, examine, near, refuse
from thespis.tick import Tick, gossip, run_tick, spread, tellings, walks
from thespis.voice import View, Voice
from thespis.world import World

SNAPSHOT_VERSION = 1
PROVISIONAL, FINAL, WITHDRAWN = "provisional", "final", "withdrawn"
ID = re.compile(r"[A-Za-z0-9_.-]+")  # an id made in play: it goes into action ids ("confront:<id>") and paths
RESERVED = ("player", "self", "narrator")
WORKERS = 4  # model calls one session has in flight at once


class Unknown(LookupError):
    """A call named an NPC, moment or line the game or session doesn't have."""


class _Fill(dict):
    """Template values; a placeholder nothing fills stays as written instead of failing mid-game."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _clamp(v: int, bounds: tuple[int, int]) -> int:
    return max(bounds[0], min(bounds[1], v))


def _other_actor(x: Claim, y: Claim) -> bool:
    """Two claims that the same thing was done to the same one, by different people: they can't both be true. That
    "someone" did it is no rival to a name: it's what a name tells more of."""
    return (x.pred, x.b, x.place, x.at) == (y.pred, y.b, y.place, y.at) and x.a != y.a and not (x.neg or y.neg) \
        and SOMEONE not in (x.a, y.a)


PLAIN = (str, int, bool, type(None))  # what a saved world holds that is never a number to put right


def _numbers(world: dict) -> dict:
    """A saved world with its numbers as Thespis wrote them: whole numbers are ints, except evidence confidences."""
    def whole(x):
        kind = type(x)
        if kind is dict:
            return {k: v if type(v) in PLAIN else whole(v) for k, v in x.items()}
        if kind is list:
            return [v if type(v) in PLAIN else whole(v) for v in x]
        return int(x) if kind is float and x.is_integer() else x

    world = whole(world)
    for b in world.get("beliefs", []):
        for e in b.get("evidence", []):
            e["conf"] = float(e["conf"])
    return world


def _patch(game: Game, w: World) -> list[str]:
    """Bring a world saved under an earlier version of the game file up to this one (Session.restore), in place, and
    say what changed, a line each."""
    d, out = game.cast.data, []
    orphans = sorted(f"{npc} ({t.get('kind')})" for npc, t in w.cast.items() if t.get("kind") not in game.kinds)
    if orphans:
        raise DefinitionError(f"this save has people of a kind the game file no longer has: {', '.join(orphans)}; "
                              "keep their [kind] in the file")
    file_npcs = d.get("npc", {})
    for npc in w.npcs:
        if npc not in file_npcs and npc not in w.cast and npc not in w.gone:
            w.gone.add(npc)
            out.append(f"{npc}: no longer in the game file, so retired; what it believed is kept")
    for npc, t in file_npcs.items():
        if npc not in w.npcs:
            w.npcs[npc] = NPC(npc, t["start"], dict(t.get("drives", {})), dict(t.get("trust_in", {})))
            out.append(f"{npc}: new in the game file, so joined at {t['start']}")
    for pid, p in game.players.items():
        if pid not in w.players:
            w.players[pid] = {"name": p["name"], "loc": p.get("start", "")}
            out.append(f"{pid}: a player new in the game file, so joined")
    if game.places:
        for n in w.npcs.values():
            if n.id not in w.gone and n.loc and n.loc not in game.places:
                start = file_npcs.get(n.id, {}).get("start") or w.cast.get(n.id, {}).get("at", "")
                out.append(f"{n.id}: {n.loc!r} is no longer a place, so back to {start!r}")
                n.loc = start
        start = d.get("player", {}).get("start", "")
        if w.player.get("loc") and w.player["loc"] not in game.places:
            out.append(f"player: {w.player['loc']!r} is no longer a place, so back to {start!r}")
            w.player["loc"] = start
        for pid, p in w.players.items():
            if p.get("loc") and p["loc"] not in game.places:
                back = game.players.get(pid, {}).get("start", "")
                out.append(f"{pid}: {p['loc']!r} is no longer a place, so back to {back!r}")
                p["loc"] = back
    return out


DEFAULT_EVENTS = {CAUGHT: "{a} caught {t} in a lie: that {claim}."}  # what Thespis writes itself, unless the game words it


class Game:
    """A game definition, compiled and checked: load once, play many sessions."""

    def __init__(self, cast: Cast):
        self.cast = cast
        d = cast.data
        self.id = str(d.get("game", {}).get("id") or cast.path.stem)
        self.name = str(d.get("game", {}).get("name", self.id))
        self.places: dict[str, str] = dict(d.get("places", {}))
        self.players: dict[str, dict] = {k: dict(v) for k, v in d.get("players", {}).items()}
        self.kinds: dict[str, dict] = {k: dict(v) for k, v in d.get("kind", {}).items()} \
            if isinstance(d.get("kind", {}), dict) else {}  # kinds of people who may join in play (Session.add)
        found, self.notes = examine(d)  # every mistake at once (thespis.schema); notes are likely slips, allowed
        if found:
            raise refuse(found)
        self.choices = declared(d)
        self.kind_choices = declared_kinds(d) if self.kinds else {}
        self.intents = declared_intents(d)
        claims = d.get("claims", {})
        self.one_actor = frozenset(claims.get("one_actor", ()))  # deeds only one person can have done to another
        self.caught = int(claims.get("caught", 2))  # how far trust falls in whoever told the story that lost
        self.first_hand = int(claims.get("first_hand", 0))
        # Does anyone keep anything quiet? If not, the grapevine needn't ask of every story it weighs.
        self.quiet = bool((d.get("gossip") or {}).get("secret")) or any(
            "keeps" in t for table in ("npc", "kind") for t in (d.get(table) or {}).values() if isinstance(t, dict))
        self.secret = frozenset((d.get("gossip") or {}).get("secret", []))  # predicates nobody passes on  # how much more a teller counts who saw it themselves
        self.ties: dict[str, list[tuple[str, str]]] = {}  # npc -> [(the other, kind)], in the order declared
        for t in d.get("tie", []):
            a, b = t["between"]
            self.ties.setdefault(a, []).append((b, t["kind"]))
            self.ties.setdefault(b, []).append((a, t["kind"]))
        vocabulary = {**{k.lower(): k for k in self.places}, **{v.lower(): k for k, v in self.places.items()}}
        for npc, t in d.get("npc", {}).items():
            vocabulary |= {npc.lower(): npc, str(t["name"]).lower(): npc,
                           **{str(a).lower(): npc for a in t.get("aliases", [])}}
        vocabulary |= {str(p["name"]).lower(): pid for pid, p in self.players.items()}
        self.names = vocabulary  # names, aliases and ids, in lower case, to ids
        stakes = {c.do.partition(":")[0] for cs in self.choices.values() for c in cs.choices if c.asserts}
        self.voice = Voice(cast=cast, validator=Validator(vocabulary), claim_text=self.claim_text,
                           sentence=self.sentence, who=self.who, setting=self.setting, describe=self.describe,
                           places=tuple(self.places), stakes=stakes)

    @classmethod
    def load(cls, path: str | Path) -> Game:
        """The game in a TOML file, checked (thespis.schema): a mistake raises DefinitionError naming its entry, or
        every one, a line each."""
        try:
            return cls(Cast(Path(path)))
        except tomllib.TOMLDecodeError as e:
            raise DefinitionError(f"not TOML: {e}") from e

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

    # ------------------------------------------------------------ words, as the model reads them
    def who(self, x: str | None, names: Mapping[str, str] | None = None) -> str:
        """Who or where `x` is, in words. `names` are a session's players, by id."""
        if not x:
            return ""
        if names and x in names:
            return names[x]
        if x == "player":
            return "the player"
        if x in self.cast.data.get("npc", {}):
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
        template = self.cast.data.get("words", {}).get("events", {}).get(e.verb) or DEFAULT_EVENTS.get(e.verb)
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
        npcs = list(d.get("npc", {}))
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
                   **{str(t["name"]).lower(): n for n, t in d.get("npc", {}).items()},
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

    # ------------------------------------------------------------ the player's words
    @cached_property
    def people(self) -> dict[str, str]:
        """Who each NPC is, briefly, from its persona's first clause: "The stable boy", "A sellsword with a
        reputation to protect". The understander reads it to know who "the barkeep" is."""
        return people(self.cast.data)

    @property
    def claim_words(self) -> dict[str, str]:
        return dict(self.cast.data.get("words", {}).get("claims", {}))

    def offers(self, w: World, player: str, offered: Sequence[Mapping[str, Any]] | None = None,
               to: str | None = None) -> list[Offer]:
        """The intents open now, with each argument's choices: the engine's (`offered`, as its buttons have them),
        held to what the game declares; or, with none given, every intent the game declares over what Thespis knows:
        the NPCs where the player is, or the one they speak `to`. An intent with an argument left no choices isn't
        open."""
        here = w.where(player)
        npcs = tuple(n.id for n in w.npcs_at(here)) if here else tuple(n for n in w.npcs if n not in w.gone)
        players = ("player", *w.players)
        out = []
        every: list[Mapping[str, Any]] = [{"verb": v} for v in self.intents]
        for o in offered if offered is not None else every:
            verb = o.get("verb")
            d = self.intents.get(str(verb))
            if d is None:
                raise Unknown(f"no intent {verb!r} in the game's [intents]")
            given = dict(o.get("args") or {})
            extra = set(given) - {a.name for a in d.args}
            if extra:
                raise DefinitionError(f"{verb}: no argument {', '.join(sorted(extra))}")
            domains: dict[str, Domain] = {}
            for a in d.args:
                domain = self._domain(a, given.get(a.name), w, npcs, players, to if a.name == "to" else None, verb)
                if not domain or (isinstance(domain, Bounds) and domain.low > domain.high):
                    break
                domains[a.name] = domain
            else:
                out.append(Offer(d.verb, domains))
        return out

    def _domain(self, a: Arg, given: Any, w: World, npcs: tuple[str, ...], players: tuple[str, ...], to: str | None,
                verb: object) -> Domain:
        where = f"{verb}.{a.name}"
        if a.type == "amount":
            low, high = a.low, a.high
            if given is not None:
                if not isinstance(given, Mapping) or not all(isinstance(given.get(k, 0), int) for k in ("min", "max")):
                    raise DefinitionError(f"{where}: an amount's choices are {{min, max}}, whole numbers")
                low, high = max(low, given.get("min", low)), min(high, given.get("max", high))
            return Bounds(low, high)
        if a.type == "claim":
            words = self.claim_words
            preds, subjects = a.preds or tuple(words), (*players, *w.npcs)
            if given is not None:
                if not isinstance(given, Mapping):
                    raise DefinitionError(f"{where}: a claim's choices are {{preds, subjects}}")
                preds = self._within(given.get("preds", preds), preds, f"{where}.preds")
                subjects = self._within(given.get("subjects", subjects), subjects, f"{where}.subjects")
            places = tuple(self.places) if any("{place}" in words.get(p, "") for p in preds) else ()
            return ClaimDomain(tuple(preds), tuple(subjects), places, a.denials)
        universe = {"npc": tuple(n for n in w.npcs if n not in w.gone), "player": players,
                    "place": tuple(self.places), "choice": a.options}[a.type]
        if given is not None:
            return self._within(given, universe, where)
        if a.type == "npc":
            return (to,) if to is not None else npcs
        return universe

    @staticmethod
    def _within(given, universe: Sequence[str], where: str) -> tuple[str, ...]:
        if not isinstance(given, list | tuple) or not all(isinstance(x, str) for x in given):
            raise DefinitionError(f"{where}: a list of ids")
        unknown = [x for x in given if x not in universe]
        if unknown:
            raise Unknown(f"{where}: {', '.join(unknown)} isn't one of {', '.join(universe)}")
        return tuple(dict.fromkeys(given))


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
    explain: list[dict] | None = None  # with decide(explain=True): every choice, open or not, and why (Session.explain)

    def to_json(self) -> dict:
        return asdict(self)


class Session:
    """One playthrough's minds: the world they live in, what each saw, and the lines still on their way."""

    def __init__(self, game: Game, world: World, witnesses: dict[str, list[str]] | None = None,
                 gateway: ModelGateway | None = None, mind: Mind | None = None, brain: Brain | None = None,
                 embedder: Embedder | None = None):
        """`embedder` serves recall by meaning, for a game that declares it (`[memory]`). A game with kinds gives
        each session its own validator, which learns the names of whoever joins; a `mind` built on the game's
        validator is moved onto it."""
        self.game, self.world = game, world
        self.cast: Cast = LiveCast(game.cast, world.cast) if game.kinds else game.cast
        self.witnesses: dict[str, list[str]] = witnesses if witnesses is not None else {}
        validator = game.voice.validator
        if game.kinds:
            validator = Validator(dict(game.names))
            if mind is not None and mind.validator is game.voice.validator:
                mind.validator = validator
        self.voice = replace(game.voice, cast=self.cast, validator=validator, sees=reported(self.witnesses),
                             who=self.who,
                             claim_text=lambda c: game.claim_text(c, self._names()),
                             sentence=self.sentence,
                             describe=lambda w, npc, action: game.describe(w, npc, action, self._names()))
        memory = game.cast.data.get("memory", {})
        if embedder is not None and memory.get("recall") == "meaning":
            self.voice.recall = MeaningRetriever(embedder, self.voice.claim_text, self.sentence,
                                                 Weights.from_toml(memory), int(memory.get("k", 5)),
                                                 int(memory.get("events", 5)))
        self.mind = mind or Mind(gateway, self.voice.validator)
        self.brain = brain or UtilityBrain()
        self.embedder = embedder
        self._lines: dict[str, Line] = {}
        self._pending: dict[str, Future] = {}
        self._lock = threading.RLock()
        self._pool: ThreadPoolExecutor | None = None
        self.settled_at: dict[str, float] = {}  # when each line settled (time.monotonic), for measuring
        self.on_pack: Callable[[StatePack], None] | None = None  # sees each state pack as it's built (Rehearsal)
        self.on_settle: Callable[[Line], None] | None = None  # sees each provisional line once it settles (a store)
        self._tied: dict[str, list[tuple[str, str]]] | None = None  # everyone's ties: the game's, and made in play
        self._keeps: dict[str, list[Keep]] = {}  # each NPC's keeps, compiled when first asked
        self.patched: list[str] = []  # how restore brought a save up to a changed game file, if it did
        for npc in world.cast:
            self._enrol(npc)

    @classmethod
    def new(cls, game: Game, seed: int = 0, **kw) -> Session:
        d = game.cast.data
        npcs = {i: NPC(i, t["start"], dict(t.get("drives", {})), dict(t.get("trust_in", {})))
                for i, t in d.get("npc", {}).items()}
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

    # ------------------------------------------------------------ a cast that grows
    def add(self, npc: str, kind: str, name: str, at: str = "", persona: str | None = None,
            goal: str | None = None) -> dict:
        """Someone joins the cast in play: an NPC of a `kind` the game declares (`[kind.<id>]`), with its own id,
        name and place, and its own persona and goal if given. From here on it is an NPC like any the game file
        names: it sees, believes, gossips, feels and chooses as its kind does."""
        with self._lock:
            w, t = self.world, self.game.kinds.get(kind)
            if t is None:
                raise Unknown(f"no kind {kind!r} in the game's [kind]")
            if not ID.fullmatch(npc) or npc in RESERVED or npc in w.npcs or npc in w.players \
                    or npc in self.game.places:
                raise DefinitionError(f"{npc!r} is taken, or isn't an id: letters, digits, _ . and -, and new")
            if not isinstance(name, str) or not name.strip():
                raise DefinitionError(f"{npc}: needs a name")
            if at and self.game.places and at not in self.game.places:
                raise DefinitionError(f"{npc}: {at!r} is not in [places]")
            own = {"kind": kind, "name": name, "at": at}
            own |= {k: v for k, v in (("persona", persona), ("goal", goal)) if v is not None}
            w.cast[npc] = own
            w.npcs[npc] = NPC(npc, at, dict(t.get("drives", {})), dict(t.get("trust_in", {})))
            self._enrol(npc)
            return self._card(npc)

    def retire(self, npc: str) -> dict:
        """An NPC leaves the story, dead or gone for good. It sees, believes, gossips, decides and says nothing
        more. What it believed is kept, and others still believe things about it."""
        with self._lock:
            self._npc(npc)
            self.world.gone.add(npc)
            return self._card(npc)

    def tie(self, a: str, b: str, kind: str) -> dict:
        """A tie between two NPCs, made in play: gossip travels along it as `[gossip] along` says for its kind. Two
        already tied in play change their tie's kind."""
        with self._lock:
            w = self.world
            self._npc(a)
            self._npc(b)
            along = self.cast.data.get("gossip", {}).get("along", {})
            if a == b or kind not in along:
                raise DefinitionError(f"a tie is between two different NPCs, of a kind in [gossip] along: {kind!r}")
            if any(o == b for o, _ in self.game.ties.get(a, [])):
                raise DefinitionError(f"{a} and {b} are tied in the game file")
            w.ties = [t for t in w.ties if {t[0], t[1]} != {a, b}] + [[a, b, kind]]
            self._tied = None
            return {"between": [a, b], "kind": kind}

    def untie(self, a: str, b: str) -> None:
        """Break a tie made in play."""
        with self._lock:
            w = self.world
            kept = [t for t in w.ties if {t[0], t[1]} != {a, b}]
            if len(kept) == len(w.ties):
                raise Unknown(f"no tie made in play between {a} and {b}")
            w.ties, self._tied = kept, None

    # ------------------------------------------------------------ the world, as the engine reports it
    def observe(self, verb: str, actor: str, target: str | None = None, at: str | None = None,
                claim: Claim | Mapping | None = None, witnesses: Sequence[str] = (), said: bool = False,
                true: bool | None = None, amount: int | None = None, conf: float | None = None) -> Event:
        """Something happened. `witnesses` saw it; the actor and target took part. A claim it carries is believed:
        a deed (`said` false) by everyone who saw it, for certain; a statement (`said`) by everyone who heard it, as
        far as each trusts the speaker, or as far as `conf` says when the engine's own rules decide how well it was
        told (a roll of the dice). Its truth, unless the engine says, is whether the ledger shows it happened."""
        with self._lock:
            w = self.world
            if conf is not None and (not said or isinstance(conf, bool) or not 0 <= conf <= 1):
                raise DefinitionError("conf is how far a statement (said) is believed, from 0 to 1")
            if isinstance(witnesses, str):
                raise DefinitionError(f"witnesses: a list of ids, not one string: [{witnesses!r}]")
            if actor != SOMEONE:  # who did it, when nobody knows yet
                self._someone("actor", actor)
            if target is not None:
                self._someone("target", target, places=True)
            self._place("at", at)
            c = self._claim(claim)
            unknown = [n for n in witnesses if n not in w.npcs and not w.is_player(n)]
            if unknown:
                raise Unknown(f"witnesses: no npc or player {', '.join(map(repr, unknown))}"
                              f"{near(unknown[0], self._people())}")
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
                            self._believe(n, c, credence(trust) if conf is None else float(conf), actor, e)
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
            self._place("loc", loc)
            if npc == "player" or npc in self.world.players:
                if any(x is not None for x in (drives, nudge, flags, trust_in)):
                    raise DefinitionError(f"a player has only a place: update({npc!r}, loc=...)")
                if npc == "player":
                    if loc is not None:
                        self.world.player["loc"] = loc
                    return dict(self.world.player)
                if loc is not None:
                    self.world.players[npc]["loc"] = loc
                return {"id": npc, **self.world.players[npc]}
            n = self._npc(npc)
            for name, given in (("drives", drives), ("nudge", nudge)):
                for k in given or {}:
                    if k not in self._drives and k not in n.drives:
                        raise Unknown(f"{name}.{k}: no NPC has a drive {k!r}{near(k, self._drives)}; a drive the "
                                      "engine sets is declared in the game file, as drives = { " + k + " = 0 }")
            for k in trust_in or {}:
                self._someone(f"trust_in.{k}", k)
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
    def _choosing(self, npc: str, moment: str, b: Mapping) -> Choices:
        """`npc`'s choices at `moment`, once the call is checked: the moment exists and every binding is given."""
        self._npc(npc)
        cs = self._choices(npc, moment)
        if cs is None:
            moments = self._moments(npc)
            raise Unknown(f"{npc} has no choices for {moment!r}" + (
                f"; it has {', '.join(map(repr, moments))}{near(moment, moments)}" if moments else
                "; the game declares none for it"))
        missing = sorted(cs.needs - set(b))
        if missing:
            raise DefinitionError(f"{npc}'s choices for {moment!r} need bindings: "
                                  + ", ".join(f"{k!r}" for k in missing) + " (decide(..., bindings={"
                                  + ", ".join(f"{k!r}: ..." for k in missing) + "}))")
        for k in sorted(cs.people):
            if isinstance(b[k], str):
                self._someone(f"bindings.{k}", b[k])
        return cs

    def explain(self, npc: str, moment: str, bindings: Mapping | None = None) -> list[dict]:
        """Why `npc` would do what it would at `moment`, now, without doing it: every choice the game declares, in
        order, with `open` (whether its `when` holds), `blocked` (what keeps it shut: "grudge is 2, needs >= 4"),
        its `utility` and `terms` (how that adds up), and `chosen` on the one it would pick. Changes nothing."""
        with self._lock:
            b = dict(bindings or {})
            return self._explained(npc, self._choosing(npc, moment, b), b)

    def _explained(self, npc: str, cs: Choices, b: Mapping, chosen: str | None = None) -> list[dict]:
        w = self.world
        out = cs.explain(w, View(w.player["loc"]), **b)
        if npc in w.gone:
            for e in out:
                e.update(open=False, blocked=f"{npc} has left the story")
            return out
        allowed = {e["do"]: e["utility"] for e in out if e["open"]}
        pick = chosen if chosen is not None else self.brain.choose(npc, allowed) if allowed else None
        for e in out:
            e["chosen"] = e["do"] == pick
        return out

    def decide(self, npc: str, moment: str, bindings: Mapping | None = None, situation: str | None = None,
               to: str | None = None, wait: bool = True, explain: bool = False) -> Line:
        """What `npc` does at `moment`, among the choices the game declares for it, and its line. The choice is
        recorded with its reason. An action that states a claim logs the statement, told `to` someone. With
        `explain`, the line carries every choice and why it was or wasn't taken (`Session.explain`), as it stood
        when the NPC chose, also when it chose nothing."""
        with self._lock:
            w, b = self.world, dict(bindings or {})
            cs = self._choosing(npc, moment, b)
            if npc in w.gone:
                return Line(None, npc, None, explain=self._explained(npc, cs, b) if explain else None)
            view = View(w.player["loc"])
            choices = cs.options(w, view, **b)
            if not choices:
                return Line(None, npc, None, explain=self._explained(npc, cs, b) if explain else None)
            choice = self.brain.choose(npc, choices)
            why = self._explained(npc, cs, b, choice) if explain else None
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
            line = self._speak("act", d, pack, Utterance(choice, text, cites, "fallback"), wait, statement)
            if why is not None:
                line.explain = why
            return line

    def react(self, npc: str, trigger: str, situation: str | None = None, cites: Sequence[str] = (),
              fill: Mapping | None = None, wait: bool = True) -> Line:
        """`npc`'s line in reply to `trigger`: its template line, voiced by the model if there is one. It cites
        `cites`, or the latest event it knows; with no template or nothing to cite it stays silent."""
        with self._lock:
            w = self.world
            self._npc(npc)
            if not any(trigger in (t.get("lines") or {}) for t in (*self.cast.data.get("npc", {}).values(),
                                                                  *self.game.kinds.values())):
                said_any = sorted({k for t in self.cast.data.get("npc", {}).values() for k in t.get("lines") or {}})
                raise Unknown(f"no NPC has a line for {trigger!r}{near(trigger, said_any)}")
            said = None if npc in w.gone else \
                self._template(npc, trigger, list(cites) or [self.voice.latest(w, npc)], dict(fill or {}))
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
                                            structured=structured, to=to)
            return self._voice(line, "tell" if structured else "narrate", pack,
                               Utterance(None, telling, line.cites, "fallback", segments=segments), wait)

    def understand(self, text: str, to: str | None = None, player: str = "player",
                   offered: Sequence[Mapping[str, Any]] | None = None) -> Understood:
        """What `player`'s words to `to` do, among the intents open now (`[intents]`, thespis.intents): an act to
        apply (`act`), readings to put to the player first (`ask`), or words that do nothing else (`talk`). It changes
        nothing: the engine applies an act as it would the button, and reports what happened with `observe`."""
        with self._lock:
            w = self.world
            if not w.is_player(player):
                raise Unknown(f"no player {player!r}")
            if to is not None:
                self._npc(to)
            if not self.game.intents:
                raise Unknown("the game declares no [intents]")
            offers = self.game.offers(w, player, offered, to)
            names = {**self.game.names, **{str(p["name"]).lower(): pid for pid, p in w.players.items()},
                     **{k: npc for npc, t in w.cast.items() for k in (npc.lower(), str(t["name"]).lower())}}
            who = people(self.cast.data) if w.cast else self.game.people
            words = Words(names, self.game.claim_words, self.who, self.voice.claim_text, who)
        # Outside the lock: a model call takes a second, and nothing here writes to the session.
        return Understander(self.game.intents, words, self.mind, self.embedder).read(text, offers, player, to)

    def tick(self, steps: int = 1) -> Tick:
        """The minds' own time, `steps` phases of it: scheduled walks, then gossip, then drives settling, then the
        next phase. Everyone at the scene of what it does sees it."""
        if isinstance(steps, bool) or not isinstance(steps, int) or steps < 0:
            raise DefinitionError(f"steps: how many ticks, a whole number from 0, got {steps!r}")
        with self._lock:
            w, d = self.world, self.cast.data
            g = d.get("gossip")
            about = None if g and g.get("about") == EVERYONE else (g or {}).get("about", ["player"])

            def walking(t: Tick) -> None:
                walks(w, t, lambda npc: None if npc in w.gone else d["npc"][npc].get("walk"))

            def hear(w: World, npc: str, c: Claim, conf: float, source: str, e: Event) -> None:
                self._believe(npc, c, conf, source, e)

            def grapevine(t: Tick) -> None:
                if g and g.get("along"):
                    tellers = self._tellers()
                    most = g.get("most")
                    turn = spread(w, tellers, self._listeners, about, g.get("priority", {}),
                                  g.get("threshold", 0.5), lambda w, c: w.ledger.happened(c), hear,
                                  self._trusting, most, w.counters.get("grapevine", 0) if most and tellers else 0,
                                  g.get("corroborate", False), self._quiet if self.game.quiet else None)
                    if most:
                        w.counters["grapevine"] = turn  # whose turn it is to tell, next tick
                elif g:
                    gossip(w, self._tellers(), about, g.get("priority", {}), g.get("threshold", 0.5),
                           g.get("decay", 0.8), lambda w, c: w.ledger.happened(c), hear, g.get("corroborate", False),
                           self._quiet if self.game.quiet else None)

            def settling(t: Tick) -> None:
                living = [n for n in w.npcs if n not in w.gone]
                for npc, rest in ((n, d["npc"][n].get("settle", {})) for n in living):
                    drives = w.npcs[npc].drives
                    for k, r in rest.items():
                        v = drives.get(k, int(r))
                        drives[k] = v - 1 if v > r else v + 1 if v < r else v
                for npc in living:
                    self._decay(npc)

            def advance(t: Tick) -> None:
                w.phase += 1

            start = len(w.ledger)
            tick = run_tick(w, [step for _ in range(max(0, steps)) for step in (walking, grapevine, settling,
                                                                                advance)])
            written = list(w.ledger)[start:]
            if written:
                order = {n: i for i, n in enumerate(w.npcs)}
                standing: dict[str, list[str]] = {}  # who is where, once for the tick
                for n in w.npcs.values():
                    if n.id not in w.gone:
                        standing.setdefault(n.loc, []).append(n.id)
                for e in written:
                    self._overheard(e, standing, order)
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
        restores the same.

        A save made before the game file changed (a patch) is brought up to it, and `patched` says how: an NPC the
        file no longer has is retired (it keeps what it believed, and others keep what they believe of it); one the
        file has gained joins at its start; someone standing in a place the file no longer has goes back to their
        start; a player the file has gained joins. A save with people of a kind the file no longer has is refused, as
        there is nothing left to say who they are. Ids are what a save goes by: an NPC whose id changed is a new NPC."""
        if not isinstance(snapshot, Mapping) or "thespis" not in snapshot:
            raise DefinitionError("not a Thespis save: a snapshot is the table Session.snapshot() returns")
        if snapshot.get("thespis") != SNAPSHOT_VERSION:
            raise DefinitionError(f"snapshot version {snapshot.get('thespis')!r}; this Thespis reads "
                                  f"{SNAPSHOT_VERSION}")
        if snapshot.get("game") != game.id:
            raise DefinitionError(f"snapshot of {snapshot.get('game')!r}, not {game.id!r}")
        try:
            world = World.from_json(_numbers(dict(snapshot["world"])))
            witnesses = {k: list(v) for k, v in dict(snapshot.get("witnesses", {})).items()}
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise DefinitionError(f"a damaged snapshot: {type(e).__name__} {e}") from e
        patched = _patch(game, world) if snapshot.get("digest") != game.digest else []
        session = cls(game, world, witnesses, **kw)
        session.patched = patched
        return session

    def inspect(self, npc: str) -> dict:
        """One NPC's mind as it stands: its state and every belief, retracted ones included, with their evidence."""
        with self._lock:
            self._npc(npc)
            return {"npc": self._card(npc), "beliefs": [b.to_json() for b in self.world.beliefs.for_npc(npc)]}

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

    def _people(self) -> set[str]:
        w = self.world
        return {"player", *w.players, *w.npcs}

    def _someone(self, where: str, x: object, places: bool = False) -> None:
        """`x` names an NPC or a player (or, with `places`, a place); else Unknown, with what was probably meant."""
        known = self._people() | (set(self.game.places) if places else set())
        if not isinstance(x, str) or (x not in known and not (places and not self.game.places)):
            what = "npc, player or place" if places else "npc or player"
            raise Unknown(f"{where}: no {what} {x!r}{near(x, known)}")

    def _place(self, where: str, x: object) -> None:
        if x is not None and self.game.places and x not in self.game.places:
            raise Unknown(f"{where}: no place {x!r} in [places]{near(x, self.game.places)}")

    def _claim(self, claim: Claim | Mapping | None) -> Claim | None:
        """A claim the engine reports, checked: its keys, a predicate the game declares, and who it names."""
        if claim is None or isinstance(claim, Claim):
            c = claim
        else:
            if not isinstance(claim, Mapping) or "pred" not in claim or "a" not in claim:
                raise DefinitionError(f"claim: needs pred and a, as {{\"pred\": ..., \"a\": ..., \"b\": ...}}, "
                                      f"got {claim!r}")
            extra = [k for k in claim if k not in CLAIM_KEYS]
            if extra:
                raise DefinitionError(f"claim: unknown key {extra[0]!r}{near(extra[0], CLAIM_KEYS)}")
            c = Claim.from_json(dict(claim))
        if c is None:
            return None
        preds = self.game.claim_words
        if preds and c.pred not in preds:
            raise Unknown(f"claim.pred: no predicate {c.pred!r} in [words.claims]{near(c.pred, preds)}")
        if not self.game.kinds:  # in a cast that grows, a claim may name someone not (yet) in it
            if c.a != SOMEONE:
                self._someone("claim.a", c.a)
            if c.b and c.b != SOMEONE:
                self._someone("claim.b", c.b, places=True)
        self._place("claim.place", c.place)
        return c

    def _moments(self, npc: str) -> list[str]:
        kind = self.world.cast.get(npc, {}).get("kind")
        return [m for (who, m) in self.game.choices if who == npc] + \
            [m for (k, m) in self.game.kind_choices if kind is not None and k == kind]

    @cached_property
    def _drives(self) -> frozenset[str]:
        """Every drive the game file gives an NPC or kind."""
        out: set[str] = set()
        for t in (*self.game.cast.data.get("npc", {}).values(), *self.game.kinds.values()):
            for key in ("drives", "settle", "decay"):
                out |= set(t.get(key, {}))
            for moves in t.get("feels", {}).values():
                out |= set(moves)
        return frozenset(out)

    def _where(self, who: str) -> str:
        return self.world.where(who)

    def _names(self) -> dict[str, str]:
        """This session's own names, by id: its players, and whoever joined its cast."""
        w = self.world
        return {**{pid: p["name"] for pid, p in w.players.items() if p.get("name")},
                **{npc: t["name"] for npc, t in w.cast.items()}}

    def _card(self, npc: str) -> dict:
        """An NPC's state, as the engine sees it: with its kind and name if it joined in play, and whether it has
        gone. What only the demo games set (`frozen_until`, `last_seen`) is left out unless it is set."""
        w = self.world
        own = w.cast.get(npc, {})
        state = {k: v for k, v in w.npcs[npc].to_json().items()
                 if not (k in ("frozen_until", "last_seen") and v is None)}
        return {**state, **{k: own[k] for k in ("kind", "name") if k in own},
                **({"gone": True} if npc in w.gone else {})}

    def _enrol(self, npc: str) -> None:
        """Someone who joined in play can be named in a line, by id or by name."""
        self.voice.validator.learn({npc: npc, str(self.world.cast[npc]["name"]): npc})

    def _choices(self, npc: str, moment: str) -> Choices | None:
        """The NPC's choices at a moment: its own, or its kind's if it joined in play."""
        cs = self.game.choices.get((npc, moment))
        if cs is None and npc in self.world.cast:
            kind = self.game.kind_choices.get((self.world.cast[npc]["kind"], moment))
            cs = replace(kind, npc=npc) if kind else None
        return cs

    def _ties(self) -> dict[str, list[tuple[str, str]]]:
        """Everyone's ties, [(the other, kind)]: the game file's, then those made in play."""
        if self._tied is None:
            tied = {k: list(v) for k, v in self.game.ties.items()}
            for a, b, kind in self.world.ties:
                tied.setdefault(a, []).append((b, kind))
                tied.setdefault(b, []).append((a, kind))
            self._tied = tied
        return self._tied

    def _overheard(self, e: Event, standing: Mapping[str, Sequence[str]] | None = None,
                   order: Mapping[str, int] | None = None) -> None:
        """Everyone at the scene of an event Thespis itself wrote saw it: NPCs, and the players standing there.
        `standing` says who is where and `order` gives each one's place in the cast, for a caller with many events."""
        w = self.world
        if not e.loc:  # it happened nowhere anyone else stood: word passed between two people apart
            return
        if standing is not None and order is not None:  # at_the_scene, looked up instead of asked of everyone
            there = {n for place in {e.loc, e.target} if place for n in standing.get(place, ())}
            seen = sorted(there - {e.actor, e.target}, key=order.__getitem__)
        else:
            seen = [n for n in w.npcs if n not in (e.actor, e.target) and n not in w.gone and at_the_scene(w, n, e)]
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
        if npc in w.gone:
            return
        # Whose story it is: what the teller had it from, followed back to whoever saw it or first said it. A report of
        # the same story, by however many mouths, counts once (thespis.beliefs.fuse).
        story = () if source in FIRST_HAND else tuple(sorted(origins(w.beliefs, source, c, w.phase) or {source}))
        belief, new = w.beliefs.add_evidence(npc, c, conf, source, e.id, w.phase, origin=story)
        if c.neg:
            w.beliefs.add_evidence(npc, c.affirmed(), conf, source, e.id, w.phase, against=True, origin=story)
            return
        if c.pred in self.game.one_actor and belief.active:
            self._one_culprit(npc, c)
        feels = self.cast.data["npc"][npc].get("feels", {}).get(c.pred)
        if new and feels and c.b == npc and belief.active and not self._felt(npc, belief):  # done to it: `b` is whom
            n = w.npcs[npc]
            for drive, steps in feels.items():
                self._drive(n, drive, _clamp(n.drives.get(drive, 0) + math.floor(steps * belief.conf + 0.5), DRIVES))

    def _felt(self, npc: str, belief) -> bool:
        """Whether the NPC already felt this deed: it held it as done by "someone" and now learns who, or the other
        way round. Learning who did it is no second offence."""
        c = belief.claim
        return any(b is not belief and b.active and b.claim.same_deed(c) and SOMEONE in (b.claim.a, c.a)
                   for b in self.world.beliefs.for_npc(npc))

    def _one_culprit(self, npc: str, c: Claim) -> None:
        """`c` says who did a deed only one person can have done (`[claims] one_actor`). If the NPC also believes
        someone else did it, the two can't both be true: the story from the source it trusts less loses, whoever told
        it that story is trusted less (`[claims] caught`), and everything else they said is weighed again
        (thespis.beliefs.reconcile). Sources it trusts alike settle nothing. A teller who saw it themselves counts
        for more than one who only heard (`[claims] first_hand`)."""
        w, n = self.world, self.world.npcs[npc]
        mine = w.beliefs.get(npc, c)
        rivals = [b for b in w.beliefs.for_npc(npc) if _other_actor(b.claim, c) and b.active]
        if mine is None or not rivals:
            return
        for b in (mine, *rivals):  # trust in a teller it had no view of starts at 0, so being caught can lower it
            for ev in b.evidence:
                for who in (ev.source, *ev.origin):
                    if who != npc and (who in w.npcs or w.is_player(who)):
                        n.trust_in.setdefault(who, 0)
        def caught(liar: str, lie: Claim) -> None:  # in the ledger, where the game (events, tick) and choices see it
            w.ledger.append(w.phase, CAUGHT, npc, liar, n.loc, lie, w.ledger.happened(lie))

        reconcile(w.beliefs, npc, c, n.trust_in, w.phase, _other_actor, self.game.caught,
                  first_hand=self.game.first_hand, caught=caught)
        for who, trust in n.trust_in.items():
            n.trust_in[who] = _clamp(trust, TRUST)

    def _drive(self, n: NPC, drive: str, value: int) -> None:
        """Set a drive; one that decays (`[npc.<id>.decay]`) fades from this new peak, from now."""
        n.drives[drive] = value
        if drive in self.cast.data["npc"][n.id].get("decay", {}):
            n.flags.setdefault("decay", {})[drive] = [value, self.world.phase]

    def _decay(self, npc: str) -> None:
        """Each decaying drive, as it will stand next phase: the baseline `to` plus what's left of its last peak
        after the ticks since, halving every `half_life` ticks, but never less than `keep` of it."""
        w, n = self.world, self.world.npcs[npc]
        for drive, c in self.cast.data["npc"][npc].get("decay", {}).items():
            peak, since = n.flags.setdefault("decay", {}).setdefault(drive, [n.drives.get(drive, c.get("to", 0)),
                                                                             w.phase])
            left = max(0.5 ** ((w.phase + 1 - since) / c["half_life"]), c.get("keep", 0))
            n.drives[drive] = _clamp(math.floor(c.get("to", 0) + (peak - c.get("to", 0)) * left + 0.5), DRIVES)

    def _gossips(self) -> list[str]:
        """Who passes news on, as `[gossip] gossips` names them: a list of NPCs, or "everyone" there is. Empty if the
        game names nobody (with ties, everyone tied then does)."""
        names = self.cast.data.get("gossip", {}).get("gossips", [])
        return list(self.world.npcs) if names == EVERYONE else list(names)

    def _tellers(self) -> list[str]:
        """Who passes news on this tick: with ties, those `gossips` names, or else everyone tied; without, those it
        names. Nobody who has left the story."""
        w, g = self.world, self.cast.data.get("gossip") or {}
        return [t for t in (self._gossips() or list(self._ties()) if g.get("along") else self._gossips())
                if t not in w.gone]

    def _quiet(self, teller: str, claim: Claim) -> bool:
        """Does `teller` keep `claim` to itself: a secret (`[gossip] secret`), or something it keeps
        (`[[npc.<id>.keeps]]`) while that keep's `when` holds?"""
        return self._keeping(teller, claim) is not None

    def _keeping(self, teller: str, claim: Claim) -> str | None:
        """Why `teller` keeps `claim` to itself, or None if it doesn't."""
        if claim.pred in self.game.secret:
            return "it's a secret: [gossip] secret"
        keeps = self._keeps.get(teller)
        if keeps is None:
            keeps = self._keeps[teller] = compile_keeps(teller, self.cast.data["npc"][teller].get("keeps", []))
        w = self.world
        for i, k in enumerate(keeps):
            if k.covers(claim) and k.when(w, w.npcs[teller], View(w.player["loc"]), {"self": teller}):
                return f"keeps it quiet ([[npc.{teller}.keeps]] {i + 1})"
        return None

    def _trusting(self, listener: str, teller: str) -> float:
        """How far a listener believes what a teller tells it along the grapevine: as it would face to face."""
        return credence(self.world.npcs[listener].trust_in.get(teller, 0))

    def events(self, after: str | None = None, verb: str | None = None) -> list[Event]:
        """The ledger's events after the event `after` (all of them if None), in order, of one `verb` if given. After
        an `observe`, `events(after=event.id)` is what it led to, such as an NPC catching someone in a lie
        (`caught`: its actor caught its target; its claim is the lie)."""
        with self._lock:
            w = self.world
            if after is not None and not self._has_event(after):
                raise Unknown(f"no event {after!r}")
            return [e for e in w.ledger.after(after) if verb is None or e.verb == verb]

    def _has_event(self, event_id: str) -> bool:
        try:
            self.world.ledger.get(event_id)
        except KeyError:
            return False
        return True

    def trace(self, claim: Claim | Mapping) -> dict:
        """How a story stands on the grapevine, changing nothing: who holds it (`holders`: how sure, and the evidence
        they have it from), what the next tick's gossip would tell of it and how sure each listener would be
        (`next`, with the sum: "0.9 x 0.9 (trust 2) x 0.9 (friend) = 0.73"), and where it stops short of someone who
        doesn't hold it, and why (`stopped`: under the threshold, something worse told first, nobody to tell)."""
        with self._lock:
            c = self._claim(claim)
            assert c is not None
            w, g = self.world, self.cast.data.get("gossip")
            holders = [{"npc": b.npc, "conf": b.conf, "status": b.status,
                        "from": [e.to_json() for e in b.evidence]} for b in w.beliefs.all() if b.claim == c]
            out: dict = {"claim": c.label(), "holders": holders, "next": [], "stopped": []}
            if not g:
                out["stopped"].append({"npc": None, "why": "the game declares no [gossip]"})
                return out
            along, threshold = bool(g.get("along")), float(g.get("threshold", 0.5))
            about = None if g.get("about") == EVERYONE else g.get("about", ["player"])
            tellers = self._tellers()
            decay = float(g.get("decay", 0.8))

            def heard_by(teller: str) -> list[tuple[str, float]]:
                if along:
                    return self._listeners(teller)
                return [(n.id, decay) for n in w.npcs_at(w.npcs[teller].loc) if n.id != teller]
            plan = tellings(w, tellers, heard_by, about, g.get("priority", {}), threshold,
                            self._trusting if along else lambda listener, teller: 1.0, g.get("corroborate", False),
                            w.counters.get("grapevine", 0) if along and g.get("most") and tellers else 0,
                            self._quiet if self.game.quiet else None)
            most = int(g["most"]) if along and g.get("most") else None
            plan, later = (plan[:most], plan[most:]) if most is not None else (plan, [])
            kinds = {(a, b): kind for a, ts in self._ties().items() for b, kind in ts}
            for t in plan:
                if t.claim != c:
                    continue
                how = f"{t.held:g}"
                if along:
                    trust = w.npcs[t.listener].trust_in.get(t.teller, 0)
                    how += f" x {t.trust:g} (trust {trust}) x {t.carry:g} " \
                           f"({kinds.get((t.teller, t.listener), 'in person')})"
                else:
                    how += f" x {t.carry:g} (decay)"
                out["next"].append({"teller": t.teller, "listener": t.listener, "conf": t.conf,
                                    "how": f"{how} = {t.conf:g}"})
            told = {(t.teller, t.listener): t.claim for t in plan}
            stopped = out["stopped"]
            waiting = {(t.teller, t.listener) for t in later if t.claim == c}
            for b in (b for b in w.beliefs.all() if b.claim == c and b.npc not in w.gone):
                h = b.npc
                if h not in tellers:
                    stopped.append({"npc": h, "why": "doesn't pass news on" + (
                        " (no ties, and not in [gossip] gossips)" if along else " (not in [gossip] gossips)")})
                elif not b.active:
                    stopped.append({"npc": h, "why": "no longer believes it"})
                elif (keeping := self._keeping(h, c)) is not None:
                    stopped.append({"npc": h, "why": keeping})
                elif about is not None and not any(c.mentions(x) for x in about):
                    stopped.append({"npc": h, "why": "it isn't news of anyone [gossip] about names"})
                elif b.conf < threshold:
                    stopped.append({"npc": h, "why": f"holds it at {b.conf:g}, under the threshold {threshold:g}"})
                elif not heard_by(h):
                    stopped.append({"npc": h, "why": "has nobody to tell" + (
                        ": no ties, and nobody where they stand" if along else ": nobody where they stand")})
                else:
                    for listener, _ in heard_by(h):
                        if told.get((h, listener)) == c:
                            continue
                        if (h, listener) in waiting:
                            why = f"waits: the town tells at most {most} things a tick"
                        elif c.a == listener:
                            why = "it is about them: they know what they did"
                        elif (other := told.get((h, listener))) is not None:
                            why = f"tells them {other.label()} first"
                        elif any(t.listener == listener and t.claim == c for t in plan):
                            why = "hears it from someone else first"
                        else:
                            continue  # they hold it already: the story reached them
                        stopped.append({"npc": h, "listener": listener, "why": why})
            return out

    def _listeners(self, teller: str) -> list[tuple[str, float]]:
        """Whom `teller` passes gossip to, and how much of it carries: everyone tied to it, wherever they are, by
        the kind of tie; then anyone else standing with it, as a stranger's tale (`[gossip] in_person`)."""
        g, w = self.game.cast.data["gossip"], self.world
        out = [(other, float(g["along"][kind])) for other, kind in self._ties().get(teller, []) if other not in w.gone]
        tied = {o for o, _ in out}
        here = w.npcs[teller].loc
        out += [(n.id, float(g.get("in_person", 0.8))) for n in w.npcs_at(here) if n.id != teller and n.id not in tied]
        return out

    def _template(self, npc: str, key: str, cites: list[str | None], fill: dict,
                  action: str | None = None) -> tuple[str, list[str]] | None:
        """The NPC's template line for `key`, filled, and what it cites; None with no template or nothing to cite."""
        text, known = self.cast.template(npc, key), [c for c in cites if c]
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
            self._settle(line.id, self._call(kind, pack, fallback), d, statement, notify=False)
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

    def _settle(self, lid: str, u: Utterance, d: Decision | None, statement: Event | None,
                notify: bool = True) -> None:
        """The line's final words. `notify` tells on_settle (a store), for a line that was provisional; a line the
        caller waited for wasn't, and settles while the caller holds the session's lock, where a store taking its own
        lock and then this one would deadlock with it (the caller's own save stores it instead)."""
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
        if notify and self.on_settle is not None:
            self.on_settle(settled)
