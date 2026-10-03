"""The seam where model providers plug in. The implementation (primary, backup, timeout, cache) is #16."""

from __future__ import annotations

from typing import Protocol


class ModelGateway(Protocol):
    def complete(self, call_type: str, prompt: str) -> dict | None:
        """Return the model's JSON reply, or None to make the caller use its fallback."""
        ...
