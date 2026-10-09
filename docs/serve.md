# Running Thespis: sidecar and server

`thespis serve` runs the `/v1` protocol ([protocol.md](protocol.md)) two ways, from one command and one codebase:

| | Sidecar | Server |
| --- | --- | --- |
| For | A game that ships Thespis beside it (Godot, Unity) | Online play and development: self-hosted, or hosted |
| Started by | The game's SDK, and stopped with it | You, once |
| Listens on | This machine only | Wherever you tell it |
| Projects | One, `local` | Many, each calling with its own key |
| Sessions kept in | A SQLite file | Postgres (or SQLite, for a small one) |
| Models | The ones it's started with: a local model (`--local`) or `LLM_*` | Each project's own keys, sealed at rest; the server's `LLM_*` for projects without |
| Network | Off, unless `--online` | On |

A session is saved before every call answers, and again when a provisional line settles. A sidecar or server that
restarts picks every session up where it was.

## The sidecar

```bash
thespis serve --game game.toml --port 0 --db saves/thespis.sqlite --parent <the game's pid> --local auto
```

- It prints `THESPIS_URL=http://127.0.0.1:<port>` on its first line once it listens, so a launcher can ask for port
  0. It waits until the local model is up before printing that.
- `--parent` ties its life to the game's. It stops when that process ends, however it ends, even if it's killed. The
  local model's server is tied to the sidecar in turn ([models.md](models.md#local-models-playing-offline)).
- If `THESPIS_TOKEN` is set when it starts, every call must send `Authorization: Bearer <token>`. That keeps other
  programs on the machine out. A launcher makes one up per start.
