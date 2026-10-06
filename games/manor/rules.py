"""The manor mystery's rules (#35): the player's verbs, Sable's lies, Lady Vane's questioning, and the verdict.

Built on the Thespis core with one addition, NPC deception (thespis.deception). Sable's lie is an action these rules
choose once she is frightened enough, and the model words it; a lie goes into the ledger with its real truth, false,
so the inspector can show it and the why-chain can trace it.

The solve: ask Sable about the morning (she lies), ask Pell (he saw her leave the study), have Lady Vane question
Pell (his testimony breaks the alibi), then accuse Sable before evening.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from games.manor import content as C
from games.manor import voice, words
from games.manor.voice import Speech
from thespis.beliefs import Belief
from thespis.brain import UtilityBrain
from thespis.deception import SAID, log_statement
from thespis.decisions import DECIDE
from thespis.expression import Mind, Observer, ReplyCache, Utterance
from thespis.gateway import ModelGateway
from thespis.ledger import Claim, Event
from thespis.moderation import Moderator
from thespis.world import LOST, PLAYING, WON, World

OUTCOMES = {
    "won": "Solved. Sable took the ring, and Lady Vane believed Pell's testimony over Sable's alibi.",
    "lost_alibi": "Lady Vane didn't believe you: as far as she knew, Sable was in the kitchen at mid-morning. "
                  "Break the alibi first.",
    "lost_innocent": "Pell didn't take the ring, and Lady Vane knew it.",
    "constable": "Evening came with the case unsolved, and Lady Vane sent for the constable.",
}


class NotAllowed(Exception):
    """The verb isn't allowed right now. `reason` is readable by a player."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class ActResult:
    events: list[Event]
    replies: list = field(default_factory=list)
    model_calls: int = 0


# ---------------------------------------------------------------- what the player may do
def allowed(w: World) -> list[dict]:
    """Every verb the player could use now; disabled ones carry a reason."""
    loc = w.player["loc"]
    here = [n.id for n in w.npcs_at(loc)]
    closed = "The case is closed" if w.status != PLAYING else None
    out: list[dict] = []

    def add(verb, target, label, args, ends_phase, ok=True, why=None):
        reason = closed or (None if ok else why)
        out.append({"verb": verb, "target": target, "label": label, "args": args, "ends_phase": ends_phase,
                    "enabled": reason is None, "reason": reason})

    topics = [{"id": k, "label": v} for k, v in C.TOPICS.items()]
    for n in here:
        add("ask", n, f"Ask {C.name(n)}...", {"topics": topics}, False)
    if C.OWNER in here:
        for n in C.SUSPECTS:
            add("request_questioning", n, f"Have Lady Vane question {C.name(n)}", {}, False,
                ok=f"{n}:morning" in w.player["asked"], why=f"Ask {C.name(n)} about this morning first")
        for n in C.SUSPECTS:
            add("accuse", n, f"Accuse {C.name(n)}", {}, True)
    for room in C.ROOMS:
        if room != loc:
            add("move", room, f"Go to {C.ROOM_NAMES[room]}", {"to": room}, True)
    return out


def _check(w: World, verb: str, target: str | None) -> None:
    for option in allowed(w):
        if option["verb"] == verb and option["target"] == target:
            if not option["enabled"]:
                raise NotAllowed(option["reason"])
            return
    raise NotAllowed(f"You can't {verb.replace('_', ' ')} {target or ''} here".strip())


