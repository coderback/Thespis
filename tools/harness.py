"""The harness (the seed of Thespis Rehearsal): play every scripted route on a host and measure what the claims rest on.

    python tools/harness.py https://thespis-production.up.railway.app    # seeds 1 and 4, writes results.md
    python tools/harness.py http://localhost:8000 --seeds 1 --out -       # print the report instead

Two passes over the routes in tools/routes.py, the same ones the acceptance test plays (#11):
  1. Rules: each route on the demo seed with the brain off. Its outcome must match the rules model.
  2. Model: each route on each seed with the brain on. Every run records its /act round trips, every NPC decision and
     line, the replies the validator blocked, and the host's own log of the model calls it caused (GET /dev/calls):
     latency and tokens.

The seed only changes the duel dice, so the default seeds are 1 (the duel is won) and 4 (it is lost); others repeat
one of these exactly and the cache answers them. So that every run also asks the model something new, in each model
run the player puts a question of its own to everyone nearby, right after the first action. Talking changes nothing
in the world, so outcomes are unaffected.

The call log covers every session on the host, so run this when nobody else is playing. Exits 1 if a rules-pass
outcome differs from the rules model.
"""

from __future__ import annotations

import argparse
import math
import random
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from games.crypt_road.content import DEMO_SEED  # noqa: E402
from tools.routes import EXPECTED, ROUTES, ApiError, Session, admin_headers, outcome, play, seed_for  # noqa: E402

QUESTIONS = [  # with OPENERS, a fresh question per model run, so its lines are new to the cache even on a rerun
    "What brings you to the tavern tonight?", "Have you heard anything about the relic?", "Who here would you trust?",
    "Is the road east safe after dark?", "What do you make of Kael?", "Seen the Captain lately?",
    "Anything worth buying at the market?", "Why does everyone want that relic?", "Who keeps the gate these days?",
    "Do you know the way to the crypt?", "What would you do with the relic?", "Who's the most honest soul here?",
    "Any trouble on the bridge lately?", "What's the word on the road?", "Do you owe anyone money?",
    "Who started the last fight in here?", "Would you lie to the Captain?", "What happens to thieves around here?",
    "Who tells the best stories?", "Ever been inside the crypt?", "Is the Captain fair?",
    "What's Kael after, really?", "Who would you never cross?", "How long have you been on this road?",
]
OPENERS = ["", "Tell me honestly, ", "Quietly now, ", "Friend, ", "One question: ", "Before I go, ", "Between us, ",
           "Be straight with me: "]


def fresh_questions(n: int, rng: random.Random) -> list[str]:
    combos = [(o, q) for o in OPENERS for q in QUESTIONS]
    rng.shuffle(combos)
    return [o + q[0].lower() + q[1:] if o else q for o, q in combos[:n]]

ROOT = Path(__file__).resolve().parents[1]
# US$ per 1M tokens (input, output), standard tier. OpenAI's list prices as reported on 22 Sep 2026; Azure's own page
# still showed GPT-6 Luna's price as "in processing" on 4 Oct 2026. Token counts are reported too, so cost can be redone.
PRICES = {"gpt-6-luna": (0.10, 0.50), "gpt-5.4-nano": (0.20, 1.25)}
PRICE_SOURCE = ("OpenAI list prices per 1M tokens: GPT-6 Luna $0.10 in / $0.50 out, GPT-5.4 nano $0.20 in / $1.25 out. "
                "Azure's pricing page listed Luna as \"in processing\" when this ran")
FAULTS = ("model unavailable", "model reply rejected")
BLOCKED = "model reply rejected: "


START, END = "<!-- judged:start -->", "<!-- judged:end -->"  # tools/judge.py's block in results.md


def with_block(text: str, judged: str | None) -> str:
    """`text` with the judged block in it: replacing an old one, or appended."""
    if not judged:
        return text
    if START in text and END in text:
        before, rest = text.split(START, 1)
        return before + judged + rest.split(END, 1)[1]
    return text.rstrip("\n") + "\n\n" + judged + "\n"


def existing_block(text: str) -> str | None:
    if START in text and END in text:
        return START + text.split(START, 1)[1].split(END, 1)[0] + END
    return None


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


class MeteredSession(Session):
    """A session that notes how many model calls each /act caused, from the host's call log. Given a question, it
    asks everyone the player may talk to, once, as soon as there is something in the ledger to talk about."""

    def __init__(self, client, question: str | None = None):
        super().__init__(client)
        self.made: list[int] = []
        self.question = question

    def act(self, verb, target=None, **fields):
        before = call_total(self.client)
        result = super().act(verb, target, **fields)
        self.made.append(call_total(self.client) - before)
        state = result["state"]
        if self.question and state["ledger_tail"] and state["status"] == "playing":
            question, self.question = self.question, None
            for (v, npc), option in self.allowed().items():
                if v == "talk" and option["enabled"]:
                    self.act("talk", npc, text=question)
        return result


