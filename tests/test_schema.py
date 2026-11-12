"""A game file is checked when it loads (thespis.schema): a typo fails at once and names its entry, with what was
probably meant, instead of quietly switching a mechanic off. `thespis check` prints every mistake, a line each."""

from pathlib import Path

import pytest

from thespis.__main__ import main
from thespis.api import Game
from thespis.considerations import DefinitionError
from thespis.schema import examine

ROOT = Path(__file__).resolve().parents[1]
QUICKSTART = (ROOT / "examples" / "quickstart" / "game.toml").read_text(encoding="utf-8")
GAMES = [*sorted((ROOT / "examples").glob("*/game.toml")), ROOT / "sdk" / "godot" / "example" / "tavern.toml",
         ROOT / "sdk" / "unity" / "Lantern" / "Assets" / "Lantern" / "tavern.toml"]


def refused(old: str, new: str) -> list[str]:
    assert old in QUICKSTART, old
    with pytest.raises(DefinitionError) as e:
        Game.parse(QUICKSTART.replace(old, new, 1), "q")
    return e.value.problems  # type: ignore[attr-defined]


@pytest.mark.parametrize("path", GAMES, ids=lambda p: p.parent.name)
def test_every_game_in_the_repository_is_sound(path):
    assert examine(Game.load(path).cast.data) == ([], [])


# What a newcomer got wrong, building a game from the docs alone: each of these used to load without a word.
@pytest.mark.parametrize("old, new, says", [
    ("[gossip]", "[gosip]", "[gosip]: unknown table; did you mean [gossip]?"),
    ("[claims]", "[clams]", "[clams]: unknown table; did you mean [claims]?"),
    ("[npc.mara.feels]", "[npc.mara.feel]", "npc.mara: unknown table 'feel'; did you mean feels?"),
    ("[npc.mara.lines]", "[npc.mara.line]", "npc.mara: unknown table 'line'; did you mean lines?"),
    ("[[npc.mara.choices.counter]]\ndo = \"serve", "[[npc.mara.choice.counter]]\ndo = \"serve",
     "npc.mara: unknown table 'choice'; did you mean choices?"),
    ('persona = "The baker', 'persna = "The baker', "npc.mara: unknown key 'persna'; did you mean persona?"),
    ("trust_in = { edda = 2 }", "trust_in = { eda = 2 }", "npc.mara.trust_in.eda: no npc or player 'eda'; did you "
                                                          "mean edda?"),
    ("drives = { anger = 0 }", "drives = { anger = 50 }", "npc.mara.drives.anger: a whole number from 0 to 10, got 50"),
    ("trust_in = { edda = 2 }", "trust_in = { edda = 9 }", "npc.mara.trust_in.edda: a whole number from -5 to 5"),
    ('believes = { pred = "stole_from"', 'believes = { pred = "stolefrom"',
     "npc.mara.choices.counter[1].when[0].believes.pred: predicate 'stolefrom' is not in [words.claims]; did you "
     "mean stole_from?"),
    ('utility = [{ drive = "anger" }]', 'utility = [{ drive = "angr" }]',
     "npc.mara.choices.counter[1].utility[0].drive: no NPC or kind has a drive 'angr'; did you mean anger?"),
    ("stole_from = { anger = 6 }", "stolen = { anger = 6 }", "npc.mara.feels.stolen: predicate 'stolen' is not in "
                                                             "[words.claims]"),
    ('one_actor = ["stole_from"]', 'one_actor = ["stolefrom"]', "claims.one_actor[0]: predicate 'stolefrom'"),
    ('do = "refuse:player"', 'do = "refuse:bob"', "npc.mara.choices.counter[1].do: 'bob' is no npc, player or place"),
    ('between = ["edda", "mara"]', 'between = ["edda", "marra"]', "tie[1]: 'marra' is not an npc; did you mean mara?"),
    ("serve = \"Fresh this morning. What'll it be?\"", 'serve = { text = "Fresh" }',
     "npc.mara.lines.serve: words in quotes"),
    ('steal = "{a} stole', 'steal = "{nme} stole', "words.events.steal: {nme} is never filled here; it may use {a}, "
                                                   "{t}, {where}, {to}, {claim}, {amount}"),
])
def test_a_slip_names_its_entry(old, new, says):
    found = refused(old, new)
    assert any(says in p for p in found), found


