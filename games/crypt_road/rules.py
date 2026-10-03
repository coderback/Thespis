"""The Crypt Road's rules on the Thespis core. tools/crypt_road_sim.py is the reference they must match.

The player's verbs go through act(), which validates against allowed() first. Phase-ending verbs run the tick:
  1. the player's phase action (the gate refuses a distrusted player);
  2. decisions on start-of-phase positions: the guard (detain, question) first, then the rival;
  3. gossip between NPCs on the same stop, before anyone moves;
  4. moves, including the scheduled walkers;
  5. drive upkeep: fear eases by 1 towards 1;
  6. the phase advances.
When the race ends the world runs two more phases (the epilogue), so it visibly carries on without the player.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from games.crypt_road import content as C
from thespis.brain import Brain, UtilityBrain
from thespis.decisions import DECIDE, Decision
from thespis.ledger import Claim, Event
from thespis.world import LOST, PLAYING, WON, World

TALK_MAX = 200
EPILOGUE_PHASES = 2
DUEL_WON = "duel_won"


class NotAllowed(Exception):
    """The verb isn't allowed right now. `reason` is readable by a player."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class Tick:
    moves: list[dict] = field(default_factory=list)  # {"who", "from", "to"}
    decisions: list[Decision] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)


@dataclass
class ActResult:
    events: list[Event]
    tick: Tick | None
    epilogue: list[Tick] | None
    replies: list = field(default_factory=list)  # lines spoken to the player: #10


# ---------------------------------------------------------------- helpers
def _npc_name(npc: str) -> str:
    return C.short_name(npc)


def _event(w: World, verb: str, actor: str, target: str | None, loc: str, claim: Claim | None = None,
           truth: bool = True) -> Event:
    return w.ledger.append(w.phase, verb, actor, target, loc, claim, truth)


def give_evidence(w: World, npc: str, claim: Claim, conf: float, source: str, event: Event) -> None:
    """Store a report. The first time the guard believes a robbery, her trust in the robber drops by 2."""
    w.beliefs.add_evidence(npc, claim, conf, source, event.id, w.phase)
    if npc == C.GUARD and claim.pred == "robbed" and w.beliefs.conf(npc, claim) >= C.CRIME_CONF:
        guard = w.npcs[C.GUARD]
        crimes = guard.flags.setdefault("crimes", [])
        if claim.to_json() not in crimes:
            crimes.append(claim.to_json())
            if claim.a in guard.trust_in:
                guard.trust_in[claim.a] -= 2


def witness(w: World, claim: Claim, actor: str, target: str, event: Event) -> None:
    """Everyone at the player's stop sees it at 1.0; the actor and target always know it."""
    for npc in w.npcs_at(w.player["loc"]):
        if npc.id not in (actor, target):
            give_evidence(w, npc.id, claim, 1.0, "witnessed", event)
    for who in (actor, target):
        if who in w.npcs:
            give_evidence(w, who, claim, 1.0, "self", event)


def _gate_blocks(w: World, who: str, loc: str) -> bool:
    guard = w.npcs[C.GUARD]
    return loc == C.GATE[0] and guard.loc == C.GATE[0] and guard.trust_in.get(who, 0) < 0


def _see(w: World) -> None:
    """Whoever shares the player's stop at the start of a phase is seen there."""
    for npc in w.npcs_at(w.player["loc"]):
        npc.last_seen = {"loc": npc.loc, "phase": w.phase}


