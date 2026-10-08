"""Affordances: the actions an NPC may take, declared once, and the decision that picks one.

An Affordance is available when its test passes and scored by its utility, both reading the world, the NPC and what
it can see of the player. Code chooses (the brain, by utility; the first declared wins a tie), the NPC's Voice words
it, and the choice is recorded as a decision with its reason. The game then applies the choice's effects.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from thespis.brain import Brain
from thespis.decisions import DECIDE, Decision
from thespis.expression import Mind, Utterance
from thespis.ledger import Claim
from thespis.minds import NPC
from thespis.voice import View, Voice
from thespis.world import World

Test = Callable[[World, NPC, View], bool]
Score = Callable[[World, NPC, View], float]


def always(w: World, npc: NPC, view: View) -> bool:
    return True


@dataclass(frozen=True)
class Affordance:
    id: str
    utility: Score
    when: Test = always


def options(w: World, npc: str, affordances: Iterable[Affordance], view: View) -> dict[str, float]:
    """The actions open to the NPC now, with their utilities, in the order they were declared."""
    n = w.npcs[npc]
    return {a.id: a.utility(w, n, view) for a in affordances if a.when(w, n, view)}


def decide(w: World, mind: Mind, voice: Voice, brain: Brain, npc: str, trigger: str, choices: Mapping[str, float],
           line_for: Callable[[str], tuple[str, list[str]] | None], situation: str, reason: str | None = None,
           ask: bool = True, view: View | None = None, asserts: Mapping[str, Claim] | None = None,
           scores: str = "scores", settle: Callable[[str, Utterance], dict] | None = None) -> Decision:
    """Choose among `choices` by code, voice the choice, and record it.

    The line is the model's words for it if `ask` and its reply passes, else the template's (`line_for`). Without a
    `reason`, the utility explains the choice ("go_to scores 6"). An action that states a claim names it in
    `asserts`. `settle` applies what must happen before the record is written, such as logging a statement, and
    returns the record's fields it sets (its cites, the event asserted)."""
    choice = brain.choose(npc, choices)
    u = voice.act(w, mind, npc, choice, line_for, situation, (asserts or {}).get(choice), view, ask)
    base = reason or f"{choice} {scores} {choices[choice]}"
    fields = {"line": u.line, "cites": u.cites, "reason": f"{base}; {u.note}" if u.note else base,
              "source": u.source, **(settle(choice, u) if settle else {})}
    return w.decisions.record(DECIDE, npc, w.phase, trigger, allowed=list(choices), chosen=choice, **fields)
