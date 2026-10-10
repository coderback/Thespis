"""What the manor's client sees: the state, with every belief and ledger event marked against the truth."""

from __future__ import annotations

from dataclasses import asdict

from games.manor import content as C
from games.manor import words
from games.manor.rules import ActResult
from thespis.intents import Reading, Understood
from thespis.ledger import Event
from thespis.world import World


def clock(phase: int) -> str:
    return C.PHASES[min(phase, len(C.PHASES) - 1)].capitalize()


def event_view(e: Event) -> dict:
    return {"id": e.id, "phase": e.phase, "verb": e.verb, "actor": e.actor, "target": e.target, "loc": e.loc,
            "text": words.sentence(e), "claim": words.claim_text(e.claim) if e.claim else None, "truth": e.truth}


def state_view(w: World) -> dict:
    cast = C.load_cast()["npc"]
    return {
        "game": "manor", "phase": w.phase, "clock": clock(w.phase), "deadline": clock(C.DEADLINE),
        "clocks": [clock(p) for p in range(len(C.PHASES))],
        "status": w.status, "ended_at": w.ended_at, "outcome": w.player.get("outcome"), "brain": w.brain_mode,
        "player": {"loc": w.player["loc"], "asked": list(w.player["asked"])},
        "rooms": [{"id": r, "name": C.ROOM_NAMES[r]} for r in C.ROOMS],
        "npcs": [{"id": n.id, "name": cast[n.id]["name"], "loc": n.loc, "drives": dict(n.drives),
                  "trust_in": dict(n.trust_in), "persona": cast[n.id]["persona"]} for n in w.npcs.values()],
        "beliefs": [{"id": b.id, "npc": b.npc, "claim": words.claim_text(b.claim), "conf": b.conf, "status": b.status,
                     "truth": w.ledger.happened(b.claim), "evidence": [asdict(e) for e in b.evidence]}
                    for b in w.beliefs.all()],
        "ledger": [event_view(e) for e in w.ledger],
        "decisions": [decision_view(w, d) for d in w.decisions],
    }


def decision_view(w: World, d) -> dict:
    """A decision; one that stated a claim also lists what the speaker believed against it, so a lie shows as one."""
    out = d.to_json()
    if d.asserted:
        said = w.ledger.get(d.asserted).claimed
        out["knew"] = [b.id for b in w.beliefs.for_npc(d.npc) if b.active and C.contradicts(b.claim, said)]
    return out


def understood_view(u: Understood, to: str) -> dict:
    """How the player's words to `to` were read (POST /manor/say): `status` is act (done), ask (the `readings` are
    put to the player, nothing done) or talk (words that do nothing here). Each reading carries the POST /manor/act
    body that performs it."""
    def reading(r: Reading) -> dict:
        body = {"verb": r.verb, "target": r.args.get("suspect", to)}
        return {"verb": r.verb, "act": body | ({"topic": r.args["topic"]} if "topic" in r.args else {})}

    return {"status": u.status, "intent": reading(u.intent) if u.intent else None, "sure": u.sure,
            "readings": [reading(r) for r in u.readings], "path": u.path, "why": u.why}


def act_view(result: ActResult, w: World) -> dict:
    return {"events": [event_view(e) for e in result.events], "replies": result.replies, "state": state_view(w)}
