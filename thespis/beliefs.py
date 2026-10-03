"""Beliefs built from evidence. Each report is kept with its source, so a belief can be explained and corrected.

A belief may be false: whether its claim really happened lives only in the ledger, never here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from thespis.ledger import Claim

ACTIVE, RETRACTED = "active", "retracted"


@dataclass(frozen=True)
class Evidence:
    source: str  # who it came from: "witnessed", "self", or the character who said it
    event: str  # the ledger event that delivered it
    phase: int
    conf: float


def combine(evidence: list[Evidence]) -> float:
    """How sure the evidence makes a belief. Maximum for now; noisy-OR can replace it later."""
    return max((e.conf for e in evidence), default=0.0)


@dataclass
class Belief:
    id: str
    npc: str
    claim: Claim
    status: str = ACTIVE
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def conf(self) -> float:
        return combine(self.evidence)

    @property
    def active(self) -> bool:
        return self.status == ACTIVE

    def to_json(self) -> dict:
        return {"id": self.id, "npc": self.npc, "claim": self.claim.to_json(), "status": self.status,
                "evidence": [asdict(e) for e in self.evidence]}

    @classmethod
    def from_json(cls, d: dict) -> Belief:
        return cls(d["id"], d["npc"], Claim.from_json(d["claim"]), d["status"],
                   [Evidence(**e) for e in d["evidence"]])


class BeliefStore:
    """Every NPC's beliefs, one record per (npc, claim), in the order they were first formed."""

    def __init__(self, beliefs: list[Belief] | None = None):
        self._beliefs: list[Belief] = list(beliefs or [])
        self._index = {(b.npc, b.claim): b for b in self._beliefs}

    def add_evidence(self, npc: str, claim: Claim, conf: float, source: str, event: str,
                     phase: int) -> tuple[Belief, bool]:
        """Store one report. Returns the belief and whether it is new.

        A retracted belief ignores new evidence: the NPC has already decided the claim is false.
        """
        belief = self._index.get((npc, claim))
        is_new = belief is None
        if is_new:
            belief = Belief(f"b{len(self._beliefs) + 1:04d}", npc, claim)
            self._beliefs.append(belief)
            self._index[(npc, claim)] = belief
        if belief.active:
            belief.evidence.append(Evidence(source, event, phase, conf))
        return belief, is_new

    def get(self, npc: str, claim: Claim) -> Belief | None:
        return self._index.get((npc, claim))

    def conf(self, npc: str, claim: Claim) -> float:
        """How sure the NPC is; 0 if it doesn't hold the belief or has retracted it."""
        belief = self.get(npc, claim)
        return belief.conf if belief and belief.active else 0.0

    def retract(self, belief: Belief) -> None:
        belief.status = RETRACTED

    def for_npc(self, npc: str) -> list[Belief]:
        return [b for b in self._beliefs if b.npc == npc]

    def all(self) -> list[Belief]:
        return list(self._beliefs)

    def to_json(self) -> list[dict]:
        return [b.to_json() for b in self._beliefs]

    @classmethod
    def from_json(cls, rows: list[dict]) -> BeliefStore:
        return cls([Belief.from_json(r) for r in rows])
