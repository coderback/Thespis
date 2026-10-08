"""Build the runtime a game ships beside it: `thespis` as one executable in one folder, zipped as one archive per
platform, with PyInstaller. Then check it against its budgets and play a turn through it.

    python tools/package.py                 # build dist/thespis-<os>-<arch>.zip and check it
    python tools/package.py --no-build      # check the build that's there

One folder, not one file: PyInstaller's one-file build unpacks itself on every start, which took a sidecar's cold
start on Windows from 2.1 s to 4.7 s, and it runs as a launcher with a child, so a game that stops the launcher
leaves the child running. The one-folder build starts as fast as Python does and is a single process.

What it leaves out: Postgres, the vault and the OpenTelemetry SDK, which only a server needs (servers run from the
image, docker/serve.Dockerfile), and the websocket and file-watching parts of uvicorn, which /v1 doesn't use.

Budgets, checked on every platform in CI:
  - the archive at most SIZE_MB;
  - cold start, from launch to /v1/health answering, at most COLD_S (the median of three starts after a first, so
    it measures the runtime, not the first scan by an antivirus).
"""

from __future__ import annotations

import argparse
import http.client
import json
import platform
import shutil
import statistics
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build" / "pyinstaller"
SIZE_MB = 25.0
COLD_S = 4.0
EXCLUDE = ["psycopg", "psycopg_pool", "psycopg_binary", "cryptography", "opentelemetry.sdk", "tkinter", "pytest",
           "numpy", "websockets", "watchfiles", "_pytest", "pyright", "ruff"]
GAME = ROOT / "examples" / "tavern" / "game.toml"


def platform_name() -> str:
    os_name = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine().lower(),
                                                                                          platform.machine().lower())
    return f"{os_name}-{arch}"


def build() -> Path:
    entry = BUILD / "entry.py"
    BUILD.mkdir(parents=True, exist_ok=True)
    entry.write_text("from thespis.__main__ import main\n\nraise SystemExit(main())\n", encoding="utf-8")
    args = [sys.executable, "-m", "PyInstaller", "--onedir", "--name", "thespis", "--paths", str(ROOT),
            "--distpath", str(DIST), "--workpath", str(BUILD / "work"), "--specpath", str(BUILD), "--noconfirm",
            "--log-level", "ERROR", *[a for m in EXCLUDE for a in ("--exclude-module", m)],
            # Linux's shared libraries carry their debug symbols; stripped, the archive halves. (macOS signs its
            # binaries, and stripping after would break the signature; Windows has nothing to strip.)
            *(["--strip"] if sys.platform.startswith("linux") else []), str(entry)]
    subprocess.run(args, check=True, cwd=ROOT)
    folder = DIST / "thespis"
    archive = DIST / f"thespis-{platform_name()}.zip"
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(folder.rglob("*")):
            z.write(f, Path("thespis") / f.relative_to(folder))
    return archive


def executable() -> Path:
    return DIST / "thespis" / ("thespis.exe" if sys.platform == "win32" else "thespis")


def get(url: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    host, port = url.removeprefix("http://").rsplit(":", 1)
    c = http.client.HTTPConnection(host, int(port), timeout=10)
    c.request("POST" if body is not None else "GET", path, json.dumps(body) if body is not None else None,
              {"Content-Type": "application/json"})
    r = c.getresponse()
    data = r.read()
    return r.status, json.loads(data) if data else {}


def start(exe: Path) -> tuple[subprocess.Popen, str, float]:
    started = time.perf_counter()
    proc = subprocess.Popen([str(exe), "serve", "--port", "0", "--db", ":memory:", "--game", str(GAME)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.stdout is not None
    url = proc.stdout.readline().strip().partition("=")[2]
    if not url:
        raise SystemExit(f"the runtime didn't start:\n{proc.stderr.read() if proc.stderr else ''}")
    while time.perf_counter() - started < 60:
        try:
            if get(url, "/v1/health")[0] == 200:
                return proc, url, time.perf_counter() - started
        except OSError:
            time.sleep(0.01)
    proc.kill()
    raise SystemExit("the runtime never answered /v1/health")


def stop(proc: subprocess.Popen) -> None:
    proc.kill()
    proc.wait(timeout=10)


def check(archive: Path) -> dict:
    exe = executable()
    size = archive.stat().st_size / 1e6
    starts = []
    for _ in range(4):
        proc, url, seconds = start(exe)
        starts.append(seconds)
        stop(proc)
    cold = statistics.median(starts[1:])
    proc, url, _ = start(exe)
    try:
        status, s = get(url, "/v1/sessions", {"game": "tavern"})
        assert status == 201, s
        sid = s["session"]
        status, _ = get(url, f"/v1/sessions/{sid}/observe", {
            "verb": "insult", "actor": "player", "target": "garrick", "witnesses": ["wren"],
            "claim": {"pred": "insulted", "a": "player", "b": "garrick"}})
        assert status == 201
        status, line = get(url, f"/v1/sessions/{sid}/decide", {"npc": "garrick", "moment": "turn"})
        assert status == 200 and line["text"], line
    finally:
        stop(proc)
    largest = sorted((f for f in (DIST / "thespis").rglob("*") if f.is_file()), key=lambda f: -f.stat().st_size)[:8]
    result = {"platform": platform_name(), "archive_mb": round(size, 1), "size_budget_mb": SIZE_MB,
              "cold_start_s": round(cold, 2), "first_start_s": round(starts[0], 2), "cold_budget_s": COLD_S,
              "played": f"garrick: {line['action']}, {line['text']!r}",
              "largest_mb": {str(f.relative_to(DIST / "thespis")): round(f.stat().st_size / 1e6, 1) for f in largest}}
    result["ok"] = size <= SIZE_MB and cold <= COLD_S
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-build", action="store_true", help="check the build already in dist/")
    args = parser.parse_args()
    if args.no_build:
        archive = DIST / f"thespis-{platform_name()}.zip"
    else:
        shutil.rmtree(DIST / "thespis", ignore_errors=True)
        archive = build()
    result = check(archive)
    print(json.dumps(result, indent=1))
    if not result["ok"]:
        print(f"over budget: at most {SIZE_MB} MB and {COLD_S} s", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
