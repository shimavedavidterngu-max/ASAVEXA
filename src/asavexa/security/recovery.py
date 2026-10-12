"""Password recovery: request a code by email, verify it, then set a new password.

Design (all state lives in the shared document store, so no new table or migration is needed):
  pwreset_code  / <user id>     the single active code: salted hash, expiry, state. A new code replaces (supersedes) the old one.
  pwreset_auth  / <user id>     the single-use reset authorisation issued after the code is verified (hash only, short expiry).
  pwreset_req   / <email hash>  how many codes were asked for this email recently (cooldown + hourly cap), whether or not an account exists.
  pwreset_try   / <email hash>  wrong guesses for this email, whether or not an account exists.
  pwd_epoch     / <user id>     when the password last changed; sessions older than this are refused.

Privacy: every public answer is the same whether or not the email belongs to an account. Counters are keyed by the email, not by
the account, so locking and cooldowns look identical for real and made-up addresses. Codes are never returned, logged or put in URLs.
The code is stored only as a salted hash and compared in constant time. A reset authorisation is bound to one account and works once.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from ..identity.domain import password_policy
from .errors import RecoveryError, RecoveryRateLimitError, RecoveryUnavailableError
from . import emailtemplates as T
from .mailer import EmailDeliveryError, Mailer

logger = logging.getLogger("asavexa.recovery")

CODE_TTL = timedelta(minutes=10)
AUTH_TTL = timedelta(minutes=10)
MAX_WRONG_CODES = 5
RESEND_COOLDOWN_SECONDS = 60
MAX_CODES_PER_HOUR = 5

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
GENERIC_REQUEST_MESSAGE = ("If an account can be recovered with that email address, a verification code is on its way. "
                           "It can take a few minutes. Check your spam folder, or request another code when the timer ends.")
BAD_CODE_MESSAGE = "That code is incorrect or has expired. Check it and try again, or request a new code."
LOCKED_MESSAGE = "Too many incorrect codes. Request a new code to continue."


def _utc():
    return datetime.now(timezone.utc)


def _h(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def normalise_email(email) -> str:
    e = (email or "").strip().lower() if isinstance(email, str) else ""
    if not _EMAIL.match(e):
        raise RecoveryError("Enter a valid email address.")
    return e


def _threaded(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


class RecoveryService:
    def __init__(self, store, identity, mailer: Optional[Mailer], log: Callable[..., None], revoke_sessions: Callable[[str], None],
                 now: Callable[[], datetime] = _utc, dispatch: Callable[[Callable[[], None]], None] = _threaded,
                 commit: Callable[[], None] = lambda: None, code_ttl: timedelta = CODE_TTL, support_email: Optional[str] = None):
        """log(action, actor, entity_id, **kw) writes an audit event. revoke_sessions(user_id) signs the person out everywhere.
        dispatch runs the email send: a background thread in production (so a real account and an unknown one take the same
        time), a direct call in tests."""
        self.store, self.identity, self.mailer, self.log, self.revoke_sessions, self.now, self.dispatch, self.commit = store, identity, mailer, log, revoke_sessions, now, dispatch, commit
        self.code_ttl, self.support_email = code_ttl, support_email

    @property
    def available(self) -> bool:
        return self.mailer is not None

    # ------------------------------------------------------------------ helpers
    def _find_user(self, email: str):
        u = self.identity.users.get_by_email(email)
        return u if u is not None else None

    def _code_hash(self, salt: str, user_id: str, code: str) -> str:
        return _h("code", salt, user_id, code)

    def _send(self, to: str, subject: str, text: str, html: str, what: str, user_id: str) -> None:
        mailer = self.mailer

        def go():
            try:
                mailer.send(to, subject, text, html)
            except EmailDeliveryError as e:
                # never the code, the address or the body: only that a delivery failed and why, for the operator
                logger.error("recovery_email_failed kind=%s user=%s provider=%s reason=%s", what, user_id, getattr(mailer, "name", "?"), e)
            except Exception:  # pragma: no cover - defensive: a send must never break the request
                logger.exception("recovery_email_error kind=%s user=%s", what, user_id)
        self.dispatch(go)

    # ------------------------------------------------------------------ step 1: request (also used to resend)
    def request(self, email) -> dict:
        if not self.available:
            raise RecoveryUnavailableError("Password recovery by email is not set up on this platform yet. "
                                           "Ask your organisation's administrator, or the person who runs ASAVEXA, to reset it.")
        e = normalise_email(email)
        key = _h("email", e)
        now = self.now()
        rec = self.store.get("pwreset_req", key, for_update=True) or {"times": []}
        times = [t for t in (datetime.fromisoformat(x) for x in rec["times"]) if now - t < timedelta(hours=1)]
        if times:
            wait = RESEND_COOLDOWN_SECONDS - int((now - max(times)).total_seconds())
            if wait > 0:
                raise RecoveryRateLimitError(f"Please wait {wait} seconds before asking for another code.")
        if len(times) >= MAX_CODES_PER_HOUR:
            raise RecoveryRateLimitError("Too many codes were requested for this email. Please try again in an hour.")
        times.append(now)
        self.store.put("pwreset_req", key, {"times": [t.isoformat() for t in times]})
        self.store.put("pwreset_try", key, {"count": 0})          # a new code starts with a clean slate of guesses

        user = self._find_user(e)
        code = f"{secrets.randbelow(10 ** 6):06d}"
        salt = secrets.token_hex(8)
        if user is not None and user.is_active:
            self.store.put("pwreset_code", user.id, {"salt": salt, "hash": self._code_hash(salt, user.id, code), "expires_at": (now + self.code_ttl).isoformat(),
                                                     "created_at": now.isoformat(), "state": "pending"})      # replaces any earlier code
            self.store.delete("pwreset_auth", user.id)                                                        # an older reset authorisation dies too
            self.log("PASSWORD_RECOVERY_REQUESTED", user.id, user.id, reason="verification code issued")
            m = T.recovery_code(code, int(self.code_ttl.total_seconds() // 60))
            self._send(user.email, m.subject, m.text, m.html, "code", user.id)
        else:
            self._dummy(salt, code)
            self.log("PASSWORD_RECOVERY_REQUESTED", e, _h("unknown", e)[:36], reason="no recoverable account")
        return {"message": GENERIC_REQUEST_MESSAGE, "cooldown_seconds": RESEND_COOLDOWN_SECONDS, "expires_in_minutes": int(self.code_ttl.total_seconds() // 60)}

    def _dummy(self, salt: str, code: str) -> None:
        self._code_hash(salt, "none", code)

    # ------------------------------------------------------------------ step 2: verify the code
    def verify(self, email, code) -> dict:
        e = normalise_email(email)
        c = code.strip() if isinstance(code, str) else ""
        if not re.fullmatch(r"\d{6}", c):
            raise RecoveryError("Enter the 6-digit code from the email.")
        key = _h("email", e)
        now = self.now()
        tries = self.store.get("pwreset_try", key, for_update=True) or {"count": 0}
        if tries["count"] >= MAX_WRONG_CODES:
            raise RecoveryRateLimitError(LOCKED_MESSAGE)
        user = self._find_user(e)
        rec = self.store.get("pwreset_code", user.id, for_update=True) if user is not None else None
        ok = False
        if rec is not None and rec.get("state") == "pending" and datetime.fromisoformat(rec["expires_at"]) > now:
            ok = hmac.compare_digest(rec["hash"], self._code_hash(rec["salt"], user.id, c))
        else:
            self._dummy("0" * 16, c)
        if not ok:
            tries["count"] += 1
            self.store.put("pwreset_try", key, tries)
            if user is not None:
                self.log("PASSWORD_RECOVERY_CODE_REJECTED", user.id, user.id, reason="wrong or expired code")
            self.commit()                                   # a refused attempt must still count
            raise RecoveryRateLimitError(LOCKED_MESSAGE) if tries["count"] >= MAX_WRONG_CODES else RecoveryError(BAD_CODE_MESSAGE)
        # success: the code is used up, a short-lived single-use reset authorisation is issued
        rec["state"] = "used"
        self.store.put("pwreset_code", user.id, rec)
        token = secrets.token_urlsafe(32)
        self.store.put("pwreset_auth", user.id, {"hash": _h("auth", user.id, token), "expires_at": (now + AUTH_TTL).isoformat(), "used": False})
        self.store.put("pwreset_try", key, {"count": 0})
        self.log("PASSWORD_RECOVERY_CODE_VERIFIED", user.id, user.id, reason="email verified")
        return {"reset_token": token, "expires_in_minutes": int(AUTH_TTL.total_seconds() // 60)}

    # ------------------------------------------------------------------ step 3 and 4: set the new password
    def reset(self, email, reset_token, new_password, confirm_password=None) -> dict:
        e = normalise_email(email)
        if confirm_password is not None and new_password != confirm_password:
            raise RecoveryError("The two passwords do not match.")
        problems = password_policy.problems(new_password)
        if problems:
            from ..identity.domain.errors import WeakPasswordError
            raise WeakPasswordError(" ".join(problems))
        now = self.now()
        user = self._find_user(e)
        auth = self.store.get("pwreset_auth", user.id, for_update=True) if user is not None else None
        good = False
        if auth is not None and not auth.get("used") and datetime.fromisoformat(auth["expires_at"]) > now and isinstance(reset_token, str):
            good = hmac.compare_digest(auth["hash"], _h("auth", user.id, reset_token))
        if not good:
            if user is not None:
                self.log("PASSWORD_RESET_REFUSED", user.id, user.id, reason="no valid verification")
            self.commit()
            raise RecoveryError("This reset link has expired or was already used. Start again from \"Forgot password?\".")
        # atomic: one transaction (the request's) changes the password, burns the authorisation and records the epoch
        self.store.put("pwreset_auth", user.id, {**auth, "used": True})
        self.store.delete("pwreset_auth", user.id)
        self.store.delete("pwreset_code", user.id)
        self.identity.set_password(user.id, new_password, reason="password reset by email verification")
        self.store.put("pwd_epoch", user.id, {"at": now.isoformat()})
        self.revoke_sessions(user.id)
        self.log("PASSWORD_RESET_COMPLETED", user.id, user.id, reason="password reset; other sessions signed out")
        if self.available:
            m = T.password_changed(self.support_email)
            self._send(user.email, m.subject, m.text, m.html, "changed", user.id)
        return {"message": "Your password has been reset successfully. You can now sign in with your new password."}
