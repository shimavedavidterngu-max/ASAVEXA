"""Privacy controls: a person can download what ASAVEXA holds about them and ask for their account to be erased.

Erasure removes the person's identity (email, password, sign-in methods, sessions, access) but cannot delete accounting
records or audit events, which must be kept; those carry only an opaque user id afterwards. An organisation owner approves
the request, and an owner cannot be erased while they are the organisation's last owner."""
from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, List

from ..audit.models import AuditEvent
from ..identity.domain.enums import MembershipStatus, Role
from .errors import NotFoundError, RetentionError, ValidationError
from .store import DocStore


def _utc():
    return datetime.now(timezone.utc)


_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_BEARER = re.compile(r"(?i)\b(bearer|token|authorization|password|secret|code)\b\s*[:=]?\s*[A-Za-z0-9._~+/=-]{8,}")
_LONG_DIGITS = re.compile(r"\b\d{9,19}\b")


def redact(text: str) -> str:
    """For log lines: hides emails, tokens/passwords and long digit strings (account/card-like numbers)."""
    t = _EMAIL.sub(lambda m: m.group(0)[0] + "***@" + m.group(0).split("@")[1], text or "")
    t = _BEARER.sub(lambda m: m.group(1) + "=[redacted]", t)
    return _LONG_DIGITS.sub("[number]", t)


DATA_INVENTORY = [
    {"data": "Email address, password hash (never the password)", "where": "Database: users", "why": "Sign-in", "kept": "Until erasure"},
    {"data": "Organisation memberships and roles", "where": "Database: memberships", "why": "Access control", "kept": "Until erasure (marked revoked)"},
    {"data": "Sessions: device description, network address, times", "where": "Database: security_docs", "why": "Security and the device list", "kept": "Removed on erasure"},
    {"data": "Authenticator secret (encrypted) and recovery-code hashes", "where": "Database: security_docs", "why": "Multi-factor sign-in", "kept": "Removed on erasure"},
    {"data": "Audit events naming the person's id", "where": "Database: audit_events", "why": "Accountability; legal record", "kept": "Kept: only the opaque id remains after erasure"},
    {"data": "Journals, evidence and imports the person created", "where": "Database and file storage", "why": "Accounting records", "kept": "Kept for the retention period"},
]


class PrivacyService:
    def __init__(self, identity, mfa, sessions_guard, audit, store: DocStore, now: Callable[[], datetime] = _utc):
        self.identity, self.mfa, self.guard, self.audit, self.store, self.now = identity, mfa, sessions_guard, audit, store, now

    def _log(self, action, actor, entity_id, **kw):
        self.audit.record(AuditEvent(id=str(uuid.uuid4()), org_id=None, entity_type="User", entity_id=entity_id, action=action, actor=actor,
                                     timestamp=self.now(), **kw))

    # --- export
    def export(self, user_id: str) -> dict:
        u = self.identity.users.get(user_id)
        if u is None:
            raise NotFoundError("Account not found.")
        mem = self.identity.memberships.list_for_user(user_id)
        sessions = [{k: m.get(k) for k in ("created_at", "last_seen", "ip", "user_agent", "auth_method", "revoked")} for m in self.guard.list_for_user(user_id)]
        events = self.audit.list_for_actor(user_id)
        self._log("PRIVACY_EXPORT", user_id, user_id)
        return {"generated_at": self.now().isoformat(), "account": {"id": u.id, "email": u.email, "active": u.is_active, "created_at": u.created_at.isoformat()},
                "memberships": [{"organisation_id": m.org_id, "role": m.role.value, "status": m.status.value, "since": m.created_at.isoformat()} for m in mem],
                "multi_factor": (self.mfa.status(user_id) if self.mfa else {"enabled": False}), "sessions": sessions,
                "audit_events_about_you": [{"time": e.timestamp.isoformat(), "action": e.action, "record": f"{e.entity_type}:{e.entity_id}", "organisation_id": e.org_id} for e in events][-1000:],
                "data_inventory": DATA_INVENTORY,
                "note": "Accounting records you created belong to your organisation and are not included here."}

    # --- erasure
    def request_erasure(self, user_id: str) -> dict:
        u = self.identity.users.get(user_id)
        if u is None or not u.is_active:
            raise NotFoundError("Account not found.")
        for r in self.requests(user_id):
            if r["status"] == "PENDING":
                return r
        rid = str(uuid.uuid4())
        orgs = [m.org_id for m in self.identity.memberships.list_for_user(user_id) if m.status == MembershipStatus.ACTIVE]
        r = {"id": rid, "user_id": user_id, "kind": "ERASURE", "status": "PENDING", "organisations": orgs, "created_at": self.now().isoformat(),
             "decided_by": None, "decided_at": None, "note": None}
        self.store.put("privacy_request", rid, r)
        self._log("PRIVACY_ERASURE_REQUESTED", user_id, user_id)
        if not orgs:
            return self.decide(rid, approver_id=user_id, approve=True, note="No organisation membership; completed automatically.", _auto=True)
        return r

    def requests(self, user_id=None, org_id=None) -> List[dict]:
        out = [r for _, r in self.store.list("privacy_request")]
        if user_id:
            out = [r for r in out if r["user_id"] == user_id]
        if org_id:
            out = [r for r in out if org_id in r["organisations"]]
        return sorted(out, key=lambda r: r["created_at"], reverse=True)

    def decide(self, request_id: str, approver_id: str, approve: bool, note: str = "", _auto: bool = False) -> dict:
        r = self.store.get("privacy_request", request_id)
        if r is None:
            raise NotFoundError("Request not found.")
        if r["status"] != "PENDING":
            raise RetentionError("That request has already been decided.")
        if not approve:
            if not (note or "").strip():
                raise ValidationError("Say why the request is being declined.")
            r.update(status="DECLINED", decided_by=approver_id, decided_at=self.now().isoformat(), note=note.strip()[:500])
            self.store.put("privacy_request", request_id, r)
            self._log("PRIVACY_ERASURE_DECLINED", approver_id, r["user_id"], reason=r["note"])
            return r
        uid = r["user_id"]
        mems = [m for m in self.identity.memberships.list_for_user(uid) if m.status == MembershipStatus.ACTIVE]
        for m in mems:
            if m.role == Role.OWNER:
                owners = [x for x in self.identity.memberships.list_for_org(m.org_id) if x.role == Role.OWNER and x.status == MembershipStatus.ACTIVE]
                if len(owners) <= 1:
                    raise RetentionError("This person is the only owner of an organisation. Make someone else an owner first.")
        u = self.identity.users.get(uid)
        tag = hashlib.sha256(uid.encode()).hexdigest()[:12]
        self.identity.users.update(replace(u, email=f"erased-{tag}@erased.invalid", password_hash="!erased", is_active=False, mfa_enabled=False))
        for m in mems:
            self.identity.memberships.update(replace(m, status=MembershipStatus.REVOKED))
        self.guard.revoke_all(uid, "account erased")
        self.store.delete("mfa", uid)
        for k, _ in self.store.list("oidc_link"):
            if (self.store.get("oidc_link", k) or {}).get("user_id") == uid:
                self.store.delete("oidc_link", k)
        r.update(status="COMPLETED", decided_by=approver_id, decided_at=self.now().isoformat(), note=(note or "")[:500])
        self.store.put("privacy_request", request_id, r)
        self._log("PRIVACY_ERASURE_COMPLETED", approver_id, uid, reason="Identity removed; accounting records and audit events retained.")
        return r
