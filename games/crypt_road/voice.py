"""NPC voices: the model's lines when there is one, template lines from cast.toml when not.

Every line, whoever writes it, cites at least one belief or ledger event its speaker knows, so the inspector's
why-chain can trace it. Each line starts as a Speech carrying its template fallback. deliver() asks the model for
all of a moment's lines at once, keeps only the replies that pass the validator, and records the result.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from games.crypt_road import content as C
from games.crypt_road import words
from thespis.beliefs import Belief
from thespis.decisions import REACT
from thespis.expression import Mind, StatePack, Utterance, Validator
from thespis.ledger import Claim, Event
from thespis.retriever import TopKRetriever
from thespis.world import World

# Every way a line can name a character or a place, mapped to its game id, for the validator.
VOCABULARY = {
    "kael": "kael", "brenna": "brenna", "captain": "brenna", "odo": "odo", "peddler": "odo",
    "mags": "mags", "innkeeper": "mags",
    "tavern": "tavern", "lantern": "tavern", "market": "market", "guard post": "guard_post", "gate": "guard_post",
    "bridge": "bridge", "crypt": "crypt",
}
_TEENS = ("ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen").split()
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60}
_UNITS = ("one two three four five six seven eight nine").split()
_NUMBER = re.compile(rf"\b(\d+)\b|\b({'|'.join(_TENS)})(?:[- ]({'|'.join(_UNITS)}))?\b|\b({'|'.join(_TEENS)})\b",
                     re.IGNORECASE)


def numbers(text: str) -> set[int]:
    """Every amount a line states, in digits or in words from ten up (smaller words, like "no one", are rarely sums)."""
    out = set()
    for digits, tens, unit, teen in _NUMBER.findall(text):
        if digits:
            out.add(int(digits))
        elif tens:
            out.add(_TENS[tens.lower()] + (_UNITS.index(unit.lower()) + 1 if unit else 0))
        else:
            out.add(10 + _TEENS.index(teen.lower()))
    return out


class CryptRoadValidator(Validator):
    """The core checks, plus one for haggling (#36): any sum Brenna names must be the offer or her price."""

    def problem(self, data: dict, pack: StatePack, kind: str) -> str | None:
        why = super().problem(data, pack, kind)
        if why is None and pack.action and pack.action["id"].partition(":")[0] in ("counter", "refuse"):
            stray = numbers(data["line"]) - numbers(pack.situation)
            if stray:
                return f"names {', '.join(map(str, sorted(stray)))}, neither the offer nor the price"
        return why


VALIDATOR = CryptRoadValidator(VOCABULARY)
RETRIEVER = TopKRetriever(5)
KNOWN_EVENTS = 5
THRESHOLDS = {"grudge": (4, 5), "respect": (4,), "fear": (4,)}  # crossing one makes the rival stop and think


@dataclass(frozen=True)
class View:
    """What NPCs perceive of the player while a phase plays out: where the player started it. A player who is
    moving is on the road until the next phase, so that move isn't visible yet (`hidden`)."""

    player_at: str
    hidden: frozenset[str] = frozenset()


def _view(w: World, view: View | None) -> View:
    return view or View(w.player["loc"])


@dataclass
class Speech:
    npc: str
    trigger: str
    said: tuple[str, list[str]] | None  # the fallback line and its cites; None means the NPC stays silent
    situation: str  # what just happened, from the NPC's point of view, for the model
    untrusted: tuple[str, ...] = ()  # what the player wrote that the situation quotes, for moderation


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


def line(npc: str, key: str, cites: Sequence[str | None], **fmt) -> tuple[str, list[str]] | None:
    """Fill a template, or None when there is no template or nothing to cite: no line without a source."""
    text, known = template(npc, key), [c for c in cites if c]
    if text is None or not known:
        return None
    return text.format(**fmt), list(dict.fromkeys(known))


def _top(w: World, npc: str, about: tuple[str, ...]) -> Belief | None:
    held = [b for b in w.beliefs.for_npc(npc) if b.active and b.conf >= C.CRIME_CONF
            and any(b.claim.mentions(x) for x in about)]
    held.sort(key=lambda b: (C.GOSSIP_PRIORITY.get(b.claim.pred, 0), b.conf), reverse=True)
    return held[0] if held else None


def _about(c: Claim, speaker: str | None = None) -> str:
    return words.claim_text(c, speaker, player=words.ABOUT_PLAYER)


def _name(who: str) -> str:
    return {"odo": "the peddler", "mags": "the innkeeper", "brenna": "the Captain", "player": "you"}.get(
        who, C.short_name(who))


# ---------------------------------------------------------------- the state pack
PERSONA_MAX = 300  # characters in an edited persona (#39)


def persona_of(w: World, npc_id: str) -> str:
    """The persona the model voices: this session's edit (#39), or the one in cast.toml."""
    return w.npcs[npc_id].flags.get("persona") or C.load_cast()["npc"][npc_id]["persona"]


def describe(option: str, w: World, npc: str) -> str:
    """One line on what an action does, for the model."""
    kind, _, who = option.partition(":")
    nxt = C.next_stop(w.npcs[npc].loc)
    return {
        "go_to": f"walk on towards the relic, to {C.STOP_NAMES[nxt]}" if nxt else "walk on",
        "wait": "stay where you are and do nothing this phase",
        "take_relic": "take the relic and win the race",
        "accuse": "tell the Captain what the player did to you; she trusts you and will stop them at the gate",
        "share_drink": "stay this phase to share a drink with the player and tell them something useful",
        "detain": f"have the sergeant hold {C.short_name(who)} for two phases",
        "question": f"ask {C.short_name(who)} whether the claim about them is true",
        "counter": f"name your price: {who} coins, and not a coin less",
        "refuse": "turn the offer down and hear no more offers for now",
    }.get(kind, option.replace("_", " "))


def pack_for(w: World, npc_id: str, situation: str, action: str | None = None, view: View | None = None,
             untrusted: tuple[str, ...] = ()) -> StatePack:
    """Everything the model may know when it speaks for this NPC, and nothing more. Never whether a belief is true.
    `action` is what code decided the NPC does, if it is acting. `untrusted` is what the player wrote that the
    situation quotes; a persona the player edited counts too."""
    npc, cast, view = w.npcs[npc_id], C.load_cast()["npc"][npc_id], _view(w, view)
    others = [n.id for n in w.npcs_at(npc.loc) if n.id != npc_id]
    if view.player_at == npc.loc:
        others.append("player")
    beliefs = RETRIEVER.beliefs(w.beliefs, npc_id)  # active only: a retracted belief is never offered as fact
    known = [e for e in reversed(list(w.ledger))
             if e.id not in view.hidden and knows(w, npc_id, e.id)][:KNOWN_EVENTS][::-1]
    names = {npc_id, *others, *C.STOPS}  # everyone knows the road
    names |= VALIDATOR.named(situation)  # and may name whoever the player just mentioned
    for b in beliefs:
        names |= {b.claim.a, b.claim.b}
    for e in known:
        names |= {e.actor, e.target}
        if e.claim:
            names |= {e.claim.a, e.claim.b}
    if action:
        names.add(action.partition(":")[2])
    return StatePack(
        npc=npc_id, name=cast["name"], persona=persona_of(w, npc_id), goal=cast["goal"], situation=situation,
        here=[words.who(x, player=words.ABOUT_PLAYER) for x in others],
        drives=dict(npc.drives), trust_in=dict(npc.trust_in),
        beliefs=[{"id": b.id, "claim": _about(b.claim), "conf": b.conf,
                  "from": sorted({e.source for e in b.evidence})} for b in beliefs],
        events=[{"id": e.id, "what": words.sentence(e, words.ABOUT_PLAYER)} for e in known],
        action={"id": action, "does": describe(action, w, npc_id)} if action else None,
        names={x for x in names if x and x != "player"},
        setting=f"You are at {C.STOP_NAMES[npc.loc]}. The road runs east: "
                + ", ".join(C.STOP_NAMES[s] for s in C.STOPS) + ". The relic lies in the crypt.",
        untrusted=[t for t in (npc.flags.get("persona"), *untrusted) if t],
    )


def deliver(w: World, mind: Mind, speeches: list[Speech]) -> list[dict]:
    """Voice a moment's lines, all model calls in parallel, and record each as a react decision."""
    voiced = [(s, s.said) for s in speeches if s.said]
    speeches = [s for s, _ in voiced]
    fallbacks = [Utterance(None, said[0], said[1], "fallback") for _, said in voiced]
    if mind.active:
        spoken = mind.react_many([(pack_for(w, s.npc, s.situation, untrusted=s.untrusted), f)
                                  for s, f in zip(speeches, fallbacks)])
    else:
        spoken = fallbacks
    replies = []
    for s, u in zip(speeches, spoken):
        reason = f"{s.trigger}; {u.note}" if u.note else s.trigger
        d = w.decisions.record(REACT, s.npc, w.phase, s.trigger, line=u.line, cites=u.cites, reason=reason,
                               source=u.source)
        replies.append({"decision": d.id, "npc": s.npc, "line": u.line, "cites": u.cites, "source": u.source})
    return replies


# ---------------------------------------------------------------- reactions to the player's verb
def react(w: World, mind: Mind, verb: str, target: str | None, events: list[Event], claim: Claim | None = None,
          text: str | None = None) -> list[dict]:
    """Lines spoken straight after a player verb, before any tick."""
    last = events[-1].id if events else None
    speeches: list[Speech] = []
    if verb == "insult":
        assert target is not None  # the rules found someone here to insult
        speeches.append(Speech(target, "insulted", line(target, "insulted", [last]), "The player just insulted you."))
    elif verb == "challenge":
        won = w.pending == "duel_won"
        key = "beaten" if won else "victor"
        what = "The player just beat you in a duel." if won else "You just beat the player in a duel."
        speeches.append(Speech(C.RIVAL, key, line(C.RIVAL, key, [last]), what))
    elif verb in ("humiliate", "spare"):
        key = "robbed" if verb == "humiliate" else "spared"
        what = ("The player beat you, then humiliated you and took your purse." if verb == "humiliate"
                else "The player beat you in a duel, then spared you.")
        speeches.append(Speech(C.RIVAL, key, line(C.RIVAL, key, [last]), what))
    elif verb == "bribe" and events and events[0].verb == "bribe":  # she took it; a haggle speaks through rules._offer
        paid = events[0].amount
        speeches.append(Speech(C.GUARD, "bribe", line(C.GUARD, "bribe", [last], amount=paid),
                               f"The player just paid you a {paid}-coin fine."))
    elif verb == "talk":
        assert target is not None
        speeches.append(Speech(target, "talk", _talk(w, target), f'The player says to you: "{text or ""}"',
                               (text,) if text else ()))
    elif verb == "tell_claim":
        assert target is not None and claim is not None
        speeches.extend(_told(w, target, claim, events))
    return deliver(w, mind, speeches)


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


def _told(w: World, listener: str, claim: Claim, events: list[Event]) -> list[Speech]:
    told = events[0]
    what = f"The player just told you that {_about(claim)}."
    if listener == C.GUARD:
        key = "told_believed" if w.beliefs.conf(C.GUARD, claim) >= C.CRIME_CONF else "told_doubted"
        out = [Speech(C.GUARD, "told", line(C.GUARD, key, [told.id]), what)]
    else:
        out = [Speech(listener, "told", line(listener, "told", [told.id]), what)]
    if not told.truth:  # a lie, overheard by the NPC it names
        lied = Claim("lied", "player", C.RIVAL)
        b = w.beliefs.get(C.RIVAL, lied)
        if b is not None and listener != C.RIVAL and any(e.event == told.id for e in b.evidence):
            victim = claim.b if claim.a == C.RIVAL else claim.a
            out.append(Speech(C.RIVAL, "lied_about",
                              line(C.RIVAL, "lied_about", [told.id, b.id], victim=_name(victim)),
                              f"You just heard the player tell {C.short_name(listener)} that {_about(claim)}. "
                              "You know it never happened."))
    return out


# ---------------------------------------------------------------- decisions inside the tick
def decision_line(w: World, npc: str, chosen: str, claim: Claim | None = None,
                  view: View | None = None) -> tuple[str, list[str]] | None:
    """The template line that goes with an NPC's decision, if it says anything."""
    if npc == C.RIVAL:
        if chosen == "accuse:player" and claim is not None:
            return line(C.RIVAL, f"accuse_{claim.pred}", belief_cites(w.beliefs.get(C.RIVAL, claim)))
        if chosen == "share_drink":
            return line(C.RIVAL, "share_drink", belief_cites(w.beliefs.get(C.RIVAL, Claim("spared", "player", C.RIVAL))))
        if chosen == "go_to" and w.npcs[C.RIVAL].loc == _view(w, view).player_at:  # said to the player's face
            return line(C.RIVAL, "leaving", belief_cites(_top(w, C.RIVAL, ("player",))))
    if npc == C.GUARD and claim is not None:
        b = belief_cites(w.beliefs.get(C.GUARD, claim))
        if chosen.startswith("detain"):
            return line(C.GUARD, "detain", b, culprit=C.short_name(claim.a), victim=_name(claim.b))
        if chosen.startswith("question"):
            return line(C.GUARD, "question", b, witness=C.short_name(chosen.split(":", 1)[1]))
    return None


def haggle_line(chosen: str, offer: Event, amount: int, price: int) -> tuple[str, list[str]] | None:
    """Brenna's template answer to an offer under her price (#36): a counter or a refusal, citing the offer."""
    return line(C.GUARD, "refuse" if chosen == "refuse" else "counter", [offer.id], offer=amount, price=price)


def crossed_threshold(w: World, npc_id: str) -> bool:
    """Has a drive crossed one of its thresholds since this NPC last decided? Remembers the drives either way."""
    npc = w.npcs[npc_id]
    before = npc.flags.get("drives_seen") or C.load_cast()["npc"][npc_id]["drives"]
    npc.flags["drives_seen"] = dict(npc.drives)
    return any(min(before.get(k, 0), npc.drives.get(k, 0)) < t <= max(before.get(k, 0), npc.drives.get(k, 0))
               for k, ts in THRESHOLDS.items() for t in ts)


def testimony(w: World, mind: Mind, witness: str, claim: Claim, event: Event) -> None:
    """The witness's own words when the guard questions them; recorded inside the tick."""
    deliver(w, mind, [Speech(witness, "testify",
                             line(witness, "testify", [event.id], culprit=C.short_name(claim.a)),
                             f"Captain Brenna asks you whether {_about(claim)}. You know it never happened.")])


# ---------------------------------------------------------------- lines when a new phase starts
def phase_start(w: World, mind: Mind, moves: list[dict]) -> list[dict]:
    """Greetings when the player and an NPC newly share a stop: the guard at the gate, the rival on the road."""
    speeches: list[Speech] = []
    here = {n.id for n in w.npcs_at(w.player["loc"])}
    arrived = {m["who"] for m in moves}
    met = here if "player" in arrived else here & arrived
    if C.GUARD in met:
        guard = w.npcs[C.GUARD]
        b = _top(w, C.GUARD, ("player",))
        if guard.trust_in.get("player", 0) < 0 and b is not None and b.claim.a == "player":
            src = max(b.evidence, key=lambda e: e.conf).source
            said = line(C.GUARD, f"arrival_{b.claim.pred}", belief_cites(b), source=C.short_name(src))
            speeches.append(Speech(C.GUARD, "arrival", said or line(C.GUARD, "arrival", belief_cites(b)),
                                   "The player has just arrived at your gate. You do not trust them."))
        else:
            arrival = next((e.id for e in reversed(list(w.ledger)) if e.verb == "move" and e.actor == "player"), None)
            speeches.append(Speech(C.GUARD, "arrival", line(C.GUARD, "arrival", [arrival] if arrival else []),
                                   "The player has just arrived at your gate."))
    if C.RIVAL in met and not w.npcs[C.RIVAL].frozen(w.phase):
        kael = w.npcs[C.RIVAL]
        accused = next((e for e in reversed(list(w.ledger)) if e.verb == "accuse" and e.actor == C.RIVAL), None)
        where = C.STOP_NAMES[kael.loc]
        if kael.flags.get("accused") and accused is not None:
            speeches.append(Speech(C.RIVAL, "shares_stop", line(C.RIVAL, "reported", [accused.id]),
                                   f"You meet the player again at {where}, after reporting them to the Captain."))
        elif kael.drives["grudge"] >= 5:
            speeches.append(Speech(C.RIVAL, "shares_stop",
                                   line(C.RIVAL, "grudge_meet", belief_cites(_top(w, C.RIVAL, ("player",)))),
                                   f"You meet the player again at {where}."))
    return deliver(w, mind, speeches)
