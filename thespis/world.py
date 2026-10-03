"""A session's whole state. It serialises to JSON and back exactly, which is what makes restarts safe."""

from __future__ import annotations

from dataclasses import dataclass, field

from thespis.beliefs import BeliefStore
from thespis.decisions import DecisionLog
from thespis.ledger import Ledger
from thespis.minds import NPC

PLAYING, WON, LOST = "playing", "won", "lost"


@dataclass
class World:
    seed: int
    player: dict
    npcs: dict[str, NPC]
    phase: int = 0
    status: str = PLAYING
    pending: str | None = None  # e.g. a choice the player must make before anything else
    ended_at: int | None = None  # the phase the race ended
    brain_mode: str = "model"  # "model" or "fallback"
    counters: dict[str, int] = field(default_factory=dict)  # e.g. challenges so far, for seeded dice
    ledger: Ledger = field(default_factory=Ledger)
    beliefs: BeliefStore = field(default_factory=BeliefStore)
    decisions: DecisionLog = field(default_factory=DecisionLog)

    def npcs_at(self, loc: str) -> list[NPC]:
        return [n for n in self.npcs.values() if n.loc == loc]

    def to_json(self) -> dict:
        return {
            "seed": self.seed, "phase": self.phase, "status": self.status, "pending": self.pending,
            "ended_at": self.ended_at, "brain_mode": self.brain_mode, "counters": dict(self.counters),
            "player": dict(self.player),
            "npcs": [n.to_json() for n in self.npcs.values()],
            "ledger": self.ledger.to_json(),
            "beliefs": self.beliefs.to_json(),
            "decisions": self.decisions.to_json(),
        }

    @classmethod
    def from_json(cls, d: dict) -> World:
        return cls(
            seed=d["seed"], phase=d["phase"], status=d["status"], pending=d["pending"], ended_at=d["ended_at"],
            brain_mode=d["brain_mode"], counters=dict(d["counters"]), player=dict(d["player"]),
            npcs={n["id"]: NPC.from_json(n) for n in d["npcs"]},
            ledger=Ledger.from_json(d["ledger"]),
            beliefs=BeliefStore.from_json(d["beliefs"]),
            decisions=DecisionLog.from_json(d["decisions"]),
        )
