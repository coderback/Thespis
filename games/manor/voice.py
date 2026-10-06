"""How the manor's people speak through the core: their state packs, the validator's vocabulary, and their lines.

The pack follows the same rule as every Thespis game: the model sees only what the NPC knows, never whether a belief
is true. Sable knows she took the ring; Lady Vane only knows what she has been told.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from games.manor import content as C
from games.manor import words
from thespis.deception import asserting
from thespis.decisions import REACT
from thespis.expression import Mind, StatePack, Utterance, Validator
from thespis.retriever import TopKRetriever
from thespis.world import World

VOCABULARY = {"lady vane": C.OWNER, "vane": C.OWNER, "her ladyship": C.OWNER, "pell": C.BUTLER, "sable": C.MAID,
              **{r: r for r in C.ROOMS}}
VALIDATOR = Validator(VOCABULARY)
RETRIEVER = TopKRetriever(5)
KNOWN_EVENTS = 5
DOES = {
    "deceive:alibi": "say you were in the kitchen at mid-morning. It isn't true: you were in the study",
    "deflect": "avoid the question without saying where you were",
}


@dataclass
class Speech:
    npc: str
    trigger: str
    said: tuple[str, list[str]] | None  # the fallback line and its cites; None means the NPC stays silent
    situation: str  # what just happened, from the NPC's point of view, for the model


def template(npc: str, key: str) -> str | None:
    return C.load_cast()["npc"][npc].get("lines", {}).get(key)


def line(npc: str, key: str, cites: Sequence[str | None]) -> tuple[str, list[str]] | None:
    """A template line and what it cites, or None when there is no template or nothing to cite."""
    text, known = template(npc, key), [c for c in cites if c]
    return (text, list(dict.fromkeys(known))) if text and known else None


def knows(w: World, npc: str, event_id: str) -> bool:
    """Can this NPC cite the event? It took part, it learned of it, or, once the player is here, it happened in its
    room. Before that, no one saw what they weren't told they saw: Pell missed the theft in his own study."""
    e = w.ledger.get(event_id)
    if npc in (e.actor, e.target):
        return True
    if any(ev.event == event_id for b in w.beliefs.for_npc(npc) for ev in b.evidence):
        return True
    return e.phase >= C.ARRIVAL and w.npcs[npc].loc in (e.loc, e.target)


def pack_for(w: World, npc_id: str, situation: str, action: str | None = None,
             asserts: str | None = None) -> StatePack:
    """Everything the model may know when it speaks for this NPC. `action` is what code decided it does, if it is
    acting, and `asserts` the claim that action states, in words."""
    npc, cast = w.npcs[npc_id], C.load_cast()["npc"][npc_id]
    others = [n.id for n in w.npcs_at(npc.loc) if n.id != npc_id]
    if w.player["loc"] == npc.loc:
        others.append("player")
    beliefs = RETRIEVER.beliefs(w.beliefs, npc_id)
    known = [e for e in reversed(list(w.ledger)) if knows(w, npc_id, e.id)][:KNOWN_EVENTS][::-1]
    doing = {"id": action, "does": DOES.get(action, action.replace("_", " "))} if action else None
    if doing and asserts:
        doing = asserting(doing, asserts)
    return StatePack(
        npc=npc_id, name=cast["name"], persona=cast["persona"], goal=cast["goal"], situation=situation,
        here=[words.who(x, about=True) for x in others], drives=dict(npc.drives), trust_in=dict(npc.trust_in),
        beliefs=[{"id": b.id, "claim": words.claim_text(b.claim, about=True), "conf": b.conf,
                  "from": sorted({e.source for e in b.evidence})} for b in beliefs],
        events=[{"id": e.id, "what": words.sentence(e, about=True)} for e in known],
        action=doing,
        names=set(C.ROOMS) | set(w.npcs),  # a small household: everyone knows everyone, and every room
        setting=f"You are in {C.ROOM_NAMES[npc.loc]} of Lady Vane's manor, which has a hall, a study and a kitchen. "
                f"It is {C.PHASES[min(w.phase, len(C.PHASES) - 1)]}.",
    )


def deliver(w: World, mind: Mind, speeches: list[Speech]) -> list[dict]:
    """Voice a moment's lines, the model calls in parallel, and record each as a react decision."""
    voiced = [(s, s.said) for s in speeches if s.said]
    speeches = [s for s, _ in voiced]
    fallbacks = [Utterance(None, said[0], said[1], "fallback") for _, said in voiced]
    if mind.active:
        spoken = mind.react_many([(pack_for(w, s.npc, s.situation), f) for s, f in zip(speeches, fallbacks)])
    else:
        spoken = fallbacks
    replies = []
    for s, u in zip(speeches, spoken):
        reason = f"{s.trigger}; {u.note}" if u.note else s.trigger
        d = w.decisions.record(REACT, s.npc, w.phase, s.trigger, line=u.line, cites=u.cites, reason=reason,
                               source=u.source)
        replies.append(reply(d))
    return replies


def reply(d) -> dict:
    return {"decision": d.id, "npc": d.npc, "line": d.line, "cites": d.cites, "source": d.source}
