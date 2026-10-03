"""The docs/api.md shapes: what the client sees of a world, a tick, and the narrator's digest."""

from __future__ import annotations

from games.crypt_road import content as C
from games.crypt_road import words
from games.crypt_road.rules import ActResult, Tick
from thespis.ledger import Event
from thespis.world import World

TAIL = 50  # covers a whole demo run
DIGEST_EVENTS = 12  # the narrator sees at most this many events


def state_view(w: World) -> dict:
    return {
        "seed": w.seed, "phase": w.phase, "day": w.phase // 4 + 1, "phase_name": C.PHASES[w.phase % 4],
        "status": w.status, "brain": w.brain_mode, "pending": w.pending, "ended_at": w.ended_at,
        "player": dict(w.player),
        "npcs": [{"id": n.id, "loc": n.loc, "last_seen": n.last_seen, "drives": dict(n.drives),
                  "trust_in": dict(n.trust_in), "frozen_until": n.frozen_until} for n in w.npcs.values()],
        "beliefs": [{**b.to_json(), "conf": b.conf, "truth": w.ledger.happened(b.claim)} for b in w.beliefs.all()],
        "ledger_tail": [e.to_json() for e in w.ledger.tail(TAIL)],
        "decisions_tail": [d.to_json() for d in w.decisions.tail(TAIL)],
    }


def tick_view(t: Tick | None) -> dict | None:
    if t is None:
        return None
    return {"moves": t.moves, "decisions": [d.to_json() for d in t.decisions],
            "events": [e.to_json() for e in t.events]}


def act_view(result: ActResult, w: World) -> dict:
    return {
        "events": [e.to_json() for e in result.events],
        "replies": result.replies,
        "tick": tick_view(result.tick),
        "epilogue": [tick_view(t) for t in result.epilogue] if result.epilogue else None,
        "state": state_view(w),
    }


# ---------------------------------------------------------------- the code-built digest (#19 adds the model's)
def _text(events: list[Event]) -> str:
    return " ".join(words.sentence(e) for e in events)


def digest_view(w: World, since: int) -> dict:
    """What happened since the given phase, from the ledger alone, plus the epilogue once the race is over."""
    events = list(w.ledger)
    end = next((i for i, e in enumerate(events) if e.verb == "take_relic"), None)
    race, after = (events, []) if end is None else (events[: end + 1], events[end + 1:])
    recent = [e for e in race if e.phase >= since][-DIGEST_EVENTS:]
    return {
        "text": _text(recent),
        "hook": None,  # story-sifting hooks arrive in #19
        "cites": [e.id for e in recent],
        "epilogue": _text(after[-DIGEST_EVENTS:]) if end is not None else None,
    }
