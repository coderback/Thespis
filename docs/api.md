# API contract: engine to client

The engine owns all game logic; the client sends verbs, renders state and animates moves.
The session id lives in the URL (`?s=`), so a reload resumes the run, and every request sends it as the
`X-Session` header.

Changing anything here? Update `fixtures/` in the same PR and get the other person's review.

## Endpoints

| Endpoint | Returns | Notes |
| --- | --- | --- |
| `POST /session` `{seed?}` | `{session, state}` | Default seed is the demo seed |
| `GET /state` | Full snapshot (shape below) | NPCs carry `last_seen`; beliefs carry an `evidence` list |
| `GET /allowed` | `{verbs: [{verb, target, label, args, ends_phase, enabled, reason}]}` | Disabled verbs come with a reason for the tooltip. After a duel win, only `humiliate` and `spare` are enabled |
| `POST /act` `{verb, target?, claim?, amount?, text?}` | `{events, replies, tick, epilogue, state}` | See [Acting](#acting) |
| `GET /digest?since=<phase>` | `{text, hook, cites, epilogue}` | Fetch while moves animate. `epilogue` is `null` until the race ends |
| `POST /reset` | `{state}` | Wipes this session, keeps the seed |
| `POST /reload` | `{state}` | Rebuilds this session from disk (dev panel) |
| `POST /dev/brain` `{mode: "model" or "fallback"}` | `{mode}` | The "brain off" toggle |
| `GET /health` | `{ok: true}` | For the host |

Errors: a malformed body returns `400`, and a verb that `/allowed` lists as disabled (or doesn't list) returns `409`.
A hit rate limit returns `429`. All three carry `{error, reason}`, with `reason` readable by a player.

## Verbs

Only verbs whose target shares the player's stop are listed. A verb with no target is always listed.

| Verb | Target | Ends phase? | Request fields | `args` in `/allowed` |
| --- | --- | --- | --- | --- |
| `talk` | NPC at your stop | No | `text`, 1 to 200 characters | `{max_len: 200}` |
| `insult` | NPC at your stop | No | | `{}` |
| `challenge` | `kael` | Yes, unless you win; see below | | `{}` |
| `humiliate` | `kael` | Yes | | `{}` |
| `spare` | `kael` | Yes | | `{}` |
| `tell_claim` | NPC at your stop | No | `claim` | `{preds: [...], subjects: [...]}`: the claim builder's options |
| `bribe` | `brenna` | No | `amount` | `{amount: 20}` (fixed for now) |
| `move` | none | Yes | | `{to: "<next stop>"}` |
| `wait` | none | Yes | | `{}` |
| `take_relic` | none | Ends the race | | `{}` |

`label` is the button text, for example `"Insult Kael"` or `"Bribe Brenna (20)"`.

**Duels.** A lost `challenge` ends the phase as usual. A won `challenge` does not end it: the response has
`tick: null` and `state.pending: "duel_won"`, and until the player picks `humiliate` or `spare` every other verb is
disabled with the reason `"Choose: humiliate or spare"`. The pick ends the phase.

**The gate.** While Brenna's trust in the player is below 0, `move` at the guard post is disabled with a reason such as
`"Blocked: Brenna's trust in you is -2"`.

## Acting

`POST /act` returns:

- `events`: the ledger events this request wrote, in order (the free action's events, then the tick's).
- `replies`: lines spoken to the player, as `[{decision, npc, line, cites, source}]`. This covers reactions to the
  verb and lines that fire when the new phase starts (an NPC greeting the player on arrival). `decision` is the id of
  the record that holds the line, so the client can open its why-chain. Lines from decisions made inside the tick are
  in `tick.decisions` instead.
- `tick`: `{moves, decisions, events}` for a phase-ending verb, or `null` for a free action. `moves` is
  `[{who, from, to}]` and includes the player. It has no digest: fetch `GET /digest` while the moves animate.
- `epilogue`: `null`, except on the request that ends the race. See [The race end](#the-race-end).
- `state`: the full snapshot after everything above.

## Shapes

Claims are `{pred, a, b}` with `pred` one of `robbed`, `beat`, `insulted`, `spared`, `lied`, and `a` and `b` each one of
`player`, `kael`, `brenna`, `odo`, `mags`.

`state` at phase 3 of the demo route (player and Kael at the guard post, Odo back at the market), trimmed to one NPC and
one belief:

```json
{
  "seed": 1, "phase": 3, "day": 1, "phase_name": "night", "status": "playing", "brain": "model",
  "pending": null, "ended_at": null,
  "player": { "loc": "guard_post", "coins": 40 },
  "npcs": [
    { "id": "kael", "loc": "guard_post", "last_seen": { "loc": "guard_post", "phase": 3 },
      "drives": { "grudge": 6, "fear": 1, "respect": 0, "ambition": 6 },
      "trust_in": {}, "frozen_until": null }
  ],
  "beliefs": [
    { "id": "b0010", "npc": "brenna", "claim": { "pred": "robbed", "a": "player", "b": "kael" },
      "conf": 0.9, "status": "active", "truth": true,
      "evidence": [ { "source": "kael", "event": "e0011", "phase": 2, "conf": 0.9 } ] }
  ],
  "ledger_tail": [], "decisions_tail": []
}
```

- `last_seen` is computed by the engine: the stop and phase where the player last shared a stop with that NPC. It
  equals the NPC's current stop while they are together, and is `null` if the player has never seen them (Brenna, until
  the guard post).
- `frozen_until` is the last phase an NPC is detained (inclusive), or `null`.
- `conf` is the highest confidence among the belief's `evidence`. `status` is `active` or `retracted`. `truth` says
  whether the claim happened, and is for the inspector only: it never reaches the model.
- `ledger_tail` and `decisions_tail` hold the last 50 of each, which covers a whole demo run.

A ledger event:

```json
{ "id": "e0011", "phase": 2, "verb": "accuse", "actor": "kael", "target": "brenna", "loc": "guard_post",
  "claim": { "pred": "robbed", "a": "player", "b": "kael" }, "truth": true, "schema_version": 1 }
```

`loc` is the stop where the event happened; for a `move` it is the stop left, and `target` is the stop reached.
`claim` is `null` for events that carry none, such as `move`. For an event
that carries a claim, `truth` says whether that claim happened, so a lie told as `tell_claim` has `truth: false`.

A decision record. Every spoken line has one: `kind` is `decide` when the NPC chose an action, or `react` for a line
alone (then `allowed` is empty and `chosen` is `null`):

```json
{
  "id": "d0009", "kind": "decide", "npc": "brenna", "phase": 3, "trigger": "arrival",
  "allowed": ["wait"], "chosen": "wait",
  "line": "Kael says you cut his purse in the tavern. You're not crossing.",
  "cites": ["b0010", "e0011"], "reason": "trust in player -2", "source": "llm"
}
```

`status` is `playing`, `won` or `lost`. `source` is `llm`, `cache` or `fallback`.

Example ids are illustrative: they follow the ledger policy below, but the client must never hard-code one. A line may
only cite ids from its speaker's state pack, so Brenna cites the accusation she heard (`e0011`), not the humiliation
she didn't see (`e0004`). The why-chain reaches the humiliation through the belief's `truth`.

## The ledger

The ledger holds what happened in the world: things someone could witness or be told about. Each event gets the next
id in its session (`e0001`, `e0002`, ...).

- **Written:** `insult`, `challenge`, `beat`, `humiliate`, `spare`, `tell_claim`, `bribe`, `move` (player and NPCs,
  one per stop moved), `block`, `accuse`, `detain`, `release`, `gossip`, `testify`, `take_relic`.
- **Not written:** `talk` and `wait` (they change nothing), and decisions, which are their own records (`d0001`, ...).
  Beliefs are records too (`b0001`, ...).

Duel dice are `hash(seed, "challenge:<n>")`, where `n` counts the session's challenges from 1. They never depend on an
event id, so adding event types can't change who wins a duel.

## The race end

The race ends when the player uses `take_relic` (`won`) or Kael takes the relic at the end of a tick (`lost`). The
engine then runs two more phases with the player idle, so the world visibly carries on: in the demo route, Odo testifies
at phase 6 and Brenna retracts the lie.

- The request that ends the race returns `epilogue: [tick, tick]`, one entry per extra phase, in the same shape as
  `tick`.
- `state.status` is final (`won` or `lost`), `state.ended_at` is the phase the race ended, and `state.phase` is the
  phase after the epilogue.
- `GET /digest?since=<ended_at>` returns the epilogue text in `epilogue`. The client shows the win or lose card, plays
  the epilogue ticks, then shows that text.
- After the race ends, `/allowed` lists only disabled verbs, and `POST /reset` starts again.

## Fog of war is the client's job

`state` always contains every NPC's true position, because the inspector shows everything. The map hides
NPCs away from the player's stop and draws `last_seen` ghosts instead.

## Stops and phases

Stops: `tavern`, `market`, `guard_post`, `bridge`, `crypt`. Phases: `morning`, `noon`, `evening`, `night`;
`day = phase // 4 + 1`.
