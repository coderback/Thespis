"""Rehearsal: play every scenario and measure what the NPCs said, live or from recordings.

    python -m rehearsal live --record          # the live model speaks; writes a report and new recordings
    python -m rehearsal live --lines 150       # judge a sample of 150 lines (default), with JUDGE_DEEPSEEK_*
    python -m rehearsal replay                 # what CI runs: the recordings answer, no network
    python -m rehearsal replay --update        # accept a change in what the NPCs say, when no call missed
    python -m rehearsal compare rehearsal/reports/baseline.json rehearsal/reports/<new>.json
    python -m rehearsal live --local gemma4-e4b --judge local:qwen3.5-4b   # offline: a local speaker and judge
    python -m rehearsal calibrate rehearsal/reports/<run>.lines.json.gz --judge local:qwen3.5-4b

`live` reads LLM_* (the speaker, as on the host) and JUDGE_<NAME>_* (the judge) from .env. With `--local <model>` the
speaker is that model on this machine instead, and no cloud model speaks; `--judge local:<model>` judges with a local
model, started once the speaker has stopped. Its report goes to rehearsal/reports/<date>-<commit>.json and .md, with
the judged lines kept beside it (.lines.json.gz) for calibrating other judges (rehearsal/calibrate.py). `replay` exits 1 if a call missed the recordings (what the model is
shown has changed: record again), if a line cites what its pack didn't hold, or if any scenario went differently
from transcripts.json. `compare` exits 1 if the new report fails the gate against the base.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import random
import subprocess
import sys
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rehearsal import calibrate, measure  # noqa: E402
from rehearsal.record import DictCache, Recorder, RecordingGateway, ReplayGateway, transcript  # noqa: E402
from rehearsal.scenarios import Scenario, Stage, scenarios  # noqa: E402
from thespis import expression  # noqa: E402
from thespis.claims import ClaimChecking  # noqa: E402

HERE = Path(__file__).resolve().parent
RECORDINGS = HERE / "recordings.json"
TRANSCRIPTS = HERE / "transcripts.json"
REPORTS = HERE / "reports"
SAMPLE_SEED = 0


def rehearse(gateway, chosen: list[Scenario], claim_check: str = "consequential",
             extractor=None) -> tuple[Stage, Recorder, dict]:
    """Play every scenario on one stage, sharing one reply cache. Returns the stage, the recorder and each
    scenario's transcript. `claim_check` is consequential, all or off, as CLAIM_CHECK on the host; `extractor` is
    the claim check's own gateway, as LLM_CHECK_* gives one, or None for the model that spoke."""
    checking = None if claim_check == "off" else ClaimChecking(claim_check, extractor)
    stage = Stage(gateway, DictCache(), checking=checking)
    recorder = Recorder(lambda: stage.world)
    stage.observer = recorder
    transcripts = {}
    for scenario in chosen:
        recorder.scenario, recorder.game = scenario.name, scenario.game
        stage.tellings = []
        w = scenario.run(stage)
        transcripts[scenario.name] = transcript(w, stage.tellings)
    return stage, recorder, transcripts


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8",
                    newline="\n")


def _pick(only: str | None) -> list[Scenario]:
    return [s for s in scenarios() if not only or only in s.name]


