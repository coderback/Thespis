"""Beliefs built from evidence. Each report is kept with its source, so a belief can be explained and corrected.

A belief may be false: whether its claim really happened lives only in the ledger, never here.

How sure an NPC is follows subjective logic (Jøsang, Subjective Logic, 2016). Each piece of evidence is an opinion
about the claim: a report with confidence c, from someone trusted that far, is belief c and uncertainty 1 - c; a
report against it (testimony that it never happened) is disbelief c instead. What the NPC saw itself (c = 1) is
certain. A belief's opinion is the cumulative fusion of its evidence, one piece per source and side, the strongest:
independent sources add up, a source repeating itself doesn't, and anything certain outweighs every report. Its
confidence is the opinion's projected probability with a base rate of 0, the belief mass, so one report of c gives
c, as it always has.

A belief is retracted when its disbelief outweighs its belief. Nothing flips it: evidence against lowers it, and
when trust in a source falls, `discredit` re-weighs everything that source said (the justifications of a truth
maintenance system, Doyle 1979), so the beliefs resting on it fall with it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace

from thespis.ledger import Claim

ACTIVE, RETRACTED = "active", "retracted"
PLACES = 4  # opinions are rounded to this many places, so the same evidence always serialises the same
LEGACY = "revised"  # the source of the evidence standing for a retraction saved before opinions (Belief.from_json)


@dataclass(frozen=True)
class Opinion:
    """Belief, disbelief and uncertainty, summing to 1."""

    b: float
    d: float
    u: float

    @classmethod
    def of(cls, conf: float, against: bool = False) -> Opinion:
        return cls(0.0, conf, 1.0 - conf) if against else cls(conf, 0.0, 1.0 - conf)

    def fuse(self, other: Opinion) -> Opinion:
        """Cumulative fusion: what two independent sources say together. Two certain opinions average."""
        if self.u == 0.0 and other.u == 0.0:
            return Opinion((self.b + other.b) / 2, (self.d + other.d) / 2, 0.0)
        k = self.u + other.u - self.u * other.u
        return Opinion((self.b * other.u + other.b * self.u) / k, (self.d * other.u + other.d * self.u) / k,
                       self.u * other.u / k)

    def rounded(self) -> Opinion:
        return Opinion(round(self.b, PLACES), round(self.d, PLACES), round(self.u, PLACES))

    def to_json(self) -> dict:
        return {"b": self.b, "d": self.d, "u": self.u}


VACUOUS = Opinion(0.0, 0.0, 1.0)  # no evidence either way


@dataclass(frozen=True)
class Evidence:
    source: str  # who it came from: "witnessed", "self", or the character who said it
    event: str  # the ledger event that delivered it
    phase: int
    conf: float
    against: bool = False  # it says the claim is false

    def to_json(self) -> dict:
        d = asdict(self)
        if not self.against:
            del d["against"]  # so evidence for a claim serialises exactly as it always has
        return d


def fuse(evidence: list[Evidence]) -> Opinion:
    """The opinion a body of evidence gives: the strongest piece per source and side, fused, in a fixed order."""
    strongest: dict[tuple[str, bool], float] = {}
    for e in evidence:
        key = (e.source, e.against)
        strongest[key] = max(strongest.get(key, 0.0), e.conf)
    out = VACUOUS
    for (_, against), conf in sorted(strongest.items()):
        out = out.fuse(Opinion.of(conf, against))
    return out.rounded()


@dataclass
class Belief:
    id: str
    npc: str
    claim: Claim
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def opinion(self) -> Opinion:
        return fuse(self.evidence)

    @property
    def conf(self) -> float:
        """How sure the NPC is: the opinion's projected probability, its belief."""
        return self.opinion.b

    @property
    def status(self) -> str:
        o = self.opinion
        return RETRACTED if o.d > o.b else ACTIVE

    @property
    def active(self) -> bool:
        return self.status == ACTIVE

    def to_json(self) -> dict:
        return {"id": self.id, "npc": self.npc, "claim": self.claim.to_json(), "status": self.status,
                "opinion": self.opinion.to_json(), "evidence": [e.to_json() for e in self.evidence]}

    @classmethod
    def from_json(cls, d: dict) -> Belief:
        evidence = [Evidence(**e) for e in d["evidence"]]
        belief = cls(d["id"], d["npc"], Claim.from_json(d["claim"]), evidence)
        if d.get("status") == RETRACTED and belief.active:
            # Saved before opinions, when testimony flipped a belief to retracted: keep it retracted, with certain
            # evidence against it standing for that decision.
            last = evidence[-1]
            belief.evidence.append(Evidence(LEGACY, last.event, last.phase, 1.0, against=True))
        return belief