# ---------------------------------------------------------------- what the player may do
def allowed(w: World) -> list[dict]:
    """Every verb the player could use now, in the docs/api.md shape; disabled ones carry a reason."""
    loc = w.player["loc"]
    here = [n.id for n in w.npcs_at(loc)]
    ended = w.status != PLAYING
    lock = "The race is over" if ended else ("Choose: humiliate or spare" if w.pending == DUEL_WON else None)
    out: list[dict] = []

    def add(verb, target, label, args, ends_phase, ok=True, why=None, reason=...):
        if reason is ...:
            reason = lock or (None if ok else why)
        out.append({"verb": verb, "target": target, "label": label, "args": args, "ends_phase": ends_phase,
                    "enabled": reason is None, "reason": reason})

    for n in here:
        add("talk", n, f"Talk to {_npc_name(n)}", {"max_len": TALK_MAX}, False)
    for n in here:
        add("insult", n, f"Insult {_npc_name(n)}", {}, False)
    if C.RIVAL in here:
        add("challenge", C.RIVAL, f"Challenge {_npc_name(C.RIVAL)}", {}, True)
        duel = "The race is over" if ended else (None if w.pending == DUEL_WON else "Win a duel first")
        add("humiliate", C.RIVAL, f"Humiliate {_npc_name(C.RIVAL)}", {}, True, reason=duel)
        add("spare", C.RIVAL, f"Spare {_npc_name(C.RIVAL)}", {}, True, reason=duel)
    for n in here:
        add("tell_claim", n, f"Tell {_npc_name(n)}...", {"preds": C.PREDS, "subjects": C.subjects()}, False)
    if C.GUARD in here:
        add("bribe", C.GUARD, f"Bribe {_npc_name(C.GUARD)} ({C.FINE})", {"amount": C.FINE}, False,
            ok=w.player["coins"] >= C.FINE, why=f"You need {C.FINE} coins")
    nxt = C.next_stop(loc)
    if nxt:
        trust = w.npcs[C.GUARD].trust_in.get("player", 0)
        add("move", None, f"Move to {C.STOP_NAMES[nxt]}", {"to": nxt}, True,
            ok=not _gate_blocks(w, "player", loc), why=f"Blocked: Brenna's trust in you is {trust}")
    else:
        add("move", None, "Move on", {}, True, ok=False, why="This is the end of the road")
    add("wait", None, "Wait", {}, True)
    add("take_relic", None, "Take the relic", {}, False, ok=loc == "crypt", why="The relic is in the crypt")
    return out


def _check(w: World, verb: str, target: str | None) -> dict:
    for option in allowed(w):
        if option["verb"] == verb and option["target"] == target:
            if not option["enabled"]:
                raise NotAllowed(option["reason"])
            return option
    raise NotAllowed(f"You can't {verb} {target or ''} here".strip())


# ---------------------------------------------------------------- acting
def act(w: World, verb: str, target: str | None = None, claim: dict | Claim | None = None,
        amount: int | None = None, text: str | None = None, brain: Brain | None = None) -> ActResult:
    """Apply one player verb, the tick it triggers, and the epilogue if the race ends."""
    _check(w, verb, target)
    brain = brain or UtilityBrain()
    start = len(w.ledger)
    tick = None

    if verb == "talk":
        if not text or len(text) > TALK_MAX:
            raise NotAllowed(f"Say something, in {TALK_MAX} characters or fewer")
    elif verb == "insult":
        if target == C.RIVAL:
            w.npcs[C.RIVAL].drives["grudge"] += 1
        c = Claim("insulted", "player", target)
        witness(w, c, "player", target, _event(w, "insult", "player", target, w.player["loc"], c))
    elif verb == "challenge":
        tick = _challenge(w, brain)
    elif verb in ("humiliate", "spare"):
        _settle_duel(w, verb)
        tick = end_phase(w, "wait", brain)
    elif verb == "tell_claim":
        _tell(w, target, _as_claim(claim))
    elif verb == "bribe":
        if amount not in (None, C.FINE):
            raise NotAllowed(f"The fine is {C.FINE} coins")
        w.player["coins"] -= C.FINE
        w.npcs[C.GUARD].trust_in["player"] += 2
        _event(w, "bribe", "player", C.GUARD, w.player["loc"])
    elif verb in ("move", "wait"):
        tick = end_phase(w, verb, brain)
    elif verb == "take_relic":
        w.status, w.ended_at = WON, w.phase
        _event(w, "take_relic", "player", None, w.player["loc"])

    events = list(w.ledger)[start:]
    epilogue = run_epilogue(w, brain) if w.status != PLAYING and w.ended_at is not None and not \
        w.counters.get("epilogue_done") else None
    return ActResult(events=events, tick=tick, epilogue=epilogue)


def _as_claim(claim: dict | Claim | None) -> Claim:
    c = claim if isinstance(claim, Claim) else Claim.from_json(claim) if claim else None
    if c is None or c.pred not in C.PREDS or c.a not in C.subjects() or c.b not in C.subjects():
        raise NotAllowed("Pick a claim from the list")
    return c


