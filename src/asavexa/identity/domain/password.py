"""
Password hashing — stdlib only (hashlib.pbkdf2_hmac), so the tested core
of the Identity module needs no external dependency, matching the
Accounting Engine's discipline.

For production, consider a dedicated password-hashing library (argon2
or bcrypt via `passlib`) once you can install dependencies — PBKDF2 is
an acceptable, NIST-recognised choice but argon2 is generally preferred
for new systems. Swapping the implementation only requires changing
`hash_password`/`verify_password`; nothing else references the hash
format directly.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from . import password_policy

_ALGORITHM = "pbkdf2_sha256"
# OWASP Password Storage Cheat Sheet's actual current recommendation for
# PBKDF2-HMAC-SHA256 is 600,000 iterations (not 260,000 — a prior
# version of this comment cited "early 2023 guidance" for 260,000, which
# was never the real OWASP figure at any point; verified directly
# against the cheat sheet during the Phase 4 security audit and
# corrected here, not assumed). Safe to raise with zero migration step:
# verify_password() below reads the iteration count from each stored
# hash string itself, not from this constant, so every previously
# issued hash remains verifiable unchanged — only newly hashed
# passwords use the new count. Never decrease this value.
_ITERATIONS = 600_000
_SALT_BYTES = 16

# A fixed, valid-format hash with no corresponding real password —
# IdentityService.authenticate() verifies against this when the
# supplied email doesn't match any account, so a nonexistent-email
# login attempt costs the same PBKDF2 work as a wrong-password attempt
# against a real account. Found during the Phase 4 security audit:
# without this, authenticate() returned immediately (skipping
# verify_password entirely) when the email didn't exist, creating a
# timing side-channel an attacker could use to enumerate which emails
# have accounts, just by measuring response time. This constant's
# specific value is arbitrary and never needs to change — it exists
# only to be a well-formed target for a wasted comparison, never to be
# a real credential. Defined at the bottom of this file, after
# hash_password exists to compute it.


def hash_password(password: str) -> str:
    # One policy for sign-up and reset: identity/domain/password_policy.py (8-128 characters, a letter and a number, not a
    # very common password). The password is hashed exactly as given: never trimmed, never altered.
    password_policy.check(password)
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGORITHM}${_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_str, salt_hex, hash_hex = stored_hash.split("$")
    except ValueError:
        return False
    if algorithm != _ALGORITHM:
        return False
    iterations = int(iterations_str)
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(hash_hex)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


DUMMY_HASH = hash_password("not-a-real-password-1-used-only-to-equalize-login-timing")