# ---------------------------------------------------------------- acting
def act(w: World, verb: str, target: str | None = None, topic: str | None = None,
        gateway: ModelGateway | None = None, cache: ReplyCache | None = None, replay: bool = False,
        budget: int | None = None, moderator: Moderator | None = None, observer: Observer | None = None) -> ActResult:
    """Apply one player verb. Code makes every choice; with a gateway and the brain on, the model words what the people
    say, and anything it gets wrong, or can't answer, falls back to the template lines."""
    _check(w, verb, target)
    if verb == "ask" and topic not in C.TOPICS:
        raise NotAllowed("Ask about this morning or the ring")
    mind = Mind(gateway if w.brain_mode == "model" else None, voice.VALIDATOR, cache, replay, budget, moderator,
                observer)
    start = len(w.ledger)
    assert target is not None  # every manor verb names someone or somewhere, and _check found it
    if verb == "ask":
        assert topic is not None
        replies = _ask(w, mind, target, topic)
    elif verb == "request_questioning":
        replies = _question(w, mind, target)
    elif verb == "accuse":
        replies = _accuse(w, mind, target)
    else:
        replies = _move(w, mind, target)
    if mind.asked:
        w.counters["model_calls"] = w.counters.get("model_calls", 0) + mind.asked
    return ActResult(list(w.ledger)[start:], replies, mind.asked)


def _ask(w: World, mind: Mind, npc: str, topic: str) -> list[dict]:
    w.player["asked"] = sorted({*w.player["asked"], f"{npc}:{topic}"})
    if npc == C.MAID:
        sable = w.npcs[C.MAID]
        sable.drives["fear"] = min(10, sable.drives.get("fear", 0) + (2 if topic == "morning" else 1))
        if topic == "morning":
            return [_sable_answers(w, mind, "player", sable.loc)]
        return voice.deliver(w, mind, [Speech(C.MAID, "asked_ring", voice.line(C.MAID, "ring", [_latest(w, C.MAID)]),
                                              "The player asks you about Lady Vane's missing signet ring.")])
    if npc == C.BUTLER:
        if topic == "morning":
            told, _ = log_statement(w, "tell", C.BUTLER, "player", w.npcs[C.BUTLER].loc, C.THE_TRUTH, [])
            saw = _held(w, C.BUTLER, C.THE_TRUTH)
            said = voice.line(C.BUTLER, "morning", [told.id, saw.id])
            return voice.deliver(w, mind, [Speech(C.BUTLER, "asked_morning", said,
                                                  "The player asks what you saw this morning. You always tell the "
                                                  "truth.")])
        return voice.deliver(w, mind, [Speech(C.BUTLER, "asked_ring", voice.line(C.BUTLER, "ring", [_latest(w, C.BUTLER)]),
                                              "The player asks you about Lady Vane's missing signet ring.")])
    # Lady Vane tells what she believes.
    if topic == "ring":
        said = voice.line(C.OWNER, "ring", [_latest(w, C.OWNER)])
        return voice.deliver(w, mind, [Speech(C.OWNER, "asked_ring", said,
                                              "The player, who has come to find your missing signet ring, asks you "
                                              "about it.")])
    alibi = _held(w, C.OWNER, C.THE_ALIBI)
    if alibi.active:
        said = voice.line(C.OWNER, "morning", [alibi.id])
    else:
        said = voice.line(C.OWNER, "morning_doubt", [_held(w, C.OWNER, C.THE_TRUTH).id])  # what broke the alibi
    return voice.deliver(w, mind, [Speech(C.OWNER, "asked_morning", said,
                                          "The player asks what you know of this morning.")])


