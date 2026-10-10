"""The minds at town size (tools/town_bench.py): what was scanned is looked up, and says what the scan said; and a big
town's grapevine tells so many things a tick, its tellers taking turns."""

import dataclasses
from pathlib import Path

import pytest

from thespis import perception
from thespis.api import DefinitionError, Game, Session
from thespis.beliefs import Belief, Evidence, fuse
from thespis.ledger import Claim, Event
from tools import town_bench

ROOT = Path(__file__).resolve().parents[1]
TOWN_TOML = (ROOT / "examples" / "town" / "game.toml").read_text(encoding="utf-8")


def played() -> Session:
    """A small town after a busy while: people, ties, deeds, lies, deaths and gossip."""
    return town_bench.play(40, 150, 30)[1]


# ---------------------------------------------------------------- lookups say what the scans said
def test_each_npcs_beliefs_are_the_ones_a_scan_finds():
    w = played().world
    assert len(w.beliefs.all()) > 100
    for npc in w.npcs:
        assert w.beliefs.for_npc(npc) == [b for b in w.beliefs.all() if b.npc == npc]


def test_what_happened_is_what_a_scan_of_the_ledger_finds():
    w = played().world
    claims = {b.claim for b in w.beliefs.all()} | {b.claim.negated() for b in w.beliefs.all()}
    assert any(not w.ledger.happened(c) for c in claims if not c.neg)  # some of what the town believes is a lie
    for c in claims:
        held = any(e.claim == c.affirmed() and e.truth for e in w.ledger)
        assert w.ledger.happened(c) is (not held if c.neg else held)


def test_what_an_npc_knows_is_what_asking_of_each_event_finds():
    s = played()
    w, sees = s.world, s.voice.sees
    for npc in list(w.npcs)[:12]:
        newest = [e for e in reversed(list(w.ledger)) if perception.knows(w, npc, e.id, sees)]
        assert perception.known(w, npc, 5, sees) == newest[:5][::-1]
        assert perception.latest(w, npc, sees) == (newest[0].id if newest else None)
        hidden = {e.id for e in newest[:2]}
        assert perception.known(w, npc, 5, sees, hidden) == [e for e in newest if e.id not in hidden][:5][::-1]


def test_who_overhears_a_tick_is_who_stands_there():
    s = played()
    w = s.world
    for e in s.tick().events:
        there = [n for n in w.npcs if n not in (e.actor, e.target) and n not in w.gone
                 and e.loc and perception.at_the_scene(w, n, e)]
        assert s.witnesses.get(e.id, []) == there + [p for p in w.players if w.players[p].get("loc") == e.loc]


def test_a_belief_remembers_its_opinion_until_its_evidence_changes():
    b = Belief("b0001", "edda", Claim("robbed", "harl", "mara"), [Evidence("player", "e0001", 0, 0.4)])
    assert b.opinion is b.opinion and b.conf == 0.4
    b.evidence.append(Evidence("wat", "e0002", 1, 0.9, against=True))  # added to in place
    assert b.opinion == fuse(b.evidence) and not b.active
    b.evidence = [dataclasses.replace(e, conf=0.2) if e.source == "wat" else e for e in b.evidence]  # replaced
    assert b.opinion == fuse(b.evidence) and b.active
    assert "_fused" not in b.to_json() and Belief.from_json(b.to_json()).opinion == b.opinion


def test_events_and_evidence_serialise_as_their_fields():
    e = Event("e0001", 2, "tell", "player", "edda", "market", Claim("robbed", "harl", "mara"), False)
    whole = {**dataclasses.asdict(e), "claim": {"pred": "robbed", "a": "harl", "b": "mara"}}
    del whole["amount"]
    assert e.to_json() == whole and list(e.to_json()) == list(whole)
    assert dataclasses.replace(e, amount=5).to_json() == {**whole, "amount": 5}
    for ev in (Evidence("wat", "e0002", 1, 0.9), Evidence("wat", "e0002", 1, 0.9, against=True)):
        fields = dataclasses.asdict(ev)
        if not ev.against:
            del fields["against"]
        assert ev.to_json() == fields and list(ev.to_json()) == list(fields)


# ---------------------------------------------------------------- so many things told a tick
def gossips(most: str) -> Session:
    """Six people in a row of ties, the first of whom saw a robbery; gossip capped as `most` says."""
    s = Session.new(Game.parse(TOWN_TOML.replace("most = 12", most), "town"))
    people = ["ann", "ben", "cat", "dan", "eve", "fay"]
    for npc in people:
        s.add(npc, "townsfolk", npc.title(), "")
    for a, b in zip(people, people[1:]):
        s.tie(a, b, "kin")
        s.update(b, trust_in={a: 5})
    s.add("mara", "townsfolk", "Mara", "docks")
    s.observe("rob", "player", "mara", at="docks", claim={"pred": "robbed", "a": "player", "b": "mara"},
              witnesses=["ann"])
    return s


def heard(s: Session) -> list[str]:
    claim = Claim("robbed", "player", "mara")
    return [n for n in s.world.npcs if s.world.beliefs.conf(n, claim) > 0]


def test_a_tick_tells_at_most_so_many_things_and_the_tellers_take_turns():
    s = gossips("most = 1")
    for told in (["ann", "mara", "ben"], ["ann", "mara", "ben", "cat"], ["ann", "mara", "ben", "cat", "dan"]):
        assert len([e for e in s.tick().events if e.verb == "gossip"]) == 1
        assert sorted(heard(s)) == sorted(told)
    assert s.world.counters["grapevine"] in range(6)  # whose turn it is next, kept in the save
    back = Session.restore(s.game, s.snapshot())
    back.tick()
    s.tick()
    assert back.snapshot() == s.snapshot()  # the turn carries over a save


def test_a_capped_grapevine_ends_where_an_uncapped_one_does():
    capped, free = gossips("most = 1"), gossips("")
    for _ in range(12):
        capped.tick()
    for _ in range(6):
        free.tick()
    assert "grapevine" not in free.world.counters
    confs = [{n: w.beliefs.conf(n, Claim("robbed", "player", "mara")) for n in w.npcs}
             for w in (capped.world, free.world)]
    assert confs[0] == confs[1] and len([c for c in confs[0].values() if c > 0]) > 3


@pytest.mark.parametrize("most", ["0", "1.5", "true", '"many"'])
def test_most_is_a_whole_number_from_one(most):
    with pytest.raises(DefinitionError) as e:
        Game.parse(TOWN_TOML.replace("most = 12", f"most = {most}"), "town")
    assert "gossip.most" in str(e.value)


# ---------------------------------------------------------------- the bench itself
def test_the_bench_plays_a_town_and_times_every_kind_of_call():
    took, s = town_bench.play(20, 60, 6)
    assert set(took) == set(town_bench.BUDGET)
    assert len(took["add"]) == 20 and len(took["tick"]) == 6 and len(s.world.npcs) == 20
    assert all(x >= 0 for xs in took.values() for x in xs)
