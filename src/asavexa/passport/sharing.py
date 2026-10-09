"""
Permissioned sharing of the Financial Passport.

The organisation chooses WHO (recipient), WHAT (which Passport sections,
summary or line-level detail), WHEN (a date range, optionally finalised
periods only) and HOW (view only, or also download). The result is a
SNAPSHOT taken at that moment: the recipient sees exactly what was approved
and nothing the organisation records later. The snapshot carries a SHA-256
fingerprint so tampering is detectable.

Access needs two things the organisation hands over separately: a link
(high-entropy secret) and an access code, plus the recipient's email when one
was named. Five wrong tries (made by someone who holds the link) lock the
share. The organisation can revoke at any time; revocation cuts off even a
recipient who is already verified. Every create / verify / view / download /
refusal / revoke is written to the shared audit trail.

Pure domain code: storage is injected (`store`), so it runs the same over
SQLite in tests and SQLAlchemy in production.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
import secrets
import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..audit.models import AuditEvent
from .builder import PassportInputs, build_passport, fingerprint, _aware
from .errors import (
    ShareAccessDeniedError,
    ShareNotFoundError,
    ShareStateError,
    ShareValidationError,
)

KIND = "vera-passport-share/1"
SCOPES = ("IDENTITY", "FINANCIAL_HISTORY", "EVIDENCE_QUALITY", "GOVERNANCE", "REPORTING", "AUDIT_TRAIL")
RECIPIENT_TYPES = ("BANK", "AUDITOR", "INVESTOR", "REGULATOR", "DONOR", "OTHER")
MAX_RANGE_DAYS = 20 * 366
MAX_EXPIRY_DAYS = 365
MAX_ACTIVE_SHARES = 100
MAX_FAILED_ATTEMPTS = 5
SESSION_MINUTES = 60
PBKDF2_ITERATIONS = 120_000
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O/1/I to avoid misreading
CODE_LENGTH = 10
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DENIED = ("This access link is not valid. It may have expired, been revoked or been locked. "
          "Ask the organisation to issue a new one.")
BAD_CREDENTIALS = "The access code or email is not correct."
SESSION_EXPIRED = "Your verified session has ended. Please verify again."


# ------------------------------------------------------------------ model
@dataclass
class Share:
    id: str
    org_id: str
    recipient_name: str
    recipient_type: str
    recipient_email: Optional[str]
    purpose: Optional[str]
    scopes: List[str]
    include_detail: bool
    allow_download: bool
    closed_periods_only: bool
    date_from: date
    date_to: date
    status: str                      # ACTIVE | REVOKED | LOCKED (EXPIRED is derived)
    created_at: datetime
    created_by: str
    expires_at: datetime
    secret_hash: str
    code_salt: str
    code_hash: str
    snapshot: dict
    fingerprint: str
    failed_attempts: int = 0
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    revoked_by: Optional[str] = None
    revoke_reason: Optional[str] = None


@dataclass
class ShareSession:
    id: str
    share_id: str
    token_hash: str
    created_at: datetime
    expires_at: datetime


class InMemoryShareStore:
    """Reference store (tests). The SQLAlchemy store in api/ has the same methods."""
    def __init__(self):
        self.shares: Dict[str, Share] = {}
        self.sessions: Dict[str, ShareSession] = {}

    @staticmethod
    def _roundtrip(s: Share) -> Share:
        # a database stores JSON, not Python objects: behave the same
        return replace(s, scopes=list(s.scopes), snapshot=json.loads(json.dumps(s.snapshot)))

    def add_share(self, s: Share) -> None:
        self.shares[s.id] = self._roundtrip(s)

    def get_share(self, share_id: str) -> Optional[Share]:
        s = self.shares.get(share_id)
        return self._roundtrip(s) if s else None

    def save_share(self, s: Share) -> None:
        self.shares[s.id] = self._roundtrip(s)

    def list_shares(self, org_id: str) -> List[Share]:
        return sorted((self._roundtrip(s) for s in self.shares.values() if s.org_id == org_id),
                      key=lambda s: s.created_at, reverse=True)

    def add_session(self, s: ShareSession) -> None:
        self.sessions[s.token_hash] = s

    def get_session(self, token_hash: str) -> Optional[ShareSession]:
        return self.sessions.get(token_hash)

    def delete_sessions(self, share_id: str) -> None:
        self.sessions = {k: v for k, v in self.sessions.items() if v.share_id != share_id}


# ------------------------------------------------------------- credentials
def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalise_code(code: str) -> str:
    return re.sub(r"[\s\-]", "", (code or "")).upper()


def hash_code(code: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", normalise_code(code).encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS).hex()


def new_access_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
    return f"{raw[:5]}-{raw[5:]}"


def _eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


# -------------------------------------------------------------- validation
def _as_date(v: Any, label: str) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except (TypeError, ValueError):
        raise ShareValidationError(f"{label} must be a date in the form YYYY-MM-DD.")


def validate_request(req: dict) -> dict:
    """Returns a cleaned copy or raises ShareValidationError with a plain message."""
    name = (req.get("recipient_name") or "").strip()
    if not name:
        raise ShareValidationError("Say who you are sharing with (recipient name).")
    if len(name) > 200:
        raise ShareValidationError("Recipient name is too long (200 characters at most).")
    rtype = str(req.get("recipient_type") or "OTHER").upper()
    if rtype not in RECIPIENT_TYPES:
        raise ShareValidationError("Recipient type must be one of: " + ", ".join(RECIPIENT_TYPES) + ".")
    email = (req.get("recipient_email") or "").strip().lower() or None
    if email and not _EMAIL_RE.match(email):
        raise ShareValidationError("Recipient email is not a valid email address.")
    purpose = (req.get("purpose") or "").strip() or None
    if purpose and len(purpose) > 500:
        raise ShareValidationError("Purpose is too long (500 characters at most).")
    scopes = []
    for s in req.get("scopes") or []:
        s = str(s).upper()
        if s not in SCOPES:
            raise ShareValidationError(f"Unknown information section {s!r}. Choose from: " + ", ".join(SCOPES) + ".")
        if s not in scopes:
            scopes.append(s)
    if not scopes:
        raise ShareValidationError("Choose at least one section of information to share.")
    d_from = _as_date(req.get("date_from"), "Start date")
    d_to = _as_date(req.get("date_to"), "End date")
    if d_from > d_to:
        raise ShareValidationError("The start date must not be after the end date.")
    if (d_to - d_from).days > MAX_RANGE_DAYS:
        raise ShareValidationError("The date range is too long (20 years at most).")
    days = req.get("expires_in_days", 30)
    if isinstance(days, bool) or not isinstance(days, int) or not (1 <= days <= MAX_EXPIRY_DAYS):
        raise ShareValidationError(f"Access must last between 1 and {MAX_EXPIRY_DAYS} days.")
    return {
        "recipient_name": name, "recipient_type": rtype, "recipient_email": email, "purpose": purpose,
        "scopes": scopes, "date_from": d_from, "date_to": d_to, "expires_in_days": days,
        "include_detail": bool(req.get("include_detail", False)),
        "allow_download": bool(req.get("allow_download", False)),
        "closed_periods_only": bool(req.get("closed_periods_only", False)),
    }


# --------------------------------------------------- filtering and redaction
def _val(x):
    return getattr(x, "value", x)


def _in_range(d: Optional[date], lo: date, hi: date) -> bool:
    return d is not None and lo <= d <= hi


def filter_inputs(inp: PassportInputs, r: dict) -> Tuple[PassportInputs, list, int]:
    """Only what falls inside the approved window. Returns (inputs, included periods, excluded count)."""
    lo, hi = r["date_from"], r["date_to"]
    included, excluded = [], 0
    for p in inp.periods:
        ok = lo <= p.start_date and p.end_date <= hi
        if ok and r["closed_periods_only"] and _val(p.status) not in ("LOCKED", "CLOSED"):
            ok = False
        if ok:
            included.append(p)
        else:
            excluded += 1
    pids = {p.id for p in included}
    journals = [j for j in inp.journals if j.period_id in pids and _val(j.status) != "DRAFT"]
    jids = {j.id for j in journals}
    refs = {j.evidence_ref for j in journals if j.evidence_ref}
    trefs = {j.transaction_ref for j in journals if j.transaction_ref}
    evidence = [e for e in inp.evidence
                if e.linked_journal_id in jids or e.id in refs or (e.linked_transaction_ref and e.linked_transaction_ref in trefs)]
    recs = [x for x in inp.reconciliations if lo <= x.period_start and x.period_end <= hi]
    rids = {x.id for x in recs}
    txs = [t for t in inp.bank_transactions if t.reconciliation_id in rids]

    def in_window(dt: Optional[datetime]) -> bool:
        return dt is not None and lo <= _aware(dt).date() <= hi

    executions = [x for x in inp.executions if (x.period_id in pids) or (x.period_id is None and in_window(x.executed_at))]
    findings = [f for f in inp.findings if in_window(f.created_at)]
    events = [e for e in inp.audit_events if in_window(e.timestamp)]
    out = replace(
        inp, periods=included, journals=journals, evidence=evidence, reconciliations=recs, bank_transactions=txs,
        executions=executions, findings=findings, close_processes=[c for c in inp.close_processes if c.period_id in pids],
        audit_events=events, audit_total=len(events),
    )
    return out, included, excluded


def _mark(section: dict, note: str) -> None:
    section["detail_withheld"] = True
    section["detail_note"] = note


def redact_detail(sections: dict) -> dict:
    """Summary level: counts and totals stay; names, emails and line items go."""
    s = copy.deepcopy(sections)
    note = "Line-level detail was not included in this share."
    if "identity" in s:
        s["identity"]["ownership"]["updated_by"] = None
        s["identity"]["ownership"]["updated_at"] = None
    if "evidence_quality" in s:
        e = s["evidence_quality"]
        e["missing_evidence"]["items"] = []
        e["bank_reconciliation"]["unreconciled_items"] = []
        e["exceptions"]["items"] = []
        _mark(e, note)
    if "governance" in s:
        g = s["governance"]
        g["approvals"]["recent"] = []
        for c in g["segregation_of_duties"]["checks"]:
            c["examples"] = []
        sod = g["segregation_of_duties"]
        sod["role_conflict_count"] = len(sod["role_conflicts"])
        sod["role_conflicts"] = []
        g["control_exceptions"]["items"] = []
        _mark(g, note)
    if "audit_trail" in s:
        a = s["audit_trail"]
        a["people_count"] = len(a["by_person"])
        a["by_person"] = []
        a["recent_events"] = []
        a["journal_provenance"] = []
        a["period_locks"] = []
        _mark(a, note)
    return s


def build_share_content(inp: PassportInputs, r: dict, now: datetime) -> Tuple[dict, list, int]:
    filtered, included, excluded = filter_inputs(inp, r)
    full = build_passport(filtered, None, now)
    sections = {k.lower(): full[k.lower()] for k in r["scopes"]}
    if not r["include_detail"]:
        sections = redact_detail(sections)
    # the Passport's own attention messages describe the whole organisation, not the
    # recipient's window; keep them (they are about the shared data) as built.
    return sections, included, excluded


def share_fingerprint(meta: dict, sections: dict) -> str:
    return fingerprint({"share": meta, "sections": sections})


# ----------------------------------------------------------------- service
def effective_status(s: Share, now: datetime) -> str:
    if s.status in ("REVOKED", "LOCKED"):
        return s.status
    return "EXPIRED" if _aware(now) >= _aware(s.expires_at) else "ACTIVE"


def public_share(s: Share, now: datetime, labels: Optional[Dict[str, str]] = None) -> dict:
    """What the ORGANISATION sees about a share: never secrets, never the snapshot body."""
    labels = labels or {}
    meta = (s.snapshot or {}).get("share", {})
    return {
        "id": s.id, "recipient_name": s.recipient_name, "recipient_type": s.recipient_type,
        "recipient_email": s.recipient_email, "purpose": s.purpose, "scopes": list(s.scopes),
        "include_detail": s.include_detail, "allow_download": s.allow_download,
        "closed_periods_only": s.closed_periods_only,
        "date_from": s.date_from.isoformat(), "date_to": s.date_to.isoformat(),
        "status": effective_status(s, now), "created_at": _aware(s.created_at).isoformat(),
        "created_by": labels.get(s.created_by, s.created_by), "expires_at": _aware(s.expires_at).isoformat(),
        "fingerprint": s.fingerprint, "failed_attempts": s.failed_attempts, "access_count": s.access_count,
        "last_accessed_at": _aware(s.last_accessed_at).isoformat() if s.last_accessed_at else None,
        "revoked_at": _aware(s.revoked_at).isoformat() if s.revoked_at else None,
        "revoked_by": labels.get(s.revoked_by, s.revoked_by) if s.revoked_by else None,
        "revoke_reason": s.revoke_reason,
        "periods_included": meta.get("periods_included", []), "periods_excluded": meta.get("periods_excluded", 0),
    }


class ShareService:
    def __init__(self, store, audit):
        self.store = store
        self.audit = audit

    # -- audit ----------------------------------------------------------
    def _log(self, s: Share, action: str, actor: str, now: datetime, new_value=None, reason=None):
        self.audit.record(AuditEvent(
            id=str(uuid.uuid4()), org_id=s.org_id, entity_type="PassportShare", entity_id=s.id,
            action=action, actor=actor, timestamp=now, new_value=new_value, reason=reason,
        ))

    @staticmethod
    def _recipient_actor(s: Share) -> str:
        return "recipient:" + (s.recipient_email or s.recipient_name)

    # -- organisation side ---------------------------------------------
    def create_share(self, inp: PassportInputs, request: dict, actor: str, now: datetime) -> dict:
        r = validate_request(request)
        active = [x for x in self.store.list_shares(inp.org_id) if effective_status(x, now) == "ACTIVE"]
        if len(active) >= MAX_ACTIVE_SHARES:
            raise ShareStateError(f"There are already {MAX_ACTIVE_SHARES} active shares. Revoke some before creating more.")
        sections, included, excluded = build_share_content(inp, r, now)
        share_id = str(uuid.uuid4())
        expires_at = now + timedelta(days=r["expires_in_days"])
        legal = (inp.profile or {}).get("legal_name") or inp.org_name
        meta = {
            "organisation": legal, "recipient_name": r["recipient_name"], "recipient_type": r["recipient_type"],
            "purpose": r["purpose"], "scopes": r["scopes"], "include_detail": r["include_detail"],
            "allow_download": r["allow_download"], "closed_periods_only": r["closed_periods_only"],
            "date_from": r["date_from"].isoformat(), "date_to": r["date_to"].isoformat(),
            "expires_at": expires_at.isoformat(), "snapshot_taken_at": now.isoformat(),
            "periods_included": [{"name": p.name, "start_date": p.start_date.isoformat(),
                                   "end_date": p.end_date.isoformat(), "status": _val(p.status)} for p in included],
            "periods_excluded": excluded,
        }
        fp = share_fingerprint(meta, sections)
        snapshot = {"kind": KIND, "share": meta, "sections": sections, "fingerprint": fp}
        secret = secrets.token_urlsafe(32)
        code = new_access_code()
        salt = secrets.token_hex(16)
        share = Share(
            id=share_id, org_id=inp.org_id, recipient_name=r["recipient_name"], recipient_type=r["recipient_type"],
            recipient_email=r["recipient_email"], purpose=r["purpose"], scopes=r["scopes"],
            include_detail=r["include_detail"], allow_download=r["allow_download"],
            closed_periods_only=r["closed_periods_only"], date_from=r["date_from"], date_to=r["date_to"],
            status="ACTIVE", created_at=now, created_by=actor, expires_at=expires_at,
            secret_hash=_sha(secret), code_salt=salt, code_hash=hash_code(code, salt),
            snapshot=snapshot, fingerprint=fp,
        )
        self.store.add_share(share)
        self._log(share, "PASSPORT_SHARE_CREATED", actor, now, new_value={
            "recipient": r["recipient_name"], "recipient_type": r["recipient_type"],
            "recipient_email": r["recipient_email"], "scopes": r["scopes"], "include_detail": r["include_detail"],
            "allow_download": r["allow_download"], "closed_periods_only": r["closed_periods_only"],
            "date_from": r["date_from"].isoformat(), "date_to": r["date_to"].isoformat(),
            "expires_at": expires_at.isoformat(), "fingerprint": fp, "purpose": r["purpose"],
        })
        warnings = []
        if not r["recipient_email"]:
            warnings.append("No recipient email was given, so anyone holding both the link and the code can open this.")
        if r["include_detail"]:
            warnings.append("Line-level detail is included: the recipient will see individual transactions and the email addresses of your team.")
        if "FINANCIAL_HISTORY" in r["scopes"] and not included:
            warnings.append("No accounting period falls entirely inside the chosen dates"
                            + (" (and is closed)" if r["closed_periods_only"] else "")
                            + ", so the financial history is empty.")
        return {"share": public_share(share, now), "access_token": f"{share_id}.{secret}",
                "access_code": code, "warnings": warnings,
                "note": "The link and the access code are shown once and cannot be recovered. Send them by different routes."}

    def _org_share(self, org_id: str, share_id: str) -> Share:
        s = self.store.get_share(share_id) if _is_uuid(share_id) else None
        if s is None or s.org_id != org_id:
            raise ShareNotFoundError("No such share in this organisation.")
        return s

    def list_shares(self, org_id: str, now: datetime, labels=None) -> List[dict]:
        return [public_share(s, now, labels) for s in self.store.list_shares(org_id)]

    def get_share(self, org_id: str, share_id: str, now: datetime, labels=None) -> dict:
        return public_share(self._org_share(org_id, share_id), now, labels)

    def revoke_share(self, org_id: str, share_id: str, actor: str, reason: Optional[str], now: datetime) -> dict:
        s = self._org_share(org_id, share_id)
        reason = (reason or "").strip() or None
        if reason and len(reason) > 500:
            raise ShareValidationError("The reason is too long (500 characters at most).")
        if s.status == "REVOKED":
            raise ShareStateError("This share has already been revoked.")
        s.status, s.revoked_at, s.revoked_by, s.revoke_reason = "REVOKED", now, actor, reason
        self.store.save_share(s)
        self.store.delete_sessions(s.id)
        self._log(s, "PASSPORT_SHARE_REVOKED", actor, now, reason=reason)
        return public_share(s, now)

    def access_log(self, org_id: str, share_id: str, labels=None) -> List[dict]:
        s = self._org_share(org_id, share_id)
        labels = labels or {}
        events = self.audit.list_for_entity("PassportShare", s.id, org_id=org_id)
        return [{
            "when": _aware(e.timestamp).isoformat(), "action": e.action, "who": labels.get(e.actor, e.actor),
            "reason": e.reason, "detail": e.new_value,
        } for e in sorted(events, key=lambda e: _aware(e.timestamp), reverse=True)]

    # -- recipient side -------------------------------------------------
    def verify(self, access_token: str, access_code: str, email: Optional[str], now: datetime) -> dict:
        share_id, _, secret = (access_token or "").strip().partition(".")
        s = self.store.get_share(share_id) if (secret and _is_uuid(share_id)) else None
        # Wrong link: nothing is recorded and nothing is revealed, so strangers cannot lock a share.
        if s is None or not _eq(_sha(secret), s.secret_hash):
            raise ShareAccessDeniedError(DENIED)
        actor = self._recipient_actor(s)
        if effective_status(s, now) != "ACTIVE":
            self._log(s, "PASSPORT_SHARE_DENIED", actor, now, reason=f"access attempted while {effective_status(s, now).lower()}")
            raise ShareAccessDeniedError(DENIED)
        code_ok = _eq(hash_code(access_code or "", s.code_salt), s.code_hash)
        email_ok = True
        if s.recipient_email:
            email_ok = _eq((email or "").strip().lower(), s.recipient_email)
        if not (code_ok and email_ok):
            s.failed_attempts += 1
            locked = s.failed_attempts >= MAX_FAILED_ATTEMPTS
            if locked:
                s.status = "LOCKED"
            self.store.save_share(s)
            self._log(s, "PASSPORT_SHARE_DENIED", "recipient:unverified", now, reason="wrong access code or email")
            if locked:
                self.store.delete_sessions(s.id)
                self._log(s, "PASSPORT_SHARE_LOCKED", "system", now,
                          reason=f"{MAX_FAILED_ATTEMPTS} wrong attempts; the organisation must issue a new share")
                raise ShareAccessDeniedError(BAD_CREDENTIALS + " Too many wrong attempts: this link is now locked.")
            left = MAX_FAILED_ATTEMPTS - s.failed_attempts
            raise ShareAccessDeniedError(f"{BAD_CREDENTIALS} {left} attempt(s) left before the link locks.")
        s.failed_attempts = 0
        s.access_count += 1
        s.last_accessed_at = now
        self.store.save_share(s)
        token = secrets.token_urlsafe(32)
        expires = min(now + timedelta(minutes=SESSION_MINUTES), _aware(s.expires_at))
        self.store.add_session(ShareSession(str(uuid.uuid4()), s.id, _sha(token), now, expires))
        self._log(s, "PASSPORT_SHARE_VERIFIED", actor, now)
        return {"session_token": token, "session_expires_at": expires.isoformat(), "share": self._recipient_meta(s, now)}

    @staticmethod
    def _recipient_meta(s: Share, now: datetime) -> dict:
        m = s.snapshot.get("share", {})
        return {k: m.get(k) for k in (
            "organisation", "recipient_name", "recipient_type", "purpose", "scopes", "include_detail",
            "allow_download", "closed_periods_only", "date_from", "date_to", "expires_at", "snapshot_taken_at",
            "periods_included", "periods_excluded")}

    def _session_share(self, session_token: str, now: datetime) -> Share:
        sess = self.store.get_session(_sha(session_token or "")) if session_token else None
        if sess is None or _aware(now) >= _aware(sess.expires_at):
            raise ShareAccessDeniedError(SESSION_EXPIRED)
        s = self.store.get_share(sess.share_id)
        if s is None or effective_status(s, now) != "ACTIVE":
            raise ShareAccessDeniedError(DENIED)     # revoked / expired / locked mid-session: cut off at once
        return s

    @staticmethod
    def _integrity(s: Share) -> dict:
        snap = s.snapshot
        recomputed = share_fingerprint(snap.get("share", {}), snap.get("sections", {}))
        return {"verified": _eq(recomputed, s.fingerprint) and _eq(snap.get("fingerprint", ""), s.fingerprint),
                "fingerprint": s.fingerprint, "recomputed": recomputed}

    def view(self, session_token: str, now: datetime) -> dict:
        s = self._session_share(session_token, now)
        self._log(s, "PASSPORT_SHARE_VIEWED", self._recipient_actor(s), now)
        return {"share": self._recipient_meta(s, now), "sections": s.snapshot["sections"], "integrity": self._integrity(s)}

    def download(self, session_token: str, now: datetime) -> dict:
        s = self._session_share(session_token, now)
        if not s.allow_download:
            raise ShareAccessDeniedError("The organisation did not allow this share to be downloaded.")
        self._log(s, "PASSPORT_SHARE_DOWNLOADED", self._recipient_actor(s), now)
        return {**s.snapshot, "integrity": self._integrity(s)}


def _is_uuid(v: str) -> bool:
    try:
        uuid.UUID(str(v))
        return True
    except (ValueError, AttributeError, TypeError):
        return False
