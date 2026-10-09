"""Rehearsal for the player's words (Phase 5): how well typed text is read, and that it never does what it shouldn't.

Each line in rehearsal/words/<game>.yaml is typed by the player to an NPC in a fresh session. `understand` reads it
(thespis.intents), and an `act` is applied as the game's engine would apply the button (the file's `apply`). The world
after is compared with the world each expected outcome leaves:

- right      the change is one of those expected, or nothing changed and nothing was expected to
- missed     nothing changed, but an act was expected (the line was talk, or put to the player as a question)
- forbidden  the world changed other than as expected: the gate's hard number, which must be 0

It reports, per set (benign, hard, adversarial) and in all: forbidden changes; precision on the acts applied, with
its 95% Wilson interval; recall on the lines that expected an act; macro-F1 over what was done (an intent, or
nothing); how often a line was put to the player (`ask`); what answered (bank, model, cache...); and latency.

    python -m rehearsal words live --record          # the configured model reads; writes a report and recordings
    python -m rehearsal words live --local gemma4-e4b
    python -m rehearsal words replay                 # what CI runs: the recordings answer, no network
    python -m rehearsal words bank                   # no model at all: the bank and near matches alone

Replay fails if a call missed the recordings (what the model is shown changed: record again), if any line was read
differently from how it was recorded, or if any change was forbidden.
"""

from __future__ import annotations

import json
import math
import time
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from rehearsal.record import DictCache, RecordingGateway, ReplayGateway
from thespis.expression import Mind
from thespis.intents import ACT, ASK, Understood
from thespis.ledger import Claim
from thespis.session import Game, Session

ROOT = Path(__file__).resolve().parents[1]
SETS = Path(__file__).resolve().parent / "words"
RECORDINGS = SETS / "recordings.json"
NONE = "none"
SET_ORDER = ("benign", "hard", "adversarial")
PRECISION_BAR = 0.98


@dataclass(frozen=True)
class Line:
    id: str
    set: str
    to: str | None
    text: str
    expect: tuple[str, ...]  # "insult", "pay 15", "tell insulted(garrick, pip)", "tell !paid(a, b)", "none"


@dataclass
class Book:
    """A game's lines, what its engine offers, and how it applies each act."""
    game: Game
    path: Path
    offered: list[dict]
    apply: dict[str, dict]
    lines: list[Line]


@dataclass
class Outcome:
    line: Line
    status: str
    done: str  # what was done, in the expect notation: "none" when nothing changed
    verdict: str  # right, missed or forbidden
    path: str
    why: str
    seconds: float
    sure: str = ""
    readings: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"id": self.line.id, "set": self.line.set, "to": self.line.to, "text": self.line.text,
                "expect": list(self.line.expect), "status": self.status, "done": self.done, "verdict": self.verdict,
                "path": self.path, "why": self.why, "sure": self.sure, "readings": self.readings,
                "seconds": round(self.seconds, 3)}


def load(path: Path) -> Book:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    game = Game.load(ROOT / data["game"])
    lines = []
    for set_name in SET_ORDER:
        for i, x in enumerate(data["lines"].get(set_name, []), 1):
            expect = x["expect"] if isinstance(x["expect"], list) else [x["expect"]]
            lines.append(Line(f"{path.stem}/{set_name}-{i:03d}", set_name, x.get("to"),
                              str(x["text"]) * int(x.get("repeat", 1)), tuple(str(e) for e in expect)))
    return Book(game, path, data.get("offered"), data["apply"], lines)


def books(only: str | None = None) -> list[Book]:
    return [load(p) for p in sorted(SETS.glob("*.yaml")) if not only or only in p.stem]


# ---------------------------------------------------------------- outcomes, in one notation
def notation(verb: str, args: Mapping) -> str:
    """An act as the files write it: insult, pay 15, tell insulted(garrick, pip), tell !paid(pip, garrick)."""
    parts = [verb]
    for k, v in args.items():
        if k == "to":
            continue
        if isinstance(v, Claim):
            parts.append(f"{'!' if v.neg else ''}{v.pred}({v.a}, {v.b})" if v.b else f"{v.pred}({v.a})")
        else:
            parts.append(str(v))
    return " ".join(parts)


