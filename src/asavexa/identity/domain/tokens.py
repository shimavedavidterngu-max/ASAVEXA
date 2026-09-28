"""
Session token generation and storage hashing.

The raw token is returned to the client exactly once, at login. Only its
SHA-256 hash is ever persisted, so a database read (or leak) does not
hand out valid bearer tokens — the same principle as password hashing,
using a fast hash here because the token itself is already
high-entropy (unlike a human-chosen password).
"""
from __future__ import annotations

import hashlib
import secrets

_TOKEN_BYTES = 32


def generate_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
