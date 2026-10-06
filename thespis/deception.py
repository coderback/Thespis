"""NPC deception as a validated action (#35).

An NPC may state something false only when the game's code chooses an action that states it, so a lie is a deliberate
act the game made, never something the model invents. The action carries the claim it asserts under a citable id,
and the line spoken with it always cites that id (thespis.expression adds it if the model didn't). Once chosen, the
statement goes into the ledger with its real truth, taken from the ledger itself: a lie is logged truth=false, and
the line's citation points at it, so the why-chain runs from the line to the statement to what really happened.
"""

from __future__ import annotations

from thespis.ledger import Claim, Event
from thespis.world import World

SAID = "said"  # the id a line cites for the claim its action asserts


def asserting(option: dict, says: str) -> dict:
    """An action that states `says` as fact. The line spoken with it cites SAID."""
    return {**option, "asserts": {"id": SAID, "claim": says}}


def log_statement(world: World, verb: str, actor: str, target: str | None, loc: str, claim: Claim,
                  cites: list[str]) -> tuple[Event, list[str]]:
    """Write a stated claim to the ledger with its real truth, and point the line's citation of SAID at it."""
    event = world.ledger.append(world.phase, verb, actor, target, loc, claim, world.ledger.happened(claim))
    return event, [event.id if c == SAID else c for c in cites]
