"""Play the Godot addon's example scene headless, once per way of running Thespis, with the scene unchanged.

    python sdk/godot/test/run.py --godot <path to Godot 4's console build>          # sidecar, then server
    python sdk/godot/test/run.py --godot <...> --mode sidecar --local gemma4-e4b    # the offline gate
    python sdk/godot/test/run.py --godot <...> --mode sidecar --exe dist/thespis/thespis.exe

- **sidecar:** the addon starts `thespis serve` itself, on this machine and offline, as a shipped game would.
- **server:** a hosted-mode server (`thespis serve --server`) with a project and its key. The scene finds it through
  THESPIS_URL and THESPIS_KEY, and sends it the game, which a server doesn't have until a project sends it.

By default the model is scripted (sdk/harness.py). With `--local`, the sidecar speaks through a local model instead
(thespis.runtime), and the run passes only if the sidecar refused nothing off this machine. `--exe` has the addon
start the packaged runtime (tools/package.py) instead of Python. Exits 0 when every run passed.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness import ROOT, base_env, hosted_server, scripted_model, sidecar_command  # noqa: E402

PROJECT = ROOT / "sdk" / "godot"


def godot(exe: str, env: dict[str, str], timeout: float) -> int:
    """Import the project (so the addon's classes are known), then play the example under the test script."""
    subprocess.run([exe, "--headless", "--path", str(PROJECT), "--import"], env=env, capture_output=True,
                   timeout=300)
    run = subprocess.run([exe, "--headless", "--path", str(PROJECT), "--script", "res://test/example_test.gd"],
                         env=env | {"THESPIS_TEST_TIMEOUT": str(timeout)}, cwd=ROOT, timeout=timeout + 60)
    return run.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--godot", default=os.environ.get("GODOT", ""), help="Godot 4's console build ($GODOT)")
    parser.add_argument("--mode", choices=["both", "sidecar", "server"], default="both")
    parser.add_argument("--local", help="the sidecar speaks through this local model, offline (e.g. gemma4-e4b)")
    parser.add_argument("--exe", help="the packaged runtime for the addon to start instead of python -m thespis")
    args = parser.parse_args()
    if not args.godot:
        parser.error("say where Godot is: --godot <path> or GODOT=<path>")
    if args.local and args.mode != "sidecar":
        parser.error("--local is for the sidecar: add --mode sidecar")

    with scripted_model() if not args.local else contextlib.nullcontext({}) as model:
        env = base_env() | model
        codes = []
        if args.mode in ("both", "sidecar"):
            print("== sidecar: the addon starts the runtime itself")
            run = env | {"THESPIS_EXPECT": "sidecar", "THESPIS_SIDECAR": sidecar_command(args.exe)}
            if args.local:
                run["THESPIS_TEST_MODEL"] = args.local
            codes.append(godot(args.godot, run, 240.0 if args.local else 60.0))
        if args.mode in ("both", "server"):
            print("== server: hosted mode, with a project and its key")
            with hosted_server(env) as server:
                codes.append(godot(args.godot, env | server | {"THESPIS_EXPECT": "server"}, 60.0))
        return next((c for c in codes if c), 0)


if __name__ == "__main__":
    raise SystemExit(main())