def _sable_answers(w: World, mind: Mind, listener: str, loc: str) -> dict:
    """Asked where she was at mid-morning, Sable lies once she is frightened enough, and deflects before that. A lie
    is an action code chose, logged false."""
    sable = w.npcs[C.MAID]
    knows = _held(w, C.MAID, C.THE_TRUTH)  # she knows where she really was
    options = {"deflect": 3}
    if sable.drives.get("fear", 0) >= C.FEAR_TO_LIE:
        options = {"deceive:alibi": sable.drives["fear"] + 2, "deflect": 3}
    asker = "The player asks" if listener == "player" else "Lady Vane asks you, in front of the player,"
    situation = f"{asker} where you were at mid-morning."

    def line_for(choice: str):
        if choice.startswith("deceive"):
            return voice.line(C.MAID, "deceive", [SAID, knows.id])
        return voice.line(C.MAID, "deflect", [knows.id])

    u = _decide(w, mind, C.MAID, options, line_for, situation,
                {"deceive:alibi": words.claim_text(C.THE_ALIBI, about=True)})
    assert u.action is not None  # a decision always carries one of the options
    reason = f"{u.action} pulls {options[u.action]}" + (f"; {u.note}" if u.note else "")
    if u.action == "deceive:alibi":
        told, cites = log_statement(w, "tell", C.MAID, listener, loc, C.THE_ALIBI, u.cites)
        if listener in w.npcs:
            _hear(w, listener, C.THE_ALIBI, C.MAID, told)
        d = w.decisions.record(DECIDE, C.MAID, w.phase, "asked_morning", allowed=list(options), chosen=u.action,
                               line=u.line, cites=cites, reason=reason, source=u.source, asserted=told.id)
    else:
        d = w.decisions.record(DECIDE, C.MAID, w.phase, "asked_morning", allowed=list(options), chosen=u.action,
                               line=u.line, cites=u.cites, reason=reason, source=u.source)
    return voice.reply(d)


def _held(w: World, npc: str, claim) -> Belief:
    """A belief the case is built on. new_world gives each of these people theirs, so it is always there."""
    belief = w.beliefs.get(npc, claim)
    if belief is None:
        raise LookupError(f"{npc} has no belief about {claim}")
    return belief


def _decide(w: World, mind: Mind, npc: str, options: Mapping[str, float], line_for, situation: str,
            asserts: dict[str, str]) -> Utterance:
    """The utility brain's choice, voiced by the model if its reply passes, else by the template line."""
    choice = UtilityBrain().choose(npc, options)
    line, cites = line_for(choice) or (None, [])
    fallback = Utterance(choice, line, cites, "fallback")
    pack = voice.pack_for(w, npc, situation, choice, asserts.get(choice))
    return mind.act(pack, fallback) if mind.active else fallback


def _question(w: World, mind: Mind, npc: str) -> list[dict]:
    """Lady Vane questions someone before the player. Pell's testimony can break Sable's alibi."""
    w.ledger.append(w.phase, "question", C.OWNER, npc, "hall")
    if npc == C.BUTLER:
        testified, _ = log_statement(w, "testify", C.BUTLER, C.OWNER, "hall", C.THE_TRUTH, [])
        _hear(w, C.OWNER, C.THE_TRUTH, C.BUTLER, testified)
        saw, heard = _held(w, C.BUTLER, C.THE_TRUTH), _held(w, C.OWNER, C.THE_TRUTH)
        return voice.deliver(w, mind, [
            Speech(C.BUTLER, "testify", voice.line(C.BUTLER, "testify", [testified.id, saw.id]),
                   "Lady Vane asks you, in front of the player, what you saw this morning. You always tell the truth."),
            Speech(C.OWNER, "questioned", voice.line(C.OWNER, "questioned", [heard.id, testified.id]),
                   "You have just questioned Pell in front of the player, and he told you he saw Sable leave the study "
                   "at mid-morning. Sable told you she was in the kitchen then, so she lied to you, and you no longer "
                   "believe her. Say so to the player."),
        ])
    sable = w.npcs[C.MAID]
    sable.drives["fear"] = min(10, sable.drives.get("fear", 0) + 2)
    replies = [_sable_answers(w, mind, C.OWNER, "hall")]
    return replies + voice.deliver(w, mind, [Speech(C.OWNER, "questioned_sable",
                                                    voice.line(C.OWNER, "questioned_sable", [_latest(w, C.OWNER)]),
                                                    "You have just questioned Sable about this morning.")])


def _hear(w: World, npc: str, claim: Claim, source: str, event: Event) -> list:
    """`npc` is told `claim` by `source`, believing it as far as it trusts them; then settles any contradiction."""
    w.beliefs.add_evidence(npc, claim, C.conf_from_trust(w.npcs[npc].trust_in.get(source, 0)), source, event.id,
                           w.phase)
    return _reconcile(w, npc, claim)


