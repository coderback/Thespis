"""The local runtime (thespis.runtime): checked, resumable downloads; choosing a tier and a device from the hardware;
llama.cpp's arguments; and a server that dies with the process that started it."""

import hashlib
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from thespis.runtime.download import ChecksumError, fetch
from thespis.runtime.hardware import Device, Machine, choose, parse_devices
from thespis.runtime.local import LocalModel, plan_for
from thespis.runtime.registry import ENGINES, MODELS, TIERS, Artifact

DATA = bytes(range(256)) * 400  # 100 KiB
GOOD = Artifact("https://models.test/m.gguf", hashlib.sha256(DATA).hexdigest(), len(DATA))


def server(data: bytes = DATA, ranges: bool = True, log: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        rng = request.headers.get("range")
        if log is not None:
            log.append(rng)
        if rng and ranges:
            start = int(rng.split("=")[1].rstrip("-"))
            return httpx.Response(206, content=data[start:])
        return httpx.Response(200, content=data)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_a_download_is_checked_and_renamed_into_place(tmp_path):
    dest = tmp_path / "m.gguf"
    assert fetch(GOOD, dest, client=server()) == dest
    assert dest.read_bytes() == DATA and not (tmp_path / "m.gguf.part").exists()
    log = []
    fetch(GOOD, dest, client=server(log=log))
    assert log == []  # whole already: nothing fetched


def test_an_interrupted_download_resumes_where_it_stopped(tmp_path):
    (tmp_path / "m.gguf.part").write_bytes(DATA[:30000])
    log = []
    fetch(GOOD, tmp_path / "m.gguf", client=server(log=log))
    assert log == ["bytes=30000-"] and (tmp_path / "m.gguf").read_bytes() == DATA


def test_a_dropped_connection_resumes_by_itself(tmp_path, monkeypatch):
    monkeypatch.setattr("thespis.runtime.download.time.sleep", lambda s: None)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers.get("range"))
        if len(calls) == 1:
            return httpx.Response(200, stream=Dropping(DATA[:40000]))
        start = int(request.headers["range"].split("=")[1].rstrip("-"))
        return httpx.Response(206, content=DATA[start:])

    fetch(GOOD, tmp_path / "m.gguf", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert calls == [None, "bytes=40000-"] and (tmp_path / "m.gguf").read_bytes() == DATA


class Dropping(httpx.SyncByteStream):
    """Some bytes, then the connection drops."""

    def __init__(self, data: bytes):
        self.data = data

    def __iter__(self):
        yield self.data
        raise httpx.ReadTimeout("the read operation timed out")


def test_a_server_that_ignores_the_range_starts_it_again(tmp_path):
    (tmp_path / "m.gguf.part").write_bytes(DATA[:30000])
    fetch(GOOD, tmp_path / "m.gguf", client=server(ranges=False))
    assert (tmp_path / "m.gguf").read_bytes() == DATA


def test_a_file_that_fails_its_checksum_is_never_used(tmp_path):
    with pytest.raises(ChecksumError, match="partial download was deleted"):
        fetch(GOOD, tmp_path / "m.gguf", client=server(data=DATA[:-1] + b"x"))
    assert list(tmp_path.iterdir()) == []


def test_every_registry_file_is_pinned():
    for a in [m.artifact for m in MODELS.values()] + list(ENGINES.values()):
        assert a.url.startswith("https://") and len(a.sha256) == 64 and a.size > 0
    assert set(TIERS) <= set(MODELS)


LISTED = """Available devices:
  Vulkan0: AMD Radeon(TM) Graphics (8110 MiB, 7704 MiB free)
  Vulkan1: NVIDIA GeForce RTX 3050 Ti Laptop GPU (3962 MiB, 3367 MiB free)
"""


def test_a_discrete_gpu_is_preferred_whatever_its_order():
    m = Machine("windows", "x64", 15.3, parse_devices(LISTED))
    assert [d.integrated for d in m.devices] == [True, False]
    assert m.gpu is not None and m.gpu.id == "Vulkan1" and m.accelerator == "vulkan"


TWO = ("qwen3.5-4b", "qwen3.5-9b")  # two tiers, to show how the choice works


@pytest.mark.parametrize("free_mb, ram, expected", [
    (12000, 32, ("qwen3.5-9b", True)),  # the largest tier that fits whole
    (3367, 15.3, ("qwen3.5-4b", True)),  # a 4 GB laptop GPU with the desktop's share taken
    (2500, 15.3, ("qwen3.5-4b", False)),  # nothing fits whole: the smallest, partly in RAM
])
def test_the_tier_is_the_largest_that_fits_and_speed_wins_otherwise(free_mb, ram, expected):
    plan = choose(Machine("linux", "x64", ram, (Device("Vulkan0", "NVIDIA RTX", free_mb, free_mb),)), TWO)
    assert (plan.model, plan.whole) == expected and plan.device is not None


def test_with_no_gpu_it_runs_the_smallest_tier_on_the_cpu():
    plan = choose(Machine("linux", "x64", 8, ()), TWO)
    assert (plan.model, plan.device) == ("qwen3.5-4b", None)


def test_the_measured_tier_is_the_default():
    plan = choose(Machine("windows", "x64", 15.3, parse_devices(LISTED)))
    assert (plan.model, plan.whole, plan.device and plan.device.id) == ("gemma4-e4b", True, "Vulkan1")


def bare(device: Device | None, os: str = "windows") -> LocalModel:
    lm = LocalModel.__new__(LocalModel)
    lm.server, lm.port, lm.parallel = "llama-server", 9999, 2
    lm.machine = Machine(os, "x64", 16, ())
    lm.plan = plan_for("qwen3.5-4b", device)
    lm.model, lm.ctx = MODELS["qwen3.5-4b"], 8192
    return lm


def test_the_server_runs_on_the_chosen_device_with_thinking_off():
    args = bare(Device("Vulkan1", "NVIDIA", 4000, 3367)).args(Path("m.gguf"))  # it fits: every layer on the GPU
    assert args[args.index("-dev") + 1] == "Vulkan1" and args[args.index("-ngl") + 1] == "99"
    assert args[args.index("--reasoning") + 1] == "off" and args[args.index("-c") + 1] == "16384"
    assert args[args.index("--cache-ram") + 1] == "512"  # not llama-server's 8 GiB beside a game
    tight = bare(Device("Vulkan1", "NVIDIA", 4000, 2000)).args(Path("m.gguf"))  # it doesn't: llama.cpp places it
    assert "--fit" in tight and "-ngl" not in tight
    cpu = bare(None).args(Path("m.gguf"))
    assert cpu[cpu.index("-dev") + 1] == "none" and cpu[cpu.index("-ngl") + 1] == "0"
    assert "-dev" not in bare(None, os="macos").args(Path("m.gguf"))  # Metal: llama.cpp chooses


PARENT = """
import subprocess, sys, time
from thespis.runtime.local import spawn
child = spawn([sys.executable, "-c", "import time; time.sleep(60)"])
print(child.pid, flush=True)
time.sleep(60)
"""


def alive(pid: int) -> bool:
    if sys.platform == "win32":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        import os
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@pytest.mark.skipif(sys.platform == "darwin", reason="macOS has no way to tie a child to its parent's life")
def test_the_server_dies_with_the_process_that_started_it():
    parent = subprocess.Popen([sys.executable, "-c", PARENT], stdout=subprocess.PIPE, text=True)
    assert parent.stdout is not None
    child = int(parent.stdout.readline())
    assert alive(child)
    parent.kill()  # a crash: no atexit, no cleanup
    parent.wait(10)
    for _ in range(50):
        if not alive(child):
            break
        time.sleep(0.1)
    assert not alive(child)
