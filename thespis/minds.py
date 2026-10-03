"""An NPC's state: where it is, its drives and its trust. What it believes lives in thespis.beliefs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class NPC:
    id: str
    loc: str
    drives: dict[str, int] = field(default_factory=dict)  # 0 to 10, e.g. grudge, fear
    trust_in: dict[str, int] = field(default_factory=dict)  # -5 to 5, per character
    frozen_until: int | None = None  # last phase it is held (inclusive), or None
    last_seen: dict | None = None  # {"loc", "phase"}: where the player last shared a stop with it
    flags: dict = field(default_factory=dict)  # game-specific state, e.g. actions already used

    def frozen(self, phase: int) -> bool:
        return self.frozen_until is not None and phase <= self.frozen_until

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> NPC:
        return cls(**d)
