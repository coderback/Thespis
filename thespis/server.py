"""The /v1 HTTP API: the session calls (thespis.session), one route each, for engines that aren't Python.

An engine opens a session on a game the server loaded, reports events and changes, and asks for decisions and lines.
Lines come back provisional by default and are polled until final (`GET .../lines/{id}?wait=2`). The routes mirror
the library's calls one for one, and the generated OpenAPI spec, committed as docs/openapi-v1.json, is the SDKs'
contract: tests fail when the two drift apart.

Errors carry `{error, reason}`: 400 for a malformed body or a definition the call breaks, 404 for an unknown game,
session, NPC, moment or line, 409 for a call the game doesn't allow now, 503 when the server holds its limit of
sessions. Sessions live in memory here; the sidecar and server runtimes (Phase 4.4) keep them in a store.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from thespis.considerations import DefinitionError
from thespis.gateway import ModelGateway
from thespis.ledger import Event
from thespis.play import NotAllowed
from thespis.session import Game, Session, Unknown

VERSION = "v1"
MAX_SESSIONS = 256
Scalar = str | int | float | bool


class ApiError(Exception):
    def __init__(self, status: int, error: str, reason: str):
        self.status, self.error, self.reason = status, error, reason


# ---------------------------------------------------------------- bodies
class ClaimIn(BaseModel):
    pred: str = Field(description="What is claimed, from the game's predicates: insulted, paid, was_in")
    a: str = Field(description="Who it is about, by id; 'player' is the player")
    b: str = ""
    place: str | None = None
    at: int | None = None
    neg: bool = Field(False, description="A denial: the claim that this did not happen")


class SessionIn(BaseModel):
    game: str = Field(description="A game the server loaded, by its id")
    seed: int = 0
    snapshot: dict[str, Any] | None = Field(None, description="Restore this snapshot instead of starting fresh")


class ObserveIn(BaseModel):
    verb: str = Field(description="What happened: the game's own word for it, as [words.events] names it")
    actor: str
    target: str | None = None
    at: str | None = Field(None, description="Where it happened; the actor's place if left out")
    claim: ClaimIn | None = Field(None, description="What it shows, or, with said, what was said")
    witnesses: list[str] = Field(default_factory=list, description="NPCs who saw it, besides the actor and target")
    said: bool = Field(False, description="The actor stated the claim: hearers believe it by their trust in them")
    true: bool | None = Field(None, description="Whether the claim is true; left out, the ledger decides")
    amount: int | None = None


class UpdateIn(BaseModel):
    npc: str = Field(description="An NPC id, or 'player' (which takes only loc)")
    loc: str | None = None
    drives: dict[str, int] | None = Field(None, description="Drives to set, 0 to 10")
    nudge: dict[str, int] | None = Field(None, description="Drives to move by a step, kept within 0 to 10")
    flags: dict[str, Any] | None = Field(None, description="Flags to set; null removes one")
    trust_in: dict[str, int] | None = Field(None, description="Trust to set, -5 to 5")


class DecideIn(BaseModel):
    npc: str
    moment: str = Field(description="Which of the NPC's declared choice sets: [[npc.<id>.choices.<moment>]]")
    bindings: dict[str, Scalar] = Field(default_factory=dict, description="Values the choices name: {culprit}")
    situation: str | None = Field(None, description="What just happened, from the NPC's side, for the model")
    to: str | None = Field(None, description="Whom an action that states a claim tells it to")
    wait: bool = Field(False, description="Wait for the model's line instead of returning it provisional")


class ReactIn(BaseModel):
    npc: str
    trigger: str = Field(description="The line's key in [npc.<id>.lines]")
    situation: str | None = None
    cites: list[str] = Field(default_factory=list, description="Event or belief ids the line rests on")
    fill: dict[str, Scalar] = Field(default_factory=dict, description="Values for the template's {placeholders}")
    wait: bool = False


class NarrateIn(BaseModel):
    since: int = Field(0, description="Tell the story from this phase on")
    wait: bool = False


class TickIn(BaseModel):
    steps: int = Field(1, ge=1, le=100)


# ---------------------------------------------------------------- replies
class SessionOut(BaseModel):
    session: str
    game: str
    phase: int


class EventOut(BaseModel):
    id: str
    phase: int
    verb: str
    actor: str
    target: str | None
    loc: str
    claim: ClaimIn | None
    truth: bool
    amount: int | None = None


class LineOut(BaseModel):
    id: str | None = Field(description="Poll it at /lines/{id}; null when the NPC had nothing to say")
    npc: str
    text: str | None
    cites: list[str]
    status: str = Field(description="provisional (more to come), final, or withdrawn (don't show it)")
    source: str = Field(description="llm, cache or fallback (the game's template line)")
    action: str | None = Field(None, description="What the NPC decided to do, for decide")
    reason: str = ""
    event: str | None = Field(None, description="The statement its action logged, if it states a claim")


class TickOut(BaseModel):
    phase: int
    moves: list[dict[str, str]]
    events: list[EventOut]


class GameOut(BaseModel):
    id: str
    name: str
    digest: str
    npcs: list[str]
    places: list[str]
    choices: dict[str, list[str]] = Field(description="Each NPC's choice sets, by moment")


class NpcOut(BaseModel):
    npc: dict[str, Any]
    beliefs: list[dict[str, Any]]


def _event(e: Event) -> EventOut:
    return EventOut(**{**e.to_json(), "claim": e.claim.to_json() if e.claim else None})


def create_app(games: Mapping[str, Game], gateway: ModelGateway | None = None,
               max_sessions: int = MAX_SESSIONS) -> FastAPI:
    """The API over `games`, by id. Every session speaks through `gateway`, or uses template lines without one."""
    app = FastAPI(title="Thespis", version=VERSION, description=__doc__ or "")
    sessions: dict[str, Session] = {}
    lock = threading.Lock()

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return JSONResponse({"error": exc.error, "reason": exc.reason}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        return JSONResponse({"error": "bad_request", "reason": f"{where}: {first.get('msg', 'invalid request')}"},
                            status_code=400)

    for error, status, kind in ((Unknown, 404, "unknown"), (DefinitionError, 400, "bad_definition"),
                                (NotAllowed, 409, "not_allowed")):
        def handler(request: Request, exc: Exception, status=status, kind=kind):
            return JSONResponse({"error": kind, "reason": getattr(exc, "reason", None) or str(exc)},
                                status_code=status)
        app.add_exception_handler(error, handler)

    def game(gid: str) -> Game:
        if gid not in games:
            raise Unknown(f"no game {gid!r}")
        return games[gid]

    def session(sid: str) -> Session:
        s = sessions.get(sid)
        if s is None:
            raise Unknown(f"no session {sid!r}")
        return s

    @app.get(f"/{VERSION}/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get(f"/{VERSION}/games")
    def list_games() -> list[GameOut]:
        out = []
        for g in games.values():
            moments: dict[str, list[str]] = {}
            for npc, moment in g.choices:
                moments.setdefault(npc, []).append(moment)
            out.append(GameOut(id=g.id, name=g.name, digest=g.digest, npcs=list(g.cast.ids()), places=list(g.places),
                               choices=moments))
        return out

    @app.post(f"/{VERSION}/sessions", status_code=201)
    def open_session(body: SessionIn) -> SessionOut:
        g = game(body.game)
        s = Session.restore(g, body.snapshot, gateway=gateway) if body.snapshot else \
            Session.new(g, body.seed, gateway=gateway)
        with lock:
            if len(sessions) >= max_sessions:
                raise ApiError(503, "full", "The server holds as many sessions as it can; close one first")
            sid = secrets.token_urlsafe(12)
            sessions[sid] = s
        return SessionOut(session=sid, game=g.id, phase=s.world.phase)

    @app.delete(f"/{VERSION}/sessions/{{sid}}", status_code=204)
    def close_session(sid: str) -> None:
        with lock:
            s = sessions.pop(sid, None)
        if s is None:
            raise Unknown(f"no session {sid!r}")
        s.close()

    @app.post(f"/{VERSION}/sessions/{{sid}}/observe", status_code=201)
    def observe(sid: str, body: ObserveIn) -> EventOut:
        claim = body.claim.model_dump() if body.claim else None
        e = session(sid).observe(body.verb, body.actor, body.target, body.at, claim, body.witnesses, body.said,
                                 body.true, body.amount)
        return _event(e)

    @app.post(f"/{VERSION}/sessions/{{sid}}/update")
    def update(sid: str, body: UpdateIn) -> dict[str, Any]:
        return session(sid).update(body.npc, body.loc, body.drives, body.nudge, body.flags, body.trust_in)

    @app.post(f"/{VERSION}/sessions/{{sid}}/decide")
    def decide(sid: str, body: DecideIn) -> LineOut:
        line = session(sid).decide(body.npc, body.moment, body.bindings, body.situation, body.to, body.wait)
        return LineOut(**line.to_json())

    @app.post(f"/{VERSION}/sessions/{{sid}}/react")
    def react(sid: str, body: ReactIn) -> LineOut:
        line = session(sid).react(body.npc, body.trigger, body.situation, body.cites, body.fill, body.wait)
        return LineOut(**line.to_json())

    @app.post(f"/{VERSION}/sessions/{{sid}}/narrate")
    def narrate(sid: str, body: NarrateIn) -> LineOut:
        return LineOut(**session(sid).narrate(body.since, body.wait).to_json())

    @app.post(f"/{VERSION}/sessions/{{sid}}/tick")
    def tick(sid: str, body: TickIn) -> TickOut:
        s = session(sid)
        t = s.tick(body.steps)
        return TickOut(phase=s.world.phase, moves=t.moves, events=[_event(e) for e in t.events])

    @app.get(f"/{VERSION}/sessions/{{sid}}/lines/{{lid}}")
    def line(sid: str, lid: str, wait: float = Query(0, ge=0, le=10)) -> LineOut:
        return LineOut(**session(sid).line(lid, wait).to_json())

    @app.get(f"/{VERSION}/sessions/{{sid}}/npcs/{{npc}}")
    def inspect(sid: str, npc: str) -> NpcOut:
        return NpcOut(**session(sid).inspect(npc))

    @app.get(f"/{VERSION}/sessions/{{sid}}/snapshot")
    def snapshot(sid: str) -> dict[str, Any]:
        return session(sid).snapshot()

    return app
