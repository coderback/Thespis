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
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from importlib import import_module

from rehearsal import checks
from rehearsal.record import refusal
from thespis.claims import BAD, ClaimVocabulary, Facts, categorize, extraction_messages, label, parse_claims, score
from thespis.gateway import OpenAICompatGateway, Provider, provider_from_env
from thespis.profiles import PROFILES
from thespis.world import World
from tools.harness import PRICES, percentile

BOOT = 2000
GATE = {"protocol": 0.01, "p95": 1.10}  # the most a new rehearsal may give: refusals per reply, p95 against the base
PROTOCOL = ("action ", "no line", "line is ", "no cites", "cites ", "states something without citing")
# Each judge reasons a little: DeepSeek V4 Pro missed the leak this metric exists to catch without thinking (paper-m1).
JUDGE_EXTRA = {"deepseek-v4-pro": {"reasoning_effort": "low", "max_tokens": 4000}}
GAMES = {"crypt_road": "games.crypt_road.claims", "manor": "games.manor.claims"}
REFERENCE_JUDGES = frozenset({"DeepSeek-V4-Pro"})  # the judge others are calibrated against (rehearsal/calibrate.py)


def protocol(reason: str) -> bool:
    return reason.startswith(PROTOCOL)


def checked(reason: str) -> str:
    """Why the claim check refused a line, without the specifics: "claim check (leak: at(odo, market))" -> "leak"."""
    why = reason.removeprefix("claim check (").removesuffix(")")
    return "doesn't state its claim" if why.startswith("doesn't state") else why.split(":")[0]


# ---------------------------------------------------------------- the judge
def judge_from_env(name: str, env: Mapping[str, str] | None = None) -> Provider | None:
    """JUDGE_<NAME>_* (BASE_URL, API_KEY, MODEL, optional EXTRA), with room to think and no randomness."""
    p = provider_from_env(os.environ if env is None else env, f"JUDGE_{name.upper()}_")
    if p is None:
        return None
    base = p.base_url.rstrip("/").removesuffix("/chat/completions")  # the full endpoint pasted as the base URL
    extra = {"max_tokens": 800, "temperature": 0, **JUDGE_EXTRA.get(p.model.lower(), {}), **p.extra}
    return dataclasses.replace(p, base_url=base, extra=extra)


@contextmanager
def judging(name: str, env: Mapping[str, str] | None = None) -> Iterator[Provider | None]:
    """The judge, for as long as it's needed. `local:<model>` starts that registry model on this machine
    (thespis.runtime) and stops it afterwards, so a rehearsal can be judged with the network off; any other name is
    JUDGE_<NAME>_* from the environment."""
    if not name.startswith("local:"):
        yield judge_from_env(name, env)
        return
    from thespis.runtime.local import LocalModel
    with LocalModel(name.split(":", 1)[1]) as lm:
        yield Provider(f"local/{lm.model.id}", lm.url, "", lm.model.id, profile=PROFILES["llamacpp"],
                       extra={"temperature": 0, "max_tokens": 800})


# Games played through sessions (rehearsal/sessions.py), by id: their vocabulary and facts come from the game file.
SESSION_GAMES: dict = {}


def register(path: str) -> str:
    """Load a game file for judging its sessions' lines; returns its id."""
    from thespis.session import Game
    game = Game.load(path)
    SESSION_GAMES[game.id] = game
    return game.id


def vocabulary(game: str) -> ClaimVocabulary:
    if game in SESSION_GAMES:
        return SESSION_GAMES[game].vocabulary()
    return import_module(GAMES[game]).VOCABULARY


def world_of(sample: dict, snapshot: dict) -> World:
    """The world a line was said in: a session's snapshot holds it with who saw what; a game's is the world."""
    return World.from_json(snapshot["world"] if sample["game"] in SESSION_GAMES else snapshot)


