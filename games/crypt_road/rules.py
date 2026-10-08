"""The Crypt Road's rules on the Thespis core. tools/crypt_road_sim.py is the reference they must match.

The player's verbs go through act(), which validates against allowed() first. Phase-ending verbs run the tick:
  1. the player's phase action (the gate refuses a distrusted player);
  2. decisions on start-of-phase positions: the guard (detain, question) first, then the rival. A player who
     moves is on the road until the next phase, so NPCs still see them where they started, and don't see the move;
  3. gossip between NPCs on the same stop, before anyone moves;
  4. moves, including the scheduled walkers;
  5. drive upkeep: fear eases by 1 towards 1;
  6. the phase advances.
When the race ends the world runs two more phases (the epilogue), so it visibly carries on without the player.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from games.crypt_road import claims, voice
from games.crypt_road import content as C
from thespis import perception
from thespis.affordances import Affordance, decide, options
from thespis.brain import Brain, UtilityBrain
from thespis.claims import ClaimChecking
from thespis.expression import Mind, Observer, ReplyCache
from thespis.gateway import ModelGateway
from thespis.ledger import Claim, Event
from thespis.minds import NPC
from thespis.moderation import Moderator
from thespis.play import NotAllowed, Verbs, check, count_calls, open_mind
from thespis.tick import Tick, gossip, run_tick, walk, walks
from thespis.voice import View, reply
from thespis.world import LOST, PLAYING, WON, World

__all__ = ["NotAllowed", "Tick"]

TALK_MAX = 200
EPILOGUE_PHASES = 2
DUEL_WON = "duel_won"


@dataclass
class ActResult:
    events: list[Event]
    tick: Tick | None
    epilogue: list[Tick] | None
    replies: list = field(default_factory=list)  # lines spoken to the player: #10
    model_calls: int = 0  # how many model calls the action made (cache hits are free)


# ---------------------------------------------------------------- helpers
STATEMENTS = ("tell_claim", "accuse")  # events where someone states a claim as fact


def happened(w: World, c: Claim) -> bool:
    """Ground truth for a claim. Most claims are true when an event that really happened carried them. A lie leaves
    no event of its own, so lied(a, b) is true when a stated a claim naming b that never happened."""
    if c.pred == "lied":
        return any(e.verb in STATEMENTS and e.actor == c.a and not e.truth and e.claim and e.claim.mentions(c.b)
                   for e in w.ledger)
    return w.ledger.happened(c)


def _npc_name(npc: str) -> str:
    return C.short_name(npc)


def _event(w: World, verb: str, actor: str, target: str | None, loc: str, claim: Claim | None = None,
           truth: bool = True, amount: int | None = None) -> Event:
    return w.ledger.append(w.phase, verb, actor, target, loc, claim, truth, amount)


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
    perception.witness(w, claim, actor, target, event, w.player["loc"], give_evidence)


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
    verbs = Verbs("The race is over" if ended else ("Choose: humiliate or spare" if w.pending == DUEL_WON else None))
    add = verbs.add

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
        guard, coins = w.npcs[C.GUARD], w.player["coins"]
        refused = guard.flags.get("refused_phase") == w.phase
        add("bribe", C.GUARD, f"Bribe {_npc_name(C.GUARD)}...",
            {"amount": min(guard.flags.get("asking", C.FINE), coins), "min": 1, "max": coins}, False,
            ok=coins >= 1 and not refused,
            why=f"{_npc_name(C.GUARD)} won't hear another offer until the next phase" if refused else "You have no coins")
    nxt = C.next_stop(loc)
    if nxt:
        trust = w.npcs[C.GUARD].trust_in.get("player", 0)
        add("move", None, f"Move to {C.STOP_NAMES[nxt]}", {"to": nxt}, True,
            ok=not _gate_blocks(w, "player", loc), why=f"Blocked: Brenna's trust in you is {trust}")
    else:
        add("move", None, "Move on", {}, True, ok=False, why="This is the end of the road")
    add("wait", None, "Wait", {}, True)
    add("take_relic", None, "Take the relic", {}, False, ok=loc == "crypt", why="The relic is in the crypt")
    return verbs.options


# ---------------------------------------------------------------- acting
def act(w: World, verb: str, target: str | None = None, claim: dict | Claim | None = None,
        amount: int | None = None, text: str | None = None, brain: Brain | None = None,
        gateway: ModelGateway | None = None, cache: ReplyCache | None = None, replay: bool = False,
        budget: int | None = None, moderator: Moderator | None = None, observer: Observer | None = None,
        checking: ClaimChecking | None = None) -> ActResult:
    """Apply one player verb, the tick it triggers, and the epilogue if the race ends.

    Code makes every choice. With a gateway and the brain switched on, the model words what NPCs say; anything it
    gets wrong, or can't answer, falls back to the template lines. A cache answers
    what has been asked before; with `replay` on, only the cache answers. `budget` caps this action's model calls;
    the session's running total is kept in `w.counters["model_calls"]`. An `observer` sees every line the model
    settles (thespis.expression.Mind). With `checking`, lines with consequences meet the claim check (thespis.claims).
    """
    check(allowed(w), verb, target)
    brain = brain or UtilityBrain()
    mind = open_mind(w, voice.VALIDATOR, gateway, cache, replay, budget, moderator, observer,
                     claims.check(w, checking, gateway) if checking and gateway else None)
    start = len(w.ledger)
    ends_phase = None  # the tick this verb triggers, if any: "move" or "wait"
    told = haggle = None

    if verb == "talk":
        if not text or len(text) > TALK_MAX:
            raise NotAllowed(f"Say something, in {TALK_MAX} characters or fewer")
    elif verb == "insult":
        assert target is not None  # _check found someone here to insult
        if target == C.RIVAL:
            w.npcs[C.RIVAL].drives["grudge"] += 1
        c = Claim("insulted", "player", target)
        witness(w, c, "player", target, _event(w, "insult", "player", target, w.player["loc"], c))
    elif verb == "challenge":
        if not _challenge(w):
            ends_phase = "wait"  # a lost duel ends the phase; a won one waits for humiliate or spare
    elif verb in ("humiliate", "spare"):
        _settle_duel(w, verb)
        ends_phase = "wait"
    elif verb == "tell_claim":
        assert target is not None  # _check found someone here to tell
        told = _as_claim(claim)
        _tell(w, target, told)
    elif verb == "bribe":
        haggle = _offer(w, mind, brain, _offered_amount(w, amount))
    elif verb in ("move", "wait"):
        ends_phase = verb
    elif verb == "take_relic":
        w.status, w.ended_at = WON, w.phase
        _event(w, "take_relic", "player", None, w.player["loc"])

    replies = voice.react(w, mind, verb, target, list(w.ledger)[start:], told, text)
    if haggle:
        replies.append(haggle)
    tick = end_phase(w, ends_phase, brain, mind) if ends_phase else None
    if tick is not None and w.status == PLAYING:
        replies += voice.phase_start(w, mind, tick.moves)
    events = list(w.ledger)[start:]
    epilogue = run_epilogue(w, brain, mind) if w.status != PLAYING and w.ended_at is not None and not \
        w.counters.get("epilogue_done") else None
    return ActResult(events=events, tick=tick, epilogue=epilogue, replies=replies, model_calls=count_calls(w, mind))


def _offered_amount(w: World, amount: int | None) -> int:
    """A bribe's offer: whole coins, at least one and no more than the player has. None means the standard fine."""
    coins = w.player["coins"]
    amount = C.FINE if amount is None else amount
    if isinstance(amount, bool) or not isinstance(amount, int) or not 1 <= amount <= coins:
        raise NotAllowed(f"Offer between 1 and {coins} coins")
    return amount


