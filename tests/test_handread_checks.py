"""The judge-free checks (rehearsal/checks.py) and the hand-read sample (rehearsal/handread.py)."""

import json
import re

import pytest

from games.crypt_road.content import new_world
from rehearsal import calibrate, checks, handread, measure
from rehearsal.__main__ import RECORDINGS, rehearse
from rehearsal.record import ReplayGateway
from rehearsal.scenarios import scenarios
from thespis.ledger import Claim

NAMES = {"kael": "kael", "brenna": "brenna", "odo": "odo", "mags": "mags"}


def test_words_in_the_players_mouth_are_caught_only_when_the_player_said_nothing():
    w = new_world(1)
    w.ledger.append(0, "insult", "player", "kael", "tavern", Claim("insulted", "player", "kael"))
    assert checks.player_words("You told me you'd pay double.", w, set())  # the player never spoke...
    assert not checks.player_words("You told me you'd pay double.", w, {"e0001"})  # ...but an insult is speech
    assert not checks.player_words("You look tired, traveller.", w, set())


def test_narration_may_say_only_those_it_was_told_of_spoke():
    w = new_world(1)
    told = w.ledger.append(0, "accuse", "kael", "brenna", "guard_post", Claim("robbed", "player", "kael"))
    walked = w.ledger.append(0, "move", "odo", "market", "tavern")
    line = "Kael told Brenna you robbed him, and Odo told her the same."
    assert checks.misattributed(line, w, {told.id, walked.id}, NAMES) == ["odo"]


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    """A judged run's kept lines, from replaying two scenarios with a judge that found nothing."""
    gateway = ReplayGateway(json.loads(RECORDINGS.read_text(encoding="utf-8")))
    _, recorder, _ = rehearse(gateway, [s for s in scenarios() if s.game == "crypt_road"][:3], gateway.claim_check)
    lines = [s for s in recorder.samples if s["source"] == "llm" and s["line"]]
    for s in lines:
        s["claims"], s["categories"] = [], {}
    measure.run_checks(lines, recorder.snapshots)
    stem = tmp_path_factory.mktemp("reports") / "local-qwen3.5-4b"  # a dot in the name, as real ones have
    calibrate.keep(calibrate.sibling(stem, ".lines.json.gz"), "reference", "now", "abc1234", lines, recorder.snapshots)
    return stem


def tick(path, choose):
    """Tick, in each item, the box `choose(item number)` names."""
    out, item = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if m := re.match(r"^## (\d+)\. ", line):
            item = int(m.group(1))
        if line.startswith("- [ ] ") and line[6:].split(":")[0] == choose(item):
            line = "- [x] " + line[6:]
        out.append(line)
    path.write_text("\n".join(out), encoding="utf-8")


def test_a_hand_read_must_be_finished_and_find_nothing_the_checks_missed(run):
    assert handread.verdict(run) is None  # not hand-read yet
    path = handread.make(run)
    text = path.read_text(encoding="utf-8")
    assert path.name == "local-qwen3.5-4b.handread.md" and "What it knew:" in text and "> " in text
    ok, detail = handread.verdict(run)
    assert not ok and "unread" in detail
    tick(path, lambda i: "fine")
    assert handread.verdict(run) == (True, f"{len(handread.read(path))} lines read; nothing the checks missed")
    path.write_text(path.read_text(encoding="utf-8").replace("- [x] fine", "- [ ] fine", 1)
                    .replace("- [ ] hallucination", "- [x] hallucination", 1), encoding="utf-8")
    ok, detail = handread.verdict(run)
    assert not ok and detail == "the reader found what no check flagged: 1: hallucination"
