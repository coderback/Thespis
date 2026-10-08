"""Decision records: what an NPC could do, what it chose, what it said, and why. Every spoken line has one."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace

DECIDE, REACT = "decide", "react"


@dataclass(frozen=True)
class Decision:
    id: str
    kind: str  # "decide" (chose an action) or "react" (a line alone)
    npc: str
    phase: int
    trigger: str
    allowed: list[str] = field(default_factory=list)
    chosen: str | None = None
    line: str | None = None
    cites: list[str] = field(default_factory=list)
    reason: str = ""
    source: str = "fallback"  # "llm", "cache" or "fallback"
    asserted: str | None = None  # the ledger event of the claim its action stated, if any (thespis.deception)

    def to_json(self) -> dict:
        d = asdict(self)
        if d["asserted"] is None:
            del d["asserted"]  # so decisions that state nothing serialise exactly as they always have
        return d


class DecisionLog:
    def __init__(self, decisions: list[Decision] | None = None):
        self._decisions: list[Decision] = list(decisions or [])

    def record(self, kind: str, npc: str, phase: int, trigger: str, **fields) -> Decision:
        decision = Decision(f"d{len(self._decisions) + 1:04d}", kind, npc, phase, trigger, **fields)
        self._decisions.append(decision)
        return decision

    def settle(self, decision_id: str, **fields) -> Decision:
        """Replace a recorded decision's line once the model has answered for it (a provisional line made final)."""
        i = int(decision_id[1:]) - 1
        self._decisions[i] = settled = replace(self._decisions[i], **fields)
        return settled

    def __len__(self) -> int:
        return len(self._decisions)

    def __iter__(self):
        return iter(self._decisions)

    def tail(self, n: int) -> list[Decision]:
        return self._decisions[-n:] if n > 0 else []

    def to_json(self) -> list[dict]:
        return [d.to_json() for d in self._decisions]

    @classmethod
    def from_json(cls, rows: list[dict]) -> DecisionLog:
        return cls([Decision(**r) for r in rows])