def _offer(w: World, mind: Mind, brain: Brain, amount: int) -> dict | None:
    """The player offers Brenna `amount` coins (#36). At or above her price she takes it and trusts them more; below
    it she refuses a lowball (under half her price) and counters anything else at her price. She never takes less.

    Returns her reply to a haggle, in the replies shape, or None when she took the money (voice.react voices that).
    """
    guard, loc = w.npcs[C.GUARD], w.player["loc"]
    price = C.asking_price(guard.trust_in.get("player", 0))
    if amount >= price:
        w.player["coins"] -= amount
        guard.trust_in["player"] += 2
        guard.flags.pop("asking", None)
        _event(w, "bribe", "player", C.GUARD, loc, amount=amount)
        return None
    offer = _event(w, "offer", "player", C.GUARD, loc, amount=amount)
    choices = {f"counter:{price}": 5, "refuse": 7 if amount * 2 < price else 3}  # a lowball is more likely refused
    d = decide(w, mind, voice.VOICE, brain, C.GUARD, "bribe_offer", choices,
               lambda ch: voice.haggle_line(ch, offer, amount, price),
               f"The player offers you {amount} coins to forget the trouble. You won't take less than {price}.",
               f"an offer of {amount}, under her price of {price}")
    if d.chosen == "refuse":
        guard.flags["refused_phase"] = w.phase
        _event(w, "refuse", C.GUARD, "player", loc)
    else:
        guard.flags["asking"] = price
        _event(w, "counter", C.GUARD, "player", loc, amount=price)
    return reply(d)


