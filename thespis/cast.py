"""A game's content, from its TOML: the cast (names, personas, goals, starting state and template lines) and the
text the game says in its own words (what each event was, the situations NPCs speak in, what their actions do).

Content lives in data so a game's code is its rules. Every template is filled with str.format.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping, Sequence
from functools import cached_property
from pathlib import Path

from thespis.world import World


class Cast:
    def __init__(self, path: Path, text: str | None = None):
        """The cast in the TOML file at `path`, or in `text` when it came some other way (a game an engine sent);
        `path` then only names it."""
        self.path, self.inline = path, text

    @cached_property
    def data(self) -> dict:
        if self.inline is not None:
            return tomllib.loads(self.inline)
        with self.path.open("rb") as f:
            return tomllib.load(f)

    @cached_property
    def source(self) -> bytes:
        return self.inline.encode() if self.inline is not None else self.path.read_bytes()

    def npc(self, npc: str) -> dict:
        return self.data["npc"][npc]

    def ids(self) -> list[str]:
        return list(self.data.get("npc", {}))

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


class LiveCast(Cast):
    """One session's cast: the game's own, and whoever joined it since (Session.add). Someone who joined is defined
    by their kind (`[kind.<id>]`: persona, goal, drives, feelings, lines, choices), with their own name and, if
    given, their own persona and goal."""

    def __init__(self, cast: Cast, joined: Mapping[str, Mapping]):
        """`joined` is the session's own record of who joined, by id: {"kind", "name", "at"} and perhaps "persona"
        and "goal". It is read as it stands, so someone added later is in the cast at once."""
        super().__init__(cast.path, cast.inline)
        self._cast, self._joined = cast, joined
        self._data: dict = {}
        self._count = -1

    @property
    def data(self) -> dict:  # type: ignore[override]  # the game's data, with the session's people among its NPCs
        if self._count != len(self._joined):  # nobody leaves a cast (Session.retire), so its size says it changed
            base = self._cast.data
            kinds = base.get("kind", {})
            own = {i: {**kinds[t["kind"]], "start": t["at"],
                       **{k: t[k] for k in ("name", "persona", "goal") if t.get(k) is not None}}
                   for i, t in self._joined.items()}
            self._data, self._count = {**base, "npc": {**base.get("npc", {}), **own}}, len(self._joined)
        return self._data

    @property
    def source(self) -> bytes:  # type: ignore[override]
        return self._cast.source
