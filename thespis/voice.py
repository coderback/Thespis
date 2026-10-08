"""How NPCs speak through the core: the state pack each line is spoken from, and the delivery of a moment's lines.

Every line, whoever writes it, cites at least one belief or ledger event its speaker knows, so the inspector's
why-chain can trace it. Each line starts as a Speech carrying its template fallback; `deliver` asks the model for all
of a moment's lines at once, keeps only the replies that pass, and records each as a react decision.

A game describes itself once, in a Voice: its cast, validator, words and perception rule. The pack follows the same
rule in every game: the model sees only what the NPC knows, never whether a belief is true.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field

from thespis import perception
from thespis.beliefs import Belief
from thespis.cast import Cast
from thespis.deception import asserting
from thespis.decisions import REACT, Decision
from thespis.expression import Mind, StatePack, Utterance, Validator
from thespis.ledger import Claim, Event
from thespis.perception import Sees, at_the_scene, known
from thespis.retriever import Retriever, TopKRetriever
from thespis.world import World


@dataclass(frozen=True)
class View:
    """What NPCs perceive of the player while a moment plays out: where the player is, and any events still
    `hidden` from them (a player who is moving is on the road until the phase ends)."""

    player_at: str
    hidden: frozenset[str] = frozenset()


@dataclass
class Speech:
    npc: str
    trigger: str
    said: tuple[str, list[str]] | None  # the fallback line and its cites; None means the NPC stays silent
    situation: str  # what just happened, from the NPC's point of view, for the model
    untrusted: tuple[str, ...] = ()  # what the player wrote that the situation quotes, for moderation


@dataclass
class Voice:
    """A game's way of speaking: everything the core needs to build its NPCs' state packs.

    `claim_text`, `sentence` and `who` put claims, events and people into words about the player ("the player"), as
    the model reads them. `setting` says where an NPC is. `describe` says what an action does, for DOING. Names a
    line may use come from what the pack mentions, or with `household`, every character and place. Lines spoken with
    an action or trigger in `stakes` meet the claim check.
    """

    cast: Cast
    validator: Validator
    claim_text: Callable[[Claim], str]
    sentence: Callable[[Event], str]
    who: Callable[[str], str]
    setting: Callable[[World, str], str]
    describe: Callable[[World, str, str], str]  # (world, npc, action id) -> what it does
    places: Collection[str] = ()
    sees: Sees = at_the_scene
    household: bool = False
    stakes: Collection[str] = ()  # actions (by id or kind) and triggers whose lines have consequences
    retriever: Retriever = field(default_factory=lambda: TopKRetriever(5))
    events: int = 5  # how many known events a pack shows

    def view(self, w: World, view: View | None = None) -> View:
        return view or View(w.player["loc"])

    def knows(self, w: World, npc: str, event_id: str) -> bool:
        return perception.knows(w, npc, event_id, self.sees)

    def latest(self, w: World, npc: str) -> str | None:
        """The most recent event the NPC knows, for a line with nothing better to cite."""
        return perception.latest(w, npc, self.sees)

    def pack(self, w: World, npc_id: str, situation: str, action: str | None = None, asserts: Claim | None = None,
             view: View | None = None, untrusted: Sequence[str] = (), stakes: bool = False) -> StatePack:
        """Everything the model may know when it speaks for this NPC, and nothing more. `action` is what code decided
        it does, if it is acting, and `asserts` the claim that action states. `untrusted` is what the player wrote
        that the situation quotes; a persona the player edited counts too."""
        npc, cast, view = w.npcs[npc_id], self.cast.npc(npc_id), self.view(w, view)
        others = [n.id for n in w.npcs_at(npc.loc) if n.id != npc_id]
        if view.player_at == npc.loc:
            others.append("player")
        others += [pid for pid, p in w.players.items() if p.get("loc") == npc.loc]  # the other players present
        beliefs = self.retriever.beliefs(w.beliefs, npc_id)  # active only: a retracted belief is never offered
        events = known(w, npc_id, self.events, self.sees, view.hidden)
        doing = {"id": action, "does": self.describe(w, npc_id, action)} if action else None
        if doing and asserts:
            doing = asserting(doing, self.claim_text(asserts))
        return StatePack(
            npc=npc_id, name=cast["name"], persona=self.cast.persona(w, npc_id), goal=cast["goal"],
            situation=situation, here=[self.who(x) for x in others], drives=dict(npc.drives),
            trust_in=dict(npc.trust_in),
            beliefs=[{"id": b.id, "claim": self.claim_text(b.claim), "conf": b.conf,
                      "from": sorted({e.source for e in b.evidence})} for b in beliefs],
            events=[{"id": e.id, "what": self.sentence(e)} for e in events],
            action=doing, asserted=asserts,
            names=self._names(w, npc_id, others, situation, beliefs, events, action),
            setting=self.setting(w, npc_id),
            untrusted=[t for t in (npc.flags.get("persona"), *untrusted) if t],
            stakes=stakes or bool(action and (action in self.stakes or action.partition(":")[0] in self.stakes)),
        )

    def _names(self, w: World, npc: str, others: list[str], situation: str, beliefs: list[Belief],
               events: list[Event], action: str | None) -> set[str]:
        if self.household:  # everyone knows everyone, and every room
            return set(self.places) | set(w.npcs)
        names = {npc, *others, *self.places}  # everyone knows the lie of the land
        names |= self.validator.named(situation)  # and may name whoever the situation mentions
        for b in beliefs:
            names |= {b.claim.a, b.claim.b}
        for e in events:
            names |= {e.actor, e.target}
            if e.claim:
                names |= {e.claim.a, e.claim.b}
        if action:
            names.add(action.partition(":")[2])
        return {x for x in names if x and x != "player"}

    def deliver(self, w: World, mind: Mind, speeches: list[Speech]) -> list[dict]:
        """Voice a moment's lines, the model calls in parallel, and record each as a react decision."""
        voiced = [s for s in speeches if s.said]
        fallbacks = [Utterance(None, s.said[0], s.said[1], "fallback") for s in voiced if s.said]
        if mind.active:
            spoken = mind.react_many([(self.pack(w, s.npc, s.situation, untrusted=s.untrusted,
                                                 stakes=s.trigger in self.stakes), f)
                                      for s, f in zip(voiced, fallbacks)])
        else:
            spoken = fallbacks
        replies = []
        for s, u in zip(voiced, spoken):
            reason = f"{s.trigger}; {u.note}" if u.note else s.trigger
            d = w.decisions.record(REACT, s.npc, w.phase, s.trigger, line=u.line, cites=u.cites, reason=reason,
                                   source=u.source)
            replies.append(reply(d))
        return replies

    def act(self, w: World, mind: Mind, npc: str, choice: str, line_for: Callable[[str], tuple[str, list[str]] | None],
            situation: str, asserts: Claim | None = None, view: View | None = None, ask: bool = True) -> Utterance:
        """The line that goes with what code decided `npc` does: the model's words for it if asked and its reply
        passes, else the template's."""
        line, cites = line_for(choice) or (None, [])
        fallback = Utterance(choice, line, cites, "fallback")
        if not (ask and mind.active):
            return fallback
        return mind.act(self.pack(w, npc, situation, choice, asserts, view), fallback)

    def narrate(self, mind: Mind | None, events: list[Event], setting: str,
                telling: Callable[[list[Event]], str]) -> tuple[str, list[str], str]:
        """The narrator's telling of `events`, the ids it cites, and where it came from: llm, cache or fallback. The
        code's own `telling` is the fallback; the narrator may name only who and where the events mention."""
        text, ids = telling(events), [e.id for e in events]
        if not events or mind is None or not mind.active:
            return text, ids, "fallback"
        u = mind.narrate(self.narration(events, setting, telling), Utterance(None, text, ids, "fallback"))
        return u.line or text, u.cites, u.source

    def narration(self, events: list[Event], setting: str, telling: Callable[[list[Event]], str],
                  audience: str | None = None) -> StatePack:
        """The narrator's state pack for `events`: each told in the code's words, and only their names to use.
        `audience` names the one player it is told to, when there are several."""
        cast = self.cast.data["narrator"]
        names = set(self.places)
        for e in events:
            names |= {e.actor, e.target}
            if e.claim:
                names |= {e.claim.a, e.claim.b}
        return StatePack(
            npc="narrator", name=cast["name"], persona=cast["persona"], goal="Tell the story so far, truthfully",
            situation=f"Tell {audience or 'the player'} what happened since they last looked.", here=[], drives={},
            trust_in={},
            beliefs=[], events=[{"id": e.id, "what": telling([e])} for e in events],
            names={x for x in names if x and x != "player"}, setting=setting, stakes=True)


def reply(d: Decision) -> dict:
    """A spoken line as the client receives it."""
    return {"decision": d.id, "npc": d.npc, "line": d.line, "cites": d.cites, "source": d.source}


def belief_cites(b: Belief | None) -> list[str]:
    """A belief and the event its strongest evidence came from."""
    if b is None:
        return []
    best = max(b.evidence, key=lambda e: e.conf)
    return [b.id, best.event]


def top_belief(w: World, npc: str, about: Collection[str], threshold: float,
               priority: Mapping[str, int]) -> Belief | None:
    """The NPC's most pressing active belief about any of `about`: worst news first, then the surest."""
    held = [b for b in w.beliefs.for_npc(npc) if b.active and b.conf >= threshold
            and any(b.claim.mentions(x) for x in about)]
    held.sort(key=lambda b: (priority.get(b.claim.pred, 0), b.conf), reverse=True)
    return held[0] if held else None
