# Contributing

Thespis is open to contributions: bug reports, fixes, docs, examples, and games built on it. For anything larger than
a fix, open an issue first and say what you have in mind, so we can agree on the shape before you build it.

## Set up

You need Python 3.12 or later. Node 22 is only for the demo games' browser client.

```bash
git clone https://github.com/coderback/Thespis
cd Thespis
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest                                 # the whole suite: no network and no model needed
```

## Before you open a pull request

Run what CI runs on the engine:

```bash
ruff check .
pyright
pytest -q
```

Some changes need more:

| If you change | Also |
| --- | --- |
| `thespis.api` or the `/v1` routes | Update [docs/protocol.md](docs/protocol.md); regenerate the contract (`python -m thespis openapi --out docs/openapi-v1.json`) and the SDKs' typed layers (`python tools/sdk_gen.py all`) |
| What NPCs believe, decide or say | `python -m tools.outcomes` shows what changed in the demo's 35 routes; `python -m rehearsal replay` what changed in the recorded scenarios. Accept an intended change with `--update`, and say why in the pull request |
| Speed at town size | `python tools/town_bench.py --check` holds each call to its budget |
| A dependency | Edit the `.in` file and recompile the lock files ([README](README.md#run-it-locally)); CI fails if they drift |
| The demo client (`client/`) | `npm run lint`, `npm test` and `npm run build` in `client/` |

Two things every change keeps:

- **A game with no model plays the same.** Every line has the game's own words to fall back on, and the tests run
  with no network.
- **The core knows no game.** `thespis/` never imports from `games/`; a test checks.

## Pull requests

- **One change per pull request,** on a branch named for what it does (`gossip-along-ties`, not `patch-1`).
- **Say what changes, why, and how you tested it.** The template asks for each.
- **CI must pass,** and the branch must be up to date with `main`. Pull requests are squash merged, one commit each.
- **No secrets in git.** Keys live in `.env`, which is ignored.

## Where things live

| Path | What it is |
| --- | --- |
| `thespis/` | The core. `thespis.api` is the public surface; the rest may change between 0.x releases |
| `examples/` | Small games in one TOML file each, and the quickstart |
| `sdk/godot/`, `sdk/unity/` | The engine clients for `/v1` |
| `games/` | The two demo games, as adapters on the core |
| `client/` | The demo games' browser client |
| `rehearsal/` | Scenarios, recordings and reports: the regression suite CI replays |
| `tools/` | Benchmarks, the packager, the load test, generators |
| `tests/` | The pytest suite |
| `docs/` | The guides and the reference ([docs/README.md](docs/README.md)) |

## Style

- Python 3.12, lines up to 120 characters, `ruff` and `pyright` as configured in `pyproject.toml`.
- Docs and comments in plain words and short sentences, saying what a thing does and why.

## Releasing

For maintainers. A release is one pull request and one tag:

1. Set the new number in `thespis/__init__.py`, and give it a section in [CHANGELOG.md](CHANGELOG.md).
2. Merge it.
3. Push the tag: `git tag -a v0.3.1 -m "Thespis 0.3.1" && git push origin v0.3.1`.

The release workflow checks that the tag, the package and the changelog agree, builds and checks the package,
publishes it to PyPI as `thespis-npc`, and makes the GitHub Release with the changelog's notes.

## If `main` breaks anyway

Revert the offending squash commit with a pull request (`git revert <sha>`), get CI green, merge, then fix forward on
a branch.

## Licence

By contributing, you agree that your contribution is licensed under the project's [MIT licence](LICENSE).
