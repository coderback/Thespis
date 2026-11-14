# Getting started

This walks through putting Thespis into a game of your own: the game file, then the calls a game makes, in the order
it makes them. It follows [examples/quickstart](../examples/quickstart), the village the README runs. The full
reference is [protocol.md](protocol.md).

## What Thespis does, and what it doesn't

Your game owns the world: where things are, what happens, the rules. Thespis owns the minds of the people in it.

- **It keeps what each NPC believes, and why.** Every belief has its sources and a confidence, and can be false.
  An NPC believes what it saw, and what it is told as far as it trusts the teller.
- **It moves news between people.** Gossip travels along the ties you declare, and weakens with each mouth.
- **It decides what an NPC does,** among the choices you declare, by drives and beliefs, with the reason recorded.
- **It speaks for them.** Each choice has a line in your own words. With a model, the model words it instead, and
  code checks that the line says nothing the NPC doesn't know.

It doesn't run your game, move your characters, decide what happened or need a model. A game with no model plays
exactly the same, on its own lines.

## Install

Thespis needs Python 3.12 or later. It's on PyPI as `thespis-sdk` (the name `thespis` was taken), and it imports as
`thespis`:

```bash
pip install thespis-sdk              # the library
pip install "thespis-sdk[serve]"     # and the sidecar, for other engines
```

The library has one dependency (`httpx`). Everything a game uses is in `thespis.api`; the rest of the package is
internal and may change between 0.x releases.

## 1. Describe the people: the game file

A game is one TOML file, checked when it loads: every mistake is named, with what was probably meant. The
quickstart's [game.toml](../examples/quickstart/game.toml) has every part a small game needs. Check yours as you write
it:

```bash
thespis check game.toml
```

```
game.toml: npc.mara: unknown table 'feel'; did you mean feels?
game.toml: npc.mara.choices.counter[1].when[0].believes.pred: predicate 'stolefrom' is not in [words.claims]; did you mean stole_from?
```

A file names only what it declares: people in `[npc]` or `[players]`, places in `[places]`, predicates in
`[words.claims]`, and drives in some NPC's `drives`. Keep your game's own data in `[custom]`; Thespis never reads it.

**In your editor.** Put this on your game file's first line, as the quickstart's does, and an editor that reads
TOML schemas (VS Code with Even Better TOML, or any editor using Taplo) offers every table and key as you type, says
what each is for, and underlines a misspelt key or a number out of range:

```toml
#:schema https://raw.githubusercontent.com/coderback/Thespis/main/docs/game.schema.json
```

The schema can't see everything `thespis check` does (that a place or a drive exists, what a template names), so
run that too.

**The world, as names.** Thespis doesn't model places; it needs their ids, for who is where.

```toml
[game]
id = "quickstart"
name = "Millbrook"
setting = "Millbrook, a village at harvest time: a bakery and a mill on either side of a square."

[places]
square = "the square"
bakery = "the bakery"

[player]
start = "square"
```

**The people.** Each NPC has a name, where it starts, and what a model reads to play it (`persona`, `goal`).
`drives` (0 to 10) are what pull it to act; `trust_in` (-5 to 5) is how far it believes each person's word.

```toml
[npc.mara]
name = "Mara"
start = "bakery"
goal = "Sell every loaf before dusk"
persona = "The baker: brisk, fair, and nobody's fool."
drives = { anger = 0 }
trust_in = { edda = 2 }

[npc.mara.feels]          # when she comes to believe this was done to her, scaled by how sure she is
stole_from = { anger = 6 }
```

**What they may do.** For each moment you'll ask about, list the choices: when each is open (`when`) and what it's
worth (`utility`). The highest wins. `[npc.<id>.lines]` holds the words for each, by the action's name.

```toml
[npc.mara.lines]
serve = "Fresh this morning. What'll it be?"
refuse = "Not you. I know what you did."

[[npc.mara.choices.counter]]
do = "serve:player"
utility = 1

[[npc.mara.choices.counter]]
do = "refuse:player"
utility = [{ drive = "anger" }]
when = [{ believes = { pred = "stole_from", a = "player", b = "self" } }]
```

**How news travels.** Ties carry gossip; `along` says how much survives each kind of tie. `[claims] one_actor` says
a theft has one thief, so someone told two stories keeps the one from the source they trust more. How far news
goes, and how sure it leaves people, is in [tuning.md](tuning.md).

```toml
[[tie]]
between = ["edda", "mara"]
kind = "friend"

[gossip]
about = ["player", "wat"]
along = { kin = 1.0, friend = 0.9 }

[claims]
one_actor = ["stole_from"]
```

**Words.** A claim and an event in words, for a model to read and for the narrator.

```toml
[words.claims]
stole_from = "{a} stole from {b}"

[words.events]
steal = "{a} stole a loaf from the counter at {where}."
```

