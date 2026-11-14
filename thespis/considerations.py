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
- `{at = place}`: where the NPC is. `{with = who}`: in the same place as `who`, an NPC or a player ("player" is where
  the player was seen).
- `{flag = f}` / `{not_flag = f}`: the NPC's flag is set, or isn't.
- `{believes = claim, min = c}`: the NPC holds the claim with at least `min` confidence, or actively at all.
- `{bound = name}`: a value the game passed when it asked is truthy. `{bound = name, is = v}`: it is exactly `v`, a
  string or a number. `{bound = name, gte | gt | lte | lt | eq = n}`: it is a number, and compares so.
- `{any = [...]}`, `{all = [...]}`, `{not = {...}}`.

Utility terms: a number, or `{drive = d, weight = 1, plus = 0, if = {...}}` (a drive times its weight plus a constant,
counted only when its `if` holds). Whole numbers stay whole, so a reason reads "go_to scores 6".

Every compiled condition can also say why it doesn't hold (`Check.why`: "grudge is 2, needs >= 4"), and every
utility how it added up (`Score.parts`), so `Choices.explain` can answer "why didn't she do X?".

Strings may name what the game binds when it asks (`do = "detain:{culprit}"`), and "self" in a claim is the NPC.
"""

from __future__ import annotations

import string
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from thespis.affordances import Affordance, options
from thespis.ledger import Claim
from thespis.minds import NPC
from thespis.voice import View
from thespis.world import World

Env = Mapping[str, object]  # what the game bound when it asked, and "self"
Test = Callable[[World, NPC, View, Env], bool]
Why = Callable[[World, NPC, View, Env], "str | None"]
Value = Callable[[World, NPC, View, Env], float]
Parts = Callable[[World, NPC, View, Env], "list[str]"]

COMPARE: dict[str, Callable[[float, float], bool]] = {
    "gte": lambda x, n: x >= n, "gt": lambda x, n: x > n, "lte": lambda x, n: x <= n, "lt": lambda x, n: x < n,
    "eq": lambda x, n: x == n}
SIGN = {"gte": ">=", "gt": ">", "lte": "<=", "lt": "<", "eq": "="}


class Check:
    """A compiled condition: call it to test it; `why` says why it doesn't hold now, or None when it does."""

    __slots__ = ("test", "why")

    def __init__(self, test: Test, why: Why):
        self.test, self.why = test, why

    def __call__(self, w: World, n: NPC, v: View, env: Env) -> bool:
        return self.test(w, n, v, env)


class Score:
    """A compiled utility (or one term of it): call it for its value; `parts` says how it adds up, a term each."""

    __slots__ = ("value", "parts")

    def __init__(self, value: Value, parts: Parts):
        self.value, self.parts = value, parts

    def __call__(self, w: World, n: NPC, v: View, env: Env) -> float:
        return self.value(w, n, v, env)


Cond = Check
Term = Score


def _num(x: float) -> str:
    return str(int(x)) if isinstance(x, float) and x.is_integer() else str(x)


def _show(c: object) -> str:
    """A condition as it was declared, inline: {flag = "accused"}."""
    if isinstance(c, Mapping):
        return "{" + ", ".join(f"{k} = {_show(v)}" for k, v in c.items()) + "}"
    if isinstance(c, list):
        return "[" + ", ".join(_show(x) for x in c) + "]"
    return f'"{c}"' if isinstance(c, str) else str(c).lower() if isinstance(c, bool) else str(c)


def _held(test: Test, why: Callable[[World, NPC, View, Env], str]) -> Check:
    """A check whose reason is only worked out when it fails."""
    return Check(test, lambda w, n, v, env: None if test(w, n, v, env) else why(w, n, v, env))


class DefinitionError(ValueError):
    """A choice declared wrongly, named by where it is."""


def _fill(s: str, env: Env) -> str:
    return str(env["self"]) if s == "self" else s.format_map(env) if "{" in s else s


