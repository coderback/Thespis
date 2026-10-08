"""A local model: llama.cpp's server running a registry model on this machine, for as long as the game runs.

`LocalModel` fetches what it needs (thespis.runtime.download), starts `llama-server` on a free localhost port with
thinking off and the chosen device, waits until the model is loaded, and warms it with one tiny call so the first
real line doesn't pay for loading. Its URL is an OpenAI-compatible endpoint: point the `llamacpp` profile at it.

The server lives and dies with the process that started it. On Windows it joins a job object that kills it when the
last handle closes; on Linux the kernel signals it when its parent dies. macOS has neither, so there it stops when
the parent exits normally, and an orphan from a crash must be stopped by hand.
"""

from __future__ import annotations

import atexit
import ctypes
import os
import socket
import subprocess
import sys
import tarfile
import threading
import time
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import IO

import httpx

from thespis.runtime.download import Progress, cache_dir, fetch
from thespis.runtime.hardware import Device, Plan, choose, machine, this_arch, this_os
from thespis.runtime.registry import ENGINES, LLAMA_CPP, MODELS

READY_TIMEOUT = 300.0  # seconds to load a model: a cold disk and a large file on a laptop
CACHE_RAM_MB = 512  # llama-server's prompt cache in RAM (its default, 8 GiB, starved a 15 GB laptop)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def engine(accelerator: str, progress: Progress | None = None) -> Path:
    """The pinned llama.cpp build's server for this platform and accelerator, fetched and unpacked if need be."""
    key = (this_os(), this_arch(), accelerator)
    if key not in ENGINES:
        raise RuntimeError(f"no llama.cpp build for {key}; available: {sorted(ENGINES)}")
    a = ENGINES[key]
    home = cache_dir() / "engines"
    unpacked = home / f"{LLAMA_CPP}-{'-'.join(key)}"
    exe = "llama-server.exe" if key[0] == "windows" else "llama-server"
    found = next(unpacked.rglob(exe), None) if unpacked.exists() else None
    if found:
        return found
    archive = fetch(a, home / a.name, progress)
    unpacked.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(unpacked)
    else:
        with tarfile.open(archive) as t:
            t.extractall(unpacked, filter="data")
    found = next(unpacked.rglob(exe), None)
    if found is None:
        raise RuntimeError(f"{a.name} has no {exe}")
    found.chmod(found.stat().st_mode | 0o111)
    return found


def model_file(model: str, progress: Progress | None = None) -> Path:
    a = MODELS[model].artifact
    return fetch(a, cache_dir() / "models" / a.name, progress)


# ---------------------------------------------------------------- lifetime
_JOB = None  # Windows: one job for every server this process starts; closing it (at exit, or a crash) kills them


def _windows_job():
    global _JOB
    if _JOB is None:
        from ctypes import wintypes

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", ctypes.c_uint64 * 6),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        job = k32.CreateJobObjectW(None, None)
        info = Extended()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise OSError("SetInformationJobObject failed")
        _JOB = job
    return _JOB


def _linux_pdeathsig() -> None:  # runs in the child, before exec
    import signal
    ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG


def watch_parent(pid: int, gone: Callable[[], None]) -> threading.Thread:
    """Call `gone` once process `pid` (the game that started this one) has ended, whatever ended it. The other side
    of `spawn`: a sidecar started by an engine stops with it, even if the engine is killed."""
    def wait() -> None:
        if sys.platform == "win32":
            from ctypes import wintypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.OpenProcess.restype = wintypes.HANDLE
            handle = k32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
            if handle:
                k32.WaitForSingleObject(wintypes.HANDLE(handle), 0xFFFFFFFF)  # INFINITE
                k32.CloseHandle(wintypes.HANDLE(handle))
        else:
            while True:
                try:
                    os.kill(pid, 0)  # POSIX: signal 0 only asks whether it exists
                except ProcessLookupError:
                    break
                except PermissionError:
                    pass
                time.sleep(1)
        gone()
    t = threading.Thread(target=wait, name="thespis-parent", daemon=True)
    t.start()
    return t