- `--db` is where sessions are kept: a SQLite file (the runtime's cache folder if left out), or `:memory:` for none.
- A game can send its definition instead of a path: `PUT /v1/games/{id}` with `{"toml": "..."}`.
- `--embed local` also starts the embedding model for memory by meaning (BGE small, on the CPU), for games that
  declare `[memory]`. `EMBED_*` points at any other.

**Offline is enforced, not assumed.** A sidecar refuses, inside its own process, every name lookup and connection
that isn't to this machine ([thespis/offline.py](../thespis/offline.py)):
- A cloud model configured by mistake fails at once, and its lines fall back to templates.
- A model that hasn't been downloaded says so, rather than fetching it.
- `GET /v1/health` reports `{"offline": true, "refused": n}`, so a game, or a test, can check that nothing tried to
  leave.

`--online` lifts all of it.

### Shipped as one archive

`python tools/package.py` builds `dist/thespis-<os>-<arch>.zip`: one folder, holding one executable, that needs no
Python. It also checks the build against its budgets and plays a turn through it. CI builds and checks it on Windows,
macOS and Linux.

| | Budget | Windows, CI | macOS, CI | Linux, CI | Windows, a Ryzen 7 5800H laptop |
| --- | --- | --- | --- | --- | --- |
| Archive | 25 MB | 17.4 MB | 21.5 MB | 17.8 MB | 20.1 MB |
| Cold start, launch to `/v1/health` answering | 4 s | 1.02 s | 1.48 s | 0.43 s | 1.73 s |

Cold start is the median of three starts after a first. Linux builds are stripped of their debug symbols: unstripped,
the archive was 38.3 MB.

**Why a folder, not a single file.** PyInstaller's one-file build was measured and turned down for two reasons:
- **It's slower to start.** It unpacks itself on every start, which took cold start from 2.1 s to 4.7 s.
- **Stopping it can leave Thespis running.** It runs as a launcher with a child process. Killing the launcher, which
  is what a game does to stop its sidecar, left the child running: seven were found after the measurements.

The one-folder build starts as fast as Python does, and it is a single process.

It leaves out what only a server needs: Postgres, the vault and the OpenTelemetry SDK.

## The server

```bash
export THESPIS_SECRET_KEY=$(thespis projects secret | cut -d= -f2)   # once; keep it with your other secrets
thespis serve --server --host 0.0.0.0 --port 8000 --db postgresql://... --game game.toml
thespis projects create my-studio --calls-per-day 20000              # prints the project's key, once
```

Or as an image: `docker build -f docker/serve.Dockerfile .`, run with `DATABASE_URL` and `THESPIS_SECRET_KEY`. CI
runs that image beside Postgres and checks three things: it wants a key, it keeps sessions across a restart, and it
doesn't run as root.

### Projects and keys

Every call except `/v1/health` sends the project's key: `Authorization: Bearer tsk_...`. The key is stored only as
a hash.
- `thespis projects key NAME` replaces a key. The old one stops working within 5 seconds.
- A project sees only its own sessions and games. Another project's session id answers 404, as if it didn't exist.

| Command | What it does |
| --- | --- |
| `thespis projects create NAME [--max-sessions N] [--calls-per-day N] [--tokens-per-day N] [--max-games N]` | A new project, and its key, shown once |
| `thespis projects list` | Every project: open sessions, today's calls and tokens, caps |
| `thespis projects caps NAME --calls-per-day N ...` | Change its caps |
| `thespis projects model NAME --profile openai --model gpt-4.1-mini --key-env OPENAI_KEY` | Set its models; the key is read from that variable, never from the command line |
| `thespis projects secret` | A new `THESPIS_SECRET_KEY` |
| `thespis usage NAME [--since 2026-10-01] [--format csv \| json] [--out file]` | Its usage events |

They work on the server's database directly: `--db`, or `$DATABASE_URL`.

### Bring your own model keys

A project sets its own models over the API, primary and optional backup, with any profile from
[models.md](models.md):

```http
PUT /v1/project/model
{"primary": {"profile": "anthropic", "model": "claude-haiku-5-5", "api_key": "sk-ant-..."}}
```

**Sealed at rest.** The settings are sealed with AES-256-GCM under `THESPIS_SECRET_KEY`, with the project's id bound
in, so a sealed copy won't open in another project's row ([thespis/vault.py](../thespis/vault.py)). The key is never
sent back: `GET /v1/project` shows the settings with `api_key_set: true`. A server without `THESPIS_SECRET_KEY`
refuses model keys.

**Public endpoints only.** A server only calls model endpoints on the public internet, over HTTPS. That stops a
project's settings turning the server into a way into the network it runs on. A server beside its own vLLM starts
with `--allow-private-models`. The address is checked when the settings are saved. A name that later resolves
somewhere private isn't caught; a firewall on the server's outbound traffic is the complete answer.

### Caps and usage

**Caps.** Each project has:
- `max_sessions` open at once (503 `full` when reached);
- `calls_per_day` and `tokens_per_day`, by UTC day;
- `max_games` of its own.

A project over a daily cap still plays: its NPCs speak their template lines until the next UTC day. Cache hits cost
nothing and count against nothing. Replies are cached per project, so a moment played twice costs one call.

**Usage.** Usage is kept as events, the groundwork for metering:
- `call`: one model call, with its call type, provider, latency and tokens;
- `line`: one line settled, with `source` llm, cache or fallback, so cache hits are counted;
- `capped`: a call a cap refused, and which cap.

`GET /v1/usage?since=<unix time>&format=csv` exports a project's own; `thespis usage` exports any project's. There
is no billing: pricing waits on the licence decision.

### Traces

Set `OTEL_EXPORTER_OTLP_ENDPOINT`, with the `thespis[otel]` extra installed, and the server sends OpenTelemetry
traces over OTLP/HTTP. Each request is one trace, with spans for:
- the request;
- the Mind's work on each line (`thespis.mind.act`, `.react`, `.narrate`), with where its words came from;
- each model call (`thespis.model`: provider, model, tokens, ok or the error);
- each claim check (`thespis.check`).

A provisional line's model call runs after its request has answered, and its spans still join that request's trace.
The standard `OTEL_*` variables apply.

### More than one instance

Several instances can share one database. Each checks a session's stored version before every call, and reloads it if
another instance moved it on. A save that finds the version moved is refused (409 `conflict`; call again) rather
than overwriting newer state.

**Lines still on their way live in the instance that started them.** Ask that same instance for them, or the line's
id answers 404 and the engine shows the template line it already has. Route each session to one instance:
- sticky sessions on the load balancer;
- or one instance per region.

## The gates (Phase 4.4)

### Load: 200 engines at once on one server process

`python tools/loadtest.py` runs `thespis serve --server` with a scripted model that answers in 400 ms, and plays the
tavern from many engines at once. Each engine:
1. opens a session;
2. reports an insult and moves a drive;
3. asks Garrick to decide, and long-polls his line until it's final;
4. asks Wren to react;
5. ticks, asks for the narration, saves, and closes.

Each engine waits 1 to 3 s between calls, as a player takes their turn. The gate: no errors, and the engine's calls
(all but the long poll, which waits for the model by design) answer within 250 ms at the 95th percentile.

| Run | Requests | Errors | Engine calls p50 / p95 / p99 | Line, asked to final, p50 / p95 |
| --- | --- | --- | --- | --- |
| [200 engines, Postgres](../tools/reports/load-200-postgres.md) | 6000 at 91/s | 0 | 19 / **50** / 91 ms | 439 / 518 ms |
| [200 engines, SQLite](../tools/reports/load-200-sqlite.md) | 6000 at 94/s | 0 | 13 / **31** / 49 ms | 425 / 502 ms |
| [Capacity: 50 engines calling flat out, Postgres](../tools/reports/load-saturation-postgres.md) | 1500 at 183/s | 0 | 111 / 281 / 340 ms | |

**Capacity.** One server process takes about 190 requests a second, model calls included. Past that, calls queue.
Two changes found by this test raised it:
- **Long polls no longer hold a thread.** A long poll now waits on the line's model call without holding a thread.
  Before, every waiting engine held one of FastAPI's 40 worker threads for up to 2 s.
- **A plain ASGI middleware for traces.** Starlette's `BaseHTTPMiddleware` added a task and a stream to every request.

The earliest runs also measured the load generator rather than the server: one Python client process tops out near
60 requests a second. The engines now run in four client processes.

These numbers are for a Ryzen 7 5800H laptop, with the server, Postgres, the model and the engines all on it. CI
runs the same test at 100 engines on every push. On a Linux runner: 2000 requests, 0 errors, engine calls p95 8 ms.

### Offline: the reference scene with the network refused

The Godot addon's example scene ([sdk/godot](../sdk/godot/README.md)) runs headless, with the addon starting the
sidecar itself, as a shipped game would. It must pass all 21 checks with the sidecar refusing nothing:

```bash
python sdk/godot/test/run.py --godot <Godot console build> --mode sidecar [--local gemma4-e4b] [--exe dist/thespis/thespis.exe]
```

| Sidecar | Model | Checks | Off-machine connections refused |
| --- | --- | --- | --- |
| `python -m thespis serve` | scripted, on localhost | 21 of 21 | 0 |
| The packaged runtime (`dist/thespis/thespis.exe`) | scripted, on localhost | 21 of 21 | 0 |
| `python -m thespis serve --local gemma4-e4b` | Gemma 4 E4B on the laptop's GPU | 21 of 21 (the model's line after 1.5 s) | 0 |
| The packaged runtime, `--local gemma4-e4b` | Gemma 4 E4B on the laptop's GPU | 21 of 21 (the model's line after 1.25 s) | 0 |

