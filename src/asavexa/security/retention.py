"""Retention policies, legal holds and controlled disposal of evidence files.

Disposal removes the file (and its decryption key) but never the evidence record, its fingerprint or any audit event, so the
trail still shows the document existed and what it was. Nothing is disposed early, and nothing under a legal hold is disposed."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

from .errors import LegalHoldError, NotFoundError, RetentionError, ValidationError
from .store import DocStore

FLOOR_DAYS = {"EVIDENCE": 2190}          # platform minimum: 6 years. Your own law may require more; set the policy accordingly.
DEFAULT_DAYS = {"EVIDENCE": 2555}        # 7 years
AUDIT_NOTE = "Audit events are never deleted by the platform."


def _utc():
    return datetime.now(timezone.utc)


class RetentionService:
    def __init__(self, store: DocStore, blobs, now: Callable[[], datetime] = _utc):
        self.store, self.blobs, self.now = store, blobs, now

    # --- policy
    def policy(self, org_id: str) -> dict:
        p = self.store.get("retention_policy", org_id) or {}
        days = {**DEFAULT_DAYS, **(p.get("days") or {})}
        return {"days": days, "floor_days": FLOOR_DAYS, "audit": AUDIT_NOTE, "updated_by": p.get("updated_by"), "updated_at": p.get("updated_at")}

    def set_policy(self, org_id: str, actor: str, evidence_days: int) -> dict:
        if not isinstance(evidence_days, int) or isinstance(evidence_days, bool):
            raise ValidationError("Retention must be a whole number of days.")
        if evidence_days < FLOOR_DAYS["EVIDENCE"]:
            raise ValidationError(f"Evidence must be kept for at least {FLOOR_DAYS['EVIDENCE']} days (6 years). Shorter periods are not allowed.")
        if evidence_days > 36500:
            raise ValidationError("Retention cannot exceed 100 years.")
        self.store.put("retention_policy", org_id, {"days": {"EVIDENCE": evidence_days}, "updated_by": actor, "updated_at": self.now().isoformat()}, org_id=org_id)
        return self.policy(org_id)

    # --- legal holds
    def place_hold(self, org_id: str, actor: str, reason: str, evidence_id: Optional[str] = None) -> dict:
        if not (reason or "").strip():
            raise ValidationError("A legal hold needs a reason.")
        hid = str(uuid.uuid4())
        h = {"id": hid, "org_id": org_id, "scope": f"EVIDENCE:{evidence_id}" if evidence_id else "ORG", "reason": reason.strip()[:500],
             "placed_by": actor, "placed_at": self.now().isoformat(), "released_at": None, "released_by": None}
        self.store.put("legal_hold", f"{org_id}:{hid}", h, org_id=org_id)
        return h

    def release_hold(self, org_id: str, hold_id: str, actor: str) -> dict:
        h = self.store.get("legal_hold", f"{org_id}:{hold_id}")
        if h is None:
            raise NotFoundError("Hold not found.")
        if h["released_at"]:
            raise RetentionError("That hold was already released.")
        h.update(released_at=self.now().isoformat(), released_by=actor)
        self.store.put("legal_hold", f"{org_id}:{hold_id}", h, org_id=org_id)
        return h

    def holds(self, org_id: str, active_only: bool = False) -> List[dict]:
        hs = [h for _, h in self.store.list("legal_hold", org_id=org_id)]
        return [h for h in hs if not (active_only and h["released_at"])]

    def is_held(self, org_id: str, evidence_id: str) -> Optional[dict]:
        for h in self.holds(org_id, active_only=True):
            if h["scope"] == "ORG" or h["scope"] == f"EVIDENCE:{evidence_id}":
                return h
        return None

    # --- disposal
    def _due_at(self, org_id: str, uploaded_at: datetime) -> datetime:
        return uploaded_at + timedelta(days=self.policy(org_id)["days"]["EVIDENCE"])

    def candidates(self, org_id: str, records) -> List[dict]:
        """Evidence whose retention period has ended. `records` are the vault's evidence records."""
        out = []
        for r in records:
            info = self.blobs.info(org_id, r.id) if self.blobs else None
            if not info or info["state"] != "STORED":
                continue
            up = r.uploaded_at if r.uploaded_at.tzinfo else r.uploaded_at.replace(tzinfo=timezone.utc)
            due = self._due_at(org_id, up)
            if due <= self.now():
                h = self.is_held(org_id, r.id)
                out.append({"evidence_id": r.id, "filename": r.original_filename, "uploaded_at": up.isoformat(), "due_at": due.isoformat(),
                            "on_hold": bool(h), "hold_reason": h["reason"] if h else None})
        return out

    def dispose(self, org_id: str, record, actor: str, reason: str) -> dict:
        if not (reason or "").strip():
            raise ValidationError("Disposal needs a reason.")
        h = self.is_held(org_id, record.id)
        if h:
            raise LegalHoldError(f"This evidence is under a legal hold ({h['reason']}). Release the hold first.")
        up = record.uploaded_at if record.uploaded_at.tzinfo else record.uploaded_at.replace(tzinfo=timezone.utc)
        due = self._due_at(org_id, up)
        if due > self.now():
            raise RetentionError(f"This evidence must be kept until {due.date().isoformat()}. It cannot be disposed of early.")
        return self.blobs.shred(org_id, record.id, reason.strip()[:300])
