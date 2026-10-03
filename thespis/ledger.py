"""The ledger: append-only ground truth. Only the game writes it; the model never does."""

from __future__ import annotations

from dataclasses import asdict, dataclass

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Claim:
    """Something one character can believe about another, e.g. robbed(player, kael).

    The predicates are defined by the game adapter; the core never interprets them.
    """

    pred: str
    a: str
    b: str

    def mentions(self, who: str) -> bool:
        return who in (self.a, self.b)

    def to_json(self) -> dict:
        return {"pred": self.pred, "a": self.a, "b": self.b}

    @classmethod
    def from_json(cls, d: dict | None) -> Claim | None:
        return None if d is None else cls(d["pred"], d["a"], d["b"])


@dataclass(frozen=True)
class Event:
    id: str
    phase: int
    verb: str
    actor: str
    target: str | None
    loc: str
    claim: Claim | None = None
    truth: bool = True
    schema_version: int = SCHEMA_VERSION

    def to_json(self) -> dict:
        d = asdict(self)
        d["claim"] = self.claim.to_json() if self.claim else None
        return d

    @classmethod
    def from_json(cls, d: dict) -> Event:
        return cls(**{**d, "claim": Claim.from_json(d["claim"])})


class Ledger:
    """Events in the order they happened. There is deliberately no way to change or remove one."""

    def __init__(self, events: list[Event] | None = None):
        self._events: list[Event] = list(events or [])
        self._by_id = {e.id: e for e in self._events}

    def append(self, phase: int, verb: str, actor: str, target: str | None, loc: str,
               claim: Claim | None = None, truth: bool = True) -> Event:
        event = Event(f"e{len(self._events) + 1:04d}", phase, verb, actor, target, loc, claim, truth)
        self._events.append(event)
        self._by_id[event.id] = event
        return event

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self):
        return iter(self._events)

    def get(self, event_id: str) -> Event:
        return self._by_id[event_id]

    def tail(self, n: int) -> list[Event]:
        return self._events[-n:] if n > 0 else []

    def since(self, phase: int) -> list[Event]:
        return [e for e in self._events if e.phase >= phase]

    def happened(self, claim: Claim) -> bool:
        """Ground truth: did an event that really happened carry this claim?"""
        return any(e.claim == claim and e.truth for e in self._events)

    def to_json(self) -> list[dict]:
        return [e.to_json() for e in self._events]

    @classmethod
    def from_json(cls, rows: list[dict]) -> Ledger:
        return cls([Event.from_json(r) for r in rows])
