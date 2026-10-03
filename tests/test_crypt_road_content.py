"""The adapter's starting state must match the rules model and the design doc's cast table."""

from games.crypt_road import content
from tools import crypt_road_sim as sim


def test_new_world_matches_the_rules_model():
    world, ref = content.new_world(content.DEMO_SEED), sim.World(sim.DEMO_SEED)
    assert content.STOPS == sim.STOPS and content.PHASES == sim.PHASES
    assert content.DEMO_SEED == sim.DEMO_SEED and content.GOSSIP_PRIORITY == sim.GOSSIP_PRIORITY
    assert world.player == {"loc": sim.STOPS[ref.player["loc"]], "coins": ref.player["coins"]}
    assert sorted(world.npcs) == sorted(sim.NPCS)
    for npc in sim.NPCS:
        assert world.npcs[npc].loc == sim.STOPS[ref.loc_of(npc)]
    kael = world.npcs["kael"].drives
    assert {k: kael[k] for k in ("grudge", "fear", "respect", "ambition")} == \
        {k: ref.kael[k] for k in ("grudge", "fear", "respect", "ambition")}
    assert world.npcs["brenna"].trust_in == ref.brenna["trust"]
    assert content.walk("odo") == [sim.STOPS[i] for i in sim.ODO_WALK]


def test_start_of_run():
    world = content.new_world(5)
    assert (world.seed, world.phase, world.status, world.counters) == (5, 0, "playing", {"challenges": 0})
    seen = {n.id: n.last_seen for n in world.npcs.values()}
    assert seen == {"kael": {"loc": "tavern", "phase": 0}, "odo": {"loc": "tavern", "phase": 0},
                    "mags": {"loc": "tavern", "phase": 0}, "brenna": None}  # Brenna is out of sight


def test_cast_has_a_persona_and_goal_for_everyone():
    cast = content.load_cast()
    for npc in content.npc_ids():
        assert cast["npc"][npc]["persona"] and cast["npc"][npc]["goal"]
    assert cast["narrator"]["persona"]
    assert content.subjects() == ["player", "kael", "brenna", "odo", "mags"]
    assert content.next_stop("guard_post") == "bridge" and content.next_stop("crypt") is None