def facts(sample: dict, snapshot: dict) -> Facts:
    """What the speaker could know when it spoke. The narrator knows exactly the events it was told about."""
    if sample["game"] in SESSION_GAMES:
        from thespis.session import Session
        known = Session.restore(SESSION_GAMES[sample["game"]], snapshot).facts(sample["npc"])
    else:
        known = import_module(GAMES[sample["game"]]).facts(World.from_json(snapshot), sample["npc"])
    if sample["npc"] == "narrator":
        ids = set(sample["ids"])
        return dataclasses.replace(known, knows=lambda event_id: event_id in ids)
    return known


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


VERIFY_PROMPT = (
    "You check one claim against one line of dialogue from a game. Answer whether the line itself states the claim "
    "as a fact: something that already happened or is true now. Threats, plans, promises, questions, orders, "
    "opinions and insults don't state facts. Reported speech states that the teller told it, and what they said. "
    "The claim is written pred(a, b) with these predicates and ids:\n{vocab}\n"
    'Reply with JSON only: {{"states": true}} or {{"states": false}}')


def verify(gateway, samples: list[dict], snapshots: dict[str, dict], progress=print) -> None:
    """The checklist pass, for judges that extract too freely: each claim the code would count against a line
    (a leak, contradiction or hallucination) goes back to the judge as one yes/no question, does the line state
    it? A claim the judge says the line doesn't state is dropped, and the line scored again. Small local models
    extract claims a line only implies (calibration found Gemma 4 E4B flagging three times as many lines as the
    reference); a yes/no question about one claim is a task they do better."""
    asks: list[tuple[dict, dict]] = []
    for s in samples:
        if not s.get("claims") or not any(s.get("categories", {}).get(k) for k in BAD):
            continue
        f = facts(s, snapshots[s["snapshot"]])
        v = vocabulary(s["game"])
        asks += [(s, c) for c in s["claims"] if categorize(v, c, f, s["asserting"]) in BAD]
    calls = [("verify", [{"role": "system", "content": VERIFY_PROMPT.format(vocab=vocabulary(s["game"]).description)},
                         {"role": "user", "content": f"Speaker: {s['name']} (id {s['npc']}). Situation: "
                                                     f"{s['situation']}\nLine: \"{s['line']}\"\nClaim: {label(c)}"}],
              None) for s, c in asks]
    replies = gateway.complete_many(calls) if calls else []
    dropped = 0
    for (s, c), reply in zip(asks, replies):
        if reply is not None and reply.data.get("states") is False:
            s["claims"] = [x for x in s["claims"] if x is not c]
            s.setdefault("unstated", []).append(c)
            dropped += 1
    progress(f"  verified {len(asks)} claims: {dropped} not stated by their lines")
    categorise([s for s in samples if s.get("unstated")], snapshots)


def categorise(samples: list[dict], snapshots: dict[str, dict]) -> None:
    for s in samples:
        if s.get("claims") is None:
            continue
        counts = score(vocabulary(s["game"]), s["claims"], facts(s, snapshots[s["snapshot"]]), s["asserting"])
        s["categories"] = dict(counts)


def run_checks(samples: list[dict], snapshots: dict[str, dict]) -> None:
    """Give every model line the judge-free checks it fails (rehearsal/checks.py), as "checks"."""
    names_of: dict[str, dict[str, str]] = {}
    for s in samples:
        if s["source"] != "llm" or not s.get("line") or not s.get("snapshot"):
            continue
        if s["game"] not in names_of:
            v = vocabulary(s["game"])
            names_of[s["game"]] = {c.lower(): c for c in v.characters} | \
                {k.lower(): x for k, x in v.aliases.items() if x in v.characters}
        f = facts(s, snapshots[s["snapshot"]])
        s["checks"] = checks.flags(s, f.world, f.knows, names_of[s["game"]])


