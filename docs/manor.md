# The manor mystery

A second game on the Thespis core (#35), to show the core works for more than one game. The engine side lives in
`games/manor/` and imports nothing from The Crypt Road; the client is the second page of the Vite client
(`client/manor/`, code in `client/src/manor/`), with a pixel-art cutaway of the house, the same inspector, a Watch
autoplay and code-built case notes. Both are served at `/manor/` on the same server.

## The case

Lady Vane's signet ring went missing from the study this morning. The player arrives at noon, so what happened before
lives only in the ledger, written when the game starts:

| Phase | Event | True? |
| --- | --- | --- |
| 0, early morning | Sable takes the ring in the study. No one sees. | ✓ |
| 1, mid-morning | Sable leaves the study. Pell sees her go. | ✓ |
| 1, mid-morning | Sable tells Lady Vane she was in the kitchen. Lady Vane believes her (0.9, from trust 2). | ✗ |
| 2, noon | The player arrives in the hall. | ✓ |

**The people.**

| Character | Room | What they do |
| --- | --- | --- |
| Lady Vane | Hall | Never moves; her beliefs decide the case. Trusts Pell 3, Sable 2 and the player 0. |
| Pell, the butler | Study | Always tells the truth. |
| Sable, the maid | Kitchen | Took the ring, and lies to protect herself once she is frightened. |

## Rules

| Verb | Where | Ends the phase? | What it does |
| --- | --- | --- | --- |
| `move` (target: a room) | anywhere | Yes | Walk to another room |
| `ask` (target, `topic`: `morning` or `ring`) | the person's room | No | Ask someone about this morning or the ring |
| `request_questioning` (target: `pell` or `sable`) | the hall | No | Lady Vane questions them; enabled once you have asked them about the morning |
| `accuse` (target: `pell` or `sable`) | the hall | Ends the game | Won only if Lady Vane believes Sable was in the study at mid-morning (0.5 or more) and has dropped her alibi |

- **Sable lies.** Asked about the morning, her fear rises by 2. At fear 3 or more her allowed actions include
  `deceive:alibi`, which states she was in the kitchen at mid-morning, beside `deflect`. The model chooses and words
  it; without a model the utility brain lies. A lie is logged in the ledger, truth false, and her line cites it.
- **Pell's testimony breaks the alibi.** Questioned by Lady Vane, he says he saw Sable leave the study. Two places for
  one person at one time can't both be true, so Lady Vane drops the claim from the source she trusts less (Sable),
  and her trust in Sable falls by 3.
- **Time runs out.** At evening (phase 7), with the case unsolved, Lady Vane sends for the constable and the game is
  lost.
- **The solve:** go to the kitchen and ask Sable about the morning; go to the study and ask Pell; go back to the hall
  and have Lady Vane question Pell; accuse Sable. Done at late afternoon (phase 5).

## NPC deception, the core feature

The one change the core needed (`thespis/deception.py`). A lie is something the game offers, never something the
model invents:

- `asserting(option, says)` marks an allowed action as stating a claim, under the citable id `said`.
- The validator refuses a line for that action unless it cites `said`, and refuses `said` from any other action.
- `log_statement(...)` writes the statement to the ledger with its real truth, from the ledger itself, and swaps
  `said` in the line's cites for the statement's event id. The decision records the event as `asserted`, so the
  why-chain runs from the line to the statement to what really happened.

Events and decisions without these fields serialise exactly as before, so The Crypt Road is untouched.

## API

All under `/manor`, with the session id in the `X-Session` header. Errors are `{error, reason}` with the status codes of
[api.md](api.md).

| Endpoint | Returns |
| --- | --- |
| `GET /manor/` | The game's page (the built client; a short notice if the client hasn't been built) |
| `POST /manor/session` | `{session, state}` |
| `GET /manor/state` | The state: phase, clock, status, outcome, room, people, beliefs (each with `truth`), ledger (each with `truth` and `text`), decisions (a lie has `asserted`) |
| `GET /manor/allowed` | `{verbs: [{verb, target, label, args, ends_phase, enabled, reason}]}` |
| `POST /manor/act` `{verb, target?, topic?}` | `{events, replies, state}`; `replies` are `{decision, npc, line, cites, source}` |
| `POST /manor/reset` | `{state}` |
| `POST /manor/reload` | `{state}`, rebuilt from disk (the dev panel) |
| `POST /manor/dev/brain` `{mode: "model" or "fallback"}` | `{mode}`: with `fallback`, no model calls |

Manor sessions live in their own database beside The Crypt Road's (`manor.sqlite`). The model, its reply cache and the
call caps are shared, so the manor's calls count against the same global cap.
