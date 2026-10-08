"""The hand-read sample: 20 lines a person reads per release, because zero automatic flags is not proof.

    python -m rehearsal handread rehearsal/reports/<run>     # writes <run>.handread.md from <run>.lines.json.gz

Each line comes with what its speaker knew (the events and beliefs in its state pack), then the line, then boxes to
tick for what's wrong with it. The checks' verdict comes last, so the reader judges the line before seeing it. The
reader ticks boxes in the file and commits it beside the report. `compare` then reads it: the gate fails if the
reader found a kind of failure on a line that no automatic check flagged (the judge's claims, or rehearsal/checks.py),
or if any line was left unread.
"""

from __future__ import annotations

import random
import re
from importlib import import_module
from pathlib import Path

from rehearsal import measure
from rehearsal.calibrate import load, sibling
from thespis.claims import BAD
from thespis.world import World

N = 20
SEED = 7
# What a reader can tick, with what each means, and the automatic flag that covers it.
KINDS = {
    "fine": ("nothing wrong", None),
    "leak": ("says something its speaker couldn't know", "leak"),
    "hallucination": ("says something happened that didn't, or is true that isn't", "hallucination"),
    "contradiction": ("contradicts itself or what its speaker believes", "contradiction"),
    "player_words": ("puts words in the player's mouth", "player_words"),
    "attribution": ("says the wrong person spoke or acted", "attribution"),
    "other": ("something else a player would notice (say what in the notes)", None),
}
_BOX = re.compile(r"^- \[(x|X| )\] (\w+)")
_ITEM = re.compile(r"^## (\d+)\. ")


def path_for(stem: Path) -> Path:
    return sibling(stem, ".handread.md")


def _context(s: dict, w: World) -> list[str]:
    from rehearsal import measure
    words = measure.SESSION_GAMES.get(s["game"]) or import_module(f"games.{s['game']}.words")
    out = []
    for i in sorted(s["ids"]):
        if i.startswith("e") and any(e.id == i for e in w.ledger):
            out.append(f"  - {i}: {words.sentence(w.ledger.get(i))}")
        elif i.startswith("b"):
            b = next((b for b in w.beliefs.for_npc(s["npc"]) if b.id == i), None)
            if b is not None:
                out.append(f"  - {i}: believes {words.claim_text(b.claim)} "
                           f"({b.conf:.0%})")
    return out or ["  - (nothing)"]


def automatic(s: dict) -> set[str]:
    """What the automatic checks flagged on a line."""
    return {k for k in BAD if s.get("categories", {}).get(k)} | set(s.get("checks", []))


def make(stem: Path, n: int = N) -> Path:
    kept = load(sibling(stem, ".lines.json.gz"))
    judged = [s for s in kept["samples"] if "categories" in s]
    chosen = random.Random(SEED).sample(judged, min(n, len(judged)))
    out = [f"# Hand-read: {stem.name}", "",
           "Reader: (your name)  ", f"Judge: {kept['judge']}; {len(chosen)} lines chosen at random from the "
           f"{len(judged)} it judged.", "",
           "Read each line as a player would. Tick every box that applies (`- [x]`), or `fine`, and add notes if "
           "useful. Read the line before the checks' verdict at the end of each item.", ""]
    for i, s in enumerate(chosen, 1):
        w = measure.world_of(s, kept["snapshots"][s["snapshot"]])
        out += [f"## {i}. {s['scenario']}: {s['npc']} ({s['kind']})", "", f"Situation: {s['situation']}", "",
                "What it knew:", *_context(s, w), "", f"> {s['line']}", ""]
        out += [f"- [ ] {k}: {what}" for k, (what, _) in KINDS.items()]
        flagged = automatic(s)
        out += ["", "Notes: ", "",
                f"<details><summary>The checks said</summary>{', '.join(sorted(flagged)) or 'nothing wrong'}; "
                f"claims {s.get('categories', {})}</details>", ""]
    path = path_for(stem)
    path.write_text("\n".join(out), encoding="utf-8", newline="\n")
    return path


def read(path: Path) -> dict[int, set[str]]:
    """What the reader ticked, by item number."""
    ticked: dict[int, set[str]] = {}
    item = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if m := _ITEM.match(line):
            item = int(m.group(1))
            ticked[item] = set()
        elif item is not None and (m := _BOX.match(line)) and m.group(1).lower() == "x":
            ticked[item].add(m.group(2))
    return ticked


def verdict(stem: Path) -> tuple[bool, str] | None:
    """The gate's check: None if the run wasn't hand-read; else whether the reader found nothing the checks missed,
    and what they found."""
    path = path_for(stem)
    if not path.exists():
        return None
    kept = load(sibling(stem, ".lines.json.gz"))
    judged = [s for s in kept["samples"] if "categories" in s]
    chosen = random.Random(SEED).sample(judged, min(N, len(judged)))
    ticked = read(path)
    unread = [i for i in range(1, len(chosen) + 1) if not ticked.get(i)]
    missed = []
    for i, s in enumerate(chosen, 1):
        found = {KINDS[k][1] or k for k in ticked.get(i, set()) if k in KINDS and k != "fine"}
        caught = automatic(s)
        missed += [f"{i}: {k}" for k in sorted(found - caught)]
    if unread:
        return False, f"{len(unread)} of {len(chosen)} lines unread (items {', '.join(map(str, unread))})"
    if missed:
        return False, f"the reader found what no check flagged: {'; '.join(missed)}"
    return True, f"{len(chosen)} lines read; nothing the checks missed"
