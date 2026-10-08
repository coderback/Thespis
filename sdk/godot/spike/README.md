# The Godot spike

One Godot 4 scene playing through the Thespis `/v1` protocol ([docs/protocol.md](../../../docs/protocol.md)). It
tests the protocol from a real engine before the Godot addon (Phase 4.6) is built on it. The scene is the tavern
from [examples/tavern/game.toml](../../../examples/tavern/game.toml): Garrick sits in the taproom while Wren polishes
the bar. Insult him, then ask what he does.

| File | What it is |
| --- | --- |
| `thespis.gd` | A thin client: one coroutine per `/v1` route, over `HTTPRequest`, in plain GDScript |
| `main.tscn`, `main.gd` | The scene. The engine reports the insult, who saw it and what it did to Garrick; Thespis says what he does and what he says |
| `test/round_trip.gd` | The gate: the scene driven headless, with 13 checks |
| `test/run.py` | Starts a scripted OpenAI-compatible model and `thespis serve` speaking through it, then runs Godot headless |

## Run it

```sh
# The round trip, headless (Godot 4.7's console build):
python sdk/godot/spike/test/run.py --godot <path to Godot_v4.7.2-stable_win64_console.exe>
GODOT=<path> pytest tests/test_godot_spike.py   # the same, under pytest; skipped when GODOT isn't set

# Or by hand: serve the tavern, then open sdk/godot/spike in the Godot editor and press F5.
python -m thespis serve --game examples/tavern/game.toml
```

The scripted model takes 1 s to answer, so the run shows the protocol's two speeds. Garrick's template line reached
the scene **23 ms** after `decide` was called (localhost, provisional), and the model's line replaced it at
**1053 ms** (final, citing the insult).

## What the spike checks

1. A session opens on the tavern.
2. Before anything happens, Garrick knows nothing. He leaves, says nothing, and no model is asked.
3. The insult is observed, with Wren as a witness, and the engine raises his grudge.
4. He confronts the player. His template line arrives provisional, and the model's line settles it, citing the insult.
5. Wren, who saw it, believes it.
6. The session is saved to a file through Godot's JSON, closed, and restored. The minds are the same, and the restored Garrick decides exactly as before.

## Protocol friction

This list is the spike's real output: everything that was awkward to do from GDScript, and what each implies.

### Fixed in this PR

| Friction | What happened | Fix |
| --- | --- | --- |
| **Saves come back as floats** | GDScript reads every JSON number as a float. A save that went through Godot restored with `phase: 1.0` and float drives, so the restored Garrick's reason read `confront:player scores 7.0` and the world was no longer the one saved. The check catches it: with the fix taken out, it fails | `Session.restore` turns whole numbers back into ints, keeping evidence confidences as floats. Tested in Python too |
| **A model call that could only fail** | Asked to decide when he knew nothing, Garrick's line came back provisional with no text, and the model was asked anyway. Every line must cite something, so the model's reply could only be rejected | When the state pack holds nothing to cite, the model isn't asked and the line is final (silent) at once |

### What it implies for later PRs

| Friction | Implies | When |
| --- | --- | --- |
| **One game event takes two calls.** The insult is `observe`, and its effect on Garrick is `update(nudge)`. In between, his mind believes the insult but isn't angry yet | Declared feelings in the game file: when an NPC comes to believe a claim about itself, its drives move (`[npc.garrick.feels] insulted = { grudge = 4 }`). The engine then reports only the event | 4.5, with drive dynamics |
| **The client unpacks and repacks saves.** A save is the minds' business, but the client parses it into a Dictionary and stringifies it back, which is how the floats got in | The SDK stores the save as the raw response text and sends it back verbatim. `/v1` doesn't change; restore already copes | 4.6 SDK |
| **Every reply is an untyped Dictionary.** `line.get("staus")` fails silently, and `grudge` is `4.0` | Typed GDScript classes generated from `docs/openapi-v1.json`, as planned | 4.6 SDK |
| **No exceptions in GDScript.** An error comes back as `{error, reason}` beside the success shapes, and the client has to look for the key | The SDK returns a result with `ok`, `value` and `error`. The bodies are already uniform, so `/v1` doesn't change | 4.6 SDK |
| **One `HTTPRequest` carries one request at a time.** A poll in flight blocks the next call on the same node | The client makes a node per call. The SDK keeps a small pool. No protocol change | 4.6 SDK |
| **The engine has to start the server.** Here the runner starts `thespis serve` | The addon launches the sidecar, health-checks it and stops it with the game | 4.4 sidecar, 4.6 addon |
| **`class_name` needs an editor import**, so a headless run of an unimported project can't see it | The spike preloads its client by path. The addon is imported by the editor, so it can use `class_name` | 4.6 addon |
| **A silent line is `text: null`**, and `"%s" % null` prints `<null>` | Keep `null`: it means the NPC chose silence, which differs from an empty line. The SDK gives `text` a default and an `is_silent()` check | 4.6 SDK |

### What turned out fine

- **Polling long-polls.** `GET .../lines/{id}?wait=2` gave the final line in one poll. Server-sent events would mean hand-driving `HTTPClient` in GDScript, so polling stays the Godot path and SSE isn't needed for Godot.
- **The routes and bodies map one to one onto coroutines.** `await thespis.decide("garrick", "turn")` reads like the library call.
- **Session ids in the URL** need no headers or cookies, which suits `HTTPRequest`.
