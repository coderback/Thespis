"""A game file's shape, checked when it loads, so a mistake fails at once and names its entry, not quietly mid-game.

Everything a game file may hold is listed here: its tables and keys, the people, places, predicates and drives it
names, and its templates. `problems` lists every mistake at once, each naming where it is and, for a typo, what was
probably meant (`npc.bess: unknown table 'feel'; did you mean feels?`). `Game` refuses a file with any, and
`thespis check` prints them all. `notes` lists what is allowed but likely a slip: a choice whose action has no line,
so the NPC does it in silence.

What a file names, it declares:
  - **People:** `npc` ids, `[players.<id>]` ids and "player". "self" in a choice is the NPC choosing. A game with
    `[kind]`s has people made in play, whose ids no file can know, so their names aren't checked there.
  - **Places:** `[places]`. A game that declares none may name any.
  - **Predicates:** `[words.claims]`. Every claim a file names (a feeling, a choice's belief, `one_actor`, a gossip
    priority) uses one of them.
  - **Drives:** whatever an NPC or kind has in `drives`, `settle`, `feels` or `decay`. A drive a choice names that
    nobody has would always be 0.
  - **Templates** are words with names in braces, filled when they're said: `{a} stole from {b}`. Only a plain name
    goes in the braces (no `{a:>9}` or `{a.b}`), and words and actions may use only the names they're given.
  - **`[custom]`** is the game's own: Thespis never reads it.
"""

from __future__ import annotations

import difflib
import re
import string
from collections.abc import Mapping
from typing import Any

from thespis.considerations import DefinitionError, compile_choices
from thespis.intents import declared_intents

DRIVES, TRUST = (0, 10), (-5, 5)
EVERYONE = "everyone"
TABLES = ("game", "places", "player", "players", "npc", "kind", "tie", "gossip", "claims", "words", "actions",
          "intents", "situations", "narrator", "memory", "custom")
PERSON = ("persona", "goal", "drives", "trust_in", "walk", "settle", "feels", "decay", "lines", "choices")
NPC_KEYS = ("name", "start", "aliases", *PERSON)
GOSSIP = ("gossips", "about", "priority", "threshold", "decay", "along", "in_person", "most", "corroborate")
CLAIMS = ("one_actor", "caught", "first_hand", "description")
INTENT = ("means", "reads", "args", "examples", "consequential", "asks")
ARG = ("type", "options", "min", "max", "preds", "optional", "denials")
MEMORY = ("recall", "salient", "k", "events", "meaning", "recency", "half_life", "salience", "confidence")
CLAIM_FIELDS = ("a", "b", "place", "at")  # what fills a claim's words
EVENT_FIELDS = ("a", "t", "where", "to", "claim", "amount")  # an event's
ACTION_FIELDS = ("who",)  # an action's
CLAIM_KEYS = ("pred", "a", "b", "place", "at", "neg")
GAME = ("id", "name", "setting")
PLAYER = ("start",)
PLAYERS = ("name", "start")
NARRATOR = ("name", "persona", "structured")
DECAY = ("to", "half_life", "keep")
TIE = ("between", "kind")
WORDS = ("claims", "events")
NAME = re.compile(r"[A-Za-z_]\w*")
_FORMAT = string.Formatter()


def near(word: object, choices) -> str:
    """"; did you mean X?" for the closest of `choices` to a slip, or nothing."""
    match = difflib.get_close_matches(str(word), [str(c) for c in choices], n=1, cutoff=0.6)
    return f"; did you mean {match[0]}?" if match else ""


