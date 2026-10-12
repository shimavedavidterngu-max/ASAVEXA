"""Transactional email for ASAVEXA. No provider existed before this, so this is the one place email leaves the platform.

Providers (chosen by EMAIL_PROVIDER, or the older name ASAVEXA_EMAIL_PROVIDER):
  resend   HTTPS API (https://resend.com). Needs EMAIL_API_KEY (or RESEND_API_KEY) and a sender: EMAIL_FROM_ADDRESS (+ optional EMAIL_FROM_NAME),
           or the older ASAVEXA_EMAIL_FROM. The address must be on a domain you verified with the provider.
           Recommended on Render's free plan, which blocks outbound SMTP.
  smtp     ASAVEXA_SMTP_HOST, ASAVEXA_SMTP_PORT (587 = STARTTLS, 465 = SSL), ASAVEXA_SMTP_USER, ASAVEXA_SMTP_PASSWORD, and the sender as above.
  (unset)  email is NOT configured: recovery and verification are switched off and say so. Nothing is pretended.
Tests use OutboxMailer, which keeps messages in memory. It is never selected from the environment.

Credentials only ever come from environment variables. A mailer raises EmailDeliveryError when the provider reports failure,
so no caller can claim a message was delivered when it was not. Bodies are never logged."""
from __future__ import annotations

import json
import logging
import os
import smtplib
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import List, Optional, Protocol

logger = logging.getLogger("asavexa.mailer")


class EmailDeliveryError(Exception):
    """The provider did not accept the message."""


class Mailer(Protocol):
    name: str

    def send(self, to: str, subject: str, text: str, html: Optional[str] = None) -> Optional[str]:
        """Hands the message to the provider. Returns the provider's message id when it gives one. Raises EmailDeliveryError otherwise."""
        ...


@dataclass
class OutboxMailer:
    """In-memory mailer for tests. `fail` makes every send raise, to test delivery failure."""
    name: str = "outbox"
    sent: List[dict] = field(default_factory=list)
    fail: bool = False

    def send(self, to, subject, text, html=None):
        if self.fail:
            raise EmailDeliveryError("test mailer is set to fail")
        self.sent.append({"to": to, "subject": subject, "text": text, "html": html})
        return f"outbox-{len(self.sent)}"


class ResendMailer:
    name = "resend"

    def __init__(self, api_key: str, sender: str, timeout: float = 10.0, opener=None):
        self.api_key, self.sender, self.timeout = api_key, sender, timeout
        self._open = opener or urllib.request.urlopen

    def send(self, to, subject, text, html=None):
        payload = {"from": self.sender, "to": [to], "subject": subject, "text": text}
        if html:
            payload["html"] = html
        req = urllib.request.Request("https://api.resend.com/emails", data=json.dumps(payload).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "User-Agent": "asavexa/1.0"})
        try:
            with self._open(req, timeout=self.timeout) as r:
                if not 200 <= getattr(r, "status", 200) < 300:
                    raise EmailDeliveryError(f"provider answered {r.status}")
                try:
                    return (json.loads(r.read() or b"{}") or {}).get("id")
                except Exception:       # the message was accepted; a missing id only means no webhook correlation
                    return None
        except urllib.error.HTTPError as e:
            raise EmailDeliveryError(f"provider answered {e.code}") from None
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            raise EmailDeliveryError(f"provider unreachable ({type(e).__name__})") from None


class SmtpMailer:
    name = "smtp"

    def __init__(self, host: str, port: int, user: str, password: str, sender: str, timeout: float = 10.0, factory=None):
        self.host, self.port, self.user, self.password, self.sender, self.timeout = host, port, user, password, sender, timeout
        self._factory = factory

    def send(self, to, subject, text, html=None):
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, to, subject
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")
        try:
            ctx = ssl.create_default_context()
            if self._factory:
                smtp = self._factory(self.host, self.port)
            elif self.port == 465:
                smtp = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=ctx)
            else:
                smtp = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
            with smtp as s:
                if not self._factory and self.port != 465:
                    s.starttls(context=ctx)
                if self.user:
                    s.login(self.user, self.password)
                s.send_message(msg)
            return None
        except (smtplib.SMTPException, OSError, TimeoutError) as e:
            raise EmailDeliveryError(f"smtp failed ({type(e).__name__})") from None


def _env(env, *names) -> str:
    for n in names:
        v = (env.get(n) or "").strip()
        if v:
            return v
    return ""


def sender_from_env(env=None) -> str:
    """'ASAVEXA <no-reply@your-domain>' from EMAIL_FROM_ADDRESS + EMAIL_FROM_NAME, or the older all-in-one ASAVEXA_EMAIL_FROM."""
    env = os.environ if env is None else env
    address = _env(env, "EMAIL_FROM_ADDRESS")
    if address:
        name = _env(env, "EMAIL_FROM_NAME") or "ASAVEXA"
        if "<" in address:           # already 'Name <address>'
            return address
        return f"{name} <{address}>"
    return _env(env, "ASAVEXA_EMAIL_FROM")


def mailer_from_env(env=None) -> Optional[Mailer]:
    """The configured provider, or None when email is not set up (or set up incompletely: that is logged, without secrets)."""
    env = os.environ if env is None else env
    which = _env(env, "EMAIL_PROVIDER", "ASAVEXA_EMAIL_PROVIDER").lower()
    sender = sender_from_env(env)
    if not which:
        return None
    if which == "resend":
        key = _env(env, "EMAIL_API_KEY", "RESEND_API_KEY")
        if key and sender:
            return ResendMailer(key, sender)
    elif which == "smtp":
        host = _env(env, "ASAVEXA_SMTP_HOST")
        if host and sender:
            try:
                port = int(env.get("ASAVEXA_SMTP_PORT") or 587)
            except ValueError:
                port = 0
            if port:
                return SmtpMailer(host, port, env.get("ASAVEXA_SMTP_USER") or "", env.get("ASAVEXA_SMTP_PASSWORD") or "", sender)
    else:
        logger.error("email_misconfigured provider=%s (unknown provider; use resend or smtp)", which)
        return None
    logger.error("email_misconfigured provider=%s (missing settings)", which)
    return None


@dataclass(frozen=True)
class EmailSettings:
    """Non-secret settings that shape the emails and the codes."""
    app_base_url: Optional[str] = None
    support_email: Optional[str] = None
    verification_ttl_minutes: int = 10
    reset_ttl_minutes: int = 10


def _minutes(env, name: str, default: int) -> int:
    try:
        return min(60, max(1, int(env.get(name) or default)))
    except ValueError:
        return default


def email_settings_from_env(env=None) -> EmailSettings:
    env = os.environ if env is None else env
    url = (env.get("APP_BASE_URL") or "").strip().rstrip("/")
    if url and not re.match(r"^https?://[^\s/]+", url):
        logger.error("APP_BASE_URL ignored: it must start with https:// (or http:// for local testing)")
        url = ""
    return EmailSettings(app_base_url=url or None, support_email=(env.get("SUPPORT_EMAIL") or "").strip() or None,
                         verification_ttl_minutes=_minutes(env, "EMAIL_VERIFICATION_CODE_TTL_MINUTES", 10),
                         reset_ttl_minutes=_minutes(env, "PASSWORD_RESET_CODE_TTL_MINUTES", 10))
