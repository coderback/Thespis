"""Before the Ice Goes Out in the browser, for playtests, beside the other games on one URL:

- /ice/          the Godot game's web build (built into the image by the Dockerfile); a friend's link is /ice/?seed=19
- /thespis/v1    the Thespis API the game talks to: Thespis's own, on a host of its own, with before-the-ice's
                 coldwater.toml loaded and no model, so the town speaks its written lines, the same for every player on
                 a seed. At most ICE_MAX_SESSIONS weeks are open at once (the oldest goes to make room). Nobody may put a
                 game on it or set its models: the game's own PUT of coldwater is answered from what's loaded.
- /ice/record    where the game sends the week's record as it goes (each morning and at the steamer), a file each on
                 the volume; /ice/records lists them and fetches one, for the admin token only.

It's on when the web build is in the image; ICE_PLAYTEST=0 turns it off.
"""

import json
import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from games.hosting import ApiError, db_path, env_int, log, require_admin

ROOT = Path(__file__).resolve().parents[2]
GAME = ROOT / "games" / "before-the-ice" / "coldwater.toml"
WEB = ROOT / "games" / "ice" / "web"  # the Dockerfile puts the export here
RECORD_MAX = 2_000_000  # characters, each of the page and the JSON
RECORDS_MAX = 5000  # files kept; past that, new weeks aren't kept
NAME = re.compile(r"^[A-Za-z0-9_-]{1,80}$")

router = APIRouter()


def enabled() -> bool:
    return (WEB / "index.html").exists() and os.environ.get("ICE_PLAYTEST", "1").strip() != "0"


def records_dir() -> Path:
    return db_path().parent / "playtest"


class Record(BaseModel):
    name: str = Field(description="The week's name, the same each time the week is sent: <stamp>-seed<N>-<random>")
    md: str = Field(description="The week as a page")
    json_: str = Field(alias="json", description="The same, as JSON")


@router.get("/ice", include_in_schema=False)
def ice_slash(request: Request):
    query = request.url.query
    return RedirectResponse("/ice/" + (f"?{query}" if query else ""))


@router.post("/ice/record")
def put_record(body: Record):
    """A week's record, sent again as it grows: each send replaces the last."""
    if not enabled():
        raise ApiError(404, "not_found", "Not found")
    if not NAME.match(body.name):
        raise ApiError(400, "bad_request", "The name may hold letters, digits, - and _ only")
    if len(body.md) > RECORD_MAX or len(body.json_) > RECORD_MAX:
        raise ApiError(413, "too_large", "That record is too long")
    try:
        json.loads(body.json_)
    except ValueError:
        raise ApiError(400, "bad_request", "The record's JSON doesn't parse") from None
    folder = records_dir()
    folder.mkdir(parents=True, exist_ok=True)
    page = folder / f"{body.name}.md"
    if not page.exists() and sum(1 for _ in folder.glob("*.md")) >= RECORDS_MAX:
        raise ApiError(507, "full", "No room for more records")
    page.write_text(body.md, encoding="utf-8")
    (folder / f"{body.name}.json").write_text(body.json_, encoding="utf-8")
    log.info("playtest record %s (%d characters)", body.name, len(body.md))
    return {"name": body.name}


@router.get("/ice/records", dependencies=[Depends(require_admin)])
def list_records():
    """Every week's record, newest first."""
    folder = records_dir()
    pages = sorted(folder.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True) if folder.exists() else []
    return [{"name": p.stem, "bytes": p.stat().st_size, "modified": int(p.stat().st_mtime)} for p in pages]


@router.get("/ice/records/{file}", dependencies=[Depends(require_admin)])
def get_record(file: str):
    """One record: <name>.md or <name>.json."""
    stem, _, ext = file.rpartition(".")
    path = records_dir() / file
    if ext not in ("md", "json") or not NAME.match(stem) or not path.exists():
        raise ApiError(404, "not_found", "No such record")
    return FileResponse(path, media_type="text/markdown" if ext == "md" else "application/json")


class _Front:
    """In front of the Thespis API. No game may be put or removed and no model set; the game's own PUT of the game it
    was built with is answered as done, since that game is loaded already.

    The host runs as a sidecar, for what a sidecar does at its limit: it drops the oldest session nobody is playing,
    and a closed tab never closes its week. A sidecar also answers only requests addressed to localhost, to keep a web
    page from reaching the sidecar on a player's own machine (DNS rebinding); this one is public on purpose, so each
    request is passed on as addressed to localhost."""

    def __init__(self, app, game_id: str, game_json: bytes):
        self.app, self.game_id, self.game_json = app, game_id, game_json

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope = {**scope, "headers": [(k, b"localhost" if k == b"host" else v) for k, v in scope["headers"]]}
        path, root = scope.get("path", ""), scope.get("root_path", "")
        path = path[len(root):] if root and path.startswith(root) else path  # the path inside the mount
        if scope["type"] == "http" and scope["method"] in ("PUT", "DELETE", "POST") and \
                path.startswith(("/v1/games", "/v1/project")):
            ours = scope["method"] == "PUT" and path == f"/v1/games/{self.game_id}"
            status, body = (200, self.game_json) if ours else \
                (403, b'{"error": "forbidden", "reason": "this server plays one game"}')
            await send({"type": "http.response.start", "status": status,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


def _thespis() -> object:
    from thespis.gateway import NoModel
    from thespis.host import SIDECAR, Host
    from thespis.server import create_app
    from thespis.session import Game
    from thespis.storage import storage

    game = Game.load(str(GAME))
    folder = db_path().parent
    folder.mkdir(parents=True, exist_ok=True)
    most = env_int("ICE_MAX_SESSIONS", 40)
    host = Host(storage(str(folder / "ice.sqlite")), {game.id: game}, NoModel(), mode=SIDECAR, max_sessions=most)
    log.info("before the ice: the web build at /ice/, Thespis at /thespis, %d weeks at once", most)
    return _Front(create_app(host=host), game.id, json.dumps({"id": game.id}).encode())


def install(app: FastAPI) -> None:
    """The routes always (they answer 404 while it's off); the API and the build only when it's on."""
    app.include_router(router)
    if enabled():
        app.mount("/thespis", _thespis(), name="thespis")
        app.mount("/ice", StaticFiles(directory=WEB, html=True), name="ice")
