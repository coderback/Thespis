"""What `thespis serve` runs: projects, each with its games, its models and its sessions, kept in a Storage
(thespis.storage). The /v1 routes (thespis.server) call into a Host; so does nothing else.

It runs three ways:
  - **memory**: one project, nothing kept past the process. The library's HTTP tests and quick experiments.
  - **sidecar**: one project, a SQLite file, localhost only. A game's SDK starts it and stops it; it is offline
    unless told otherwise (thespis.offline). A token, if the launcher sets one, keeps other local programs out.
  - **server**: many projects, each calling with its own key (`Authorization: Bearer tsk_...`), on SQLite or
    Postgres. Each project brings its own model keys, sealed at rest (thespis.vault), and has its own caps.

Every session call is saved before it answers, and every provisional line again when it settles, so a restart, or
another instance, picks the session up where it was. A session held in memory checks its stored version before
each call and reloads if another instance moved it on; lines still on their way are lost then, and their ids answer
404, so an engine shows the template line it already has.

Each session speaks through its project's gateway, metered: every model call and every settled line is a usage
event (thespis.storage.Usage), and a project over its daily call or token cap gets template lines until the next
UTC day. Replies are cached per project, so the same moment played twice costs one call.
"""

from __future__ import annotations

import hmac
import ipaddress
import logging
import secrets
import socket
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from thespis.considerations import DefinitionError
from thespis.expression import Mind, StatePack, Utterance
from thespis.gateway import MAX_CONCURRENT, Call, ModelGateway, ModelReply, NoModel, gateway_from_env
from thespis.session import Game, Line, Session, Unknown
from thespis.storage import LOCAL, Caps, Conflict, Project, SqliteStorage, Storage, Usage
from thespis.vault import Vault, VaultError

log = logging.getLogger("thespis.host")

MEMORY, SIDECAR, SERVER = "memory", "sidecar", "server"
LIVE = 1024  # sessions one instance keeps in memory; the rest are loaded from storage when called
KEYS_FOR = 5.0  # seconds a key, once checked, is trusted without asking storage again (so a new key or caps take
# effect within this long)
MAX_GAME_BYTES = 256 * 1024
PROVIDER_FIELDS = ("profile", "base_url", "model", "api_key", "timeout", "extra", "api_version", "structured")


class HostError(Exception):
    def __init__(self, status: int, error: str, reason: str):
        super().__init__(reason)
        self.status, self.error, self.reason = status, error, reason


@dataclass
class Live:
    """A session held in memory, with the version of it last stored."""
    session: Session
    project: str
    game: str
    version: int
    lock: threading.Lock = field(default_factory=threading.Lock)  # one call at a time
    saving: threading.Lock = field(default_factory=threading.Lock)  # one save at a time


class ProjectCache:
    """The model reply cache (thespis.expression.ReplyCache), one per project."""

    def __init__(self, storage: Storage, project: str):
        self.storage, self.project = storage, project

    def get_reply(self, key: str) -> tuple[dict, str] | None:
        return self.storage.get_reply(self.project, key)

    def put_reply(self, key: str, call_type: str, data: dict, provider: str) -> None:
        self.storage.put_reply(self.project, key, call_type, data, provider)


class Metered:
    """A project's gateway as one session sees it: each call is checked against the project's caps and recorded."""

    def __init__(self, host: Host, project: Project, session: str, inner: ModelGateway):
        self.host, self.project, self.session, self.inner = host, project, session, inner
        self.providers = getattr(inner, "providers", ())

    @property
    def models(self) -> tuple[str, ...]:
        return self.inner.models

    def complete(self, call_type: str, messages: list[dict], schema: dict | None = None) -> ModelReply | None:
        capped = self.host.over_cap(self.project)
        if capped:
            self.host.record(Usage(self.project.id, self.session, "capped", call_type, False, source=capped))
            return None
        started = time.perf_counter()
        reply = self.inner.complete(call_type, messages, schema)
        self.host.record(Usage(
            self.project.id, self.session, "call", call_type, reply is not None,
            provider=reply.provider if reply else None, latency_ms=round((time.perf_counter() - started) * 1000),
            prompt_tokens=reply.prompt_tokens if reply else None,
            completion_tokens=reply.completion_tokens if reply else None))
        return reply

    def complete_many(self, calls: Sequence[Call]) -> list[ModelReply | None]:
        if len(calls) <= 1:
            return [self.complete(*c) for c in calls]
        with ThreadPoolExecutor(max_workers=min(MAX_CONCURRENT, len(calls))) as pool:
            return list(pool.map(lambda c: self.complete(*c), calls))


