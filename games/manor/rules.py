"""The manor mystery's rules (#35): the player's verbs, Sable's lies, Lady Vane's questioning, and the verdict.

Built on the Thespis core with one addition, NPC deception (thespis.deception). Sable's lie is an action these rules
choose once she is frightened enough, and the model words it; a lie goes into the ledger with its real truth, false,
so the inspector can show it and the why-chain can trace it.

The solve: ask Sable about the morning (she lies), ask Pell (he saw her leave the study), have Lady Vane question
Pell (his testimony breaks the alibi), then accuse Sable before evening.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from games.manor import claims, voice
from games.manor import content as C
from games.manor.voice import Speech
from thespis.affordances import decide
from thespis.beliefs import Belief, credence, reconcile
from thespis.brain import UtilityBrain
from thespis.claims import ClaimChecking
from thespis.deception import SAID, log_statement
from thespis.expression import Mind, Observer, ReplyCache
from thespis.gateway import ModelGateway
from thespis.ledger import Claim, Event
from thespis.moderation import Moderator
from thespis.play import NotAllowed, Verbs, check, count_calls, open_mind
from thespis.world import LOST, PLAYING, WON, World

__all__ = ["NotAllowed"]

OUTCOMES = C.CAST.data["outcomes"]


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
    verbs = Verbs("The case is closed" if w.status != PLAYING else None)
    add = verbs.add

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
    return verbs.options


# ---------------------------------------------------------------- acting
def act(w: World, verb: str, target: str | None = None, topic: str | None = None,
        gateway: ModelGateway | None = None, cache: ReplyCache | None = None, replay: bool = False,
        budget: int | None = None, moderator: Moderator | None = None, observer: Observer | None = None,
        checking: ClaimChecking | None = None) -> ActResult:
    """Apply one player verb. Code makes every choice; with a gateway and the brain on, the model words what the people
    say, and anything it gets wrong, or can't answer, falls back to the template lines."""
    check(allowed(w), verb, target)
    if verb == "ask" and topic not in C.TOPICS:
        raise NotAllowed("Ask about this morning or the ring")
    mind = open_mind(w, voice.VALIDATOR, gateway, cache, replay, budget, moderator, observer,
                     claims.check(w, checking, gateway) if checking and gateway else None)
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
    return ActResult(list(w.ledger)[start:], replies, count_calls(w, mind))


def _speech(npc: str, trigger: str, key: str, cites: list, situation: str | None = None, **fmt) -> Speech:
    """`npc`'s template `key`, citing `cites`, in the situation cast.toml gives for `situation` (or the trigger)."""
    return Speech(npc, trigger, voice.line(npc, key, cites), C.CAST.text("situations", situation or trigger, **fmt))


def _say(w: World, mind: Mind, *speech, **fmt) -> list[dict]:
    return voice.deliver(w, mind, [_speech(*speech, **fmt)])


def _ask(w: World, mind: Mind, npc: str, topic: str) -> list[dict]:
    w.player["asked"] = sorted({*w.player["asked"], f"{npc}:{topic}"})
    if npc == C.MAID:
        sable = w.npcs[C.MAID]
        sable.drives["fear"] = min(10, sable.drives.get("fear", 0) + (2 if topic == "morning" else 1))
        if topic == "morning":
            return [_sable_answers(w, mind, "player", sable.loc)]
        return _say(w, mind, C.MAID, "asked_ring", "ring", [_latest(w, C.MAID)])
    if npc == C.BUTLER:
        if topic == "morning":
            told, _ = log_statement(w, "tell", C.BUTLER, "player", w.npcs[C.BUTLER].loc, C.THE_TRUTH, [])
            saw = _held(w, C.BUTLER, C.THE_TRUTH)
            return _say(w, mind, C.BUTLER, "asked_morning", "morning", [told.id, saw.id], "pell_asked_morning")
        return _say(w, mind, C.BUTLER, "asked_ring", "ring", [_latest(w, C.BUTLER)])
    # Lady Vane tells what she believes.
    if topic == "ring":
        return _say(w, mind, C.OWNER, "asked_ring", "ring", [_latest(w, C.OWNER)], "vane_asked_ring")
    alibi = _held(w, C.OWNER, C.THE_ALIBI)
    key, cite = ("morning", alibi.id) if alibi.active else ("morning_doubt", _held(w, C.OWNER, C.THE_TRUTH).id)
    return _say(w, mind, C.OWNER, "asked_morning", key, [cite], "vane_asked_morning")  # morning_doubt: what broke it


