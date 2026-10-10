"""The Crypt Road's fixed content: the road, the time of day, the claim types and the cast's starting state.

The rules that act on it (verbs, the tick, gossip, testimony) live in rules.py (#9).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from thespis.beliefs import credence
from thespis.cast import Cast
from thespis.considerations import declared
from thespis.minds import NPC
from thespis.world import World

STOPS = ["tavern", "market", "guard_post", "bridge", "crypt"]
STOP_NAMES = {"tavern": "the tavern", "market": "the market", "guard_post": "the guard post",
              "bridge": "the bridge", "crypt": "the crypt"}
PHASES = ["morning", "noon", "evening", "night"]
GATE = ("guard_post", "bridge")  # the crossing Brenna controls
PREDS = ["robbed", "beat", "insulted", "spared", "lied"]
GOSSIP_PRIORITY = {"robbed": 3, "beat": 2, "insulted": 1}  # worst news travels first
DEMO_SEED = 1
PLAYER_START = {"loc": "tavern", "coins": 10}

RIVAL = "kael"  # races you to the relic and remembers what you did
GUARD = "brenna"  # holds the gate; believes people she trusts
GOSSIPS = ("odo", "mags")  # pass on what they know, in this order
WITNESSES = ("odo", "mags")  # the guard can question them
FINE = 20  # the standard fine, in coins: the offer the client suggests first
PRICE_MIN, PRICE_MAX = 15, 30  # the bounds on what Brenna will take (#36)
RELENT = 5  # what an appeal to her duty takes off her price, once
DUEL_WIN_CHANCE = 0.6
CRIME_CONF = 0.5  # beliefs below this are stored and shown but never acted on


def dice(seed: int, key: str) -> float:
    """Deterministic uniform [0, 1) from (seed, key). Duels use key "challenge:<n>", never an event id."""
    h = hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()
    return int(h[:8], 16) / 0x100000000


conf_from_trust = credence  # how strongly a listener believes a claim, from its trust in the speaker


def asking_price(trust: int) -> int:
    """The least Brenna will take to look the other way, from her trust in the payer (#36).

    Always between PRICE_MIN and PRICE_MAX, and never under the standard fine while she distrusts you.
    """
    if trust >= 0:
        return PRICE_MIN
    return min(PRICE_MAX, FINE + 5 * max(0, -trust - 2))  # 20 at -1 or -2, 25 at -3, 30 from -4


def short_name(npc: str) -> str:
    return npc.capitalize()

CAST = Cast(Path(__file__).with_name("cast.toml"))
CHOICES = declared(CAST.data)  # what each NPC may choose, compiled from cast.toml


def load_cast() -> dict:
    return CAST.data


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
