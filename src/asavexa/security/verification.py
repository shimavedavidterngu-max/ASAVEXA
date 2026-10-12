"""Email verification at sign-up: the welcome email, a 6-digit code, confirming the code, and resending.

All state lives in the shared document store (no new table, no migration):
  emailv_code  / <user id>      the single active code: salted hash, expiry, state. A new code supersedes the old one.
  emailv_ok    / <user id>      present once the address was verified by a correct code (never set any other way).
  emailv_req   / <email hash>   how many codes were asked for this email recently (cooldown + hourly cap), real account or not.
  emailv_try   / <email hash>   wrong guesses for this email, real account or not.
  welcome_sent / <user id>      the welcome email was accepted by the provider once: it is never sent a second time.

Truthfulness: the registration answer says "sent" only when the provider accepted the message. A provider that is down, rejects the
request or is not configured gives "not sent" and the account is kept. Accepted is not the same as delivered: delivery, bounce and
complaint events arrive separately (see mailevents.py). Codes are never returned, logged or stored in plain text.
Public answers to resend/confirm are identical for real, unknown and already-verified emails.
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

from . import emailtemplates as T
from .errors import VerificationError, VerificationRateLimitError, VerificationUnavailableError
from .mailer import EmailDeliveryError, EmailSettings, Mailer

logger = logging.getLogger("asavexa.verification")

MAX_WRONG_CODES = 5
RESEND_COOLDOWN_SECONDS = 60
MAX_CODES_PER_HOUR = 5

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
GENERIC_RESEND_MESSAGE = ("If this email address can be verified, a new 6-digit code is on its way. It can take a few minutes. "
                          "Check your spam folder too. Any earlier code no longer works.")
BAD_CODE_MESSAGE = "That code is incorrect or has expired. Check it and try again, or ask for a new code."
LOCKED_MESSAGE = "Too many incorrect codes. Ask for a new code to continue."
VERIFIED_MESSAGE = "Your email address has been verified."
UNAVAILABLE_MESSAGE = ("Email is not set up on this platform yet, so no verification code can be sent. "
                       "Ask the person who runs ASAVEXA to finish the email setup.")


def _utc():
    return datetime.now(timezone.utc)


def _h(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def _threaded(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


def normalise_email(email) -> str:
    e = (email or "").strip().lower() if isinstance(email, str) else ""
    if not _EMAIL.match(e):
        raise VerificationError("Enter a valid email address.")
    return e


class EmailVerificationService:
    def __init__(self, store, identity, mailer: Optional[Mailer], log: Callable[..., None], now: Callable[[], datetime] = _utc,
                 commit: Callable[[], None] = lambda: None, settings: Optional[EmailSettings] = None,
                 dispatch: Callable[[Callable[[], None]], None] = _threaded):
        self.store, self.identity, self.mailer, self.log, self.now, self.commit = store, identity, mailer, log, now, commit
        self.settings = settings or EmailSettings()
        self.dispatch = dispatch
        self.ttl = timedelta(minutes=self.settings.verification_ttl_minutes)

    @property
    def available(self) -> bool:
        return self.mailer is not None

    @property
    def minutes(self) -> int:
        return int(self.ttl.total_seconds() // 60)

    # ------------------------------------------------------------------ helpers
    def is_verified(self, user_id: str) -> bool:
        return self.store.get("emailv_ok", user_id) is not None

    def _code_hash(self, salt: str, user_id: str, code: str) -> str:
        return _h("emailv", salt, user_id, code)

    def _issue_code(self, user_id: str) -> str:
        """A fresh code replaces any earlier one. Only its salted hash is stored."""
        code = f"{secrets.randbelow(10 ** 6):06d}"
        salt, now = secrets.token_hex(8), self.now()
        self.store.put("emailv_code", user_id, {"salt": salt, "hash": self._code_hash(salt, user_id, code),
                                                "expires_at": (now + self.ttl).isoformat(), "created_at": now.isoformat(), "state": "pending"})
        return code

    def _deliver(self, to: str, mail: T.Email, kind: str, user_id: str) -> bool:
        """True only when the provider accepted the message. Failure is logged for the operator without the address, code or body."""
        try:
            self.mailer.send(to, mail.subject, mail.text, mail.html)
            return True
        except EmailDeliveryError as e:
            logger.error("verification_email_failed kind=%s user=%s provider=%s reason=%s", kind, user_id, getattr(self.mailer, "name", "?"), e)
        except Exception:  # pragma: no cover - a send must never break the request
            logger.exception("verification_email_error kind=%s user=%s", kind, user_id)
        return False

    def _welcome(self, user) -> bool:
        """The welcome email, once per account: a second call (a retry, a resend) never sends it again."""
        if self.store.get("welcome_sent", user.id) is not None:
            return True
        mail = T.account_created(self.settings.app_base_url, self.settings.support_email, verification_pending=True)
        if self._deliver(user.email, mail, "welcome", user.id):
            self.store.put("welcome_sent", user.id, {"at": self.now().isoformat()})
            self.log("ACCOUNT_WELCOME_EMAIL_ACCEPTED", user.id, user.id, reason="provider accepted the welcome email")
            return True
        return False

    def _note_request(self, key: str) -> None:
        now = self.now()
        rec = self.store.get("emailv_req", key, for_update=True) or {"times": []}
        times = [t for t in (datetime.fromisoformat(x) for x in rec["times"]) if now - t < timedelta(hours=1)] + [now]
        self.store.put("emailv_req", key, {"times": [t.isoformat() for t in times]})
        self.store.put("emailv_try", key, {"count": 0})

    # ------------------------------------------------------------------ right after sign-up
    def on_registered(self, user) -> dict:
        """Sends the welcome email and the verification code for a NEW account and says truthfully what happened.
        Called once per created account (a duplicate sign-up fails before this point, so it can never send a second email)."""
        if not self.available:
            logger.error("verification_email_not_sent user=%s reason=email provider not configured", user.id)
            return {"sent": False, "reason": "not_configured", "cooldown_seconds": 0, "expires_in_minutes": self.minutes}
        self.commit()                                        # the account is saved before anything is sent
        code = self._issue_code(user.id)
        welcome_ok = self._welcome(user)
        code_ok = self._deliver(user.email, T.verify_email(code, self.minutes), "code", user.id)
        if code_ok:
            self._note_request(_h("email", user.email.lower()))
            self.log("EMAIL_VERIFICATION_SENT", user.id, user.id, reason="verification code email accepted by the provider")
        self.commit()
        ok = welcome_ok and code_ok
        return {"sent": ok, "reason": None if ok else "delivery_failed", "code_sent": code_ok, "welcome_sent": welcome_ok,
                "cooldown_seconds": RESEND_COOLDOWN_SECONDS if code_ok else 0, "expires_in_minutes": self.minutes}

    # ------------------------------------------------------------------ resend
    def request(self, email) -> dict:
        if not self.available:
            raise VerificationUnavailableError(UNAVAILABLE_MESSAGE)
        e = normalise_email(email)
        key = _h("email", e)
        now = self.now()
        rec = self.store.get("emailv_req", key, for_update=True) or {"times": []}
        times = [t for t in (datetime.fromisoformat(x) for x in rec["times"]) if now - t < timedelta(hours=1)]
        if times:
            wait = RESEND_COOLDOWN_SECONDS - int((now - max(times)).total_seconds())
            if wait > 0:
                raise VerificationRateLimitError(f"Please wait {wait} seconds before asking for another code.")
        if len(times) >= MAX_CODES_PER_HOUR:
            raise VerificationRateLimitError("Too many codes were requested for this email. Please try again in an hour.")
        self._note_request(key)
        user = self.identity.users.get_by_email(e)
        if user is not None and user.is_active and not self.is_verified(user.id):
            code = self._issue_code(user.id)
            self.log("EMAIL_VERIFICATION_REQUESTED", user.id, user.id, reason="verification code re-issued")

            def go(u=user, c=code):
                self._welcome(u)                                # sent now if it never got through the first time
                self._deliver(u.email, T.verify_email(c, self.minutes), "code", u.id)
            self.dispatch(go)
        else:
            self._code_hash("0" * 16, "none", f"{secrets.randbelow(10 ** 6):06d}")      # same work for unknown or already-verified emails
        return {"message": GENERIC_RESEND_MESSAGE, "cooldown_seconds": RESEND_COOLDOWN_SECONDS, "expires_in_minutes": self.minutes}

    # ------------------------------------------------------------------ confirm the code
    def confirm(self, email, code) -> dict:
        e = normalise_email(email)
        c = code.strip() if isinstance(code, str) else ""
        if not re.fullmatch(r"\d{6}", c):
            raise VerificationError("Enter the 6-digit code from the email.")
        key = _h("email", e)
        now = self.now()
        tries = self.store.get("emailv_try", key, for_update=True) or {"count": 0}
        if tries["count"] >= MAX_WRONG_CODES:
            raise VerificationRateLimitError(LOCKED_MESSAGE)
        user = self.identity.users.get_by_email(e)
        rec = self.store.get("emailv_code", user.id, for_update=True) if user is not None else None
        ok = False
        if rec is not None and rec.get("state") == "pending" and datetime.fromisoformat(rec["expires_at"]) > now:
            ok = hmac.compare_digest(rec["hash"], self._code_hash(rec["salt"], user.id, c))
        else:
            self._code_hash("0" * 16, "none", c)
        if not ok:
            tries["count"] += 1
            self.store.put("emailv_try", key, tries)
            if user is not None:
                self.log("EMAIL_VERIFICATION_CODE_REJECTED", user.id, user.id, reason="wrong, expired or used code")
            self.commit()                                    # a refused attempt must still count
            raise VerificationRateLimitError(LOCKED_MESSAGE) if tries["count"] >= MAX_WRONG_CODES else VerificationError(BAD_CODE_MESSAGE)
        rec["state"] = "used"                                # single use: gone the moment it works
        self.store.put("emailv_code", user.id, rec)
        self.store.put("emailv_ok", user.id, {"at": now.isoformat()})
        self.store.put("emailv_try", key, {"count": 0})
        self.log("EMAIL_VERIFIED", user.id, user.id, reason="email address verified with a code")
        return {"verified": True, "message": VERIFIED_MESSAGE}
