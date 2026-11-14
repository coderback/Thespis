"""The game file's JSON Schema (thespis.gameschema), for editors: committed as docs/game.schema.json, accepting every
game the loader accepts, and refusing the slips the loader refuses that a schema can see."""

import json
import tomllib
from pathlib import Path

import jsonschema
import pytest

from tests.test_schema import GAMES, QUICKSTART
from thespis.__main__ import game_schema
from thespis.api import Game
from thespis.considerations import DefinitionError
from thespis.gameschema import schema

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = jsonschema.Draft7Validator(schema())


def errors(text: str) -> list[str]:
    return ["/".join(map(str, e.absolute_path)) + ": " + e.message for e in VALIDATOR.iter_errors(tomllib.loads(text))]


def test_the_committed_schema_is_the_one_generated():
    """Regenerate with: python -m thespis schema --out docs/game.schema.json"""
    assert (ROOT / "docs" / "game.schema.json").read_text(encoding="utf-8") == game_schema()


def test_it_is_a_valid_schema():
    jsonschema.Draft7Validator.check_schema(json.loads(game_schema()))


@pytest.mark.parametrize("path", GAMES, ids=lambda p: p.parent.name)
def test_it_accepts_every_game_in_the_repository(path):
    assert errors(path.read_text(encoding="utf-8")) == []


# Slips the loader refuses that a schema can see: the wrong table or key, a number out of range, the wrong type.
@pytest.mark.parametrize("old, new", [
    ("[gossip]", "[gosip]"),
    ("[claims]", "[clams]"),
    ("[npc.mara.feels]", "[npc.mara.feel]"),
    ("[npc.mara.lines]", "[npc.mara.line]"),
    ("[[npc.mara.choices.counter]]\ndo = \"serve", "[[npc.mara.choice.counter]]\ndo = \"serve"),
    ('persona = "The baker', 'persna = "The baker'),
    ("drives = { anger = 0 }", "drives = { anger = 50 }"),
    ("trust_in = { edda = 2 }", "trust_in = { edda = 9 }"),
    ("trust_in = { edda = 2 }", "trust_in = { edda = 1.5 }"),
    ("along = { kin = 1.0, friend = 0.9 }", "along = { kin = 1.0, friend = 9 }"),
    ('when = [{ believes = { pred = "stole_from", a = "player", b = "self" } }]',
     'when = [{ belives = { pred = "stole_from", a = "player", b = "self" } }]'),
    ('when = [{ believes = { pred = "stole_from", a = "player", b = "self" } }]',
     'when = [{ believes = { prd = "stole_from", a = "player", b = "self" } }]'),
    ('utility = [{ drive = "anger" }]', 'utility = [{ drive = "anger", wieght = 2 }]'),
    ('one_actor = ["stole_from"]', 'one_actor = "stole_from"'),
    ("[[tie]]\nbetween = [\"wat\", \"edda\"]", "[[tie]]\nbetwen = [\"wat\", \"edda\"]"),
])
def test_it_refuses_what_the_loader_refuses(old, new):
    assert old in QUICKSTART, old
    bad = QUICKSTART.replace(old, new, 1)
    with pytest.raises(DefinitionError):
        Game.parse(bad, "q")
    assert errors(bad), new


def test_every_key_the_loader_allows_is_offered():
    """The schema is built from the loader's own lists: each table holds exactly the keys the loader allows."""
    from thespis import schema as loader
    s = schema()
    tables = s["properties"]
    assert set(tables) == set(loader.TABLES)
    assert set(tables["gossip"]["properties"]) == set(loader.GOSSIP)
    assert set(tables["claims"]["properties"]) == set(loader.CLAIMS)
    assert set(tables["memory"]["properties"]) == set(loader.MEMORY)
    npc = tables["npc"]["additionalProperties"]
    assert set(npc["properties"]) == set(loader.NPC_KEYS)
    assert set(tables["kind"]["additionalProperties"]["properties"]) == set(loader.PERSON)


def test_the_quickstart_points_editors_at_it():
    first = (ROOT / "examples" / "quickstart" / "game.toml").read_text(encoding="utf-8").splitlines()[0]
    assert first == "#:schema https://raw.githubusercontent.com/coderback/Thespis/main/docs/game.schema.json"