def _challenge(w: World, brain: Brain) -> Tick | None:
    kael = w.npcs[C.RIVAL].drives
    w.counters["challenges"] = n = w.counters.get("challenges", 0) + 1
    _event(w, "challenge", "player", C.RIVAL, w.player["loc"])
    if C.dice(w.seed, f"challenge:{n}") < C.DUEL_WIN_CHANCE:
        kael["fear"] += 2
        kael["grudge"] += 2
        c = Claim("beat", "player", C.RIVAL)
        witness(w, c, "player", C.RIVAL, _event(w, "beat", "player", C.RIVAL, w.player["loc"], c))
        w.pending = DUEL_WON  # the player must humiliate or spare, which ends the phase
        return None
    kael["grudge"] += 1
    c = Claim("beat", C.RIVAL, "player")
    witness(w, c, C.RIVAL, "player", _event(w, "beat", C.RIVAL, "player", w.player["loc"], c))
    return end_phase(w, "wait", brain)


def _settle_duel(w: World, verb: str) -> None:
    w.pending = None
    kael = w.npcs[C.RIVAL].drives
    if verb == "humiliate":
        kael["grudge"] += 3
        kael["respect"] = max(0, kael["respect"] - 1)
        w.player["coins"] += 30
        c = Claim("robbed", "player", C.RIVAL)
    else:
        kael["grudge"] = max(0, kael["grudge"] - 2)
        kael["respect"] += 3
        c = Claim("spared", "player", C.RIVAL)
    witness(w, c, "player", C.RIVAL, _event(w, verb, "player", C.RIVAL, w.player["loc"], c))


def _tell(w: World, listener: str, c: Claim) -> None:
    truth = w.ledger.happened(c)
    e = _event(w, "tell_claim", "player", listener, w.player["loc"], c, truth)
    give_evidence(w, listener, c, C.conf_from_trust(w.npcs[listener].trust_in.get("player", 0)), "player", e)
    # An NPC named in a lie it overhears knows it was lied about.
    for npc in w.npcs_at(w.player["loc"]):
        if c.mentions(npc.id) and npc.id != listener and not truth and "grudge" in npc.drives:
            npc.drives["grudge"] += 2
            give_evidence(w, npc.id, Claim("lied", "player", npc.id), 1.0, "self", e)