def check_rates(samples: list[dict]) -> dict:
    """How often model lines failed the judge-free checks: every line for words in the player's mouth, the
    narrator's for who spoke."""
    lines = [s for s in samples if "checks" in s]
    narration = [s for s in lines if s["npc"] == "narrator"]
    return {"player_words": [("player_words" in s["checks"]) for s in lines],
            "attribution": [("attribution" in s["checks"]) for s in narration],
            "failed": [{"scenario": s["scenario"], "npc": s["npc"], "line": s["line"], "checks": s["checks"]}
                       for s in lines if s["checks"]]}


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
        "claim_check": dict(Counter(checked(r) for r in reasons.elements() if r.startswith("claim check"))),
        "protocol_refusals": sum(n for r, n in reasons.items() if protocol(r)),
        "calls": len(calls), "failed": dict(Counter(f"{c.call_type}: {c.error}" for c in calls if not c.ok)),
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
    checked = [s for s in samples if s.get("stakes") and "categories" in s]
    return {"judge": judge, "sampled": len(samples), "judged": len(flags["any_bad"]),
            "rates": {k: rate(v) for k, v in flags.items()}, "flags": flags, "claims": dict(claims),
            "checked_bad": rate([any(s["categories"].get(k) for k in BAD) for s in checked]),
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
    for k, what in (("player_words", "words in the player's mouth"), ("attribution", "narration's speakers")):
        if k in base.get("checks", {}) and k in new.get("checks", {}):
            b, n = base["checks"][k], new["checks"][k]
            d = difference(b, n)
            ok = d["d"] is None or (d["lo"] is not None and d["lo"] <= 0)
            detail = "no lines" if d["d"] is None else \
                f"{_pct(sum(n) / len(n))} vs {_pct(sum(b) / len(b))}: {d['d']:+.1%} [{d['lo']:+.1%}, {d['hi']:+.1%}]"
            out.append((f"{what} no worse (n={len(n)} vs {len(b)})", ok, detail))
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


def calibrate_describe(result: dict) -> str:
    from rehearsal.calibrate import describe
    return describe(result)


def markdown(report: dict) -> str:
    s, c = report["summary"], report["claims"]
    extractor = f" Claim check extracted by {', '.join(report['extractor'])}." if report.get("extractor") else ""
    out = [
        f"# Rehearsal {report['when']}",
        "",
        f"Engine `{report['commit']}`, prompts {report['prompts']}. Speaker: {', '.join(report['models'])}.{extractor} "
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
        *([f"| Provisional lines settled, p50 / p95 | {_ms(report['sessions']['settle_p50'])} / "
            f"{_ms(report['sessions']['settle_p95'])} ({report['sessions']['provisional']} of "
            f"{report['sessions']['asked']} lines asked) |",
            f"| Provisional lines that settled after the world moved on | {report['sessions']['stale']} |",
            f"| Lines withdrawn (the session ended first) | {report['sessions']['withdrawn']} |"]
          if report.get("sessions") else []),
        *([f"| Lines putting words in the player's mouth (every line) | {_rate(rate(report['checks']['player_words']))} |",
           f"| Narration naming a speaker who didn't speak | {_rate(rate(report['checks']['attribution']))} |"]
          if report.get("checks") else []),
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
    if c.get("judge") and c["judge"] not in REFERENCE_JUDGES:  # a stand-in judge: say how far to trust it
        cal = c.get("calibration")
        out += [f"Judge calibration: {calibrate_describe(cal)}." if cal else
                "Judge calibration: none. This judge hasn't been measured against the reference "
                "(python -m rehearsal calibrate), so its rates can't be compared with a reference-judged report.", ""]
    if report.get("claim_check", "off") != "off":
        out += [f"Claim check ({report['claim_check']}): it refused {sum(s.get('claim_check', {}).values())} lines "
                f"{s.get('claim_check') or ''}; of the lines it passed that the judge read, "
                f"{_rate(c.get('checked_bad', rate([])))} still had a leak, hallucination or contradiction.", ""]
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
