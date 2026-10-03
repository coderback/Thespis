"""The Crypt Road web app: the engine API from docs/api.md and the built client, from one URL.

Run locally:  uvicorn games.crypt_road.app:app --reload
Each request loads its session from SQLite and saves it back, so a restart loses nothing.
"""

import logging
import os
import threading
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from games.crypt_road import rules, views
from games.crypt_road.content import DEMO_SEED, new_world
from thespis.store import SessionNotFound, Store

ROOT = Path(__file__).resolve().parents[2]
CLIENT_DIST = ROOT / "client" / "dist"

log = logging.getLogger("thespis")
_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)  # one request at a time per session


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
# The client's dev server runs on another port; in production it is served from this app.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ApiError(Exception):
    def __init__(self, status: int, error: str, reason: str):
        self.status, self.error, self.reason = status, error, reason


@app.exception_handler(ApiError)
async def api_error(request: Request, exc: ApiError):
    return JSONResponse({"error": exc.error, "reason": exc.reason}, status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def bad_request(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    return JSONResponse({"error": "bad_request", "reason": f"{where}: {first.get('msg', 'invalid request')}"},
                        status_code=400)


class SessionBody(BaseModel):
    seed: int | None = None


class ClaimBody(BaseModel):
    pred: str
    a: str
    b: str


class ActBody(BaseModel):
    verb: str
    target: str | None = None
    claim: ClaimBody | None = None
    amount: int | None = None
    text: str | None = None


class BrainBody(BaseModel):
    mode: Literal["model", "fallback"]


def _store(request: Request) -> Store:
    return request.app.state.store


def _session(x_session: str | None) -> str:
    if not x_session:
        raise ApiError(400, "bad_request", "Send the session id in the X-Session header")
    return x_session


def _load(store: Store, session: str):
    try:
        return store.load(session)
    except SessionNotFound:
        raise ApiError(404, "unknown_session", "That session doesn't exist; start a new one") from None


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/session")
def create_session(request: Request, body: SessionBody | None = None):
    store = _store(request)
    seed = body.seed if body and body.seed is not None else DEMO_SEED
    session = store.create_session(seed)
    world = new_world(seed)
    store.save(session, world)
    return {"session": session, "state": views.state_view(world)}


@app.get("/state")
def get_state(request: Request, x_session: str | None = Header(default=None)):
    return views.state_view(_load(_store(request), _session(x_session)))


@app.get("/allowed")
def get_allowed(request: Request, x_session: str | None = Header(default=None)):
    return {"verbs": rules.allowed(_load(_store(request), _session(x_session)))}


@app.post("/act")
def post_act(body: ActBody, request: Request, x_session: str | None = Header(default=None)):
    store, session = _store(request), _session(x_session)
    with _locks[session]:
        world = _load(store, session)
        try:
            result = rules.act(world, body.verb, body.target, body.claim.model_dump() if body.claim else None,
                               body.amount, body.text)
        except rules.NotAllowed as e:
            raise ApiError(409, "not_allowed", e.reason) from None
        store.save(session, world)
        return views.act_view(result, world)


@app.get("/digest")
def get_digest(request: Request, since: int = 0, x_session: str | None = Header(default=None)):
    return views.digest_view(_load(_store(request), _session(x_session)), since)


@app.post("/reset")
def post_reset(request: Request, x_session: str | None = Header(default=None)):
    store, session = _store(request), _session(x_session)
    with _locks[session]:
        _load(store, session)
        world = new_world(store.seed_of(session))
        store.reset(session, world)
        return {"state": views.state_view(world)}


@app.post("/reload")
def post_reload(request: Request, x_session: str | None = Header(default=None)):
    """Rebuild the session from disk. Every request already does; this is the dev panel's explicit button."""
    return {"state": views.state_view(_load(_store(request), _session(x_session)))}


@app.post("/dev/brain")
def post_brain(body: BrainBody, request: Request, x_session: str | None = Header(default=None)):
    store, session = _store(request), _session(x_session)
    with _locks[session]:
        world = _load(store, session)
        world.brain_mode = body.mode
        store.save(session, world)
        return {"mode": world.brain_mode}


# Mounted last so API routes win. Present once the client has been built (client/dist/index.html).
if (CLIENT_DIST / "index.html").exists():
    app.mount("/", StaticFiles(directory=CLIENT_DIST, html=True), name="client")