# ---------------------------------------------------------------- the tick
def end_phase(w: World, action: str, brain: Brain | None = None) -> Tick:
    brain = brain or UtilityBrain()
    p, pl = w.phase, w.player
    kael, guard = w.npcs[C.RIVAL], w.npcs[C.GUARD]
    start_events, start_decisions = len(w.ledger), len(w.decisions)
    tick = Tick()

    # 1. The player's phase action.
    if action == "move" and C.next_stop(pl["loc"]):
        if _gate_blocks(w, "player", pl["loc"]):
            _event(w, "block", "player", C.GUARD, pl["loc"])
        else:
            frm, pl["loc"] = pl["loc"], C.next_stop(pl["loc"])
            _event(w, "move", "player", pl["loc"], frm)
            tick.moves.append({"who": "player", "from": frm, "to": pl["loc"]})

    # 2a. The guard decides: detain anyone she believes robbed someone, then question witnesses.
    if kael.loc == guard.loc and not kael.frozen(p):
        for cj in list(guard.flags.get("crimes", [])):
            c = Claim.from_json(cj)
            detained = guard.flags.setdefault("detained_for", [])
            if c.a == C.RIVAL and w.beliefs.conf(C.GUARD, c) >= C.CRIME_CONF and cj not in detained:
                options = {f"detain:{C.RIVAL}": 10, "wait": 1}
                chosen = brain.choose(C.GUARD, options)
                _decide(w, C.GUARD, "crime_belief", options, chosen, "believes a robbery at 0.5 or more")
                if chosen.startswith("detain"):
                    detained.append(cj)
                    kael.frozen_until = p + 1
                    _event(w, "detain", C.GUARD, C.RIVAL, guard.loc, c, w.ledger.happened(c))
    for wit in C.WITNESSES:
        if w.npcs[wit].loc != guard.loc:
            continue
        for belief in w.beliefs.for_npc(C.GUARD):
            if not belief.active or not belief.claim.mentions(wit):
                continue
            if all(e.source == wit for e in belief.evidence):
                continue
            if w.ledger.happened(belief.claim):
                continue
            options = {f"question:{wit}": 8, "wait": 1}
            chosen = brain.choose(C.GUARD, options)
            _decide(w, C.GUARD, "witness_present", options, chosen, f"{wit} can speak to a claim about them")
            if not chosen.startswith("question"):
                continue
            w.beliefs.retract(belief)  # the witness knows it never happened
            for src in {e.source for e in belief.evidence}:
                if src in guard.trust_in:
                    guard.trust_in[src] -= 3
            _event(w, "testify", wit, C.GUARD, guard.loc, belief.claim, w.ledger.happened(belief.claim))
            if kael.frozen(p):
                kael.frozen_until = None
                _event(w, "release", C.GUARD, C.RIVAL, guard.loc)

    # 2b. The rival decides.
    kael_moves = False
    if not kael.frozen(p):
        d = kael.drives
        options = {"go_to": d["ambition"], "wait": 0}
        if kael.loc == "crypt":
            options["take_relic"] = 100
        robbed, beaten = Claim("robbed", "player", C.RIVAL), Claim("beat", "player", C.RIVAL)
        if (kael.loc == guard.loc and d["grudge"] >= 4 and not kael.flags.get("accused")
                and (w.beliefs.conf(C.RIVAL, robbed) or w.beliefs.conf(C.RIVAL, beaten))):
            options["accuse:player"] = d["grudge"] + 3
        if d["respect"] >= 4 and kael.loc == pl["loc"] and not kael.flags.get("drink"):
            options["share_drink"] = d["respect"] + 3
        chosen = brain.choose(C.RIVAL, options)
        _decide(w, C.RIVAL, "tick", options, chosen, f"{chosen} scores {options[chosen]}")
        if chosen == "take_relic":
            if w.status == PLAYING:
                w.status, w.ended_at = LOST, p
                _event(w, "take_relic", C.RIVAL, None, kael.loc)
        elif chosen == "accuse:player":
            kael.flags["accused"] = True
            c = robbed if w.beliefs.conf(C.RIVAL, robbed) else beaten
            e = _event(w, "accuse", C.RIVAL, C.GUARD, kael.loc, c, w.ledger.happened(c))
            give_evidence(w, C.GUARD, c, C.conf_from_trust(guard.trust_in.get(C.RIVAL, 0)), C.RIVAL, e)
        elif chosen == "share_drink":
            kael.flags["drink"] = True
        elif chosen == "go_to":
            if _gate_blocks(w, C.RIVAL, kael.loc):
                _event(w, "block", C.RIVAL, C.GUARD, kael.loc)
            elif C.next_stop(kael.loc):
                kael_moves = True

    # 3. Gossip, on the positions before anyone moves.
    for g in C.GOSSIPS:
        gossip = w.npcs[g]
        mine = [b for b in w.beliefs.for_npc(g)
                if b.active and b.conf >= C.CRIME_CONF and (b.claim.mentions("player") or b.claim.mentions(C.RIVAL))]
        mine.sort(key=lambda b: (C.GOSSIP_PRIORITY.get(b.claim.pred, 0), b.conf,
                                 (b.claim.pred, b.claim.a, b.claim.b)), reverse=True)
        for listener in w.npcs_at(gossip.loc):
            if listener.id == g:
                continue
            for b in mine:
                if w.beliefs.get(listener.id, b.claim) is None:
                    e = _event(w, "gossip", g, listener.id, gossip.loc, b.claim, w.ledger.happened(b.claim))
                    give_evidence(w, listener.id, b.claim, round(b.conf * 0.8, 2), g, e)
                    break

    # 4. Moves: the rival, then everyone on a fixed walk.
    if kael_moves:
        frm, kael.loc = kael.loc, C.next_stop(kael.loc)
        _event(w, "move", C.RIVAL, kael.loc, frm)
        tick.moves.append({"who": C.RIVAL, "from": frm, "to": kael.loc})
    for npc in w.npcs.values():
        route = C.walk(npc.id)
        if route and route[(p + 1) % len(route)] != npc.loc:
            frm, npc.loc = npc.loc, route[(p + 1) % len(route)]
            _event(w, "move", npc.id, npc.loc, frm)
            tick.moves.append({"who": npc.id, "from": frm, "to": npc.loc})

    # 5. Drive upkeep, then 6. the next phase.
    kael.drives["fear"] = max(1, kael.drives["fear"] - 1)
    w.phase += 1
    _see(w)

    tick.events = list(w.ledger)[start_events:]
    tick.decisions = list(w.decisions)[start_decisions:]
    return tick


def _decide(w: World, npc: str, trigger: str, options: dict, chosen: str, reason: str) -> Decision:
    return w.decisions.record(DECIDE, npc, w.phase, trigger, allowed=list(options), chosen=chosen,
                              reason=reason, source="fallback")


def run_epilogue(w: World, brain: Brain | None = None) -> list[Tick]:
    """After the race, the world runs on for two phases with the player idle."""
    w.counters["epilogue_done"] = 1
    return [end_phase(w, "wait", brain) for _ in range(EPILOGUE_PHASES)]
