"""NPC voices: the model's lines when there is one, template lines from cast.toml when not.

The core (thespis.voice) builds each state pack and delivers each moment's lines; this module says which line each
moment calls for, and what the Crypt Road's NPCs see and say.
"""

from __future__ import annotations

import re

from games.crypt_road import content as C
from games.crypt_road import words
from thespis.beliefs import Belief
from thespis.expression import Mind, StatePack, Validator
from thespis.ledger import Claim, Event
from thespis.voice import Speech, View, Voice, belief_cites, top_belief
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
KNOWN_EVENTS = 5
THRESHOLDS = {"grudge": (4, 5), "respect": (4,), "fear": (4,)}  # crossing one makes the rival stop and think
# Lines with consequences, which meet the claim check (thespis.claims): accusations, arrests, questioning, deals,
# and testimony. The narrator's tellings are checked too (narrator.py).
STAKES_ACTIONS = ("accuse", "detain", "question", "counter", "refuse")
STAKES_TRIGGERS = ("testify",)


def line(npc: str, key: str, cites, **fmt) -> tuple[str, list[str]] | None:
    return C.CAST.line(npc, key, cites, **fmt)


def _top(w: World, npc: str, about: tuple[str, ...]) -> Belief | None:
    return top_belief(w, npc, about, C.CRIME_CONF, C.GOSSIP_PRIORITY)


def _about(c: Claim, speaker: str | None = None) -> str:
    return words.claim_text(c, speaker, player=words.ABOUT_PLAYER)


def _name(who: str) -> str:
    return {"odo": "the peddler", "mags": "the innkeeper", "brenna": "the Captain", "player": "you"}.get(
        who, C.short_name(who))


# ---------------------------------------------------------------- the state pack
PERSONA_MAX = 300  # characters in an edited persona (#39)


def persona_of(w: World, npc_id: str) -> str:
    """The persona the model voices: this session's edit (#39), or the one in cast.toml."""
    return C.CAST.persona(w, npc_id)


def describe(w: World, npc: str, option: str) -> str:
    """One line on what an action does, for the model."""
    kind, _, who = option.partition(":")
    nxt = C.next_stop(w.npcs[npc].loc)
    kind = "go_to_end" if kind == "go_to" and not nxt else kind
    if not C.CAST.has("actions", kind):
        return option.replace("_", " ")
    return C.CAST.text("actions", kind, next=C.STOP_NAMES.get(nxt or "", ""),
                       who=who if kind == "counter" else C.short_name(who))


VOICE = Voice(
    cast=C.CAST, validator=VALIDATOR, claim_text=lambda c: _about(c),
    sentence=lambda e: words.sentence(e, words.ABOUT_PLAYER), who=lambda x: words.who(x, player=words.ABOUT_PLAYER),
    setting=lambda w, npc: f"You are at {C.STOP_NAMES[w.npcs[npc].loc]}. The road runs east: "
                           + ", ".join(C.STOP_NAMES[s] for s in C.STOPS) + ". The relic lies in the crypt.",
    describe=describe, places=C.STOPS, stakes={*STAKES_ACTIONS, *STAKES_TRIGGERS}, events=KNOWN_EVENTS)


def knows(w: World, npc: str, event_id: str) -> bool:
    """Can this NPC cite the event? It took part, it learned of it, or it happened at its stop."""
    return VOICE.knows(w, npc, event_id)


def pack_for(w: World, npc_id: str, situation: str, action: str | None = None, view: View | None = None,
             untrusted: tuple[str, ...] = (), stakes: bool = False) -> StatePack:
    """Everything the model may know when it speaks for this NPC (thespis.voice.Voice.pack)."""
    return VOICE.pack(w, npc_id, situation, action, view=view, untrusted=untrusted, stakes=stakes)


def deliver(w: World, mind: Mind, speeches: list[Speech]) -> list[dict]:
    return VOICE.deliver(w, mind, speeches)


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
        if chosen == "go_to" and w.npcs[C.RIVAL].loc == VOICE.view(w, view).player_at:  # said to the player's face
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
    before = npc.flags.get("drives_seen") or C.CAST.npc(npc_id)["drives"]
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