def credence(trust: int) -> float:
    """How strongly a listener believes what it's told, from its trust in the teller (-5 to 5)."""
    if trust >= 2:
        return 0.9
    if trust >= 0:
        return 0.4
    return 0.2


class BeliefStore:
    """Every NPC's beliefs, one record per (npc, claim), in the order they were first formed."""

    def __init__(self, beliefs: list[Belief] | None = None):
        self._beliefs: list[Belief] = list(beliefs or [])
        self._index = {(b.npc, b.claim): b for b in self._beliefs}

    def add_evidence(self, npc: str, claim: Claim, conf: float, source: str, event: str,
                     phase: int, against: bool = False) -> tuple[Belief, bool]:
        """Store one report, for the claim or `against` it. Returns the belief and whether it is new.

        Evidence counts whatever the belief's status: a retracted belief can come back if enough evidence says so.
        """
        belief = self._index.get((npc, claim))
        is_new = belief is None
        if belief is None:
            belief = Belief(f"b{len(self._beliefs) + 1:04d}", npc, claim)
            self._beliefs.append(belief)
            self._index[(npc, claim)] = belief
        belief.evidence.append(Evidence(source, event, phase, conf, against))
        return belief, is_new

    def discredit(self, npc: str, source: str, conf: float) -> list[Belief]:
        """The NPC now trusts `source` only as far as `conf`: every piece of evidence it holds from them is capped
        there, so everything they said is re-weighed. Returns the beliefs whose opinion changed."""
        changed = []
        for belief in self.for_npc(npc):
            before = belief.opinion
            belief.evidence = [replace(e, conf=conf) if e.source == source and e.conf > conf else e
                               for e in belief.evidence]
            if belief.opinion != before:
                changed.append(belief)
        return changed

    def get(self, npc: str, claim: Claim) -> Belief | None:
        return self._index.get((npc, claim))

    def conf(self, npc: str, claim: Claim) -> float:
        """How sure the NPC is; 0 if it doesn't hold the belief or has retracted it."""
        belief = self.get(npc, claim)
        return belief.conf if belief and belief.active else 0.0

    def for_npc(self, npc: str) -> list[Belief]:
        return [b for b in self._beliefs if b.npc == npc]

    def all(self) -> list[Belief]:
        return list(self._beliefs)

    def to_json(self) -> list[dict]:
        return [b.to_json() for b in self._beliefs]

    @classmethod
    def from_json(cls, rows: list[dict]) -> BeliefStore:
        return cls([Belief.from_json(r) for r in rows])


FIRST_HAND = ("self", "witnessed")
SEEN = 6  # what an NPC saw itself counts as more than the most trust it can have in anyone (5): beyond their word


def credit(belief: Belief, trust: dict[str, int]) -> int:
    """How far the NPC trusts a belief's best source: what it saw itself beats anyone's word."""
    return max(SEEN if e.source in FIRST_HAND else trust.get(e.source, 0) for e in belief.evidence)


def reconcile(store: BeliefStore, npc: str, claim: Claim, trust: dict[str, int], phase: int,
              contradicts: Callable[[Claim, Claim], bool], penalty: int,
              credence: Callable[[int], float] = credence) -> list[Belief]:
    """Settle what `claim` contradicts among the NPC's beliefs. Of two claims that can't both be true, the one from the
    less trusted source loses: what the more trusted one said counts against it, and whoever told it the loser is
    trusted `penalty` less, so everything they said is re-weighed (`discredit`). A tie settles nothing. Returns the
    beliefs that ended retracted."""
    new = store.get(npc, claim)
    if new is None or not new.active:
        return []
    retracted = []
    for old in store.for_npc(npc):
        if old is new or not old.active or not contradicts(old.claim, new.claim):
            continue
        if credit(new, trust) > credit(old, trust):
            loser, winner = old, new
        elif credit(old, trust) > credit(new, trust):
            loser, winner = new, old
        else:
            continue
        sources = {e.source for e in loser.evidence if not e.against}
        best = max(winner.evidence, key=lambda e: e.conf)
        store.add_evidence(npc, loser.claim, best.conf, best.source, best.event, phase, against=True)
        for src in sorted(sources):
            if src in trust:
                trust[src] -= penalty
                store.discredit(npc, src, credence(trust[src]))
        if not loser.active:
            retracted.append(loser)
    return retracted
