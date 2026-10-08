"""Calibrating a judge: how far a local judge agrees with the reference one, on the same lines, so a report judged
offline says how much its numbers can be trusted.

A live rehearsal keeps the lines it judged (`<report>.lines.json.gz`): each line with the reference judge's claims,
and the world as it stood when the line was said. `python -m rehearsal calibrate <lines file> --judge local:<model>`
has another judge extract the same lines' claims, scores both judges' claims with the same code (thespis.claims),
and measures their agreement per line: was the line bad (a leak, hallucination or contradiction), and was it each of
those. Agreement is Cohen's kappa, which discounts the agreement two judges would reach by chance (most lines are
fine, so raw agreement flatters), with a 95% bootstrap interval. The result goes to
rehearsal/calibration/<judge model>.json, and every report the judge scores prints it.

Rough reading of kappa: under 0.4 the judge can't stand in for the reference; 0.4 to 0.6 it shows direction but not
small differences; above 0.6 its rates can be compared with the reference's.
"""

from __future__ import annotations

import copy
import gzip
import json
import random
from datetime import UTC, datetime
from pathlib import Path

from thespis.claims import BAD

HERE = Path(__file__).resolve().parent
CALIBRATION = HERE / "calibration"
BOOT = 2000
CALIBRATE_N = 100


def sibling(stem: Path, suffix: str) -> Path:
    """A file beside a report, named from its stem (which may hold dots: local-qwen3.5-4b)."""
    return stem.with_name(stem.name + suffix)


def stem_of(report: Path) -> Path:
    """A report's stem, from its .json, .md or .lines.json.gz path, or the stem itself."""
    name = report.name
    for suffix in (".lines.json.gz", ".handread.md", ".json", ".md"):
        if name.endswith(suffix):
            return report.with_name(name[: -len(suffix)])
    return report


def keep(path: Path, judge: str | None, when: str, commit: str, samples: list[dict], snapshots: dict,
         games: dict[str, str] | None = None) -> Path:
    """Save the judged lines and the snapshots they need, compressed, beside the report. `games` names the game
    files of any session games among them, so their lines can be judged again later."""
    used = {s["snapshot"] for s in samples if s.get("snapshot")}
    body = {"judge": judge, "when": when, "commit": commit, "samples": samples, "games": games or {},
            "snapshots": {k: v for k, v in snapshots.items() if k in used}}
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)
    return path


def load(path: Path) -> dict:
    """Kept lines, with any session games they came from registered for judging."""
    from rehearsal import measure
    with gzip.open(path, "rt", encoding="utf-8") as f:
        kept = json.load(f)
    for path_ in kept.get("games", {}).values():
        measure.register(path_)
    return kept


def kappa(a: list[bool], b: list[bool]) -> float | None:
    """Cohen's kappa for two raters' yes/no verdicts on the same items. None when it isn't defined (both always
    said the same single answer, so there is nothing to agree about beyond chance)."""
    n = len(a)
    if not n:
        return None
    observed = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    chance = pa * pb + (1 - pa) * (1 - pb)
    return None if chance == 1 else (observed - chance) / (1 - chance)


def kappa_interval(a: list[bool], b: list[bool], seed: int = 0) -> tuple[float | None, float | None]:
    rng, n = random.Random(seed), len(a)
    boots = []
    for _ in range(BOOT):
        idx = [rng.randrange(n) for _ in range(n)]
        k = kappa([a[i] for i in idx], [b[i] for i in idx])
        if k is not None:
            boots.append(k)
    if len(boots) < BOOT // 2:
        return None, None
    boots.sort()
    return boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots)) - 1]


def verdicts(samples: list[dict]) -> dict[str, list[bool]]:
    """Each line's verdicts: bad at all, and each kind of bad."""
    cats = [s["categories"] for s in samples]
    out = {k: [c.get(k, 0) > 0 for c in cats] for k in BAD}
    out["any_bad"] = [any(c.get(k, 0) for k in BAD) for c in cats]
    return out


def agreement(reference: list[dict], judged: list[dict]) -> dict:
    """Per verdict: kappa with its interval, raw agreement, and how often each judge said yes. Only lines both
    judges scored count."""
    both = [(r, j) for r, j in zip(reference, judged) if "categories" in r and "categories" in j]
    ref, new = verdicts([r for r, _ in both]), verdicts([j for _, j in both])
    out: dict = {"n": len(both)}
    for k in ("any_bad", *BAD):
        a, b = ref[k], new[k]
        lo, hi = kappa_interval(a, b)
        out[k] = {"kappa": kappa(a, b), "lo": lo, "hi": hi,
                  "agree": sum(x == y for x, y in zip(a, b)) / len(a) if a else None,
                  "reference_yes": sum(a), "judge_yes": sum(b),
                  "missed": sum(x and not y for x, y in zip(a, b)), "extra": sum(y and not x for x, y in zip(a, b))}
    return out


