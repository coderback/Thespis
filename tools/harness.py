"""The harness (the seed of Thespis Rehearsal): play every scripted route on a host and measure what the claims rest on.

    python tools/harness.py https://thespis-production.up.railway.app    # seeds 1 2 3, writes results.md
    python tools/harness.py http://localhost:8000 --seeds 1 --out -       # print the report instead

Two passes over the routes in tools/routes.py, the same ones the acceptance test plays (#11):
  1. Rules: each route on the demo seed with the brain off. Its outcome must match the rules model.
  2. Model: each route on each seed with the brain on. Every run records its /act round trips, every NPC decision and
     line, the replies the validator blocked, and the host's own log of the model calls it caused (GET /dev/calls):
     latency and tokens.

The call log covers every session on the host, so run this when nobody else is playing. Exits 1 if a rules-pass
outcome differs from the rules model.
"""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from games.crypt_road.content import DEMO_SEED  # noqa: E402
from tools.routes import EXPECTED, ROUTES, ApiError, Session, outcome, play, seed_for  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# US$ per 1M tokens (input, output), standard tier. OpenAI's list prices as reported on 22 Sep 2026; Azure's own page
# still showed GPT-6 Luna's price as "in processing" on 4 Oct 2026. Token counts are reported too, so cost can be redone.
PRICES = {"gpt-6-luna": (0.10, 0.50), "gpt-5.4-nano": (0.20, 1.25)}
PRICE_SOURCE = ("OpenAI list prices per 1M tokens: GPT-6 Luna $0.10 in / $0.50 out, GPT-5.4 nano $0.20 in / $1.25 out. "
                "Azure's pricing page listed Luna as \"in processing\" when this ran")
FAULTS = ("model unavailable", "model reply rejected")
BLOCKED = "model reply rejected: "


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile; None for no values."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered), max(1, math.ceil(q / 100 * len(ordered)))) - 1]


def why_blocked(reason: str) -> str:
    """The validator's reason, without the specifics: e.g. 'cites e0099, not in its state pack' -> 'cites ids not in
    its state pack'."""
    why = reason.split(BLOCKED, 1)[1]
    for start, label in (("action", "action not allowed"), ("no line", "no line"), ("line is", "line too long"),
                         ("no cites", "no cites"), ("cites", "cites ids not in its state pack"),
                         ("names", "names someone absent from its state pack")):
        if why.startswith(start):
            return label
    return why


def call_total(client) -> int:
    return client.get("/dev/calls", params={"since": 10**12}).json()["total"]


def run_route(client, name: str, seed: int, brain: str) -> dict:
    before = call_total(client)
    s = Session(client)
    s.start(seed_for(name, seed), brain)
    started = time.perf_counter()
    try:
        state, error = play(s, name), None
    except ApiError as e:
        state, error = s.state(), str(e)
    elapsed = time.perf_counter() - started
    calls = client.get("/dev/calls", params={"since": before}).json()["calls"]
    decisions = state["decisions_tail"]
    if decisions and decisions[0]["id"] != "d0001":
        raise RuntimeError(f"{name}: more decisions than the state's tail holds")
    asked = [d for d in decisions if d["kind"] == "decide" and (
        d["source"] != "fallback" or any(f in d["reason"] for f in FAULTS))]
    return {
        "route": name, "seed": seed_for(name, seed), "brain": brain, "outcome": outcome(state), "error": error,
        "seconds": elapsed, "acts": s.timings, "phases": state["phase"], "npcs": len(state["npcs"]),
        "asked": len(asked), "decides": sum(d["kind"] == "decide" for d in decisions),
        "lines": Counter(d["source"] for d in decisions if d["line"]),
        "blocked": [why_blocked(d["reason"]) for d in decisions if BLOCKED in d["reason"]],
        "unavailable": sum("model unavailable" in d["reason"] for d in decisions),
        "replay": any("replay: not in the cache" in d["reason"] for d in decisions),
        "calls": calls,
    }