def bound_names(x: object) -> set[str]:
    """The names a declaration leaves for the caller to bind: every "{name}" in its strings, at any depth."""
    if isinstance(x, str):
        try:
            return {f for _, f, _, _ in string.Formatter().parse(x) if f}
        except ValueError:
            return set()
    if isinstance(x, Mapping):
        return set().union(*(bound_names(v) for v in x.values())) if x else set()
    if isinstance(x, list | tuple):
        return set().union(*(bound_names(v) for v in x)) if x else set()
    return set()


def _people_names(x: object) -> set[str]:
    """The bound names a declaration uses as people: in `with`, and as a claim's `a` or `b`."""
    out: set[str] = set()
    if isinstance(x, Mapping):
        for k, v in x.items():
            if k == "with" or (k in ("a", "b") and isinstance(v, str)):
                out |= bound_names(v)
            else:
                out |= _people_names(v)
    elif isinstance(x, list | tuple):
        for v in x:
            out |= _people_names(v)
    return out


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
        signs = [(SIGN[k], _number(v, k)) for k, v in c.items() if k in COMPARE]
        return _held(lambda w, n, v, env: all(op(n.drives.get(d, 0), x) for op, x in ops),
                     lambda w, n, v, env: f"{d} is {_num(n.drives.get(d, 0))}, needs "
                                          + " and ".join(f"{s} {_num(x)}" for s, x in signs))
    if "bound" in c:
        _only(c, {"bound", "is", *COMPARE}, where)
        name, same = str(c["bound"]), c.get("is")
        if "is" in c and (isinstance(same, bool) or not isinstance(same, str | int | float)):
            raise DefinitionError(f"{where}.is: expected a string or a number, got {same!r}")
        ops = [(COMPARE[k], _number(v, f"{where}.{k}")) for k, v in c.items() if k in COMPARE]
        signs = [(SIGN[k], _number(v, k)) for k, v in c.items() if k in COMPARE]
        if len(c) == 1:
            return _held(lambda w, n, v, env: bool(env.get(name)),
                         lambda w, n, v, env: f"{name} is {env.get(name)!r}, not set")

        def bound(w: World, n: NPC, v: View, env: Env) -> bool:
            x = env.get(name)
            if "is" in c and (isinstance(x, bool) or x != same):
                return False
            if not ops:
                return True
            return isinstance(x, int | float) and not isinstance(x, bool) and all(op(x, k) for op, k in ops)

        def unbound(w: World, n: NPC, v: View, env: Env) -> str:
            x = env.get(name)
            if "is" in c and (isinstance(x, bool) or x != same):
                return f"{name} is {x!r}, needs {same!r}"
            if not isinstance(x, int | float) or isinstance(x, bool):
                return f"{name} is {x!r}, not a number"
            return f"{name} is {_num(x)}, needs " + " and ".join(f"{s} {_num(k)}" for s, k in signs)
        return _held(bound, unbound)
    key = next(iter(c))
    if len(c) != 1 and key != "believes":
        raise DefinitionError(f"{where}: one condition per table, got {', '.join(c)}")
    val = c[key]
    match key:
        case "at":
            place = str(val)
            return _held(lambda w, n, v, env: n.loc == _fill(place, env),
                         lambda w, n, v, env: f"{n.id} is at {n.loc or 'nowhere'}, not {_fill(place, env)}")
        case "with":
            who = str(val)

            def there(w: World, v: View, env: Env) -> tuple[str, str | None]:
                x = _fill(who, env)
                return x, v.player_at if x == "player" else w.where(x)

            def apart(w: World, n: NPC, v: View, env: Env) -> str:
                x, at = there(w, v, env)
                return f"{x} is at {at or 'nowhere known'}, {n.id} at {n.loc or 'nowhere'}"
            return _held(lambda w, n, v, env: n.loc == there(w, v, env)[1], apart)
        case "flag" | "not_flag":
            flag, want = str(val), key == "flag"
            return _held(lambda w, n, v, env: bool(n.flags.get(flag)) == want,
                         lambda w, n, v, env: f"flag {flag!r} is {'not set' if want else 'set'}")
        case "believes":
            _only(c, {"believes", "min"}, where)
            if not isinstance(val, Mapping) or "pred" not in val or "a" not in val:
                raise DefinitionError(f"{where}.believes: a claim needs pred and a")
            claim, least = dict(val), _number(c.get("min", 0), f"{where}.min")

            def of(env: Env) -> Claim:
                return Claim.from_json({k: _fill(x, env) if isinstance(x, str) else x for k, x in claim.items()})

            def believes(w: World, n: NPC, v: View, env: Env) -> bool:
                conf = w.beliefs.conf(n.id, of(env))  # 0 unless held and active
                return conf >= least if least else conf > 0

            def doubts(w: World, n: NPC, v: View, env: Env) -> str:
                held = of(env)
                b = w.beliefs.get(n.id, held)
                if b is None:
                    return f"doesn't know of {held.label()}"
                if not b.active:
                    return f"no longer believes {held.label()} (retracted)"
                return f"believes {held.label()} only at {_num(round(b.conf, 2))}, needs {_num(least)}"
            return _held(believes, doubts)
        case "any" | "all":
            if not isinstance(val, Sequence) or isinstance(val, str):
                raise DefinitionError(f"{where}.{key}: expected a list of conditions")
            parts = [condition(x, f"{where}.{key}[{i}]") for i, x in enumerate(val)]
            if key == "any":
                return _held(lambda w, n, v, env: any(p(w, n, v, env) for p in parts),
                             lambda w, n, v, env: "none of: " + "; ".join(
                                 str(p.why(w, n, v, env)) for p in parts))
            return _held(lambda w, n, v, env: all(p(w, n, v, env) for p in parts),
                         lambda w, n, v, env: "; ".join(r for p in parts if (r := p.why(w, n, v, env))))
        case "not":
            inner = condition(val, f"{where}.not")
            return _held(lambda w, n, v, env: not inner(w, n, v, env),
                         lambda w, n, v, env: f"{_show(val)} holds")
    raise DefinitionError(f"{where}: unknown condition {key!r}")


