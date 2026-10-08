"""The ledger: append-only ground truth. Only the game writes it; the model never does."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import overload

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Claim:
    """Something one character can believe about the world, e.g. robbed(player, kael), or was_in(sable) in the study
    at mid-morning.

    The predicates are defined by the game adapter; the core never interprets them. `a` is who the claim is about and
    `b` whom or what it names, if anyone; `place` is where it held and `at` the phase it held, for a claim tied to a
    time and place. `neg` denies it: the claim says this never happened. Unset fields are left out of the JSON, so a
    claim with only a predicate and two names serialises as it always has.
    """

    pred: str
    a: str
    b: str = ""
    place: str | None = None
    at: int | None = None
    neg: bool = False

    def mentions(self, who: str) -> bool:
        return who in (self.a, self.b)

    def negated(self) -> Claim:
        """The same fact, denied (or affirmed, if this denies it)."""
        return replace(self, neg=not self.neg)

    def affirmed(self) -> Claim:
        """The fact this claim affirms or denies, affirmed."""
        return replace(self, neg=False) if self.neg else self

    def same_fact(self, other: Claim) -> bool:
        """Whether two claims are about the same fact, whether they affirm or deny it."""
        return self.affirmed() == other.affirmed()

    def label(self) -> str:
        """The claim as it reads in a report: robbed(odo, kael), was_in(sable, kitchen@1), not robbed(odo, kael)."""
        b = self.b or (f"{self.place}@{self.at}" if self.place is not None and self.at is not None else self.place or "")
        text = f"{self.pred}({self.a}, {b})"
        return f"not {text}" if self.neg else text

    def to_json(self) -> dict:
        d: dict = {"pred": self.pred, "a": self.a}
        if self.b:
            d["b"] = self.b
        if self.place is not None:
            d["place"] = self.place
        if self.at is not None:
            d["at"] = self.at
        if self.neg:
            d["neg"] = True
        return d

    @overload
    @classmethod
    def from_json(cls, d: dict) -> Claim: ...

    @overload
    @classmethod
    def from_json(cls, d: None) -> None: ...

    @classmethod
    def from_json(cls, d: dict | None) -> Claim | None:
        if d is None:
            return None
        return cls(d["pred"], d["a"], d.get("b", ""), d.get("place"), d.get("at"), bool(d.get("neg", False)))


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
    amount: int | None = None  # a quantity the event moved, such as coins paid; the game decides what it counts

    @property
    def claimed(self) -> Claim:
        """The claim this event carries, for a verb that always carries one, such as a theft or a statement."""
        if self.claim is None:
            raise ValueError(f"{self.id} ({self.verb}) carries no claim")
        return self.claim

    def to_json(self) -> dict:
        d = asdict(self)
        d["claim"] = self.claim.to_json() if self.claim else None
        if d["amount"] is None:
            del d["amount"]  # so events without one serialise exactly as they always have
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
               claim: Claim | None = None, truth: bool = True, amount: int | None = None) -> Event:
        event = Event(f"e{len(self._events) + 1:04d}", phase, verb, actor, target, loc, claim, truth, amount=amount)
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
        """Ground truth: did an event that really happened carry this claim? A denial is true when the fact it denies
        never happened."""
        fact = claim.affirmed()
        held = any(e.claim == fact and e.truth for e in self._events)
        return not held if claim.neg else held

    def to_json(self) -> list[dict]:
        return [e.to_json() for e in self._events]

    @classmethod
    def from_json(cls, rows: list[dict]) -> Ledger:
        return cls([Event.from_json(r) for r in rows])