def live(args) -> int:
    from dotenv import load_dotenv

    from thespis.claims import checking_from_env
    from thespis.gateway import OpenAICompatGateway, gateway_from_env

    load_dotenv(ROOT / ".env")
    env: dict[str, str] = dict(os.environ)
    local = None
    if args.local:  # the speaker runs here; every cloud LLM_* setting is dropped, so nothing else can speak
        from thespis.runtime.local import LocalModel
        local = LocalModel(args.local).start()
        env = {k: v for k, v in env.items() if not k.startswith("LLM_")} | local.env()
        print(f"speaking through {local.plan.describe()}")
    speaker = gateway_from_env(env)
    if not isinstance(speaker, OpenAICompatGateway):
        print("No model configured: set LLM_* in .env, or pass --local <model>")
        return 1
    if args.lines and not args.judge.startswith("local:") and measure.judge_from_env(args.judge) is None:
        print(f"No judge: set JUDGE_{args.judge.upper()}_* in .env, judge with local:<model>, or pass --lines 0")
        return 1
    speaker.calls = deque()  # keep every call, not just the latest 1000
    checking = checking_from_env(env) if args.claim_check != "off" else None
    extractor = checking.gateway if checking is not None else None  # LLM_CHECK_*, if set
    if isinstance(extractor, OpenAICompatGateway):
        extractor.calls = deque()
    recording = RecordingGateway(speaker)
    chosen = _pick(args.only)
    print(f"playing {len(chosen)} scenarios with {', '.join(speaker.models)}, claim check {args.claim_check}"
          + (f", extracted by {', '.join(extractor.models)}" if extractor is not None else ""))
    try:
        stage, recorder, transcripts = rehearse(recording, chosen, args.claim_check, extractor)
    finally:
        speaker.close()
        if isinstance(extractor, OpenAICompatGateway):
            extractor.close()
        if local is not None:
            local.stop()  # before a local judge starts: one model on the GPU at a time
    calls = list(speaker.calls) + list(getattr(extractor, "calls", []))
    report = {
        "when": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"), "commit": _commit(),
        "prompts": str(getattr(expression, "PROMPT_HASH", getattr(expression, "PROMPT_VERSION", "?"))),
        "models": list(speaker.models), "claim_check": args.claim_check,
        "extractor": list(extractor.models) if extractor is not None else None,
        "summary": measure.summary(recorder.samples, calls, stage.acts, len(chosen)),
        "violations": recorder.violations,
    }
    report["summary"]["unanswered"] = recorder.unanswered
    lines = [s for s in recorder.samples if s["source"] == "llm" and s["line"]]
    sample = random.Random(SAMPLE_SEED).sample(lines, min(args.lines, len(lines)))
    judge_model = None
    if sample and args.lines:
        with measure.judging(args.judge, env) if args.judge.startswith("local:") else \
                contextlib.nullcontext(measure.judge_from_env(args.judge)) as judge:
            assert judge is not None
            judge_model = judge.model
            print(f"judging {len(sample)} of {len(lines)} model lines with {judge.model}")
            gateway = measure.judge_gateway(judge)
            try:
                measure.extract(gateway, sample)
            finally:
                gateway.close()
        measure.categorise(sample, recorder.snapshots)
    report["claims"] = measure.judged(sample, judge_model)
    report["claims"]["calibration"] = calibrate.lookup(judge_model)
    REPORTS.mkdir(exist_ok=True)
    stem = REPORTS / f"{datetime.now(UTC).strftime('%Y-%m-%d-%H%M')}-{report['commit']}"
    if sample and judge_model:
        kept = calibrate.keep(stem.with_suffix(".lines.json.gz"), judge_model, report["when"], report["commit"],
                              sample, recorder.snapshots)
        print(f"kept the judged lines in {kept.relative_to(ROOT)}")
    stem.with_suffix(".json").write_text(measure.dumps(report), encoding="utf-8", newline="\n")
    stem.with_suffix(".md").write_text(measure.markdown(report), encoding="utf-8", newline="\n")
    print(measure.markdown(report))
    print(f"wrote {stem.with_suffix('.json').relative_to(ROOT)} and .md")
    if args.record:
        if args.only or extractor is not None:
            print("not recording: --only played a subset" if args.only else
                  "not recording: LLM_CHECK_* gave the claim check its own model, whose replies aren't recorded")
        else:
            _write(RECORDINGS, recording.recordings(args.claim_check))
            _write(TRANSCRIPTS, transcripts)
            print(f"recorded {sum(len(v) for v in recording.replies.values())} replies to "
                  f"{RECORDINGS.relative_to(ROOT)}, transcripts to {TRANSCRIPTS.relative_to(ROOT)}")
    return 0


def calibrate_judge(args) -> int:
    """Have a judge re-judge lines another judge scored, and record how far they agree."""
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    files = [Path(f) for f in args.files]
    with measure.judging(args.judge) as judge:
        if judge is None:
            print(f"No judge: set JUDGE_{args.judge.upper()}_* in .env, or judge with local:<model>")
            return 1
        gateway = measure.judge_gateway(judge)
        try:
            result = calibrate.calibrate(files, judge.model, gateway, args.n)
        finally:
            gateway.close()
    path = calibrate.save(result)
    print(calibrate.markdown(result))
    print(f"wrote {path.relative_to(ROOT)}")
    return 0