def calibrate(files: list[Path], judge_name: str, judge_gateway, n: int = CALIBRATE_N, progress=print,
              verify: bool = False) -> dict:
    """Have `judge_gateway` re-judge up to `n` lines the reference judged, and measure agreement. With `verify`,
    the judge also checks each claim it would count against a line (measure.verify)."""
    from rehearsal import measure

    reference, snapshots, sources, ref_judges = [], {}, [], set()
    for f in files:
        kept = load(f)
        ref_judges.add(kept["judge"])
        reference += [s for s in kept["samples"] if "categories" in s]
        snapshots |= kept["snapshots"]
        sources.append(f.name)
    reference = random.Random(0).sample(reference, min(n, len(reference)))
    judged = [{k: v for k, v in copy.deepcopy(s).items() if k not in ("claims", "categories")} for s in reference]
    progress(f"re-judging {len(judged)} lines with {judge_name}")
    measure.extract(judge_gateway, judged, progress)
    measure.categorise(judged, snapshots)
    if verify:
        measure.verify(judge_gateway, judged, snapshots, progress)
        judge_name = f"{judge_name}+verify"
    return {"judge": judge_name, "reference": sorted(j for j in ref_judges if j), "sources": sources,
            "when": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"), "agreement": agreement(reference, judged),
            "unanswered": sum(1 for s in judged if s.get("claims") is None),
            "disagreements": disagreements(reference, judged)}


def disagreements(reference: list[dict], judged: list[dict]) -> list[dict]:
    """The lines the judges called differently, with what each extracted: where to look to improve a judge."""
    out = []
    for r, j in zip(reference, judged):
        bad_r, bad_j = (any(x.get("categories", {}).get(k) for k in BAD) for x in (r, j))
        if "categories" in r and "categories" in j and bad_r != bad_j:
            out.append({"scenario": r["scenario"], "npc": r["npc"], "line": r["line"],
                        "reference": {"claims": r.get("claims"), "categories": r["categories"]},
                        "judge": {"claims": j.get("claims"), "categories": j["categories"]}})
    return out


def path_for(judge_model: str) -> Path:
    return CALIBRATION / f"{judge_model.replace('/', '_')}.json"


def save(result: dict) -> Path:
    CALIBRATION.mkdir(exist_ok=True)
    p = path_for(result["judge"])
    p.write_text(json.dumps(result, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8",
                 newline="\n")
    return p


def lookup(judge_model: str | None) -> dict | None:
    """A judge's calibration, if it has one."""
    if not judge_model:
        return None
    p = path_for(judge_model)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _k(v: dict) -> str:
    if v["kappa"] is None:
        return "n/a"
    def f(x: float) -> str:
        return f"{x + 0.0:.2f}".replace("-0.00", "0.00")
    ci = f" [{f(v['lo'])}, {f(v['hi'])}]" if v["lo"] is not None else ""
    return f"{f(v['kappa'])}{ci}"


def describe(result: dict) -> str:
    """One line for a report: the judge's agreement with the reference on bad lines."""
    a = result["agreement"]
    return (f"{result['judge']} agrees with {', '.join(result['reference']) or 'the reference'} on whether a line is "
            f"bad with kappa {_k(a['any_bad'])} (n={a['n']}, {a['any_bad']['agree']:.0%} raw agreement; calibrated "
            f"{result['when'][:10]})")


def markdown(result: dict) -> str:
    a = result["agreement"]
    rows = [f"| {k} | {_k(a[k])} | {a[k]['agree']:.0%} | {a[k]['reference_yes']} | {a[k]['judge_yes']} | "
            f"{a[k]['missed']} | {a[k]['extra']} |" for k in ("any_bad", *BAD) if a[k]["agree"] is not None]
    return "\n".join([
        f"# Judge calibration: {result['judge']}", "",
        f"Against {', '.join(result['reference'])} on {a['n']} lines from {', '.join(result['sources'])}; "
        f"{result['unanswered']} lines got no answer from the judge. {result['when']}.", "",
        "| Verdict | Kappa [95%] | Raw agreement | Reference said yes | Judge said yes | Judge missed | Judge added |",
        "| --- | --- | --- | --- | --- | --- | --- |", *rows, ""])
