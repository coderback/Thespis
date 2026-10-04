"""SQLite persistence: an insert-only ledger table plus one JSON snapshot per session, and the model reply cache.

A restart loads the snapshot, so a reloaded session is identical to the one that was running. The ledger rows are
never updated or deleted; a reset starts a new run of the same session instead. The cache is shared by every
session, so a route played once is answered from it the next time, on any session, after any restart.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from thespis.ledger import SCHEMA_VERSION
from thespis.world import World

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY, seed INTEGER NOT NULL, run INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL, updated_at REAL NOT NULL, snapshot TEXT
);
CREATE TABLE IF NOT EXISTS ledger (
    session_id TEXT NOT NULL, run INTEGER NOT NULL, seq INTEGER NOT NULL,
    id TEXT NOT NULL, phase INTEGER NOT NULL, event TEXT NOT NULL,
    PRIMARY KEY (session_id, run, seq)
);
CREATE TABLE IF NOT EXISTS model_cache (
    key TEXT PRIMARY KEY, call_type TEXT NOT NULL, reply TEXT NOT NULL, provider TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


class SessionNotFound(KeyError):
    pass


class LedgerMismatch(RuntimeError):
    """The snapshot and the ledger table disagree, so the stored state can't be trusted."""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(_SCHEMA)
            db.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
            db.commit()

    def _connect(self) -> sqlite3.Connection:
        # One short-lived connection per call: simple, and safe across uvicorn's threads.
        return sqlite3.connect(self.path, timeout=10)

    def _run(self, fn):
        with closing(self._connect()) as db, db:  # `with db` commits, or rolls back on error
            return fn(db)

    # ---------------------------------------------------------------- sessions
    def create_session(self, seed: int) -> str:
        session_id = secrets.token_urlsafe(8)
        now = time.time()
        self._run(lambda db: db.execute(
            "INSERT INTO sessions (id, seed, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, seed, now, now)))
        return session_id

    def save(self, session_id: str, world: World) -> None:
        """Append the ledger events not yet stored, then replace the snapshot, in one transaction."""
        def write(db):
            run = self._run_of(db, session_id)
            stored = db.execute("SELECT COUNT(*) FROM ledger WHERE session_id = ? AND run = ?",
                                (session_id, run)).fetchone()[0]
            events = list(world.ledger)
            if stored > len(events):
                raise LedgerMismatch(f"{session_id}: {stored} events stored but only {len(events)} in memory")
            db.executemany(
                "INSERT INTO ledger (session_id, run, seq, id, phase, event) VALUES (?, ?, ?, ?, ?, ?)",
                [(session_id, run, seq, e.id, e.phase, json.dumps(e.to_json()))
                 for seq, e in enumerate(events[stored:], start=stored + 1)])
            db.execute("UPDATE sessions SET snapshot = ?, updated_at = ? WHERE id = ?",
                       (json.dumps(world.to_json()), time.time(), session_id))
        self._run(write)

    def load(self, session_id: str) -> World:
        def read(db):
            run = self._run_of(db, session_id)
            snapshot = db.execute("SELECT snapshot FROM sessions WHERE id = ?", (session_id,)).fetchone()[0]
            rows = [json.loads(r[0]) for r in db.execute(
                "SELECT event FROM ledger WHERE session_id = ? AND run = ? ORDER BY seq", (session_id, run))]
            return snapshot, rows
        snapshot, rows = self._run(read)
        if snapshot is None:
            raise SessionNotFound(f"{session_id} has no saved state yet")
        data = json.loads(snapshot)
        if data["ledger"] != rows:
            raise LedgerMismatch(f"{session_id}: snapshot holds {len(data['ledger'])} events, "
                                 f"ledger table {len(rows)}, or they differ")
        return World.from_json(data)

    def reset(self, session_id: str, world: World) -> None:
        """Start a new run of the session from `world`. Earlier runs' ledger rows are kept."""
        self._run(lambda db: db.execute("UPDATE sessions SET run = run + 1, snapshot = NULL WHERE id = ?",
                                        (self._exists(db, session_id),)))
        self.save(session_id, world)

    def seed_of(self, session_id: str) -> int:
        return self._run(lambda db: db.execute("SELECT seed FROM sessions WHERE id = ?",
                                               (self._exists(db, session_id),)).fetchone()[0])

    def _exists(self, db, session_id: str) -> str:
        if db.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone() is None:
            raise SessionNotFound(session_id)
        return session_id

    def _run_of(self, db, session_id: str) -> int:
        row = db.execute("SELECT run FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise SessionNotFound(session_id)
        return row[0]

    # ---------------------------------------------------------------- model reply cache
    def get_reply(self, key: str) -> tuple[dict, str] | None:
        row = self._run(lambda db: db.execute("SELECT reply, provider FROM model_cache WHERE key = ?",
                                              (key,)).fetchone())
        return (json.loads(row[0]), row[1]) if row else None

    def put_reply(self, key: str, call_type: str, data: dict, provider: str) -> None:
        """The first reply stored for a key stays, so a replay always says what was said the first time."""
        self._run(lambda db: db.execute("INSERT OR IGNORE INTO model_cache VALUES (?, ?, ?, ?, ?)",
                                        (key, call_type, json.dumps(data), provider, time.time())))

    def cached_replies(self) -> int:
        return self._run(lambda db: db.execute("SELECT COUNT(*) FROM model_cache").fetchone()[0])

    # ---------------------------------------------------------------- meta
    def count_calls(self, n: int) -> int:
        """Add n to the model calls made across every session, and return the new total. Survives restarts."""
        def add(db):
            db.execute("INSERT OR IGNORE INTO meta VALUES ('model_calls', '0')")
            db.execute("UPDATE meta SET value = CAST(value AS INTEGER) + ? WHERE key = 'model_calls'", (n,))
            return int(db.execute("SELECT value FROM meta WHERE key = 'model_calls'").fetchone()[0])
        return self._run(add)

    def calls_made(self) -> int:
        row = self._run(lambda db: db.execute("SELECT value FROM meta WHERE key = 'model_calls'").fetchone())
        return int(row[0]) if row else 0

    def record_boot(self) -> int:
        """Count server starts. On the host, a count that keeps rising across redeploys proves the volume persists."""
        def bump(db):
            row = db.execute("SELECT value FROM meta WHERE key = 'boots'").fetchone()
            if row is None:
                # Carry over the count from the first deploy, which kept boots in their own table.
                legacy = db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'boots'").fetchone()
                count = db.execute("SELECT COUNT(*) FROM boots").fetchone()[0] if legacy else 0
            else:
                count = int(row[0])
            db.execute("INSERT OR REPLACE INTO meta VALUES ('boots', ?)", (str(count + 1),))
            return count + 1
        return self._run(bump)