def _as_claim(claim: dict | Claim | None) -> Claim:
    c = claim if isinstance(claim, Claim) else Claim.from_json(claim) if claim else None
    if c is None or c.pred not in C.PREDS or c.a not in C.subjects() or c.b not in C.subjects():
        raise NotAllowed("Pick a claim from the list")
    return c


def _challenge(w: World) -> bool:
    """Roll the duel. Returns whether the player won."""
    kael = w.npcs[C.RIVAL].drives
    w.counters["challenges"] = n = w.counters.get("challenges", 0) + 1
    _event(w, "challenge", "player", C.RIVAL, w.player["loc"])
    if C.dice(w.seed, f"challenge:{n}") < C.DUEL_WIN_CHANCE:
        kael["fear"] += 2
        kael["grudge"] += 2
        c = Claim("beat", "player", C.RIVAL)
        witness(w, c, "player", C.RIVAL, _event(w, "beat", "player", C.RIVAL, w.player["loc"], c))
        w.pending = DUEL_WON  # the player must humiliate or spare, which ends the phase
        return True
    kael["grudge"] += 1
    c = Claim("beat", C.RIVAL, "player")
    witness(w, c, C.RIVAL, "player", _event(w, "beat", C.RIVAL, "player", w.player["loc"], c))
    return False


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
    truth = happened(w, c)
    e = _event(w, "tell_claim", "player", listener, w.player["loc"], c, truth)
    give_evidence(w, listener, c, C.conf_from_trust(w.npcs[listener].trust_in.get("player", 0)), "player", e)
    # An NPC named in a lie it overhears knows it was lied about.
    for npc in w.npcs_at(w.player["loc"]):
        if c.mentions(npc.id) and npc.id != listener and not truth and "grudge" in npc.drives:
            npc.drives["grudge"] += 2
            give_evidence(w, npc.id, Claim("lied", "player", npc.id), 1.0, "self", e)


# ---------------------------------------------------------------- the tick
# What Kael may do each phase, by utility; the first declared wins a tie.
ROBBED, BEATEN = Claim("robbed", "player", C.RIVAL), Claim("beat", "player", C.RIVAL)


