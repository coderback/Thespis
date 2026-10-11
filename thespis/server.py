"""The /v1 HTTP API: the session calls (thespis.session), one route each, for engines that aren't Python.

An engine opens a session on a game the server loaded or the project sent, reports events and changes, and asks for
decisions and lines. Lines come back provisional by default and are polled until final (`GET .../lines/{id}?wait=2`).
The routes mirror the library's calls one for one, and the generated OpenAPI spec, committed as docs/openapi-v1.json,
is the SDKs' contract: tests fail when the two drift apart.

A server (`thespis serve --server`) wants the project's key on every call: `Authorization: Bearer tsk_...`. A sidecar
wants the token its launcher gave it, if it was given one. Projects send their own games (`PUT /v1/games/{id}`), set
their own model keys on a server (`PUT /v1/project/model`), and export their usage (`GET /v1/usage`).

Errors carry `{error, reason}`: 400 for a malformed body or a definition the call breaks, 401 without the right key,
404 for an unknown game, session, NPC, moment or line, 409 for a call the game doesn't allow now (or a session another
instance moved on), 413 for a game too large, 429 over a project's cap, 503 when the project holds its limit of
sessions. Sessions are kept by the host (thespis.host): in memory, in a sidecar's SQLite file, or in a server's
database.
"""

from __future__ import annotations

import asyncio
import csv
import io
from collections.abc import Mapping
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from thespis import offline
from thespis.considerations import DefinitionError
from thespis.gateway import ModelGateway
from thespis.host import MEMORY, Host, HostError
from thespis.ledger import Event
from thespis.play import NotAllowed
from thespis.session import Game, Session, Unknown
from thespis.storage import USAGE_FIELDS, Project
from thespis.tracing import span
from thespis.vault import VaultError

VERSION = "v1"
MAX_SESSIONS = 256
Scalar = str | int | float | bool


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
    conf: float | None = Field(None, ge=0, le=1, description=(
        "With said: how far its hearers believe it, when the engine's own rules decide that (a roll of the dice); "
        "left out, each hearer's trust in the speaker decides"))


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
    to: str | None = Field(None, description="Tell it to this player: only what they took part in or saw")


class OfferIn(BaseModel):
    verb: str = Field(description="An intent the game declares: [intents.<verb>]")
    args: dict[str, Any] = Field(default_factory=dict, description=(
        "Each argument's choices now, narrowing the game's: ids for an npc, player, place or choice; {min, max} for "
        "an amount; {preds, subjects} for a claim. Left out, the game's (an npc: whoever is where the player is)"))


class UnderstandIn(BaseModel):
    text: str = Field(max_length=4000, description="What the player typed")
    to: str | None = Field(None, description="The NPC the player is speaking to")
    player: str = Field("player", description="Who typed it")
    offered: list[OfferIn] | None = Field(None, description=(
        "The intents open now, as the engine's buttons have them; left out, every intent the game declares"))


class JoinIn(BaseModel):
    player: str = Field(description="A new player's id (not 'player', which every game has, nor an NPC's)")
    name: str | None = Field(None, description="What NPCs and the narrator call them")
    at: str | None = Field(None, description="Where they are")


class NpcIn(BaseModel):
    id: str = Field(description="A new NPC's id: letters, digits, _ . and -, and not one already taken")
    kind: str = Field(description="A kind of person the game declares: [kind.<id>]")
    name: str = Field(description="What others and the narrator call them")
    at: str = Field("", description="Where they are")
    persona: str | None = Field(None, description="Their own persona; their kind's if left out")
    goal: str | None = Field(None, description="Their own goal; their kind's if left out")


class TieIn(BaseModel):
    a: str
    b: str
    kind: str = Field(description="A kind of tie the game's [gossip] along declares")


class TickIn(BaseModel):
    steps: int = Field(1, ge=1, le=100)


class GameIn(BaseModel):
    toml: str = Field(description="The game's definition, as in a game.toml")


class ProviderIn(BaseModel):
    profile: str = Field("", description="A provider profile: openai, azure, anthropic, gemini, groq, ...")
    base_url: str = Field("", description="The endpoint; the profile's if left out")
    model: str
    api_key: str = Field("", description="Kept sealed; never sent back")
    timeout: float | None = Field(None, gt=0, le=120)
    extra: dict[str, Any] | None = None
    api_version: str = ""
    structured: bool = True


class ModelIn(BaseModel):
    primary: ProviderIn
    backup: ProviderIn | None = None


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
    segments: list[dict[str, Any]] | None = Field(
        None, description="A told scene, for a game whose narrator is structured: in order, each the narrator's "
                          "words or one speaker's ({speaker, line, cites})")


