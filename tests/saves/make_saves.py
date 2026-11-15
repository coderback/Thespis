"""Saves made by Thespis 0.5.0, for tests/test_old_saves.py. Run it inside an export of the v0.5.0 tag:

    git archive v0.5.0 | tar -x -C /tmp/v050 && cd /tmp/v050 && python <repo>/tests/saves/make_saves.py <repo>/tests/saves/0.5.0
"""
import json
import sys

sys.path.insert(0, ".")
import thespis  # noqa: E402
from games.crypt_road import rules  # noqa: E402
from games.crypt_road.content import DEMO_SEED, new_world  # noqa: E402
from games.manor import rules as manor  # noqa: E402
from games.manor.content import new_world as manor_world  # noqa: E402
from thespis.api import Game, Session  # noqa: E402

assert thespis.__version__ == "0.5.0"
out = sys.argv[1]
LIE = {"pred": "robbed", "a": "kael", "b": "odo"}


def save(name, data):
    with open(f"{out}/{name}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), sort_keys=True)


w = new_world(DEMO_SEED)
rules.act(w, "insult", "kael")
rules.act(w, "challenge", "kael")
assert w.pending == "duel_won"
save("crypt_road_duel_won", w.to_json())
rules.act(w, "humiliate", "kael")
rules.act(w, "move")
rules.act(w, "move")
rules.act(w, "bribe", "brenna")
rules.act(w, "bribe", "brenna")
rules.act(w, "tell_claim", "brenna", claim=LIE)
rules.act(w, "move")
rules.act(w, "move")
rules.act(w, "take_relic")
assert (w.status, w.ended_at) == ("won", 5)
save("crypt_road_won", w.to_json())

m = manor_world()
m.brain_mode = "fallback"
for step in [("move", "kitchen", None), ("ask", "sable", "morning"), ("move", "study", None),
             ("ask", "pell", "morning"), ("move", "hall", None), ("request_questioning", "pell", None),
             ("accuse", "sable", None)]:
    manor.act(m, *step)
assert m.status == "won", m.status
save("manor", m.to_json())

s = Session.new(Game.load("examples/tavern/game.toml"), seed=3)
s.observe("insult", "player", "garrick", claim={"pred": "insulted", "a": "player", "b": "garrick"}, witnesses=["wren"])
s.tick()
save("tavern_snapshot", s.snapshot())
print("ok")
