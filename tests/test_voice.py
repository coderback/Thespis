"""#10's done-when: with no model, every NPC line cites at least one id, and only ids its speaker knows."""

import pytest

from games.crypt_road import rules, voice
from games.crypt_road.content import new_world
from tests.test_rules import ROUTES


def lines_of(w):
    return [d for d in w.decisions if d.line is not None]


def check_cites(w):
    beliefs = {b.id: b for b in w.beliefs.all()}
    events = {e.id for e in w.ledger}
    for d in lines_of(w):
        assert d.cites, f"{d.id} ({d.npc}) says {d.line!r} citing nothing"
        for cite in d.cites:
            if cite in beliefs:
                assert beliefs[cite].npc == d.npc, f"{d.id}: {d.npc} cites {cite}, someone else's belief"
            else:
                assert cite in events, f"{d.id} cites unknown id {cite}"
                assert voice.knows(w, d.npc, cite), f"{d.id}: {d.npc} cites {cite} without knowing it"
        assert "{" not in d.line, f"{d.id}: unfilled template {d.line!r}"


@pytest.mark.parametrize("name", list(ROUTES))
def test_every_line_cites_what_its_speaker_knows(name):
    engine_route, _, kwargs = ROUTES[name]
    w = engine_route(1, **kwargs)
    assert lines_of(w), "every route has some dialogue"
    check_cites(w)


def test_demo_lines_with_the_model_off():
    w = new_world(1)
    replies = []
    for verb, target, extra in [("insult", "kael", {}), ("challenge", "kael", {}), ("humiliate", "kael", {}),
                                ("talk", "mags", {"text": "Well?"}), ("move", None, {}), ("move", None, {})]:
        replies += rules.act(w, verb, target, **extra).replies
    by = {(r["npc"], r["line"]) for r in replies}
    assert ("kael", "Laugh now. The road is long.") in by
    assert ("mags", "Odo saw the whole thing, and Odo talks.") in by
    assert ("brenna", "Kael says you cut his purse in the tavern. You're not crossing.") in by
    assert ("kael", "Told the Captain what you did in the tavern. Enjoy the view.") in by
    accuse = next(d for d in w.decisions if d.chosen == "accuse:player")
    assert accuse.phase == 2 and accuse.source == "fallback" and accuse.line and accuse.cites
    assert all(r["source"] == "fallback" and r["cites"] for r in replies)
    check_cites(w)


def test_lie_is_called_out_and_exposed():
    w = new_world(1)
    for verb, target in [("insult", "kael"), ("challenge", "kael"), ("humiliate", "kael"), ("move", None),
                         ("move", None), ("bribe", "brenna"), ("bribe", "brenna")]:
        rules.act(w, verb, target)
    lie = rules.act(w, "tell_claim", "brenna", claim={"pred": "robbed", "a": "kael", "b": "odo"})
    assert ("kael", "Liar! I never touched the peddler!") in {(r["npc"], r["line"]) for r in lie.replies}
    rules.act(w, "move")
    rules.act(w, "move")
    end = rules.act(w, "take_relic")
    said = {d.line for t in end.epilogue for d in t.decisions if d.line}
    assert "Robbed? Me? By Kael? Captain, I've never been robbed in my life." in said
    check_cites(w)