def _credit(w: World, npc: str, belief) -> int:
    """How far the NPC trusts a belief's best source: what it saw itself beats anyone's word."""
    trust = w.npcs[npc].trust_in
    return max(5 if e.source in ("self", "witnessed") else trust.get(e.source, 0) for e in belief.evidence)


def _reconcile(w: World, npc: str, claim: Claim) -> list:
    """Two places at once can't both be true: the NPC drops whichever it has from the less trusted source, and
    trusts whoever told it that one less. Returns the beliefs it retracted."""
    new = w.beliefs.get(npc, claim)
    if new is None or not new.active:
        return []
    retracted = []
    for old in w.beliefs.for_npc(npc):
        if old is new or not old.active or not C.contradicts(old.claim, new.claim):
            continue
        loser = old if _credit(w, npc, new) > _credit(w, npc, old) else new if _credit(w, npc, old) > _credit(
            w, npc, new) else None
        if loser is None:
            continue
        w.beliefs.retract(loser)
        retracted.append(loser)
        for src in {e.source for e in loser.evidence}:
            if src in w.npcs[npc].trust_in:
                w.npcs[npc].trust_in[src] -= C.CONTRADICTED
    return retracted


def _accuse(w: World, mind: Mind, npc: str) -> list[dict]:
    """The verdict: won only if Lady Vane believes Pell's account and has dropped Sable's alibi."""
    accused = w.ledger.append(w.phase, "accuse", "player", npc, w.player["loc"])
    alibi = _held(w, C.OWNER, C.THE_ALIBI)
    solved = npc == C.MAID and w.beliefs.conf(C.OWNER, C.THE_TRUTH) >= C.BELIEVED and not alibi.active
    w.status, w.ended_at = (WON if solved else LOST), w.phase
    if solved:
        key, cites = "won", [_held(w, C.OWNER, C.THE_TRUTH).id, accused.id]  # solved means she believes it
        situation = ("The player accuses Sable of taking your ring. Pell saw her leave the study at mid-morning, so "
                     "she lied to you about the kitchen. You accept the accusation: order Sable to give back your "
                     "ring.")
    elif npc == C.MAID:
        key, cites = "lost_alibi", [alibi.id, accused.id]
        situation = ("The player accuses Sable of taking your ring, but as far as you know she was in the kitchen at "
                     "mid-morning. You reject the accusation and dismiss the player.")
    else:
        key, cites = "lost_innocent", [accused.id]
        situation = ("The player accuses Pell, your butler of thirty years, of taking your ring. You reject the "
                     "accusation and dismiss the player.")
    w.player["outcome"] = OUTCOMES[key]
    return voice.deliver(w, mind, [Speech(C.OWNER, f"accused_{npc}", voice.line(C.OWNER, key, cites), situation)])


def _move(w: World, mind: Mind, room: str) -> list[dict]:
    """Walking to another room takes the rest of the phase. At evening the case is lost."""
    frm, w.player["loc"] = w.player["loc"], room
    w.ledger.append(w.phase, "move", "player", room, frm)
    w.phase += 1
    if w.phase < C.DEADLINE:
        return []
    w.status, w.ended_at = LOST, w.phase
    sent = w.ledger.append(w.phase, "constable", C.OWNER, None, "hall")
    w.player["outcome"] = OUTCOMES["constable"]
    if room != "hall":
        return []
    return voice.deliver(w, mind, [Speech(C.OWNER, "constable", voice.line(C.OWNER, "constable", [sent.id]),
                                          "Evening has come and your ring is still missing; you have sent for the "
                                          "constable.")])


def _latest(w: World, npc: str) -> str | None:
    """The most recent event the NPC knows, for a line with nothing better to cite."""
    return next((e.id for e in reversed(list(w.ledger)) if voice.knows(w, npc, e.id)), None)
