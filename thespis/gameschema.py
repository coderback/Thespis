"""A JSON Schema for game files, for editors: autocomplete, hover help and red underlines while writing a game.toml.

Built from the same lists the loader checks against (thespis.schema, thespis.considerations, thespis.intents), so the
two can't drift: a key the loader accepts, the schema offers, and a key it refuses, the schema underlines. The loader
checks more than a schema can say (that a place exists, that a drive is somebody's, what a template names), so
`thespis check` is still the last word; the schema catches slips as they're typed.

    python -m thespis schema --out docs/game.schema.json

Point an editor at it with a comment on a game file's first line (Even Better TOML, and any editor using Taplo):

    #:schema https://raw.githubusercontent.com/coderback/Thespis/main/docs/game.schema.json
"""

from __future__ import annotations

from typing import Any

from thespis.considerations import CHOICE, COMPARE, TERM
from thespis.intents import TYPES
from thespis.schema import (
    ARG,
    CLAIM_KEYS,
    CLAIMS,
    DECAY,
    DRIVES,
    EVERYONE,
    GAME,
    GOSSIP,
    INTENT,
    MEMORY,
    NARRATOR,
    NPC_KEYS,
    PERSON,
    PLAYER,
    PLAYERS,
    TABLES,
    TIE,
    TRUST,
    WORDS,
)

ID = "https://raw.githubusercontent.com/coderback/Thespis/main/docs/game.schema.json"
J = dict[str, Any]


def _table(props: dict[str, J], keys: tuple[str, ...], required: tuple[str, ...] = (), about: str = "") -> J:
    """A table that holds exactly `keys` (every one described in `props`), and needs `required`."""
    missing = set(keys) - set(props)
    assert not missing, f"no schema for {sorted(missing)}"  # a key the loader allows must be described here
    out: J = {"type": "object", "properties": {k: props[k] for k in keys}, "additionalProperties": False}
    if required:
        out["required"] = list(required)
    if about:
        out["description"] = about
    return out


def _of(value: J, about: str = "") -> J:
    """A table of any keys, each holding `value`."""
    out: J = {"type": "object", "additionalProperties": value}
    if about:
        out["description"] = about
    return out


def _say(about: str, **schema: Any) -> J:
    return {**schema, "description": about}


TEXT = {"type": "string"}
WORDS_OF = _of(TEXT)
NAMES = {"type": "array", "items": TEXT}
SHARE = {"type": "number", "minimum": 0, "maximum": 1}
WHOLE_FROM_0 = {"type": "integer", "minimum": 0}


