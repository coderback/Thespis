"""The Crypt Road's fixed content: the road, the time of day, the claim types and the cast's starting state.

The rules that act on it (verbs, the tick, gossip, testimony) live in rules.py (#9).
"""

from __future__ import annotations

import tomllib
from functools import cache
from pathlib import Path

from thespis.minds import NPC
from thespis.world import World

STOPS = ["tavern", "market", "guard_post", "bridge", "crypt"]
PHASES = ["morning", "noon", "evening", "night"]
GATE = ("guard_post", "bridge")  # the crossing Brenna controls
PREDS = ["robbed", "beat", "insulted", "spared", "lied"]
GOSSIP_PRIORITY = {"robbed": 3, "beat": 2, "insulted": 1}  # worst news travels first
DEMO_SEED = 1
PLAYER_START = {"loc": "tavern", "coins": 10}

CAST_FILE = Path(__file__).with_name("cast.toml")


@cache
def load_cast() -> dict:
    with CAST_FILE.open("rb") as f:
        return tomllib.load(f)


def npc_ids() -> list[str]:
    return list(load_cast()["npc"])


def subjects() -> list[str]:
    """Who a claim can name: the player and every NPC."""
    return ["player", *npc_ids()]


def walk(npc: str) -> list[str] | None:
    """An NPC's fixed route by phase of day, or None if it decides where to go."""
    return load_cast()["npc"][npc].get("walk")


def next_stop(loc: str) -> str | None:
    i = STOPS.index(loc)
    return STOPS[i + 1] if i + 1 < len(STOPS) else None


def new_world(seed: int = DEMO_SEED) -> World:
    """The starting state of a run: phase 0, morning, at the tavern."""
    npcs = {}
    for npc_id, c in load_cast()["npc"].items():
        npcs[npc_id] = NPC(id=npc_id, loc=c["start"], drives=dict(c["drives"]), trust_in=dict(c["trust_in"]))
    world = World(seed=seed, player=dict(PLAYER_START), npcs=npcs, counters={"challenges": 0})
    for npc in world.npcs_at(world.player["loc"]):  # the player can see everyone who starts beside them
        npc.last_seen = {"loc": npc.loc, "phase": 0}
    return world
