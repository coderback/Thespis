"""What any game hosted on this server shares: errors, the per-IP session limit, the database path and the model call
caps. The Crypt Road's app hosts the server; the manor mystery (#35) mounts its routes on it and uses these too.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import Request

from thespis.store import Store
from thespis.world import World

log = logging.getLogger("thespis")


class ApiError(Exception):
    def __init__(self, status: int, error: str, reason: str):
        self.status, self.error, self.reason = status, error, reason


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


class SessionLimiter:
    """At most `per_hour` new sessions per client IP in any hour; 0 turns it off. Kept in memory: a restart resets it."""

    def __init__(self, per_hour: int, clock=time.monotonic):
        self.per_hour, self.clock = per_hour, clock
        self._seen: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def wait(self, ip: str) -> float:
        """0 if this IP may start a session now (and count it), else the seconds until it may."""
        if self.per_hour <= 0:
            return 0.0
        now = self.clock()
        with self._lock:
            seen = self._seen[ip]
            while seen and seen[0] <= now - 3600:
                seen.popleft()
            if len(seen) >= self.per_hour:
                return seen[0] + 3600 - now
            seen.append(now)
            return 0.0


def client_ip(request: Request) -> str:
    """Railway's edge sets X-Real-IP to the client's address; X-Forwarded-For's first entry is the same."""
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return request.headers.get("x-real-ip") or forwarded or (request.client.host if request.client else "unknown")


def db_path() -> Path:
    """DB_PATH, except that with a Railway volume attached the database always lives on the volume: anywhere else it
    would be wiped, with every session and the model cache, on the next deploy."""
    path = Path(os.environ.get("DB_PATH", "./data/thespis.sqlite"))
    volume = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if volume and not path.resolve().is_relative_to(Path(volume).resolve()):
        log.warning("DB_PATH %s is not on the volume at %s, so it would not survive a deploy; ignoring it", path, volume)
        path = Path(volume) / "thespis.sqlite"
    return path


def budget(state, store: Store, world: World) -> int | None:
    """How many model calls an action may make: what's left of the session's cap and of the global cap."""
    left = []
    if state.session_cap > 0:
        left.append(state.session_cap - world.counters.get("model_calls", 0))
    if state.global_cap > 0:
        left.append(state.global_cap - store.calls_made())
    return max(0, min(left)) if left else None