[protocol.md](protocol.md#the-game-definition) lists every table, and the other examples use more of them:
[tavern](../examples/tavern/game.toml) (a whole scene, and the player's words),
[hamlet](../examples/hamlet/game.toml) (two players, feelings that fade) and
[town](../examples/town/game.toml) (people made in play, nobody named in the file).

## 2. Start a session

```python
from thespis.api import Game, Session, gateway_from_env

game = Game.load("game.toml")
s = Session.new(game, gateway=gateway_from_env())   # with no LLM_* set, there's no model: lines are your own words
```

A session is one playthrough's minds. Make one per save game.

## 3. Report what happened: `observe`

Call it whenever something happens that someone could know about. Thespis never decides what happened: it believes
you.

```python
# A deed: whoever saw it, or took part, believes it for certain.
s.observe("steal", "player", at="bakery", claim={"pred": "stole_from", "a": "player", "b": "mara"}, witnesses=["wat"])

# A statement: whoever heard it believes it as far as they trust the speaker. Its truth comes from the ledger.
s.observe("tell", "player", "mara", claim={"pred": "stole_from", "a": "wat", "b": "mara"}, said=True)
```

- `actor` and `target` took part, so they know. In the quickstart Mara was in the back room, so the theft has no
  target and only Wat saw it.
- `witnesses` are whoever else saw it: NPCs, or other players.
- `conf` sets how far a statement is believed when your own rules decide it, for example by a dice roll.

When your rules change an NPC (it moves, it's paid, it's hurt), say so with `update`:
`s.update("mara", loc="square", nudge={"anger": -2})`. `s.update("player", loc="bakery")` moves the player.

## 4. Let time pass: `tick`

```python
s.tick()        # or s.tick(3)
```

A tick is the minds' own time: NPCs walk their declared routes, gossip passes one step along each tie, drives drift
back and fade. Call it as often as your game's clock suggests: once a turn, once an in-game hour.

## 5. Ask what an NPC does: `decide` and `react`

```python
line = s.decide("mara", "counter")
line.action   # "refuse:player": apply it under your own rules
line.text     # "Not you. I know what you did."
line.reason   # "refuse:player scores 4"
```

- `decide(npc, moment)` picks among the choices for that moment and says its line. Pass `bindings` for names the
  choices leave open (`do = "accuse:{who}"`, `bindings={"who": "player"}`).
- `react(npc, trigger)` is a line with no decision behind it: a reply when the player insults them, a greeting. Its
  words are `[npc.<id>.lines]` by the trigger's name.
- An NPC that knows nothing says nothing: `line.text` is `None`.
- **Why (not)?** `s.explain("mara", "counter")`, or `decide(..., explain=True)`, lists every choice: whether it was
  open, what kept it shut (`"doesn't know of stole_from(player, mara)"`), and how its utility added up.

**With a model**, the library waits for it by default, so the line comes back final. Pass `wait=False` to get your
own line at once (`status == "provisional"`) and fetch the model's later with `s.line(line.id, wait=2)`. Either way
the model's line must cite what the NPC knows, or yours is used.

## 6. Look inside: `inspect`

```python
for b in s.inspect("mara")["beliefs"]:
    print(b["claim"], b["status"], b["opinion"]["b"], b["evidence"])
```

Every belief, retracted ones too, with its evidence: who it came from, through which event, how sure. It's what to
show in a debug panel, or a "why" view for players.

Through a sidecar or a server, you needn't build that panel to see it: `thespis serve` serves an inspector at
`/inspector/`. Open it beside the game (`http://127.0.0.1:7878/inspector/#token=<THESPIS_TOKEN>`) to watch the
cast, each mind, why an NPC chose what it did, the ledger and the grapevine as you play. It only reads.

## 7. Save and load

```python
saved = s.snapshot()                        # plain JSON: store it in your save file as text
s = Session.restore(game, saved)            # the same minds, which go on to play the same
```

A save made before you patched the game file still restores, brought up to the new file: an NPC you removed
retires, one you added joins, and `s.patched` says what changed. Keep NPC ids stable between releases: a new id is
a new NPC. [protocol.md](protocol.md#saves) has the rules.

## The player's words (optional)

If players can type to NPCs, declare what typing may do (`[intents]`, as in the [tavern](../examples/tavern/game.toml))
and ask `s.understand(text, to="mara")`. It reads the words as one of the acts open now (`act`), as something to
confirm first (`ask`), or as talk. It changes nothing: your game applies an act as it would the button.
[protocol.md](protocol.md#the-players-words) has the rules, and how it's measured.

## A model, or none

- **None:** the default. Every line is yours, and the game plays the same.
- **A hosted model:** set `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` for any OpenAI-compatible endpoint, with
  `LLM_PROFILE` for others (Anthropic, Gemini, Groq, vLLM, llama.cpp, Ollama). See [models.md](models.md).
- **A local model, offline:** `thespis models hardware` says what this machine can run, and `thespis models serve`
  runs it ([models.md](models.md#local-models-playing-offline)).

Whichever you use, code checks every line before it's heard: it cites only what the NPC knows, names only people the
game has, and stays short. A line that fails is replaced by yours.

## From another engine

`thespis serve --game game.toml` runs the same calls over HTTP, as a sidecar beside your game: localhost only, saved
to SQLite, offline unless you allow otherwise. [serve.md](serve.md) explains it, and the engines have clients:

- **Godot 4:** the [addon](../sdk/godot/README.md), with an example scene.
- **Unity:** the [package](../sdk/unity/README.md), with an example project.
- **Anything else:** the HTTP contract is [openapi-v1.json](openapi-v1.json).

## Testing your NPCs

With no model, the minds are deterministic: the same calls give the same beliefs, choices and lines. So an ordinary
unit test can play a scene and check what each NPC came to believe and do, as
[tests/test_quickstart.py](../tests/test_quickstart.py) does for the quickstart.

To measure what a model says, the repository's Rehearsal plays scenarios of engine calls and counts lines that leak
what the NPC couldn't know, invent things, or contradict it. The [tavern](../examples/tavern/scenarios.toml) has
scenarios; the README's [Rehearsal](../README.md#rehearsal) section shows how to run them. Rehearsal isn't in the
package, so it needs a clone.
