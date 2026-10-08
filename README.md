# Thespis

[![CI](https://github.com/coderback/Thespis/actions/workflows/ci.yml/badge.svg)](https://github.com/coderback/Thespis/actions/workflows/ci.yml)
[![Play the demo](https://img.shields.io/badge/demo-play%20live-f0a03a)](https://thespis-production.up.railway.app)
[![Play the manor mystery](https://img.shields.io/badge/second%20game-manor%20mystery-8e6c3a)](https://thespis-production.up.railway.app/manor/)
[![Watch the video](https://img.shields.io/badge/video-2%20min-red?logo=youtube&logoColor=white)](https://youtu.be/WD7oslaKQO4)
[![MIT licence](https://img.shields.io/badge/licence-MIT-blue)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776ab?logo=python&logoColor=white)](pyproject.toml)
[![Cambridge x Arcade AI Hackathon 2026](https://img.shields.io/badge/Cambridge%20%C3%97%20Arcade%20AI-Hackathon%202026-6c5ce7)](#team)

An AI toolkit for game developers. Its first module, **Thespis Cast**, gives NPCs minds of their own: they remember
what happened, believe things that may be false, want things for reasons, and keep acting when the player isn't
looking.

The game owns the truth. Every event goes into an append-only ledger. Each NPC builds beliefs from evidence, with a
source and a confidence, and a belief can be wrong and later retracted. Numeric drives and trust decide what an NPC
does. A language model only voices it, and every line it says must cite the ledger events and beliefs behind it,
checked by code before anyone hears it.

- **Play it:** <https://thespis-production.up.railway.app>. Press **Watch the 60-second story**, or play it yourself.
- **A second game on the same core:** <https://thespis-production.up.railway.app/manor/>, The Manor Mystery, a
  detective scene where a maid lies to protect herself and the inspector catches her. Press **Watch the case solved**,
  or solve it yourself.
- **Video:** <https://youtu.be/WD7oslaKQO4> (2 minutes, with subtitles).
- **Numbers:** [results.md](results.md), measured on the hosted engine.

[![The why-chain in The Crypt Road: Captain Brenna's line traced to the decision behind it and the beliefs it cites](docs/images/crypt-road-why-chain.jpg)](https://youtu.be/WD7oslaKQO4)

*The why-chain: Captain Brenna's line, traced to the decision behind it, the beliefs it cites and the ledger events at the root. Click the picture to watch the video.*

## The demo: The Crypt Road

A race to a relic in a crypt, five stops down one road. Insult your rival Kael, beat him in a duel and take his
purse, and he remembers. Out of your sight he tells Captain Brenna, and she won't let you through the gate. Pay her
fine, then frame Kael with a lie, and she detains him. You win the race, but Odo, a peddler who saw everything, tells
the Captain the truth afterwards, and she remembers whose word she trusted.

Every NPC line in the client opens a **why-chain**: the line, the decision that produced it, the beliefs it cites, and
the ledger event at the root, marked true or false.

## How it works

```mermaid
flowchart LR
    P["Player verb"] --> R["Game rules"]
    R -->|"appends"| L[("Ledger: what really happened")]
    L -->|"seen, told, gossiped"| B["Each NPC's beliefs: source, confidence, can be false"]
    B --> D["Drives and trust"]
    D --> U["Utility brain scores the allowed actions"]
    U -->|"the ones close to the best"| S["State pack: beliefs, events, allowed actions. Never the truth"]
    S --> C{"Cache"}
    C -->|"miss"| M["Language model"]
    C -->|"hit"| V
    M --> V{"Validator"}
    V -->|"passes"| A["Action and a line citing ledger ids"]
    V -->|"fails"| F["The code's choice and a template line"]
    A --> R
    F --> R
```

- **Ledger:** append-only ground truth (`thespis/ledger.py`). Nothing edits or deletes an event. Claims are typed:
  a predicate, who it's about and whom it names, and optionally where and when it held and whether it's denied.
- **Beliefs:** each NPC's evidence for or against a claim, with its source and confidence (`thespis/beliefs.py`),
  fused into a subjective-logic opinion: belief, disbelief and uncertainty. Independent sources add up; testimony
  counts against a claim, and a belief is retracted once disbelief outweighs belief. When an NPC stops trusting
  someone, everything that source told it is re-weighed. Truth is never stored with a belief; it's derived from the
  ledger, so a belief can be false.
- **Drives decide, the model words it:** the utility brain scores every allowed action from the NPC's drives and
  trust, and takes the best. The model is told only what the NPC is doing, with no other options and no scores, and
  writes the line. Offered a choice, it took the strongest pull 86 times in 86 ([docs/cast-review.md](docs/cast-review.md)),
  so with the model on, every route ends exactly as with it off.
- **State pack and validator** (`thespis/expression.py`): the model sees only what the NPC knows, never whether it's
  true, with its beliefs and events under short references (b1, e1, ...). Each call's JSON schema lists exactly the
  references its pack holds, and a model with structured outputs can't step outside it. A reply is rejected unless the line is 1 to 160
  characters, it cites at least one reference, every one is in the pack, and it names no one the NPC doesn't know
  about. A rejected reply, a timeout or no model at all falls back to a template line.
- **Claim check** (`thespis/claims.py`, off by default for now; see Deploy): the validator checks form; this checks
  meaning. A line with consequences (an accusation, an arrest, testimony, a deal, Sable's answer, Lady Vane on the
  case, the narrator) has its claims extracted by a model in the game's own vocabulary, and code checks each one
  against the ledger and what the speaker could know. A line that leaks, hallucinates or contradicts its speaker
  falls back, as does a lie that doesn't state the claim its action asserts. If the extractor doesn't answer, the
  line falls back too.
- **Model gateway** (`thespis/gateway.py`): any OpenAI-compatible endpoint, including Azure. A primary, then a backup,
  then the fallback, within 4 seconds each, with no retries.
- **Cache and replay:** every reply that passes is cached, keyed by the model, the prompt version, the call type and
  the state pack, so the same moment says the same thing again with no model call. `REPLAY=1` serves only from the
  cache and the fallback.
- **The tick:** each phase, the player acts; the Captain and Kael decide; gossips pass on what they believe; everyone
  moves; fear fades. NPCs decide on where everyone stood when the phase began.
- **Core and adapter:** `thespis/` knows nothing about this game; `games/crypt_road/` is one adapter on it. A test
  fails if the core ever imports from a game. [examples/minimal_client.py](examples/minimal_client.py) uses the core
  alone, in about 30 lines.
- **Persistence:** SQLite, an insert-only ledger table plus a snapshot per session, so a restart loses nothing.
- **The Dungeon Master:** after each phase the model tells the player what happened, including what they couldn't
  see, citing the events it uses. Code sifts the ledger for the story's threads (revenge brewing, a lie told, a lie
  exposed) and shows the live one under the telling. If a telling fails the validator, the code-built telling stands.
- **Live persona editing:** in the inspector's Minds tab, change an NPC's persona and its next line follows it. The
  edit belongs to that game, so other players and the demo cache are untouched.
- **Haggling:** offer Brenna any bribe. Code sets her price from her trust in you (15 to 30 coins, never under 20
  while she distrusts you); under it she refuses a lowball (under half her price) and counters anything else, and the model words it.

## Numbers

From [results.md](results.md): every scripted route, played on the hosted engine with GPT-6 Luna. The last two rows
are model-judged: GPT-5.4 nano read 50 of Luna's lines beside the state packs they came from (`tools/judge.py`).

| Measure | Value |
| --- | --- |
| NPC turns played by code alone, with no model call | 87% |
| Model replies blocked by the validator | 0 of 91 |
| Model call latency on the host, p50 / p95 | 1131 ms / 1704 ms |
| An action that calls the model, p50 / p95 | 1.6 s / 2.2 s |
| An action that doesn't | 34 ms |
| Cost per run, every call to the model | $0.00071 |
| Routes ending as the rules model predicts | 10 of 10 |
| Lines stating only what the NPC knew (model-judged) | 43 of 50 |
| Lines in character (model-judged) | 50 of 50 |

Which models and why: [docs/models.md](docs/models.md).

## Same core, a different game: the manor mystery

[The Manor Mystery](https://thespis-production.up.railway.app/manor/) is a three-room detective scene on the same
core, with its own adapter (`games/manor/`) and none of the Crypt Road's code. Lady Vane's signet ring went
missing before you arrived; the ledger knows Sable took it and that Pell saw her leave the study. Ask Sable where she
was and she lies. Her lie is an action the rules choose once she's frightened enough: the model words it, the line
cites the claim it states, and the ledger logs it false, so the inspector marks it. Ask Pell,
have Lady Vane question him, and his testimony breaks the alibi. Accuse Sable before evening to win.

[![The manor mystery: Sable's lie in the why-chain, beside the house with the hall in darkness](docs/images/manor-lie-why-chain.jpg)](https://thespis-production.up.railway.app/manor/)

*Sable's lie, traced: her line, the action she chose (to lie rather than dodge), the statement the ledger logged false,
and what she really knew. Click the picture to play.*

In the browser it plays like The Crypt Road. The house is a pixel-art cutaway drawn in code, where only the room you're
in is lit and the afternoon turns to evening in the windows. People walk between rooms and speak in typed bubbles, Sable
sweats as her fear rises, a red LIE stamp lands when a statement is logged false, and Pell walks into the hall to
testify. Press **Watch the case solved** for the solve with captions (about a minute), or solve it yourself. The case
notes after every move are built from the ledger with no model calls, and the inspector is The Crypt Road's: Minds,
Beliefs, Ledger and Why.

The only change the core needed was that one feature, NPC deception as a validated action (`thespis/deception.py`).
`python tools/manor_solve.py <host>` solves it by script. Rules and API: [docs/manor.md](docs/manor.md).

## What's new, and what isn't

NPCs whose beliefs can be false against ground truth have existed in symbolic systems for a decade, so that isn't our
claim. What's new is putting that model under a language model that may only choose code-validated actions and must
cite ledger events in what it says. That makes an NPC's lies and mistakes checkable rather than hallucinated.

| Prior work | What it does | What it lacks next to Thespis |
| --- | --- | --- |
| [Talk of the Town](https://www.gameaipro.com/GameAIPro3/GameAIPro3_Chapter37_Simulating_Character_Knowledge_Phenomena_in_Talk_of_the_Town.pdf) (Ryan et al., 2015) | Per-character beliefs that can be false, with sources and decaying strength; lies and misremembering | No language model, no validated action set, not a reusable framework |
| [Versu](https://versu.com/wp-content/uploads/2014/05/versu.pdf) (Evans and Short, 2013) | Individual and false beliefs, actions from social practices, a drama manager | No language model, no ledger, no confidence-weighted gossip |
| [Viv](https://viv.sifty.studio/introduction/) (Ryan, Sifty) | A domain-agnostic engine: a chronicle, witnessed memories, gossip, plans and story sifting | No language model; we found no confidence, false beliefs or retraction |
| [Generative Agents](https://arxiv.org/abs/2304.03442) (Park et al., 2023) | Language-model memory, reflection, planning and information spreading | No ground truth or confidence; the model drives agents with no validated action set |
| [Orchestrated Reality](https://arxiv.org/html/2606.16014v1) (2026) | An append-only event journal, plan-diff-validate-apply, deny-first permissions | No per-NPC beliefs or gossip |

What we claim: the model has no write path to memory, since only the game writes the ledger and beliefs; every line
cites ids the validator checked; and NPCs can be wrong, act on it, and be corrected by testimony.

## Run it locally

You need Python 3.12 or later (CI uses 3.13) and Node 22.

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest                                 # the whole suite, no network needed

cd client && npm ci && npm run build && cd ..
uvicorn games.crypt_road.app:app --reload   # the game and the API on http://localhost:8000
```

That runs with no model at all: every NPC uses its code choice and template lines, and the game plays the same. To
hear the model, copy `.env.example` to `.env`, fill in an OpenAI-compatible endpoint, key and model (Azure works;
see [docs/models.md](docs/models.md)), and start the engine with `--env-file .env`. Never commit `.env`.

The tools that read the host's call log (`harness`, `smoke`, `warm_cache`, `manor_solve`) need the host's
`ADMIN_TOKEN`; they read it from the environment or `.env`.

**Dependencies** are pinned with hashes in `requirements.txt` and `requirements-dev.txt`, compiled by
[uv](https://docs.astral.sh/uv/) from `requirements.in` and `requirements-dev.in`. To add or upgrade one, edit the
`.in` file and recompile both (CI fails if they drift):

```bash
uv pip compile requirements.in --universal --generate-hashes --python-version 3.12 -o requirements.txt
uv pip compile requirements-dev.in --universal --generate-hashes --python-version 3.12 -o requirements-dev.txt
```

CI also runs `ruff check .`, `pyright` and `pytest`, and builds and checks the image (`scripts/check-image.sh`).

### Rehearsal

Rehearsal plays fixed scenarios of both games in-process and measures what the NPCs said
([docs/cast-review.md](docs/cast-review.md#rehearsal-the-papers-instrument-as-a-release-gate)). The scenarios are:

- every route of The Crypt Road on two seeds;
- five routes through the manor;
- eight adversarial lines, each said at two moments.

On every pull request, `pytest` replays the recorded replies with no network (`tests/test_rehearsal.py`). It fails
in either of these cases:

- **What the model is shown changed.** A call misses the recordings: record again.
- **What an NPC says or does changed.** A scenario differs from `rehearsal/transcripts.json`: if the change was
  intended, accept it with `replay --update`.

```bash
python -m rehearsal replay                 # what CI runs: no network
python -m rehearsal replay --update        # accept a change in what the NPCs say, when no call missed
python -m rehearsal live --record          # the live model (LLM_*): a new report, new recordings and transcripts
python -m rehearsal compare rehearsal/reports/baseline.json rehearsal/reports/<new>.json   # the gate
```

**`live`** needs `LLM_*` in `.env` and a judge, `JUDGE_<NAME>_*` (by default `JUDGE_DEEPSEEK_*`; `--lines 0` skips
the judge). Its report covers:
- refusals by reason;
- per line: leaks, hallucinations and contradictions, each with a 95% interval. The judge only extracts what each
  line claims (`thespis/claims.py`); code checks each claim against the ledger and against what the speaker could
  know.
- latency per call type and per action;
- cost.

**`compare`** fails when the new report is worse than the base in any of these ways:
- protocol refusals above 1% of replies;
- leaks or hallucinations worse with 95% confidence;
- action p95 more than 10% slower.

`rehearsal/reports/baseline.json` is the system before Phase 2.

To work on the client with hot reload, run `npm run dev` in `client/` next to the engine and open
<http://localhost:5173>; [client/README.md](client/README.md) has the rest.

### Tools

| Command | What it does |
| --- | --- |
| `python examples/minimal_client.py` | The core alone, no game: a ledger, a belief, allowed actions, and a cited line from the model or the fallback |
| `python tools/crypt_road_sim.py` | The reference rules model: route outcomes and the demo-route acceptance test |
| `python tools/harness.py <host>` | Plays every route on a host and writes `results.md` |
| `python tools/warm_cache.py <host>` | Plays the client's autoplay route until the cache answers it all |
| `python tools/bench_models.py` | Each configured model alone on real state packs: latency and valid picks |
| `python tools/make_fixtures.py` | Regenerates `fixtures/` from the real API |
| `python tools/manor_solve.py <host>` | Solves the manor mystery by script, and checks two wrong turns lose |
| `python tools/exposure.py <host>` | Checks the host keeps its edges shut against a stranger: no call log, API docs or CORS, a body limit, security headers |
| `DEMO_HOST=<host> pytest tests/demo_test.py` | The demo script's checks, beat by beat, against a live host |

## Repository layout

```
thespis/            the core: ledger, beliefs, minds, decisions, gateway, expression, store. Knows no game
games/crypt_road/   the demo game as a Thespis adapter: content, rules, voice, views, the web app
games/manor/        a second adapter: the manor mystery, served at /manor (its client is client/manor/)
client/             the browser client for both games: The Crypt Road (index.html) and the manor (manor/)
docs/               the API contract (api.md), models.md, and the design docs
fixtures/           real API responses along the demo route, for building the client
tools/              the rules model, harness, cache warmer, model benchmark and fixture generator
rehearsal/          scenarios, recordings and reports: the regression suite CI replays
tests/              the pytest suite, run by CI on every pull request
```

## Modules

| Module | What it does | Status |
| --- | --- | --- |
| **Cast** | NPC minds: ledger, beliefs, drives, validator, model voice | Built for this hackathon |
| **Rehearsal** | Regression suite and benchmark | v1: `python -m rehearsal`, replayed in CI; `tools/harness.py` for a host |
| **Director** | Story sifting, pacing, quests from the ledger | Planned; the registry is in `thespis/director.py` |
| **Stage** | Game adapters and engine SDKs | Planned; The Crypt Road is the first adapter |

## Deploy

One Docker image serves the engine API and the built client from one URL (`Dockerfile`). It's hosted on Railway,
which rebuilds and redeploys every merge to `main`.

- **Settings:** `.railway/railway.py` declares the service: the Dockerfile build, a `/health` check, one replica,
  the volume, and the names of its variables. Railway doesn't read it on deploy. A change reaches the live service
  only through `railway config plan` and then `railway config apply`, which need `railway-sdk` (a dev dependency).
  Apply removes whatever the file leaves out, so add a new variable's name there before setting it in the
  dashboard, and read the plan before every apply.
- **Volume:** mounted at `/data`. The database is `/data/thespis.sqlite`, set by the image. Don't set `DB_PATH` on
  Railway: with a volume attached, the app ignores any path off it and logs a warning.
- **Model keys:** Railway variables, never in the repo.
- **Admin token:** `ADMIN_TOKEN` opens `GET /dev/calls`, the call log across every session, which the harness and
  smoke test read. Unset, the endpoint doesn't exist. Generate it yourself, e.g.
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`, and keep it out of the repo.
- **Moderation:** with `CONTENT_SAFETY_ENDPOINT` and `CONTENT_SAFETY_KEY` set, Azure AI Content Safety checks what
  players write before a model reads it and every model line before a player hears it. Thresholds per category:
  Hate, Sexual and SelfHarm at 4, Violence at 6, overridden by `MODERATION_THRESHOLDS` (JSON). It fails closed: if the
  service is down, NPCs use their code lines. It sends at most `CONTENT_SAFETY_RPS` requests a second (4, under the
  free tier's 5; set 100 on the standard tier), one text per request, since joined texts hid a harmful line in tests. A game can also list words in `[moderation] blocklist` in its
  `cast.toml`. The boot log says which moderation is active.
- **Claim check:** off by default for now. `CLAIM_CHECK=consequential` checks the lines with consequences, and `all`
  checks every model line. Each check is one more model call, counted against the caps, through the model that
  spoke unless `LLM_CHECK_*` names another. The boot log says which.

  Why off: in three rehearsals the check refused 9 lines that the extractor (gpt-6-luna) had misread, and no line it
  should have refused. Marking whom each claim is credited to (`attributed_to`) stopped it refusing Lady Vane's
  verdict, which repeats Sable's alibi, but extraction slowed to 1.5 s, and act p95 rose to 3.3 s from 2.3 s without
  the check. gpt-5.4-nano thinking a little was slower still: 19 calls timed out. With so few lines actually wrong,
  the check needs extraction both more accurate and faster than either. The reports are
  `rehearsal/reports/claim-check-*.md`.
- **Edges:** no CORS unless `CORS_ORIGINS` lists origins; no generated API docs unless `API_DOCS=1`; bodies over
  64 KiB refused. After a deploy, `python tools/exposure.py <host>` should pass every check.
- **Logs:** JSON lines (`LOG_FORMAT=json`, set by the image) with `message`, `level` and fields such as `path`,
  `status`, `ms` and `call_type`, which Railway can filter by (`@status:500`). Sessions appear as a short hash, never
  their id, and moderation logs why it flagged something, never the text.
- **User:** the app runs as uid 10001, not root. The entrypoint gives it `/data` and then drops root.
- **Caps:** `SESSION_CALL_CAP` (default 60) and `GLOBAL_CALL_CAP` (default 0, no cap) bound model calls; cache
  hits are free, and past a cap NPCs fall back to code and the game plays on. `SESSIONS_PER_IP_HOUR` (default
  30) limits new games per IP. The boot log shows the caps and the calls made so far.
- **Model cache:** playing the demo route on the host warms it (`tools/warm_cache.py`). Re-warm after any change to a
  prompt, a persona or the state pack. `REPLAY=1` then plays from the cache and the fallback alone. The boot log
  shows `model cache: N replies`.
- **Persistence check:** redeploy the service, and the log's `boot #N` should go up by one.
- **Backups:** Railway's scheduled volume backups need the Pro plan, so on Hobby copy the volume down with the
  [Railway CLI](https://docs.railway.com/cli/volume) before any risky deploy. It holds both games' databases and
  their WAL files:

  ```bash
  railway login && railway link                      # once, in this folder
  railway volume list                                # the volume's name
  railway volume files --volume <name> download / ./backups/$(date +%F)
  python -c "import sqlite3, sys; print(sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check').fetchone()[0])" ./backups/$(date +%F)/thespis.sqlite
  ```

  The last line should print `ok`. To restore, upload the files back (`railway volume files --volume <name> upload
  <folder> / --overwrite`) while the service is stopped. Keep `backups/` out of git; it's ignored.

Test the image locally:

```bash
docker build -t thespis:dev .
docker run --rm -p 8000:8000 -v thespis-data:/data thespis:dev
sh scripts/check-image.sh thespis:dev       # what CI checks: non-root, JSON logs, the volume persists
```

## Credits

- **Art and fonts:** drawn in code for this game; fonts are under the SIL Open Font License. See
  [client/CREDITS.md](client/CREDITS.md).
- **NPC voices:** GPT-6 Luna, with GPT-5.4 nano as the backup, on Azure AI Foundry ([docs/models.md](docs/models.md)).
- **Ideas:** the character-knowledge work of Talk of the Town, Versu and Viv, and Generative Agents, as cited above.

## Licence

[MIT](LICENSE).

## Team

- Tobi ([@coderback](https://github.com/coderback)): engine, model layer, harness, deployment
- Ahmed ([@AhmedBokaniUsman](https://github.com/AhmedBokaniUsman)): client, inspector, autoplay, video

Read [CONTRIBUTING.md](CONTRIBUTING.md) before your first pull request. Built for the Cambridge University x Arcade
AI Hackathon, 3 to 4 October 2026.
