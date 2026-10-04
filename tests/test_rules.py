"""The engine's rules must give exactly the rules model's results, route by route and step by step."""

import pytest

from games.crypt_road import content as C
from games.crypt_road import rules
from games.crypt_road.content import new_world
from thespis.ledger import Claim
from thespis.world import PLAYING
from tools import crypt_road_sim as sim

ROBBED = {"pred": "robbed", "a": "player", "b": "kael"}
LIE = {"pred": "robbed", "a": "kael", "b": "odo"}


def enabled(w, verb):
    return any(o["verb"] == verb and o["enabled"] for o in rules.allowed(w))


def advance(w):
    """Like the sim's advance(): head for the crypt, take the relic on arrival. A blocked move is a wait."""
    while w.status == PLAYING and w.phase < 14:
        if enabled(w, "take_relic"):
            rules.act(w, "take_relic")
        else:
            rules.act(w, "move" if enabled(w, "move") else "wait")


def provoke(w):
    rules.act(w, "insult", "kael")
    rules.act(w, "challenge", "kael")
    if w.pending == rules.DUEL_WON:
        rules.act(w, "humiliate", "kael")
        return True
    return False


# ---------------------------------------------------------------- engine routes, as in tools/crypt_road_sim.py
def route_rush(seed):
    w = new_world(seed)
    advance(w)
    return w


def route_provoke(seed, pay=True, frame=False, wait_after=False):
    w = new_world(seed)
    if not provoke(w):
        advance(w)
        return w
    if wait_after:
        rules.act(w, "wait")
    rules.act(w, "move")
    rules.act(w, "move")
    if w.status == PLAYING and w.player["loc"] == "guard_post":
        if frame:
            rules.act(w, "bribe", "brenna")
            rules.act(w, "bribe", "brenna")
            rules.act(w, "tell_claim", "brenna", claim=LIE)
        elif pay and w.npcs["brenna"].trust_in["player"] < 0:
            rules.act(w, "bribe", "brenna")
    advance(w)
    return w


def route_lie_unpaid(seed):
    w = new_world(seed)
    provoke(w)
    rules.act(w, "move")
    rules.act(w, "move")
    rules.act(w, "tell_claim", "brenna", claim=LIE)
    advance(w)
    return w


def route_spare(seed):
    w = new_world(seed)
    rules.act(w, "insult", "kael")
    rules.act(w, "challenge", "kael")
    if w.pending == rules.DUEL_WON:
        rules.act(w, "spare", "kael")
    advance(w)
    return w


def route_duel_lost(seed):
    s = seed
    while C.dice(s, "challenge:1") < C.DUEL_WIN_CHANCE:
        s += 1
    w = new_world(s)
    rules.act(w, "insult", "kael")
    rules.act(w, "challenge", "kael")
    advance(w)
    return w


ROUTES = {
    "rush": (route_rush, sim.route_rush, {}),
    "provoke_pay": (route_provoke, sim.route_provoke, {"pay": True}),
    "provoke_no_pay": (route_provoke, sim.route_provoke, {"pay": False}),
    "frame": (route_provoke, sim.route_provoke, {"frame": True}),
    "lie_unpaid": (route_lie_unpaid, sim.route_lie_unpaid, {}),
    "spare": (route_spare, sim.route_spare, {}),
    "duel_lost": (route_duel_lost, sim.route_duel_lost, {}),
    "provoke_wait": (route_provoke, sim.route_provoke, {"pay": True, "wait_after": True}),
    "provoke_wait_frame": (route_provoke, sim.route_provoke, {"frame": True, "wait_after": True}),
}


@pytest.mark.parametrize("seed", [sim.DEMO_SEED, 2, 4])
@pytest.mark.parametrize("name", list(ROUTES))
def test_route_matches_rules_model(name, seed):
    engine_route, sim_route, kwargs = ROUTES[name]
    if name == "lie_unpaid" and C.dice(seed, "challenge:1") >= C.DUEL_WIN_CHANCE:
        pytest.skip("the rules model's lie_unpaid route assumes the first duel is won")
    w, ref = engine_route(seed, **kwargs), sim_route(seed, **kwargs)
    assert f"{w.status}@{w.ended_at}" == ref.status
    assert w.player["coins"] == ref.player["coins"]
    assert w.npcs["kael"].drives["grudge"] == ref.kael["grudge"]


# ---------------------------------------------------------------- the demo route, step by step
def same_state(w, ref):
    """Every number the rules model tracks must match the engine's."""
    assert w.phase == ref.phase
    assert w.player == {"loc": sim.STOPS[ref.player["loc"]], "coins": ref.player["coins"]}
    kael = w.npcs["kael"]
    assert kael.loc == sim.STOPS[ref.kael["loc"]]
    assert {k: kael.drives[k] for k in ("grudge", "fear", "respect")} == \
        {k: ref.kael[k] for k in ("grudge", "fear", "respect")}
    assert kael.frozen(w.phase) == (ref.kael["frozen_until"] >= ref.phase)
    assert w.npcs["brenna"].trust_in == ref.brenna["trust"]
    assert w.npcs["odo"].loc == sim.STOPS[ref.locs["odo"]]
    got = {(b.npc, (b.claim.pred, b.claim.a, b.claim.b)): (b.conf if b.active else 0.0, b.status)
           for b in w.beliefs.all()}
    want = {(n, c): (ref.conf(n, c), v["status"]) for n in sim.NPCS for c, v in ref.beliefs[n].items()}
    assert got == want


