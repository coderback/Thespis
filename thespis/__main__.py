"""The thespis command.

    python -m thespis serve [--game G.toml ...] [--port 7878 | 0] [--local auto] [--db FILE] [--parent PID]
                                                        # a sidecar: localhost, SQLite, offline unless --online
    python -m thespis serve --server --db postgres://... [--host 0.0.0.0] [--game G.toml ...]
                                                        # a server: projects, each with its key
    python -m thespis projects create NAME | list | key NAME | caps NAME ... | model NAME ... | secret
    python -m thespis usage NAME [--since 2026-10-01] [--format csv | json] [--out usage.csv]
    python -m thespis openapi [--out docs/openapi-v1.json]                                # the API's contract
    python -m thespis models list | hardware                       # what the runtime can run, and on what
    python -m thespis models pull [auto | <model>]                 # fetch a model (and llama.cpp), checked
    python -m thespis models serve [auto | <model>] [--device ID]  # run it locally; prints the LLM_* settings
    python -m thespis models probe <url> [--model M] [--key-env NAME] [--out profile.json]

`serve` speaks through the models the environment configures (thespis.gateway), through a local model with
`--local`, or with each game's template lines when there's neither; on a server, a project's own model settings
come first. It prints `THESPIS_URL=http://...` once it listens, so a launcher that asked for port 0 knows where.
A sidecar keeps its sessions in `--db` (a SQLite file; the runtime's cache folder if left out, `:memory:` for none),
takes the token in THESPIS_TOKEN if it is set, and stops when the `--parent` process does. A server keeps them in
`--db` or $DATABASE_URL, and model keys sealed under THESPIS_SECRET_KEY (thespis.vault).
`projects` and `usage` work on a server's database directly (`--db`, or $DATABASE_URL). No key or secret is ever
taken on the command line: `projects model` reads the API key from the variable `--key-env` names.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
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
            print(f"{m.id:12} {m.params:>4} {m.quant:11} {m.artifact.size / 1e9:5.2f} GB  {m.licence:11} {tier}")
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


def _db(args: argparse.Namespace):
    from thespis.storage import storage
    where = args.db or os.environ.get("DATABASE_URL", "")
    if not where:
        raise SystemExit("say which database: --db <file or postgres://...>, or set DATABASE_URL")
    return storage(where)


def _caps(args: argparse.Namespace, base=None):
    from thespis.storage import Caps
    base = (base or Caps()).to_json()
    given = {k: getattr(args, k) for k in base if getattr(args, k, None) is not None}
    return Caps(**{**base, **given})


def projects(args: argparse.Namespace) -> int:
    if args.action == "secret":
        from thespis.vault import ENV, new_secret
        print(f"{ENV}={new_secret()}")
        return 0
    db = _db(args)
    try:
        if args.action == "list":
            for p in db.projects():
                calls, tokens = db.today(p.id)
                print(f"{p.id:16} {p.name:20} sessions {db.open_sessions(p.id):>4}  today {calls} calls, {tokens} "
                      f"tokens  caps {p.caps.to_json()}")
            return 0
        if not args.name:
            print(f"say which project: projects {args.action} NAME", file=sys.stderr)
            return 2
        if args.action == "create":
            p, key = db.create_project(args.name, _caps(args))
            print(f"created {p.name} ({p.id}). Its key, shown this once:\n{key}")
            return 0
        p = db.project(args.name)
        if p is None:
            print(f"no project {args.name!r}", file=sys.stderr)
            return 1
        if args.action == "key":
            print(f"{p.name}'s new key (the old one no longer works):\n{db.rotate_key(p.id)}")
        elif args.action == "caps":
            caps = _caps(args, p.caps)
            db.set_caps(p.id, caps)
            print(f"{p.name}: {caps.to_json()}")
        elif args.action == "model":
            from thespis.host import SERVER, Host
            from thespis.vault import Vault
            host = Host(db, mode=SERVER, vault=Vault.from_env(), allow_private_models=args.allow_private_models)
            if args.clear:
                host.set_model(p, None)
                print(f"{p.name} speaks through the server's models")
                return 0
            key = os.environ.get(args.key_env, "") if args.key_env else ""
            if args.key_env and not key:
                print(f"{args.key_env} is not set", file=sys.stderr)
                return 1
            primary = {"profile": args.profile or "", "base_url": args.base_url or "", "model": args.model or "",
                       "api_key": key}
            host.set_model(p, {"primary": primary})
            print(f"{p.name} speaks through {args.model} ({args.profile or args.base_url}); key "
                  f"{'kept, sealed' if key else 'none'}")
        return 0
    finally:
        db.close()


def usage(args: argparse.Namespace) -> int:
    import csv
    import datetime as dt

    from thespis.storage import USAGE_FIELDS
    db = _db(args)
    try:
        p = db.project(args.name)
        if p is None:
            print(f"no project {args.name!r}", file=sys.stderr)
            return 1
        since = dt.datetime.fromisoformat(args.since).replace(tzinfo=dt.UTC).timestamp() if args.since else 0
        events = [e.to_json() for e in db.usage(p.id, since, limit=10_000_000)]
    finally:
        db.close()
    out = open(args.out, "w", newline="", encoding="utf-8") if args.out else sys.stdout
    try:
        if args.format == "json":
            json.dump(events, out, indent=1)
            out.write("\n")
        else:
            writer = csv.DictWriter(out, fieldnames=USAGE_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(events)
    finally:
        if args.out:
            out.close()
            print(f"wrote {len(events)} events to {args.out}", file=sys.stderr)
    return 0


def serve(args: argparse.Namespace) -> int:
    import uvicorn

    from thespis import offline, tracing
    from thespis.gateway import gateway_from_env
    from thespis.host import SERVER, SIDECAR, Host
    from thespis.runtime.download import cache_dir
    from thespis.server import create_app
    from thespis.session import Game
    from thespis.storage import storage
    from thespis.vault import Vault

    mode = SERVER if args.server else SIDECAR
    if mode == SIDECAR and not offline.local(args.host):
        print("a sidecar listens on this machine only; use --server to listen elsewhere", file=sys.stderr)
        return 2
    online = args.online or mode == SERVER
    if not online:
        offline.guard()
    games = {g.id: g for g in (Game.load(p) for p in args.game)}
    env = dict(os.environ)
    local = None
    if args.local:
        from thespis.runtime.local import LocalModel
        try:
            local = LocalModel(None if args.local == "auto" else args.local, progress=_progress).start()
        except Exception as e:
            if offline.refused:
                print(f"offline, and the local model isn't here yet ({e}). Fetch it once while online: "
                      f"python -m thespis models pull {args.local}; or pass --online", file=sys.stderr)
                return 1
            raise
        env = {k: v for k, v in env.items() if not k.startswith("LLM_")} | local.env()
        print(f"speaking through {local.plan.describe()} at {local.url}", file=sys.stderr)
    gateway = gateway_from_env(env)
    embed = None
    if args.embed == "local":  # recall by meaning through BGE small, on the CPU beside the chat model
        from thespis.runtime.local import LocalModel
        embed = LocalModel("bge-small", device=None, progress=_progress).start()
        env |= embed.env()
        print(f"recalling through {embed.model.id} at {embed.url}", file=sys.stderr)
    from thespis.recall import embedder_from_env
    embedder = embedder_from_env(env)
    if not online:
        far = [p.name for p in getattr(gateway, "providers", ()) if not offline.local(_hostname(p.base_url))]
        if far:
            print(f"offline: {', '.join(far)} is off this machine, so its lines fall back to templates; pass "
                  f"--online to reach it", file=sys.stderr)
    if mode == SERVER:
        db = storage(args.db or os.environ.get("DATABASE_URL", "") or "")
    else:
        db = storage(args.db or str(cache_dir() / "sidecar.sqlite"))
    host = Host(db, games, gateway, mode=mode, max_sessions=args.max_sessions,
                token=os.environ.get("THESPIS_TOKEN") or None if mode == SIDECAR else None,
                vault=Vault.from_env() if mode == SERVER else None, cache=not args.no_cache,
                allow_private_models=args.allow_private_models, embedder=embedder)
    if tracing.configure():
        print("tracing to $OTEL_EXPORTER_OTLP_ENDPOINT", file=sys.stderr)

    family = socket.AF_INET6 if ":" in args.host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.bind((args.host, args.port))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(host=host), log_level="warning", access_log=False, ws="none",
                                           lifespan="off"))
    if args.parent:
        from thespis.runtime.local import watch_parent

        def gone() -> None:
            server.should_exit = True
        watch_parent(args.parent, gone)
    shown = f"[{args.host}]" if family == socket.AF_INET6 else args.host
    print(f"THESPIS_URL=http://{shown}:{port}", flush=True)
    print(f"{mode} on {shown}:{port}, {'online' if online else 'offline'}, sessions in "
          f"{getattr(db, 'path', 'postgres')}", file=sys.stderr, flush=True)
    try:
        server.run(sockets=[sock])
    finally:
        host.shutdown()
        if local:
            local.stop()
        if embed:
            embed.stop()
        if offline.refused:
            print(f"offline, refused {len(offline.refused)}: {'; '.join(sorted(set(offline.refused)))}",
                  file=sys.stderr)
    return 0


def _hostname(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).hostname or ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="thespis")
    sub = parser.add_subparsers(dest="command", required=True)
    serve_p = sub.add_parser("serve", help="serve the /v1 API: a sidecar, or with --server a server")
    serve_p.add_argument("--game", action="append", default=[], help="a game.toml every project can play (repeatable)")
    serve_p.add_argument("--server", action="store_true", help="many projects, each calling with its own key")
    serve_p.add_argument("--db", help="sessions go here: a SQLite file, :memory:, or postgres://...")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=7878, help="0 picks a free one (printed as THESPIS_URL)")
    serve_p.add_argument("--local", nargs="?", const="auto", help="speak through a local model: auto, or a model id")
    serve_p.add_argument("--online", action="store_true", help="a sidecar may use the network")
    serve_p.add_argument("--embed", choices=["local"], help="recall by meaning through a local embedding model "
                                                            "(else EMBED_* if set)")
    serve_p.add_argument("--parent", type=int, help="stop when this process ends")
    serve_p.add_argument("--max-sessions", type=int, default=256, help="a sidecar's open sessions at most")
    serve_p.add_argument("--no-cache", action="store_true", help="don't reuse model replies")
    serve_p.add_argument("--allow-private-models", action="store_true",
                         help="a server lets projects use model endpoints on its own network, or plain http")
    proj = sub.add_parser("projects", help="a server's projects")
    proj.add_argument("action", choices=["create", "list", "key", "caps", "model", "secret"])
    proj.add_argument("name", nargs="?")
    proj.add_argument("--db", help="the server's database (default $DATABASE_URL)")
    for cap in ("max_sessions", "calls_per_day", "tokens_per_day", "max_games"):
        proj.add_argument(f"--{cap.replace('_', '-')}", dest=cap, type=int)
    proj.add_argument("--profile", help="model: a provider profile")
    proj.add_argument("--base-url", help="model: the endpoint, if not the profile's")
    proj.add_argument("--model", help="model: which model")
    proj.add_argument("--key-env", help="model: the environment variable holding its API key")
    proj.add_argument("--clear", action="store_true", help="model: forget the project's models")
    proj.add_argument("--allow-private-models", action="store_true")
    use = sub.add_parser("usage", help="export a project's usage events")
    use.add_argument("name")
    use.add_argument("--db")
    use.add_argument("--since", help="a date or time, UTC: 2026-10-01")
    use.add_argument("--format", choices=["csv", "json"], default="csv")
    use.add_argument("--out")
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
    if args.command == "projects":
        return projects(args)
    if args.command == "usage":
        return usage(args)
    return serve(args)


if __name__ == "__main__":
    raise SystemExit(main())