def spawn(args: Sequence[str], log: IO[bytes] | int = subprocess.DEVNULL) -> subprocess.Popen:
    """Start a process that dies with this one (see the module's docstring for macOS)."""
    if sys.platform == "win32":
        proc = subprocess.Popen(list(args), stdout=log, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        if not k32.AssignProcessToJobObject(ctypes.c_void_p(_windows_job()),
                                            ctypes.c_void_p(int(proc._handle))):  # type: ignore[attr-defined]
            proc.kill()
            raise OSError("AssignProcessToJobObject failed")
        return proc
    if sys.platform.startswith("linux"):
        return subprocess.Popen(list(args), stdout=log, stderr=subprocess.STDOUT, preexec_fn=_linux_pdeathsig)
    return subprocess.Popen(list(args), stdout=log, stderr=subprocess.STDOUT)


# ---------------------------------------------------------------- the server
def plan_for(model: str, device: Device | None) -> Plan:
    return Plan(model, device, device is not None and MODELS[model].vram_gb * 1024 <= device.free_mb)


class LocalModel:
    """llama.cpp's server on one model. Use as a context manager, or call start() and stop()."""

    def __init__(self, model: str | None = None, device: str | None = "auto", ctx: int | None = None,
                 parallel: int = 2, port: int | None = None, progress: Progress | None = None):
        """`model` is a registry id, or None for the hardware's choice. `device` is "auto" (the best GPU), a
        llama.cpp device id ("Vulkan1"), or None for the CPU."""
        self.progress = progress
        # The Vulkan build runs on the CPU too when there's no GPU, so one build serves every Windows and Linux machine.
        self.server = engine("metal" if this_os() == "macos" else "vulkan", progress)
        self.machine = m = machine(self.server)
        if device == "auto":
            plan = choose(m) if model is None else plan_for(model, m.gpu)
        else:
            dev = None if device is None else next((d for d in m.devices if d.id == device), None)
            if device is not None and dev is None:
                raise ValueError(f"no device {device!r}; this machine has {[d.id for d in m.devices]}")
            plan = plan_for(model or choose(m).model, dev)
        self.plan = plan
        self.model = MODELS[plan.model]
        self.ctx = ctx or self.model.ctx
        self.parallel = parallel
        self.port = port or free_port()
        self.proc: subprocess.Popen | None = None
        self.log_path = cache_dir() / "logs" / f"llama-server-{self.port}.log"
        self.load_seconds: float | None = None

    @property
    def url(self) -> str:
        """The OpenAI-compatible base URL."""
        return f"http://127.0.0.1:{self.port}/v1"

    def args(self, path: Path) -> list[str]:
        """llama-server's arguments. A model that fits goes wholly on the GPU (-ngl 99): on a 4 GB laptop GPU that
        processed prompts 75 times faster than llama.cpp's own --fit, which held back layers for safety, and loaded
        in 18 s rather than 162 s. One that doesn't fit is placed by --fit."""
        dev = self.plan.device
        # --cache-ram: llama-server keeps past prompts in RAM to reuse their prefixes, up to 8 GiB by default. Over a
        # live Rehearsal it grew to 7.5 GB on a 15 GB laptop and starved the machine; a game needs that memory.
        args = [str(self.server), "-m", str(path), "--host", "127.0.0.1", "--port", str(self.port),
                "-c", str(self.ctx * self.parallel), "-np", str(self.parallel), "--reasoning", "off", "--no-webui",
                "--cache-ram", str(CACHE_RAM_MB)]
        if self.model.kind == "embed":
            args += ["--embedding"]  # /v1/embeddings, pooled as the model was trained (BGE: its CLS token)
        if self.machine.os != "macos":
            if dev is None:
                args += ["-dev", "none", "-ngl", "0"]
            else:
                args += ["-dev", dev.id] + (["-ngl", "99"] if self.plan.whole else ["--fit", "on"])
        return args

    def start(self) -> LocalModel:
        path = model_file(self.model.id, self.progress)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        atexit.register(self.stop)
        try:
            self._launch(path)
        except RuntimeError:
            if not self.plan.whole:
                raise
            # The whole model didn't fit after all (another program took GPU memory): let llama.cpp place it.
            self.plan = Plan(self.plan.model, self.plan.device, False)
            self._launch(path)
        self.load_seconds = time.perf_counter() - started
        self.warm()
        return self

    def _launch(self, path: Path) -> None:
        with self.log_path.open("ab") as log:
            self.proc = spawn(self.args(path), log)
        try:
            self._wait_ready()
        except Exception:
            self.stop()
            raise

    def _wait_ready(self) -> None:
        deadline = time.monotonic() + READY_TIMEOUT
        while time.monotonic() < deadline:
            if self.proc is None or self.proc.poll() is not None:
                raise RuntimeError(f"llama-server exited while loading; see {self.log_path}:\n{self.log_tail()}")
            try:
                if httpx.get(f"http://127.0.0.1:{self.port}/health", timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        raise TimeoutError(f"{self.model.id} wasn't ready in {READY_TIMEOUT:.0f} s; see {self.log_path}")

    def warm(self) -> None:
        """Calls shaped like play's, small to large, so the first real lines don't pay for first use. On Vulkan
        that cost is real: a GPU compiles its kernels for each new size of prompt it meets, and in live Rehearsal the
        first lines of a run met them at 1 to 3 tokens a second, 14 to 32 seconds a call, where warm ones ran at 755.
        A two-word warm-up never reached those sizes. An embedding model embeds one short text."""
        if self.model.kind == "embed":
            httpx.post(f"{self.url}/embeddings", timeout=60, json={"model": self.model.id, "input": ["warm"]})
            return
        schema = {"type": "object", "required": ["cites", "line"], "additionalProperties": False,
                  "properties": {"cites": {"type": "array", "minItems": 1, "items": {"type": "string",
                                                                                    "enum": ["e1", "e2"]}},
                                 "line": {"type": "string", "maxLength": 160}}}
        event = "e{}: Someone walked from the market to the tavern, where the innkeeper was polishing the bar. "
        for n in (2, 12, 40):  # roughly 60, 300 and 900 prompt tokens: a short reply, a state pack, a long one
            content = "".join(event.format(i) for i in range(1, n + 1)) + "Say one line, citing an event."
            httpx.post(f"{self.url}/chat/completions", timeout=180, json={
                "model": self.model.id, "max_tokens": 24, "messages": [{"role": "user", "content": content}],
                "response_format": {"type": "json_schema", "json_schema": {"name": "warm", "schema": schema}}})

    def log_tail(self, n: int = 20) -> str:
        try:
            return "\n".join(self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
        except OSError:
            return ""

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def env(self, prefix: str = "LLM_") -> dict[str, str]:
        """The settings that point the gateway at this server; for an embedding model, recall (EMBED_*)."""
        if self.model.kind == "embed":
            return {"EMBED_BASE_URL": self.url, "EMBED_MODEL": self.model.id}
        return {f"{prefix}PROFILE": "llamacpp", f"{prefix}BASE_URL": self.url, f"{prefix}MODEL": self.model.id}

    def __enter__(self) -> LocalModel:
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