def replay(args) -> int:
    """Play every scenario from the recordings. Returns the problems found, none if it went as recorded."""
    problems = check()
    if args.update and not any(p.startswith(("missed", "stray")) for p in problems):
        gateway = ReplayGateway(json.loads(RECORDINGS.read_text(encoding="utf-8")))
        _, _, transcripts = rehearse(gateway, scenarios(), gateway.claim_check)
        _write(TRANSCRIPTS, transcripts)
        print(f"updated {TRANSCRIPTS.relative_to(ROOT)}")
        return 0
    for p in problems:
        print(p)
    print("replay: every scenario went as recorded" if not problems else f"replay: {len(problems)} problems")
    return 1 if problems else 0


def check() -> list[str]:
    """Replay every scenario and list what differs from the recordings and transcripts."""
    if not RECORDINGS.exists():
        return [f"missed: no recordings at {RECORDINGS.relative_to(ROOT)}; run python -m rehearsal live --record"]
    gateway = ReplayGateway(json.loads(RECORDINGS.read_text(encoding="utf-8")))
    _, recorder, transcripts = rehearse(gateway, scenarios(), gateway.claim_check)
    problems = []
    if gateway.misses:
        problems.append(f"missed: {len(gateway.misses)} model calls weren't recorded ({', '.join(sorted(set(gateway.misses)))}), "
                        "so what the model is shown has changed. Record again: python -m rehearsal live --record")
    problems += [f"stray: {v}" for v in recorder.violations]
    expected = json.loads(TRANSCRIPTS.read_text(encoding="utf-8")) if TRANSCRIPTS.exists() else {}
    for name, got in transcripts.items():
        want = expected.get(name)
        if want is None:
            problems.append(f"changed: {name} has no transcript; run python -m rehearsal replay --update")
            continue
        for key in ("outcome", "story", "lines", "tellings", "refused"):
            if got[key] != want[key]:
                problems.append(f"changed: {name} {key}: {_differ(want[key], got[key])}")
    return problems


def _differ(want, got) -> str:
    if isinstance(want, list) and isinstance(got, list):
        for i, (a, b) in enumerate(zip(want, got)):
            if a != b:
                return f"item {i}: was {a}, now {b}"
        return f"was {len(want)} items, now {len(got)}"
    return f"was {want}, now {got}"


def compare(args) -> int:
    base, new = (json.loads(Path(p).read_text(encoding="utf-8")) for p in (args.base, args.new))
    results = measure.gate(base, new)
    for what, ok, detail in results:
        print(f"{'ok  ' if ok else 'FAIL'} {what}: {detail}")
    return 0 if all(ok for _, ok, _ in results) else 1


def _commit() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                          cwd=ROOT).stdout.strip() or "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m rehearsal", description=(__doc__ or "").split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("live", help="the live model speaks")
    p.add_argument("--lines", type=int, default=150, help="model lines to judge; 0 skips the judge")
    p.add_argument("--judge", default="deepseek", help="JUDGE_<NAME>_* in .env, or local:<model>")
    p.add_argument("--record", action="store_true", help="write recordings.json and transcripts.json")
    p.add_argument("--only", help="play only scenarios whose name contains this")
    p.add_argument("--claim-check", default="consequential", choices=("consequential", "all", "off"),
                   help="which lines meet the claim check, as CLAIM_CHECK on the host")
    p.add_argument("--local", help="speak through this registry model on this machine (thespis.runtime)")
    p.set_defaults(fn=live)
    p = sub.add_parser("calibrate", help="a judge against the reference, on lines the reference judged")
    p.add_argument("files", nargs="+", help="<report>.lines.json.gz files")
    p.add_argument("--judge", required=True, help="local:<model>, or a JUDGE_<NAME>_* name")
    p.add_argument("--n", type=int, default=calibrate.CALIBRATE_N, help="lines to re-judge")
    p.set_defaults(fn=calibrate_judge)
    p = sub.add_parser("replay", help="the recordings answer, no network")
    p.add_argument("--update", action="store_true", help="rewrite transcripts.json from the replay")
    p.set_defaults(fn=replay)
    p = sub.add_parser("compare", help="the gate: a new report against a base")
    p.add_argument("base")
    p.add_argument("new")
    p.set_defaults(fn=compare)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
