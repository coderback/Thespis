"""Model-judged numbers (#37): a second model checks NPC lines against the state packs they were spoken from.

    python tools/judge.py              # 50 lines, from the LLM_* (speaker) and LLM_BACKUP_* (judge) settings in .env
    python tools/judge.py --lines 30

It plays the scripted routes in-process on an empty cache, so every line is live from the primary model, asking
fresh questions as the harness does, and keeps each line that passed the validator together with its state pack.
The backup model then judges each one: does it only state what the NPC knew, and is it in character? To check the
judge, it also gets canaries: real lines moved to another NPC's moment, citing nothing in that NPC's pack, which it
should flag. The rates go into results.md between judged markers, labelled as model-judged.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import random
import secrets
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from thespis.expression import PROMPT_VERSION, Mind, StatePack  # noqa: E402
from thespis.gateway import OpenAICompatGateway, Provider, gateway_from_env  # noqa: E402
from tools.harness import END, START, fresh_questions, run_route, with_block  # noqa: E402
from tools.routes import ROUTES  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CANARIES = 10
JUDGE_PROMPT = (
    "You audit lines spoken by characters in a game. A character may only know what is in its state pack: its "
    "beliefs, the events it knows, who is here, the setting and the situation. Given the character's persona, its "
    "state pack and what it said, answer two questions.\n"
    "1. consistent: does the line state only facts that are in the state pack or plainly follow from it, and "
    "contradict none of it? Opinions, feelings, threats, plans and questions are fine. A fact the pack doesn't hold, "
    "or one it contradicts, is not.\n"
    "2. in_character: does the line fit the persona?\n"
    'Reply with JSON only: {"consistent": true, "in_character": true, "reason": "one short sentence"}')


@dataclasses.dataclass
class Sample:
    kind: str
    pack: StatePack
    action: str | None
    line: str
    cites: list[str]
    canary: bool = False


def collect(gateway, lines: int, seeds=(1, 4)) -> list[Sample]:
    """Play routes in-process on an empty cache until `lines` validated model lines are in hand, with their packs."""
    from fastapi.testclient import TestClient

    samples: list[Sample] = []
    original = Mind._accept

    def recording(self, reply, pack, fallback, kind):
        u = original(self, reply, pack, fallback, kind)
        if u.source == "llm":
            samples.append(Sample(kind, pack, u.action if kind == "decide" else None, u.line, u.cites))
        return u

    saved = os.environ.get("DB_PATH")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DB_PATH"] = str(Path(tmp) / "judge.sqlite")
        Mind._accept = recording
        try:
            from games.crypt_road.app import app
            with TestClient(app) as client:
                app.state.gateway = gateway
                app.state.admin_token = token = secrets.token_urlsafe(16)  # run_route reads the call log
                client.headers["Authorization"] = f"Bearer {token}"
                runs = [(name, seed) for seed in seeds for name in ROUTES]
                for (name, seed), question in zip(runs, fresh_questions(len(runs), random.Random())):
                    if len(samples) >= lines:
                        break
                    run_route(client, name, seed, "model", question)
        finally:
            Mind._accept = original
            if saved is None:
                os.environ.pop("DB_PATH", None)
            else:
                os.environ["DB_PATH"] = saved
    return samples[:lines]


def canaries(samples: list[Sample], n: int = CANARIES) -> list[Sample]:
    """Real lines moved to another NPC's moment whose pack holds none of the ids they cite."""
    out = []
    for s in samples:
        for other in samples:
            if other.pack.npc != s.pack.npc and not set(s.cites) & other.pack.ids:
                out.append(Sample("react", other.pack, None, s.line, s.cites, canary=True))
                break
        if len(out) == n:
            break
    return out


def judge_messages(s: Sample) -> list[dict]:
    said = {"line": s.line, "cites": s.cites}
    if s.action is not None:
        said["action"] = s.action
    return [{"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": json.dumps({"character": s.pack.name, "persona": s.pack.persona,
                                                    "state_pack": s.pack.payload(), "said": said},
                                                   ensure_ascii=False)}]


