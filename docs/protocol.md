# The Thespis protocol (v1)

How a game whose world lives in an engine (Godot, Unity, a web or desktop game) gives its NPCs Thespis minds. The
engine owns the world; Thespis owns the minds. The engine reports what happened and who saw it, and asks what an NPC
does and says. Thespis remembers, believes, gossips, chooses among the actions the game declares, and speaks only
from what each NPC knows.

There's one set of calls, made in one of two ways:

| Runtime | For | How |
| --- | --- | --- |
| Library | Python games | `from thespis.api import Game, Session` |
| `/v1` HTTP | Any engine | `thespis serve --game game.toml`, a sidecar beside the game, or `thespis serve --server`, many projects each with its key ([serve.md](serve.md)). Needs `pip install thespis[serve]`, or `thespis[server]` for a server |

The two make the same calls with the same results; a test plays one scene both ways and compares them.
[openapi-v1.json](openapi-v1.json) is the HTTP contract, generated from the server and committed. A test fails when
the two drift, so a change to `/v1` shows up as a diff to review.

## The game definition

A game is one TOML file. [examples/tavern/game.toml](../examples/tavern/game.toml) is a complete one: a tavern, three
NPCs, one choice set, gossip and words. Everything in it is checked when it loads, and a mistake names its entry
(`npc.garrick.choices.turn[2].when[1]: unknown key most`).

| Table | What it holds |
| --- | --- |
| `[game]` | `id`, `name`, and the `setting` every NPC's model reads |
| `[places]` | Place ids and their names |
| `[player]` | `start`: where the player begins |
| `[npc.<id>]` | `name`, `persona`, `goal`, `start`, and optionally `drives` (0 to 10), `trust_in` (-5 to 5), `walk` (a place per tick), `settle` (drives that drift back to a resting value), `aliases` |
| `[npc.<id>.lines]` | Template lines by key: an action's kind for `decide`, a trigger for `react`. `{who}` and bindings fill them |
| `[[npc.<id>.choices.<moment>]]` | What the NPC may do at that moment (below) |
| `[gossip]` | `gossips`, `about`, `priority` by predicate, `threshold`, `decay` |
| `[words.claims]`, `[words.events]` | A claim and an event in words, as the model reads them |
| `[actions]` | What each action does, by kind, for the model |
| `[situations]` | The situation a moment or trigger is spoken in, if the caller doesn't say |
| `[narrator]` | `name` and `persona`, for `narrate` with a model |

### Choices

Each choice names an action (`do`), when it's open (`when`: every condition must hold) and what it's worth
(`utility`: a sum of terms). The highest utility wins; the first listed wins a tie. The evaluator never calls
`eval`, so a definition is safe to load from anywhere.

```toml
[[npc.garrick.choices.turn]]
do = "confront:player"
utility = [{ drive = "grudge", plus = 3 }]
when = [{ with = "player" }, { drive = "grudge", gte = 4 },
        { believes = { pred = "insulted", a = "player", b = "self" } }]
```

| Condition | Holds when |
| --- | --- |
| `{ drive = d, gte = n }` (or `gt`, `lte`, `lt`, `eq`) | The drive compares so; a drive the NPC lacks is 0 |
| `{ at = place }` | The NPC is there |
| `{ with = who }` | The NPC shares a place with `who`; `"player"` is where the player is |
| `{ flag = f }`, `{ not_flag = f }` | The NPC's flag is set, or isn't |
| `{ believes = claim, min = c }` | The NPC holds the claim actively, with at least `min` confidence if given; `"self"` is the NPC |
| `{ bound = name }` | A value the caller bound is truthy |
| `{ any = [...] }`, `{ all = [...] }`, `{ not = {...} }` | As named |

A utility term is a number, or `{ drive = d, weight = 1, plus = 0, if = {...} }`. Whole numbers stay whole, so a
decision's reason reads `confront:player scores 7`. An action may name values the caller binds when it asks
(`do = "detain:{culprit}"`), and may state a claim (`asserts = { pred = "was_in", a = "self", place = "kitchen", at = 1 }`):
the statement is logged with its real truth, and the listener `to` believes it as far as it trusts the speaker.

The Crypt Road and the manor declare their NPCs' choices this way too (`games/*/cast.toml`). Kael's race, Brenna's
arrests and haggling, and Sable's lie play all 35 routes exactly as they did in code (`tests/test_outcomes.py`).

## The calls