def _whole(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _number(v: object) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def _bound(s: object) -> bool:
    """A string the caller fills when it asks: "{who}"."""
    return isinstance(s, str) and "{" in s


class _Check:
    def __init__(self, d: Mapping):
        self.d, self.out, self.notes = d, [], []
        npcs, kinds = d.get("npc", {}), d.get("kind", {})
        self.npcs = dict(npcs) if isinstance(npcs, Mapping) else {}
        self.kinds = dict(kinds) if isinstance(kinds, Mapping) else {}
        places, players = d.get("places", {}), d.get("players", {})
        self.places = dict(places) if isinstance(places, Mapping) else {}
        self.players = dict(players) if isinstance(players, Mapping) else {}
        self.people = {"player", *self.npcs, *self.players}
        words = d.get("words", {})
        claims = words.get("claims", {}) if isinstance(words, Mapping) else {}
        self.preds = set(claims) if isinstance(claims, Mapping) else set()
        self.drives = set()
        for t in (*self.npcs.values(), *self.kinds.values()):
            if isinstance(t, Mapping):
                for key in ("drives", "settle", "decay"):
                    if isinstance(t.get(key), Mapping):
                        self.drives |= set(t[key])
                for moves in (t.get("feels") or {}).values() if isinstance(t.get("feels"), Mapping) else ():
                    if isinstance(moves, Mapping):
                        self.drives |= set(moves)

    def add(self, problem: str) -> None:
        self.out.append(problem)

    # ------------------------------------------------------------ shapes
    def keys(self, t: Mapping, allowed, where: str) -> None:
        for k, v in t.items():
            if k not in allowed:
                what = "table" if isinstance(v, Mapping) or (isinstance(v, list) and v and isinstance(v[0], Mapping)) \
                    else "key"
                self.add(f"{where}: unknown {what} {k!r}{near(k, allowed)}")

    def table(self, where: str, v: object) -> Mapping:
        if not isinstance(v, Mapping):
            self.add(f"{where}: a table, got {v!r}")
            return {}
        return v

    def text(self, where: str, v: object) -> None:
        if not isinstance(v, str):
            self.add(f"{where}: words in quotes, got {v!r}")

    def share(self, where: str, v: object, what: str) -> None:
        if not _number(v) or not 0 <= v <= 1:  # type: ignore[operator]
            self.add(f"{where}: {what}, 0 to 1")

    def template(self, where: str, s: object, allowed: tuple[str, ...] | None) -> None:
        """Words with names in braces. `allowed` names what fills them; None for the caller's own bindings."""
        if not isinstance(s, str):
            self.add(f"{where}: words in quotes, got {s!r}")
            return
        try:
            parts = list(_FORMAT.parse(s))
        except ValueError as e:
            self.add(f"{where}: {e} (write {{{{ or }}}} for a brace itself)")
            return
        for _, field, spec, conversion in parts:
            if field is None:
                continue
            if not NAME.fullmatch(field) or spec or conversion:
                whole = field + (f"!{conversion}" if conversion else "") + (f":{spec}" if spec else "")
                self.add(f"{where}: {{{whole}}}: only a plain name goes in braces, like {{a}}")
            elif allowed is not None and field not in allowed:
                self.add(f"{where}: {{{field}}} is never filled here; it may use "
                         f"{', '.join('{' + a + '}' for a in allowed)}{near(field, allowed)}")

    # ------------------------------------------------------------ what a file names
    def person(self, where: str, x: object, also: tuple[str, ...] = ()) -> None:
        if not isinstance(x, str):
            self.add(f"{where}: an id in quotes, got {x!r}")
        elif not (_bound(x) or x in self.people or x in also or self.kinds):
            self.add(f"{where}: no npc or player {x!r}{near(x, (*self.people, *also))}")

    def place(self, where: str, x: object) -> None:
        if not isinstance(x, str):
            self.add(f"{where}: a place id in quotes, got {x!r}")
        elif self.places and not _bound(x) and x not in self.places:
            self.add(f"{where}: {x!r} is not in [places]{near(x, self.places)}")

    def pred(self, where: str, p: object) -> None:
        if not isinstance(p, str):
            self.add(f"{where}: a predicate in quotes, got {p!r}")
        elif not _bound(p) and p not in self.preds:
            self.add(f"{where}: predicate {p!r} is not in [words.claims]{near(p, self.preds)}"
                     if self.preds else f"{where}: predicate {p!r} needs words in [words.claims]: {p} = \"{{a}} ... "
                                         "{b}\"")

    def drive(self, where: str, d: object) -> None:
        if not isinstance(d, str):
            self.add(f"{where}: a drive's name in quotes, got {d!r}")
        elif not _bound(d) and d not in self.drives:
            self.add(f"{where}: no NPC or kind has a drive {d!r}"
                     + (near(d, self.drives) or f"; if the game sets it, give an NPC drives = {{ {d} = 0 }}"))

    def claim(self, where: str, c: Mapping) -> None:
        self.keys(c, CLAIM_KEYS, where)
        self.pred(f"{where}.pred", c.get("pred"))
        for k in ("a", "b"):
            if k in c:
                self.person(f"{where}.{k}", c[k], ("self", "someone"))
        if "place" in c:
            self.place(f"{where}.place", c["place"])

    def condition(self, where: str, c: object) -> None:
        if not isinstance(c, Mapping):
            return  # its shape is compile_choices' to report
        if "drive" in c:
            self.drive(f"{where}.drive", c["drive"])
        elif "at" in c:
            self.place(f"{where}.at", c["at"])
        elif "with" in c:
            self.person(f"{where}.with", c["with"])
        elif "trust" in c:
            self.person(f"{where}.trust", c["trust"])
        elif "caught" in c:
            self.person(f"{where}.caught", c["caught"])
        elif "believes" in c and isinstance(c["believes"], Mapping):
            self.claim(f"{where}.believes", c["believes"])
        elif "any" in c or "all" in c:
            key = "any" if "any" in c else "all"
            for i, x in enumerate(c[key] if isinstance(c[key], list) else ()):
                self.condition(f"{where}.{key}[{i}]", x)
        elif "not" in c:
            self.condition(f"{where}.not", c["not"])

    def conditions(self, where: str, cs: object) -> None:
        for i, c in enumerate(cs if isinstance(cs, list) else [cs] if cs is not None else []):
            self.condition(f"{where}[{i}]" if isinstance(cs, list) else where, c)

    # ------------------------------------------------------------ the tables
    def check(self) -> None:
        d = self.d
        for k in d:
            if k not in TABLES:
                near = difflib.get_close_matches(k, TABLES, n=1, cutoff=0.6)
                self.add(f"[{k}]: unknown table" + (f"; did you mean [{near[0]}]?" if near else
                                                   "; keep the game's own data in [custom]"))
        for name in ("game", "places", "player", "players", "gossip", "claims", "words", "actions", "intents",
                     "situations", "narrator", "memory", "kind", "npc"):
            if name in d:
                self.table(f"[{name}]", d[name])
        if not (self.npcs or self.kinds):
            self.add("a game needs at least one [npc.<id>], or a [kind.<id>] for people who join in play")
        game = d.get("game", {})
        if isinstance(game, Mapping):
            self.keys(game, GAME, "game")
            for k in GAME:
                if k in game:
                    self.text(f"game.{k}", game[k])
        for p, name in self.places.items():
            self.text(f"places.{p}", name)
        player = d.get("player", {})
        if isinstance(player, Mapping):
            self.keys(player, PLAYER, "player")
            if player.get("start") is not None:
                start = player["start"]
                if self.places and start not in self.places:
                    self.add(f"player.start: {start!r} is not in [places]{near(start, self.places)}")
        for pid, p in self.players.items():
            if pid in self.npcs or pid == "player" or not isinstance(p, Mapping) or not isinstance(p.get("name"), str):
                self.add(f"players.{pid}: needs name = \"...\", and an id no NPC has")
                continue
            self.keys(p, PLAYERS, f"players.{pid}")
            if self.places and p.get("start") is not None and p["start"] not in self.places:
                self.add(f"players.{pid}.start: {p['start']!r} is not in [places]{near(p['start'], self.places)}")
        for npc, t in self.npcs.items():
            self.npc(f"npc.{npc}", npc, t, "npc")
        for kind, t in self.kinds.items():
            self.npc(f"kind.{kind}", kind, t, "kind")
        self.gossip()
        self.claims()
        self.words()
        self.intents()
        situations = d.get("situations", {})
        for k, s in situations.items() if isinstance(situations, Mapping) else ():
            self.template(f"situations.{k}", s, None)
        narrator = d.get("narrator", {})
        if isinstance(narrator, Mapping):
            self.keys(narrator, NARRATOR, "narrator")
            for k in ("name", "persona"):
                if k in narrator:
                    self.text(f"narrator.{k}", narrator[k])
            if not isinstance(narrator.get("structured", False), bool):
                self.add("narrator.structured: true or false")
        memory = d.get("memory", {})
        if isinstance(memory, Mapping):
            self.keys(memory, MEMORY, "memory")
            for k in ("meaning", "recency", "half_life", "salience", "confidence", "k", "events"):
                if k in memory and not _number(memory[k]):
                    self.add(f"memory.{k}: a number, got {memory[k]!r}")
            if "recall" in memory and memory["recall"] != "meaning":
                self.add(f"memory.recall: \"meaning\", or leave it out, got {memory['recall']!r}")
            salient = memory.get("salient", {})
            for p, v in salient.items() if isinstance(salient, Mapping) else ():
                self.pred(f"memory.salient.{p}", p)
                if not _number(v):
                    self.add(f"memory.salient.{p}: a number, got {v!r}")

    def npc(self, where: str, me: str, t: object, table: str) -> None:
        if not isinstance(t, Mapping):
            self.add(f"{where}: a table, got {t!r}")
            return
        if table == "kind":
            for key in ("name", "start"):
                if key in t:
                    self.add(f"{where}: {key} is each person's own, given when they join")
            self.keys(t, (*PERSON, "name", "start"), where)
        else:
            self.keys(t, NPC_KEYS, where)
        for key in ("name", "persona", "goal", "start") if table == "npc" else ("persona", "goal"):
            if not isinstance(t.get(key), str):
                self.add(f"{where}: needs {key} = \"...\"")
        if table == "npc" and isinstance(t.get("start"), str):
            self.place(f"{where}.start", t["start"])
        walk = t.get("walk", [])
        if not isinstance(walk, list):
            self.add(f"{where}.walk: a list of places, one a tick")
        for i, p in enumerate(walk if isinstance(walk, list) else ()):
            self.place(f"{where}.walk[{i}]", p)
        aliases = t.get("aliases", [])
        if not (isinstance(aliases, list) and all(isinstance(a, str) for a in aliases)):
            self.add(f"{where}.aliases: a list of names")
        for key, bounds, what in (("drives", DRIVES, "a whole number from 0 to 10"),
                                  ("settle", DRIVES, "the value it drifts back to, a whole number from 0 to 10")):
            for k, v in self.table(f"{where}.{key}", t[key]).items() if key in t else ():
                if not _whole(v) or not bounds[0] <= v <= bounds[1]:
                    self.add(f"{where}.{key}.{k}: {what}, got {v!r}")
        for k, v in self.table(f"{where}.trust_in", t["trust_in"]).items() if "trust_in" in t else ():
            self.person(f"{where}.trust_in.{k}", k)
            if not _whole(v) or not TRUST[0] <= v <= TRUST[1]:
                self.add(f"{where}.trust_in.{k}: a whole number from -5 to 5, got {v!r}")
        for p, moves in self.table(f"{where}.feels", t["feels"]).items() if "feels" in t else ():
            self.pred(f"{where}.feels.{p}", p)
            if not isinstance(moves, Mapping) or not all(_whole(v) for v in moves.values()):
                self.add(f"{where}.feels.{p}: {{drive = steps, ...}}, whole numbers")
        for drive, c in self.table(f"{where}.decay", t["decay"]).items() if "decay" in t else ():
            if not isinstance(c, Mapping) or not _number(c.get("half_life")) or c["half_life"] <= 0:
                self.add(f"{where}.decay.{drive}: needs half_life > 0 (ticks)")
                continue
            self.keys(c, DECAY, f"{where}.decay.{drive}")
            if not _number(c.get("keep", 0)) or not 0 <= c.get("keep", 0) <= 1:
                self.add(f"{where}.decay.{drive}: keep is a share of the peak, 0 to 1")
            if not _number(c.get("to", 0)):
                self.add(f"{where}.decay.{drive}.to: the drive's resting value, a number")
        lines = self.table(f"{where}.lines", t["lines"]) if "lines" in t else {}
        for k, s in lines.items():
            self.template(f"{where}.lines.{k}", s, None)
        for moment, cs in self.table(f"{where}.choices", t["choices"]).items() if "choices" in t else ():
            at = f"{where}.choices.{moment}"
            try:
                compile_choices(me, moment, cs, table)
            except DefinitionError as e:
                self.add(str(e))
                continue
            for i, c in enumerate(cs):
                self.choice(f"{at}[{i}]", me, c, lines)

    def choice(self, where: str, me: str, c: Mapping, lines: Mapping) -> None:
        kind, _, arg = c["do"].partition(":")
        if arg and not _bound(arg) and not (arg in self.people or arg in self.places or arg == "self"
                                            or arg.lstrip("-").isdigit() or self.kinds):
            self.add(f"{where}.do: {arg!r} is no npc, player or place{near(arg, (*self.people, *self.places))}")
        if kind not in lines:
            self.notes.append(f"{where}.do: {me} has no line for {kind!r} in its lines, so it does this in silence")
        if isinstance(c.get("asserts"), Mapping):
            self.claim(f"{where}.asserts", c["asserts"])
        self.conditions(f"{where}.when", c.get("when"))
        for i, u in enumerate(c["utility"] if isinstance(c["utility"], list) else [c["utility"]]):
            at = f"{where}.utility[{i}]" if isinstance(c["utility"], list) else f"{where}.utility"
            if isinstance(u, Mapping):
                if "drive" in u:
                    self.drive(f"{at}.drive", u["drive"])
                if "if" in u:
                    self.conditions(f"{at}.if", u["if"])

    def gossip(self) -> None:
        g = self.d.get("gossip", {})
        if not isinstance(g, Mapping):
            return
        self.keys(g, GOSSIP, "gossip")
        gossips = g.get("gossips", [])
        if gossips != EVERYONE and not isinstance(gossips, list):
            self.add(f"gossip.gossips: a list of npcs, or \"{EVERYONE}\"")
        for who in gossips if isinstance(gossips, list) else ():
            if who not in self.npcs:
                self.add(f"gossip.gossips: {who!r} is not an npc{near(who, self.npcs)}")
        about = g.get("about", [])
        if about != EVERYONE and not (isinstance(about, list) and all(isinstance(x, str) for x in about)):
            self.add(f"gossip.about: a list of ids, or \"{EVERYONE}\"")
        for i, x in enumerate(about if isinstance(about, list) else ()):
            self.person(f"gossip.about[{i}]", x)
        for p, v in self.table("gossip.priority", g["priority"]).items() if "priority" in g else ():
            self.pred(f"gossip.priority.{p}", p)
            if not _number(v):
                self.add(f"gossip.priority.{p}: a number, the higher told first, got {v!r}")
        for k, what in (("threshold", "how sure a teller must be to pass something on"),
                        ("decay", "how much of a story survives each telling"),
                        ("in_person", "how much carries to someone standing with the teller")):
            if k in g:
                self.share(f"gossip.{k}", g[k], what)
        most = g.get("most")
        if most is not None and (not _whole(most) or most < 1):
            self.add("gossip.most: how many things are told in a tick, a whole number from 1")
        if not isinstance(g.get("corroborate", False), bool):
            self.add("gossip.corroborate: true if a second witness's word makes a listener surer")
        along = g.get("along", {})
        for kind, carry in self.table("gossip.along", along).items() if "along" in g else ():
            self.share(f"gossip.along.{kind}", carry, "how much carries")
        ties = self.d.get("tie", [])
        if not isinstance(ties, list):
            self.add("tie: [[tie]] tables, each between = [a, b] and a kind")
            ties = []
        for i, t in enumerate(ties):
            if not isinstance(t, Mapping):
                self.add(f"tie[{i}]: a table, between = [a, b] and a kind")
                continue
            self.keys(t, TIE, f"tie[{i}]")
            pair = t.get("between")
            if not (isinstance(pair, list) and len(pair) == 2 and pair[0] != pair[1]):
                self.add(f"tie[{i}]: between = [two different npcs]")
            else:
                for x in pair:
                    if x not in self.npcs:
                        self.add(f"tie[{i}]: {x!r} is not an npc{near(x, self.npcs)}")
            if not isinstance(along, Mapping) or t.get("kind") not in along:
                self.add(f"tie[{i}]: kind {t.get('kind')!r} is not in [gossip] along"
                         f"{near(t.get('kind'), along if isinstance(along, Mapping) else ())}")

    def claims(self) -> None:
        c = self.d.get("claims", {})
        if not isinstance(c, Mapping):
            return
        self.keys(c, CLAIMS, "claims")
        one_actor = c.get("one_actor", [])
        if not isinstance(one_actor, list) or not all(isinstance(x, str) for x in one_actor):
            self.add("claims.one_actor: a list of predicates")
        else:
            for i, p in enumerate(one_actor):
                self.pred(f"claims.one_actor[{i}]", p)
        if not _whole(c.get("caught", 0)) or c.get("caught", 0) < 0:
            self.add("claims.caught: how far trust falls, a whole number from 0")
        if not _whole(c.get("first_hand", 0)) or c.get("first_hand", 0) < 0:
            self.add("claims.first_hand: how much more a teller who saw it counts, a whole number from 0")
        if "description" in c:
            self.text("claims.description", c["description"])

    def words(self) -> None:
        words = self.d.get("words", {})
        if not isinstance(words, Mapping):
            return
        self.keys(words, WORDS, "words")
        for k, s in self.table("words.claims", words["claims"]).items() if "claims" in words else ():
            self.template(f"words.claims.{k}", s, CLAIM_FIELDS)
        for k, s in self.table("words.events", words["events"]).items() if "events" in words else ():
            self.template(f"words.events.{k}", s, EVENT_FIELDS)
        actions = self.d.get("actions", {})
        for k, s in actions.items() if isinstance(actions, Mapping) else ():
            self.template(f"actions.{k}", s, ACTION_FIELDS)

    def intents(self) -> None:
        intents = self.d.get("intents", {})
        if not isinstance(intents, Mapping):
            return
        for verb, t in intents.items():
            if not isinstance(t, Mapping):
                continue  # declared_intents reports it
            self.keys(t, INTENT, f"intents.{verb}")
            args = t.get("args", {})
            for name, spec in args.items() if isinstance(args, Mapping) else ():
                if isinstance(spec, Mapping):
                    self.keys(spec, ARG, f"intents.{verb}.args.{name}")
        try:
            declared_intents(self.d)
        except DefinitionError as e:
            self.add(str(e))


def examine(data: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """A game file's data, checked: its problems (every mistake, each naming its entry; none if it's sound), and its
    notes (what a sound file allows but is likely a slip, such as an action with no line, done in silence)."""
    c = _Check(data)
    c.check()
    return list(dict.fromkeys(c.out)), list(dict.fromkeys(c.notes))


def problems(data: Mapping[str, Any]) -> list[str]:
    return examine(data)[0]


def refuse(found: list[str]) -> DefinitionError:
    """The error for a file with `found` problems: all of them, one a line, the first first."""
    e = DefinitionError("\n".join(found))
    e.problems = found  # type: ignore[attr-defined]
    return e
