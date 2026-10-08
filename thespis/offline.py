"""Offline, enforced: a sidecar runs with the network off unless told otherwise, so a game that promises offline play
can't quietly depend on the internet. `guard()` refuses, inside this process, every name lookup and connection that
isn't to this machine: a cloud model call fails at once (the NPC uses its template line, as on any failed call), a
download says to pull the model first, and `refused` lists what was tried, so a test can prove nothing left.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
from collections.abc import Callable
from typing import Any

LOCAL_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost", ""})

refused: list[str] = []
_lock = threading.Lock()
_original: dict[str, Callable[..., Any]] = {}


class Offline(OSError):
    """A connection to somewhere other than this machine, refused because the runtime is offline."""


def local(host: Any) -> bool:
    if host is None:
        return True
    name = host.decode() if isinstance(host, bytes) else str(host)
    name = name.strip("[]").split("%")[0].lower()
    if name in LOCAL_NAMES or name.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def _refuse(what: str) -> Offline:
    with _lock:
        refused.append(what)
    return Offline(f"offline: refused {what} (start with --online to allow it)")


def active() -> bool:
    """Is this process offline (guarded)?"""
    return bool(_original)


def guard() -> None:
    """Refuse every lookup and connection off this machine, from now until `release()`."""
    if _original:
        return
    _original.update(getaddrinfo=socket.getaddrinfo, connect=socket.socket.connect,
                     connect_ex=socket.socket.connect_ex)

    def getaddrinfo(host, *args, **kw):
        if not local(host):
            raise _refuse(f"looking up {host}")
        return _original["getaddrinfo"](host, *args, **kw)

    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not local(address[0]):
            raise _refuse(f"connecting to {address[0]}")
        return _original["connect"](self, address)

    def connect_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not local(address[0]):
            raise _refuse(f"connecting to {address[0]}")
        return _original["connect_ex"](self, address)

    socket.getaddrinfo = getaddrinfo
    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]


def release() -> None:
    if not _original:
        return
    socket.getaddrinfo = _original.pop("getaddrinfo")
    socket.socket.connect = _original.pop("connect")  # type: ignore[method-assign]
    socket.socket.connect_ex = _original.pop("connect_ex")  # type: ignore[method-assign]
