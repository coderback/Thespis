"""The director's pattern registry. Story-sifting patterns find arcs in the ledger and become narrator hooks.

Adapters register their patterns here; the Crypt Road's (revenge brewing, lie told, lie exposed) arrive in #19.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from thespis.world import World


@dataclass(frozen=True)
class Hook:
    pattern: str
    text: str
    cites: tuple[str, ...] = ()


Pattern = Callable[[World], "Hook | None"]

_PATTERNS: dict[str, Pattern] = {}


def register(name: str) -> Callable[[Pattern], Pattern]:
    def decorate(fn: Pattern) -> Pattern:
        _PATTERNS[name] = fn
        return fn
    return decorate


def patterns() -> dict[str, Pattern]:
    return dict(_PATTERNS)


def sift(world: World) -> list[Hook]:
    """Run every registered pattern; return the hooks that matched, in registration order."""
    return [hook for fn in _PATTERNS.values() if (hook := fn(world)) is not None]
