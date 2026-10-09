"""Rehearsal for the player's words (rehearsal/words.py), as CI holds it: no forbidden change, ever."""

import pytest

from rehearsal import words
from thespis.ledger import Claim


def test_the_notation_reads_both_ways():
    assert words.parse("tell !paid(pip, garrick)") == ("tell", {"claim": Claim("paid", "pip", "garrick", neg=True)})
    assert words.parse("pay 15") == ("pay", {"amount": 15}) and words.parse("none") is None
    assert words.notation("tell", {"to": "wren", "claim": Claim("insulted", "garrick", "pip")}) == \
        "tell insulted(garrick, pip)"


def test_every_expected_outcome_is_one_the_engine_can_apply():
    for book in words.books():
        for line in book.lines:
            for e in line.expect:
                reading = words.parse(e)
                assert reading is None or reading[0] in book.apply, (line.id, e)


def test_with_no_model_nothing_changes_that_shouldnt():
    outcomes = words.run(words.books())
    forbidden = [(o.line.id, o.done) for o in outcomes if o.verdict == "forbidden"]
    assert forbidden == []
    assert words.summary(outcomes)["precision"] == 1.0


@pytest.mark.skipif(not words.RECORDINGS.exists(), reason="no recordings yet")
def test_the_recorded_reader_reads_every_line_as_it_did():
    outcomes, problems = words.replay()
    assert problems == []
    assert words.summary(outcomes)["forbidden"] == 0
