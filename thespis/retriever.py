"""Retrievers pick what an NPC remembers for its state pack. Top five by confidence now; temporal later."""

from __future__ import annotations

from typing import Protocol

from thespis.beliefs import Belief, BeliefStore


class Retriever(Protocol):
    def beliefs(self, store: BeliefStore, npc: str) -> list[Belief]: ...


class TopKRetriever:
    def __init__(self, k: int = 5):
        self.k = k

    def beliefs(self, store: BeliefStore, npc: str) -> list[Belief]:
        """The NPC's strongest active beliefs, by confidence, then most recent evidence."""
        active = [b for b in store.for_npc(npc) if b.active]
        active.sort(key=lambda b: (b.conf, max(e.phase for e in b.evidence), b.id), reverse=True)
        return active[: self.k]
