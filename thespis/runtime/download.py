"""Fetching registry artifacts: resumable, checked, and never half-used.

A download goes to `<name>.part`. If the connection drops it resumes from where it stopped (an HTTP Range request),
by itself a few times and after that on the next call.
The finished file must have the registry's size and SHA-256. Only then is it renamed into place, so a file under its
real name is always a whole, checked one. A part that fails the check is deleted and fetched again from the start.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from thespis.runtime.registry import Artifact

CHUNK = 1 << 20
Progress = Callable[[int, int], None]  # (bytes so far, total)


class ChecksumError(RuntimeError):
    pass


def cache_dir() -> Path:
    """Where the runtime keeps models and engines: $THESPIS_HOME, else the platform's per-user cache."""
    if home := os.environ.get("THESPIS_HOME"):
        return Path(home)
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "thespis"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "thespis"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "thespis"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def fetch(a: Artifact, dest: Path, progress: Progress | None = None, client: httpx.Client | None = None,
          retries: int = 5) -> Path:
    """`a` at `dest`, downloading or resuming it if it isn't there whole. A dropped or stalled connection resumes
    by itself, up to `retries` times. Raises ChecksumError if what arrives isn't what the registry says, and httpx
    errors if the network keeps failing (call again to resume)."""
    if dest.exists() and dest.stat().st_size == a.size:
        return dest  # checked when it was renamed into place
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    if have > a.size:
        part.unlink()
        have = 0
    h = hashlib.sha256()
    if have:
        with part.open("rb") as f:
            while chunk := f.read(CHUNK):
                h.update(chunk)
    own = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60.0, connect=15.0))
    try:
        for attempt in range(retries + 1):
            try:
                if have < a.size:
                    headers = {"Range": f"bytes={have}-"} if have else {}
                    with client.stream("GET", a.url, headers=headers) as r:
                        if have and r.status_code != 206:  # the server ignored the range: start again
                            have, h = 0, hashlib.sha256()
                        r.raise_for_status()
                        with part.open("ab" if have else "wb") as f:
                            for chunk in r.iter_bytes():  # as they arrive: a drop loses nothing written
                                f.write(chunk)
                                h.update(chunk)
                                have += len(chunk)
                                if progress:
                                    progress(have, a.size)
                break
            except httpx.TransportError:
                # The connection dropped or stalled: resume from what arrived, after a pause.
                if attempt == retries:
                    raise
                time.sleep(min(2 ** attempt, 30))
    finally:
        if own:
            client.close()
    if have != a.size or h.hexdigest() != a.sha256:
        part.unlink(missing_ok=True)
        raise ChecksumError(f"{a.name}: got {have} bytes with SHA-256 {h.hexdigest()[:12]}..., expected {a.size} "
                            f"bytes with {a.sha256[:12]}...; the partial download was deleted")
    os.replace(part, dest)
    return dest
