"""Provider profiles: what each kind of model endpoint speaks, enforces and needs, so Thespis can use any of them.

A profile says:
- the wire protocol (`api`): OpenAI's chat completions, which most providers and every local server speak, or
  Anthropic's Messages API;
- how it holds a reply to a JSON schema (`schema`): `strict` structured outputs (a fixed subset of JSON Schema),
  a `grammar` built from the schema (llama.cpp, vLLM, Ollama: they enforce more of it), `tool` input (Anthropic), or
  `json` mode only;
- which keywords beyond the strict subset it enforces (`enforces`). Thespis's reply schema follows: "cite at least
  one" (`minItems`) and the line's length (`maxLength`) go into the schema only where the provider enforces them.
  The validator checks them either way;
- its latency budget (`timeout`): a cloud model answers in about a second, but a laptop's local model may take ten;
- how many calls it takes at once (`concurrency`), whether it needs a key, and its prices, where known.

`LLM_PROFILE` picks one by name, or names a profile file that `python -m thespis models probe` wrote after
measuring an endpoint. Measured facts beat these defaults: run the probe on a new endpoint before trusting it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

LINE_LIMITS = {"act": 160, "react": 160, "narrate": 400}  # characters per line, by call type (expression.LIMITS)


@dataclass(frozen=True)
class Profile:
    name: str
    api: str = "openai"  # "openai" (chat completions) or "anthropic" (Messages)
    base_url: str = ""
    schema: str = "strict"  # strict, grammar, tool or json
    enforces: frozenset[str] = frozenset()  # beyond the strict subset: minItems, maxLength
    timeout: float = 4.0  # seconds for the whole call
    concurrency: int = 4
    key: bool = True  # needs an API key
    stream: bool = True
    price_in: float | None = None  # USD per million input tokens
    price_out: float | None = None
    extra: dict = field(default_factory=dict)  # merged into every request body
    measured: dict = field(default_factory=dict)  # what the probe found: latency, first token, enforcement

    def adapt(self, schema: dict, call_type: str) -> dict:
        """Thespis's reply schema with the constraints this provider enforces. Others stay out: a strict provider
        refuses keywords outside its subset, and the validator checks them anyway."""
        props = schema.get("properties", {})
        if not ({"cites", "line"} <= set(props)) or not self.enforces:
            return schema
        cites, line = dict(props["cites"]), dict(props["line"])
        if "minItems" in self.enforces:
            cites["minItems"] = 1
        if "maxLength" in self.enforces and call_type in LINE_LIMITS:
            line["maxLength"] = LINE_LIMITS[call_type]
        return {**schema, "properties": {**props, "cites": cites, "line": line}}

    def to_json(self) -> dict:
        return {**asdict(self), "enforces": sorted(self.enforces)}

    @classmethod
    def from_json(cls, d: dict) -> Profile:
        return cls(**{**d, "enforces": frozenset(d.get("enforces", ()))})


# Local servers: thinking off (Qwen and other hybrid models), and room for a claim check's list of claims, which
# 150 tokens cut off mid-JSON in live Rehearsal (the cloud deployments get 300 through LLM_EXTRA).
_LOCAL = {"chat_template_kwargs": {"enable_thinking": False}, "max_tokens": 300}

PROFILES: dict[str, Profile] = {p.name: p for p in (
    Profile("openai", base_url="https://api.openai.com/v1"),
    Profile("azure"),  # base_url is the deployment's; its hosts get the api-key header
    Profile("openrouter", base_url="https://openrouter.ai/api/v1", timeout=6.0),
    Profile("groq", base_url="https://api.groq.com/openai/v1", schema="json"),
    Profile("together", base_url="https://api.together.xyz/v1", schema="json", timeout=6.0),
    Profile("gemini", base_url="https://generativelanguage.googleapis.com/v1beta/openai", timeout=6.0),
    Profile("anthropic", api="anthropic", base_url="https://api.anthropic.com/v1", schema="tool", timeout=6.0),
    Profile("vllm", base_url="http://127.0.0.1:8000/v1", schema="grammar", enforces=frozenset({"minItems"}),
            timeout=10.0, key=False, extra=_LOCAL),
    Profile("llamacpp", base_url="http://127.0.0.1:8080/v1", schema="grammar",
            enforces=frozenset({"minItems", "maxLength"}), timeout=15.0, concurrency=2, key=False, extra=_LOCAL),
    Profile("ollama", base_url="http://127.0.0.1:11434/v1", schema="grammar", enforces=frozenset({"minItems"}),
            timeout=15.0, concurrency=1, key=False, extra={"max_tokens": 300}),
)}
DEFAULT = PROFILES["openai"]


def profile(name_or_path: str) -> Profile:
    """A built-in profile by name, or one a probe wrote, by path. Unknown names fail loudly: a typo would otherwise
    quietly give a laptop model the cloud's 4-second budget."""
    if not name_or_path:
        return DEFAULT
    if name_or_path in PROFILES:
        return PROFILES[name_or_path]
    path = Path(name_or_path)
    if path.suffix == ".json" and path.exists():
        return Profile.from_json(json.loads(path.read_text(encoding="utf-8")))
    raise ValueError(f"no profile {name_or_path!r}: use one of {', '.join(PROFILES)} or a probe's .json file")


def with_timeout(p: Profile, timeout: float | None) -> Profile:
    return replace(p, timeout=timeout) if timeout else p