def schema() -> J:
    """The JSON Schema (draft-07) of a game file."""
    claim = _table({
        "pred": _say("A predicate from [words.claims]", **TEXT),
        "a": _say("Who it's about: an npc, \"player\", or \"self\" (the NPC choosing)", **TEXT),
        "b": _say("Whom or what it names", **TEXT),
        "place": _say("Where it held, from [places]", **TEXT),
        "at": _say("The phase it held", type="integer"),
        "neg": _say("A denial: it never happened", type="boolean"),
    }, CLAIM_KEYS, ("pred", "a"), "A claim: something one can believe")
    ref = {"$ref": "#/definitions/condition"}
    conditions = {"anyOf": [ref, {"type": "array", "items": ref}]}
    compare = {k: {"type": "number"} for k in COMPARE}
    condition = {"anyOf": [
        {**_table({"drive": TEXT, **compare}, ("drive", *COMPARE), ("drive",),
                  "A drive compared: {drive = \"anger\", gte = 4}"), "minProperties": 2},
        _table({"bound": TEXT, "is": {"type": ["string", "number"]}, **compare}, ("bound", "is", *COMPARE),
               ("bound",), "A value the game passed when it asked: {bound = \"amount\", gte = 10}"),
        _table({"at": TEXT}, ("at",), ("at",), "Where the NPC is"),
        _table({"with": TEXT}, ("with",), ("with",), "In the same place as someone"),
        {**_table({"trust": TEXT, **compare}, ("trust", *COMPARE), ("trust",),
                  "The NPC's trust in someone, -5 to 5: {trust = \"player\", gte = 2}"), "minProperties": 2},
        _table({"caught": TEXT}, ("caught",), ("caught",), "The NPC has caught someone in a lie"),
        _table({"flag": TEXT}, ("flag",), ("flag",), "A flag of the NPC's is set"),
        _table({"not_flag": TEXT}, ("not_flag",), ("not_flag",), "A flag of the NPC's isn't set"),
        _table({"believes": claim, "min": SHARE}, ("believes", "min"), ("believes",),
               "The NPC believes a claim, at least as surely as `min` if given"),
        _table({"any": {"type": "array", "items": ref}}, ("any",), ("any",), "Any of these holds"),
        _table({"all": {"type": "array", "items": ref}}, ("all",), ("all",), "All of these hold"),
        _table({"not": ref}, ("not",), ("not",), "This doesn't hold"),
    ]}
    term = _table({"drive": TEXT, "bound": TEXT, "weight": {"type": "number"}, "plus": {"type": "number"},
                   "if": conditions}, TERM, (),
                  "A drive (or a number the game passed, `bound`) times its weight plus a constant, counted only "
                  "when its `if` holds")
    one = {"anyOf": [{"type": "number"}, term]}
    choice = _table({
        "do": _say("The action: \"serve:player\", \"accuse:{who}\"", **TEXT),
        "utility": _say("How much it's worth: a number, a term, or a list of them added up",
                        anyOf=[one, {"type": "array", "items": one}]),
        "when": _say("Every condition must hold for it to be open", **conditions),
        "asserts": _say("The claim the action states", **claim),
    }, CHOICE, ("do", "utility"))
    drives = _of({"type": "integer", "minimum": DRIVES[0], "maximum": DRIVES[1]})
    person = {
        "name": _say("What others and the narrator call them", **TEXT),
        "start": _say("Where they start, from [places]", **TEXT),
        "aliases": _say("Other names the player may use", **NAMES),
        "persona": _say("Who they are, for the model", **TEXT),
        "goal": _say("What they want, for the model", **TEXT),
        "drives": _say("Their drives and where each starts, 0 to 10", **drives),
        "trust_in": _say("Trust in each person, -5 to 5 (0 if left out)",
                         **_of({"type": "integer", "minimum": TRUST[0], "maximum": TRUST[1]})),
        "walk": _say("Places, one a tick, round and round", **NAMES),
        "settle": _say("The value each drive drifts back to, a step a tick", **drives),
        "feels": _say("Drives moved when they come to believe a predicate was done to them, by how sure they are",
                      **_of(_of({"type": "integer"}))),
        "decay": _say("Drives that fade towards `to` with a half-life, keeping a share `keep` of their peak",
                      **_of(_table({"to": {"type": "number"}, "half_life": {"type": "number", "exclusiveMinimum": 0},
                                    "keep": SHARE}, DECAY, ("half_life",)))),
        "lines": _say("Their own words by key: an action's kind, or a trigger", **WORDS_OF),
        "choices": _say("What they may do at each moment the game asks: [[npc.<id>.choices.<moment>]]",
                        **_of({"type": "array", "items": choice, "minItems": 1})),
    }
    arg = {"anyOf": [{"enum": list(TYPES)}, _table({
        "type": {"enum": list(TYPES)}, "options": NAMES, "min": {"type": "integer"}, "max": {"type": "integer"},
        "preds": NAMES, "optional": {"type": "boolean"}, "denials": {"type": "boolean"},
    }, ARG, ("type",))]}
    everyone = {"anyOf": [{"const": EVERYONE}, NAMES]}
    tables: dict[str, J] = {
        "game": _table({k: TEXT for k in GAME}, GAME, (), "The game's id, name and setting"),
        "places": _say("Every place, by id: its name", **WORDS_OF),
        "player": _table({"start": TEXT}, PLAYER, (), "Where the player starts"),
        "players": _say("More players, by id", **_of(_table({"name": TEXT, "start": TEXT}, PLAYERS, ("name",)))),
        "npc": _say("The cast, by id", **_of(_table(person, NPC_KEYS, ("name", "start", "persona", "goal")))),
        "kind": _say("Kinds of people who join in play (add), by kind", **_of(_table(person, PERSON,
                                                                                     ("persona", "goal")))),
        "tie": _say("Relationships gossip travels along: [[tie]] between = [a, b], kind = ...",
                    type="array", items=_table({"between": {**NAMES, "minItems": 2, "maxItems": 2}, "kind": TEXT},
                                               TIE, TIE)),
        "gossip": _table({
            "gossips": _say("Who passes news on: npc ids, or \"everyone\"", **everyone),
            "about": _say("Whose news travels: ids, or \"everyone\" (the player's if left out)", **everyone),
            "priority": _say("By predicate: the higher, the sooner it's told", **_of({"type": "number"})),
            "threshold": _say("How sure a teller must be to pass something on (0.5)", **SHARE),
            "decay": _say("How much of a story survives each telling, without ties (0.8)", **SHARE),
            "along": _say("By kind of tie: how much of a story carries along it", **_of(SHARE)),
            "in_person": _say("How much carries to someone standing with the teller (0.8)", **SHARE),
            "most": _say("At most this many things told a tick, the town over", type="integer", minimum=1),
            "corroborate": _say("A second witness's word makes a listener surer", type="boolean"),
        }, GOSSIP, (), "How news travels"),
        "claims": _table({
            "one_actor": _say("Deeds only one person can have done to another", **NAMES),
            "caught": _say("How far trust falls in whoever started a losing story (2)", **WHOLE_FROM_0),
            "first_hand": _say("How much more a teller who saw it counts", **WHOLE_FROM_0),
            "description": TEXT,
        }, CLAIMS, (), "What can't both be true"),
        "words": _table({"claims": _say("Every predicate, in words: \"{a} stole from {b}\"", **WORDS_OF),
                         "events": _say("Every event's verb, in words: \"{a} told {t} that {claim}.\"",
                                        **WORDS_OF)}, WORDS),
        "actions": _say("Every action's kind, in words: \"{who}\"", **WORDS_OF),
        "intents": _say("What the player's words may do, by verb", **_of(_table({
            "means": _say("What doing it is", **TEXT), "reads": TEXT,
            "args": _of(arg), "examples": NAMES, "consequential": {"type": "boolean"}, "asks": {"type": "boolean"},
        }, INTENT, ()))),
        "situations": _say("What's happening at a moment, for the model, by moment", **WORDS_OF),
        "narrator": _table({"name": TEXT, "persona": TEXT, "structured": {"type": "boolean"}}, NARRATOR),
        "memory": _table({
            "recall": {"const": "meaning"}, "salient": _of({"type": "number"}),
            **{k: {"type": "number"} for k in MEMORY if k not in ("recall", "salient")},
        }, MEMORY, (), "Recall by meaning"),
        "custom": _say("The game's own data: Thespis never reads it", type="object"),
    }
    out = _table(tables, TABLES)
    return {"$schema": "http://json-schema.org/draft-07/schema#", "$id": ID, "title": "Thespis game file",
            "description": "A game.toml: its people, places, words and rules (docs/protocol.md)",
            **out, "definitions": {"condition": condition}}
