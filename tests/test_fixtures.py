"""The client builds against fixtures/, so they must keep the docs/api.md shapes and the rules model's numbers.

tools/make_fixtures.py generates them by playing the demo route through the real API; regenerate after any
engine change (python tools/make_fixtures.py) and commit the result.
"""

import json
import pathlib

import pytest

from tools import crypt_road_sim as sim
from tools import make_fixtures

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures"

STATE_KEYS = {"seed", "phase", "day", "phase_name", "status", "brain", "pending", "ended_at", "player", "npcs",
              "beliefs", "ledger_tail", "decisions_tail"}
NPC_KEYS = {"id", "loc", "last_seen", "drives", "trust_in", "frozen_until", "persona", "persona_edited"}
BELIEF_KEYS = {"id", "npc", "claim", "conf", "status", "truth", "evidence"}
EVENT_KEYS = {"id", "phase", "verb", "actor", "target", "loc", "claim", "truth", "schema_version"}
DECISION_KEYS = {"id", "kind", "npc", "phase", "trigger", "allowed", "chosen", "line", "cites", "reason", "source"}
VERB_KEYS = {"verb", "target", "label", "args", "ends_phase", "enabled", "reason"}
ACT_KEYS = {"events", "replies", "tick", "epilogue", "state"}
REPLY_KEYS = {"decision", "npc", "line", "cites", "source"}


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def all_states():
    for path in sorted(FIXTURES.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if path.name.startswith("state_"):
            yield path.name, data
        elif "state" in data:
            yield path.name, data["state"]


def check_state(s):
    assert set(s) == STATE_KEYS
    assert s["day"] == s["phase"] // 4 + 1
    assert s["phase_name"] == sim.PHASES[s["phase"] % 4]
    assert s["status"] in ("playing", "won", "lost") and s["brain"] in ("model", "fallback")
    assert s["player"]["loc"] in sim.STOPS
    assert sorted(n["id"] for n in s["npcs"]) == sorted(sim.NPCS)
    for n in s["npcs"]:
        assert set(n) == NPC_KEYS and n["loc"] in sim.STOPS
    for b in s["beliefs"]:
        assert set(b) == BELIEF_KEYS
        assert b["conf"] == max(e["conf"] for e in b["evidence"])
    for e in s["ledger_tail"]:
        assert set(e) - {"amount"} == EVENT_KEYS and e["loc"] in sim.STOPS  # amount only where coins moved (#36)
    for d in s["decisions_tail"]:
        assert set(d) == DECISION_KEYS and d["kind"] in ("decide", "react")
        assert d["source"] in ("llm", "cache", "fallback")
        if d["kind"] == "decide":
            assert d["chosen"] in d["allowed"]


def test_fixtures_exist():
    assert len(list(FIXTURES.glob("*.json"))) >= 6


@pytest.mark.parametrize("name,state", list(all_states()))
def test_state_shape_and_ids_resolve(name, state):
    check_state(state)
    events = {e["id"] for e in state["ledger_tail"]}
    beliefs = {b["id"] for b in state["beliefs"]}
    for b in state["beliefs"]:
        assert all(ev["event"] in events for ev in b["evidence"]), f"{name}: {b['id']} cites a missing event"
    for d in state["decisions_tail"]:
        assert set(d["cites"]) <= events | beliefs, f"{name}: {d['id']} cites a missing id"
        assert (d["line"] is None) == (d["cites"] == []), f"{name}: {d['id']} line without cites, or cites alone"


@pytest.mark.parametrize("name", sorted(p.name for p in FIXTURES.glob("act_*.json")))
def test_act_shape(name):
    a = load(name)
    assert set(a) == ACT_KEYS
    decisions = {d["id"] for d in a["state"]["decisions_tail"]}
    for r in a["replies"]:
        assert set(r) == REPLY_KEYS and r["decision"] in decisions
    for tick in [a["tick"], *(a["epilogue"] or [])]:
        if tick is not None:
            assert set(tick) == {"moves", "decisions", "events"}
    if a["tick"] is not None and a["tick"]["events"]:
        assert [e["id"] for e in a["tick"]["events"]] == [e["id"] for e in a["events"]][-len(a["tick"]["events"]):]
    if a["epilogue"] is not None:
        assert len(a["epilogue"]) == 2 and a["state"]["status"] in ("won", "lost")


@pytest.mark.parametrize("name", sorted(p.name for p in FIXTURES.glob("allowed_*.json")))
def test_allowed_shape(name):
    verbs = load(name)["verbs"]
    for v in verbs:
        assert set(v) == VERB_KEYS
        assert v["enabled"] == (v["reason"] is None), f"{name}: {v['verb']} needs a reason exactly when disabled"


def test_duel_won_enables_only_humiliate_and_spare():
    enabled = {v["verb"] for v in load("allowed_p0_duel_won.json")["verbs"] if v["enabled"]}
    assert enabled == {"humiliate", "spare"}


def test_gate_blocks_move_at_trust_minus_2():
    move = next(v for v in load("allowed_p3_gate.json")["verbs"] if v["verb"] == "move")
    assert not move["enabled"] and "-2" in move["reason"]


def demo_world_at(phase):
    """The demo route in the rules model, stopped at the start of the given phase."""
    w = sim.World(sim.DEMO_SEED)
    w.insult()
    w.challenge()
    w.humiliate()
    while w.phase < phase:
        w.tick("move")
    return w


@pytest.mark.parametrize("name,phase", [("state_p1_after_humiliate.json", 1),
                                        ("act_05_move_to_market.json", 2),
                                        ("state_p3_gate.json", 3)])
def test_numbers_match_rules_model(name, phase):
    data = load(name)
    s = data.get("state", data)
    w = demo_world_at(phase)
    npcs = {n["id"]: n for n in s["npcs"]}
    assert s["phase"] == w.phase
    assert s["player"] == {"loc": sim.STOPS[w.player["loc"]], "coins": w.player["coins"]}
    kael = npcs["kael"]
    assert kael["loc"] == sim.STOPS[w.kael["loc"]]
    assert {k: kael["drives"][k] for k in ("grudge", "fear", "respect")} == \
        {k: w.kael[k] for k in ("grudge", "fear", "respect")}
    assert npcs["brenna"]["trust_in"] == w.brenna["trust"]
    assert npcs["odo"]["loc"] == sim.STOPS[w.locs["odo"]]
    got = {(b["npc"], (b["claim"]["pred"], b["claim"]["a"], b["claim"]["b"])): b["conf"] for b in s["beliefs"]}
    want = {(n, c): w.conf(n, c) for n in sim.NPCS for c in w.beliefs[n]}
    assert got == want


def test_end_of_demo_matches_rules_model():
    """After the win and the epilogue: the lie is exposed and Brenna's trust in you is -1."""
    s = load("state_p7_end.json")
    ref = sim.demo_acceptance(sim.DEMO_SEED)
    assert (s["status"], s["ended_at"], s["phase"]) == ("won", 5, ref.phase)
    assert next(n for n in s["npcs"] if n["id"] == "brenna")["trust_in"] == ref.brenna["trust"]
    lie = next(b for b in s["beliefs"] if b["claim"] == {"pred": "robbed", "a": "kael", "b": "odo"})
    assert (lie["status"], lie["truth"]) == ("retracted", False)
    assert all(not v["enabled"] for v in load("allowed_p7_end.json")["verbs"])
    assert load("digest_epilogue.json")["epilogue"]


def test_committed_fixtures_match_the_engine():
    """Fails when the engine changes and fixtures/ wasn't regenerated: run python tools/make_fixtures.py."""
    for name, data in make_fixtures.generate().items():
        assert load(name) == data, f"{name} is stale: run python tools/make_fixtures.py"
