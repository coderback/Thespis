"""The reference rules model must keep matching the design doc.

If you change a rule on purpose, update tools/crypt_road_sim.py, these
expectations and the design doc together, in one PR.
"""

from tools import crypt_road_sim as sim

EXPECTED = {
    "rush": "won@4",
    "provoke_pay": "won@5",
    "provoke_no_pay": "lost@5",
    "frame": "won@5",
    "lie_unpaid": "lost@5",
    "spare": "won@5",
    "duel_lost": "lost@4",
    "provoke_wait": "lost@5",
}


def test_demo_route_acceptance():
    sim.demo_acceptance(sim.DEMO_SEED)


def test_route_outcomes():
    s = sim.DEMO_SEED
    got = {
        "rush": sim.route_rush(s).status,
        "provoke_pay": sim.route_provoke(s, pay=True).status,
        "provoke_no_pay": sim.route_provoke(s, pay=False).status,
        "frame": sim.route_provoke(s, frame=True).status,
        "lie_unpaid": sim.route_lie_unpaid(s).status,
        "spare": sim.route_spare(s).status,
        "duel_lost": sim.route_duel_lost(s).status,
        "provoke_wait": sim.route_provoke(s, pay=True, wait_after=True).status,
    }
    assert got == EXPECTED
