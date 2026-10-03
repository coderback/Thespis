"""The docs/api.md shapes: what the client sees of a world, a tick, and the narrator's digest."""

from __future__ import annotations

from games.crypt_road import content as C
from games.crypt_road.rules import ActResult, Tick
from thespis.ledger import Claim, Event
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
def _who(name: str | None, start: bool = False) -> str:
    if name == "player":
        return "You" if start else "you"
    return C.short_name(name) if name else ""


PRONOUNS = {"kael": ("he", "him"), "brenna": ("she", "her"), "odo": ("he", "him"), "mags": ("she", "her")}
VERBS = {"robbed": "robbed", "beat": "beat", "insulted": "insulted", "spared": "spared", "lied": "lied to"}


def _claim(c: Claim, speaker: str | None = None, negate: bool = False) -> str:
    """A claim as words. Whoever is telling it becomes he/him or she/her: "Kael told Brenna that you robbed him"."""
    def name(who: str, subject: bool) -> str:
        if who == speaker and who in PRONOUNS:
            return PRONOUNS[who][0 if subject else 1]
        return _who(who)
    verb = VERBS.get(c.pred, c.pred)
    return f"{name(c.a, True)} {'never ' if negate else ''}{verb} {name(c.b, False)}"


def sentence(e: Event) -> str:
    a, t = _who(e.actor, start=True), _who(e.target)
    where = C.STOP_NAMES.get(e.loc, e.loc)
    match e.verb:
        case "insult":
            return f"{a} insulted {t} at {where}."
        case "challenge":
            return f"{a} challenged {t} to a duel."
        case "beat":
            return f"{a} beat {t} in the duel."
        case "humiliate":
            return f"{a} humiliated {t} and took {'your' if e.target == 'player' else 'his'} purse."
        case "spare":
            return f"{a} spared {t}."
        case "bribe":
            return f"{a} paid {t} a fine."
        case "move":
            return f"{a} walked from {where} to {C.STOP_NAMES.get(e.target, e.target)}."
        case "block":
            return f"{_who(C.GUARD, start=True)} turned {_who(e.actor)} back at the gate."
        case "detain":
            return f"{a} detained {t}."
        case "release":
            return f"{a} released {t}."
        case "testify":
            return f"{a} told {t} that {_claim(e.claim, e.actor, negate=True)}."
        case "take_relic":
            return f"{a} took the relic."
        case _ if e.claim is not None:  # tell_claim, accuse, gossip
            return f"{a} told {t} that {_claim(e.claim, e.actor)}."
    return f"{a} {e.verb.replace('_', ' ')} {t}.".replace("  ", " ")


def _text(events: list[Event]) -> str:
    return " ".join(sentence(e) for e in events)


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
