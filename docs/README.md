# Docs

## Using Thespis

| Doc | What it is |
| --- | --- |
| [getting-started.md](getting-started.md) | Thespis in your own game: the game file, then the calls a game makes, in order |
| [protocol.md](protocol.md) | The reference: every table of the game file, every call, in the library and over `/v1` HTTP; [openapi-v1.json](openapi-v1.json) is the HTTP contract |
| [serve.md](serve.md) | `thespis serve`: a sidecar beside a game, or a server for many projects |
| [models.md](models.md) | Which models voice the NPCs, any provider or none, and local models for playing offline |
| [maintainers.md](maintainers.md) | Running the hosted demo: the Railway service, its settings, checks after a deploy, backups, releases |
| [../sdk/godot/README.md](../sdk/godot/README.md) | The Godot 4 addon |
| [../sdk/unity/README.md](../sdk/unity/README.md) | The Unity package |

## The demo games

Two games built on the core, playable online. Their own APIs are theirs, not Thespis's.

| Doc | What it is |
| --- | --- |
| [crypt-road-v2.md](crypt-road-v2.md) | The Crypt Road's design, as written for the Cambridge x Arcade AI Hackathon (3 to 4 October 2026): world, cast, rules, routes, model calls, UX, demo script |
| [api.md](api.md) | The Crypt Road's HTTP API, between its engine and its browser client |
| [manor.md](manor.md) | The manor mystery: its rules and its API |

## Research and reviews

| Doc | What it is |
| --- | --- |
| [redefining-the-npc.md](redefining-the-npc.md) | Research on stateful, autonomous NPCs: the landscape, memory, planning, personality, player studies, and the architecture Thespis follows |
| [cast-review.md](cast-review.md) | Thespis Cast's architecture reviewed after the hackathon (6 October 2026), and the road to production it set out: the claim check, Rehearsal as a release gate |
