"""The manor mystery's API and its page, at /manor on the same server as The Crypt Road (#35).

Its sessions live in their own database beside the Crypt Road's, so neither game can ever load the other's world. The
model, its reply cache and the call caps are the server's, shared with The Crypt Road through app.state.
"""

from __future__ import annotations

import math
import threading
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Header, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel

from games.hosting import ApiError, SessionLocks, budget, client_ip, db_path
from games.manor import content as C
from games.manor import rules, views
from games.manor.content import new_world
from thespis.store import SessionNotFound, Store
from thespis.world import World

PAGE = Path(__file__).resolve().parents[2] / "client" / "dist" / "manor" / "index.html"  # built by the client
UNBUILT = ("<!doctype html><meta charset='utf-8'><title>The Manor Mystery</title><body style='font:16px system-ui;"
           "background:#120e15;color:#efe6f5;padding:40px'><h1>The Manor Mystery</h1><p>Build the client to play: "
           "<code>cd client &amp;&amp; npm run build</code>. The API is under <code>/manor</code>; see docs/manor.md.</p>")
router = APIRouter(prefix="/manor", tags=["manor"])
LOCKS = SessionLocks()  # one request at a time per session
_open = threading.Lock()


class ActBody(BaseModel):
    verb: str
    target: str | None = None
    topic: str | None = None


class BrainBody(BaseModel):
    mode: Literal["model", "fallback"]


def _sessions(request: Request) -> Store:
    """The manor's own session store, beside the server's database (on the volume, when there is one)."""
    path, state = db_path().with_name("manor.sqlite"), request.app.state
    with _open:
        if getattr(state, "manor_path", None) != path:
            state.manor_store, state.manor_path = Store(path), path
        return state.manor_store


def _session(x_session: str | None) -> str:
    if not x_session:
        raise ApiError(400, "bad_request", "Send the session id in the X-Session header")
    return x_session


def _load(store: Store, session: str) -> World:
    try:
        return store.load(session, C.upgrade_claim)
    except SessionNotFound:
        raise ApiError(404, "unknown_session", "That session doesn't exist; start a new one") from None


@router.get("", include_in_schema=False)
def page_redirect():
    return RedirectResponse("/manor/")


@router.get("/", include_in_schema=False)
def page():
    """The game's page from the client build; its assets load from /assets, served with The Crypt Road's."""
    return FileResponse(PAGE, media_type="text/html") if PAGE.exists() else HTMLResponse(UNBUILT)


@router.post("/session")
def create_session(request: Request):
    wait = request.app.state.limiter.wait(client_ip(request))
    if wait:
        raise ApiError(429, "rate_limited", f"Too many new games from here; try again in {math.ceil(wait / 60)} min")
    store = _sessions(request)
    session = store.create_session(1)
    world = new_world()
    store.save(session, world)
    return {"session": session, "state": views.state_view(world)}


@router.get("/state")
def get_state(request: Request, x_session: str | None = Header(default=None)):
    return views.state_view(_load(_sessions(request), _session(x_session)))


@router.get("/allowed")
def get_allowed(request: Request, x_session: str | None = Header(default=None)):
    return {"verbs": rules.allowed(_load(_sessions(request), _session(x_session)))}


@router.post("/act")
def post_act(body: ActBody, request: Request, x_session: str | None = Header(default=None)):
    store, session, state = _sessions(request), _session(x_session), request.app.state
    with LOCKS.hold(session):
        world = _load(store, session)
        try:
            result = rules.act(world, body.verb, body.target, body.topic, gateway=state.gateway, cache=state.store,
                               replay=state.replay, budget=budget(state, state.store, world),
                               moderator=state.manor_moderator, checking=getattr(state, "checking", None))
        except rules.NotAllowed as e:
            raise ApiError(409, "not_allowed", e.reason) from None
        store.save(session, world)
        if result.model_calls:
            state.store.count_calls(result.model_calls)  # counted with The Crypt Road's, against the global cap
        return views.act_view(result, world)


@router.post("/reset")
def post_reset(request: Request, x_session: str | None = Header(default=None)):
    store, session = _sessions(request), _session(x_session)
    with LOCKS.hold(session):
        _load(store, session)
        world = new_world()
        store.reset(session, world)
        return {"state": views.state_view(world)}


@router.post("/reload")
def post_reload(request: Request, x_session: str | None = Header(default=None)):
    """Rebuild the session from disk. Every request already does; this is the dev panel's explicit button."""
    return {"state": views.state_view(_load(_sessions(request), _session(x_session)))}


@router.post("/dev/brain")
def post_brain(body: BrainBody, request: Request, x_session: str | None = Header(default=None)):
    """The dev panel's brain switch: "fallback" plays with no model calls at all."""
    store, session = _sessions(request), _session(x_session)
    with LOCKS.hold(session):
        world = _load(store, session)
        world.brain_mode = body.mode
        store.save(session, world)
        return {"mode": world.brain_mode}