def conditions(cs: object, where: str) -> Cond:
    """A list of conditions, all of which must hold; `why` names every one that doesn't."""
    if cs is None:
        return Check(lambda w, n, v, env: True, lambda w, n, v, env: None)
    parts = [condition(x, f"{where}[{i}]") for i, x in enumerate(cs)] if isinstance(cs, list) else \
        [condition(cs, where)]
    return _held(lambda w, n, v, env: all(p(w, n, v, env) for p in parts),
                 lambda w, n, v, env: "; ".join(r for p in parts if (r := p.why(w, n, v, env))))


def term(t: object, where: str) -> Term:
    if not isinstance(t, Mapping):
        k = _number(t, where)
        return Score(lambda w, n, v, env: k, lambda w, n, v, env: [_num(k)])
    _only(t, {"drive", "weight", "plus", "if"}, where)
    d = str(t["drive"]) if "drive" in t else None
    weight, plus = _number(t.get("weight", 1), f"{where}.weight"), _number(t.get("plus", 0), f"{where}.plus")
    gate = conditions(t["if"], f"{where}.if") if "if" in t else None

    def value(w: World, n: NPC, v: View, env: Env) -> float:
        if gate and not gate(w, n, v, env):
            return 0
        return (n.drives.get(d, 0) * weight if d else 0) + plus

    def parts(w: World, n: NPC, v: View, env: Env) -> list[str]:
        """'anger 6', 'grudge 4 x 2 + 1 = 9', '3', or '0 (grudge only if: ...)' when its `if` doesn't hold."""
        if gate and (why := gate.why(w, n, v, env)):
            return [f"0 ({d or _num(plus)} only if: {why})"]
        if d is None:
            return [_num(plus)]
        text = f"{d} {_num(n.drives.get(d, 0))}" + (f" x {_num(weight)}" if weight != 1 else "") + \
            (f" + {_num(plus)}" if plus else "")
        return [f"{text} = {_num(value(w, n, v, env))}" if weight != 1 or plus else text]
    return Score(value, parts)


