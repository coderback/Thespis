"""The fallback voice: template lines from cast.toml, each citing the ids it rests on.

Every line cites at least one belief or ledger event its speaker knows, so the inspector's why-chain can trace it.
The model voice (#17) replaces the words; the cites rule stays.
"""

from __future__ import annotations

from games.crypt_road import content as C
from thespis.beliefs import Belief
from thespis.decisions import REACT
from thespis.ledger import Claim, Event
from thespis.world import World


def template(npc: str, key: str) -> str | None:
    return C.load_cast()["npc"][npc].get("lines", {}).get(key)


def knows(w: World, npc: str, event_id: str) -> bool:
    """Can this NPC cite the event? It took part, it learned of it, or it happened at its stop."""
    e = w.ledger.get(event_id)
    if npc in (e.actor, e.target):
        return True
    if any(ev.event == event_id for b in w.beliefs.for_npc(npc) for ev in b.evidence):
        return True
    return w.npcs[npc].loc in (e.loc, e.target)


def belief_cites(b: Belief | None) -> list[str]:
    """A belief and the event its strongest evidence came from."""
    if b is None:
        return []
    best = max(b.evidence, key=lambda e: e.conf)
    return [b.id, best.event]


def line(npc: str, key: str, cites: list[str], **fmt) -> tuple[str, list[str]] | None:
    """Fill a template, or None when there is no template or nothing to cite: no line without a source."""
    text = template(npc, key)
    if text is None or not cites:
        return None
    return text.format(**fmt), list(dict.fromkeys(cites))


def say(w: World, npc: str, trigger: str, said: tuple[str, list[str]] | None) -> dict | None:
    """Record a spoken line as a react decision and return it as a reply."""
    if said is None:
        return None
    text, cites = said
    d = w.decisions.record(REACT, npc, w.phase, trigger, line=text, cites=cites, reason=trigger, source="fallback")
    return {"decision": d.id, "npc": npc, "line": text, "cites": cites, "source": d.source}


def _top(w: World, npc: str, about: tuple[str, ...]) -> Belief | None:
    held = [b for b in w.beliefs.for_npc(npc) if b.active and b.conf >= C.CRIME_CONF
            and any(b.claim.mentions(x) for x in about)]
    held.sort(key=lambda b: (C.GOSSIP_PRIORITY.get(b.claim.pred, 0), b.conf), reverse=True)
    return held[0] if held else None


# ---------------------------------------------------------------- reactions to the player's verb
def react(w: World, verb: str, target: str | None, events: list[Event], claim: Claim | None = None) -> list[dict]:
    """Lines spoken straight after a player verb, before any tick."""
    last = events[-1].id if events else None
    out: list[dict | None] = []
    if verb == "insult":
        out.append(say(w, target, "insulted", line(target, "insulted", [last])))
    elif verb == "challenge":
        won = w.pending == "duel_won"
        out.append(say(w, C.RIVAL, "beaten" if won else "victor",
                       line(C.RIVAL, "beaten" if won else "victor", [last])))
    elif verb in ("humiliate", "spare"):
        key = "robbed" if verb == "humiliate" else "spared"
        out.append(say(w, C.RIVAL, key, line(C.RIVAL, key, [last])))
    elif verb == "bribe":
        out.append(say(w, C.GUARD, "bribe", line(C.GUARD, "bribe", [last])))
    elif verb == "talk":
        out.append(say(w, target, "talk", _talk(w, target)))
    elif verb == "tell_claim":
        out.extend(_told(w, target, claim, events))
    return [r for r in out if r]


def _talk(w: World, npc: str) -> tuple[str, list[str]] | None:
    if npc == "mags":
        b = _top(w, "mags", ("player", C.RIVAL))
        if b and b.claim.pred == "robbed":
            return line("mags", "talk_robbed", belief_cites(b))
        if b:
            return line("mags", "talk_grudge", belief_cites(b))
    if npc == "odo":
        b = _top(w, "odo", ("player", C.RIVAL))
        if b and b.claim.pred == "robbed":
            return line("odo", "talk_saw", belief_cites(b))
    if npc == C.GUARD and w.npcs[C.GUARD].trust_in.get("player", 0) < 0:
        b = _top(w, C.GUARD, ("player",))
        return line(C.GUARD, "talk_distrust", belief_cites(b))
    # Nothing on their mind: a greeting, citing the last thing they saw at their stop.
    seen = [e.id for e in reversed(list(w.ledger)) if knows(w, npc, e.id)][:1]
    return line(npc, "talk", seen)


