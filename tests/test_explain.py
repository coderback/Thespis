"""Why an NPC did what it did, and why not the rest (Session.explain, decide(explain=True)): every choice the game
declares, whether it was open, what kept it shut, and how its utility added up. A designer tuning a game by guesswork
spent half their time on "why didn't she do X?"; the answer is here."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from thespis.api import Game, Session
from thespis.server import create_app

ROOT = Path(__file__).resolve().parents[1]
QUICKSTART = (ROOT / "examples" / "quickstart" / "game.toml").read_text(encoding="utf-8")
THEFT = {"pred": "stole_from", "a": "player", "b": "mara"}
EXTRA = '''
[[npc.mara.choices.evening]]
do = "shut_shop"
utility = [3, { drive = "anger", weight = 2, plus = 1, if = { flag = "tired" } }]
when = [{ drive = "anger", gte = 4 }, { at = "bakery" }, { with = "player" }, { not_flag = "closed" }]

[[npc.mara.choices.evening]]
do = "accept:{amount}"
utility = [{ drive = "anger" }]
when = [{ bound = "amount", gte = 10 }, { any = [{ flag = "greedy" }, { not = { flag = "honest" } }] }]

[[npc.mara.choices.evening]]
do = "call_guard"
utility = 5
when = [{ believes = { pred = "stole_from", a = "player", b = "self" }, min = 0.8 }]

[[npc.mara.choices.suspect]]
do = "glare:wat"
utility = 1
when = [{ believes = { pred = "stole_from", a = "wat", b = "self" } }]
'''


def session() -> Session:
    return Session.new(Game.parse(QUICKSTART + EXTRA, "quickstart"))


def by_do(entries: list[dict]) -> dict[str, dict]:
    return {e["do"]: e for e in entries}


def test_every_shut_choice_says_what_shut_it_with_the_values_it_saw():
    s = session()
    s.update("mara", flags={"honest": True})
    e = by_do(s.explain("mara", "evening", {"amount": 5}))
    assert e["shut_shop"]["blocked"] == "anger is 0, needs >= 4; player is at square, mara at bakery"
    assert e["accept:5"]["blocked"] == "amount is 5, needs >= 10; none of: flag 'greedy' is not set; " \
                                       '{flag = "honest"} holds'
    assert e["call_guard"]["blocked"] == "doesn't know of stole_from(player, mara)"
    assert not any(x["open"] or x["chosen"] for x in e.values())


def test_utility_terms_say_how_they_add_up_and_a_gated_term_why_it_counted_nothing():
    s = session()
    s.update("mara", drives={"anger": 5}, flags={"tired": True})
    s.update("player", loc="bakery")
    e = by_do(s.explain("mara", "evening", {"amount": 20}))
    assert e["shut_shop"] == {"do": "shut_shop", "open": True, "utility": 14, "terms": ["3", "anger 5 x 2 + 1 = 11"],
                              "chosen": True}
    s.update("mara", flags={"tired": None})
    assert by_do(s.explain("mara", "evening", {"amount": 20}))["shut_shop"]["terms"] == \
        ["3", "0 (anger only if: flag 'tired' is not set)"]


def test_a_belief_too_weak_or_retracted_says_so():
    s = session()
    s.observe("steal", "player", at="bakery", claim=THEFT, witnesses=["wat"])
    s.tick(2)  # Wat 1.0, Edda 0.9, Mara 0.73: below call_guard's 0.8
    assert by_do(s.explain("mara", "evening", {"amount": 0}))["call_guard"]["blocked"] == \
        "believes stole_from(player, mara) only at 0.73, needs 0.8"
    s.observe("tell", "player", "mara", claim={**THEFT, "a": "wat"}, said=True)  # the player blames Wat
    assert by_do(s.explain("mara", "suspect"))["glare:wat"]["blocked"] == \
        "no longer believes stole_from(wat, mara) (retracted)"  # Edda's story beat the player's


def test_decide_carries_its_explanation_and_it_matches_what_was_decided():
    s = session()
    s.update("player", loc="bakery")
    s.observe("steal", "player", at="bakery", claim=THEFT, witnesses=["wat"])
    s.tick(2)
    line = s.decide("mara", "counter", explain=True)
    assert line.action == "refuse:player" and line.explain == [
        {"do": "serve:player", "open": True, "utility": 1, "terms": ["1"], "chosen": False},
        {"do": "refuse:player", "open": True, "utility": 4, "terms": ["anger 4"], "chosen": True}]
    assert s.decide("mara", "counter").explain is None  # only when asked


def test_choosing_nothing_still_says_why():
    s = session()
    line = s.decide("mara", "evening", {"amount": 0}, explain=True)
    assert line.action is None and line.explain is not None and len(line.explain) == 3
    s.retire("mara")
    gone = s.decide("mara", "evening", {"amount": 0}, explain=True)
    assert gone.explain is not None and {e["blocked"] for e in gone.explain} == {"mara has left the story"}


def test_explain_changes_nothing():
    s = session()
    before = s.snapshot()
    s.explain("mara", "counter")
    assert s.snapshot() == before


def test_explain_checks_the_call_as_decide_does():
    s = session()
    with pytest.raises(Exception, match="need bindings: 'amount'"):
        s.explain("mara", "evening")


def test_over_http():
    game = Game.parse(QUICKSTART, "quickstart")
    client = TestClient(create_app({"quickstart": game}))
    sid = client.post("/v1/sessions", json={"game": "quickstart"}).json()["session"]
    r = client.post(f"/v1/sessions/{sid}/decide", json={"npc": "mara", "moment": "counter", "explain": True})
    assert r.status_code == 200, r.text
    assert [e["do"] for e in r.json()["explain"]] == ["serve:player", "refuse:player"]
    plain = client.post(f"/v1/sessions/{sid}/decide", json={"npc": "mara", "moment": "counter"}).json()
    assert plain["explain"] is None
