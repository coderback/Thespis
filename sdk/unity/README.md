# Thespis for Unity

A Unity package that gives a game's NPCs Thespis minds through the `/v1` protocol ([docs/protocol.md](../../docs/protocol.md)).
It has the same shape as the Godot addon ([sdk/godot](../godot/README.md)). The engine owns the world: it reports
what happened and who saw it, and asks what an NPC does and says. Thespis owns the minds.

The same scene plays **offline**, through a sidecar the package starts on the player's machine, and **online**,
through a Thespis server. Which one is a setting, not code.

| Path | What it is |
| --- | --- |
| `com.thespis.client/` | The package (UPM): add it to a project |
| `com.thespis.client/Runtime/Core/` | The client in plain C#, with no UnityEngine: `ThespisClient`, `ThespisLine`, `Result<T>`, `Sidecar` |
| `com.thespis.client/Runtime/Core/Api.g.cs` | A typed class per `/v1` schema and the route table, **generated** from [docs/openapi-v1.json](../../docs/openapi-v1.json) |
| `com.thespis.client/Runtime/Unity/` | `ThespisBehaviour` (the scene's client) and `ThespisSettings` (an asset saying where Thespis runs) |
| `com.thespis.client/Editor/` | Imports a `game.toml` as a text asset |
| `Lantern/` | A Unity 6 project with the example: the Lantern, the crypt road's first act in miniature |
| `dotnet/` | The core and the example's game built and played under plain .NET, as CI tests them |
| `test/run.py` | The gate: the example against a sidecar and a server, under .NET and in the editor |

## Install

1. Package Manager → **+** → *Install package from disk*, and pick `com.thespis.client/package.json`. Or add it to
   `Packages/manifest.json` as a git URL with `?path=/sdk/unity/com.thespis.client`. It depends on Unity's Newtonsoft
   JSON package, which Unity installs with it.
2. Put your `game.toml` in `Assets/`. It imports as a text asset.
3. Create → Thespis → Settings, name it `ThespisSettings`, put it in a `Resources` folder, and point its **Game** at
   your `game.toml`.

Needs Unity 6 and a desktop platform: Windows, macOS or Linux. WebGL can't start a sidecar or use `HttpClient`, so the
package excludes it.

## Play

```csharp
using Thespis;
using Thespis.Api;

public class Taproom : MonoBehaviour
{
    ThespisClient thespis;

    async void Start()
    {
        thespis = ThespisBehaviour.Client;
        thespis.LineArrived += Show;     // a line to show now; it may be the template, provisional
        thespis.LineSettled += Show;     // the model's words replaced it (or it was withdrawn)
        var r = await thespis.StartAsync();          // the sidecar or the server the settings say
        if (r.Ok) await thespis.OpenAsync("tavern");
        else Debug.LogWarning($"No Thespis: {r.Reason}");
    }

    public async void InsultGarrick()
    {
        // The engine says what happened and who saw it. The game file says what an insult does to Garrick.
        await thespis.ObserveAsync(ThespisClient.Event("insult", "player", "garrick",
            ThespisClient.Claim("insulted", "player", "garrick"), "wren"));
    }

    public async void AskGarrick()
    {
        var r = await thespis.DecideAsync("garrick", "turn");   // his choice, among his game file's
        if (r.Ok && r.Value.Action == "share_drink:player") PourDrinks();
    }

    void Show(ThespisLine line)
    {
        bubble.text = line.IsWithdrawn ? "" : line.Words("...");  // null Text: the NPC chose silence
        bubble.alpha = line.IsProvisional ? 0.6f : 1f;
    }
}
```

- **Every call returns a `Result<T>`:** `Ok`, then `Value` or `Error`, `Reason` and `Status`. A server that's away
  is a result like any other (`unreachable`), not an exception.
- **Replies are typed:** `DecideAsync` gives a `ThespisLine`, `ObserveAsync` an `EventOut`, `TickAsync` a `TickOut`.
  Options are the generated request classes: `DecideAsync("garrick", "turn", new DecideIn { Wait = true })`.
- **Lines settle by themselves.** A provisional line is the game's own template line, safe to show at once. The client
  follows it by long-polling and updates the same `ThespisLine` in place, then raises `LineSettled` and the line's
  own `Settled`. `await thespis.SettleAsync(line)` waits for it.
- **The main thread.** Awaited from a MonoBehaviour, every continuation and event comes back on Unity's main thread,
  so handlers can touch the scene. The test checks it.
- **Many calls at once:** up to `MaxRequests` (6) in flight, and the rest wait their turn.

## Saves

```csharp
var minds = await thespis.SnapshotAsync();          // Ok with a string: the session as Thespis wrote it
save.minds = minds.Value;                            // keep it as text in your own save
...
await thespis.RestoreAsync("tavern", save.minds);   // sent back exactly as written
```

## Where it runs

| `ThespisSettings` | Default | What it does |
| --- | --- | --- |
| Server | empty | A Thespis server. **Empty: start a sidecar on this machine.** `$THESPIS_URL` overrides it |
| Key | empty | The server's project key (`tsk_...`). `$THESPIS_KEY` overrides it |
| Game | none | The game's `game.toml`, sent on start so the runtime knows the game |
| Sidecar Command | empty | How to run the runtime. Empty: `thespis/thespis(.exe)` beside a build's executable, `python -m thespis` in the editor |
| Sidecar Model | empty | A local model: `auto`, or an id such as `gemma4-e4b`. Empty: the game's template lines. `$THESPIS_MODEL` overrides it |
| Sidecar Online | off | Let the sidecar reach the network, for a cloud model. Off, it refuses every connection off the machine |
| Sidecar Start Timeout | 120 s | How long to wait for it, a local model's first load included |

**Offline (the sidecar).** `StartAsync()` runs `thespis serve --port 0`, reads the address it prints, and gives it a
random token through its environment.
- **When it stops:** the sidecar stops with the game. `ThespisBehaviour` kills it on quit, and `--parent` has the
  runtime watch the game's process in case the game is killed first.
- **Shipping it:** ship the packaged runtime from `python tools/package.py` as `thespis/` beside the build's
  executable.
- **The local model:** it must be on the player's machine before the first offline run (`thespis models pull <id>`).
- **Sessions:** they're kept under `Application.persistentDataPath/thespis/`.

**Online (a server).** Set **Server** and **Key**. `StartAsync()` sends the game, since a server only knows the games
its projects send it. A key in the settings ships inside the build, where players can read it. That's fine for
development, but a public online game should reach Thespis through its own backend.

## The typed layer is generated

`Api.g.cs` is written by [tools/sdk_gen.py](../../tools/sdk_gen.py) (`python tools/sdk_gen.py unity`) from the
committed OpenAPI spec, beside the Godot addon's `api.gd`. The calls you write against are written by hand around it.
CI fails while either is stale.

## Test

```sh
python sdk/unity/test/run.py                                    # .NET: sidecar, then server
python sdk/unity/test/run.py --unity "<Unity 6>/Editor/Unity.exe"   # and the scene, in the editor in batch mode
python sdk/unity/test/run.py --runner unity --unity <...> --mode sidecar --local gemma4-e4b   # offline
```

There are two runners, and both play the same game (`Lantern/Assets/Lantern/LanternGame.cs`):

| Runner | What it runs | Sidecar | Server |
| --- | --- | --- | --- |
| `dotnet` | the core built as Unity builds it (netstandard2.1, C# 9), and the game, under .NET 10 | 19 checks | 17 checks |
| `unity` | the Lantern scene in Unity 6000.6 in batch mode: a play-mode test plays it through `ThespisBehaviour` and reads what the screen shows | 22 checks | 20 checks |

Offline with local Gemma 4 E4B, the `unity` runner passes 22 of 22 through the Python runtime (the model's line
after 1.6 s) and through the packaged one (1.5 s), with the sidecar refusing nothing off the machine
([docs/serve.md](../../docs/serve.md)).

The scene doesn't change between the two Thespis runs.

What the checks cover:
- typed replies;
- a provisional line shown faded, then followed until it settles, and shown final;
- the line events arriving on Unity's main thread;
- a failed call coming back as a result;
- a tick, and a narration;
- eight calls at once;
- a save restored as it was;
- the sidecar refusing nothing off the machine, and stopping with the client.

**CI** runs both on every push:
- **`unity`:** the `dotnet` runner.
- **`unity-editor`:** the `unity` runner. It installs the editor the project names (cached between runs) and signs in
  with a Unity Personal licence. Then it plays the scene and returns the seat when the job ends. Runs queue rather
  than overlap, since a Personal licence has few seats.

The licence comes from two repository secrets, `UNITY_USERNAME` (the Unity ID's email) and `UNITY_PASSWORD`. Without
them, as on a fork's pull request, the job skips. Unity no longer issues `.ulf` licence files for Personal seats, so
the licence is signed in with the account itself. Use an account without two-factor sign-in, ideally one kept for
CI.
