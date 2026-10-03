"""Regenerate fixtures/ by playing the demo route through the real HTTP API.

    python tools/make_fixtures.py

Every file is a real response, so the client's fixtures can never drift from the engine. tests/test_fixtures.py
fails if the committed fixtures differ from what this produces.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
SESSION = "demo-0001"  # stands in for the random session id, so regenerating gives no diff

LIE = {"pred": "robbed", "a": "kael", "b": "odo"}


def generate() -> dict[str, dict]:
    """Play the demo route on the default seed and return {file name: response}."""
    sys.path.insert(0, str(ROOT))
    saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("LLM_")}  # fixtures never use a model
    try:
        return _play()
    finally:
        os.environ.update(saved)


def _play() -> dict[str, dict]:
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DB_PATH"] = str(Path(tmp) / "fixtures.sqlite")
        from games.crypt_road.app import app

        out: dict[str, dict] = {}
        with TestClient(app) as client:
            created = client.post("/session", json={}).json()
            headers = {"X-Session": created["session"]}
            out["session_new.json"] = {**created, "session": SESSION}

            def get(name, path):
                r = client.get(path, headers=headers)
                assert r.status_code == 200, (path, r.text)
                out[name] = r.json()

            def act(name, **body):
                r = client.post("/act", json=body, headers=headers)
                assert r.status_code == 200, (body, r.text)
                out[name] = r.json()

            get("state_p0_start.json", "/state")
            get("allowed_p0_tavern.json", "/allowed")
            act("act_01_insult_kael.json", verb="insult", target="kael")
            act("act_02_challenge_kael_win.json", verb="challenge", target="kael")
            get("allowed_p0_duel_won.json", "/allowed")
            act("act_03_humiliate_kael.json", verb="humiliate", target="kael")
            get("state_p1_after_humiliate.json", "/state")
            act("act_04_talk_mags.json", verb="talk", target="mags", text="What did you make of that?")
            act("act_05_move_to_market.json", verb="move")
            act("act_06_move_to_guard_post.json", verb="move")
            get("digest_p2.json", "/digest?since=2")
            get("state_p3_gate.json", "/state")
            get("allowed_p3_gate.json", "/allowed")
            act("act_07_bribe_brenna.json", verb="bribe", target="brenna", amount=20)
            act("act_08_bribe_brenna.json", verb="bribe", target="brenna", amount=20)
            act("act_09_tell_brenna_lie.json", verb="tell_claim", target="brenna", claim=LIE)
            act("act_10_move_to_bridge.json", verb="move")
            act("act_11_move_to_crypt.json", verb="move")
            act("act_12_take_relic.json", verb="take_relic")
            get("state_p7_end.json", "/state")
            get("allowed_p7_end.json", "/allowed")
            get("digest_epilogue.json", "/digest?since=5")
        return out


def write(out_dir: Path = FIXTURES) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = generate()
    for old in out_dir.glob("*.json"):
        if old.name not in files:
            old.unlink()
    for name, data in files.items():
        (out_dir / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                                    newline="\n")
    return sorted(files)


if __name__ == "__main__":
    names = write()
    print(f"wrote {len(names)} fixtures to {FIXTURES}")