def run_route(client, name: str, seed: int, brain: str, question: str | None = None) -> dict:
    before = call_total(client)
    s = MeteredSession(client, question)
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
        "seconds": elapsed, "acts": s.timings, "made": s.made, "phases": state["phase"], "npcs": len(state["npcs"]),
        "cached": sum(d["source"] == "cache" for d in decisions),
        "talked": sum(d["trigger"] == "talk" for d in decisions),
        "asked": len(asked), "decides": sum(d["kind"] == "decide" for d in decisions),
        "lines": Counter(d["source"] for d in decisions if d["line"]),
        "blocked": [why_blocked(d["reason"]) for d in decisions if BLOCKED in d["reason"]],
        "unavailable": sum("model unavailable" in d["reason"] for d in decisions),
        "replay": any("replay: not in the cache" in d["reason"] for d in decisions),
        "calls": calls,
    }


def measure(client, seeds: list[int], rng: random.Random | None = None) -> dict:
    rules = [run_route(client, name, DEMO_SEED, "fallback") for name in ROUTES]
    runs = [(name, seed) for seed in seeds for name in ROUTES]
    questions = fresh_questions(len(runs), rng or random.Random())
    model = [run_route(client, name, seed, "model", q) for (name, seed), q in zip(runs, questions)]
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
    per_call = cost / len(ok) if ok else 0.0
    live_calls = len(calls) + sum(r["cached"] for r in runs)  # each cached answer is a call the cache saved
    timed = [(t, m) for r in runs for t, m in zip(r["acts"], r["made"])]
    turns = sum(r["phases"] * r["npcs"] for r in runs)
    asked = sum(r["asked"] for r in runs)
    blocked = Counter(b for r in runs for b in r["blocked"])
    acts = [t for r in runs for t in r["acts"]]
    lines = sum((r["lines"] for r in runs), Counter())
    return {
        "runs": len(runs), "calls": len(calls), "ok": len(ok), "failed": Counter(c["error"] for c in calls if not c["ok"]),
        "by_model": Counter(_model(c["provider"]) for c in ok), "tokens": tokens, "cost": cost,
        "cost_per_run": cost / len(runs) if runs else 0.0, "calls_per_run": len(calls) / len(runs) if runs else 0.0,
        "live_per_run": live_calls / len(runs) if runs else 0.0,
        "live_cost_per_run": per_call * live_calls / len(runs) if runs else 0.0,
        "with_call_p50": percentile([t for t, m in timed if m], 50), "with_call_p95": percentile([t for t, m in timed if m], 95),
        "no_call_p50": percentile([t for t, m in timed if not m], 50), "no_call_p95": percentile([t for t, m in timed if not m], 95),
        "with_call": sum(1 for _, m in timed if m), "no_call": sum(1 for _, m in timed if not m),
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
    models = ", then ".join(f"{m} ({n} call{'' if n == 1 else 's'})" for m, n in s["by_model"].most_common()) or "none answered"
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
        f"| `/act` round trip when it calls the model, p50 / p95 | **{_ms(s['with_call_p50'])} / "
        f"{_ms(s['with_call_p95'])}** ({s['with_call']} actions) |",
        f"| `/act` round trip with no model call, p50 / p95 | **{_ms(s['no_call_p50'])} / {_ms(s['no_call_p95'])}** "
        f"({s['no_call']} actions) |",
        f"| Cost per run, every call to the model | **${s['live_cost_per_run']:.5f}** "
        f"({s['live_per_run']:.1f} calls per run) |",
        f"| Cost per run as played, with the cache | **${s['cost_per_run']:.5f}** "
        f"({s['calls_per_run']:.1f} calls per run) |",
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
        "- **`/act` round trip:** the time for the harness, over the internet, to get each `/act` answer: what a player "
        "waits. Split by whether the action caused a model call, from the call log's count before and after it.",
        f"- **Cost:** tokens from each call's reported usage, priced at {PRICE_SOURCE}. \"Every call to the model\" "
        "prices each answer the cache gave as one more call at the measured average; \"as played\" is what was spent.",
        "- **Model runs:** right after the first action, the player asks everyone nearby a question of its own, so "
        "every run makes new model calls. Talking changes nothing in the world.",
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
        "Model pass: the brain on. Code makes every choice and the model only words it, so on the demo seed each "
        "outcome matches the rules pass. On other seeds the duel dice differ.",
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
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("host")
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 4])
    parser.add_argument("--out", default=str(ROOT / "results.md"), help="where to write the report; - to print it")
    args = parser.parse_args(argv)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    with httpx.Client(base_url=args.host, timeout=60, headers=admin_headers()) as client:
        results = measure(client, args.seeds)
    text = report(results, args.host, commit)
    if args.out == "-":
        print(text)
    else:
        out = Path(args.out)
        old = out.read_text(encoding="utf-8") if out.exists() else ""
        out.write_text(with_block(text, existing_block(old)), encoding="utf-8", newline="\n")  # keep #37's numbers
        print(f"wrote {args.out}")
        print("\n".join(text.split("\n")[5:16]))
    return 0 if all(r["outcome"] == EXPECTED[r["route"]] for r in results["rules"]) else 1


if __name__ == "__main__":
    sys.exit(main())
