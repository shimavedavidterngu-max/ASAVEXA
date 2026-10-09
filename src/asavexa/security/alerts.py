"""Security alerts: rules over the audit trail. Each alert has a stable id, so re-checking never duplicates it, and a person can
acknowledge it with a note. New alerts can be pushed to a webhook (Slack, Teams, a pager); nothing is sent unless one is configured."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

from .errors import NotFoundError, ValidationError
from .store import DocStore

SEVERITY = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
FAIL_THRESHOLD, FAIL_WINDOW = 5, timedelta(minutes=15)
DOWNLOAD_THRESHOLD, DOWNLOAD_WINDOW = 20, timedelta(minutes=10)
PRIVILEGED = {"OWNER", "ADMINISTRATOR"}


def _utc():
    return datetime.now(timezone.utc)


def _aware(t):
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _aid(rule, who, bucket) -> str:
    return hashlib.sha256(f"{rule}|{who}|{bucket}".encode()).hexdigest()[:24]


def detect(events, now: datetime, lookback: timedelta = timedelta(days=7)) -> List[dict]:
    """events: AuditEvent objects (any order). Returns candidate alerts (no state)."""
    out: List[dict] = []
    evs = sorted((e for e in events if _aware(e.timestamp) >= now - lookback), key=lambda e: _aware(e.timestamp))
    by = defaultdict(list)
    for e in evs:
        by[(e.actor, e.action)].append(e)

    def add(rule, sev, who, ts, title, detail, bucket=None):
        out.append({"id": _aid(rule, who, bucket or _aware(ts).strftime("%Y%m%d%H")), "rule": rule, "severity": sev, "actor": who,
                    "time": _aware(ts).isoformat(), "title": title, "detail": detail})

    # repeated failed sign-ins (sliding window)
    for (who, action), lst in by.items():
        if action != "LOGIN_FAILED":
            continue
        times = [_aware(e.timestamp) for e in lst]
        for i in range(len(times)):
            j = i
            while j < len(times) and times[j] - times[i] <= FAIL_WINDOW:
                j += 1
            if j - i >= FAIL_THRESHOLD:
                succeeded = [e for e in by.get((who, "LOGIN_SUCCEEDED"), []) if times[i] <= _aware(e.timestamp) <= times[j - 1] + FAIL_WINDOW]
                if succeeded:
                    add("FAILED_THEN_SUCCEEDED", "HIGH", who, succeeded[0].timestamp, "Sign-in succeeded right after repeated failures",
                        f"{j - i} failed attempts, then a successful sign-in. Check whether this was the account owner.", bucket=times[i].strftime("%Y%m%d%H"))
                else:
                    add("REPEATED_LOGIN_FAILURES", "MEDIUM", who, times[i], "Repeated failed sign-ins",
                        f"{j - i} failed attempts within {int(FAIL_WINDOW.total_seconds() // 60)} minutes.", bucket=times[i].strftime("%Y%m%d%H"))
                break
    for e in evs:
        if e.action == "MFA_DISABLED":
            add("MFA_DISABLED", "HIGH", e.actor, e.timestamp, "Multi-factor authentication was turned off", "A person turned MFA off for their account.", bucket=e.id)
        elif e.action == "MFA_LOCKED":
            add("MFA_LOCKED", "MEDIUM", e.actor, e.timestamp, "MFA locked after wrong codes", "Several wrong codes were entered.")
        elif e.action == "MEMBERSHIP_ROLE_CHANGED" and ((e.new_value or {}).get("role") in PRIVILEGED):
            add("PRIVILEGE_GRANTED", "HIGH", e.actor, e.timestamp, f"Someone was given the {(e.new_value or {}).get('role')} role",
                f"Role changed on membership {e.entity_id}. Confirm this was intended.", bucket=e.id)
        elif e.action == "MEMBERSHIP_CREATED" and ((e.new_value or {}).get("role") in PRIVILEGED) and (e.new_value or {}).get("user_id") != e.actor:   # a person becoming their own organisation's first owner is normal
            add("PRIVILEGED_MEMBER_ADDED", "MEDIUM", e.actor, e.timestamp, f"A {(e.new_value or {}).get('role')} was added", "A new privileged member was added.", bucket=e.id)
        elif e.action in ("SECURITY_SETTINGS_CHANGED", "LEGAL_HOLD_RELEASED"):
            add(e.action, "MEDIUM", e.actor, e.timestamp, e.action.replace("_", " ").capitalize(), (e.reason or "A security control was changed."), bucket=e.id)
        elif e.action in ("EVIDENCE_DISPOSED", "KEY_ROTATION_RUN"):
            add(e.action, "LOW", e.actor, e.timestamp, e.action.replace("_", " ").capitalize(), (e.reason or ""), bucket=e.id)
        elif e.action == "AUDIT_CHAIN_FAILED":
            add("AUDIT_CHAIN_FAILED", "CRITICAL", e.actor, e.timestamp, "The audit log failed its integrity check", (e.reason or "Records may have been altered."), bucket=e.id)
    # download bursts
    for (who, action), lst in by.items():
        if action != "EVIDENCE_DOWNLOADED":
            continue
        times = [_aware(e.timestamp) for e in lst]
        for i in range(len(times)):
            j = i
            while j < len(times) and times[j] - times[i] <= DOWNLOAD_WINDOW:
                j += 1
            if j - i >= DOWNLOAD_THRESHOLD:
                add("DOWNLOAD_BURST", "HIGH", who, times[i], "Many evidence files downloaded quickly", f"{j - i} downloads in {int(DOWNLOAD_WINDOW.total_seconds() // 60)} minutes.",
                    bucket=times[i].strftime("%Y%m%d%H"))
                break
    return sorted(out, key=lambda a: (-SEVERITY[a["severity"]], a["time"]), reverse=False)


class AlertService:
    def __init__(self, store: DocStore, now: Callable[[], datetime] = _utc, notifier: Optional[Callable[[dict], None]] = None):
        self.store, self.now, self.notifier = store, now, notifier

    def refresh(self, org_id: str, events, extra: Optional[List[dict]] = None) -> dict:
        """Stores any alert not seen before and notifies about new ones. Returns counts."""
        new = 0
        for a in detect(events, self.now()) + list(extra or []):
            key = f"{org_id}:{a['id']}"
            if self.store.get("alert", key) is None:
                self.store.put("alert", key, {**a, "org_id": org_id, "status": "OPEN", "first_seen": self.now().isoformat(), "ack_by": None, "ack_note": None}, org_id=org_id)
                new += 1
                if self.notifier:
                    try:
                        self.notifier({**a, "org_id": org_id})
                    except Exception:
                        pass            # a broken webhook must never break the app
        return {"new": new}

    def list(self, org_id: str, status: Optional[str] = None) -> List[dict]:
        out = [a for _, a in self.store.list("alert", org_id=org_id) if not status or a["status"] == status]
        return sorted(out, key=lambda a: (a["status"] != "OPEN", -SEVERITY[a["severity"]], a["time"]), reverse=False)

    def acknowledge(self, org_id: str, alert_id: str, actor: str, note: str) -> dict:
        a = self.store.get("alert", f"{org_id}:{alert_id}")
        if a is None:
            raise NotFoundError("Alert not found.")
        if not (note or "").strip():
            raise ValidationError("Add a short note saying what you found.")
        a.update(status="ACKNOWLEDGED", ack_by=actor, ack_note=note.strip()[:500], ack_at=self.now().isoformat())
        self.store.put("alert", f"{org_id}:{alert_id}", a, org_id=org_id)
        return a
