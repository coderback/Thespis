"""The gossip trace (Session.trace): who holds a story, what the next tick would tell of it and how sure each
listener would be, and where it stops and why. Its predictions are the tick's own: a random town checks them."""

import random
import re
from pathlib import Path

import pytest

from thespis.api import Game, Session
from thespis.ledger import Claim

ROOT = Path(__file__).resolve().parents[1]
QUICKSTART = (ROOT / "examples" / "quickstart" / "game.toml").read_text(encoding="utf-8")
TAVERN = Game.load(ROOT / "examples" / "tavern" / "game.toml")
TOWN = (ROOT / "examples" / "town" / "game.toml").read_text(encoding="utf-8")
THEFT = {"pred": "stole_from", "a": "player", "b": "mara"}


def quickstart(text: str = QUICKSTART) -> Session:
    return Session.new(Game.parse(text, "quickstart"))


def test_a_story_along_ties_with_the_sum_for_each_hop():
    s = quickstart()
    s.observe("steal", "player", at="bakery", claim=THEFT, witnesses=["wat"])
    t = s.trace(THEFT)
    assert t["claim"] == "stole_from(player, mara)"
    assert [(h["npc"], h["conf"]) for h in t["holders"]] == [("wat", 1.0)]
    assert t["next"] == [{"teller": "wat", "listener": "edda", "conf": 0.9, "how": "1 x 0.9 (trust 2) x 1 (kin) = 0.9"}]
    s.tick()
    assert s.trace(THEFT)["next"] == [{"teller": "edda", "listener": "mara", "conf": 0.73,
                                       "how": "0.9 x 0.9 (trust 2) x 0.9 (friend) = 0.73"}]
    s.tick()
    t = s.trace(THEFT)
    assert [(h["npc"], h["conf"]) for h in t["holders"]] == [("wat", 1.0), ("edda", 0.9), ("mara", 0.73)]
    assert t["next"] == [] and t["stopped"] == []  # everyone it can reach has it


def test_where_a_story_stops_and_why():
    s = quickstart(QUICKSTART.replace("trust_in = { wat = 2 }", "trust_in = { wat = 0 }"))
    s.observe("steal", "player", at="bakery", claim=THEFT, witnesses=["wat"])
    s.tick()  # Edda trusts Wat only at 0: she believes him at 0.4
    t = s.trace(THEFT)
    assert {"npc": "edda", "why": "holds it at 0.4, under the threshold 0.5"} in t["stopped"]
    assert t["next"] == []


def test_worse_news_goes_first():
    s = quickstart()
    s.observe("steal", "player", at="bakery", claim=THEFT, witnesses=["wat"])
    s.observe("steal", "player", at="bakery", claim={**THEFT, "b": "edda"}, witnesses=["wat"])
    t = s.trace({**THEFT, "b": "edda"})  # Wat tells Edda one thing a tick: the theft from Mara goes first
    assert t["next"] == []
    assert t["stopped"] == [{"npc": "wat", "listener": "edda", "why": "tells them stole_from(player, mara) first"}]
    s.tick()
    assert [n["listener"] for n in s.trace({**THEFT, "b": "edda"})["next"]] == ["edda"]  # and then this


def test_gossip_without_ties_shows_the_decay():
    s = Session.new(TAVERN)
    s.observe("insult", "player", "garrick", claim={"pred": "insulted", "a": "player", "b": "garrick"},
              witnesses=["wren"])
    insult = {"pred": "insulted", "a": "player", "b": "garrick"}
    t = s.trace(insult)  # Wren, who gossips, has nobody new in the taproom; Garrick doesn't gossip
    assert t["next"] == [] and t["stopped"] == [{"npc": "garrick", "why": "doesn't pass news on (not in [gossip] "
                                                                             "gossips)"}]
    s.update("pip", loc="taproom")
    assert s.trace(insult)["next"] == [{"teller": "wren", "listener": "pip", "conf": 0.8,
                                        "how": "1 x 0.8 (decay) = 0.8"}]