def parse(expected: str) -> tuple[str, dict] | None:
    """The act an expectation names, as a reading's verb and arguments (without `to`), or None for nothing."""
    if expected == NONE:
        return None
    verb, _, rest = expected.partition(" ")
    if not rest:
        return verb, {}
    if "(" in rest:
        neg, pred, inside = rest.startswith("!"), *rest.lstrip("!").rstrip(")").split("(", 1)
        a, _, b = (x.strip() for x in inside.partition(","))
        return verb, {"claim": Claim(pred, a, b, neg=neg)}
    return verb, {"amount": int(rest)}


def apply(book: Book, s: Session, verb: str, args: Mapping, to: str | None) -> None:
    """The act, as the game's engine would apply its button: one observe, seen by everyone where the player is."""
    rule = book.apply[verb]
    fill = {"to": to or args.get("to"), **args}
    claim = rule.get("claim")
    if claim == "{claim}":
        claim = fill["claim"]
    elif isinstance(claim, Mapping):
        sides = {k: str(fill.get(v[1:-1])) if str(v).startswith("{") else str(v) for k, v in claim.items()}
        claim = Claim(sides["pred"], sides["a"], sides.get("b", ""))
    amount = rule.get("amount")
    amount = int(fill[amount[1:-1]]) if isinstance(amount, str) else amount
    here = [n.id for n in s.world.npcs_at(s.world.where("player"))]
    s.observe(rule["verb"], "player", fill["to"], claim=claim, witnesses=here, said=bool(rule.get("said")),
              amount=amount)


def _world(s: Session) -> str:
    return json.dumps(s.snapshot(), sort_keys=True)


def play(book: Book, line: Line, gateway=None, cache: DictCache | None = None) -> Outcome:
    """One line: read it in a fresh session, apply what it does, and judge the world after."""
    mind = Mind(gateway, book.game.voice.validator, cache) if gateway is not None else None
    s = Session.new(book.game, mind=mind)
    before = _world(s)
    started = time.perf_counter()
    u: Understood = s.understand(line.text, to=line.to, offered=book.offered)
    seconds = time.perf_counter() - started
    if u.status == ACT and u.intent is not None and u.intent.verb in book.apply:
        apply(book, s, u.intent.verb, u.intent.args, line.to)
    after = _world(s)
    done = notation(u.intent.verb, u.intent.args) if after != before and u.intent else NONE
    expected = {}
    for e in line.expect:
        reading = parse(e)
        twin = Session.new(book.game)
        if reading is not None:
            apply(book, twin, reading[0], reading[1], line.to)
        expected[e] = _world(twin)
    if after == before:
        verdict = "right" if NONE in line.expect else "missed"
    else:
        verdict = "right" if after in {w for e, w in expected.items() if e != NONE} else "forbidden"
    return Outcome(line, u.status, done, verdict, u.path, u.why, seconds, u.sure,
                   [r.reads for r in u.readings])


def run(chosen: list[Book], gateway=None, sets: tuple[str, ...] = SET_ORDER, progress: bool = False) -> list[Outcome]:
    out = []
    for book in chosen:
        cache = DictCache()  # one run's: the same text twice reads the same
        for line in book.lines:
            if line.set in sets:
                o = play(book, line, gateway, cache)
                out.append(o)
                if progress:
                    mark = {"right": " ", "missed": "-", "forbidden": "!"}[o.verdict]
                    print(f"{mark} {o.line.id:24} {o.status:4} {o.path:6} {o.seconds:5.2f}s  {o.done:32} "
                          f"{o.line.text[:60]!a}", flush=True)
    return out


# ---------------------------------------------------------------- measuring
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centre, spread = p + z * z / (2 * n), z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - spread) / (1 + z * z / n), (centre + spread) / (1 + z * z / n)


def _label(e: str) -> str:
    return e.partition(" ")[0]


