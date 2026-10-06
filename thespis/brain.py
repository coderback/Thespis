"""Brains choose an NPC's action from a list the game has already validated.

UtilityBrain is the fallback that keeps every demo route playable with no model. The LLM brain arrives in #17;
a learned policy can plug in here later.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


class Brain(Protocol):
    def choose(self, npc: str, allowed: Mapping[str, float], pack: dict | None = None) -> str:
        """Return one key of `allowed` (action id -> utility)."""
        ...


class UtilityBrain:
    def choose(self, npc: str, allowed: Mapping[str, float], pack: dict | None = None) -> str:
        # On a tie the first-listed action wins, matching tools/crypt_road_sim.py.
        return max(allowed, key=lambda action: allowed[action])
