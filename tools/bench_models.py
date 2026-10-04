"""Benchmark each configured model on real state packs: latency and how often its reply passes the validator.

    python tools/bench_models.py             # 20 calls per model, from the LLM_* and LLM_BACKUP_* settings in .env
    python tools/bench_models.py --calls 40

It plays the demo route in-process with a stand-in model to collect the state packs the real game builds (every
decision and line the model would be asked for), then sends them in turn to each provider on its own: no backup, no
cache. A pick is valid when the reply passes the same validator the game uses. Prints a markdown table for
docs/models.md. Keys are read from the environment and never printed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

from games.crypt_road import rules, voice  # noqa: E402
from games.crypt_road.content import new_world  # noqa: E402
from thespis.expression import StatePack  # noqa: E402
from thespis.gateway import ModelReply, OpenAICompatGateway, gateway_from_env  # noqa: E402
from tools.harness import percentile  # noqa: E402
from tools.warm_cache import ROUTE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class Recorder:
    """A stand-in model that answers nothing, so every NPC falls back, while the packs it was offered are kept."""

    providers = ("recorder",)
    models = ("recorder",)

    def __init__(self):
        self.packs: list[tuple[str, StatePack]] = []

    def complete(self, call_type, messages) -> ModelReply | None:
        return None

    def complete_many(self, calls):
        return [None for _ in calls]


def demo_packs() -> list[tuple[str, StatePack]]:
    """Every (call type, state pack) the demo route asks the model for, in order."""
    recorder, packs = Recorder(), []
    original = voice.pack_for

    def recording(*args, **kwargs):
        pack = original(*args, **kwargs)
        packs.append(("decide" if pack.allowed else "react", pack))
        return pack

    voice.pack_for = recording
    try:
        w = new_world(1)
        for step in ROUTE:
            rules.act(w, step["verb"], step.get("target"), step.get("claim"), step.get("amount"), step.get("text"),
                      gateway=recorder)
    finally:
        voice.pack_for = original
    return packs


def bench(provider, packs, calls: int, transport=None) -> dict:
    gateway = OpenAICompatGateway([provider], transport=transport)
    valid, problems = 0, {}
    try:
        for i in range(calls):
            kind, pack = packs[i % len(packs)]
            reply = gateway.complete(kind, pack.messages(kind))
            problem = "no reply" if reply is None else voice.VALIDATOR.problem(reply.data, pack, kind)
            if problem is None:
                valid += 1
            else:
                key = problem.split(",")[0].split(" is ")[0]
                problems[key] = problems.get(key, 0) + 1
    finally:
        gateway.close()
    ok = [c.latency for c in gateway.calls if c.ok]
    return {"model": provider.model, "calls": calls, "answered": len(ok), "valid": valid, "problems": problems,
            "p50": percentile(ok, 50), "p95": percentile(ok, 95), "max": max(ok, default=None),
            "decides": sum(k == "decide" for k, _ in (packs[i % len(packs)] for i in range(calls)))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--calls", type=int, default=20)
    args = parser.parse_args(argv)
    load_dotenv(ROOT / ".env")
    providers = gateway_from_env().providers
    if not providers:
        print("No models configured: set LLM_* (and LLM_BACKUP_*) in .env")
        return 1
    packs = demo_packs()
    print(f"{len(packs)} state packs from the demo route ({sum(k == 'decide' for k, _ in packs)} decisions)\n")
    print("| Model | Calls (decisions) | Answered | Valid picks | p50 | p95 | Max | Rejections |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for p in providers:
        r = bench(p, packs, args.calls)
        ms = lambda s: "n/a" if s is None else f"{s * 1000:.0f} ms"  # noqa: E731
        print(f"| {r['model']} | {r['calls']} ({r['decides']}) | {r['answered']} | {r['valid'] / r['calls']:.0%} | "
              f"{ms(r['p50'])} | {ms(r['p95'])} | {ms(r['max'])} | {r['problems'] or 'none'} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
