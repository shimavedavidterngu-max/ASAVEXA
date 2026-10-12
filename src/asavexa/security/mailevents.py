"""Delivery events from the email provider (Resend sends them through Svix webhooks): delivered, bounced, complained, delayed, failed.

Why: the provider accepting a message is not proof it reached an inbox. These events are the evidence. They are recorded per recipient
(by a hash of the address, never the address itself) and logged without addresses or message content.

Security: every request is checked against the shared signing secret (RESEND_WEBHOOK_SECRET, "whsec_..."): a missing or wrong
signature, a stale timestamp (older than 5 minutes) or a message id seen before is refused. With no secret configured the endpoint says so
and records nothing: an unsigned webhook is never trusted.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from .errors import WebhookError

logger = logging.getLogger("asavexa.mailevents")

TOLERANCE_SECONDS = 300
KNOWN = {"email.sent": "sent", "email.delivered": "delivered", "email.delivery_delayed": "delayed", "email.bounced": "bounced",
         "email.complained": "complained", "email.failed": "failed", "email.suppressed": "suppressed"}


def _utc():
    return datetime.now(timezone.utc)


def recipient_key(address: str) -> str:
    return hashlib.sha256(("mail\x1f" + address.strip().lower()).encode()).hexdigest()


class MailEvents:
    def __init__(self, store, secret: Optional[str], now: Callable[[], datetime] = _utc):
        self.store, self.secret, self.now = store, (secret or "").strip(), now

    @property
    def configured(self) -> bool:
        return bool(self.secret)

    def _key(self) -> bytes:
        s = self.secret[6:] if self.secret.startswith("whsec_") else self.secret
        try:
            return base64.b64decode(s)
        except Exception:
            return s.encode()

    def verify(self, raw: bytes, headers) -> None:
        if not self.configured:
            raise WebhookError("Delivery webhooks are not set up on this platform (RESEND_WEBHOOK_SECRET).")
        h = {str(k).lower(): v for k, v in dict(headers).items()}
        mid, ts, sig = h.get("svix-id"), h.get("svix-timestamp"), h.get("svix-signature")
        if not (mid and ts and sig):
            raise WebhookError("Missing webhook signature.")
        try:
            sent_at = datetime.fromtimestamp(int(ts), timezone.utc)
        except (ValueError, OverflowError, OSError):
            raise WebhookError("Bad webhook timestamp.") from None
        if abs((self.now() - sent_at).total_seconds()) > TOLERANCE_SECONDS:
            raise WebhookError("Webhook timestamp is too old or too new.")
        signed = f"{mid}.{ts}.".encode() + raw
        want = base64.b64encode(hmac.new(self._key(), signed, hashlib.sha256).digest()).decode()
        given = [p.split(",", 1)[1] for p in sig.split() if p.startswith("v1,") and "," in p]
        if not any(hmac.compare_digest(want, g) for g in given):
            raise WebhookError("Webhook signature does not match.")

    def handle(self, raw: bytes, headers) -> dict:
        self.verify(raw, headers)
        mid = {str(k).lower(): v for k, v in dict(headers).items()}["svix-id"]
        if self.store.get("mail_event_seen", mid) is not None:
            return {"ok": True, "duplicate": True}              # a replay or a provider retry: already recorded
        try:
            event = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise WebhookError("Webhook body is not valid JSON.") from None
        kind = KNOWN.get(str(event.get("type", "")))
        data = event.get("data") or {}
        to = data.get("to")
        recipients = [to] if isinstance(to, str) else [x for x in (to or []) if isinstance(x, str)]
        self.store.put("mail_event_seen", mid, {"at": self.now().isoformat()})
        if kind is None or not recipients:
            return {"ok": True, "recorded": False}
        for r in recipients:
            k = recipient_key(r)
            self.store.put("mail_status", k, {"status": kind, "at": self.now().isoformat(), "message_id": str(data.get("email_id") or "")[:64]})
            if kind in ("bounced", "complained", "failed", "suppressed"):
                logger.warning("mail_delivery_problem status=%s recipient=%s", kind, k[:12])
        return {"ok": True, "recorded": True}

    def status_for(self, address: str) -> Optional[dict]:
        return self.store.get("mail_status", recipient_key(address))
