"""A save made before the game file changed still restores, brought up to the file, and says how. A released game is
patched while its players' saves stay on disk: a save that loaded and then failed mid-game (KeyError on the first
tick after an NPC was renamed) would lose them their game."""

from pathlib import Path

import pytest

from thespis.api import Game, Session
from thespis.considerations import DefinitionError

ROOT = Path(__file__).resolve().parents[1]
QUICKSTART = (ROOT / "examples" / "quickstart" / "game.toml").read_text(encoding="utf-8")
TOWN = (ROOT / "examples" / "town" / "game.toml").read_text(encoding="utf-8")
THEFT = {"pred": "stole_from", "a": "player", "b": "mara"}


def played() -> dict:
    s = Session.new(Game.parse(QUICKSTART, "quickstart"))
    s.observe("steal", "player", at="bakery", claim=THEFT, witnesses=["wat"])
    s.tick()
    return s.snapshot()


def test_the_same_game_restores_unpatched():
    s = Session.restore(Game.parse(QUICKSTART, "quickstart"), played())
    assert s.patched == []


def test_an_npc_renamed_in_a_patch_is_a_new_one_and_the_old_retires():
    saved = played()
    renamed = QUICKSTART.replace("[npc.wat]", "[npc.walt]").replace('"wat"', '"walt"').replace("wat =", "walt =")
    s = Session.restore(Game.parse(renamed, "quickstart"), saved)
    assert s.patched == ["wat: no longer in the game file, so retired; what it believed is kept",
                         "walt: new in the game file, so joined at mill"]
    assert s.inspect("walt")["beliefs"] == []  # he saw nothing: he wasn't there
    s.tick(2)  # used to be KeyError: 'wat'
    assert s.inspect("wat")["npc"]["gone"] and s.inspect("wat")["beliefs"]  # he keeps what he saw
    assert Session.restore(Game.parse(renamed, "quickstart"), s.snapshot()).patched == []  # saved under the new file


def test_an_npc_in_a_place_the_patch_removed_goes_back_to_its_start():
    s = Session.new(Game.parse(QUICKSTART.replace('square = "the square"', 'square = "the square"\nyard = "a yard"'),
                               "quickstart"))
    s.update("edda", loc="yard")
    s.update("player", loc="yard")
    s = Session.restore(Game.parse(QUICKSTART, "quickstart"), s.snapshot())
    assert s.patched == ["edda: 'yard' is no longer a place, so back to 'mill'",
                         "player: 'yard' is no longer a place, so back to 'square'"]
    assert s.inspect("edda")["npc"]["loc"] == "mill" and s.world.player["loc"] == "square"


def test_a_patch_that_changes_only_words_changes_nothing_else():
    saved = played()
    s = Session.restore(Game.parse(QUICKSTART.replace("Not you. I know what you did.", "Not you, thief."),
                                   "quickstart"), saved)
    assert s.patched == []
    s.tick()  # the story reaches Mara, as it would have
    s.update("player", loc="bakery")
    assert s.decide("mara", "counter").text == "Not you, thief."


def test_a_save_with_people_of_a_kind_the_patch_removed_is_refused():
    s = Session.new(Game.parse(TOWN, "town"))
    s.add("mara", "guard", "Mara Reed", at="docks")
    without = TOWN[:TOWN.index("[kind.guard]")] + TOWN[TOWN.index("[gossip]"):]
    with pytest.raises(DefinitionError, match=r"people of a kind the game file no longer has: mara \(guard\)"):
        Session.restore(Game.parse(without, "town"), s.snapshot())