class IntentOut(BaseModel):
    verb: str
    args: dict[str, Any] = Field(description="Each argument: an id, a whole number, or a claim {pred, a, b, ...}")
    reads: str = Field(description="As put to the player: 'Tell Wren that Garrick insulted her'")


class UnderstandOut(BaseModel):
    status: str = Field(description="act (apply the intent), ask (put the readings to the player first) or talk "
                                    "(words that do nothing else)")
    intent: IntentOut | None = Field(description="The act, or for talk, the game's talk intent if it declares one")
    sure: str = Field(description="certain, likely or unsure")
    readings: list[IntentOut] = Field(description="For ask: what the words might do, most likely first")
    path: str = Field(description="What answered: guard, bank, near, model, cache or none")
    why: str = ""


class TickOut(BaseModel):
    phase: int
    moves: list[dict[str, str]]
    events: list[EventOut]


class TieOut(BaseModel):
    between: list[str]
    kind: str


class GameOut(BaseModel):
    id: str
    name: str
    digest: str
    npcs: list[str]
    kinds: list[str] = Field(default_factory=list, description="Kinds of people the engine may add in play")
    places: list[str]
    choices: dict[str, list[str]] = Field(description="Each NPC's choice sets, by moment")


class NpcOut(BaseModel):
    npc: dict[str, Any]
    beliefs: list[dict[str, Any]]


class HealthOut(BaseModel):
    ok: bool
    offline: bool = Field(description="It refuses every connection off this machine (a sidecar, unless --online)")
    refused: int = Field(description="Connections off this machine it has refused since it started")


class ProjectOut(BaseModel):
    id: str
    name: str
    caps: dict[str, int] = Field(description="0 means no cap")
    today: dict[str, int] = Field(description="Model calls and tokens so far today (UTC)")
    sessions: int = Field(description="Sessions open now")
    model: dict[str, Any] | None = Field(None, description="Its own model settings, keys left out; null: the host's")


class UsageOut(BaseModel):
    project: str
    session: str | None
    kind: str = Field(description="call (a model call), line (a line settled) or capped (a call the caps refused)")
    call_type: str
    ok: bool
    provider: str | None
    source: str | None = Field(description="For a line: llm, cache or fallback. For capped: which cap")
    latency_ms: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    at: float


def _event(e: Event) -> EventOut:
    return EventOut(**{**e.to_json(), "claim": e.claim.to_json() if e.claim else None})


async def _caller(request: Request, authorization: Annotated[
        str | None, Header(description="Bearer <the project's key, or the sidecar's token>")] = None) -> Project:
    host: Host = request.app.state.host
    return host.known(authorization) or await asyncio.to_thread(host.authenticate, authorization)


