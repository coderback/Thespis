"""The thespis command.

    python -m thespis serve --game examples/tavern/game.toml [--port 7878]   # the /v1 API on localhost
    python -m thespis openapi [--out docs/openapi-v1.json]                  # the API's contract

`serve` speaks through the models the environment configures (thespis.gateway), or uses each game's template lines
when it configures none. It listens on 127.0.0.1 unless told otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from thespis.server import create_app
from thespis.session import Game


def openapi() -> str:
    """The /v1 spec, as committed: stable key order and a trailing newline, so a diff shows only real changes."""
    return json.dumps(create_app({}).openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="thespis")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="serve the /v1 API")
    serve.add_argument("--game", action="append", required=True, help="a game.toml to load (repeatable)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=7878)
    spec = sub.add_parser("openapi", help="print the /v1 OpenAPI spec")
    spec.add_argument("--out", help="write it here instead")
    args = parser.parse_args(argv)

    if args.command == "openapi":
        if args.out:
            Path(args.out).write_bytes(openapi().encode())
        else:
            sys.stdout.write(openapi())
        return 0

    import uvicorn

    from thespis.gateway import gateway_from_env

    games = {g.id: g for g in (Game.load(p) for p in args.game)}
    uvicorn.run(create_app(games, gateway_from_env()), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
