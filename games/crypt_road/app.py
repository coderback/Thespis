"""The Crypt Road web app: the engine API from docs/api.md and the built client, from one URL.

Run locally:  uvicorn games.crypt_road.app:app --reload
Each request loads its session from SQLite and saves it back, so a restart loses nothing.
"""

import math
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from games.crypt_road import claims, rules, views, voice
from games.crypt_road.content import DEMO_SEED, load_cast, new_world
from games.hosting import (
    ApiError,
    Guard,
    SessionLimiter,
    SessionLocks,
    blocklist,
    client_ip,
    configure_logging,
    cors_origins,
    db_path,
    docs_settings,
    log,
    require_admin,
)
from games.hosting import budget as _budget
from games.hosting import env_int as _env_int
from games.manor import api as manor
from games.manor.content import load_cast as manor_cast
from thespis.claims import checking_from_env
from thespis.expression import PROMPT_HASH, Mind
from thespis.gateway import OpenAICompatGateway, gateway_from_env
from thespis.moderation import Layered, content_safety_from_env
from thespis.store import SessionNotFound, Store

ROOT = Path(__file__).resolve().parents[2]
CLIENT_DIST = ROOT / "client" / "dist"

LOCKS = SessionLocks()  # one request at a time per session

# Configured on import, not at startup: uvicorn imports the app before its first lines ("Started server process"),
# which would otherwise go to stderr unformatted, and Railway shows stderr as errors.
configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    path = db_path()
    app.state.store = Store(path)
    app.state.admin_token = os.environ.get("ADMIN_TOKEN", "").strip()  # unset: the admin endpoints don't exist
    # On the host, a count that keeps rising across redeploys proves the volume persists.
    log.info("boot #%d, database at %s", app.state.store.record_boot(), path.resolve())
    gateway = app.state.gateway = gateway_from_env()
    app.state.replay = os.environ.get("REPLAY", "0").strip() == "1"  # the cache and fallback only, never the network
    names = [f"{p.name} ({'structured' if p.structured else 'JSON mode'})" for p in gateway.providers]
    log.info("models: %s%s", " then ".join(names) + " then fallback" if names else "none configured, fallback only",
                "; REPLAY=1, so only cached replies, no model calls" if app.state.replay else "")
    log.info("prompts: %s; model cache: %d replies", PROMPT_HASH, app.state.store.cached_replies())
    # #24: caps on model calls (0 = none; cache hits are free) and on new sessions per IP
    app.state.session_cap = _env_int("SESSION_CALL_CAP", 60)
    app.state.global_cap = _env_int("GLOBAL_CALL_CAP", 0)
    app.state.limiter = SessionLimiter(_env_int("SESSIONS_PER_IP_HOUR", 30))
    log.info("caps: %s model calls per session, %s in all (%d made so far), %s new sessions per IP per hour",
                app.state.session_cap or "no cap on", app.state.global_cap or "no cap on",
                app.state.store.calls_made(), app.state.limiter.per_hour or "no limit on")
    # Moderation, both ways, for both games: Content Safety when configured, after each game's own blocklist.
    remote = content_safety_from_env()
    app.state.moderator = Layered(blocklist(load_cast()), remote)
    app.state.manor_moderator = Layered(blocklist(manor_cast()), remote)
    log.info("moderation: %s; the manor: %s", app.state.moderator, app.state.manor_moderator)
    checking = app.state.checking = checking_from_env(os.environ)
    log.info("claim check: %s", "off" if checking is None else
             f"{'every line' if checking.mode == 'all' else 'lines with consequences'}, extracted by "
             + (" then ".join(p.name for p in getattr(checking.gateway, "providers", ())) if checking.gateway
                else "the model that spoke"))
    yield
    gateway.close()  # the one this app opened, even if a test swapped app.state.gateway
    if checking is not None and isinstance(checking.gateway, OpenAICompatGateway):
        checking.gateway.close()
    if remote is not None:
        remote.close()


