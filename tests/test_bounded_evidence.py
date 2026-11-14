"""Bounded evidence: a belief keeps, of the reports one teller gave of one story on one side, the first, the strongest
and the latest. Everything the minds read from evidence is the same as with every report kept, so nothing plays
differently, but a long game no longer slows down with every repeat (a 20,000-event town: observe 1.45 ms at the
end, against 0.42 ms bounded) or saves every one of them."""

import json
import random
from pathlib import Path

from thespis.api import Game, Session
from thespis.beliefs import KEPT, Belief, Evidence, bounded, fuse
from thespis.ledger import Claim

ROOT = Path(__file__).resolve().parents[1]
QUICKSTART = Game.load(ROOT / "examples" / "quickstart" / "game.toml")
THEFT = {"pred": "stole_from", "a": "player", "b": "mara"}


def reports(rng: random.Random, n: int) -> list[Evidence]:
    """Reports from a few tellers, of a few stories, both sides, at rising phases."""
    out = []
    for i in range(n):
        source = rng.choice(["wat", "edda", "bess", "witnessed"])
        origin = rng.choice([(), ("wat",), ("bess", "wat")]) if source != "witnessed" else ()
        out.append(Evidence(source, f"e{i:04d}", i // 3, rng.choice([0.2, 0.4, 0.73, 0.9, 1.0]),
                            rng.random() < 0.2, origin))
    return out


def test_what_the_minds_read_is_the_same_as_with_every_report():
    rng = random.Random(7)
    for _ in range(300):
        full = reports(rng, rng.randint(1, 40))
        kept = bounded(full)
        assert fuse(kept) == fuse(full)  # the opinion: the strongest per story and side
        assert {e.source for e in kept} == {e.source for e in full}  # who told it (credit, _news, voice)
        assert max(e.phase for e in kept) == max(e.phase for e in full)  # how recent (recall)
        for src in {e.source for e in full}:  # the earliest report each teller gave (origins)
            assert min(e.phase for e in kept if e.source == src) == min(e.phase for e in full if e.source == src)
        assert max(kept, key=lambda e: e.conf).conf == max(full, key=lambda e: e.conf).conf  # the best to cite
        assert bounded(kept) == kept  # a kept list is already bounded
        assert all(sum((x.source, x.story, x.against) == (e.source, e.story, e.against) for x in kept) <= KEPT
                   for e in kept)
        assert [e for e in full if e in kept] == kept  # order is kept


def test_a_story_told_again_and_again_keeps_three_reports():
    s = Session.new(QUICKSTART)
    s.update("player", loc="bakery")
    for _ in range(50):  # the player tells Mara the same lie fifty times
        s.observe("tell", "player", "mara", claim={**THEFT, "a": "wat"}, said=True)
    [b] = [b for b in s.world.beliefs.for_npc("mara") if b.claim.a == "wat"]
    assert len(b.evidence) <= KEPT
    assert b.evidence[0].event == "e0001" and b.evidence[-1].event == "e0050"


def test_a_save_restores_exactly_after_repeats_and_a_liar_caught():
    s = Session.new(QUICKSTART)
    s.update("player", loc="bakery")
    for _ in range(10):
        s.observe("tell", "player", "mara", claim={**THEFT, "a": "wat"}, said=True)
    s.observe("steal", "player", at="bakery", claim=THEFT, witnesses=["wat"])
    s.tick(3)  # the truth reaches Mara through Edda and beats the lie: the player is discredited
    s.observe("tell", "player", "mara", claim={**THEFT, "a": "wat"}, said=True)  # and tells it once more, weaker
    saved = json.loads(json.dumps(s.snapshot()))
    assert Session.restore(QUICKSTART, saved).snapshot() == saved


def test_an_old_save_with_every_report_loads_bounded_and_believes_the_same():
    claim = Claim("stole_from", "wat", "mara")
    full = [Evidence("player", f"e{i:04d}", i, 0.4) for i in range(1, 60)]
    old = Belief("b0001", "mara", claim, full).to_json()
    loaded = Belief.from_json(old)
    assert len(loaded.evidence) <= KEPT and loaded.opinion == fuse(full)
