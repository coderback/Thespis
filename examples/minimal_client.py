"""Thespis Cast without any game: the core API in about 30 lines.

    python examples/minimal_client.py    # uses the model in .env (LLM_*), or the code fallback without one

A smith saw the player steal her hammer, and the reeve asks her about it. The game writes what happened to the ledger,
code gives her a belief and decides what she does, and the model words it and must cite her evidence, or she falls
back to the code's line. Nothing here comes from games/.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from thespis.beliefs import BeliefStore  # noqa: E402
from thespis.brain import UtilityBrain  # noqa: E402
from thespis.expression import Mind, StatePack, Utterance, Validator  # noqa: E402
from thespis.gateway import gateway_from_env  # noqa: E402
from thespis.ledger import Claim, Ledger  # noqa: E402

load_dotenv(ROOT / ".env")

# 1. The game owns the truth: it writes what happened, and the smith believes what she saw.
ledger, beliefs = Ledger(), BeliefStore()
theft = ledger.append(phase=0, verb="steal", actor="player", target="tamsin", loc="forge",
                      claim=Claim("stole", "player", "tamsin"))
saw, _ = beliefs.add_evidence("tamsin", theft.claimed, 1.0, "self", theft.id, phase=0)

# 2. Code decides what she does: her drives pull her harder towards reporting the thief than keeping quiet.
does = {"report:player": "tell the reeve what the player did", "stay_quiet": "say nothing about it"}
choice = UtilityBrain().choose("tamsin", {"report:player": 4.0, "stay_quiet": 3.0})
fallback = Utterance(choice, "Reeve, that stranger took my hammer.", [saw.id], "fallback")

# 3. The model sees only her state pack, never whether a belief is true, and must cite it as it words her line.
pack = StatePack(
    npc="tamsin", name="Tamsin", persona="A blunt smith who has no patience for thieves.",
    goal="Keep the forge running", situation="The reeve asks whether you saw anything odd today.",
    here=["the reeve"], drives={"honesty": 4}, trust_in={"player": -2},
    beliefs=[{"id": saw.id, "claim": "the player stole your hammer", "conf": saw.conf, "from": ["you saw it"]}],
    events=[{"id": theft.id, "what": "The player stole your hammer at the forge."}],
    action={"id": choice, "does": does[choice]}, names={"tamsin", "reeve"}, setting="You are at your forge.")
said = Mind(gateway_from_env(), Validator({"tamsin": "tamsin", "reeve": "reeve"})).act(pack, fallback)

print(f"Tamsin does {said.action}, worded by {said.source}, citing {said.cites}:\n  {said.line}")
