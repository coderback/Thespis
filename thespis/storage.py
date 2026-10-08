"""What `thespis serve` keeps beyond a request: projects, their games and model settings, sessions, usage, and the
model reply cache. SQLite for the sidecar (one file beside the game) and for small servers; Postgres for a server
that should outlive its machine. One schema and one set of statements serve both.

Sessions are stored as the snapshot the engine would save (thespis.session), with a version that rises on every save:
a runtime that holds a session in memory checks the version before each call and reloads when another instance has
moved it on, and a save that finds the version moved is refused rather than overwriting newer state.

Usage is kept as events, one per model call and one per line settled, for export; a per-project daily total holds
what the caps read. Project keys are kept only as hashes. A project's model settings arrive encrypted
(thespis.vault) and are stored as they arrive.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

KEY_PREFIX = "tsk_"
LOCAL = "local"  # the sidecar's one project, and the one an unauthenticated runtime serves

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, key_hash TEXT UNIQUE, caps TEXT NOT NULL,
        model TEXT, created_at REAL NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS games (
        project TEXT NOT NULL, id TEXT NOT NULL, toml TEXT NOT NULL, updated_at REAL NOT NULL,
        PRIMARY KEY (project, id))""",
    """CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY, project TEXT NOT NULL, game TEXT NOT NULL, snapshot TEXT NOT NULL,
        version INTEGER NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS sessions_by_project ON sessions (project)",
    """CREATE TABLE IF NOT EXISTS usage (
        project TEXT NOT NULL, session TEXT, at REAL NOT NULL, kind TEXT NOT NULL, call_type TEXT NOT NULL,
        provider TEXT, source TEXT, ok INTEGER NOT NULL, latency_ms INTEGER, prompt_tokens INTEGER,
        completion_tokens INTEGER)""",
    "CREATE INDEX IF NOT EXISTS usage_by_project ON usage (project, at)",
    """CREATE TABLE IF NOT EXISTS usage_daily (
        project TEXT NOT NULL, day TEXT NOT NULL, calls INTEGER NOT NULL, tokens INTEGER NOT NULL,
        PRIMARY KEY (project, day))""",
    """CREATE TABLE IF NOT EXISTS replies (
        project TEXT NOT NULL, key TEXT NOT NULL, call_type TEXT NOT NULL, reply TEXT NOT NULL,
        provider TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY (project, key))""",
]


class Conflict(RuntimeError):
    """A save found the session moved on since it was loaded: another instance holds newer state."""


@dataclass(frozen=True)
class Caps:
    """What one project may use. 0 means no cap. Cache hits cost nothing and count against nothing."""
    max_sessions: int = 256  # open at once
    calls_per_day: int = 0  # model calls, UTC day
    tokens_per_day: int = 0  # prompt plus completion tokens, as providers report them
    max_games: int = 20

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> Caps:
        return cls(**{k: int(v) for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    caps: Caps = field(default_factory=Caps)
    created_at: float = 0.0


@dataclass(frozen=True)
class Usage:
    """One model call (kind "call") or one line settled (kind "line", whose source says llm, cache or fallback)."""
    project: str
    session: str | None
    kind: str
    call_type: str
    ok: bool
    provider: str | None = None
    source: str | None = None
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    at: float = field(default_factory=time.time)

    def to_json(self) -> dict:
        return asdict(self)


USAGE_FIELDS = tuple(Usage.__dataclass_fields__)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def day(at: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(at))


class Storage(Protocol):
    """What a runtime keeps. SqliteStorage and PostgresStorage are the two kinds."""

    def create_project(self, name: str, caps: Caps | None = None, key: bool = True,
                       project_id: str | None = None) -> tuple[Project, str | None]: ...
    def project(self, name_or_id: str) -> Project | None: ...
    def project_by_key(self, key: str) -> Project | None: ...
    def projects(self) -> list[Project]: ...
    def rotate_key(self, project: str) -> str: ...
    def set_caps(self, project: str, caps: Caps) -> None: ...
    def set_model(self, project: str, sealed: str | None) -> None: ...
    def model(self, project: str) -> str | None: ...

    def put_game(self, project: str, game: str, toml: str) -> None: ...
    def games(self, project: str) -> dict[str, str]: ...
    def delete_game(self, project: str, game: str) -> bool: ...

    def create_session(self, project: str, sid: str, game: str, snapshot: dict) -> None: ...
    def save_session(self, sid: str, snapshot: dict, version: int) -> int: ...
    def load_session(self, project: str, sid: str) -> tuple[str, dict, int] | None: ...
    def session_version(self, sid: str) -> int | None: ...
    def delete_session(self, project: str, sid: str) -> bool: ...
    def open_sessions(self, project: str) -> int: ...

    def record(self, events: Sequence[Usage]) -> None: ...
    def usage(self, project: str, since: float = 0, until: float | None = None,
              limit: int = 10_000) -> list[Usage]: ...
    def today(self, project: str) -> tuple[int, int]: ...

    def get_reply(self, project: str, key: str) -> tuple[dict, str] | None: ...
    def put_reply(self, project: str, key: str, call_type: str, data: dict, provider: str) -> None: ...

    def close(self) -> None: ...


class _Sql:
    """The statements, written once with ? placeholders; each kind supplies connections and its own dialect."""

    placeholder = "?"
    real = "REAL"

    def _schema(self) -> None:
        with self._tx() as db:
            for statement in _SCHEMA:
                self._exec(db, statement.replace("REAL", self.real))

    @contextmanager
    def _tx(self) -> Iterator[Any]:  # pragma: no cover - each kind has its own
        raise NotImplementedError
        yield

    def _exec(self, db, sql: str, params: Sequence = ()) -> Any:
        return db.execute(sql.replace("?", self.placeholder) if self.placeholder != "?" else sql, tuple(params))

    def _one(self, sql: str, params: Sequence = ()) -> tuple | None:
        with self._tx() as db:
            return self._exec(db, sql, params).fetchone()

    def _all(self, sql: str, params: Sequence = ()) -> list[tuple]:
        with self._tx() as db:
            return list(self._exec(db, sql, params).fetchall())

    def _write(self, sql: str, params: Sequence = ()) -> int:
        with self._tx() as db:
            return self._exec(db, sql, params).rowcount

    # ------------------------------------------------------------ projects
    def create_project(self, name: str, caps: Caps | None = None, key: bool = True,
                       project_id: str | None = None) -> tuple[Project, str | None]:
        """A new project and its key, which is shown once and kept only as a hash. Without `key` it takes none:
        the sidecar's local project, which the runtime serves without one."""
        p = Project(project_id or "p_" + secrets.token_hex(6), name, caps or Caps(), time.time())
        k = new_key() if key else None
        self._write("INSERT INTO projects (id, name, key_hash, caps, created_at) VALUES (?, ?, ?, ?, ?)",
                    (p.id, p.name, hash_key(k) if k else None, json.dumps(p.caps.to_json()), p.created_at))
        return p, k

    def _project(self, row: tuple | None) -> Project | None:
        return Project(row[0], row[1], Caps.from_json(json.loads(row[2])), row[3]) if row else None

    def project(self, name_or_id: str) -> Project | None:
        return self._project(self._one("SELECT id, name, caps, created_at FROM projects WHERE id = ? OR name = ?",
                                       (name_or_id, name_or_id)))

    def project_by_key(self, key: str) -> Project | None:
        if not key.startswith(KEY_PREFIX):
            return None
        return self._project(self._one("SELECT id, name, caps, created_at FROM projects WHERE key_hash = ?",
                                       (hash_key(key),)))

    def projects(self) -> list[Project]:
        return [p for p in (self._project(r) for r in self._all(
            "SELECT id, name, caps, created_at FROM projects ORDER BY created_at")) if p]

    def rotate_key(self, project: str) -> str:
        k = new_key()
        if not self._write("UPDATE projects SET key_hash = ? WHERE id = ?", (hash_key(k), project)):
            raise KeyError(project)
        return k

    def set_caps(self, project: str, caps: Caps) -> None:
        self._write("UPDATE projects SET caps = ? WHERE id = ?", (json.dumps(caps.to_json()), project))

    def set_model(self, project: str, sealed: str | None) -> None:
        self._write("UPDATE projects SET model = ? WHERE id = ?", (sealed, project))

    def model(self, project: str) -> str | None:
        row = self._one("SELECT model FROM projects WHERE id = ?", (project,))
        return row[0] if row else None

    # ------------------------------------------------------------ games
    def put_game(self, project: str, game: str, toml: str) -> None:
        self._write("INSERT INTO games (project, id, toml, updated_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT (project, id) DO UPDATE SET toml = excluded.toml, updated_at = excluded.updated_at",
                    (project, game, toml, time.time()))

    def games(self, project: str) -> dict[str, str]:
        return {r[0]: r[1] for r in self._all("SELECT id, toml FROM games WHERE project = ? ORDER BY id", (project,))}

    def delete_game(self, project: str, game: str) -> bool:
        return self._write("DELETE FROM games WHERE project = ? AND id = ?", (project, game)) > 0

    # ------------------------------------------------------------ sessions
    def create_session(self, project: str, sid: str, game: str, snapshot: dict) -> None:
        now = time.time()
        self._write("INSERT INTO sessions (id, project, game, snapshot, version, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, 1, ?, ?)", (sid, project, game, json.dumps(snapshot), now, now))

    def save_session(self, sid: str, snapshot: dict, version: int) -> int:
        """Replace the snapshot saved at `version`, and return the new version. Raises Conflict if the stored
        version moved on (another instance saved it) or the session is gone."""
        if not self._write("UPDATE sessions SET snapshot = ?, version = version + 1, updated_at = ? "
                           "WHERE id = ? AND version = ?", (json.dumps(snapshot), time.time(), sid, version)):
            raise Conflict(sid)
        return version + 1

    def load_session(self, project: str, sid: str) -> tuple[str, dict, int] | None:
        row = self._one("SELECT game, snapshot, version FROM sessions WHERE id = ? AND project = ?", (sid, project))
        return (row[0], json.loads(row[1]), row[2]) if row else None

    def session_version(self, sid: str) -> int | None:
        row = self._one("SELECT version FROM sessions WHERE id = ?", (sid,))
        return row[0] if row else None

    def delete_session(self, project: str, sid: str) -> bool:
        return self._write("DELETE FROM sessions WHERE id = ? AND project = ?", (sid, project)) > 0

    def open_sessions(self, project: str) -> int:
        row = self._one("SELECT COUNT(*) FROM sessions WHERE project = ?", (project,))
        return row[0] if row else 0

    # ------------------------------------------------------------ usage
    def record(self, events: Sequence[Usage]) -> None:
        if not events:
            return
        with self._tx() as db:
            for e in events:
                self._exec(db, f"INSERT INTO usage ({', '.join(USAGE_FIELDS)}) VALUES "
                               f"({', '.join('?' for _ in USAGE_FIELDS)})",
                           [int(v) if isinstance(v, bool) else v for v in (getattr(e, f) for f in USAGE_FIELDS)])
                if e.kind == "call":
                    tokens = (e.prompt_tokens or 0) + (e.completion_tokens or 0)
                    self._exec(db, "INSERT INTO usage_daily (project, day, calls, tokens) VALUES (?, ?, 1, ?) "
                                   "ON CONFLICT (project, day) DO UPDATE SET calls = usage_daily.calls + 1, "
                                   "tokens = usage_daily.tokens + excluded.tokens", (e.project, day(e.at), tokens))

    def usage(self, project: str, since: float = 0, until: float | None = None,
              limit: int = 10_000) -> list[Usage]:
        rows = self._all(f"SELECT {', '.join(USAGE_FIELDS)} FROM usage WHERE project = ? AND at >= ? AND at < ? "
                         "ORDER BY at LIMIT ?", (project, since, until if until is not None else 1e12, limit))
        return [Usage(**{**dict(zip(USAGE_FIELDS, r)), "ok": bool(r[USAGE_FIELDS.index("ok")])}) for r in rows]

    def today(self, project: str) -> tuple[int, int]:
        """Model calls and tokens so far today (UTC)."""
        row = self._one("SELECT calls, tokens FROM usage_daily WHERE project = ? AND day = ?",
                        (project, day(time.time())))
        return (row[0], row[1]) if row else (0, 0)

    # ------------------------------------------------------------ the model reply cache, one per project
    def get_reply(self, project: str, key: str) -> tuple[dict, str] | None:
        row = self._one("SELECT reply, provider FROM replies WHERE project = ? AND key = ?", (project, key))
        return (json.loads(row[0]), row[1]) if row else None

    def put_reply(self, project: str, key: str, call_type: str, data: dict, provider: str) -> None:
        """The first reply stored for a key stays."""
        self._write("INSERT INTO replies VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (project, key) DO NOTHING",
                    (project, key, call_type, json.dumps(data), provider, time.time()))


