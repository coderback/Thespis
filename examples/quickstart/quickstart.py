"""Thespis in your own game, in about 30 lines: the README's "Use it in your game", run as it is written there.

    pip install thespis-sdk
    python quickstart.py        # with game.toml beside it

The player steals a loaf from Mara while the miller Wat is watching. Word travels from Wat to his sister Edda, and
from Edda to her friend Mara. The player then tells Mara it was Wat, but Mara trusts Edda more than a stranger. When
the player comes to her counter, she refuses them, and says why. No model is needed: every line falls back to the
game's own words. Set LLM_* (docs/models.md) and a model voices them instead, citing the same events.
"""

from pathlib import Path

from thespis.api import Game, Session, gateway_from_env

game = Game.load(Path(__file__).with_name("game.toml"))
s = Session.new(game, gateway=gateway_from_env())

# 1. Your game reports what happened, and who saw it. Thespis never decides what happened. Mara was in the back
#    room, so she isn't the event's target: only Wat saw it.
theft = {"pred": "stole_from", "a": "player", "b": "mara"}
s.observe("steal", "player", at="bakery", claim=theft, witnesses=["wat"])

# 2. Time passes in the minds: the story goes from Wat to Edda, then from Edda to Mara, weaker at each step.
s.tick(2)

# 3. The player lies. Mara believes a stranger only so far, and a theft has one thief.
s.observe("tell", "player", "mara", claim={"pred": "stole_from", "a": "wat", "b": "mara"}, said=True)

# 4. The player comes to Mara's counter. She chooses among the choices the game file gives her, and speaks.
s.update("player", loc="bakery")
line = s.decide("mara", "counter")
print(f"Mara: {line.text}  ({line.reason})")

# 5. Why: everything each of them believes, how sure, and the events behind it.
for npc in ("wat", "edda", "mara"):
    for b in s.inspect(npc)["beliefs"]:
        c, sure = b["claim"], b["opinion"]["b"]
        print(f"  {npc} {b['status']}: {c['a']} {c['pred']} {c['b']} at {sure:.2f}, from",
              ", ".join(f"{e['source']} ({e['event']}{', against' if e.get('against') else ''})" for e in b["evidence"]))
