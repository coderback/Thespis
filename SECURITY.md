# Security

## Reporting a vulnerability

Report it privately: on GitHub, open the repository's **Security** tab and choose **Report a vulnerability**. Please
don't open a public issue, pull request or discussion for it.

Say what is affected (the `thespis-sdk` package and its version, `thespis serve` as a sidecar or a server, an SDK, or
the hosted demo), how to reproduce it, and what it lets someone do. We aim to answer within a week, agree on a fix
and a date with you, and credit you in the release notes unless you'd rather not be named.

## Supported versions

The latest release on [PyPI](https://pypi.org/project/thespis-sdk/) gets security fixes. Thespis is 0.x: a fix lands
in the next release, not in older ones.

## What Thespis defends, and how

- **A sidecar** (`thespis serve`, the default) listens on this machine only, refuses requests addressed to any other
  name (DNS rebinding), wants the token its launcher sets (`THESPIS_TOKEN`), and is offline unless started with
  `--online`: it refuses every connection off the machine from inside its own process
  ([docs/serve.md](docs/serve.md)).
- **A server** (`thespis serve --server`) wants each project's key on every call, keeps projects' sessions and games
  apart, seals each project's model keys at rest (AES-256-GCM under `THESPIS_SECRET_KEY`), and refuses model
  addresses on private networks unless told otherwise.
- **Every `/v1` call** is checked against the game before it changes anything, and bodies have size limits.
- **Model output** never decides what happened: a line must cite what the NPC knows, and the validator refuses one
  that doesn't. What a player types is read only as one of the intents the game offers now (`understand`), and
  changes nothing by itself: the game applies the act. Moderation is optional (`CONTENT_SAFETY_*`).

Within scope: anything that gets around one of these, leaks a key or another project's data, runs code from a game
file or a request, or lets a request crash or exhaust a sidecar or server. Testing the hosted demo is welcome as long
as it doesn't degrade it for others: no load or denial-of-service testing against it.
