"""The thespis command.

    python -m thespis serve --game examples/tavern/game.toml [--port 7878] [--local auto]  # the /v1 API on localhost
    python -m thespis openapi [--out docs/openapi-v1.json]                                # the API's contract
    python -m thespis models list | hardware                       # what the runtime can run, and on what
    python -m thespis models pull [auto | <model>]                 # fetch a model (and llama.cpp), checked
    python -m thespis models serve [auto | <model>] [--device ID]  # run it locally; prints the LLM_* settings
    python -m thespis models probe <url> [--model M] [--key-env NAME] [--out profile.json]

`serve` speaks through the models the environment configures (thespis.gateway), through a local model with
`--local`, or with each game's template lines when there's neither. It listens on 127.0.0.1 unless told otherwise.
`models probe` reads an API key from the environment variable `--key-env` names, never from the command line.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def openapi() -> str:
    """The /v1 spec, as committed: stable key order and a trailing newline, so a diff shows only real changes."""
    from thespis.server import create_app
    return json.dumps(create_app({}).openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _progress(n: int, total: int, last: list[float] = [0.0]) -> None:  # noqa: B006 (shared on purpose)
    if n == total or n / total - last[0] >= 0.05 or n < last[0] * total:
        last[0] = n / total
        print(f"  {n / 1e9:.2f} of {total / 1e9:.2f} GB", file=sys.stderr, flush=True)


def models(args: argparse.Namespace) -> int:
    from thespis.runtime.hardware import choose, machine
    from thespis.runtime.local import LocalModel, engine, model_file
    from thespis.runtime.registry import MODELS, TIERS

    if args.action == "list":
        for m in MODELS.values():
            tier = f"tier {TIERS.index(m.id) + 1}" if m.id in TIERS else ""
            print(f"{m.id:12} {m.params:>4} {m.quant:7} {m.artifact.size / 1e9:5.2f} GB  {m.licence:11} {tier}")
        return 0
    if args.action == "hardware":
        m = machine(engine("metal" if sys.platform == "darwin" else "vulkan", _progress))
        print(f"{m.os} {m.arch}, {m.ram_gb} GB RAM")
        for d in m.devices:
            print(f"  {d.id}: {d.name}, {d.free_mb} of {d.total_mb} MiB free{' (integrated)' if d.integrated else ''}")
        print(f"choice: {choose(m).describe()}")
        return 0
    if args.action == "pull":
        name = None if args.model in (None, "auto") else args.model
        lm = LocalModel(name, progress=_progress)
        print(model_file(lm.plan.model, _progress))
        return 0
    if args.action == "serve":
        lm = LocalModel(None if args.model in (None, "auto") else args.model,
                        device=None if args.device == "cpu" else args.device, port=args.port, progress=_progress)
        print(f"starting {lm.plan.describe()}", file=sys.stderr)
        with lm:
            print(f"ready in {lm.load_seconds:.1f} s at {lm.url}; log: {lm.log_path}", file=sys.stderr)
            for k, v in lm.env().items():
                print(f"{k}={v}")
            sys.stdout.flush()
            try:
                while lm.proc and lm.proc.poll() is None:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        return 0
    if args.action == "probe":
        from thespis.probe import Prober
        if not args.url:
            print("say which endpoint: models probe <url>", file=sys.stderr)
            return 2
        key = os.environ.get(args.key_env, "") if args.key_env else ""
        profile = Prober(args.url, key, args.model or "").run(args.name or "")
        text = json.dumps(profile.to_json(), indent=2, ensure_ascii=False) + "\n"
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"wrote {args.out}: LLM_PROFILE={args.out}", file=sys.stderr)
        else:
            sys.stdout.write(text)
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="thespis")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="serve the /v1 API")
    serve.add_argument("--game", action="append", required=True, help="a game.toml to load (repeatable)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=7878)
    serve.add_argument("--local", nargs="?", const="auto", help="speak through a local model: auto, or a model id")
    spec = sub.add_parser("openapi", help="print the /v1 OpenAPI spec")
    spec.add_argument("--out", help="write it here instead")
    mdl = sub.add_parser("models", help="local models and model endpoints")
    mdl.add_argument("action", choices=["list", "hardware", "pull", "serve", "probe"])
    mdl.add_argument("model", nargs="?", help="a model id or auto (pull, serve); an endpoint URL (probe)")
    mdl.add_argument("--device", default="auto", help="serve on this device (e.g. Vulkan1), or cpu")
    mdl.add_argument("--port", type=int)
    mdl.add_argument("--model", dest="probe_model", help="probe: which model on the endpoint")
    mdl.add_argument("--key-env", help="probe: the environment variable holding the endpoint's API key")
    mdl.add_argument("--name", help="probe: the profile's name")
    mdl.add_argument("--out", help="probe: write the profile here")
    args = parser.parse_args(argv)

    if args.command == "openapi":
        if args.out:
            Path(args.out).write_bytes(openapi().encode())
        else:
            sys.stdout.write(openapi())
        return 0
    if args.command == "models":
        if args.action == "probe":
            args.url, args.model = args.model, args.probe_model
        return models(args)

    import uvicorn

    from thespis.gateway import gateway_from_env
    from thespis.server import create_app
    from thespis.session import Game

    games = {g.id: g for g in (Game.load(p) for p in args.game)}
    env = dict(os.environ)
    local = None
    if args.local:
        from thespis.runtime.local import LocalModel
        local = LocalModel(None if args.local == "auto" else args.local, progress=_progress).start()
        env = {k: v for k, v in env.items() if not k.startswith("LLM_")} | local.env()
        print(f"speaking through {local.plan.describe()} at {local.url}", file=sys.stderr)
    try:
        uvicorn.run(create_app(games, gateway_from_env(env)), host=args.host, port=args.port)
    finally:
        if local:
            local.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
