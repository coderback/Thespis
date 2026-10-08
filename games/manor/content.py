"""The manor mystery's content (#35): three rooms, three people, a missing signet ring, and the truth of the morning.

Everything that happened before the player arrives is written into the ledger by new_world(), so the crime lives only
there: Sable took the ring, Pell saw her leave the study, and she told Lady Vane she was in the kitchen, a lie.
"""

from __future__ import annotations

import tomllib
from functools import cache
from pathlib import Path

from thespis.deception import log_statement
from thespis.ledger import Claim
from thespis.minds import NPC
from thespis.world import World

ROOMS = ("hall", "study", "kitchen")
ROOM_NAMES = {"hall": "the hall", "study": "the study", "kitchen": "the kitchen"}
PHASES = ("early morning", "mid-morning", "noon", "early afternoon", "mid-afternoon", "late afternoon", "teatime",
          "evening")
ARRIVAL = 2  # the player arrives at noon: everything before happened offscreen
DEADLINE = 7  # at evening Lady Vane sends for the constable, and the case is lost
OWNER, BUTLER, MAID = "vane", "pell", "sable"
SUSPECTS = (BUTLER, MAID)
ITEM = "ring"
TOPICS = {"morning": "this morning", "ring": "the ring"}
FEAR_TO_LIE = 3  # Sable may lie once her fear reaches this
CONTRADICTED = 3  # how far Lady Vane's trust falls in someone caught lying to her
BELIEVED = 0.5  # beliefs below this are held but never acted on
CAST_FILE = Path(__file__).with_name("cast.toml")


@cache
def load_cast() -> dict:
    with CAST_FILE.open("rb") as f:
        return tomllib.load(f)


def name(who: str) -> str:
    return load_cast()["npc"][who]["name"] if who in load_cast()["npc"] else who


def took(who: str) -> Claim:
    return Claim("took", who, ITEM)


def was_in(who: str, room: str, phase: int) -> Claim:
    return Claim("was_in", who, place=room, at=phase)


def contradicts(a: Claim, b: Claim) -> bool:
    """Two places for the same person at the same time can't both be true."""
    return a.pred == b.pred == "was_in" and a.a == b.a and a.at == b.at and a.place != b.place


def upgrade_claim(d: dict) -> dict:
    """A claim saved before typed claims, when the room and the phase shared its second slot ("study@1"), as it is
    saved now. Applied when a session is loaded, so sessions saved before keep working."""
    if d.get("pred") == "was_in" and "@" in str(d.get("b", "")):
        room, _, phase = d["b"].partition("@")
        return {k: v for k, v in d.items() if k != "b"} | {"place": room, "at": int(phase)}
    return d


def conf_from_trust(trust: int) -> float:
    """How strongly a listener believes a claim, from its trust in the speaker."""
    if trust >= 2:
        return 0.9
    if trust >= 0:
        return 0.4
    return 0.2


THE_TRUTH = was_in(MAID, "study", 1)
THE_ALIBI = was_in(MAID, "kitchen", 1)


def new_world(seed: int = 1) -> World:
    """The manor at noon, with the morning already in the ledger."""
    cast = load_cast()["npc"]
    npcs = {i: NPC(id=i, loc=c["room"], drives=dict(c["drives"]), trust_in=dict(c["trust_in"])) for i, c in cast.items()}
    w = World(seed=seed, player={"loc": "hall", "asked": []}, npcs=npcs)

    # Early morning: Sable takes the ring from the study. No one sees.
    taken = w.ledger.append(0, "take", MAID, ITEM, "study", took(MAID))
    w.beliefs.add_evidence(MAID, took(MAID), 1.0, "self", taken.id, 0)
    # Mid-morning: she leaves the study, and Pell sees her go.
    w.phase = 1
    left = w.ledger.append(1, "leave", MAID, None, "study", THE_TRUTH)
    w.beliefs.add_evidence(MAID, THE_TRUTH, 1.0, "self", left.id, 1)
    w.beliefs.add_evidence(BUTLER, THE_TRUTH, 1.0, "witnessed", left.id, 1)
    # She tells Lady Vane she was in the kitchen: a lie, so the ledger logs it false. Vane believes her.
    alibi, _ = log_statement(w, "tell", MAID, OWNER, "hall", THE_ALIBI, [])
    w.beliefs.add_evidence(OWNER, THE_ALIBI, conf_from_trust(npcs[OWNER].trust_in[MAID]), MAID, alibi.id, 1)
    # Noon: the player arrives in the hall, where Lady Vane is waiting.
    w.phase = ARRIVAL
    w.ledger.append(ARRIVAL, "arrive", "player", None, "hall")
    return w