def utility(u: object, where: str) -> Term:
    terms = [term(x, f"{where}[{i}]") for i, x in enumerate(u)] if isinstance(u, list) else [term(u, where)]
    return Score(lambda w, n, v, env: sum(t(w, n, v, env) for t in terms),
                 lambda w, n, v, env: [p for t in terms for p in t.parts(w, n, v, env)])


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
    needs: frozenset[str] = frozenset()  # the names a caller must bind when it asks ("culprit"), "self" aside
    people: frozenset[str] = frozenset()  # those among them that name someone: an NPC or a player

    def bind(self, **bindings) -> tuple[Affordance, ...]:
        env = {**bindings, "self": self.npc}
        return tuple(Affordance(_fill(c.do, env), lambda w, n, v, c=c: c.utility(w, n, v, env),
                                lambda w, n, v, c=c: c.when(w, n, v, env)) for c in self.choices)

    def options(self, w: World, view: View, **bindings) -> dict[str, float]:
        """The actions open to the NPC now, with their utilities, in the order declared (thespis.affordances)."""
        return options(w, self.npc, self.bind(**bindings), view)

    def explain(self, w: World, view: View, **bindings) -> list[dict]:
        """Every choice, in the order declared: its action, whether it is open now, what keeps it shut if it isn't
        (`blocked`), and its utility with how it adds up (`terms`), open or not."""
        env, n = {**bindings, "self": self.npc}, w.npcs[self.npc]
        out = []
        for c in self.choices:
            why = c.when.why(w, n, view, env)
            entry: dict = {"do": _fill(c.do, env), "open": why is None}
            if why is not None:
                entry["blocked"] = why
            entry["utility"] = c.utility(w, n, view, env)
            entry["terms"] = c.utility.parts(w, n, view, env)
            out.append(entry)
        return out

    def asserts(self, **bindings) -> dict[str, Claim]:
        """What each action that states a claim states, by its id."""
        env = {**bindings, "self": self.npc}
        return {_fill(c.do, env): Claim.from_json({k: _fill(x, env) if isinstance(x, str) else x
                                                   for k, x in c.asserts.items()})
                for c in self.choices if c.asserts}


def compile_choices(npc: str, moment: str, declared: object, table: str = "npc") -> Choices:
    """Compile `[[npc.<npc>.choices.<moment>]]`, or a kind's (`table` "kind": whoever joins as one chooses by it).
    Raises DefinitionError naming the faulty entry."""
    where = f"{table}.{npc}.choices.{moment}"
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
    return Choices(npc, moment, tuple(out), frozenset(bound_names(declared) - {"self"}),
                   frozenset(_people_names(declared) - {"self"}))


def declared(data: Mapping) -> dict[tuple[str, str], Choices]:
    """Every NPC's choices in a cast's data, by (npc, moment), compiled and checked at once."""
    return {(npc, moment): compile_choices(npc, moment, cs)
            for npc, d in data.get("npc", {}).items() for moment, cs in d.get("choices", {}).items()}


def declared_kinds(data: Mapping) -> dict[tuple[str, str], Choices]:
    """Every kind's choices in a cast's data, by (kind, moment): each stands for whoever joins as that kind
    (`dataclasses.replace(choices, npc=...)`)."""
    return {(kind, moment): compile_choices(kind, moment, cs, "kind")
            for kind, d in data.get("kind", {}).items() for moment, cs in d.get("choices", {}).items()}