def _told(w: World, listener: str, claim: Claim, events: list[Event]) -> list[dict | None]:
    told = events[0]
    out = []
    if listener == C.GUARD:
        key = "told_believed" if w.beliefs.conf(C.GUARD, claim) >= C.CRIME_CONF else "told_doubted"
        out.append(say(w, C.GUARD, "told", line(C.GUARD, key, [told.id])))
    else:
        out.append(say(w, listener, "told", line(listener, "told", [told.id])))
    if not told.truth:  # a lie, overheard by the NPC it names
        lied = Claim("lied", "player", C.RIVAL)
        b = w.beliefs.get(C.RIVAL, lied)
        if b is not None and listener != C.RIVAL and any(e.event == told.id for e in b.evidence):
            victim = claim.b if claim.a == C.RIVAL else claim.a
            out.append(say(w, C.RIVAL, "lied_about",
                           line(C.RIVAL, "lied_about", [told.id, b.id], victim=_name(victim))))
    return out


def _name(who: str) -> str:
    return {"odo": "the peddler", "mags": "the innkeeper", "brenna": "the Captain", "player": "you"}.get(
        who, C.short_name(who))


# ---------------------------------------------------------------- lines inside the tick
def decision_line(w: World, npc: str, chosen: str, claim: Claim | None = None) -> tuple[str, list[str]] | None:
    """The line that goes with an NPC's decision, if it says anything."""
    if npc == C.RIVAL:
        if chosen == "accuse:player" and claim is not None:
            return line(C.RIVAL, f"accuse_{claim.pred}", belief_cites(w.beliefs.get(C.RIVAL, claim)))
        if chosen == "share_drink":
            return line(C.RIVAL, "share_drink", belief_cites(w.beliefs.get(C.RIVAL, Claim("spared", "player", C.RIVAL))))
        if chosen == "go_to" and w.npcs[C.RIVAL].loc == w.player["loc"]:
            return line(C.RIVAL, "leaving", belief_cites(_top(w, C.RIVAL, ("player",))))
    if npc == C.GUARD and claim is not None:
        b = belief_cites(w.beliefs.get(C.GUARD, claim))
        if chosen.startswith("detain"):
            return line(C.GUARD, "detain", b, culprit=C.short_name(claim.a), victim=_name(claim.b))
        if chosen.startswith("question"):
            return line(C.GUARD, "question", b, witness=C.short_name(chosen.split(":", 1)[1]))
    return None


def testimony(w: World, witness: str, claim: Claim, event: Event) -> None:
    """The witness's own words when the guard questions them; recorded inside the tick."""
    say(w, witness, "testify", line(witness, "testify", [event.id], culprit=C.short_name(claim.a)))


# ---------------------------------------------------------------- lines when a new phase starts
def phase_start(w: World, moves: list[dict]) -> list[dict]:
    """Greetings when the player and an NPC newly share a stop: the guard at the gate, the rival on the road."""
    out: list[dict | None] = []
    here = {n.id for n in w.npcs_at(w.player["loc"])}
    arrived = {m["who"] for m in moves}
    met = here if "player" in arrived else here & arrived
    if C.GUARD in met:
        guard = w.npcs[C.GUARD]
        b = _top(w, C.GUARD, ("player",))
        if guard.trust_in.get("player", 0) < 0 and b is not None and b.claim.a == "player":
            src = max(b.evidence, key=lambda e: e.conf).source
            said = line(C.GUARD, f"arrival_{b.claim.pred}", belief_cites(b), source=C.short_name(src))
            out.append(say(w, C.GUARD, "arrival", said or line(C.GUARD, "arrival", belief_cites(b))))
        else:
            arrival = next((e.id for e in reversed(list(w.ledger)) if e.verb == "move" and e.actor == "player"), None)
            out.append(say(w, C.GUARD, "arrival", line(C.GUARD, "arrival", [arrival] if arrival else [])))
    if C.RIVAL in met and not w.npcs[C.RIVAL].frozen(w.phase):
        kael = w.npcs[C.RIVAL]
        accused = next((e for e in reversed(list(w.ledger)) if e.verb == "accuse" and e.actor == C.RIVAL), None)
        if kael.flags.get("accused") and accused is not None:
            out.append(say(w, C.RIVAL, "shares_stop", line(C.RIVAL, "reported", [accused.id])))
        elif kael.drives["grudge"] >= 5:
            out.append(say(w, C.RIVAL, "shares_stop",
                           line(C.RIVAL, "grudge_meet", belief_cites(_top(w, C.RIVAL, ("player",))))))
    return [r for r in out if r]
