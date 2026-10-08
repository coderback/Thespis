"""Every route plays to the outcome recorded in tests/outcomes.json (tools.outcomes), beliefs included.

A change that means to alter what happens updates the record in the same PR: `python -m tools.outcomes` shows the
difference, and `python -m tools.outcomes --update` records it.
"""

import json

from tools.outcomes import BASELINE, differences, outcomes


def test_every_route_plays_as_recorded():
    diff = differences(json.loads(BASELINE.read_text(encoding="utf-8")), outcomes())
    assert not diff, "\n".join(diff[:20])
