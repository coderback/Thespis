"""Play the Unity package's Lantern example, once per way of running Thespis, with the game unchanged.

    python sdk/unity/test/run.py                                   # .NET: the core and the game, sidecar then server
    python sdk/unity/test/run.py --unity <Unity.exe>               # and the scene in Unity, in batch mode
    python sdk/unity/test/run.py --runner unity --unity <...> --mode sidecar --local gemma4-e4b   # offline

Two runners play the same game (sdk/unity/Lantern/Assets/Lantern/LanternGame.cs):
- **dotnet:** the package's core built as Unity builds it (netstandard2.1, C# 9) and the game, under plain .NET
  (sdk/unity/dotnet). It needs only the .NET SDK, so CI runs it.
- **unity:** the Lantern project in the Unity editor, in batch mode: its play-mode test loads the scene and plays it
  through the ThespisBehaviour component, checking what the screen shows too. It needs a licensed editor.

Each plays against a sidecar the client starts itself and against a hosted-mode server with a project key
(sdk/harness.py), with a scripted model unless `--local` names a local one. Exits 0 when every run passed.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness import ROOT, TAVERN, base_env, hosted_server, scripted_model, sidecar_command  # noqa: E402

UNITY = ROOT / "sdk" / "unity"
CHECK = UNITY / "dotnet" / "Check" / "Lantern.Check.csproj"
PROJECT = UNITY / "Lantern"


def dotnet() -> str:
    found = shutil.which("dotnet") or next((str(p) for p in [Path(r"C:\Program Files\dotnet\dotnet.exe")]
                                             if p.exists()), "")
    if not found:
        raise SystemExit("no .NET SDK: install it, or put dotnet on PATH")
    return found


def run_dotnet(env: dict[str, str]) -> int:
    exe = dotnet()
    built = subprocess.run([exe, "build", str(CHECK), "-v", "q", "-nologo"], env=env, capture_output=True, text=True)
    if built.returncode:
        print(built.stdout[-3000:], built.stderr[-2000:])
        return built.returncode
    return subprocess.run([exe, "run", "--no-build", "--project", str(CHECK)],
                          env=env | {"THESPIS_GAME": str(TAVERN)}, cwd=ROOT, timeout=600).returncode


def run_unity(unity: str, env: dict[str, str]) -> int:
    """The play-mode tests in batch mode; their results file says what passed."""
    out = Path(env.get("TEMP", "/tmp")) / f"thespis-unity-{env['THESPIS_EXPECT']}.xml"
    log = out.with_suffix(".log")
    out.unlink(missing_ok=True)
    headless = ["-nographics"] if sys.platform != "win32" else []  # a CI runner has no display
    code = subprocess.run([unity, "-batchmode", *headless, "-projectPath", str(PROJECT), "-runTests", "-testPlatform",
                           "PlayMode", "-testResults", str(out), "-logFile", str(log)], env=env, timeout=1800).returncode
    if not out.exists():
        print(f"Unity wrote no results (exit {code}); its log: {log}")
        print(log.read_text(encoding="utf-8", errors="replace")[-4000:] if log.exists() else "")
        return code or 1
    run = ET.parse(out).getroot()
    for case in run.iter("test-case"):
        print(f"  {'ok  ' if case.get('result') == 'Passed' else 'FAIL'} {case.get('name')}")
        for line in (case.findtext("output") or "").splitlines():
            print(f"       {line}")
        failure = case.find("failure")
        if failure is not None:
            print(f"       {(failure.findtext('message') or '').strip()}")
    print(f"{run.get('passed')} passed, {run.get('failed')} failed")
    return 0 if run.get("result", "").startswith("Passed") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runner", choices=["all", "dotnet", "unity"], default="all")
    parser.add_argument("--unity", default=os.environ.get("UNITY", ""), help="the Unity editor ($UNITY)")
    parser.add_argument("--mode", choices=["both", "sidecar", "server"], default="both")
    parser.add_argument("--local", help="the sidecar speaks through this local model, offline (e.g. gemma4-e4b)")
    parser.add_argument("--exe", help="the packaged runtime for the client to start instead of python -m thespis")
    args = parser.parse_args()
    runners = ["dotnet", "unity"] if args.runner == "all" else [args.runner]
    if "unity" in runners and not args.unity:
        if args.runner == "unity":
            parser.error("say where Unity is: --unity <path> or UNITY=<path>")
        runners.remove("unity")
    if args.local and args.mode != "sidecar":
        parser.error("--local is for the sidecar: add --mode sidecar")

    def play(runner: str, env: dict[str, str]) -> int:
        return run_dotnet(env) if runner == "dotnet" else run_unity(args.unity, env)

    codes = []
    with scripted_model() if not args.local else contextlib.nullcontext({}) as model:
        env = base_env() | model
        for runner in runners:
            if args.mode in ("both", "sidecar"):
                print(f"== {runner}, sidecar: the client starts the runtime itself")
                run = env | {"THESPIS_EXPECT": "sidecar", "THESPIS_SIDECAR": sidecar_command(args.exe)}
                if args.local:
                    run["THESPIS_MODEL"] = args.local
                codes.append(play(runner, run))
            if args.mode in ("both", "server"):
                print(f"== {runner}, server: hosted mode, with a project and its key")
                with hosted_server(env) as server:
                    codes.append(play(runner, env | server | {"THESPIS_EXPECT": "server"}))
    return next((c for c in codes if c), 0)


if __name__ == "__main__":
    raise SystemExit(main())
