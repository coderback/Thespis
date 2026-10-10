# Thespis for Godot

A Godot 4 addon that gives a game's NPCs Thespis minds through the `/v1` protocol ([docs/protocol.md](../../docs/protocol.md)).
The engine owns the world: it reports what happened and who saw it, and asks what an NPC does and says. Thespis
owns the minds: what each NPC believes, what it chooses among the actions the game file declares, and its words.

The same scene plays **offline**, through a sidecar the addon starts on the player's machine, and **online**,
through a Thespis server. Which one is a setting, not code.

| Path | What it is |
| --- | --- |
| `addons/thespis/` | The addon: copy this folder into your project |
| `addons/thespis/thespis.gd` | `ThespisClient`, the `Thespis` autoload: every call, as a coroutine |
| `addons/thespis/api.gd` | `ThespisApi`: a typed class per `/v1` schema and the route table, **generated** from [docs/openapi-v1.json](../../docs/openapi-v1.json) |
| `addons/thespis/line.gd`, `result.gd` | `ThespisLine` (a line that settles) and `ThespisResult` (what every call returns) |
| `addons/thespis/sidecar.gd` | `ThespisSidecar`: starts the runtime beside the game and stops it with the game |
| `example/` | The Lantern: the crypt road's first act in miniature, played through the addon |
| `test/` | The gate: the example driven headless against a sidecar and a server |

## Install

1. Copy `addons/thespis` into your project's `addons/`.
2. Enable **Thespis** in Project Settings → Plugins. That adds the `Thespis` autoload and the `thespis/*` settings.
3. Put your `game.toml` in the project and point `thespis/game/definition` at it. In the export preset, add `*.toml`
   to the non-resource files to export (Resources → Filters), so it ships in the game.

## Play

```gdscript
func _ready() -> void:
    Thespis.line_arrived.connect(show_line)     # a line to show now; it may be the template, provisional
    Thespis.line_settled.connect(show_line)     # the model's words replaced it (or it was withdrawn)
    var r := await Thespis.start()              # the sidecar or the server the settings say
    if r.ok:
        r = await Thespis.open("tavern")
    if not r.ok:
        push_warning("No Thespis: %s" % r.reason)

func insult_garrick() -> void:
    # The engine says what happened and who saw it. The game file says what an insult does to Garrick.
    await Thespis.observe(ThespisClient.event("insult", "player", "garrick",
            ThespisClient.claim("insulted", "player", "garrick"), ["wren"]))

func ask_garrick() -> void:
    var r := await Thespis.decide("garrick", "turn")    # his choice, among the ones his game file declares
    if r.ok and r.value.action == "share_drink:player":
        pour_drinks()                                    # the engine carries it out

func show_line(line: ThespisLine) -> void:
    if line.is_withdrawn():
        bubble.hide()
    else:
        bubble.text = line.words("...")                  # null text means the NPC chose silence
        bubble.modulate.a = 0.6 if line.is_provisional() else 1.0
```

- **Every call is a coroutine returning a `ThespisResult`:** `ok`, then `value` or `error`, `reason` and `status`.
  Nothing raises, and a server that's away is a result like any other (`unreachable`).
- **Replies are typed.** `decide` gives a `ThespisLine`, `observe` a `ThespisApi.EventOut`, `tick` a
  `ThespisApi.TickOut`. Whole numbers come back as `int`, not GDScript JSON's floats.
- **Lines settle by themselves.** A provisional line is the game's own template line, safe to show at once. The client
  follows it (long-polling the server) and updates the same `ThespisLine` in place, then emits `line_settled` and the
  line's own `settled`. `await Thespis.settle(line)` waits for it. Pass `{"wait": true}` to get the final line in one
  call instead.
- **Many calls at once are fine.** Each request uses its own `HTTPRequest` from a small pool (`max_requests`, 6), so
  a poll held open never blocks the player's next action.

## The player's words

