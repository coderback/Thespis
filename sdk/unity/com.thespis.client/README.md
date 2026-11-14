# Thespis for Unity

NPC minds through the Thespis `/v1` protocol: what each NPC believes, what it chooses among the actions your game
file declares, and its words. Offline through a sidecar on the player's machine, or online through a Thespis
server. MIT licensed (LICENSE.md).

- **Guide:** <https://github.com/coderback/Thespis/blob/main/sdk/unity/README.md>
- **The game file and every call:** <https://github.com/coderback/Thespis/blob/main/docs/protocol.md>
- **The runtime to ship beside your game:** a zip for your platform from
  <https://github.com/coderback/Thespis/releases>, unzipped as `thespis/` beside the build's executable.

## Calls

Every call on `ThespisClient` (`ThespisBehaviour.Client` in a scene) returns a `Result<T>` (`Ok`, `Value`, `Reason`).

| Call | What it does |
| --- | --- |
| `StartAsync()`, `StopAsync()` | Reach the runtime (a sidecar it starts, or the server the settings name), and stop it |
| `OpenAsync`, `RestoreAsync`, `SnapshotAsync`, `CloseAsync` | A session: start one, load a save, save, end it |
| `ObserveAsync`, `UpdateAsync`, `TickAsync` | What happened, what the engine changed, the minds' own time |
| `DecideAsync`, `ReactAsync`, `NarrateAsync` | What an NPC does and says |
| `UnderstandAsync` | What the player's words do, among the game's intents |
| `JoinAsync`, `AddAsync`, `RetireAsync`, `TieAsync`, `UntieAsync` | The cast in play |
| `InspectAsync`, `TraceAsync`, `EventsAsync` | Look inside: beliefs, a story on the grapevine, the ledger |

`RuntimeVersion` is the runtime's version once `StartAsync` reaches it. A runtime older than this package needs
(`MinRuntime`) raises `Warned` (logged by `ThespisBehaviour`), since some calls will fail on it.
