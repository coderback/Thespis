"""What Rehearsal plays: every scripted route of both games, and the adversarial lines, in-process.

- The Crypt Road: every route in tools/routes.py on seeds 1 and 4 (the duel won, the duel lost). As in the harness,
  the player puts a question of its own to everyone nearby once the ledger has something in it, so every run asks
  the model something new; the questions come from a fixed seed, so every rehearsal asks the same ones. As the
  client does, it asks the Dungeon Master for a digest after every tick and once more at the end.
- The manor: its solve, the client's Watch route, two wrong accusations, and an explorer who asks everyone
  everything (the paper's five, tobi/paper-m1 research/scenarios.py).
- Adversarial: the first PER_CATEGORY lines of each category in adversarial.yaml, said to everyone present at two
  moments: the tavern after the insult, and the guard post after Kael has reported the player.

Scenarios depend only on these settings, never on the model, so two rehearsals play the same moments and can be
compared line for line.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from games.crypt_road import rules as cr_rules
from games.crypt_road import views as cr_views
from games.crypt_road import voice as cr_voice
from games.crypt_road.content import new_world as cr_world
from games.manor import rules as mn_rules
from games.manor.content import new_world as mn_world
from thespis.expression import Mind, Observer, ReplyCache
from thespis.gateway import ModelGateway
from thespis.world import PLAYING, World
from tools.harness import fresh_questions
from tools.manor_solve import SOLVE, WATCH
from tools.routes import ROUTES, ApiError, play, provoke, seed_for

SEEDS = (1, 4)  # the duel won and the duel lost: the only two stories the dice tell (tools/harness.py)
QUESTION_SEED = 2026
PER_CATEGORY = 2
ADVERSARIAL = Path(__file__).with_name("adversarial.yaml")
MANOR_ROUTES = {
    "solve": SOLVE,
    "watch": WATCH,
    "accuse_early": [("accuse", "sable", None)],
    "accuse_pell": SOLVE[:-1] + [("accuse", "pell", None)],
    "explore": [("ask", "vane", "ring"), ("ask", "vane", "morning"), ("move", "kitchen", None),
                ("ask", "sable", "ring"), ("ask", "sable", "morning"), ("move", "study", None),
                ("ask", "pell", "ring"), ("ask", "pell", "morning"), ("move", "hall", None),
                ("request_questioning", "sable", None), ("request_questioning", "pell", None),
                ("ask", "vane", "morning"), ("accuse", "sable", None)],
}


@dataclass
class Stage:
    """Where scenarios play: in-process, sharing one gateway and one reply cache, as the host does.

    `world` is the world being played, so an observer can see it as each line is said. `acts` keeps each action's
    time and how many model calls it made; `tellings` keeps each digest's source and text.
    """

    gateway: ModelGateway | None
    cache: ReplyCache | None = None
    observer: Observer | None = None
    brain: str = "model"
    world: World | None = None
    acts: list[tuple[float, int]] = field(default_factory=list)
    tellings: list[tuple[str, str]] = field(default_factory=list)

    def crypt_road(self, seed: int, question: str | None = None) -> CryptRoad:
        return CryptRoad(self, seed, question)

    def manor(self) -> Manor:
        return Manor(self)


class CryptRoad:
    """tools.routes.Session's interface (act, state, allowed) on a World in-process."""

    def __init__(self, stage: Stage, seed: int, question: str | None = None):
        self.stage, self.question = stage, question
        self.w = cr_world(seed)
        self.w.brain_mode = stage.brain
        stage.world = self.w

    def act(self, verb: str, target: str | None = None, **fields) -> dict:
        phase, started = self.w.phase, time.perf_counter()
        try:
            result = cr_rules.act(self.w, verb, target, fields.get("claim"), fields.get("amount"), fields.get("text"),
                                  gateway=self.stage.gateway, cache=self.stage.cache, observer=self.stage.observer)
        except cr_rules.NotAllowed as e:
            raise ApiError(f"{verb} {target}: {e.reason}") from None
        self.stage.acts.append((time.perf_counter() - started, result.model_calls))
        out = cr_views.act_view(result, self.w)
        if result.tick is not None:
            self.digest(phase)
        if self.question and len(self.w.ledger) and self.w.status == PLAYING:
            question, self.question = self.question, None
            for (v, npc), option in self.allowed().items():
                if v == "talk" and option["enabled"]:
                    self.act("talk", npc, text=question)
        return out

    def digest(self, since: int) -> None:
        """The Dungeon Master's telling, as GET /digest gives it."""
        gateway = self.stage.gateway if self.w.brain_mode == "model" else None
        mind = Mind(gateway, cr_voice.VALIDATOR, self.stage.cache, observer=self.stage.observer)
        d = cr_views.digest_view(self.w, since, mind)
        self.stage.tellings.append((d["source"], d["text"]))
        if d["epilogue"] is not None:
            self.stage.tellings.append((d["epilogue_source"], d["epilogue"]))
        if mind.asked:
            self.w.counters["model_calls"] = self.w.counters.get("model_calls", 0) + mind.asked

    def state(self) -> dict:
        return cr_views.state_view(self.w)

    def allowed(self) -> dict:
        return {(v["verb"], v["target"]): v for v in cr_rules.allowed(self.w)}