def measure(client, seeds: list[int]) -> dict:
    rules = [run_route(client, name, DEMO_SEED, "fallback") for name in ROUTES]
    model = [run_route(client, name, seed, "model") for seed in seeds for name in ROUTES]
    return {"rules": rules, "model": model, "seeds": seeds}


# ---------------------------------------------------------------- the report
def _ms(seconds: float | None) -> str:
    return "n/a" if seconds is None else f"{seconds * 1000:.0f} ms"


def _model(provider: str) -> str:
    return provider.rsplit("/", 1)[-1]


def summarise(results: dict) -> dict:
    runs = results["model"]
    calls = [c for r in runs for c in r["calls"]]
    ok = [c for c in calls if c["ok"]]
    tokens: dict[str, list[int]] = {}
    for c in ok:
        t = tokens.setdefault(_model(c["provider"]), [0, 0])
        t[0] += c["prompt_tokens"] or 0
        t[1] += c["completion_tokens"] or 0
    cost = sum(PRICES[m][0] * t[0] / 1e6 + PRICES[m][1] * t[1] / 1e6 for m, t in tokens.items() if m in PRICES)
    turns = sum(r["phases"] * r["npcs"] for r in runs)
    asked = sum(r["asked"] for r in runs)
    blocked = Counter(b for r in runs for b in r["blocked"])
    acts = [t for r in runs for t in r["acts"]]
    lines = sum((r["lines"] for r in runs), Counter())
    return {
        "runs": len(runs), "calls": len(calls), "ok": len(ok), "failed": Counter(c["error"] for c in calls if not c["ok"]),
        "by_model": Counter(_model(c["provider"]) for c in ok), "tokens": tokens, "cost": cost,
        "cost_per_run": cost / len(runs) if runs else 0.0, "calls_per_run": len(calls) / len(runs) if runs else 0.0,
        "turns": turns, "asked": asked, "code_only": (turns - asked) / turns if turns else 0.0,
        "blocked": blocked, "blocked_total": sum(blocked.values()), "answered": len(ok),
        "unavailable": sum(r["unavailable"] for r in runs), "lines": lines,
        "call_p50": percentile([c["latency"] for c in ok], 50), "call_p95": percentile([c["latency"] for c in ok], 95),
        "call_max": max((c["latency"] for c in ok), default=None),
        "act_p50": percentile(acts, 50), "act_p95": percentile(acts, 95), "acts": len(acts),
        "replay": any(r["replay"] for r in runs),
    }