def check_model_url(url: str, allow_private: bool = False) -> None:
    """A server only calls model endpoints on the public internet, over HTTPS: a project's settings must not turn
    it into a way into the network it runs in. `allow_private` lifts that, for a server beside its own vLLM."""
    u = urlparse(url)
    if u.scheme not in ("https", "http") or not u.hostname:
        raise HostError(400, "bad_request", f"base_url {url!r} is not an http(s) URL")
    if allow_private:
        return
    if u.scheme != "https":
        raise HostError(400, "bad_request", "base_url must be https")
    try:
        addresses = {a[4][0] for a in socket.getaddrinfo(u.hostname, u.port or 443, proto=socket.IPPROTO_TCP)}
    except OSError as e:
        raise HostError(400, "bad_request", f"base_url host {u.hostname!r} doesn't resolve") from e
    for a in addresses:
        ip = ipaddress.ip_address(str(a).split("%")[0])
        if not ip.is_global:
            raise HostError(400, "bad_request", f"base_url host {u.hostname!r} is not on the public internet")


def provider_env(settings: Mapping[str, Any]) -> dict[str, str]:
    """A project's model settings as the LLM_* and LLM_BACKUP_* variables thespis.gateway reads."""
    env: dict[str, str] = {}
    for prefix, part in (("LLM_", settings.get("primary")), ("LLM_BACKUP_", settings.get("backup"))):
        for k, v in (part or {}).items():
            if v is None or v == "" or k not in PROVIDER_FIELDS:
                continue
            if k == "extra":
                import json
                v = json.dumps(v)
            elif k == "structured":
                v = "1" if v else "0"
            env[f"{prefix}{k.upper()}"] = str(v)
    return env


