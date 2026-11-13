# Changelog

Thespis follows semantic versioning at 0.x: a minor release may change anything outside `thespis.api` and the `/v1`
protocol, and those change only with a note here. A release is made by pushing its tag (`v0.3.1`), which publishes it
to PyPI and GitHub Releases from the section below that has its number.

## 0.4.0 (13 November 2026)

Thespis you can trust with a real game: a game file and every call on it are checked, saves survive a patch, the
sidecar is safe to ship beside a game, and NPCs settle conflicting stories the way a designer would expect.

```bash
pip install --upgrade thespis-sdk
```

**Before you upgrade.** These can change what an existing game does:
- **A file that loaded before may now be refused.** Misspelled tables and keys, ids, places, predicates and drives
  the file never declares, numbers out of range, and templates with more than a plain `{name}` are errors now. Run
  `thespis check game.toml` to see them all at once. A game's own data belongs in `[custom]`.
- **Calls that named someone or something unknown are refused** with what was probably meant, instead of taking it
  as new (a misspelt drive used to become a new one).
- **Beliefs.** A game using `[claims] one_actor`, or where one story reaches an NPC by two mouths, may play
  differently (below). The demo's 35 routes play as before.
- **A sidecar refuses requests not addressed to this machine** (403), and every `/v1` body has a size limit (413).
  The Godot and Unity SDKs are unaffected.

### Checked

- **A game file is checked whole when it loads.** Every mistake is named, a line each, with what was probably meant.
  These used to load and quietly switch a mechanic off.
- **`thespis check game.toml`** prints every mistake, and notes what is allowed but likely a slip (an action with no
  line). `thespis serve` refuses a bad file the same way, without a traceback.
- **Calls check what they're given.** `observe`, `update`, `decide`, `react`, `tick` and `restore` refuse an
  unknown person, place, predicate, drive, moment, trigger or binding, instead of failing with a Python `KeyError`.
  A damaged snapshot is a `DefinitionError` (HTTP 400), not a 500.

### Beliefs: one story, one weight, and its teller pays

- A listener weighs each story once, by whose it is (who saw it, or first said it): a lie passed on by a friend and
  then told to its face no longer counts twice. Evidence records its `origin`.
- When one culprit's story beats another, whoever started the losing story is trusted less, not whoever only passed
  it on.
- The losing story is always retracted, even when the winner is weakly believed. It could stay active, believed more
  than the story that beat it.

### Saves and the sidecar

- **A save outlives a patch.** A save made before the game file changed restores under the new one: an NPC the file
  dropped (or renamed) retires with what it believed, a new one joins, whoever stood in a removed place goes back to
  their start, and `Session.patched` says what changed. It used to load and then fail on the first tick.
- **A shipped game's sidecar no longer fills up.** The engines' launchers kill it on quit, so its sessions were never
  closed, and after 256 launches it refused new ones. At its limit a sidecar now drops the session saved longest ago
  that nobody is playing. A server still refuses with 503.
- **A sidecar answers only this machine.** It refuses (403) a request whose `Host` isn't localhost, so a web page
  can't reach it by DNS rebinding, and warns at start when it has no `THESPIS_TOKEN`. Every `/v1` body is at most
  1 MB (64 MB to open a session from a snapshot), refused (413) before it is read whole.
- **Prebuilt runtimes.** This release attaches the sidecar a game ships beside it, for Windows (x64), macOS (Apple
  silicon) and Linux (x64), each checked against its size and cold-start budgets: unzip as `thespis/` beside the
  game's executable.

### Docs and the project

- **`docs/tuning.md`:** the numbers that decide outcomes, worked through: the trust ladder (0.9, 0.4, 0.2), how far a
  story travels before the gossip threshold stops it, how stories fuse and conflict, and which knob to turn.
- **Docs for outsiders.** How the hosted demo is run moved to `docs/maintainers.md`; `docs/models.md` opens with any
  provider or none. The PyPI page is the README up to running the repository.
- **`SECURITY.md` and a code of conduct.** Vulnerabilities are reported privately through GitHub's "Report a
  vulnerability"; the project follows the Contributor Covenant 2.1.

## 0.3.1

The first release on PyPI, as `thespis-sdk` (the name `thespis` was taken). It installs and imports as `thespis`:

```bash
pip install thespis-sdk
```

- **For newcomers:** a quickstart (`examples/quickstart`), and a guide to putting Thespis in your own game
  (`docs/getting-started.md`).
- **Typed:** the package ships `py.typed`, so type checkers read its annotations.
- No change to `thespis.api`, `/v1` or snapshots.

## 0.3.0 (12 October 2026)

At town size, with a cast that grows in play.

- **A cast that grows:** `[kind.<id>]` declares kinds of people; `add`, `retire`, `tie` and `untie` change the cast
  and its ties in play.
- **One culprit:** `[claims] one_actor`. Told two stories of one deed, an NPC keeps the one from the source it
  trusts more, and trusts the other teller less (`caught`). `first_hand` counts a teller who saw it for more.
- **At town size:** beliefs and the ledger are indexed; `[gossip] most` caps what a tick tells; `tools/town_bench.py`
  holds a tick, an `observe`, a `decide` and a save to budgets in CI.
- **Statements believed as the engine's rules say:** `observe(..., conf=)`.
- **A second witness:** `[gossip] corroborate` lets a report from a different witness count, and
  `gossips = "everyone"` lets anyone pass news on.

## 0.2.0 (8 to 10 October 2026)

Thespis for any game and any engine.

- **The protocol and the library:** a game is one TOML file; `thespis.api` (`Game`, `Session`) makes the calls, and
  `thespis serve` makes the same ones over `/v1` HTTP, as a sidecar beside a game or a server for many projects.
- **Engines:** a Godot 4 addon and a Unity package.
- **Models:** profiles for any provider (OpenAI, Azure, Anthropic, Gemini, Groq, vLLM, llama.cpp, Ollama), and a
  local runtime for playing offline (Gemma 4 E4B by default).
- **Minds:** players as agents, feelings and their decay, gossip along ties, denials, told scenes, and memory by
  meaning.
- **The player's words:** `understand` reads what a player types as one of the acts open now, or as talk.
- **Rehearsal** runs offline, with calibrated judges and hand-reads, on any game.

## 0.1.0 (3 to 6 October 2026)

Built for the Cambridge University x Arcade AI Hackathon, 3 to 4 October 2026, then hardened. Not tagged.

- **The core:** an append-only ledger, beliefs with sources and confidence that can be false, drives and trust, a
  utility brain, and a model that only voices what code decided, citing the events behind each line, with the
  game's own words to fall back on.
- **Two games on it:** The Crypt Road and the manor mystery.
- **Rehearsal v1** and the claim check: what each line claims, checked in code against the ledger and against what
  the speaker could know.
