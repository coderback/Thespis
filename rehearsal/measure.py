"""What a live rehearsal measures, and the gate one rehearsal must pass against another.

- Refusals: every model reply the validator or the moderator refused, by reason. Protocol refusals are the ones a
  schema could prevent (an action not offered, a missing or unknown cite, no line, a line too long); the rest are
  about content (a name the NPC can't know of, an amount nobody offered).
- Claims: a judge model from another vendor extracts what a sample of the lines asserts (thespis.claims); code
  checks each claim against the world as it stood. Per line: does it leak, hallucinate or contradict itself?
  Each rate has a 95% bootstrap interval.
- Latency: each model call's time, by call type, and each action's time when it called the model, in-process.
- Cost: tokens from each call's reported usage, at tools/harness.py's prices, per scenario played.
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import random
from collections import Counter
from collections.abc import Mapping
from importlib import import_module

from rehearsal.record import refusal
from thespis.claims import BAD, ClaimVocabulary, Facts, extraction_messages, parse_claims, score
from thespis.gateway import OpenAICompatGateway, Provider, provider_from_env
from thespis.world import World
from tools.harness import PRICES, percentile

BOOT = 2000
GATE = {"protocol": 0.01, "p95": 1.10}  # the most a new rehearsal may give: refusals per reply, p95 against the base
PROTOCOL = ("action ", "no line", "line is ", "no cites", "cites ", "states something without citing")
# Each judge reasons a little: DeepSeek V4 Pro missed the leak this metric exists to catch without thinking (paper-m1).
JUDGE_EXTRA = {"deepseek-v4-pro": {"reasoning_effort": "low", "max_tokens": 4000}}
GAMES = {"crypt_road": "games.crypt_road.claims", "manor": "games.manor.claims"}


def protocol(reason: str) -> bool:
    return reason.startswith(PROTOCOL)


# ---------------------------------------------------------------- the judge
def judge_from_env(name: str, env: Mapping[str, str] | None = None) -> Provider | None:
    """JUDGE_<NAME>_* (BASE_URL, API_KEY, MODEL, optional EXTRA), with room to think and no randomness."""
    p = provider_from_env(os.environ if env is None else env, f"JUDGE_{name.upper()}_")
    if p is None:
        return None
    base = p.base_url.rstrip("/").removesuffix("/chat/completions")  # the full endpoint pasted as the base URL
    extra = {"max_tokens": 800, "temperature": 0, **JUDGE_EXTRA.get(p.model.lower(), {}), **p.extra}
    return dataclasses.replace(p, base_url=base, extra=extra)


def vocabulary(game: str) -> ClaimVocabulary:
    return import_module(GAMES[game]).VOCABULARY


def facts(sample: dict, snapshot: dict) -> Facts:
    """What the speaker could know when it spoke. The narrator knows exactly the events it was told about."""
    module, w = import_module(GAMES[sample["game"]]), World.from_json(snapshot)
    if sample["npc"] == "narrator":
        ids = set(sample["ids"])
        return dataclasses.replace(module.facts(w, "narrator"), knows=lambda event_id: event_id in ids)
    return module.facts(w, sample["npc"])


def extract(gateway, samples: list[dict], progress=print) -> None:
    """Give each sample the claims the judge says its line makes ("claims"), or None if the judge gave none."""
    batch = 8
    for start in range(0, len(samples), batch):
        chunk = samples[start:start + batch]
        calls = [("extract", extraction_messages(vocabulary(s["game"]), s["npc"], s["name"], s["situation"],
                                                 s["here"], s["line"]), None) for s in chunk]
        for s, reply in zip(chunk, gateway.complete_many(calls)):
            s["claims"] = parse_claims(reply.data) if reply is not None else None
        progress(f"  judged {min(start + batch, len(samples))} of {len(samples)} lines")


def categorise(samples: list[dict], snapshots: dict[str, dict]) -> None:
    for s in samples:
        if s.get("claims") is None:
            continue
        counts = score(vocabulary(s["game"]), s["claims"], facts(s, snapshots[s["snapshot"]]), s["asserting"])
        s["categories"] = dict(counts)


# ---------------------------------------------------------------- numbers
def rate(flags: list[bool], seed: int = 0) -> dict:
    """The proportion, its 95% bootstrap interval, and n."""
    n = len(flags)
    if not n:
        return {"p": None, "lo": None, "hi": None, "n": 0}
    rng = random.Random(seed)
    boots = sorted(sum(rng.choices(flags, k=n)) / n for _ in range(BOOT))
    return {"p": sum(flags) / n, "lo": boots[int(0.025 * BOOT)], "hi": boots[int(0.975 * BOOT) - 1], "n": n}


def difference(base: list[bool], new: list[bool], seed: int = 0) -> dict:
    """new's rate minus base's, with a 95% bootstrap interval."""
    if not base or not new:
        return {"d": None, "lo": None, "hi": None}
    rng = random.Random(seed)
    boots = sorted(sum(rng.choices(new, k=len(new))) / len(new) - sum(rng.choices(base, k=len(base))) / len(base)
                   for _ in range(BOOT))
    return {"d": sum(new) / len(new) - sum(base) / len(base), "lo": boots[int(0.025 * BOOT)],
            "hi": boots[int(0.975 * BOOT) - 1]}


def line_flags(samples: list[dict]) -> dict[str, list[bool]]:
    judged = [s["categories"] for s in samples if "categories" in s]
    flags = {k: [c.get(k, 0) > 0 for c in judged] for k in (*BAD, "lie", "false_belief")}
    flags["any_bad"] = [any(c.get(k, 0) for k in BAD) for c in judged]
    return flags


def summary(samples: list[dict], calls: list, acts: list[tuple[float, int]], scenarios: int) -> dict:
    """Everything but the claims: refusals, sources, latency, tokens and cost."""
    reasons = Counter(r for s in samples if (r := refusal(s["note"])))
    ok = [c for c in calls if c.ok]
    by_type: dict[str, list[float]] = {}
    for c in ok:
        by_type.setdefault(c.call_type, []).append(c.latency)
    tokens: dict[str, list[int]] = {}
    for c in ok:
        t = tokens.setdefault(c.provider.rsplit("/", 1)[-1], [0, 0])
        t[0] += c.prompt_tokens or 0
        t[1] += c.completion_tokens or 0
    cost = sum(PRICES[m][0] * t[0] / 1e6 + PRICES[m][1] * t[1] / 1e6 for m, t in tokens.items() if m in PRICES)
    timed = [t for t, made in acts if made]
    return {
        "scenarios": scenarios, "replies": len(samples),
        "sources": dict(Counter(s["source"] for s in samples)),
        "refused": dict(reasons.most_common()),
        "protocol_refusals": sum(n for r, n in reasons.items() if protocol(r)),
        "calls": len(calls), "failed": dict(Counter(c.error for c in calls if not c.ok)),
        "call_latency": {k: {"p50": percentile(v, 50), "p95": percentile(v, 95), "n": len(v)}
                         for k, v in sorted(by_type.items())},
        "act_latency": {"p50": percentile(timed, 50), "p95": percentile(timed, 95), "n": len(timed)},
        "tokens": tokens, "cost": cost, "cost_per_scenario": cost / scenarios if scenarios else 0.0,
    }


def judged(samples: list[dict], judge: str | None) -> dict:
    flags = line_flags(samples)
    claims = Counter()
    for s in samples:
        claims.update(s.get("categories", {}))
    return {"judge": judge, "sampled": len(samples), "judged": len(flags["any_bad"]),
            "rates": {k: rate(v) for k, v in flags.items()}, "flags": flags, "claims": dict(claims),
            "bad_lines": [{"scenario": s["scenario"], "npc": s["npc"], "line": s["line"],
                           "categories": s["categories"]} for s in samples
                          if any(s.get("categories", {}).get(k) for k in BAD)]}


# ---------------------------------------------------------------- the gate
def gate(base: dict, new: dict) -> list[tuple[str, bool, str]]:
    """(check, passed, detail) for each part of Phase 2's gate (docs/cast-review.md).

    At the hundred or so lines a rehearsal judges, a rate's interval is several points wide, so "no worse" means not
    worse with 95% confidence: the difference's interval must reach zero. The detail shows the interval, so a change
    that is probably worse, though not surely, is still plain to see.
    """
    out = []
    replies = new["summary"]["replies"]
    share = new["summary"]["protocol_refusals"] / replies if replies else 0.0
    out.append(("protocol refusals near zero", share <= GATE["protocol"],
                f"{new['summary']['protocol_refusals']} of {replies} replies ({share:.1%}); "
                f"base {base['summary']['protocol_refusals']} of {base['summary']['replies']}"))
    for k in ("leak", "hallucination"):
        b, n = base["claims"]["flags"].get(k, []), new["claims"]["flags"].get(k, [])
        d = difference(b, n)
        ok = d["lo"] is not None and d["lo"] <= 0  # failed only when it is worse with 95% confidence
        detail = "not judged" if d["d"] is None else \
            f"{_pct(sum(n) / len(n))} vs {_pct(sum(b) / len(b))}: {d['d']:+.1%} [{d['lo']:+.1%}, {d['hi']:+.1%}]"
        out.append((f"{k} no worse (n={len(n)} vs {len(b)})", ok, detail))
    bp, np_ = base["summary"]["act_latency"]["p95"], new["summary"]["act_latency"]["p95"]
    ok = bp is not None and np_ is not None and np_ <= bp * GATE["p95"]
    out.append(("act p95 no worse", ok, f"{_ms(np_)} vs {_ms(bp)}"))
    return out


# ---------------------------------------------------------------- the report
def _pct(p: float | None) -> str:
    return "n/a" if p is None or (isinstance(p, float) and math.isnan(p)) else f"{p:.1%}"


def _ms(s: float | None) -> str:
    return "n/a" if s is None else f"{s * 1000:.0f} ms"


def _rate(r: dict) -> str:
    return "n/a" if not r["n"] else f"{_pct(r['p'])} [{_pct(r['lo'])}, {_pct(r['hi'])}] (n={r['n']})"


def markdown(report: dict) -> str:
    s, c = report["summary"], report["claims"]
    out = [
        f"# Rehearsal {report['when']}",
        "",
        f"Engine `{report['commit']}`, prompts {report['prompts']}. Speaker: {', '.join(report['models'])}. "
        f"{s['scenarios']} scenarios, {s['replies']} model replies, {s['calls']} calls.",
        "",
        "| Measure | Value |",
        "| --- | --- |",
        f"| Protocol refusals | **{s['protocol_refusals']}** of {s['replies']} replies |",
        f"| All refusals | {sum(s['refused'].values())} |",
        f"| Lines with a leak | {_rate(c['rates']['leak'])} |",
        f"| Lines with a hallucination | {_rate(c['rates']['hallucination'])} |",
        f"| Lines with a contradiction | {_rate(c['rates']['contradiction'])} |",
        f"| Lines with any of the three | {_rate(c['rates']['any_bad'])} |",
        f"| Action with a model call, p50 / p95 | {_ms(s['act_latency']['p50'])} / {_ms(s['act_latency']['p95'])} "
        f"({s['act_latency']['n']} actions) |",
        *[f"| `{k}` call, p50 / p95 | {_ms(v['p50'])} / {_ms(v['p95'])} ({v['n']} calls) |"
          for k, v in s["call_latency"].items()],
        f"| Cost per scenario | ${s['cost_per_scenario']:.5f} |",
        "",
        f"Claims judged by {c['judge'] or 'nobody'}: {c['judged']} of {c['sampled']} sampled lines. "
        f"Claims by category: {c['claims'] or 'none'}.",
        "",
    ]
    if s["refused"]:
        out += ["Refusals by reason:", "", *[f"- {r}: {n}" for r, n in s["refused"].items()], ""]
    if s["failed"] or s.get("unanswered"):
        out += [f"Failed calls: {s['failed'] or 'none'}; lines that fell back with no answer: {s.get('unanswered', 0)}.",
                ""]
    if c["bad_lines"]:
        out += ["Lines with a leak, hallucination or contradiction:", ""]
        out += [f"- {b['scenario']}, {b['npc']}: \"{b['line']}\" {b['categories']}" for b in c["bad_lines"]]
        out.append("")
    return "\n".join(out)


def dumps(report: dict) -> str:
    return json.dumps(report, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def judge_gateway(provider: Provider) -> OpenAICompatGateway:
    return OpenAICompatGateway([provider], timeout=120)
