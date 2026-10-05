"""The docs/api.md shapes: what the client sees of a world, a tick, and the narrator's digest."""

from __future__ import annotations

from games.crypt_road import content as C
from games.crypt_road import hooks, narrator, voice  # importing hooks registers the story patterns
from games.crypt_road.rules import ActResult, Tick, happened
from thespis.director import sift
from thespis.expression import Mind
from thespis.world import World

TAIL = 50  # covers a whole demo run
DIGEST_EVENTS = 12  # the narrator sees at most this many events


def state_view(w: World) -> dict:
    return {
        "seed": w.seed, "phase": w.phase, "day": w.phase // 4 + 1, "phase_name": C.PHASES[w.phase % 4],
        "status": w.status, "brain": w.brain_mode, "pending": w.pending, "ended_at": w.ended_at,
        "player": dict(w.player),
        "npcs": [{"id": n.id, "loc": n.loc, "last_seen": n.last_seen, "drives": dict(n.drives),
                  "trust_in": dict(n.trust_in), "frozen_until": n.frozen_until,
                  "persona": voice.persona_of(w, n.id), "persona_edited": "persona" in n.flags} for n in w.npcs.values()],
        "beliefs": [{**b.to_json(), "conf": b.conf, "truth": happened(w, b.claim)} for b in w.beliefs.all()],
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


# ---------------------------------------------------------------- the digest: told by the model, or built by code (#19)
def digest_view(w: World, since: int, mind: Mind | None = None) -> dict:
    """What happened since the given phase, plus the epilogue once the race is over, and the story's live thread.

    With a mind whose brain is on, the Dungeon Master (the model) tells it; otherwise, or if its telling fails the
    validator, the code builds it from the ledger. The hook is code-sifted from the ledger either way.
    """
    events = list(w.ledger)
    end = next((i for i, e in enumerate(events) if e.verb == "take_relic"), None)
    race, after = (events, []) if end is None else (events[: end + 1], events[end + 1:])
    recent = [e for e in race if e.phase >= since][-DIGEST_EVENTS:]
    epilogue_events = after[-DIGEST_EVENTS:] if end is not None else []
    hook = _hook(w, {e.id for e in recent + epilogue_events})
    text, cites, source = narrator.narrate(mind, recent)
    epilogue = epilogue_source = None
    if end is not None:
        epilogue, _, epilogue_source = narrator.narrate(mind, epilogue_events)
    return {"text": text, "hook": hook, "cites": cites, "epilogue": epilogue, "source": source,
            "epilogue_source": epilogue_source}


def _hook(w: World, window: set[str]) -> str | None:
    """The strongest story thread whose events fall in this window, if any."""
    live = {h.pattern: h for h in sift(w)}
    for name in hooks.PRIORITY:
        if name in live and set(live[name].cites) & window:
            return live[name].text
    return None