app = FastAPI(title="Thespis: The Crypt Road", lifespan=lifespan, **docs_settings())
# The client is served from this app, and in dev Vite proxies the API, so other origins are let in only by name.
if cors_origins():
    app.add_middleware(CORSMiddleware, allow_origins=cors_origins(), allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type", "X-Session"])
app.add_middleware(Guard)  # outermost: body size and security headers, for both games


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
    appeal: str | None = None  # how a bribe is pressed, when the player's words said (POST /say)


class SayBody(BaseModel):
    target: str
    text: str


class BrainBody(BaseModel):
    mode: Literal["model", "fallback"]


class PersonaBody(BaseModel):
    npc: str
    persona: str | None = None  # empty or null: back to the persona in cast.toml


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
    wait = request.app.state.limiter.wait(client_ip(request))
    if wait:
        raise ApiError(429, "rate_limited", f"Too many new games from here; try again in {math.ceil(wait / 60)} min, "
                                            "or carry on with the one you have")
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
    with LOCKS.hold(session):
        world = _load(store, session)
        try:
            result = rules.act(world, body.verb, body.target, body.claim.model_dump() if body.claim else None,
                               body.amount, body.text, gateway=request.app.state.gateway, cache=store,
                               replay=request.app.state.replay, budget=_budget(request.app.state, store, world),
                               moderator=request.app.state.moderator, checking=request.app.state.checking,
                               appeal=body.appeal)
        except rules.NotAllowed as e:
            raise ApiError(409, "not_allowed", e.reason) from None
        store.save(session, world)
        if result.model_calls:
            store.count_calls(result.model_calls)
        return views.act_view(result, world)


@app.post("/say")
def post_say(body: SayBody, request: Request, x_session: str | None = Header(default=None)):
    """What the player types to someone, read as one of the buttons open with them now and applied as that button
    would be (thespis.intents). The answer is /act's, with `understood`: how the words were read. A reading that
    isn't sure enough comes back with nothing done, to be put to the player."""
    store, session = _store(request), _session(x_session)
    with LOCKS.hold(session):
        world = _load(store, session)
        try:
            understood, result = rules.say(
                world, body.target, body.text, gateway=request.app.state.gateway, cache=store,
                replay=request.app.state.replay, budget=_budget(request.app.state, store, world),
                moderator=request.app.state.moderator, checking=request.app.state.checking)
        except rules.NotAllowed as e:
            raise ApiError(409, "not_allowed", e.reason) from None
        store.save(session, world)
        if result.model_calls:
            store.count_calls(result.model_calls)
        return {**views.act_view(result, world), "understood": views.understood_view(understood, body.target)}


@app.get("/digest")
def get_digest(request: Request, since: int = 0, x_session: str | None = Header(default=None)):
    """The Dungeon Master's telling. With the brain on it may call the model, so it counts against the caps."""
    store, session, state = _store(request), _session(x_session), request.app.state
    with LOCKS.hold(session):
        world = _load(store, session)
        gateway = state.gateway if world.brain_mode == "model" else None
        checker = claims.check(world, state.checking, gateway) if state.checking and gateway else None
        mind = Mind(gateway, voice.VALIDATOR, store, state.replay, _budget(state, store, world), state.moderator,
                    checker=checker)
        digest = views.digest_view(world, since, mind)
        if mind.asked:
            world.counters["model_calls"] = world.counters.get("model_calls", 0) + mind.asked
            store.save(session, world)
            store.count_calls(mind.asked)
        return digest


@app.post("/reset")
def post_reset(request: Request, x_session: str | None = Header(default=None)):
    store, session = _store(request), _session(x_session)
    with LOCKS.hold(session):
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
    with LOCKS.hold(session):
        world = _load(store, session)
        world.brain_mode = body.mode
        store.save(session, world)
        return {"mode": world.brain_mode}


@app.get("/dev/calls")
def get_calls(request: Request, since: int = 0):
    """The model calls made since `since` (the `total` of an earlier answer), with latency and tokens, for the harness.
    Across every session, and at most the latest 1000, so it answers only to the admin token."""
    require_admin(request)
    gateway = request.app.state.gateway
    total = getattr(gateway, "total", 0)
    calls = list(getattr(gateway, "calls", ()))[-(total - since):] if total > since else []
    return {"total": total, "calls": [asdict(c) for c in calls]}


@app.post("/dev/persona")
def post_persona(body: PersonaBody, request: Request, x_session: str | None = Header(default=None)):
    """Live persona editing (#39): this session's NPC speaks with the new persona from its next model line. Other
    sessions, and the cache for the default personas, are untouched; an edited persona is a new cache key."""
    store, session = _store(request), _session(x_session)
    with LOCKS.hold(session):
        world = _load(store, session)
        if body.npc not in world.npcs:
            raise ApiError(400, "bad_request", f"There's no one called {body.npc!r} to edit")
        text = (body.persona or "").strip()
        if len(text) > voice.PERSONA_MAX:
            raise ApiError(400, "bad_request", f"Keep the persona to {voice.PERSONA_MAX} characters")
        if text and (verdict := request.app.state.moderator.check([text])[0]).flagged:
            log.info("persona flagged", extra={"stage": "in", "npc": body.npc, "why": verdict.why})
            raise ApiError(400, "bad_request", "That persona can't be used; try another")
        flags = world.npcs[body.npc].flags
        if text:
            flags["persona"] = text
        else:
            flags.pop("persona", None)
        store.save(session, world)
        return {"npc": body.npc, "persona": voice.persona_of(world, body.npc), "default": not text}


# The second game on the same core (#35), text-only, at /manor.
app.include_router(manor.router)

# Mounted last so API routes win. Present once the client has been built (client/dist/index.html).
if (CLIENT_DIST / "index.html").exists():
    app.mount("/", StaticFiles(directory=CLIENT_DIST, html=True), name="client")
