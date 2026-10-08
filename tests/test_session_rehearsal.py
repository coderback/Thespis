"""Rehearsal for any game (rehearsal/sessions.py): a game file and scenarios, played through sessions as an engine
plays them, with lines asked for provisionally and judged against the world as it stood when each was asked."""

import json
import time
from pathlib import Path

import pytest

from rehearsal import calibrate, handread, measure, sessions
from tests.test_model_voice import FakeModel

ROOT = Path(__file__).resolve().parents[1]
TAVERN = ROOT / "examples" / "tavern" / "game.toml"


class SlowModel(FakeModel):
    """A well-behaved model that takes a moment, so lines arrive provisional and settle later."""

    def complete(self, call_type, messages, schema=None):
        time.sleep(0.2)
        return super().complete(call_type, messages, schema)


SCENARIOS = """
[[scenario]]
name = "insult"
steps = [
  { call = "observe", verb = "insult", actor = "player", target = "garrick", witnesses = ["wren"], claim = { pred = "insulted", a = "player", b = "garrick" } },
  { call = "update", npc = "garrick", nudge = { grudge = 4 } },
  { call = "decide", npc = "garrick", moment = "turn" },
  { call = "tick" },
  { call = "react", npc = "wren", trigger = "talk" },
  { call = "wait", seconds = 0.5 },
  { call = "react", npc = "pip", trigger = "talk" },
]
"""


@pytest.fixture(scope="module")
def played(tmp_path_factory):
    path = tmp_path_factory.mktemp("scenarios") / "scenarios.toml"
    path.write_text(SCENARIOS, encoding="utf-8")
    gid = measure.register(str(TAVERN))
    chosen = sessions.load(path, measure.SESSION_GAMES[gid])
    recorder = sessions.SessionRecorder()
    result = sessions.play(measure.SESSION_GAMES[gid], SlowModel(), chosen, recorder, settle=5)
    return result, recorder


def test_an_engine_that_doesnt_wait_sees_lines_settle_after_the_world_moved_on(played):
    result, _ = played
    m = sessions.measures(result)
    assert (m["asked"], m["provisional"], m["withdrawn"]) == (3, 3, 0)  # Pip walked in at the tick and heard Wren
    assert m["stale"] == 1  # Garrick's line was asked before the tick and settled after it
    assert 0.15 < m["settle_p50"] < 2 and result.acts and result.acts[0][1] == 1


def test_each_line_is_judged_against_the_world_as_it_was_asked(played):
    _, recorder = played
    garrick = next(s for s in recorder.samples if s["npc"] == "garrick")
    snapshot = recorder.snapshots[garrick["snapshot"]]
    assert snapshot["world"]["phase"] == 0  # before the tick that came while the model was answering
    known = measure.facts(garrick, snapshot)
    assert known.knows("e0001") and known.happened(known.world, known.world.ledger.get("e0001").claimed)
    assert "insulted" in measure.vocabulary(garrick["game"]).preds


def test_session_lines_are_checked_kept_and_hand_read(played, tmp_path):
    _, recorder = played
    lines = [s for s in recorder.samples if s["source"] == "llm" and s["line"]]
    measure.run_checks(lines, recorder.snapshots)
    assert all(s["checks"] == [] for s in lines)
    for s in lines:
        s["claims"] = [{"pred": "insulted", "a": "player", "b": "garrick", "happened": True}]
    measure.categorise(lines, recorder.snapshots)
    assert all(s["categories"] == {"grounded": 1} for s in lines)
    stem = tmp_path / "tavern-run"
    calibrate.keep(calibrate.sibling(stem, ".lines.json.gz"), "reference", "now", "abc", lines, recorder.snapshots,
                   {"tavern": str(TAVERN)})
    measure.SESSION_GAMES.clear()  # a later process: the kept file names the game, so it can be judged again
    assert "tavern" in json.dumps(calibrate.load(calibrate.sibling(stem, ".lines.json.gz"))["games"])
    text = handread.make(stem).read_text(encoding="utf-8")
    assert "The player insulted Garrick in the Lantern's taproom." in text


def test_a_scenario_file_with_an_unknown_call_fails_at_load(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text('[[scenario]]\nname = "x"\nsteps = [{ call = "fly" }]\n', encoding="utf-8")
    measure.register(str(TAVERN))
    with pytest.raises(ValueError, match="unknown call 'fly'"):
        sessions.load(path, measure.SESSION_GAMES["tavern"])


def test_the_tavern_scenarios_load():
    measure.register(str(TAVERN))
    chosen = sessions.load(ROOT / "examples" / "tavern" / "scenarios.toml", measure.SESSION_GAMES["tavern"])
    assert len(chosen) == 6 and chosen[0].name == "tavern/insult_and_answer"


@pytest.mark.parametrize("game", ["tavern", "hamlet"])
def test_every_example_scenario_plays_through(game):
    """Each example game's scenario file loads and plays end to end, every call accepted, every line settled."""
    gid = measure.register(str(ROOT / "examples" / game / "game.toml"))
    chosen = sessions.load(ROOT / "examples" / game / "scenarios.toml", measure.SESSION_GAMES[gid])
    result = sessions.play(measure.SESSION_GAMES[gid], FakeModel(), chosen, sessions.SessionRecorder(), settle=5,
                           pace=0)
    spoken = [x for x in result.lines if not x.get("silent")]
    assert spoken and all(x["status"] == "final" for x in spoken), result.lines
    assert {x["scenario"].split("/")[1] for x in result.lines} == {sc.name.split("/")[1] for sc in chosen}
