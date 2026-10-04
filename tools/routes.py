"""The scripted routes through The Crypt Road, played over the HTTP API: shared by the acceptance test and the harness.

Each route is a few steps from the start. After them the player heads for the crypt: take the relic on arrival, move
when the gate allows, otherwise wait. EXPECTED is how each route ends on the demo seed with the fallback brain, as the
rules model (tools/crypt_road_sim.py) predicts.
"""

from __future__ import annotations

import time

from games.crypt_road import content as C

LIE = {"pred": "robbed", "a": "kael", "b": "odo"}

ROUTES = {
    "rush": [],
    "provoke_pay": ["provoke", "move", "move", "pay"],
    "provoke_no_pay": ["provoke", "move", "move"],
    "frame": ["provoke", "move", "move", "bribe", "bribe", "lie"],
    "lie_unpaid": ["provoke", "move", "move", "lie"],
    "spare": ["insult", "challenge", "spare"],
    "duel_lost": ["insult", "challenge"],
    "provoke_wait": ["provoke", "wait", "move", "move", "pay"],
}
EXPECTED = {
    "rush": "won@4",
    "provoke_pay": "won@5",
    "provoke_no_pay": "lost@5",
    "frame": "won@5",
    "lie_unpaid": "lost@5",
    "spare": "won@5",
    "duel_lost": "lost@4",
    "provoke_wait": "lost@5",
}


class ApiError(RuntimeError):
    pass


_pool: dict[tuple[int, int], str] = {}  # (client, seed) -> a session the tools reset rather than open anew


def fresh_session(client, seed: int) -> str:
    """A session at the start of the race on `seed`. The tools reuse one per seed, resetting it, so a harness run
    doesn't use up the host's limit of new sessions per IP (#24)."""
    key = (id(client), seed)
    if key in _pool and client.post("/reset", headers={"X-Session": _pool[key]}).status_code == 200:
        return _pool[key]
    r = client.post("/session", json={"seed": seed})
    if r.status_code != 200:
        raise ApiError(f"POST /session: {r.status_code} {r.text}")
    _pool[key] = r.json()["session"]
    return _pool[key]


class Session:
    """One session over an httpx.Client or a TestClient. Every /act's round-trip time is kept in `timings`."""

    def __init__(self, client):
        self.client = client
        self.session = None
        self.timings: list[float] = []

    def start(self, seed: int = C.DEMO_SEED, brain: str = "fallback") -> dict:
        self.session = fresh_session(self.client, seed)
        self.post("/dev/brain", {"mode": brain})
        return self.state()

    def get(self, path: str) -> dict:
        return self._check(self.client.get(path, headers={"X-Session": self.session}))

    def post(self, path: str, body: dict | None = None) -> dict:
        return self._check(self.client.post(path, json=body or {}, headers={"X-Session": self.session}))

    def act(self, verb: str, target: str | None = None, **fields) -> dict:
        started = time.perf_counter()
        result = self.post("/act", {"verb": verb, "target": target, **fields})
        self.timings.append(time.perf_counter() - started)
        return result

    def state(self) -> dict:
        return self.get("/state")

    def allowed(self) -> dict:
        return {(v["verb"], v["target"]): v for v in self.get("/allowed")["verbs"]}

    @staticmethod
    def _check(r) -> dict:
        if r.status_code != 200:
            raise ApiError(f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text}")
        return r.json()


def losing_seed(start: int = C.DEMO_SEED) -> int:
    """The first seed from `start` on which the player loses the first duel."""
    s = start
    while C.dice(s, "challenge:1") < C.DUEL_WIN_CHANCE:
        s += 1
    return s


def seed_for(name: str, seed: int) -> int:
    return losing_seed(seed) if name == "duel_lost" else seed


def npc(state: dict, npc_id: str) -> dict:
    return next(n for n in state["npcs"] if n["id"] == npc_id)


def provoke(s: Session) -> None:
    s.act("insult", "kael")
    if s.act("challenge", "kael")["state"]["pending"] == "duel_won":
        s.act("humiliate", "kael")


def advance(s: Session) -> dict:
    """Head for the crypt: take the relic on arrival, move when the gate allows, otherwise wait."""
    for _ in range(20):
        state = s.state()
        if state["status"] != "playing":
            return state
        allowed = s.allowed()
        if allowed[("take_relic", None)]["enabled"]:
            s.act("take_relic")
        else:
            s.act("move" if allowed[("move", None)]["enabled"] else "wait")
    return s.state()


def play(s: Session, name: str) -> dict:
    """Play a started session along a route to the end of the race, and return the final state."""
    for step in ROUTES[name]:
        if step == "provoke":
            provoke(s)
        elif step == "pay":
            if npc(s.state(), "brenna")["trust_in"]["player"] < 0:
                s.act("bribe", "brenna", amount=C.FINE)
        elif step == "lie":
            s.act("tell_claim", "brenna", claim=LIE)
        elif step == "bribe":
            if s.state()["player"]["coins"] >= C.FINE:  # after a lost duel there's no purse to pay with
                s.act("bribe", "brenna", amount=C.FINE)
        elif step in ("insult", "challenge", "spare"):
            if step != "spare" or s.state()["pending"] == "duel_won":
                s.act(step, "kael")
        else:
            s.act(step)
    return advance(s)


def outcome(state: dict) -> str:
    return f"{state['status']}@{state['ended_at']}"
