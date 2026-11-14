"""An unknown culprit: "someone" robbed Mara, and a later witness says who. A deed by "someone" is believed like any
other; a condition on "someone" holds for the deed by anyone, known or not; and learning the name is neither a rival
story (no conflict, nobody caught) nor a second offence (her anger moves once)."""

from pathlib import Path

import pytest

from thespis.api import Game, Session
from thespis.considerations import DefinitionError
from thespis.ledger import CAUGHT, SOMEONE, Claim

ROOT = Path(__file__).resolve().parents[1]
QUICKSTART = (ROOT / "examples" / "quickstart" / "game.toml").read_text(encoding="utf-8")
BY_SOMEONE = {"pred": "stole_from", "a": SOMEONE, "b": "mara"}
BY_PLAYER = {**BY_SOMEONE, "a": "player"}
EXTRA = '''
[[npc.mara.choices.close]]
do = "lock_up"
utility = 2
when = [{ believes = { pred = "stole_from", a = "someone", b = "self" } }]

[[npc.mara.choices.close]]
do = "accuse:{who}"
utility = 5
when = [{ believes = { pred = "stole_from", a = "{who}", b = "self" } }]

[[npc.mara.choices.close]]
do = "carry_on"
utility = 1
'''


def session() -> Session:
    return Session.new(Game.parse(QUICKSTART + EXTRA, "quickstart"))


def robbed_by_someone(s: Session) -> None:
    s.observe("steal", SOMEONE, "mara", at="bakery", claim=BY_SOMEONE)  # she finds the till empty


def test_a_deed_by_someone_is_believed_and_a_condition_on_someone_holds():
    s = session()
    assert s.explain("mara", "close", {"who": "player"})[0]["blocked"] == "doesn't know of stole_from(someone, mara)"
    robbed_by_someone(s)
    assert s.world.beliefs.conf("mara", Claim.from_json(BY_SOMEONE)) == 1.0
    assert s.decide("mara", "close", {"who": "player"}).action == "lock_up"


def test_a_name_later_opens_the_named_choice_and_keeps_the_someone():
    s = session()
    robbed_by_someone(s)
    s.observe("tell", "wat", "mara", claim=BY_PLAYER, said=True)  # Wat: it was the player
    held = {b.claim.a: (b.status, b.conf) for b in s.world.beliefs.for_npc("mara") if b.claim.pred == "stole_from"}
    assert held == {SOMEONE: ("active", 1.0), "player": ("active", 0.4)}  # no rival stories: both stand
    e = {x["do"]: x for x in s.explain("mara", "close", {"who": "player"})}
    assert e["lock_up"]["open"] and e["accuse:player"]["open"] and e["accuse:player"]["chosen"]
    assert s.events(verb=CAUGHT) == []  # nobody was caught: "someone" lost to nobody


def test_the_someone_condition_holds_for_a_name_alone_too():
    s = session()
    s.observe("tell", "wat", "mara", claim=BY_PLAYER, said=True)
    assert {x["do"]: x["open"] for x in s.explain("mara", "close", {"who": "player"})}["lock_up"]


def test_learning_who_did_it_is_no_second_offence():
    s = session()
    robbed_by_someone(s)
    assert s.world.npcs["mara"].drives["anger"] == 6
    s.observe("steal", "player", "mara", at="bakery", claim=BY_PLAYER)  # then she catches the thief at it
    assert s.world.npcs["mara"].drives["anger"] == 6


def test_two_names_still_conflict():
    s = session()
    robbed_by_someone(s)
    s.observe("tell", "edda", "mara", claim=BY_PLAYER, said=True)  # trusted: 0.9
    s.observe("tell", "player", "mara", claim={**BY_SOMEONE, "a": "wat"}, said=True)  # 0.4, and it loses
    held = {b.claim.a: b.status for b in s.world.beliefs.for_npc("mara") if b.claim.pred == "stole_from"}
    assert held == {SOMEONE: "active", "player": "active", "wat": "retracted"}
    assert [(e.actor, e.target) for e in s.events(verb=CAUGHT)] == [("mara", "player")]


def test_a_file_may_name_someone_in_a_claim_but_not_elsewhere():
    Game.parse(QUICKSTART + EXTRA, "quickstart")
    with pytest.raises(DefinitionError, match="no npc or player 'someone'"):
        Game.parse(QUICKSTART.replace("trust_in = { edda = 2 }", "trust_in = { someone = 2 }"), "quickstart")


def test_told_and_reported_as_someone():
    from fastapi.testclient import TestClient

    from thespis.server import create_app
    s = session()
    robbed_by_someone(s)
    assert s.narrate().text == "Someone stole a loaf from the counter at the bakery."
    client = TestClient(create_app({"quickstart": Game.parse(QUICKSTART, "quickstart")}))
    sid = client.post("/v1/sessions", json={"game": "quickstart"}).json()["session"]
    r = client.post(f"/v1/sessions/{sid}/observe", json={"verb": "steal", "actor": SOMEONE, "target": "mara",
                                                          "at": "bakery", "claim": BY_SOMEONE})
    assert r.status_code == 201 and r.json()["actor"] == SOMEONE
