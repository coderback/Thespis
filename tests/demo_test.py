"""The demo script as the definition of done: every beat's "Must be true" column, checked through the HTTP API.

    pytest tests/demo_test.py                                   # in-process engine (what CI runs)
    DEMO_HOST=https://thespis-production.up.railway.app pytest tests/demo_test.py   # a live host

Against a live host the restart beat uses POST /reload, since a test can't kill the server; locally it starts a
fresh app on the same database.
"""

from __future__ import annotations

import os

import httpx
import pytest

from games.crypt_road import content as C
from tools.routes import EXPECTED, ROUTES, Session, outcome, play, seed_for

HOST = os.environ.get("DEMO_HOST")
ROBBED = {"pred": "robbed", "a": "player", "b": "kael"}
LIE = {"pred": "robbed", "a": "kael", "b": "odo"}


Api = Session  # a thin client for one session, over either the in-process app or a live host


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "demo.sqlite"
    monkeypatch.setenv("DB_PATH", str(path))
    return path


@pytest.fixture
def api(db):
    if HOST:
        with httpx.Client(base_url=HOST, timeout=30) as client:
            yield Api(client)
        return
    from fastapi.testclient import TestClient

    from games.crypt_road.app import app
    with TestClient(app) as client:
        yield Api(client)


def npc(state, npc_id):
    return next(n for n in state["npcs"] if n["id"] == npc_id)


def belief(state, holder, claim):
    return next((b for b in state["beliefs"] if b["npc"] == holder and b["claim"] == claim), None)


def check_every_run(state):
    """The demo script's last rule: every line cites an id, and no decision falls outside its allowed list."""
    for d in state["decisions_tail"]:
        if d["line"]:
            assert d["cites"], f"{d['id']} says {d['line']!r} citing nothing"
        if d["kind"] == "decide":
            assert d["chosen"] in d["allowed"], f"{d['id']} chose outside its allowed list"
        assert d["source"] == "fallback"  # the model is off


def test_demo_route(api, db):
    api.start()

    # Beat 1, phase 0 at the tavern: insult, win the duel, humiliate.
    api.act("insult", "kael")
    duel = api.act("challenge", "kael")
    assert duel["tick"] is None and duel["state"]["pending"] == "duel_won"
    assert {k for k, v in api.allowed().items() if v["enabled"]} == {("humiliate", "kael"), ("spare", "kael")}
    beat1 = api.act("humiliate", "kael")
    s = beat1["state"]
    assert (npc(s, "kael")["drives"]["grudge"], npc(s, "kael")["drives"]["fear"], npc(s, "kael")["drives"]["respect"]) \
        == (6, 2, 0)  # fear 3 after the duel, 2 once the tick runs
    assert s["player"]["coins"] == 40
    for witness in ("mags", "odo"):
        b = belief(s, witness, ROBBED)
        assert (b["conf"], b["truth"]) == (1.0, True)
    assert [d["chosen"] for d in beat1["tick"]["decisions"] if d["npc"] == "kael"] == ["go_to"]
    assert "Laugh now. The road is long." in [r["line"] for r in beat1["replies"]]

    # Beat 2, phase 1: talk to Mags, then move. Kael and Odo have gone ahead, out of sight.
    mags = api.act("talk", "mags", text="What did you make of that?")
    assert mags["replies"][0]["line"] == "Odo saw the whole thing, and Odo talks."
    api.act("move")

    # Beat 3, phase 2 at the market: move. Offscreen, Kael accuses you to Brenna and Odo gossips to her.
    beat3 = api.act("move")
    accuse = next(d for d in beat3["tick"]["decisions"] if d["chosen"] == "accuse:player")
    assert accuse["phase"] == 2 and accuse["cites"]
    s = beat3["state"]
    b = belief(s, "brenna", ROBBED)
    assert b["conf"] == 0.9 and b["evidence"][0]["source"] == "kael"
    assert npc(s, "brenna")["trust_in"]["player"] == -2
    assert any(e["verb"] == "gossip" and e["actor"] == "odo" and e["target"] == "brenna" for e in beat3["events"])
    digest = api.get("/digest?since=2")
    assert "Kael told Brenna that you robbed him." in digest["text"]

    # Beat 4: kill and restart the server, reload. Same phase, positions, beliefs, grudge and decision log.
    before, allowed_before = api.state(), api.allowed()
    if HOST:
        assert api.post("/reload")["state"] == before
    else:
        from fastapi.testclient import TestClient

        from games.crypt_road.app import app
        with TestClient(app) as restarted:  # a new app lifespan on the same database
            again = Api(restarted)
            again.session = api.session
            assert again.state() == before and again.allowed() == allowed_before

    # Beat 5, phase 3 at the guard post: Kael is still there, his line cites the tavern, and the gate is shut.
    assert (before["phase"], before["player"]["loc"], npc(before, "kael")["loc"]) == (3, "guard_post", "guard_post")
    greetings = {r["npc"]: r for r in beat3["replies"]}
    assert greetings["kael"]["line"] == "Told the Captain what you did in the tavern. Enjoy the view."
    assert greetings["brenna"]["cites"] == [b["id"], b["evidence"][0]["event"]]  # the why-chain's first links
    move = allowed_before[("move", None)]
    assert not move["enabled"] and move["reason"] == "Blocked: Brenna's trust in you is -2"

    # Beat 6: bribe twice, tell Brenna robbed(kael, odo), move. Brenna detains Kael; you reach the bridge.
    api.act("bribe", "brenna", amount=20)
    api.act("bribe", "brenna", amount=20)
    lie = api.act("tell_claim", "brenna", claim=LIE)
    s = lie["state"]
    told = belief(s, "brenna", LIE)
    assert (told["conf"], told["truth"]) == (0.9, False)
    assert npc(s, "brenna")["trust_in"]["kael"] == 0
    assert npc(s, "kael")["drives"]["grudge"] == 8
    assert belief(s, "kael", {"pred": "lied", "a": "player", "b": "kael"})["conf"] == 1.0
    assert "Liar! I never touched the peddler!" in [r["line"] for r in lie["replies"]]
    beat6 = api.act("move")
    assert any(d["chosen"] == "detain:kael" and d["phase"] == 3 for d in beat6["tick"]["decisions"])
    assert beat6["state"]["player"]["loc"] == "bridge"

    # Beat 7: phase 4 move, phase 5 take the relic. Epilogue: at phase 6 Odo testifies and the lie is retracted.
    api.act("move")
    win = api.act("take_relic")
    s = win["state"]
    assert (s["status"], s["ended_at"]) == ("won", 5) and len(win["epilogue"]) == 2
    testify = [e for t in win["epilogue"] for e in t["events"] if e["verb"] == "testify"]
    assert testify and testify[0]["phase"] == 6 and testify[0]["actor"] == "odo"
    assert belief(s, "brenna", LIE)["status"] == "retracted"
    assert npc(s, "brenna")["trust_in"]["player"] == -1
    assert api.get("/digest?since=5")["epilogue"]
    check_every_run(s)


@pytest.mark.parametrize("name", list(ROUTES))
def test_route_outcomes_through_the_api(api, name):
    api.start(seed_for(name, C.DEMO_SEED))
    s = play(api, name)
    assert outcome(s) == EXPECTED[name]
    check_every_run(s)