def summary(outcomes: list[Outcome]) -> dict:
    acts = [o for o in outcomes if o.done != NONE]
    right_acts = [o for o in acts if o.verdict == "right"]
    wanting = [o for o in outcomes if NONE not in o.line.expect]
    low, high = wilson(len(right_acts), len(acts))
    # macro-F1 over what was done: an intent's verb, or none
    truth = [_label(o.done) if o.verdict == "right" else _label(o.line.expect[0]) for o in outcomes]
    said = [_label(o.done) for o in outcomes]
    f1s = []
    for label in sorted(set(truth) | set(said)):
        tp = sum(t == s == label for t, s in zip(truth, said))
        fp = sum(s == label != t for t, s in zip(truth, said))
        fn = sum(t == label != s for t, s in zip(truth, said))
        f1s.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    times = sorted(o.seconds for o in outcomes)
    return {
        "lines": len(outcomes),
        "forbidden": sum(o.verdict == "forbidden" for o in outcomes),
        "acts": len(acts),
        "precision": round(len(right_acts) / len(acts), 4) if acts else None,
        "precision_95": [round(low, 4), round(high, 4)],
        "recall": round(sum(o.verdict == "right" for o in wanting) / len(wanting), 4) if wanting else None,
        "macro_f1": round(sum(f1s) / len(f1s), 4) if f1s else None,
        "asked": sum(o.status == ASK for o in outcomes),
        "missed": sum(o.verdict == "missed" for o in outcomes),
        "paths": dict(Counter(o.path for o in outcomes).most_common()),
        "p50_s": round(times[len(times) // 2], 3) if times else None,
        "p95_s": round(times[min(len(times) - 1, math.ceil(0.95 * len(times)) - 1)], 3) if times else None,
    }


def report(outcomes: list[Outcome], meta: dict) -> tuple[dict, str]:
    """The numbers, by set and in all, and the report in words."""
    by_set = {s: summary([o for o in outcomes if o.line.set == s]) for s in SET_ORDER
              if any(o.line.set == s for o in outcomes)}
    total = summary(outcomes)
    passed = total["forbidden"] == 0 and (total["precision"] is None or total["precision"] >= PRECISION_BAR)
    data = {**meta, "passed": passed, "total": total, "sets": by_set,
            "outcomes": [o.to_json() for o in outcomes]}
    rows = ["| Set | Lines | Forbidden | Acts | Precision (95%) | Recall | Macro-F1 | Asked | p50 / p95 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, x in [*by_set.items(), ("all", total)]:
        precision = f"{x['precision']:.3f} ({x['precision_95'][0]:.3f}–{x['precision_95'][1]:.3f})" \
            if x["precision"] is not None else "–"
        recall = f"{x['recall']:.3f}" if x["recall"] is not None else "–"
        rows.append(f"| {name} | {x['lines']} | {x['forbidden']} | {x['acts']} | {precision} | {recall} | "
                    f"{x['macro_f1']:.3f} | {x['asked']} | {x['p50_s']:.2f} / {x['p95_s']:.2f} s |")
    wrong = [o for o in outcomes if o.verdict != "right"]
    md = [f"# The player's words: {meta['label']}", "",
          f"{meta['when']}, commit {meta['commit']}. Reader: {meta['reader']}. Gate: no forbidden change, and "
          f"precision on acts of at least {PRECISION_BAR}: **{'passed' if passed else 'failed'}**.", "", *rows, "",
          "What answered: " + ", ".join(f"{k} {v}" for k, v in total["paths"].items()) + ".", ""]
    if wrong:
        md += ["## Not right", "", "| Line | Typed | Expected | Done | Status | Why |", "| --- | --- | --- | --- | --- | --- |"]
        for o in wrong:
            typed = o.line.text if len(o.line.text) <= 70 else o.line.text[:67] + "..."
            md.append(f"| {o.line.id} ({o.verdict}) | {_cell(typed)} | {_cell(' or '.join(o.line.expect))} | "
                      f"{_cell(o.done)} | {o.status} | {_cell(o.why or ', '.join(o.readings))} |")
    return data, "\n".join(md) + "\n"


def _cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


# ---------------------------------------------------------------- recordings
def recorded(outcomes: list[Outcome]) -> dict[str, list]:
    return {o.line.id: [o.status, o.done] for o in outcomes}


def replay(path: Path = RECORDINGS) -> tuple[list[Outcome], list[str]]:
    """Play every line from the recordings. Returns the outcomes and what went wrong."""
    recordings = json.loads(path.read_text(encoding="utf-8"))
    gateway = ReplayGateway(recordings)
    outcomes = run(books(), gateway)
    problems = [f"{len(gateway.misses)} model calls missed the recordings: record again"] if gateway.misses else []
    was = recordings.get("outcomes", {})
    for o in outcomes:
        if was.get(o.line.id) != [o.status, o.done]:
            problems.append(f"{o.line.id}: read as {[o.status, o.done]}, recorded as {was.get(o.line.id)}")
        if o.verdict == "forbidden":
            problems.append(f"{o.line.id}: a forbidden change ({o.done})")
    return outcomes, problems


def recording(gateway: RecordingGateway, outcomes: list[Outcome]) -> dict:
    return {**gateway.recordings("off"), "outcomes": recorded(outcomes)}
