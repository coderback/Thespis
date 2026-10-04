# Thespis

An AI/ML toolkit for game developers. Its first module, **Thespis Cast**, gives NPCs minds of their own:
they remember what happened, believe things that may be false, want things for reasons, and keep acting
when the player is not looking.

The game owns the truth. Every event goes into an append-only ledger. Each NPC builds beliefs from
evidence (source, confidence, can be wrong, can be retracted), and numeric drives and trust decide what
it will do. The language model only picks from actions the code has validated and voices them, citing
the ledger events behind each line.

**Live:** <https://thespis-production.up.railway.app> (the engine is in progress; `/health` answers today).

**Demo game:** *The Crypt Road*, a race to a relic where a humiliated rival reports you to the guard out
of sight, a lie can frame him, and a passing witness can expose you.

## Modules

| Module | What it does | Status |
| --- | --- | --- |
| **Cast** | NPC minds: ledger, beliefs, drives, validator, model voice | Building (hackathon) |
| **Director** | Story sifting, pacing, quests from the ledger | Planned |
| **Stage** | Game adapters and engine SDKs | Planned |
| **Rehearsal** | Test harness and benchmark | Planned |

## Repository layout

```
thespis/            core: knows nothing about any specific game (Tobi)
games/crypt_road/   the demo game, as a Thespis adapter (Tobi)
client/             browser client: map, play UI, inspector (Ahmed)
docs/api.md         the API contract between engine and client (both)
fixtures/           canned API responses for building the client (both)
tools/              reference rules model and helper scripts
tests/              pytest suite, run by CI on every PR
scripts/            one-off setup scripts
```

## Run it locally

```powershell
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                          # rules model + architecture checks
python tools/crypt_road_sim.py  # route outcomes and the demo-route acceptance test
uvicorn games.crypt_road.app:app --reload   # the app on http://localhost:8000
```

Copy `.env.example` to `.env` for model keys. Never commit `.env`.

## Deploy

One Docker image serves the engine API and the built client from the same URL (`Dockerfile`). It is hosted on
Railway, which rebuilds and redeploys every merge to `main`, so the hosted URL always matches `main`.

- **Settings:** `railway.toml` sets the Dockerfile build, a `/health` check and one replica.
- **Volume:** mounted at `/data`. The SQLite database is `DB_PATH=/data/thespis.sqlite`.
- **Model keys:** set as Railway variables, never in the repo.
- **Model cache:** every validated model reply is kept in the database, so playing the demo route twice on
  the host warms it. `REPLAY=1` then plays from the cache and the fallback alone, with no model calls, which
  keeps the demo working if the keys or credits die. The boot log shows `model cache: N replies`.
- **URL:** <https://thespis-production.up.railway.app>
- **Check the volume persists:** *redeploy* the service (a fresh container, unlike a restart), and the log line
  `boot #N` should go up by one. Checked on 3 Oct: a redeploy logged `boot #2`.
- **Freeze:** turn off auto-deploy at Sunday 12:00.

Test the image locally:

```bash
docker build -t thespis:dev .
docker run --rm -p 8000:8000 -v thespis-data:/data thespis:dev   # restart it: "boot #N" keeps counting
```

## How we work

Read [CONTRIBUTING.md](CONTRIBUTING.md) before your first PR. In short: nobody pushes to `main`,
every change goes through a pull request that CI must pass, and each of us owns our own folders.

## Team

- Tobi ([@coderback](https://github.com/coderback)): engine, model layer, harness, deployment
- Ahmed ([@AhmedBokaniUsman](https://github.com/AhmedBokaniUsman)): client, inspector, autoplay, video

Built for the Cambridge University x Arcade AI Hackathon, 3 to 4 October 2026.
