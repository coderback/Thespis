"""The Crypt Road web app: the engine API and the built client from one URL.

Run locally:  uvicorn games.crypt_road.app:app --reload
The session endpoints from docs/api.md arrive in #8; for now this serves /health and the client build.
"""

import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[2]
CLIENT_DIST = ROOT / "client" / "dist"

log = logging.getLogger("thespis")


def db_path() -> Path:
    return Path(os.environ.get("DB_PATH", "./data/thespis.sqlite"))


def record_boot(path: Path) -> int:
    """Log this start in the database and return how many starts it has seen.

    On the host, a count that keeps rising across restarts proves the volume persists.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS boots (id INTEGER PRIMARY KEY, at REAL NOT NULL)")
        db.execute("INSERT INTO boots (at) VALUES (?)", (time.time(),))
        return db.execute("SELECT COUNT(*) FROM boots").fetchone()[0]


@asynccontextmanager
async def lifespan(app: FastAPI):
    path = db_path()
    boots = record_boot(path)
    log.warning("boot #%d, database at %s", boots, path.resolve())
    yield


app = FastAPI(title="Thespis: The Crypt Road", lifespan=lifespan)


@app.get("/health")
def health():
    return {"ok": True}


# Mounted last so API routes win. Present once the client has been built (client/dist/index.html).
if (CLIENT_DIST / "index.html").exists():
    app.mount("/", StaticFiles(directory=CLIENT_DIST, html=True), name="client")
