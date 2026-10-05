"""NPC deception as a validated action (#35).

An NPC may state something false only when the game offers the statement as one of its allowed actions, so a lie is
a deliberate act the game made possible, never something the model invents. The offer carries the claim it asserts
under a citable id, and the validator refuses a line for that action unless it cites the id. Once chosen, the
statement goes into the ledger with its real truth, taken from the ledger itself: a lie is logged truth=false, and
the line's citation points at it, so the why-chain runs from the line to the statement to what really happened.
"""

from __future__ import annotations

from thespis.ledger import Claim, Event
from thespis.world import World

SAID = "said"  # the id a line cites for the claim its action asserts


def asserting(option: dict, says: str) -> dict:
    """An allowed-action entry that states `says` as fact. A line choosing it must cite SAID."""
    return {**option, "asserts": {"id": SAID, "claim": says}}


def log_statement(world: World, verb: str, actor: str, target: str | None, loc: str, claim: Claim,
                  cites: list[str]) -> tuple[Event, list[str]]:
    """Write a stated claim to the ledger with its real truth, and point the line's citation of SAID at it."""
    event = world.ledger.append(world.phase, verb, actor, target, loc, claim, world.ledger.happened(claim))
    return event, [event.id if c == SAID else c for c in cites]
