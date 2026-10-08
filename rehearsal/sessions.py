"""Rehearsal for any game: a game file and a scenario file, played through the session API as an engine plays it.

    python -m rehearsal live --game examples/tavern/game.toml --scenarios examples/tavern/scenarios.toml

A scenario is a list of steps, each a session call (thespis.session) with its arguments, plus `wait` (seconds of
the player's pacing):

    [[scenario]]
    name = "insult_then_turn"
    steps = [
      { call = "observe", verb = "insult", actor = "player", target = "garrick", witnesses = ["wren"],
        claim = { pred = "insulted", a = "player", b = "garrick" } },
      { call = "update", npc = "garrick", nudge = { grudge = 4 } },
      { call = "decide", npc = "garrick", moment = "turn" },
      { call = "wait", seconds = 1.0 },
      { call = "tick" },
    ]

Lines are asked for as an engine asks: provisional, without waiting, and the scenario goes on. So besides what the
lines say (judged like any rehearsal's, with a vocabulary built from the game file), it measures what an engine sees:
how long a provisional line takes to settle, how many settled after the world had moved on (stale: right when asked,
perhaps not when shown), and how many were withdrawn because the session ended first.
"""

from __future__ import annotations

import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from rehearsal.record import Recorder
from thespis.expression import Mind, StatePack
from thespis.session import FINAL, WITHDRAWN, Game, Session

SETTLE = 20.0  # seconds to wait, at the end of a scenario, for lines still on their way
SPEAKS = ("decide", "react", "narrate")
CHANGES = ("observe", "update", "tick", "join")


@dataclass
class Scenario:
    name: str
    game: str
    steps: list[dict]
    seed: int = 0


def load(path: Path, game: Game) -> list[Scenario]:
    with path.open("rb") as f:
        data = tomllib.load(f)
    out = []
    for i, sc in enumerate(data.get("scenario", [])):
        steps = sc.get("steps")
        if not isinstance(steps, list) or not all(isinstance(s, dict) and "call" in s for s in steps):
            raise ValueError(f"scenario[{i}]: steps must be a list of tables, each with a call")
        bad = [s["call"] for s in steps if s["call"] not in (*SPEAKS, *CHANGES, "wait")]
        if bad:
            raise ValueError(f"scenario[{i}]: unknown call {bad[0]!r}")
        out.append(Scenario(f"{game.id}/{sc.get('name', i)}", game.id, steps, int(sc.get("seed", 0))))
    return out


class SessionRecorder(Recorder):
    """The Mind's observer for sessions. A provisional line's reply comes back on another thread, after the engine
    may have moved the world on, so each line's snapshot is the world as its pack was built, not as its reply
    arrived."""

    def __init__(self):
        super().__init__(world=lambda: None)
        self.session: Session | None = None
        self._at_pack: dict[int, str] = {}

    def saw_pack(self, pack: StatePack) -> None:
        s = self.session
        assert s is not None
        body = s.snapshot()
        sid = self._key(body)
        self.snapshots.setdefault(sid, body)
        self._at_pack[id(pack)] = sid

    def __call__(self, kind, pack, reply, used) -> None:
        before = len(self.samples)
        super().__call__(kind, pack, reply, used)
        if len(self.samples) > before:
            self.samples[-1]["snapshot"] = self._at_pack.pop(id(pack), None)

    @staticmethod
    def _key(body: dict) -> str:
        import hashlib
        import json
        return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()[:16]


@dataclass
class Played:
    lines: list[dict] = field(default_factory=list)  # one per line asked for: how it went, as an engine saw it
    acts: list[tuple[float, int]] = field(default_factory=list)  # decide: seconds to settle, whether a model spoke


def play(game: Game, gateway, chosen: list[Scenario], recorder: SessionRecorder, settle: float = SETTLE,
         pace: float = 1.0) -> Played:
    """Play `chosen` as an engine would. `pace` scales the scenarios' waits (0: no pauses, for a quick check)."""
    played = Played()
    for sc in chosen:
        s = Session.new(game, sc.seed, mind=Mind(gateway, game.voice.validator, observer=recorder))
        recorder.session, recorder.scenario, recorder.game = s, sc.name, game.id
        s.on_pack = recorder.saw_pack
        asked: list[tuple[str, str, float, str]] = []  # (line id, call, asked at, status when returned)
        changed: list[float] = []  # when the engine changed the world
        for step in sc.steps:
            args = {k: v for k, v in step.items() if k != "call"}
            call = step["call"]
            if call == "wait":
                time.sleep(float(args.get("seconds", 0)) * pace)
            elif call in CHANGES:
                getattr(s, call)(**args)
                changed.append(time.monotonic())
            else:
                at = time.monotonic()
                line = getattr(s, call)(**args, wait=False)
                if line.id is None:
                    played.lines.append({"scenario": sc.name, "call": call, "npc": line.npc, "silent": True})
                else:
                    asked.append((line.id, call, at, line.status))
        deadline = time.monotonic() + settle
        for lid, *_ in asked:
            s.line(lid, wait=max(0.0, deadline - time.monotonic()))
        s.close()
        for lid, call, at, first in asked:
            final = s.line(lid)
            settled = s.settled_at.get(lid)
            took = None if settled is None else settled - at
            played.lines.append({
                "scenario": sc.name, "call": call, "npc": final.npc, "first": first, "status": final.status,
                "source": final.source, "seconds": took, "silent": final.text is None,
                "stale": settled is not None and any(at < t < settled for t in changed)})
            if call == "decide" and took is not None:
                played.acts.append((took, int(final.source != "fallback" or first != FINAL)))
    return played


def measures(played: Played) -> dict:
    """What an engine saw of the lines: settled, stale, withdrawn, and how long provisional ones took."""
    from tools.harness import percentile

    asked = [x for x in played.lines if not x.get("silent") or "status" in x]
    provisional = [x for x in asked if x.get("first") == "provisional"]
    waits = sorted(x["seconds"] for x in provisional if x.get("seconds") is not None)
    return {"asked": len(asked), "provisional": len(provisional),
            "withdrawn": sum(x.get("status") == WITHDRAWN for x in asked),
            "stale": sum(bool(x.get("stale")) for x in provisional),
            "settle_p50": percentile(waits, 50) if waits else None,
            "settle_p95": percentile(waits, 95) if waits else None}