| Library (`Session`) | HTTP | What it does |
| --- | --- | --- |
| `Session.new(game, seed)` | `POST /v1/sessions {game, seed}` | A new playthrough |
| `observe(verb, actor, target, at, claim, witnesses, said, true, amount)` | `POST .../observe` | Something happened. `witnesses` saw it. A deed's claim is believed for certain by whoever saw it or took part in it. A statement (`said`) is believed by whoever heard it, as far as each trusts the speaker. Its truth is the ledger's unless `true` says |
| `update(npc, loc, drives, nudge, flags, trust_in)` | `POST .../update` | The engine's rules changed an NPC (or, with `"player"`, moved the player) |
| `decide(npc, moment, bindings, situation, to, wait)` | `POST .../decide` | The NPC chooses among its declared choices, with the reason recorded, and says its line |
| `react(npc, trigger, situation, cites, fill, wait)` | `POST .../react` | A line in reply to something |
| `narrate(since, wait)` | `POST .../narrate` | The story since a phase, citing every event it tells |
| `tick(steps)` | `POST .../tick` | The minds' own time: scheduled walks, gossip, drives settling, the next phase |
| `line(id, wait)` | `GET .../lines/{id}?wait=2` | A line as it stands now; `wait` holds the request up to that many seconds for the model |
| `inspect(npc)` | `GET .../npcs/{npc}` | The NPC's state and every belief, with its evidence |
| `snapshot()` | `GET .../snapshot` | The minds, for the engine's save file |
| `Session.restore(game, snapshot)` | `POST /v1/sessions {game, snapshot}` | A playthrough from a save |
| `close()` | `DELETE /v1/sessions/{id}` | Stop; withdraw lines still on their way |

### Lines

Every call that speaks returns its line at once:

| `status` | Means | The engine |
| --- | --- | --- |
| `provisional` | The template line; the model's line is on its way | Shows it, and polls `line(id)` |
| `final` | Settled: the model's words, or the template's when there's no model or its reply failed a check | Shows it |
| `withdrawn` | The session closed before the model answered | Drops it |

With no model configured, or with `wait`, a line is final at once (the library waits by default; HTTP doesn't).
A line needs something to cite: an NPC that knows nothing yet says nothing (`text: null`), and no model is asked,
since its reply could only be rejected.

### Saves

`snapshot()` is plain JSON: the world, every belief and its evidence, the ledger, the decisions, and who witnessed
what. Restoring it gives the same minds, which go on to play the same: a test plays a scene on from both copies and
compares them. A snapshot of another game, or from a newer Thespis, is refused. Store it as the text you were sent:
an engine with one number type (GDScript reads every JSON number as a float) can still hand it back parsed, and it
restores the same, but there's no reason to unpack it.

### Errors

HTTP errors carry `{error, reason}`:

| Status | Error | Cause |
| --- | --- | --- |
| 400 | `bad_request` or `bad_definition` | A malformed body, or a snapshot of another game or version |
| 401 | `unauthorized` | No key, or the wrong one: a server wants the project's, a sidecar its token if it has one |
| 404 | `unknown` | An unknown game, session, NPC, choice set or line, or another project's session |
| 409 | `not_allowed` or `conflict` | A call the game doesn't allow now, or a session another instance moved on (call again) |
| 413 | `too_large` | A game definition over 256 KB |
| 429 | `over_cap` | A project at its limit of games |
| 503 | `full` | The project holds its limit of sessions |

Over a daily model cap a project isn't refused: its lines come from templates until the next UTC day
([serve.md](serve.md#caps-and-usage)).

### Projects

| Route | What it does |
| --- | --- |
| `PUT /v1/games/{id}` / `DELETE` | Send a game definition (`{"toml": "..."}`): the project's own, shadowing the host's of the same id |
| `GET /v1/project` | Its caps, today's calls and tokens, open sessions, and its model settings with the keys left out |
| `PUT /v1/project/model` / `DELETE` | Its own models and keys, sealed at rest (a server only) |
| `GET /v1/usage?since=&format=csv` | Its usage events: model calls, lines settled and where from, calls a cap refused |
| `GET /v1/health` | Up, and whether it's offline: `{"ok", "offline", "refused"}` |

## Not yet

These are still to come in Phase 4:

- Lines are polled. The Godot spike (4.1b) found long-polling (`?wait=2`) natural in GDScript, where server-sent events
  would mean driving `HTTPClient` by hand, so SSE waits until an engine needs it ([sdk/godot/spike](../sdk/godot/spike/README.md)).
- Multi-speaker narration, many players, relationship ties and retrieval by meaning (4.5).
