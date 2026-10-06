"""What any game hosted on this server shares: errors, the per-IP session limit, the database path, the model call
caps, and what keeps the server's edges shut: the admin token, CORS, API docs, body size and security headers. The
Crypt Road's app hosts the server; the manor mystery (#35) mounts its routes on it and uses these too.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import Request

from thespis.store import Store
from thespis.world import World

log = logging.getLogger("thespis")

MAX_BODY = 64 * 1024  # bytes in a request body; the largest real one, a persona edit, is well under 1 KB
SECURITY_HEADERS = [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"strict-origin-when-cross-origin")]


class ApiError(Exception):
    def __init__(self, status: int, error: str, reason: str):
        self.status, self.error, self.reason = status, error, reason


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


# ---------------------------------------------------------------- the server's edges
def require_admin(request: Request) -> None:
    """Endpoints that see across every session answer only to ADMIN_TOKEN, sent as a Bearer token. With no token set
    they don't exist (404); with a missing or wrong one, 401."""
    token = getattr(request.app.state, "admin_token", "")
    if not token:
        raise ApiError(404, "not_found", "Not found")
    scheme, _, sent = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(sent.strip().encode(), token.encode()):
        raise ApiError(401, "unauthorized", "This endpoint needs the admin token")


def docs_settings() -> dict:
    """FastAPI's generated API docs (/docs, /redoc, /openapi.json) only with API_DOCS=1: they list every endpoint."""
    return {} if os.environ.get("API_DOCS", "").strip() == "1" else \
        {"docs_url": None, "redoc_url": None, "openapi_url": None}


def cors_origins() -> list[str]:
    """CORS_ORIGINS, comma-separated. Empty by default: the server serves its own client, and in dev Vite proxies the
    API, so no browser ever needs another origin to read it."""
    return [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]


class Guard:
    """ASGI middleware on every request: refuse a body over MAX_BODY with 413, and add the security headers."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        length = headers.get(b"content-length")
        if length is not None and (not length.isdigit() or int(length) > MAX_BODY):
            return await _too_large(send)
        if length is None and b"chunked" in headers.get(b"transfer-encoding", b""):
            body = await _read_body(receive)  # no length given: read it here, up to the limit, then hand it on
            if body is None:
                return await _too_large(send)
            receive = _replay(body)

        async def secured(message):
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), *SECURITY_HEADERS]
            await send(message)

        await self.app(scope, receive, secured)


async def _too_large(send) -> None:
    body = json.dumps({"error": "too_large", "reason": f"Request bodies are limited to {MAX_BODY} bytes"}).encode()
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                            *SECURITY_HEADERS]})
    await send({"type": "http.response.body", "body": body})


async def _read_body(receive) -> bytes | None:
    """The whole body, or None once it passes MAX_BODY."""
    chunks, size = [], 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            break
        chunks.append(message.get("body", b""))
        size += len(chunks[-1])
        if size > MAX_BODY:
            return None
        if not message.get("more_body"):
            break
    return b"".join(chunks)


def _replay(body: bytes):
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}
    return receive


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