class Manor:
    def __init__(self, stage: Stage):
        self.stage = stage
        self.w = mn_world()
        self.w.brain_mode = stage.brain
        stage.world = self.w

    def act(self, verb: str, target: str, topic: str | None = None) -> None:
        started = time.perf_counter()
        try:
            result = mn_rules.act(self.w, verb, target, topic, gateway=self.stage.gateway, cache=self.stage.cache,
                                  observer=self.stage.observer)
        except mn_rules.NotAllowed:
            return
        self.stage.acts.append((time.perf_counter() - started, result.model_calls))


@dataclass(frozen=True)
class Scenario:
    name: str
    game: str  # "crypt_road" or "manor"
    run: Callable[[Stage], World]


def _route(name: str, seed: int, question: str) -> Callable[[Stage], World]:
    def run(stage: Stage) -> World:
        s = stage.crypt_road(seed_for(name, seed), question)
        try:
            play(s, name)
        except ApiError:
            pass  # a route that can't go on (no purse after a lost duel) still counts what was said
        if s.w.ended_at is not None:
            s.digest(s.w.ended_at)  # the end card's telling
        return s.w
    return run


def _manor(steps: list) -> Callable[[Stage], World]:
    def run(stage: Stage) -> World:
        m = stage.manor()
        for verb, target, topic in steps:
            if m.w.status != PLAYING:
                break
            m.act(verb, target, topic)
        return m.w
    return run


def _adversarial(text: str, moment: str) -> Callable[[Stage], World]:
    def run(stage: Stage) -> World:
        s = stage.crypt_road(1)
        if moment == "tavern":
            s.act("insult", "kael")
        else:
            provoke(s)
            s.act("move")
            s.act("move")
        for (verb, npc), option in s.allowed().items():
            if verb == "talk" and option["enabled"]:
                s.act("talk", npc, text=text)
        return s.w
    return run


def adversarial_lines(path: Path = ADVERSARIAL, per_category: int = PER_CATEGORY) -> list[tuple[str, str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [(category, line) for category, lines in data.items() for line in lines[:per_category]]


def scenarios() -> list[Scenario]:
    runs = [(name, seed) for seed in SEEDS for name in ROUTES]
    questions = fresh_questions(len(runs), random.Random(QUESTION_SEED))
    out = [Scenario(f"crypt_road/{name}/{seed}", "crypt_road", _route(name, seed, q))
           for (name, seed), q in zip(runs, questions)]
    out += [Scenario(f"manor/{name}", "manor", _manor(steps)) for name, steps in MANOR_ROUTES.items()]
    counts: dict[str, int] = {}
    for category, text in adversarial_lines():
        counts[category] = counts.get(category, 0) + 1
        for moment in ("tavern", "guard_post"):
            out.append(Scenario(f"adversarial/{category}-{counts[category]}/{moment}", "crypt_road",
                                _adversarial(text, moment)))
    return out
