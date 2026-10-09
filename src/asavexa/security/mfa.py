"""Multi-factor authentication: authenticator-app codes (TOTP) plus one-time recovery codes.

The TOTP secret is stored sealed (encrypted) under the platform keyring, never in plain text. A code can be used once
(replay protection), and repeated wrong codes lock the factor for a while. Logging in with MFA is two steps: the password
check returns a short-lived, single-use challenge; the code turns the challenge into a session."""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from . import totp
from .crypto import KeyProvider, open_text, seal_text
from .errors import MfaError, MfaLockedError
from .store import DocStore

MAX_FAILURES = 5
LOCK_MINUTES = 15
CHALLENGE_SECONDS = 300


def _utc() -> datetime:
    return datetime.now(timezone.utc)


class MfaService:
    def __init__(self, store: DocStore, keys: KeyProvider, now: Callable[[], datetime] = _utc, issuer: str = "ASAVEXA"):
        self.store, self.keys, self.now, self.issuer = store, keys, now, issuer

    # --- state
    def _doc(self, user_id: str) -> Optional[dict]:
        return self.store.get("mfa", user_id)

    def is_enabled(self, user_id: str) -> bool:
        d = self._doc(user_id)
        return bool(d and d.get("enabled"))

    def status(self, user_id: str) -> dict:
        d = self._doc(user_id) or {}
        return {"enabled": bool(d.get("enabled")), "pending_setup": bool(d and not d.get("enabled")),
                "recovery_codes_left": len(d.get("recovery", [])) if d.get("enabled") else 0, "enabled_at": d.get("enabled_at")}

    # --- enrolment
    def begin_enrolment(self, user_id: str, account: str) -> dict:
        d = self._doc(user_id)
        if d and d.get("enabled"):
            raise MfaError("Multi-factor authentication is already on. Turn it off first to set it up again.")
        secret = totp.new_secret()
        self.store.put("mfa", user_id, {"enabled": False, "secret": seal_text(self.keys, secret, "mfa:" + user_id), "failed": 0,
                                        "created_at": self.now().isoformat()})
        return {"secret": secret, "otpauth_uri": totp.otpauth_uri(secret, account, self.issuer), "issuer": self.issuer}

    def confirm_enrolment(self, user_id: str, code: str) -> dict:
        d = self._doc(user_id)
        if not d or d.get("enabled"):
            raise MfaError("Start the setup first.")
        step = totp.verify(open_text(self.keys, d["secret"], "mfa:" + user_id), code, now=self.now().timestamp())
        if step is None:
            raise MfaError("That code is not right. Check the time on your phone and try the newest code.")
        codes = totp.new_recovery_codes()
        d.update(enabled=True, enabled_at=self.now().isoformat(), last_step=step, failed=0, locked_until=None,
                 recovery=[totp.hash_recovery(c) for c in codes])
        self.store.put("mfa", user_id, d)
        return {"recovery_codes": codes}

    # --- verifying
    def verify(self, user_id: str, code: str) -> str:
        """Returns 'TOTP' or 'RECOVERY'. Raises MfaError / MfaLockedError."""
        d = self.store.get("mfa", user_id, for_update=True)
        if not d or not d.get("enabled"):
            raise MfaError("Multi-factor authentication is not set up for this account.")
        now = self.now()
        if d.get("locked_until") and now < datetime.fromisoformat(d["locked_until"]):
            raise MfaLockedError("Too many wrong codes. Try again in a few minutes.")
        code = (code or "").strip()
        step = totp.verify(open_text(self.keys, d["secret"], "mfa:" + user_id), code, now=now.timestamp(), last_used_step=d.get("last_step"))
        if step is not None:
            d.update(last_step=step, failed=0, locked_until=None)
            self.store.put("mfa", user_id, d)
            return "TOTP"
        h = totp.hash_recovery(code)
        if h in d.get("recovery", []):
            d["recovery"].remove(h)
            d.update(failed=0, locked_until=None)
            self.store.put("mfa", user_id, d)
            return "RECOVERY"
        d["failed"] = d.get("failed", 0) + 1
        if d["failed"] >= MAX_FAILURES:
            d["locked_until"] = (now + timedelta(minutes=LOCK_MINUTES)).isoformat()
            d["failed"] = 0
        self.store.put("mfa", user_id, d)
        raise MfaError("That code is not right.")

    def disable(self, user_id: str, code: str) -> None:
        self.verify(user_id, code)
        self.store.delete("mfa", user_id)

    def regenerate_recovery(self, user_id: str, code: str) -> list:
        self.verify(user_id, code)
        d = self._doc(user_id)
        codes = totp.new_recovery_codes()
        d["recovery"] = [totp.hash_recovery(c) for c in codes]
        self.store.put("mfa", user_id, d)
        return codes

    # --- login challenge (password was right, code still needed)
    def issue_challenge(self, user_id: str) -> str:
        payload = json.dumps({"u": user_id, "exp": (self.now() + timedelta(seconds=CHALLENGE_SECONDS)).timestamp(), "n": secrets.token_hex(8)})
        return seal_text(self.keys, payload, "mfa-challenge")

    def redeem_challenge(self, challenge: str, code: str) -> str:
        """Returns the user id. The challenge is single-use once a code is accepted."""
        try:
            p = json.loads(open_text(self.keys, challenge, "mfa-challenge"))
        except Exception:
            raise MfaError("This sign-in has expired. Please start again.")
        if self.now().timestamp() > p["exp"] or self.store.get("mfa_challenge_used", p["n"]):
            raise MfaError("This sign-in has expired. Please start again.")
        self.verify(p["u"], code)
        self.store.put("mfa_challenge_used", p["n"], {"user": p["u"], "at": self.now().isoformat()})
        return p["u"]