def test_a_game_without_gossip_says_so():
    s = quickstart(QUICKSTART[:QUICKSTART.index("# ---------------------------------------------------------------- "
                                                "the grapevine")]
                   + QUICKSTART[QUICKSTART.index("# ---------------------------------------------------------------- "
                                                 "what can't both be true"):])
    s.observe("steal", "player", at="bakery", claim=THEFT, witnesses=["wat"])
    assert s.trace(THEFT)["stopped"] == [{"npc": None, "why": "the game declares no [gossip]"}]


def test_the_trace_changes_nothing():
    s = quickstart()
    s.observe("steal", "player", at="bakery", claim=THEFT, witnesses=["wat"])
    before = s.snapshot()
    s.trace(THEFT)
    assert s.snapshot() == before


@pytest.mark.parametrize("most", [True, False])
def test_what_the_trace_predicts_is_what_the_tick_does(most):
    """A town of 40 played at random, with its cap on what a tick tells (`most`) and without: before each tick,
    every story's `next`; after it, the evidence each listener gained from that teller. They must agree, listener,
    teller and confidence."""
    rng = random.Random(3)
    places_toml = "".join(f'p{i:02d} = "place {i}"\n' for i in range(8))
    text = re.sub(r"\[places\]\n(?:.+\n)+", "[places]\n" + places_toml, TOWN, count=1)
    game = Game.parse(text if most else re.sub(r"\nmost = .*", "", text), "town")
    places = list(game.places)
    s = Session.new(game, 3)
    ids = [f"n{i:02d}" for i in range(40)]
    for i, npc in enumerate(ids):
        s.add(npc, "guard" if i % 10 == 0 else "townsfolk", f"Person {i}", places[i % len(places)])
    for i, npc in enumerate(ids):
        s.tie(npc, ids[(i + 1) % 40], rng.choice(["kin", "friend"]))
        s.update(npc, trust_in={ids[(i + 1) % 40]: rng.choice([-1, 0, 2, 3]), ids[(i - 1) % 40]: rng.choice([0, 2])})
    checked = 0
    for step in range(30):
        for _ in range(4):
            target = rng.choice(ids)
            at = s.world.npcs[target].loc
            here = [x.id for x in s.world.npcs_at(at) if x.id != target]
            s.update("player", loc=at)
            s.observe("rob", "player", target, at=at, claim={"pred": "robbed", "a": "player", "b": target},
                      witnesses=here)
        claims = {b.claim for b in s.world.beliefs.all()}
        predicted = {(n["teller"], n["listener"], c, n["conf"]) for c in claims
                     for n in s.trace(c.to_json())["next"]}
        events = len(s.world.ledger)
        s.tick()
        gossip = [e for e in list(s.world.ledger)[events:] if e.verb == "gossip"]
        actual = set()
        for e in gossip:
            assert e.claim is not None and e.target is not None
            b = s.world.beliefs.get(e.target, e.claim)
            assert b is not None
            [ev] = [x for x in b.evidence if x.event == e.id]
            actual.add((e.actor, e.target, e.claim, ev.conf))
        assert predicted == actual, step
        checked += len(actual)
    assert checked > 50  # the town did gossip


def test_over_a_claim_object_too():
    s = quickstart()
    s.observe("steal", "player", at="bakery", claim=THEFT, witnesses=["wat"])
    assert s.trace(Claim("stole_from", "player", "mara"))["holders"][0]["npc"] == "wat"


def test_over_http():
    from fastapi.testclient import TestClient

    from thespis.server import create_app
    client = TestClient(create_app({"quickstart": Game.parse(QUICKSTART, "quickstart")}))
    sid = client.post("/v1/sessions", json={"game": "quickstart"}).json()["session"]
    client.post(f"/v1/sessions/{sid}/observe", json={"verb": "steal", "actor": "player", "at": "bakery",
                                                      "claim": THEFT, "witnesses": ["wat"]})
    r = client.post(f"/v1/sessions/{sid}/trace", json=THEFT)
    assert r.status_code == 200, r.text
    assert r.json()["next"][0]["how"] == "1 x 0.9 (trust 2) x 1 (kin) = 0.9"
    assert client.post(f"/v1/sessions/{sid}/trace", json={"pred": "stole", "a": "player"}).status_code == 404