class _Traced:
    """A span for each request (thespis.tracing), as plain ASGI: Starlette's BaseHTTPMiddleware costs every request
    a task and a stream, which a busy server notices."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        with span("thespis.http", method=scope["method"]) as s:
            async def sent(message):
                if message["type"] == "http.response.start":
                    s.set_attribute("http.status_code", message["status"])
                await send(message)
            await self.app(scope, receive, sent)
            route = scope.get("route")
            s.set_attribute("http.route", getattr(route, "path", scope["path"]))


Caller = Annotated[Project, Depends(_caller)]


def _game(g: Game) -> GameOut:
    moments: dict[str, list[str]] = {}
    for npc, moment in g.choices:
        moments.setdefault(npc, []).append(moment)
    return GameOut(id=g.id, name=g.name, digest=g.digest, npcs=list(g.cast.ids()), kinds=list(g.kinds),
                   places=list(g.places), choices=moments)


def create_app(games: Mapping[str, Game] | None = None, gateway: ModelGateway | None = None,
               max_sessions: int = MAX_SESSIONS, host: Host | None = None) -> FastAPI:
    """The API over `host`; without one, over `games` (by id) in memory, every session speaking through `gateway`,
    or using template lines without one."""
    host = host or Host(games=games, gateway=gateway, mode=MEMORY, max_sessions=max_sessions)
    app = FastAPI(title="Thespis", version=VERSION, description=__doc__ or "")
    app.state.host = host

    app.add_middleware(_Traced)

    @app.exception_handler(HostError)
    async def host_error(request: Request, exc: HostError):
        return JSONResponse({"error": exc.error, "reason": exc.reason}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        return JSONResponse({"error": "bad_request", "reason": f"{where}: {first.get('msg', 'invalid request')}"},
                            status_code=400)

    for error, status, kind in ((Unknown, 404, "unknown"), (DefinitionError, 400, "bad_definition"),
                                (NotAllowed, 409, "not_allowed"), (VaultError, 500, "vault")):
        def handler(request: Request, exc: Exception, status=status, kind=kind):
            return JSONResponse({"error": kind, "reason": getattr(exc, "reason", None) or str(exc)},
                                status_code=status)
        app.add_exception_handler(error, handler)

    def call(p: Project, sid: str, fn, saves: bool = True):
        return host.call(p, sid, fn, saves)

    @app.get(f"/{VERSION}/health")
    def health() -> HealthOut:
        """Up, and whether it is offline (thespis.offline): a game promising offline play can check it is."""
        return HealthOut(ok=True, offline=offline.active(), refused=len(offline.refused))

    @app.get(f"/{VERSION}/games")
    def list_games(p: Caller) -> list[GameOut]:
        return [_game(g) for g in host.games(p).values()]

    @app.put(f"/{VERSION}/games/{{gid}}")
    def put_game(p: Caller, gid: str, body: GameIn) -> GameOut:
        """Send a game: the project's own, which shadows the host's game of the same id."""
        return _game(host.put_game(p, gid, body.toml))

    @app.delete(f"/{VERSION}/games/{{gid}}", status_code=204)
    def delete_game(p: Caller, gid: str) -> None:
        host.delete_game(p, gid)

    @app.post(f"/{VERSION}/sessions", status_code=201)
    def open_session(p: Caller, body: SessionIn) -> SessionOut:
        sid, live = host.open(p, body.game, body.seed, body.snapshot)
        return SessionOut(session=sid, game=live.game, phase=live.session.world.phase)

    @app.delete(f"/{VERSION}/sessions/{{sid}}", status_code=204)
    def close_session(p: Caller, sid: str) -> None:
        host.close(p, sid)

    @app.post(f"/{VERSION}/sessions/{{sid}}/observe", status_code=201)
    def observe(p: Caller, sid: str, body: ObserveIn) -> EventOut:
        claim = body.claim.model_dump() if body.claim else None
        return _event(call(p, sid, lambda s: s.observe(body.verb, body.actor, body.target, body.at, claim,
                                                       body.witnesses, body.said, body.true, body.amount,
                                                       body.conf)))

    @app.post(f"/{VERSION}/sessions/{{sid}}/update")
    def update(p: Caller, sid: str, body: UpdateIn) -> dict[str, Any]:
        return call(p, sid, lambda s: s.update(body.npc, body.loc, body.drives, body.nudge, body.flags,
                                               body.trust_in))

    @app.post(f"/{VERSION}/sessions/{{sid}}/decide")
    def decide(p: Caller, sid: str, body: DecideIn) -> LineOut:
        line = call(p, sid, lambda s: s.decide(body.npc, body.moment, body.bindings, body.situation, body.to,
                                               body.wait))
        return LineOut(**line.to_json())

    @app.post(f"/{VERSION}/sessions/{{sid}}/react")
    def react(p: Caller, sid: str, body: ReactIn) -> LineOut:
        line = call(p, sid, lambda s: s.react(body.npc, body.trigger, body.situation, body.cites, body.fill,
                                              body.wait))
        return LineOut(**line.to_json())

    @app.post(f"/{VERSION}/sessions/{{sid}}/narrate")
    def narrate(p: Caller, sid: str, body: NarrateIn) -> LineOut:
        return LineOut(**call(p, sid, lambda s: s.narrate(body.since, body.wait, body.to)).to_json())

    @app.post(f"/{VERSION}/sessions/{{sid}}/understand")
    def understand(p: Caller, sid: str, body: UnderstandIn) -> UnderstandOut:
        """What the player's words do, among the intents open now: an act to apply as the engine would apply the
        button, readings to put to the player first, or talk. It changes nothing; report the act with observe."""
        offered = [o.model_dump() for o in body.offered] if body.offered is not None else None
        return UnderstandOut(**call(p, sid, lambda s: s.understand(body.text, body.to, body.player, offered),
                                    saves=False).to_json())

    @app.post(f"/{VERSION}/sessions/{{sid}}/players", status_code=201)
    def join(p: Caller, sid: str, body: JoinIn) -> dict[str, Any]:
        """A player joins, or one already here is renamed or moves: an agent NPCs see, hear and hold beliefs
        about by id. Move them later with update (npc = their id, loc)."""
        return call(p, sid, lambda s: s.join(body.player, body.name, body.at))

    @app.post(f"/{VERSION}/sessions/{{sid}}/npcs", status_code=201)
    def add(p: Caller, sid: str, body: NpcIn) -> dict[str, Any]:
        """Someone joins the cast in play: an NPC of a kind the game declares, with its own id, name and place.
        From here on it is an NPC like any the game file names."""
        return call(p, sid, lambda s: s.add(body.id, body.kind, body.name, body.at, body.persona, body.goal))

    @app.delete(f"/{VERSION}/sessions/{{sid}}/npcs/{{npc}}")
    def retire(p: Caller, sid: str, npc: str) -> dict[str, Any]:
        """An NPC leaves the story, dead or gone for good: it sees, says and decides nothing more. What it believed
        is kept, and others still believe things about it."""
        return call(p, sid, lambda s: s.retire(npc))

    @app.post(f"/{VERSION}/sessions/{{sid}}/ties", status_code=201)
    def tie(p: Caller, sid: str, body: TieIn) -> TieOut:
        """A tie between two NPCs, made in play: gossip travels along it as [gossip] along says for its kind."""
        return TieOut(**call(p, sid, lambda s: s.tie(body.a, body.b, body.kind)))

    @app.delete(f"/{VERSION}/sessions/{{sid}}/ties/{{a}}/{{b}}", status_code=204)
    def untie(p: Caller, sid: str, a: str, b: str) -> None:
        """Break a tie made in play."""
        call(p, sid, lambda s: s.untie(a, b))

    @app.post(f"/{VERSION}/sessions/{{sid}}/tick")
    def tick(p: Caller, sid: str, body: TickIn) -> TickOut:
        def run(s: Session) -> TickOut:
            t = s.tick(body.steps)
            return TickOut(phase=s.world.phase, moves=t.moves, events=[_event(e) for e in t.events])
        return call(p, sid, run)

    @app.get(f"/{VERSION}/sessions/{{sid}}/lines/{{lid}}")
    async def line(p: Caller, sid: str, lid: str, wait: float = Query(0, ge=0, le=10)) -> LineOut:
        # A long poll waits on the line's model call without holding a thread, or the session's lock: many engines
        # may be waiting at once, and the engine's next call mustn't wait behind its own poll.
        session = (await asyncio.to_thread(host.live, p, sid)).session
        pending = session.pending(lid)
        if pending is not None and wait > 0:
            try:
                await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(pending)), wait)
            except Exception:
                pass  # still provisional, or it settled with the template line: either way, say how it stands
        # Read off the event loop: the line takes the session's lock, which a waited call holds through its model
        # call, and the loop serves every session.
        return LineOut(**(await asyncio.to_thread(session.line, lid)).to_json())

    @app.get(f"/{VERSION}/sessions/{{sid}}/npcs/{{npc}}")
    def inspect(p: Caller, sid: str, npc: str) -> NpcOut:
        return NpcOut(**call(p, sid, lambda s: s.inspect(npc), saves=False))

    @app.get(f"/{VERSION}/sessions/{{sid}}/snapshot")
    def snapshot(p: Caller, sid: str) -> dict[str, Any]:
        return call(p, sid, lambda s: s.snapshot(), saves=False)

    @app.get(f"/{VERSION}/project")
    def get_project(p: Caller) -> ProjectOut:
        calls, tokens = host.storage.today(p.id)
        return ProjectOut(id=p.id, name=p.name, caps=p.caps.to_json(), today={"calls": calls, "tokens": tokens},
                          sessions=host.storage.open_sessions(p.id), model=host.model_settings(p))

    @app.put(f"/{VERSION}/project/model", status_code=204)
    def put_model(p: Caller, body: ModelIn) -> None:
        """Set the models the project's sessions speak through, with its own keys (a server only). Sessions
        opened or reloaded from now on use them."""
        host.set_model(p, body.model_dump())

    @app.delete(f"/{VERSION}/project/model", status_code=204)
    def delete_model(p: Caller) -> None:
        host.set_model(p, None)

    @app.get(f"/{VERSION}/usage", response_model=list[UsageOut])
    def usage(p: Caller, since: float = Query(0, description="Unix time"), until: float | None = None,
              limit: int = Query(10_000, ge=1, le=100_000),
              format: str = Query("json", pattern="^(json|csv)$")) -> Any:
        """The project's usage events, oldest first: each model call, each line settled, each call a cap refused."""
        events = host.storage.usage(p.id, since, until, limit)
        if format == "json":
            return [e.to_json() for e in events]
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=USAGE_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(e.to_json() for e in events)
        return Response(out.getvalue(), media_type="text/csv")

    return app
