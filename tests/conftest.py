"""Every test runs without the developer's real services, and leaves the environment as it found it.

The minimal example loads .env, as a real program would. Without this, everything it loaded (model keys, the Content
Safety key, an admin token) would stay in the environment for every later test, and those would call real services.
"""

import os

import pytest

SERVICES = ("LLM_", "JUDGE_", "CONTENT_SAFETY_", "MODERATION_")
SETTINGS = ("ADMIN_TOKEN", "CORS_ORIGINS", "API_DOCS", "REPLAY", "CLAIM_CHECK")


@pytest.fixture(autouse=True)
def isolated_environment():
    saved = dict(os.environ)
    for name in [n for n in os.environ if n.startswith(SERVICES) or n in SETTINGS]:
        del os.environ[name]
    yield
    os.environ.clear()
    os.environ.update(saved)