def report(results: dict, host: str, commit: str) -> str:
    s = summarise(results)
    when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    rules_ok = all(r["outcome"] == EXPECTED[r["route"]] for r in results["rules"])
    models = ", then ".join(f"{m} ({n} calls)" for m, n in s["by_model"].most_common()) or "none answered"
    out = [
        "# Results",
        "",
        f"Measured by `tools/harness.py` against **{host}** on {when}, engine at `{commit}`.",
        f"Models: {models}. Seeds: {', '.join(map(str, results['seeds']))}.",
        "",
        "## Headline numbers",
        "",
        "| Measure | Value |",
        "| --- | --- |",
        f"| NPC turns decided by code alone, with no model call | **{s['code_only']:.0%}** "
        f"({s['turns'] - s['asked']} of {s['turns']}) |",
        f"| Invalid model replies blocked by the validator | **{s['blocked_total']}** of {s['answered']} replies |",
        f"| Model call latency, p50 / p95 (on the host) | **{_ms(s['call_p50'])} / {_ms(s['call_p95'])}** "
        f"(max {_ms(s['call_max'])}, {s['ok']} calls) |",
        f"| `/act` round trip, p50 / p95 (from the harness) | **{_ms(s['act_p50'])} / {_ms(s['act_p95'])}** "
        f"({s['acts']} actions) |",
        f"| Cost per run | **${s['cost_per_run']:.5f}** ({s['calls_per_run']:.1f} model calls per run) |",
        f"| Rules routes matching the rules model | **{sum(r['outcome'] == EXPECTED[r['route']] for r in results['rules'])}"
        f" of {len(results['rules'])}** |",
        "",
        "## How each number is counted",
        "",
        "- **NPC turns:** one per NPC per phase that ran, epilogue included (4 NPCs). A turn counts as a model turn when "
        "the model was asked to choose the NPC's action: a decision from the model or the cache, or a fallback the model "
        "caused. Spoken lines are counted separately below.",
        "- **Blocked replies:** model replies the validator rejected, so the NPC used its code choice and template line "
        "instead. Out of every reply the model returned.",
        "- **Model call latency:** each call's time inside the host's gateway, from its own log (`GET /dev/calls`), "
        "successful calls only.",
        "- **`/act` round trip:** the time for the harness, over the internet, to get each `/act` answer. That's what a "
        "player waits, including any model calls the action caused.",
        f"- **Cost:** tokens from each call's reported usage, priced at {PRICE_SOURCE}. Lines served from the cache cost "
        "nothing and aren't counted as calls.",
        "",
        "## Where lines came from (model pass)",
        "",
        "| Source | Lines |",
        "| --- | --- |",
        *[f"| {src} | {n} |" for src, n in sorted(s["lines"].items())],
        "",
    ]
    if s["blocked"]:
        out += ["Blocked replies by reason:", "", *[f"- {why}: {n}" for why, n in s["blocked"].most_common()], ""]
    if s["failed"] or s["unavailable"]:
        out += [f"Failed calls: {dict(s['failed']) or 'none'}. Turns or lines that fell back because the model was "
                f"unavailable: {s['unavailable']}.", ""]
    tok = ", ".join(f"{m}: {t[0]:,} in / {t[1]:,} out" for m, t in s["tokens"].items()) or "none"
    out += [f"Tokens over all {s['runs']} model runs: {tok}. Total cost: ${s['cost']:.4f}.", ""]
    if s["replay"]:
        out += ["**The host had REPLAY=1:** cache misses fell back without a call, so these numbers aren't live.", ""]
    out += [
        "## Route outcomes",
        "",
        "Rules pass: the brain off, the demo seed. Each outcome must match the rules model (`tools/crypt_road_sim.py`).",
        "",
        "| Route | Expected | Got |",
        "| --- | --- | --- |",
        *[f"| {r['route']} | {EXPECTED[r['route']]} | {r['outcome']} {'✓' if r['outcome'] == EXPECTED[r['route']] else '✗'}"
          f"{' (' + r['error'] + ')' if r['error'] else ''} |" for r in results["rules"]],
        "",
        "Model pass: the brain on. The model chooses among the actions the NPC's drives rate close to the best, so an "
        "outcome can differ from the rules model's. On other seeds the duel dice differ too.",
        "",
        "| Route | Seed | Outcome | Model calls | Lines: model / cache / template | Blocked | `/act` p50 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        *[f"| {r['route']} | {r['seed']} | {r['outcome']}{' (error)' if r['error'] else ''} | {len(r['calls'])} | "
          f"{r['lines']['llm']} / {r['lines']['cache']} / {r['lines']['fallback']} | {len(r['blocked'])} | "
          f"{_ms(percentile(r['acts'], 50))} |" for r in results["model"]],
        "",
    ]
    if not rules_ok:
        out += ["**A rules-pass outcome differs from the rules model.**", ""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("host")
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--out", default=str(ROOT / "results.md"), help="where to write the report; - to print it")
    args = parser.parse_args(argv)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    with httpx.Client(base_url=args.host, timeout=60) as client:
        results = measure(client, args.seeds)
    text = report(results, args.host, commit)
    if args.out == "-":
        print(text)
    else:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.out}")
        print("\n".join(text.split("\n")[5:16]))
    return 0 if all(r["outcome"] == EXPECTED[r["route"]] for r in results["rules"]) else 1


if __name__ == "__main__":
    sys.exit(main())
