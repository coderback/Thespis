"""The Crypt Road web app: the engine API and the built client from one URL.

Run locally:  uvicorn games.crypt_road.app:app --reload
The session endpoints from docs/api.md arrive in #8; for now this serves /health and the client build.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from thespis.store import Store

ROOT = Path(__file__).resolve().parents[2]
CLIENT_DIST = ROOT / "client" / "dist"

log = logging.getLogger("thespis")


def db_path() -> Path:
    return Path(os.environ.get("DB_PATH", "./data/thespis.sqlite"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    path = db_path()
    app.state.store = Store(path)
    # On the host, a count that keeps rising across redeploys proves the volume persists.
    log.warning("boot #%d, database at %s", app.state.store.record_boot(), path.resolve())
    yield


app = FastAPI(title="Thespis: The Crypt Road", lifespan=lifespan)


@app.get("/health")
def health():
    return {"ok": True}


# Mounted last so API routes win. Present once the client has been built (client/dist/index.html).
if (CLIENT_DIST / "index.html").exists():
    app.mount("/", StaticFiles(directory=CLIENT_DIST, html=True), name="client")
