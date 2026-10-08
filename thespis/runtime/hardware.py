"""What this machine can run: its memory, its GPUs, and the model tier and device to run on.

GPUs come from llama.cpp itself (`llama-server --list-devices`), so what the probe sees is what the runtime will use.
An integrated GPU reports shared system memory as its own (an AMD laptop's "Radeon(TM) Graphics" lists 8 GB), so
the probe tells integrated from discrete by name and prefers a discrete one, whatever order the devices come in.

The choice: the largest tier that fits wholly in the best GPU's free memory; failing that, the smallest tier, with
llama.cpp fitting what it can onto the GPU and the rest in RAM; with no usable GPU, the smallest tier on the CPU.
Speed decides over size because a player is waiting for every line.
"""

from __future__ import annotations

import ctypes
import os
import platform
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from thespis.runtime.registry import MODELS, TIERS

_DEVICE = re.compile(r"^\s*(\w+\d+):\s*(.+?)\s*\((\d+) MiB,\s*(\d+) MiB free\)", re.M)
_INTEGRATED = re.compile(r"Radeon\(TM\) Graphics|Radeon Graphics|Vega \d+ Graphics|Intel\(R\) (UHD|HD|Iris|Arc\(TM\) "
                         r"Graphics)|Intel\(R\) Graphics|llvmpipe", re.I)


@dataclass(frozen=True)
class Device:
    id: str  # llama.cpp's name for it: "Vulkan1", "CUDA0", "Metal"
    name: str
    total_mb: int
    free_mb: int

    @property
    def integrated(self) -> bool:
        return bool(_INTEGRATED.search(self.name))


@dataclass(frozen=True)
class Machine:
    os: str  # windows, linux or macos
    arch: str  # x64 or arm64
    ram_gb: float
    devices: tuple[Device, ...] = ()

    @property
    def accelerator(self) -> str:
        """Which llama.cpp build to run: Metal on a Mac, Vulkan where there's a GPU, else the CPU build."""
        if self.os == "macos":
            return "metal"
        return "vulkan" if self.gpu else "cpu"

    @property
    def gpu(self) -> Device | None:
        """The GPU to run on: a discrete one with the most free memory, or, failing that, an integrated one."""
        ranked = sorted(self.devices, key=lambda d: (not d.integrated, d.free_mb), reverse=True)
        return ranked[0] if ranked else None


@dataclass(frozen=True)
class Plan:
    model: str
    device: Device | None  # None: the CPU
    whole: bool  # the whole model fits on the device

    def describe(self) -> str:
        m = MODELS[self.model]
        where = "the CPU" if self.device is None else \
            f"{self.device.name} ({self.device.id}, {self.device.free_mb} MiB free)"
        return f"{m.id} ({m.params} {m.quant}) on {where}" + ("" if self.whole or self.device is None else
                                                             ", partly in RAM")


def this_os() -> str:
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def this_arch() -> str:
    return "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"


def ram_gb() -> float:
    """Physical memory, in GB."""
    if sys.platform == "win32":
        class Status(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        s = Status()
        s.dwLength = ctypes.sizeof(Status)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))  # type: ignore[attr-defined]
        return s.ullTotalPhys / 2**30
    if sys.platform == "darwin":
        return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout) / 2**30
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30


def parse_devices(text: str) -> tuple[Device, ...]:
    """The devices in `llama-server --list-devices` output."""
    return tuple(Device(m[1], m[2], int(m[3]), int(m[4])) for m in _DEVICE.finditer(text))


def list_devices(server: Path) -> tuple[Device, ...]:
    r = subprocess.run([str(server), "--list-devices"], capture_output=True, text=True, timeout=60)
    return parse_devices(r.stdout + r.stderr)


def machine(server: Path | None = None) -> Machine:
    """This machine. Without a llama.cpp build to ask, it lists no GPUs."""
    return Machine(this_os(), this_arch(), round(ram_gb(), 1), list_devices(server) if server else ())


def choose(m: Machine, tiers: tuple[str, ...] = TIERS) -> Plan:
    gpu = m.gpu
    if gpu is not None:
        for t in reversed(tiers):
            if MODELS[t].vram_gb * 1024 <= gpu.free_mb:
                return Plan(t, gpu, True)
        smallest = MODELS[tiers[0]]
        if smallest.ram_gb <= m.ram_gb * 0.6:
            return Plan(smallest.id, gpu, False)
    return Plan(tiers[0], None, False)