The same scene also plays through a hosted-mode server with a project key, unchanged (19 checks: the sidecar's two
don't apply), and CI plays both on Linux on every push. After each run, nothing is left running: no runtime and no
llama-server.

The Unity package's Lantern scene ([sdk/unity](../sdk/unity/README.md)) passes the same gate in the editor, in batch
mode, with the package starting the sidecar. It has 22 checks, the extra one confirming that line events come on
Unity's main thread:

```bash
python sdk/unity/test/run.py --runner unity --unity <Unity.exe> --mode sidecar --local gemma4-e4b [--exe dist/thespis/thespis.exe]
```

| Sidecar | Model | Checks | Off-machine connections refused |
| --- | --- | --- | --- |
| `python -m thespis serve --local gemma4-e4b` | Gemma 4 E4B on the laptop's GPU | 22 of 22 (the model's line after 1.6 s) | 0 |
| The packaged runtime, `--local gemma4-e4b` | Gemma 4 E4B on the laptop's GPU | 22 of 22 (the model's line after 1.5 s) | 0 |

With a scripted model, CI plays the scene in the editor on every push (`unity-editor`), against a sidecar and a
server.

The template line shows in under 30 ms either way, and the model's words replace it when they come.

## Not yet

- **Billing.** Usage events are kept, but nothing prices them.
- **Changing `THESPIS_SECRET_KEY`.** The projects' model settings would need sealing again under the new key. Today
  they set them again.
- **Old usage events.** Nothing removes them yet. Export them, then prune the `usage` table.
- **Streaming.** Lines are long-polled; server-sent events wait until an engine needs them
  ([protocol.md](protocol.md#not-yet)).