def _can_accuse(w: World, kael: NPC, view: View) -> bool:
    """At the guard post, angry enough, not yet done, and with something to report."""
    return (kael.loc == w.npcs[C.GUARD].loc and kael.drives["grudge"] >= 4 and not kael.flags.get("accused")
            and bool(w.beliefs.conf(C.RIVAL, ROBBED) or w.beliefs.conf(C.RIVAL, BEATEN)))


KAEL = (
    Affordance("go_to", lambda w, n, v: n.drives["ambition"]),
    Affordance("wait", lambda w, n, v: 0),
    Affordance("take_relic", lambda w, n, v: 100, when=lambda w, n, v: n.loc == "crypt"),
    Affordance("accuse:player", lambda w, n, v: n.drives["grudge"] + 3, when=_can_accuse),
    Affordance("share_drink", lambda w, n, v: n.drives["respect"] + 3,
               when=lambda w, n, v: n.drives["respect"] >= 4 and n.loc == v.player_at and not n.flags.get("drink")),
)


def end_phase(w: World, action: str, brain: Brain | None = None, mind: Mind | None = None) -> Tick:
    """One phase, in order (see the module's docstring): the player's action, the guard, the rival, gossip, moves,
    then upkeep and the next phase."""
    brain = brain or UtilityBrain()
    mind = mind or Mind(None, voice.VALIDATOR)
    p, pl = w.phase, w.player
    kael, guard = w.npcs[C.RIVAL], w.npcs[C.GUARD]
    view = View(pl["loc"])  # what NPCs see of the player this phase: where they started it
    kael_to: str | None = None  # where the rival walks this phase, if he does

    def choose(npc, trigger, choices, line_for, situation, reason=None, ask=True) -> str:
        return decide(w, mind, voice.VOICE, brain, npc, trigger, choices, line_for, situation, reason, ask,
                      view).chosen or ""

    def player(tick: Tick) -> None:
        nonlocal view
        if action == "move" and C.next_stop(pl["loc"]):
            if _gate_blocks(w, "player", pl["loc"]):
                _event(w, "block", "player", C.GUARD, pl["loc"])
            else:
                frm, pl["loc"] = pl["loc"], C.next_stop(pl["loc"])
                move = _event(w, "move", "player", pl["loc"], frm)
                tick.moves.append({"who": "player", "from": frm, "to": pl["loc"]})
                view = View(frm, frozenset({move.id}))  # still on the road until the phase ends

    def the_guard(tick: Tick) -> None:
        """Detain anyone she believes robbed someone, then question witnesses."""
        if kael.loc == guard.loc and not kael.frozen(p):
            for cj in list(guard.flags.get("crimes", [])):
                c = Claim.from_json(cj)
                detained = guard.flags.setdefault("detained_for", [])
                if c.a == C.RIVAL and w.beliefs.conf(C.GUARD, c) >= C.CRIME_CONF and cj not in detained:
                    chosen = choose(C.GUARD, "crime_belief", {f"detain:{C.RIVAL}": 10, "wait": 1},
                                    lambda ch, c=c: voice.decision_line(w, C.GUARD, ch, c, view),
                                    f"You believe {voice._about(c)}. {C.short_name(c.a)} is here at your post.",
                                    "believes a robbery at 0.5 or more")
                    if chosen.startswith("detain"):
                        detained.append(cj)
                        kael.frozen_until = p + 1
                        _event(w, "detain", C.GUARD, C.RIVAL, guard.loc, c, happened(w, c))
        for wit in C.WITNESSES:
            if w.npcs[wit].loc != guard.loc:
                continue
            for belief in w.beliefs.for_npc(C.GUARD):
                if not belief.active or not belief.claim.mentions(wit) or happened(w, belief.claim):
                    continue
                if all(e.source == wit for e in belief.evidence):
                    continue
                chosen = choose(C.GUARD, "witness_present", {f"question:{wit}": 8, "wait": 1},
                                lambda ch, c=belief.claim: voice.decision_line(w, C.GUARD, ch, c, view),
                                f"{C.short_name(wit)} is here. You were told that {voice._about(belief.claim)}; "
                                f"{C.short_name(wit)} would know whether it happened.",
                                f"{wit} can speak to a claim about them")
                if chosen.startswith("question"):
                    _testify(w, mind, wit, belief)

    def the_rival(tick: Tick) -> None:
        nonlocal kael_to
        if kael.frozen(p):
            return
        choices = options(w, C.RIVAL, KAEL, view)
        grievance = ROBBED if w.beliefs.conf(C.RIVAL, ROBBED) else BEATEN
        # Voice the choice only when it matters: an option beyond the default walk, or a drive past a threshold.
        ask = voice.crossed_threshold(w, C.RIVAL) or len(choices) > 2
        chosen = choose(C.RIVAL, "tick", choices, lambda ch: voice.decision_line(w, C.RIVAL, ch, grievance, view),
                        f"You are at {C.STOP_NAMES[kael.loc]}.", ask=ask)
        if chosen == "take_relic":
            if w.status == PLAYING:
                w.status, w.ended_at = LOST, p
                _event(w, "take_relic", C.RIVAL, None, kael.loc)
        elif chosen == "accuse:player":
            kael.flags["accused"] = True
            e = _event(w, "accuse", C.RIVAL, C.GUARD, kael.loc, grievance, happened(w, grievance))
            give_evidence(w, C.GUARD, grievance, C.conf_from_trust(guard.trust_in.get(C.RIVAL, 0)), C.RIVAL, e)
        elif chosen == "share_drink":
            kael.flags["drink"] = True
        elif chosen == "go_to":
            if _gate_blocks(w, C.RIVAL, kael.loc):
                _event(w, "block", C.RIVAL, C.GUARD, kael.loc)
            elif nxt := C.next_stop(kael.loc):
                kael_to = nxt

    def moves(tick: Tick) -> None:
        if kael_to:
            walk(w, tick, C.RIVAL, kael_to)
        walks(w, tick, C.walk)

    def upkeep(tick: Tick) -> None:
        kael.drives["fear"] = max(1, kael.drives["fear"] - 1)
        w.phase += 1
        _see(w)

    return run_tick(w, [player, the_guard, the_rival,
                        lambda t: gossip(w, C.GOSSIPS, ("player", C.RIVAL), C.GOSSIP_PRIORITY, C.CRIME_CONF, 0.8,
                                         happened, give_evidence),
                        moves, upkeep])


