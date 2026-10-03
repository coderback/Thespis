"""Check the configured model providers: one small JSON call to each, with its latency.

    python tools/model_ping.py            # reads LLM_* and LLM_BACKUP_* from the environment, or from .env

Run it from the host to see the latency judges will get. It prints provider names and models, never keys.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from thespis.gateway import OpenAICompatGateway, gateway_from_env  # noqa: E402

PING = [
    {"role": "system", "content": "Reply with JSON only."},
    {"role": "user", "content": 'Pick one action id from ALLOWED: ["go_to", "wait"]. '
                                'Reply as {"action": "...", "line": "at most 10 words"}.'},
]


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Fill missing environment variables from .env, if there is one. Existing variables win."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def main() -> int:
    load_dotenv()
    configured = gateway_from_env()
    if not configured.providers:
        print("No model configured: set LLM_BASE_URL, LLM_API_KEY and LLM_MODEL (and LLM_BACKUP_*).")
        return 1
    failures = 0
    for provider in configured.providers:  # each on its own, so a failing primary doesn't hide behind the backup
        g = OpenAICompatGateway([provider])
        reply = g.complete("ping", PING)
        call = g.calls[-1]
        if reply:
            print(f"OK    {provider.name}: {call.latency:.2f}s  {reply.data}")
        else:
            failures += 1
            print(f"FAIL  {provider.name}: {call.latency:.2f}s  {call.error}")
        g.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
