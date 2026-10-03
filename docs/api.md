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
| `GET /allowed` | `{verbs: [{verb, target, args, ends_phase, enabled, reason}]}` | Disabled verbs come with a reason for the tooltip. After a duel win, only `humiliate` and `spare` are enabled |
| `POST /act` `{verb, target?, claim?, amount?}` | `{events, replies, tick, state}` | Replies carry `cites` and `source`. `tick` is `{moves, decisions, events}` or `null` for free actions; it has no digest |
| `GET /digest?since=<phase>` | `{text, hook, cites}` | Fetch while moves animate. After a win it also returns the epilogue |
| `POST /reset` | `{state}` | Wipes this session, keeps the seed |
| `POST /reload` | `{state}` | Rebuilds this session from disk (dev panel) |
| `POST /dev/brain` `{mode: "model" or "fallback"}` | `{mode}` | The "brain off" toggle |
| `GET /health` | `{ok: true}` | For the host |

## Shapes

Claims are `{pred, a, b}` with `pred` one of `robbed`, `beat`, `insulted`, `spared`, `lied`.

`state` (trimmed):

```json
{
  "phase": 3, "day": 1, "phase_name": "night", "status": "playing", "brain": "model",
  "player": { "loc": "guard_post", "coins": 40 },
  "npcs": [
    { "id": "kael", "loc": "guard_post", "last_seen": { "loc": "tavern", "phase": 0 },
      "drives": { "grudge": 6, "fear": 2, "respect": 0, "ambition": 6 },
      "trust_in": {}, "frozen_until": null }
  ],
  "beliefs": [
    { "id": "b0012", "npc": "brenna", "claim": { "pred": "robbed", "a": "player", "b": "kael" },
      "conf": 0.9, "status": "active", "truth": true,
      "evidence": [ { "source": "kael", "event": "e0009", "phase": 2, "conf": 0.9 } ] }
  ],
  "ledger_tail": [], "decisions_tail": []
}
```

A decision record:

```json
{
  "id": "d0012", "npc": "brenna", "phase": 3, "trigger": "arrival",
  "allowed": ["wait"], "chosen": "wait",
  "line": "Kael says you cut his purse in the tavern. You're not crossing.",
  "cites": ["b0012", "e0004"], "reason": "trust in player -2", "source": "llm"
}
```

`status` is `playing`, `won` or `lost`. `source` is `llm`, `cache` or `fallback`.

## Fog of war is the client's job

`state` always contains every NPC's true position, because the inspector shows everything. The map hides
NPCs away from the player's stop and draws `last_seen` ghosts instead.

## Stops and phases

Stops: `tavern`, `market`, `guard_post`, `bridge`, `crypt`. Phases: `morning`, `noon`, `evening`, `night`;
`day = phase // 4 + 1`.