class SqliteStorage(_Sql):
    """One SQLite file (or ":memory:"), through one connection: SQLite writes one at a time anyway."""

    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, timeout=10, check_same_thread=False, isolation_level=None)
        self._lock = threading.RLock()
        if self.path != ":memory:":
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
        self._schema()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._db.execute("BEGIN")
            try:
                yield self._db
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")

    def close(self) -> None:
        with self._lock:
            self._db.close()


class PostgresStorage(_Sql):
    """A Postgres database, through a pool of connections (psycopg, the `thespis[server]` extra)."""

    placeholder = "%s"
    real = "DOUBLE PRECISION"

    def __init__(self, dsn: str, size: int = 10):
        from psycopg_pool import ConnectionPool
        self.dsn = dsn
        self._pool = ConnectionPool(dsn, min_size=1, max_size=size, open=True, kwargs={"autocommit": False})
        self._schema()

    @contextmanager
    def _tx(self) -> Iterator[Any]:
        with self._pool.connection() as db:  # commits on success, rolls back on error
            yield db

    def close(self) -> None:
        self._pool.close()


def storage(where: str) -> SqliteStorage | PostgresStorage:
    """Storage from a URL or a path: postgres://... or postgresql://... for Postgres, anything else a SQLite file
    (":memory:" for none)."""
    if where.startswith(("postgres://", "postgresql://")):
        return PostgresStorage(where)
    return SqliteStorage(where)
