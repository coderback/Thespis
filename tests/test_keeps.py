"""Secrets and silence: predicates nobody passes on (`[gossip] secret`), and what one NPC keeps to itself
(`[[npc.<id>.keeps]]`: news of someone, of a predicate, or both), while a condition holds: hush money is a flag the
game sets, loyalty a trust condition. A kept story stops where it's kept, and the trace says so."""

import re
from pathlib import Path

import pytest

from thespis.api import Game, Session
from thespis.considerations import DefinitionError

ROOT = Path(__file__).resolve().parents[1]
QUICKSTART = (ROOT / "examples" / "quickstart" / "game.toml").read_text(encoding="utf-8")
TOWN = (ROOT / "examples" / "town" / "game.toml").read_text(encoding="utf-8")
THEFT = {"pred": "stole_from", "a": "player", "b": "mara"}


def with_wat(extra: str) -> str:
    """The quickstart, with more under [npc.wat]."""
    return QUICKSTART.replace('persona = "The miller: slow to speak and never wrong about what he saw."',
                              'persona = "The miller: slow to speak and never wrong about what he saw."' + extra)


def seen_by_wat(text: str) -> Session:
    s = Session.new(Game.parse(text, "quickstart"))
    s.observe("steal", "player", at="bakery", claim=THEFT, witnesses=["wat"])
    return s


def edda_heard(s: Session) -> bool:
    s.tick()
    return any(b.claim.pred == "stole_from" for b in s.world.beliefs.for_npc("edda"))


def test_without_keeps_the_story_travels():
    assert edda_heard(seen_by_wat(QUICKSTART))


def test_a_secret_is_never_passed_on():
    s = seen_by_wat(QUICKSTART.replace("[gossip]\n", '[gossip]\nsecret = ["stole_from"]\n'))
    assert {"npc": "wat", "why": "it's a secret: [gossip] secret"} in s.trace(THEFT)["stopped"]
    assert not edda_heard(s)


def test_hush_money_keeps_it_while_the_flag_is_set():
    text = with_wat('\n\n[[npc.wat.keeps]]\nabout = "player"\nwhen = [{ flag = "paid_off" }]\n')
    assert edda_heard(seen_by_wat(text))  # not paid: he tells
    s = seen_by_wat(text)
    s.update("wat", flags={"paid_off": True})
    assert {"npc": "wat", "why": "keeps it quiet ([[npc.wat.keeps]] 1)"} in s.trace(THEFT)["stopped"]
    assert s.trace(THEFT)["next"] == []
    assert not edda_heard(s)


def test_loyalty_keeps_a_kind_of_news_while_trust_is_high():
    text = with_wat('\n\n[[npc.wat.keeps]]\npred = "stole_from"\nwhen = [{ trust = "player", gte = 3 }]\n')
    s = seen_by_wat(text)
    s.update("wat", trust_in={"player": 4})
    assert not edda_heard(s)
    s.update("wat", trust_in={"player": 0})  # the loyalty is gone: he tells now
    assert edda_heard(s)


def test_a_keep_with_no_when_always_holds_and_covers_only_its_news():
    s = seen_by_wat(with_wat('\n\n[[npc.wat.keeps]]\nabout = "edda"\n'))
    assert edda_heard(s)  # news of the player isn't news of Edda: he tells it


def test_a_kind_keeps_for_everyone_who_joins_as_it():
    places = "".join(f'p{i} = "place {i}"\n' for i in range(2))
    text = re.sub(r"\[places\]\n(?:.+\n)+", "[places]\n" + places, TOWN, count=1)
    text = text.replace("[kind.townsfolk.lines]", '[[kind.townsfolk.keeps]]\nabout = "player"\n\n[kind.townsfolk.lines]')
    s = Session.new(Game.parse(text, "town"))
    s.add("ann", "townsfolk", "Ann", at="p0")
    s.add("bob", "townsfolk", "Bob", at="p1")
    s.tie("ann", "bob", "friend")
    robbed = {"pred": "robbed", "a": "player", "b": "ann"}
    s.observe("rob", "player", "ann", at="p0", claim=robbed)
    s.tick()
    assert not any(b.claim.pred == "robbed" for b in s.world.beliefs.for_npc("bob"))
    assert {"npc": "ann", "why": "keeps it quiet ([[npc.ann.keeps]] 1)"} in s.trace(robbed)["stopped"]


@pytest.mark.parametrize("extra, says", [
    ('\n\n[[npc.wat.keeps]]\nwhen = [{ flag = "x" }]\n', "npc.wat.keeps[0]: needs about"),
    ('\n\n[[npc.wat.keeps]]\nabout = "plyer"\n', "npc.wat.keeps[0].about: no npc or player 'plyer'"),
    ('\n\n[[npc.wat.keeps]]\npred = "stole"\n', "npc.wat.keeps[0].pred: "),
    ('\n\n[[npc.wat.keeps]]\nabout = "player"\nwhen = [{ flg = "x" }]\n', "unknown condition 'flg'"),
    ('\n\n[[npc.wat.keeps]]\nabout = "player"\nsilent = true\n', "unknown key silent"),
])
def test_a_keep_is_checked_when_the_file_loads(extra, says):
    with pytest.raises(DefinitionError) as e:
        Game.parse(with_wat(extra), "quickstart")
    assert any(says in p for p in e.value.problems), e.value.problems  # type: ignore[attr-defined]


def test_a_secret_names_a_predicate():
    with pytest.raises(DefinitionError, match="gossip.secret"):
        Game.parse(QUICKSTART.replace("[gossip]\n", '[gossip]\nsecret = ["stolen"]\n'), "quickstart")


def test_the_editors_schema_knows_them():
    import tomllib

    import jsonschema

    from thespis.gameschema import schema
    text = with_wat('\n\n[[npc.wat.keeps]]\nabout = "player"\nwhen = [{ flag = "paid_off" }]\n') \
        .replace("[gossip]\n", '[gossip]\nsecret = ["stole_from"]\n')
    assert list(jsonschema.Draft7Validator(schema()).iter_errors(tomllib.loads(text))) == []
    bad = with_wat('\n\n[[npc.wat.keeps]]\nwhen = [{ flag = "x" }]\n')
    assert list(jsonschema.Draft7Validator(schema()).iter_errors(tomllib.loads(bad)))
