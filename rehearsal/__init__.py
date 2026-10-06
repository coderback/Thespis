"""Thespis Rehearsal: the paper's instrument as a release gate (docs/cast-review.md).

It plays fixed scenarios of both games in-process and measures what the NPCs said: refusals, lines that leak,
hallucinate or contradict what the speaker knows, latency and cost. On every pull request, CI replays recorded
replies with no network and checks that every scenario still goes as recorded. Run it with python -m rehearsal.
"""
