"""#4: the model benchmark sends the demo route's real state packs and counts replies that pass the validator."""

import json

import httpx

from tests.test_model_voice import FakeModel
from thespis.gateway import Provider
from tools import bench_models


def test_the_benchmark_uses_the_demo_routes_state_packs():
    packs = bench_models.demo_packs()
    assert len(packs) == 15 and sum(kind == "act" for kind, _ in packs) == 4  # the route's 15 model calls
    assert {p.npc for _, p in packs} == {"kael", "mags", "brenna", "odo"}


def test_the_benchmark_counts_valid_picks():
    def answer(request):
        pack = json.loads(json.loads(request.content)["messages"][1]["content"])
        data = FakeModel.good("act" if "DOING" in pack else "react", pack)
        if "DOING" in pack:
            data["cites"] = ["e99"]  # every action's line cites a reference its pack doesn't have
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(data)}}]})

    r = bench_models.bench(Provider("p", "https://primary.test/v1", "k", "m"), bench_models.demo_packs(), 20,
                           transport=httpx.MockTransport(answer))
    assert (r["calls"], r["answered"], r["acts"]) == (20, 20, 5)
    assert r["valid"] == 15 and r["problems"] == {"cites e99": 5}