def judge(gateway, samples: list[Sample]) -> list[dict | None]:
    """The judge's verdict on each sample: {"consistent", "in_character", "reason"}, or None if it gave none."""
    replies = gateway.complete_many([("judge", judge_messages(s)) for s in samples])
    verdicts = []
    for r in replies:
        ok = r is not None and isinstance(r.data.get("consistent"), bool) and isinstance(r.data.get("in_character"), bool)
        verdicts.append(r.data if ok else None)
    return verdicts


def summarise(samples, verdicts, plants, plant_verdicts) -> dict:
    judged = [(s, v) for s, v in zip(samples, verdicts) if v is not None]
    caught = [v for v in plant_verdicts if v is not None and not v["consistent"]]
    return {
        "lines": len(samples), "judged": len(judged), "unjudged": len(samples) - len(judged),
        "consistent": sum(v["consistent"] for _, v in judged),
        "in_character": sum(v["in_character"] for _, v in judged),
        "canaries": len(plants), "canaries_judged": sum(v is not None for v in plant_verdicts), "caught": len(caught),
        "flagged": [(s, v) for s, v in judged if not v["consistent"] or not v["in_character"]],
    }


def block(summary: dict, speaker: str, judge_model: str, when: str) -> str:
    s = summary
    pct = lambda n, d: f"{n / d:.0%}" if d else "n/a"  # noqa: E731
    out = [
        START,
        "## Model-judged (#37)",
        "",
        f"**Model-judged, not measured:** {judge_model} read {s['judged']} lines by {speaker}, each beside the state "
        f"pack it was spoken from, on {when}. The lines come from the scripted routes with fresh questions, played "
        f"in-process with the same code and prompts as the host (prompt version {PROMPT_VERSION}), and only lines that "
        "passed the validator count, since those are the ones players hear.",
        "",
        "| Measure (model-judged) | Value |",
        "| --- | --- |",
        f"| Lines that state only what the NPC knew | **{s['consistent']} of {s['judged']}** "
        f"({pct(s['consistent'], s['judged'])}) |",
        f"| Lines in character | **{s['in_character']} of {s['judged']}** ({pct(s['in_character'], s['judged'])}) |",
        f"| Check on the judge: planted lines it flagged | {s['caught']} of {s['canaries_judged']} |",
        "",
        "The planted lines are real lines moved to another NPC's moment, where nothing they cite is in the pack, so a "
        "careful judge should flag them. A line can be consistent and still wrong about the world: NPCs may hold false "
        "beliefs by design, and this checks only what each NPC knew.",
    ]
    if s["unjudged"]:
        out += ["", f"{s['unjudged']} lines got no usable verdict from the judge and aren't counted."]
    if s["flagged"]:
        out += ["", "Lines the judge flagged:", ""]
        for smp, v in s["flagged"]:
            what = [k for k in ("consistent", "in_character") if not v[k]]
            out.append(f"- {smp.pack.name}: \"{smp.line}\" ({', '.join('not ' + w.replace('_', ' ') for w in what)}: "
                       f"{v.get('reason', '').strip()})")
    out.append(END)
    return "\n".join(out)


def judge_provider(p: Provider) -> Provider:
    """The judge thinks a little: reasoning low, room for it, and no response cap from the speaker's settings."""
    extra = {**p.extra, "reasoning_effort": "low", "max_tokens": None, "max_completion_tokens": 800, "temperature": None}
    return dataclasses.replace(p, extra=extra)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--lines", type=int, default=50)
    parser.add_argument("--out", default=str(ROOT / "results.md"))
    args = parser.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    providers = gateway_from_env().providers
    if len(providers) < 2:
        print("Needs two models: LLM_* speaks, LLM_BACKUP_* judges")
        return 1
    speaker = OpenAICompatGateway([providers[0]])
    judge_gateway = OpenAICompatGateway([judge_provider(providers[1])], timeout=30)
    try:
        samples = collect(speaker, args.lines)
        plants = canaries(samples)
        verdicts = judge(judge_gateway, samples + plants)
    finally:
        speaker.close()
        judge_gateway.close()
    summary = summarise(samples, verdicts[:len(samples)], plants, verdicts[len(samples):])
    text = block(summary, providers[0].model, providers[1].model, datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"))
    out = Path(args.out)
    out.write_text(with_block(out.read_text(encoding="utf-8") if out.exists() else "", text), encoding="utf-8",
                   newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