class Host:
    def __init__(self, storage: Storage | None = None, games: Mapping[str, Game] | None = None,
                 gateway: ModelGateway | None = None, mode: str = MEMORY, max_sessions: int = 256,
                 token: str | None = None, vault: Vault | None = None, cache: bool = True,
                 allow_private_models: bool = False, live: int = LIVE):
        """`games` every project can play; `gateway` speaks for projects with no models of their own (and for the
        sidecar's one project). `token`, for a sidecar, is what callers must present."""
        if mode not in (MEMORY, SIDECAR, SERVER):
            raise ValueError(f"mode {mode!r}")
        self.storage = storage or SqliteStorage(":memory:")
        self.shared = dict(games or {})
        self.gateway = gateway or NoModel()
        self.mode, self.token, self.vault, self.cache = mode, token, vault, cache
        self.allow_private_models = allow_private_models
        self._live: OrderedDict[str, Live] = OrderedDict()
        self._live_max = live
        self._lock = threading.Lock()
        self._compiled: dict[tuple[str, str], tuple[str, Game]] = {}  # (project, game) -> (its TOML, compiled)
        self._gateways: dict[str, tuple[str | None, ModelGateway]] = {}  # project -> (sealed settings, gateway)
        self._keys: dict[str, tuple[Project, float]] = {}  # key -> (its project, when it was checked)
        if mode != SERVER:
            local = self.storage.project(LOCAL)
            caps = Caps(max_sessions=max_sessions)
            if local is None:
                self.storage.create_project(LOCAL, caps, key=False, project_id=LOCAL)
            elif local.caps.max_sessions != max_sessions:
                self.storage.set_caps(LOCAL, Caps(**{**local.caps.to_json(), "max_sessions": max_sessions}))

    # ------------------------------------------------------------ who is calling
    def known(self, authorization: str | None) -> Project | None:
        """The caller's project if its key was checked in the last KEYS_FOR seconds, without asking storage."""
        if self.mode != SERVER:
            return None
        known = self._keys.get((authorization or "").removeprefix("Bearer ").strip())
        return known[0] if known is not None and time.monotonic() - known[1] < KEYS_FOR else None

    def authenticate(self, authorization: str | None) -> Project:
        given = (authorization or "").removeprefix("Bearer ").strip()
        if self.mode == SERVER:
            if (known := self.known(authorization)) is not None:
                return known
            project = self.storage.project_by_key(given) if given else None
            if project is not None:
                with self._lock:
                    if len(self._keys) > 10_000:
                        self._keys.clear()
                    self._keys[given] = (project, time.monotonic())
            if project is None:
                raise HostError(401, "unauthorized", "send the project's key: Authorization: Bearer tsk_...")
            return project
        if self.token and not hmac.compare_digest(given.encode(), self.token.encode()):
            raise HostError(401, "unauthorized", "send the sidecar's token: Authorization: Bearer <token>")
        project = self.storage.project(LOCAL)
        assert project is not None
        return project

    # ------------------------------------------------------------ games
    def games(self, project: Project) -> dict[str, Game]:
        """The games the project can play: the host's, and its own, which shadow the host's of the same id."""
        own = self.storage.games(project.id)
        out = dict(self.shared)
        for gid, toml in own.items():
            cached = self._compiled.get((project.id, gid))
            if cached is None or cached[0] != toml:
                cached = (toml, Game.parse(toml, gid))
                self._compiled[(project.id, gid)] = cached
            out[gid] = cached[1]
        return out

    def game(self, project: Project, gid: str) -> Game:
        games = self.games(project)
        if gid not in games:
            raise Unknown(f"no game {gid!r}")
        return games[gid]

    def put_game(self, project: Project, gid: str, toml: str) -> Game:
        if len(toml.encode()) > MAX_GAME_BYTES:
            raise HostError(413, "too_large", f"a game is at most {MAX_GAME_BYTES // 1024} KB")
        game = Game.parse(toml, gid)
        if game.id != gid:
            raise DefinitionError(f"the game says its id is {game.id!r}, not {gid!r}")
        own = self.storage.games(project.id)
        if gid not in own and project.caps.max_games and len(own) >= project.caps.max_games:
            raise HostError(429, "over_cap", f"the project has its {project.caps.max_games} games; delete one first")
        self.storage.put_game(project.id, gid, toml)
        self._compiled[(project.id, gid)] = (toml, game)
        return game

    def delete_game(self, project: Project, gid: str) -> None:
        if not self.storage.delete_game(project.id, gid):
            raise Unknown(f"no game {gid!r} of the project's own")
        self._compiled.pop((project.id, gid), None)

    # ------------------------------------------------------------ models
    def set_model(self, project: Project, settings: Mapping[str, Any] | None) -> None:
        """Keep the project's model settings, sealed, or forget them (None)."""
        if settings is None:
            self.storage.set_model(project.id, None)
            return
        if self.mode != SERVER:
            raise HostError(409, "not_allowed", "a sidecar speaks through the models it was started with")
        if self.vault is None:
            raise HostError(503, "no_vault", "the server can't keep model keys: it has no THESPIS_SECRET_KEY")
        env = provider_env(settings)
        primary = gateway_from_env(env)
        if not getattr(primary, "providers", None):
            raise HostError(400, "bad_request", "primary needs a model, a base_url or a profile with one, and the "
                                                "api_key that profile needs")
        for p in primary.providers:  # type: ignore[attr-defined]
            check_model_url(p.base_url, self.allow_private_models)
        self.storage.set_model(project.id, self.vault.seal(project.id, dict(settings)))

    def model_settings(self, project: Project) -> dict | None:
        """The project's model settings with the keys left out, or None if it has none."""
        sealed = self.storage.model(project.id)
        if not sealed or self.vault is None:
            return None
        settings = self.vault.open(project.id, sealed)
        return {part: {k: v for k, v in p.items() if k != "api_key"} | {"api_key_set": bool(p.get("api_key"))}
                for part, p in settings.items() if p}

    def project_gateway(self, project: Project) -> ModelGateway:
        sealed = self.storage.model(project.id) if self.mode == SERVER else None
        with self._lock:
            known = self._gateways.get(project.id)
            if known is not None and known[0] == sealed:
                return known[1]
        if sealed and self.vault is not None:
            try:
                gateway: ModelGateway = gateway_from_env(provider_env(self.vault.open(project.id, sealed)))
            except VaultError as e:
                log.error("project %s: %s; it speaks through the server's models", project.id, e)
                gateway = self.gateway
        else:
            gateway = self.gateway
        with self._lock:
            self._gateways[project.id] = (sealed, gateway)
        return gateway

    # ------------------------------------------------------------ usage and caps
    def record(self, event: Usage) -> None:
        try:
            self.storage.record([event])
        except Exception:  # metering must never cost a player their line
            log.exception("couldn't record usage")

    def over_cap(self, project: Project) -> str | None:
        caps = project.caps
        if not (caps.calls_per_day or caps.tokens_per_day):
            return None
        calls, tokens = self.storage.today(project.id)
        if caps.calls_per_day and calls >= caps.calls_per_day:
            return "calls_per_day"
        if caps.tokens_per_day and tokens >= caps.tokens_per_day:
            return "tokens_per_day"
        return None

    # ------------------------------------------------------------ sessions
    def _session(self, project: Project, sid: str, game: Game, snapshot: Mapping | None, seed: int) -> Session:
        metered = Metered(self, project, sid, self.project_gateway(project))
        observer = self._observer(project.id, sid)
        mind = Mind(metered, game.voice.validator, cache=ProjectCache(self.storage, project.id) if self.cache else None,
                    observer=observer)
        return Session.restore(game, snapshot, mind=mind) if snapshot else Session.new(game, seed, mind=mind)

    def _observer(self, project: str, sid: str) -> Callable[[str, StatePack, ModelReply | None, Utterance], None]:
        def seen(kind: str, pack: StatePack, reply: ModelReply | None, u: Utterance) -> None:
            self.record(Usage(project, sid, "line", kind, u.source != "fallback", source=u.source))
        return seen

    def open(self, project: Project, gid: str, seed: int = 0, snapshot: Mapping | None = None) -> tuple[str, Live]:
        game = self.game(project, gid)
        if project.caps.max_sessions and self.storage.open_sessions(project.id) >= project.caps.max_sessions:
            raise HostError(503, "full", "The project holds as many sessions as it may; close one first")
        sid = secrets.token_urlsafe(12)
        session = self._session(project, sid, game, snapshot, seed)
        self.storage.create_session(project.id, sid, gid, session.snapshot())
        live = self._hold(sid, Live(session, project.id, gid, 1))
        return sid, live

    def live(self, project: Project, sid: str) -> Live:
        """The session, from memory if it is current there, otherwise from storage."""
        with self._lock:
            live = self._live.get(sid)
            if live is not None:
                self._live.move_to_end(sid)
        if live is not None and live.project != project.id:
            raise Unknown(f"no session {sid!r}")
        if live is not None:
            stored = self.storage.session_version(sid)
            if stored == live.version:
                return live
            self._drop(sid)  # closed, or moved on by another instance
            if stored is None:
                raise Unknown(f"no session {sid!r}")
        found = self.storage.load_session(project.id, sid)
        if found is None:
            raise Unknown(f"no session {sid!r}")
        gid, snapshot, version = found
        session = self._session(project, sid, self.game(project, gid), snapshot, 0)
        return self._hold(sid, Live(session, project.id, gid, version))

    def call(self, project: Project, sid: str, fn: Callable[[Session], Any], saves: bool = True) -> Any:
        """`fn` on the session, one call at a time, saved before it returns if it changes anything."""
        live = self.live(project, sid)
        with live.lock:
            out = fn(live.session)
            if saves:
                self._save(sid, live)
        return out

    def close(self, project: Project, sid: str) -> None:
        live = self.live(project, sid)
        self.storage.delete_session(project.id, sid)
        self._drop(sid)
        live.session.close()

    def _save(self, sid: str, live: Live) -> None:
        with live.saving:
            try:
                live.version = self.storage.save_session(sid, live.session.snapshot(), live.version)
            except Conflict:
                self._drop(sid)
                raise HostError(409, "conflict", "the session moved on elsewhere; call again") from None

    def _hold(self, sid: str, live: Live) -> Live:
        def settled(line: Line) -> None:
            try:
                self._save(sid, live)
            except HostError:
                log.warning("session %s: a line settled after the session moved on elsewhere", sid)
        live.session.on_settle = settled
        with self._lock:
            self._live[sid] = live
            evict = [k for k, v in self._live.items() if not v.session._pending and not v.lock.locked()]
            excess = len(self._live) - self._live_max
        for k in evict[:max(0, excess)]:
            self._drop(k)
        return live

    def _drop(self, sid: str) -> None:
        with self._lock:
            live = self._live.pop(sid, None)
        if live is not None:
            live.session.close()

    def held(self) -> int:
        with self._lock:
            return len(self._live)

    def shutdown(self) -> None:
        for sid in list(self._live):
            self._drop(sid)
        self.storage.close()
