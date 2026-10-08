"""Model keys at rest: a project's model settings, API keys included, are sealed with AES-256-GCM before they are
stored, under a key the server holds in its environment (THESPIS_SECRET_KEY, 32 random bytes in base64; make one
with `python -m thespis projects secret`). The project's id is bound in as associated data, so a sealed blob copied
to another project's row won't open there. Losing the key loses the stored model keys, nothing else: projects set
them again.
"""

from __future__ import annotations

import base64
import json
import os
import secrets

ENV = "THESPIS_SECRET_KEY"
VERSION = "v1"


class VaultError(RuntimeError):
    pass


def new_secret() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode()


class Vault:
    def __init__(self, secret: str):
        try:
            key = base64.b64decode(secret, validate=True)
        except ValueError as e:
            raise VaultError(f"{ENV} is not base64") from e
        if len(key) != 32:
            raise VaultError(f"{ENV} must be 32 bytes in base64; make one with `python -m thespis projects secret`")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # the thespis[server] extra
        self._aead = AESGCM(key)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Vault | None:
        secret = (os.environ if env is None else env).get(ENV, "").strip()
        return cls(secret) if secret else None

    def seal(self, project: str, data: dict) -> str:
        nonce = secrets.token_bytes(12)
        sealed = self._aead.encrypt(nonce, json.dumps(data).encode(), project.encode())
        return f"{VERSION}:{base64.b64encode(nonce + sealed).decode()}"

    def open(self, project: str, sealed: str) -> dict:
        from cryptography.exceptions import InvalidTag
        version, _, body = sealed.partition(":")
        if version != VERSION:
            raise VaultError(f"sealed with {version!r}; this Thespis reads {VERSION}")
        raw = base64.b64decode(body)
        try:
            return json.loads(self._aead.decrypt(raw[:12], raw[12:], project.encode()))
        except InvalidTag as e:
            raise VaultError("the model settings don't open with this key, or belong to another project") from e
