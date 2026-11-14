# Changelog

Thespis follows semantic versioning at 0.x: a minor release may change anything outside `thespis.api` and the `/v1`
protocol, and those change only with a note here. A release is made by pushing its tag (`v0.3.1`), which publishes it
to PyPI and GitHub Releases from the section below that has its number.

## Unreleased

- **An inspector.** `thespis serve` serves a page at `/inspector/` that shows its sessions as the game plays: the
  cast and its ties, each NPC's beliefs with their evidence, why an NPC would choose what it would, the ledger, and
  where a story goes. It only reads, takes the token in its address's fragment, and loads nothing from anywhere else,
  so it works offline. The runtimes on GitHub Releases carry it too.
- **Read-only calls for it, and for tools.** `GET /v1/sessions` lists a project's sessions; `GET /v1/sessions/{id}`
  (`Session.overview()`) shows one at a glance; `POST .../explain` gives over HTTP what `Session.explain` gives.
  The Godot and Unity clients' generated layers have them.

## 0.5.0 (14 November 2026)

Thespis you can design with: it says why an NPC did or didn't do something, follows a story along the grapevine,
stays as fast late in a long game as early, underlines a game file's mistakes as you type, and has the words crime
and social games asked for: an unknown culprit, a liar caught, secrets kept, a bribe that counts by its size.

```bash
pip install --upgrade thespis-sdk
```

**Before you upgrade.** These can change what an existing game sees:
- **A liar caught is now an event.** When one culprit's story loses (`[claims] one_actor`), Thespis writes a
  `caught` event to the ledger, so the ids of events written after it move on by one. A game that stores event ids
  keeps working; one that predicts them may not.
- **A long game keeps less evidence.** Of the repeats of one report, an NPC keeps the first, the strongest and the
  latest; what it believes and does is unchanged, but it can no longer cite the repeats in between. Older saves are
  trimmed when they load.
- **`inspect` and `add`** leave out `frozen_until` and `last_seen` unless they're set (only the demo games set them).
- **The Godot and Unity clients are 0.5.0** and warn when the runtime is older than 0.5.0.

### Why, and why not

- **`Session.explain(npc, moment, bindings)`** lists every choice the NPC has: whether it is open, what keeps it shut
  with the values it saw (`anger is 2, needs >= 4`; `believes stole_from(player, mara) only at 0.73, needs 0.8`),
  and how its utility adds up (`anger 5 x 2 + 1 = 11`). `decide(..., explain=True)` puts the same on the line, as it
  stood when the NPC chose, also when it chose nothing; over HTTP too.
- **`Session.trace(claim)`** (and `POST .../trace`) follows a story on the grapevine without changing anything: who
  holds it and from whom, what the next tick would tell of it with the sum for each listener (`0.9 x 0.9 (trust 2) x
  0.9 (friend) = 0.73`), and where it stops and why. Its predictions are the tick's own.
- **`Session.events(after, verb)`** (and `GET .../events`) lists the ledger after an event: after an `observe`, what
  it led to.

### New words for the game file

- **Caught in a lie.** A `caught` event when an NPC's story from someone loses to a truer one, and a condition
  `{ caught = "{who}" }`.
- **Someone did it.** A claim, and an event's actor, may name `"someone"` when nobody knows who did a deed yet. A
  condition on `a = "someone"` holds for the deed by anyone; a name learned later is no rival story and no second
  offence.
- **Secrets and silence.** `[gossip] secret` names predicates nobody passes on, and `[[npc.<id>.keeps]]` news one NPC
  (or a kind) won't pass on, while its `when` holds: hush money is a flag the game sets, loyalty a trust condition.
- **Trust and amounts in choices.** `{ trust = who, gte = n }`, and a utility term `{ bound = "amount", weight = 0.5 }`
  so a bribe counts by its size.

### Speed, editors and engines

- **A long game no longer slows down.** Over 20,000 events an `observe` stays near 0.42 ms where it climbed to
  1.45 ms, and the save is half the size (`tools/long_game.py`).
- **A schema for editors.** `docs/game.schema.json`, built from the loader's own lists: with a `#:schema` line at the
  top of a game file, VS Code's Even Better TOML and other Taplo editors offer every table and key and underline a
  misspelt key or a number out of range. `python -m thespis schema` prints it.
- **Engine clients for the whole cast.** The Godot and Unity clients add, retire, tie and untie NPCs in play, trace
  stories and read the ledger. `/v1/health` reports the runtime's version, which the clients check. Each package
  carries its licence and a README listing every call, for the asset stores.
- **The core sheds the demo's leftovers.** The demo's SQLite store and story-hook registry moved to `games/`, so the
  package no longer ships them.

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
