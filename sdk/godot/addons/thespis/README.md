# Thespis for Godot 4

NPC minds through the Thespis `/v1` protocol: what each NPC believes, what it chooses among the actions your game
file declares, and its words. Offline through a sidecar on the player's machine, or online through a Thespis
server. MIT licensed (LICENSE.md).

- **Guide:** <https://github.com/coderback/Thespis/blob/main/sdk/godot/README.md>
- **The game file and every call:** <https://github.com/coderback/Thespis/blob/main/docs/protocol.md>
- **The runtime to ship beside your game:** a zip for your platform from
  <https://github.com/coderback/Thespis/releases>, unzipped as `thespis/` beside the executable.

## Calls

Every call is a coroutine on the `Thespis` autoload that returns a `ThespisResult` (`ok`, `value`, `reason`).

| Call | What it does |
| --- | --- |
| `start()`, `stop()` | Reach the runtime (a sidecar it starts, or the server the settings name), and stop it |
| `open(game)`, `restore(game, saved)`, `snapshot()`, `close()` | A session: start one, load a save, save, end it |
| `observe(what)`, `update(npc, change)`, `tick(steps)` | What happened, what the engine changed, the minds' own time |
| `decide(npc, moment, options)`, `react(npc, trigger, options)`, `narrate(options)` | What an NPC does and says |
| `understand(text, to, options)` | What the player's words do, among the game's intents |
| `join(player, ...)`, `add_npc(id, kind, name, at)`, `retire(npc)`, `tie(a, b, kind)`, `untie(a, b)` | The cast in play |
| `inspect(npc)`, `trace(claim)`, `events(after, verb)` | Look inside: beliefs, a story on the grapevine, the ledger |

`runtime_version` is the runtime's version once `start()` reaches it. A runtime older than this addon needs
(`MIN_RUNTIME`) gives a warning (`warned`), since some calls will fail on it.
