"""Playing a turn: which verbs the player may use, refusing the rest, and the Mind each action speaks through.

The verbs come in the docs/api.md shape: {verb, target, label, args, ends_phase, enabled, reason}, where a disabled
verb carries a reason a player can read. Every action opens one Mind, with the brain on or off as the session says,
and adds the model calls it made to the session's running total.
"""

from __future__ import annotations

from types import EllipsisType

from thespis.claims import ClaimCheck
from thespis.expression import Mind, Observer, ReplyCache, Validator
from thespis.gateway import ModelGateway
from thespis.moderation import Moderator
from thespis.world import World


class NotAllowed(Exception):
    """The verb isn't allowed right now. `reason` is readable by a player."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Verbs:
    """The verbs the player could use now. A `lock` (the race is over, a choice is pending) disables every verb that
    doesn't give its own reason."""

    def __init__(self, lock: str | None = None):
        self.lock = lock
        self.options: list[dict] = []

    def add(self, verb: str, target: str | None, label: str, args: dict, ends_phase: bool, ok: bool = True,
            why: str | None = None, reason: str | None | EllipsisType = ...) -> None:
        if reason is ...:
            reason = self.lock or (None if ok else why)
        self.options.append({"verb": verb, "target": target, "label": label, "args": args, "ends_phase": ends_phase,
                             "enabled": reason is None, "reason": reason})


def check(options: list[dict], verb: str, target: str | None) -> dict:
    """The option for this verb and target, or NotAllowed with the reason it's disabled, or that it isn't on offer."""
    for option in options:
        if option["verb"] == verb and option["target"] == target:
            if not option["enabled"]:
                raise NotAllowed(option["reason"])
            return option
    raise NotAllowed(" ".join(x for x in ("You can't", verb.replace("_", " "), target, "here") if x))


def open_mind(w: World, validator: Validator, gateway: ModelGateway | None = None, cache: ReplyCache | None = None,
              replay: bool = False, budget: int | None = None, moderator: Moderator | None = None,
              observer: Observer | None = None, checker: ClaimCheck | None = None) -> Mind:
    """The Mind one action speaks through: the model only while the session's brain is on."""
    return Mind(gateway if w.brain_mode == "model" else None, validator, cache, replay, budget, moderator, observer,
                checker)


def count_calls(w: World, mind: Mind) -> int:
    """Add the action's model calls to the session's running total, and return them."""
    if mind.asked:
        w.counters["model_calls"] = w.counters.get("model_calls", 0) + mind.asked
    return mind.asked