@pytest.mark.parametrize("field", ["{a:>30000000}", "{a.__class__}", "{a[0]}", "{a!r}", "{}", "{0}"])
def test_a_template_holds_only_plain_names(field):
    """A template is filled with str.format, which would pad to any width or reach into objects: a game file sent to
    a server could make it build a string of any size."""
    found = refused('steal = "{a} stole', f'steal = "{field} stole')
    assert any(p.startswith("words.events.steal: ") and "only a plain name goes in braces" in p for p in found), found


def test_every_mistake_is_named_at_once():
    found = refused("[npc.mara.feels]", "[npc.mara.feel]")  # one slip...
    assert len(found) == 1
    text = QUICKSTART.replace("[npc.mara.feels]", "[npc.mara.feel]").replace("[claims]", "[clams]") \
        .replace("drives = { anger = 0 }", "drives = { anger = 11 }")
    with pytest.raises(DefinitionError) as e:
        Game.parse(text, "q")
    assert len(e.value.problems) == 3  # type: ignore[attr-defined]  # ...and three, in one go
    assert str(e.value).count("\n") == 2


def test_the_games_own_data_goes_in_custom():
    g = Game.parse(QUICKSTART + '\n[custom]\nmusic = "harvest.ogg"\n[custom.levels]\nfirst = 1\n', "q")
    assert g.cast.data["custom"]["levels"] == {"first": 1}
    assert any("keep the game's own data in [custom]" in p for p in refused("[claims]", "[levels]\nx = 1\n[claims]"))


def test_a_game_with_kinds_may_name_people_made_in_play():
    town = (ROOT / "examples" / "town" / "game.toml").read_text(encoding="utf-8")
    assert Game.parse(town.replace('[kind.townsfolk]', '[kind.townsfolk]\ntrust_in = { harl = -2 }', 1), "town")


def test_an_action_with_no_line_is_noted_not_refused():
    g = Game.parse(QUICKSTART.replace('serve = "Fresh this morning. What\'ll it be?"\n', ""), "q")
    assert g.notes == ["npc.mara.choices.counter[0].do: mara has no line for 'serve' in its lines, so it does this "
                       "in silence"]


def test_a_file_that_isnt_toml_says_so(tmp_path):
    bad = tmp_path / "game.toml"
    bad.write_text(QUICKSTART + "\n[game\n", encoding="utf-8")
    with pytest.raises(DefinitionError, match="not TOML: "):
        Game.load(bad)


def test_check_prints_each_mistake_a_line_and_fails(tmp_path, capsys):
    good, bad = tmp_path / "good.toml", tmp_path / "bad.toml"
    good.write_text(QUICKSTART, encoding="utf-8")
    bad.write_text(QUICKSTART.replace("[claims]", "[clams]").replace(
        "[npc.mara.feels]", "[npc.mara.feel]"), encoding="utf-8")
    assert main(["check", str(good)]) == 0
    assert capsys.readouterr().out == f"{good}: ok, quickstart: 3 npcs, 1 choice sets, 0 intents\n"
    assert main(["check", str(good), str(bad), str(tmp_path / "missing.toml")]) == 1
    out = capsys.readouterr().out.splitlines()
    assert f"{bad}: [clams]: unknown table; did you mean [claims]?" in out
    assert f"{bad}: npc.mara: unknown table 'feel'; did you mean feels?" in out
    assert any(line.startswith(f"{tmp_path / 'missing.toml'}: can't read it") for line in out)
    assert f"{good}: ok, quickstart: 3 npcs, 1 choice sets, 0 intents" in out


def test_serve_refuses_a_bad_game_in_a_line_not_a_traceback(tmp_path, capsys):
    bad = tmp_path / "bad.toml"
    bad.write_text(QUICKSTART.replace("[npc.mara.feels]", "[npc.mara.feel]"), encoding="utf-8")
    assert main(["serve", "--game", str(bad), "--port", "0", "--db", ":memory:"]) == 2
    assert capsys.readouterr().err == f"{bad}: npc.mara: unknown table 'feel'; did you mean feels?\n"