def _testify(w: World, mind: Mind, wit: str, belief) -> None:
    """The witness tells the guard it never happened: evidence against it, as far as she trusts the witness. Whoever
    told her loses her trust, everything they told her is re-weighed, and a rival held on their word goes free."""
    guard, kael = w.npcs[C.GUARD], w.npcs[C.RIVAL]
    sources = {e.source for e in belief.evidence if not e.against}
    e = _event(w, "testify", wit, C.GUARD, guard.loc, belief.claim, happened(w, belief.claim))
    w.beliefs.add_evidence(C.GUARD, belief.claim, C.conf_from_trust(guard.trust_in.get(wit, 0)), wit, e.id,
                           w.phase, against=True)
    for src in sorted(sources):
        if src in guard.trust_in:
            guard.trust_in[src] -= 3
            w.beliefs.discredit(C.GUARD, src, C.conf_from_trust(guard.trust_in[src]))
    voice.testimony(w, mind, wit, belief.claim, e)
    if kael.frozen(w.phase):
        kael.frozen_until = None
        _event(w, "release", C.GUARD, C.RIVAL, guard.loc)


def run_epilogue(w: World, brain: Brain | None = None, mind: Mind | None = None) -> list[Tick]:
    """After the race, the world runs on for two phases with the player idle."""
    w.counters["epilogue_done"] = 1
    return [end_phase(w, "wait", brain, mind) for _ in range(EPILOGUE_PHASES)]