def _sable_answers(w: World, mind: Mind, listener: str, loc: str) -> dict:
    """Where Sable says she was at mid-morning. A lie is an action code chose, logged false."""
    knows = _held(w, C.MAID, C.THE_TRUTH)  # she knows where she really was
    asker = C.CAST.text("situations", "asker_player" if listener == "player" else "asker_vane")

    def line_for(choice: str):
        if choice.startswith("deceive"):
            return voice.line(C.MAID, "deceive", [SAID, knows.id])
        return voice.line(C.MAID, "deflect", [knows.id])

    def settle(choice: str, u) -> dict:
        if choice != "deceive:alibi":
            return {}
        told, cites = log_statement(w, "tell", C.MAID, listener, loc, C.THE_ALIBI, u.cites)
        if listener in w.npcs:
            _hear(w, listener, C.THE_ALIBI, C.MAID, told)
        return {"cites": cites, "asserted": told.id}

    # Asked about the morning, she lies once she is frightened enough and deflects before that (cast.toml).
    sable = C.CHOICES[C.MAID, "asked_morning"]
    choices = sable.options(w, voice.VOICE.view(w))
    d = decide(w, mind, voice.VOICE, UtilityBrain(), C.MAID, "asked_morning", choices, line_for,
               C.CAST.text("situations", "sable_asked_morning", asker=asker), asserts=sable.asserts(),
               scores="pulls", settle=settle)
    return voice.reply(d)


def _held(w: World, npc: str, claim) -> Belief:
    """A belief the case is built on. new_world gives each of these people theirs, so it is always there."""
    belief = w.beliefs.get(npc, claim)
    if belief is None:
        raise LookupError(f"{npc} has no belief about {claim}")
    return belief


def _question(w: World, mind: Mind, npc: str) -> list[dict]:
    """Lady Vane questions someone before the player. Pell's testimony can break Sable's alibi."""
    w.ledger.append(w.phase, "question", C.OWNER, npc, "hall")
    if npc == C.BUTLER:
        testified, _ = log_statement(w, "testify", C.BUTLER, C.OWNER, "hall", C.THE_TRUTH, [])
        _hear(w, C.OWNER, C.THE_TRUTH, C.BUTLER, testified)
        saw, heard = _held(w, C.BUTLER, C.THE_TRUTH), _held(w, C.OWNER, C.THE_TRUTH)
        return voice.deliver(w, mind, [_speech(C.BUTLER, "testify", "testify", [testified.id, saw.id]),
                                       _speech(C.OWNER, "questioned", "questioned", [heard.id, testified.id])])
    sable = w.npcs[C.MAID]
    sable.drives["fear"] = min(10, sable.drives.get("fear", 0) + 2)
    replies = [_sable_answers(w, mind, C.OWNER, "hall")]
    return replies + _say(w, mind, C.OWNER, "questioned_sable", "questioned_sable", [_latest(w, C.OWNER)])


def _hear(w: World, npc: str, claim: Claim, source: str, event: Event) -> list:
    """`npc` is told `claim` by `source`, believing it as far as it trusts them; then settles any contradiction: two
    places at once can't both be true (thespis.beliefs.reconcile)."""
    trust = w.npcs[npc].trust_in
    w.beliefs.add_evidence(npc, claim, credence(trust.get(source, 0)), source, event.id, w.phase)
    return reconcile(w.beliefs, npc, claim, trust, w.phase, C.contradicts, C.CONTRADICTED)


def _accuse(w: World, mind: Mind, npc: str) -> list[dict]:
    """The verdict: won only if Lady Vane believes Pell's account and has dropped Sable's alibi."""
    accused = w.ledger.append(w.phase, "accuse", "player", npc, w.player["loc"])
    alibi = _held(w, C.OWNER, C.THE_ALIBI)
    solved = npc == C.MAID and w.beliefs.conf(C.OWNER, C.THE_TRUTH) >= C.BELIEVED and not alibi.active
    w.status, w.ended_at = (WON if solved else LOST), w.phase
    if solved:
        key, cites = "won", [_held(w, C.OWNER, C.THE_TRUTH).id, accused.id]  # solved means she believes it
    elif npc == C.MAID:
        key, cites = "lost_alibi", [alibi.id, accused.id]
    else:
        key, cites = "lost_innocent", [accused.id]
    w.player["outcome"] = OUTCOMES[key]
    return _say(w, mind, C.OWNER, f"accused_{npc}", key, cites, key)


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
    return _say(w, mind, C.OWNER, "constable", "constable", [sent.id])


def _latest(w: World, npc: str) -> str | None:
    """The most recent event the NPC knows, for a line with nothing better to cite."""
    return voice.VOICE.latest(w, npc)