A player can type instead of pressing a button. The game file declares the acts they may do by typing (`[intents]`,
[docs/protocol.md](../../docs/protocol.md#the-players-words)), and `understand` says which one their words do:

```gdscript
func say(text: String) -> void:
    var r := await Thespis.understand(text, "garrick")    # what the player typed, and whom they said it to
    if not r.ok:
        return
    match r.value.status:
        "act":                                            # a sure reading: carry it out, as its button would
            carry_out(r.value.intent)
        "ask":                                            # perhaps an act with consequences: ask the player first
            for reading in r.value.readings:
                add_button("Did you mean: %s?" % reading.reads, carry_out.bind(reading))
        "talk":                                           # the words do none of the game's acts
            await Thespis.react("garrick", "talk")

func carry_out(intent: ThespisApi.IntentOut) -> void:
    match intent.verb:
        "insult":
            insult_garrick()
        "tell":                                           # the claim goes back to observe as it came
            await Thespis.observe(ThespisClient.event("tell", "player", "garrick", intent.args["claim"],
                    ["wren"], {"said": true}))
```

- **`understand` only reads.** The engine carries the act out as it would the button, and reports it with `observe`.
  So a lie the player types ("Wren insulted Pip.") is logged false by the ledger, as one told with a button is.
- **The words can only pick.** A reading is one of the acts the game declares, and each argument comes from the game's
  own lists: the NPCs there, its claims, an amount within its bounds. A line that tells the model what to answer can
  pick, at most, an act the player could have clicked. The gate types one to a model that obeys it: 5000 coins, where
  the game offers up to 100, is refused, and nothing changes.
- **Say what's open now** with `offered`, as your buttons have it:
  `Thespis.understand(text, "garrick", {"offered": [{"verb": "pay", "args": {"amount": {"min": 1, "max": coins}}}]})`.
  Left out, every act the game declares is open.
- **A local model asks first.** None has passed the words gate, so an act with consequences that one reads comes back
  as `ask`. What the game's own phrases read (an intent's `examples`, and its claims stated plainly) is `act`, with no
  model at all.
- **Numbers in `intent.args` are floats,** as every JSON number is in GDScript: `int(intent.args["amount"])`.

The Lantern has a box to say something to Garrick (`example/tavern.gd`: `say`, `carry_out`).

## Saves

```gdscript
var minds := await Thespis.snapshot()             # ok with a String: the session as Thespis wrote it
save["minds"] = minds.value                       # keep it as text in your own save file
...
await Thespis.restore("tavern", save["minds"])    # sent back exactly as written
```

Keep the snapshot as text. Parsed into a `Dictionary`, its whole numbers would become floats on the way through.

## Where it runs

| Setting | Default | What it does |
| --- | --- | --- |
| `thespis/connection/url` | empty | A Thespis server. **Empty: start a sidecar on this machine.** `$THESPIS_URL` overrides it |
| `thespis/connection/key` | empty | The server's project key (`tsk_...`). `$THESPIS_KEY` overrides it |
| `thespis/game/definition` | empty | The game file `start()` sends, so the runtime knows the game |
| `thespis/sidecar/command` | empty | How to run the runtime. Empty: `thespis/thespis(.exe)` beside the game's executable, else `python -m thespis` |
| `thespis/sidecar/model` | empty | A local model for the sidecar: `auto`, or an id such as `gemma4-e4b`. Empty: the game's template lines |
| `thespis/sidecar/online` | off | Let the sidecar reach the network, for a cloud model. Off, it refuses every connection off the machine |
| `thespis/sidecar/start_timeout` | 120 s | How long to wait for the sidecar, a local model's first load included |

**Offline (the sidecar).** `start()` runs `thespis serve --port 0`, reads the address it prints, and gives it a random
token through its environment, so no other program on the machine can use it.
- **When it stops:** the sidecar stops with the game. The client kills it on the way out, and `--parent` has the
  runtime watch the game's process in case the game is killed first.
- **Shipping it:** ship the packaged runtime from `python tools/package.py` (one folder, about 20 MB, no Python
  needed) as `thespis/` beside the game's executable.
- **The local model:** it must be on the player's machine before the first offline run. The runtime fetches it once
  while online with `thespis models pull <id>`, or your installer can.
- **Sessions:** they're kept in `user://thespis/sessions.sqlite`.

**Online (a server).** Set `thespis/connection/url` to a server (`thespis serve --server`, [docs/serve.md](../../docs/serve.md))
and `thespis/connection/key` to your project's key. `start()` sends the game file, since a server only knows the games
its projects send it.

A key in the game's settings ships inside the game, where any player can read it. That's fine for development, and for
a server only you use. A public game should reach Thespis through its own backend, which holds the key.

## The typed layer is generated

`api.gd` is written by [tools/sdk_gen.py](../../tools/sdk_gen.py) from the committed OpenAPI spec. It holds one class
per schema, with typed fields, `read()` and `to_dict()`, and the table of routes the client calls through. The calls
you write against (`decide`, `observe`, the signals) are written by hand around it. A change to the server changes
the spec, `python tools/sdk_gen.py godot` regenerates the file, and CI fails while either is stale.

## Test

```sh
python sdk/godot/test/run.py --godot <Godot 4.7 console build>              # the example, against a sidecar and a server
python sdk/godot/test/run.py --godot <...> --mode sidecar --local gemma4-e4b      # offline, through a local model
python sdk/godot/test/run.py --godot <...> --mode sidecar --exe dist/thespis/thespis.exe   # the packaged runtime
```

The runner plays `example/tavern.tscn` under `test/example_test.gd` twice, and the scene doesn't change between the
two runs:
- **Sidecar:** the addon starts the runtime itself, offline. It gets 30 checks.
- **Server:** a hosted-mode server with a project and its key, found through `THESPIS_URL` and `THESPIS_KEY`. It
  gets 28 checks; the two sidecar-only ones don't apply.

By default the model is scripted ([sdk/harness.py](../harness.py)), answering a line after 1 s. A typical run shows
the template line 33 ms after `decide`, then the model's line 1.04 s after it. Reading the player's words, the
scripted model does as it's told: it gives back as its reading any JSON the text carries, and says yes when asked to
confirm one. So the injection check is read by a model that obeys the injection.

The checks:
- typed replies;
- a provisional line followed until it settles, and shown in the scene;
- a failed call coming back as a result;
- a tick, and a narration;
- eight calls at once through six requests;
- the player's words, typed to Garrick (nine checks):
  - an insult read from the game's own phrases with no model, and carried out as the button would;
  - a lie typed in the scene's box, logged false by the ledger and believed by Garrick;
  - an injection that the model obeys, which is no act and leaves every mind and the ledger as they were;
  - an unsure reading shown as a "Did you mean...?" button, which carries the act out when pressed;
- a save through the game's own save file, restored as it was;
- the sidecar refusing nothing off the machine, and stopping with the client.

CI runs the same on Linux with Godot 4.7.2.

## What the spike taught, and what the addon does about it

The spike (Phase 4.1b) played the tavern through a thin client to find what was awkward in `/v1` from GDScript. Its
list, and the answers:

| Friction | Answer |
| --- | --- |
| One game event took two calls (`observe`, then `update` to anger Garrick) | Declared feelings, 4.5: `[npc.garrick.feels] insulted = { grudge = 4 }`. The scene reports only the event |
| Saves came back as floats through GDScript's JSON | The server turns whole numbers back into ints (4.1b), and the addon keeps a snapshot as text, so nothing parses it on the way |
| Every reply was an untyped Dictionary | Typed classes generated from the spec: `line.status`, not `line.get("staus")` |
| No exceptions in GDScript | `ThespisResult` on every call |
| One `HTTPRequest` carries one request | A pool of them, and calls past `max_requests` wait their turn |
| The engine had to start the server | `ThespisSidecar`: started, health-checked and stopped by the addon |
| `class_name` needs an editor import | The addon is imported, so its classes have names. The runner imports headless first (`--import`) |
| A silent line is `text: null` | Kept, because silence differs from an empty line. `is_silent()` tells them apart, and `words(otherwise)` gives text to show |
| Polling vs server-sent events | Polling stays. The client long-polls, so a line settles in one round trip after the model answers |
