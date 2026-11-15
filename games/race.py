"""The demo games' race: whether it is still on, how it ended and when, and a choice the player must make first.

It is the games' own state, so it lives in `World.custom`, which Thespis saves with the world and never reads.
"""

from __future__ import annotations

from thespis.world import World

PLAYING, WON, LOST = "playing", "won", "lost"


def status(w: World) -> str:
    """PLAYING, WON or LOST."""
    return w.custom.get("status", PLAYING)


def over(w: World) -> bool:
    return status(w) != PLAYING


def ended_at(w: World) -> int | None:
    """The phase the race ended, or None while it is on."""
    return w.custom.get("ended_at")


def end(w: World, how: str, phase: int | None = None) -> None:
    """End the race, WON or LOST, at this phase (by default the world's)."""
    w.custom["status"], w.custom["ended_at"] = how, w.phase if phase is None else phase


def pending(w: World) -> str | None:
    """A choice the player must make before anything else, e.g. after winning a duel."""
    return w.custom.get("pending")


def set_pending(w: World, choice: str | None) -> None:
    if choice is None:
        w.custom.pop("pending", None)
    else:
        w.custom["pending"] = choice
