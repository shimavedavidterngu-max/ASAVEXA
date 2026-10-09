"""RFC 6238 time-based one-time passwords (what Google Authenticator, Microsoft Authenticator, Authy and 1Password use)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from typing import Optional
from urllib.parse import quote


def new_secret(nbytes: int = 20) -> str:
    """Base32 secret (160 bits by default), the form authenticator apps accept."""
    return base64.b32encode(secrets.token_bytes(nbytes)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    s = secret.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def hotp(secret: str, counter: int, digits: int = 6, algo=hashlib.sha1) -> str:
    mac = hmac.new(_key(secret), struct.pack(">Q", counter), algo).digest()
    off = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def totp_at(secret: str, t: float, step: int = 30, digits: int = 6, algo=hashlib.sha1) -> str:
    return hotp(secret, int(t // step), digits, algo)


def verify(secret: str, code: str, now: Optional[float] = None, window: int = 1, step: int = 30,
           last_used_step: Optional[int] = None, digits: int = 6) -> Optional[int]:
    """Returns the matched time-step (so the caller can remember it) or None.
    A step at or before `last_used_step` is refused, so a code cannot be used twice. Constant-time comparison."""
    code = (code or "").strip().replace(" ", "")
    if len(code) != digits or not code.isdigit():
        return None
    now = time.time() if now is None else now
    cur = int(now // step)
    hit = None
    for s in range(cur - window, cur + window + 1):
        ok = hmac.compare_digest(hotp(secret, s, digits), code)
        if ok and hit is None and (last_used_step is None or s > last_used_step):
            hit = s
    return hit


def otpauth_uri(secret: str, account: str, issuer: str = "ASAVEXA") -> str:
    return (f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits=6&period=30")


def new_recovery_codes(n: int = 10) -> list:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return ["".join(secrets.choice(alphabet) for _ in range(5)) + "-" + "".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(n)]


def hash_recovery(code: str) -> str:
    return hashlib.sha256(code.strip().upper().replace(" ", "").encode()).hexdigest()