def test_demo_route_step_by_step():
    w, ref = new_world(sim.DEMO_SEED), sim.World(sim.DEMO_SEED)
    steps = [
        (lambda: rules.act(w, "insult", "kael"), ref.insult),
        (lambda: rules.act(w, "challenge", "kael"), ref.challenge),
        (lambda: rules.act(w, "humiliate", "kael"), ref.humiliate),
        (lambda: rules.act(w, "talk", "mags", text="What did you see?"), lambda: None),
        (lambda: rules.act(w, "move"), lambda: ref.tick("move")),
        (lambda: rules.act(w, "move"), lambda: ref.tick("move")),
        (lambda: rules.act(w, "bribe", "brenna"), ref.bribe),
        (lambda: rules.act(w, "bribe", "brenna"), ref.bribe),
        (lambda: rules.act(w, "tell_claim", "brenna", claim=LIE), lambda: ref.tell_claim("brenna", sim_lie)),
        (lambda: rules.act(w, "move"), lambda: ref.tick("move")),
        (lambda: rules.act(w, "move"), lambda: ref.tick("move")),
    ]
    sim_lie = ("robbed", "kael", "odo")
    for engine_step, sim_step in steps:
        engine_step()
        sim_step()
        same_state(w, ref)
    result = rules.act(w, "take_relic")
    assert ref.take_relic() and (w.status, w.ended_at) == ("won", 5)
    ref.status = "epilogue"
    ref.tick("wait")
    ref.tick("wait")
    same_state(w, ref)
    assert len(result.epilogue) == 2 and w.phase == 7


def test_demo_route_beats():
    """The 'Must be true' column of the demo script, checked on the engine."""
    w = new_world(sim.DEMO_SEED)
    rules.act(w, "insult", "kael")
    rules.act(w, "challenge", "kael")
    assert w.pending == "duel_won" and {o["verb"] for o in rules.allowed(w) if o["enabled"]} == {"humiliate", "spare"}
    tick0 = rules.act(w, "humiliate", "kael").tick
    assert [d.chosen for d in tick0.decisions] == ["go_to"]
    for npc in ("mags", "odo"):
        assert w.beliefs.conf(npc, Claim(**ROBBED)) == 1.0
    assert w.npcs["kael"].last_seen == {"loc": "tavern", "phase": 0}  # he has left the tavern

    rules.act(w, "move")
    tick2 = rules.act(w, "move").tick
    accuse = next(e for e in tick2.events if e.verb == "accuse")
    assert (accuse.id, accuse.loc, accuse.phase) == ("e0011", "guard_post", 2)  # as in docs/api.md
    belief = w.beliefs.get("brenna", Claim(**ROBBED))
    assert (belief.id, belief.conf, belief.evidence[0].source, belief.evidence[0].event) == ("b0010", 0.9, "kael", "e0011")
    assert w.npcs["brenna"].trust_in["player"] == -2
    move = next(o for o in rules.allowed(w) if o["verb"] == "move")
    assert not move["enabled"] and move["reason"] == "Blocked: Brenna's trust in you is -2"
    with pytest.raises(rules.NotAllowed, match="Blocked"):
        rules.act(w, "move")

    rules.act(w, "bribe", "brenna")
    rules.act(w, "bribe", "brenna")
    assert not rules.happened(w, Claim("lied", "player", "kael"))
    lie = rules.act(w, "tell_claim", "brenna", claim=LIE).events[0]
    assert lie.truth is False and w.beliefs.conf("brenna", Claim(**LIE)) == 0.9
    assert w.npcs["kael"].drives["grudge"] == 8 and w.beliefs.conf("kael", Claim("lied", "player", "kael")) == 1.0
    assert rules.happened(w, Claim("lied", "player", "kael"))  # a lie leaves no event of its own, but Kael is right
    tick3 = rules.act(w, "move").tick
    assert any(d.npc == "brenna" and d.chosen == "detain:kael" for d in tick3.decisions)
    assert w.player["loc"] == "bridge" and w.npcs["kael"].frozen(w.phase)

    rules.act(w, "move")
    end = rules.act(w, "take_relic")
    assert (w.status, w.ended_at) == ("won", 5)
    epilogue_decisions = [d for t in end.epilogue for d in t.decisions]
    assert any(d.npc == "brenna" and d.chosen == "question:odo" and d.phase == 6 for d in epilogue_decisions)
    testify = next(e for t in end.epilogue for e in t.events if e.verb == "testify")
    assert testify.truth is False and testify.loc == "guard_post"
    assert w.beliefs.get("brenna", Claim(**LIE)).status == "retracted"
    assert w.npcs["brenna"].trust_in["player"] == -1
    assert not w.ledger.happened(Claim(**LIE))  # the testimony doesn't make the lie true
    assert all(not o["enabled"] and o["reason"] == "The race is over" for o in rules.allowed(w))


def test_dice_use_the_challenge_count_not_event_ids():
    w = new_world(sim.DEMO_SEED)
    w.ledger.append(0, "move", "odo", "market", "tavern")  # an extra event before the duel
    rules.act(w, "challenge", "kael")
    assert w.pending == "duel_won"  # seed 1 still wins its first duel


def test_invalid_acts_are_refused():
    w = new_world(sim.DEMO_SEED)
    with pytest.raises(rules.NotAllowed):
        rules.act(w, "bribe", "brenna")  # she isn't at the tavern
    with pytest.raises(rules.NotAllowed):
        rules.act(w, "talk", "kael", text="x" * 201)
    with pytest.raises(rules.NotAllowed):
        rules.act(w, "tell_claim", "kael", claim={"pred": "stole", "a": "odo", "b": "kael"})
    with pytest.raises(rules.NotAllowed, match="Win a duel first"):
        rules.act(w, "humiliate", "kael")
    assert len(w.ledger) == 0
