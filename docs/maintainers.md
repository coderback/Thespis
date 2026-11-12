# Running the hosted demo

How the demo at <https://thespis-production.up.railway.app> is run. This is for whoever maintains that host; to run
Thespis beside your own game, see [serve.md](serve.md).

## The service

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

## Test the image locally

```bash
docker build -t thespis:dev .
docker run --rm -p 8000:8000 -v thespis-data:/data thespis:dev
sh scripts/check-image.sh thespis:dev       # what CI checks: non-root, JSON logs, the volume persists
```

## After every merge to main

Railway redeploys. Once the deploy is live, run the three checks against it:

```bash
python tools/smoke.py https://thespis-production.up.railway.app
python tools/exposure.py https://thespis-production.up.railway.app
python tools/manor_solve.py https://thespis-production.up.railway.app
```

## Releasing

Push a tag named for the version in `thespis/__init__.py` (`v0.3.1`). The release workflow builds the package,
publishes it to PyPI by trusted publishing once a maintainer approves the `pypi` environment, and makes a GitHub
Release from that version's section of [CHANGELOG.md](../CHANGELOG.md).
