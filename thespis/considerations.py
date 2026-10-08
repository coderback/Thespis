"""Considerations: an NPC's choices declared as data, in the Utility AI style, compiled to affordances.

A game declares, per NPC and per moment it chooses in, the actions it may take: when each is open (`when`, every
condition must hold) and how much it is worth (`utility`, a sum of terms). The highest utility wins; the first
declared wins a tie. Nothing here calls `eval`, so a definition is safe to load from any engine or any file.

    [[npc.kael.choices.tick]]
    do = "accuse:player"
    utility = [{drive = "grudge", plus = 3}]
    when = [{with = "brenna"}, {drive = "grudge", gte = 4}, {not_flag = "accused"},
            {any = [{believes = {pred = "robbed", a = "player", b = "self"}}]}]

Conditions:
- `{drive = d, gte | gt | lte | lt | eq = n}`: a drive, which is 0 when the NPC doesn't have it.
- `{at = place}`: where the NPC is. `{with = who}`: in the same place as `who` ("player" is where the player was seen).
- `{flag = f}` / `{not_flag = f}`: the NPC's flag is set, or isn't.
- `{believes = claim, min = c}`: the NPC holds the claim with at least `min` confidence, or actively at all.
- `{bound = name}`: a value the game passed when it asked is truthy.
- `{any = [...]}`, `{all = [...]}`, `{not = {...}}`.

Utility terms: a number, or `{drive = d, weight = 1, plus = 0, if = {...}}` (a drive times its weight plus a constant,
counted only when its `if` holds). Whole numbers stay whole, so a reason reads "go_to scores 6".

Strings may name what the game binds when it asks (`do = "detain:{culprit}"`), and "self" in a claim is the NPC.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from thespis.affordances import Affordance, options
from thespis.ledger import Claim
from thespis.minds import NPC
from thespis.voice import View
from thespis.world import World

Env = Mapping[str, object]  # what the game bound when it asked, and "self"
Cond = Callable[[World, NPC, View, Env], bool]
Term = Callable[[World, NPC, View, Env], float]

COMPARE: dict[str, Callable[[float, float], bool]] = {
    "gte": lambda x, n: x >= n, "gt": lambda x, n: x > n, "lte": lambda x, n: x <= n, "lt": lambda x, n: x < n,
    "eq": lambda x, n: x == n}


class DefinitionError(ValueError):
    """A choice declared wrongly, named by where it is."""


def _fill(s: str, env: Env) -> str:
    return str(env["self"]) if s == "self" else s.format_map(env) if "{" in s else s


def _number(v: object, where: str) -> float:
    if isinstance(v, bool) or not isinstance(v, int | float):
        raise DefinitionError(f"{where}: expected a number, got {v!r}")
    return v


def _only(d: Mapping, keys: set[str], where: str) -> None:
    if extra := set(d) - keys:
        raise DefinitionError(f"{where}: unknown key {', '.join(sorted(extra))}")


def condition(c: object, where: str) -> Cond:
    """Compile one condition, checking its shape now so a mistake fails at load, not in play."""
    if not isinstance(c, Mapping) or not c:
        raise DefinitionError(f"{where}: a condition is a table, got {c!r}")
    if "drive" in c:
        _only(c, {"drive", *COMPARE}, where)
        ops = [(COMPARE[k], _number(v, f"{where}.{k}")) for k, v in c.items() if k in COMPARE]
        if not ops:
            raise DefinitionError(f"{where}: a drive condition needs one of {', '.join(COMPARE)}")
        d = str(c["drive"])
        return lambda w, n, v, env: all(op(n.drives.get(d, 0), x) for op, x in ops)
    key = next(iter(c))
    if len(c) != 1 and key != "believes":
        raise DefinitionError(f"{where}: one condition per table, got {', '.join(c)}")
    val = c[key]
    match key:
        case "at":
            place = str(val)
            return lambda w, n, v, env: n.loc == _fill(place, env)
        case "with":
            who = str(val)
            return lambda w, n, v, env: n.loc == (v.player_at if (x := _fill(who, env)) == "player" else w.npcs[x].loc)
        case "flag" | "not_flag":
            flag, want = str(val), key == "flag"
            return lambda w, n, v, env: bool(n.flags.get(flag)) == want
        case "bound":
            name = str(val)
            return lambda w, n, v, env: bool(env.get(name))
        case "believes":
            _only(c, {"believes", "min"}, where)
            if not isinstance(val, Mapping) or "pred" not in val or "a" not in val:
                raise DefinitionError(f"{where}.believes: a claim needs pred and a")
            claim, least = dict(val), _number(c.get("min", 0), f"{where}.min")

            def believes(w: World, n: NPC, v: View, env: Env) -> bool:
                held = Claim.from_json({k: _fill(x, env) if isinstance(x, str) else x for k, x in claim.items()})
                conf = w.beliefs.conf(n.id, held)  # 0 unless held and active
                return conf >= least if least else conf > 0
            return believes
        case "any" | "all":
            if not isinstance(val, Sequence) or isinstance(val, str):
                raise DefinitionError(f"{where}.{key}: expected a list of conditions")
            parts = [condition(x, f"{where}.{key}[{i}]") for i, x in enumerate(val)]
            pick = any if key == "any" else all
            return lambda w, n, v, env: pick(p(w, n, v, env) for p in parts)
        case "not":
            inner = condition(val, f"{where}.not")
            return lambda w, n, v, env: not inner(w, n, v, env)
    raise DefinitionError(f"{where}: unknown condition {key!r}")


def conditions(cs: object, where: str) -> Cond:
    if cs is None:
        return lambda w, n, v, env: True
    parts = [condition(x, f"{where}[{i}]") for i, x in enumerate(cs)] if isinstance(cs, list) else \
        [condition(cs, where)]
    return lambda w, n, v, env: all(p(w, n, v, env) for p in parts)


def term(t: object, where: str) -> Term:
    if not isinstance(t, Mapping):
        k = _number(t, where)
        return lambda w, n, v, env: k
    _only(t, {"drive", "weight", "plus", "if"}, where)
    d = str(t["drive"]) if "drive" in t else None
    weight, plus = _number(t.get("weight", 1), f"{where}.weight"), _number(t.get("plus", 0), f"{where}.plus")
    gate = conditions(t["if"], f"{where}.if") if "if" in t else None

    def value(w: World, n: NPC, v: View, env: Env) -> float:
        if gate and not gate(w, n, v, env):
            return 0
        return (n.drives.get(d, 0) * weight if d else 0) + plus
    return value


def utility(u: object, where: str) -> Term:
    terms = [term(x, f"{where}[{i}]") for i, x in enumerate(u)] if isinstance(u, list) else [term(u, where)]
    return lambda w, n, v, env: sum(t(w, n, v, env) for t in terms)


@dataclass(frozen=True)
class Choice:
    do: str  # the action's id, which may name bindings: "detain:{culprit}"
    utility: Term
    when: Cond
    asserts: Mapping | None = None  # the claim the action states, if it states one


@dataclass(frozen=True)
class Choices:
    """One NPC's choices at one moment, compiled. `bind` gives the core's affordances for a call."""
    npc: str
    moment: str
    choices: tuple[Choice, ...]

    def bind(self, **bindings) -> tuple[Affordance, ...]:
        env = {**bindings, "self": self.npc}
        return tuple(Affordance(_fill(c.do, env), lambda w, n, v, c=c: c.utility(w, n, v, env),
                                lambda w, n, v, c=c: c.when(w, n, v, env)) for c in self.choices)

    def options(self, w: World, view: View, **bindings) -> dict[str, float]:
        """The actions open to the NPC now, with their utilities, in the order declared (thespis.affordances)."""
        return options(w, self.npc, self.bind(**bindings), view)

    def asserts(self, **bindings) -> dict[str, Claim]:
        """What each action that states a claim states, by its id."""
        env = {**bindings, "self": self.npc}
        return {_fill(c.do, env): Claim.from_json({k: _fill(x, env) if isinstance(x, str) else x
                                                   for k, x in c.asserts.items()})
                for c in self.choices if c.asserts}


def compile_choices(npc: str, moment: str, declared: object) -> Choices:
    """Compile `[[npc.<npc>.choices.<moment>]]`. Raises DefinitionError naming the faulty entry."""
    where = f"npc.{npc}.choices.{moment}"
    if not isinstance(declared, list) or not declared:
        raise DefinitionError(f"{where}: expected a list of choices")
    out = []
    for i, c in enumerate(declared):
        at = f"{where}[{i}]"
        if not isinstance(c, Mapping) or not isinstance(c.get("do"), str):
            raise DefinitionError(f"{at}: a choice needs do = \"<action>\"")
        _only(c, {"do", "utility", "when", "asserts"}, at)
        if "utility" not in c:
            raise DefinitionError(f"{at}: a choice needs a utility")
        asserts = c.get("asserts")
        if asserts is not None and (not isinstance(asserts, Mapping) or "pred" not in asserts or "a" not in asserts):
            raise DefinitionError(f"{at}.asserts: a claim needs pred and a")
        out.append(Choice(c["do"], utility(c["utility"], f"{at}.utility"), conditions(c.get("when"), f"{at}.when"),
                          asserts))
    ids = [c.do for c in out]
    if len(set(ids)) != len(ids):
        raise DefinitionError(f"{where}: an action is declared twice")
    return Choices(npc, moment, tuple(out))


def declared(data: Mapping) -> dict[tuple[str, str], Choices]:
    """Every NPC's choices in a cast's data, by (npc, moment), compiled and checked at once."""
    return {(npc, moment): compile_choices(npc, moment, cs)
            for npc, d in data.get("npc", {}).items() for moment, cs in d.get("choices", {}).items()}
