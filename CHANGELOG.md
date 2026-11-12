# Changelog

Thespis follows semantic versioning at 0.x: a minor release may change anything outside `thespis.api` and the `/v1`
protocol, and those change only with a note here. A release is made by pushing its tag (`v0.3.1`), which publishes it
to PyPI and GitHub Releases from the section below that has its number.

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
