"""A game's content, from its TOML: the cast (names, personas, goals, starting state and template lines) and the
text the game says in its own words (what each event was, the situations NPCs speak in, what their actions do).

Content lives in data so a game's code is its rules. Every template is filled with str.format.
"""

from __future__ import annotations

import tomllib
from collections.abc import Sequence
from functools import cached_property
from pathlib import Path

from thespis.world import World


class Cast:
    def __init__(self, path: Path):
        self.path = path

    @cached_property
    def data(self) -> dict:
        with self.path.open("rb") as f:
            return tomllib.load(f)

    def npc(self, npc: str) -> dict:
        return self.data["npc"][npc]

    def ids(self) -> list[str]:
        return list(self.data["npc"])

    def persona(self, world: World, npc: str) -> str:
        """The persona the model voices: this session's edit, if there is one, or the cast's."""
        return world.npcs[npc].flags.get("persona") or self.npc(npc)["persona"]

    def template(self, npc: str, key: str) -> str | None:
        return self.npc(npc).get("lines", {}).get(key)

    def line(self, npc: str, key: str, cites: Sequence[str | None], **fmt) -> tuple[str, list[str]] | None:
        """A template line and what it cites, or None when there is no template or nothing to cite: no line without
        a source."""
        text, known = self.template(npc, key), [c for c in cites if c]
        if text is None or not known:
            return None
        return (text.format(**fmt) if fmt else text), list(dict.fromkeys(known))

    def text(self, path: str, key: str, **fmt) -> str:
        """A content string from a table, e.g. text("words.events", "insult", a=..., t=...)."""
        table = self.data
        for part in path.split("."):
            table = table[part]
        return table[key].format(**fmt)

    def has(self, path: str, key: str) -> bool:
        table = self.data
        for part in path.split("."):
            table = table.get(part, {})
        return key in table
