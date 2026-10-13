"""Verified Standards Registry (Stage 6).

The catalog (catalog.py) is a set of suggested defaults. This registry is where an organisation records WHERE a standard or rule comes from and
that a person checked it: an official source link, the version, when it takes effect, and when it must be reviewed again.

Lifecycle of a source: DRAFT -> UNDER_REVIEW -> APPROVED -> (SUPERSEDED by a newer approved version | WITHDRAWN). A reviewer can send it back to DRAFT.
A source is never edited after it is submitted; a new version is a new source. The approver cannot be the person who added or submitted it.

Honest by design: a framework is VERIFIED only when an APPROVED source exists and its review date has not passed. Otherwise it is UNVERIFIED or
REVIEW_OVERDUE. The registry stores links and a person's approval; it does not fetch the link, read the standard, or give legal advice.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Callable, List, Optional
from urllib.parse import urlparse

from ..security.errors import SecurityError
from . import catalog as C

KIND = "std_source"
STATUSES = ("DRAFT", "UNDER_REVIEW", "APPROVED", "SUPERSEDED", "WITHDRAWN")
MAX_TEXT = 2000


class RegistryError(SecurityError): status = 400
class RegistryNotFoundError(RegistryError): status = 404
class RegistryStateError(RegistryError): status = 409
class RegistryForbiddenError(RegistryError): status = 403


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _text(v, label, required=True, limit=MAX_TEXT) -> str:
    s = (v or "").strip() if isinstance(v, str) or v is None else str(v).strip()
    if required and not s:
        raise RegistryError(f"{label} is required.")
    if len(s) > limit:
        raise RegistryError(f"{label} must be at most {limit} characters.")
    return s


def _date(v, label, required=True) -> Optional[str]:
    if not v:
        if required:
            raise RegistryError(f"{label} is required.")
        return None
    try:
        return date.fromisoformat(str(v)).isoformat()
    except ValueError:
        raise RegistryError(f"{label} must be a date like 2026-12-31.")


def _url(v) -> str:
    s = _text(v, "Source link", limit=500)
    u = urlparse(s)
    if u.scheme != "https" or not u.netloc or " " in s or "." not in u.netloc:
        raise RegistryError("The source link must be a full https:// address.")
    return s


class StandardsRegistry:
    def __init__(self, store, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _now):
        self.store, self.log, self.now = store, log, now

    def today(self) -> date: return self.now().date()

    def _put(self, org, s): self.store.put(KIND, f"{org}:{s['id']}", s, org_id=org)

    def _get(self, org, sid, for_update=False) -> dict:
        s = self.store.get(KIND, f"{org}:{sid}", for_update=for_update)
        if s is None or s.get("org") != org:
            raise RegistryNotFoundError("Source not found.")
        return s

    def _stamp(self, s, actor, event, note=""):
        s["history"].append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})
        s["updated_at"] = self.now().isoformat()

    # ---------------------------------------------------------------- write
    def add_source(self, org, actor, framework, title, url, authority, version, effective_from, review_by,
                   summary="", jurisdiction: Optional[str] = None) -> dict:
        if framework not in C.FRAMEWORKS:
            raise RegistryError("Choose a framework from the catalog.")
        if jurisdiction and jurisdiction not in C.JURISDICTIONS:
            raise RegistryError("Choose a jurisdiction from the catalog, or leave it blank for an international standard.")
        eff, rev = _date(effective_from, "Effective date"), _date(review_by, "Review-by date")
        if rev <= eff:
            raise RegistryError("The review-by date must be after the effective date.")
        sid = str(uuid.uuid4())
        s = {"id": sid, "org": org, "framework": framework, "jurisdiction": jurisdiction or None, "title": _text(title, "Title", limit=300),
             "url": _url(url), "authority": _text(authority, "Issuing authority", limit=200), "version": _text(version, "Version", limit=60),
             "effective_from": eff, "review_by": rev, "summary": _text(summary, "Summary", required=False),
             "status": "DRAFT", "created_by": actor, "submitted_by": None, "approved_by": None, "superseded_by": None, "history": [],
             "created_at": self.now().isoformat(), "updated_at": self.now().isoformat()}
        self._stamp(s, actor, "ADDED")
        self._put(org, s)
        self.log("STANDARDS_SOURCE_ADDED", actor, sid, org, f"{framework} {s['version']}")
        return s

    def submit(self, org, sid, actor) -> dict:
        s = self._get(org, sid, for_update=True)
        if s["status"] != "DRAFT":
            raise RegistryStateError(f"Only a draft can be submitted (this one is {s['status']}).")
        s.update(status="UNDER_REVIEW", submitted_by=actor)
        self._stamp(s, actor, "SUBMITTED")
        self._put(org, s)
        self.log("STANDARDS_SOURCE_SUBMITTED", actor, sid, org, s["framework"])
        return s

    def approve(self, org, sid, actor, note: str = "") -> dict:
        s = self._get(org, sid, for_update=True)
        if s["status"] != "UNDER_REVIEW":
            raise RegistryStateError(f"Only a source under review can be approved (this one is {s['status']}).")
        if actor in (s["created_by"], s["submitted_by"]):
            raise RegistryForbiddenError("The person who added or submitted a source cannot approve it. Someone else must.")
        if s["review_by"] <= self.today().isoformat():
            raise RegistryStateError("The review-by date has already passed, so this source cannot be approved. Add a current version.")
        for _, other in self.store.list(KIND, org_id=org):
            if other["id"] != sid and other["status"] == "APPROVED" and other["framework"] == s["framework"] and other["jurisdiction"] == s["jurisdiction"]:
                other = self._get(org, other["id"], for_update=True)
                other.update(status="SUPERSEDED", superseded_by=sid)
                self._stamp(other, actor, "SUPERSEDED", f"by version {s['version']}")
                self._put(org, other)
                self.log("STANDARDS_SOURCE_SUPERSEDED", actor, other["id"], org, f"by {sid}")
        s.update(status="APPROVED", approved_by=actor)
        self._stamp(s, actor, "APPROVED", _text(note, "Note", required=False))
        self._put(org, s)
        self.log("STANDARDS_SOURCE_APPROVED", actor, sid, org, s["framework"])
        return s

    def send_back(self, org, sid, actor, reason) -> dict:
        s = self._get(org, sid, for_update=True)
        if s["status"] != "UNDER_REVIEW":
            raise RegistryStateError(f"Only a source under review can be sent back (this one is {s['status']}).")
        reason = _text(reason, "Reason")
        s.update(status="DRAFT", submitted_by=None)
        self._stamp(s, actor, "SENT_BACK", reason)
        self._put(org, s)
        self.log("STANDARDS_SOURCE_SENT_BACK", actor, sid, org, reason[:200])
        return s

    def withdraw(self, org, sid, actor, reason) -> dict:
        s = self._get(org, sid, for_update=True)
        if s["status"] not in ("APPROVED", "UNDER_REVIEW", "DRAFT"):
            raise RegistryStateError(f"This source is already {s['status']}.")
        reason = _text(reason, "Reason")
        s["status"] = "WITHDRAWN"
        self._stamp(s, actor, "WITHDRAWN", reason)
        self._put(org, s)
        self.log("STANDARDS_SOURCE_WITHDRAWN", actor, sid, org, reason[:200])
        return s

    # ---------------------------------------------------------------- read
    def get_source(self, org, sid) -> dict:
        return self._get(org, sid)

    def list_sources(self, org, status: Optional[str] = None, framework: Optional[str] = None) -> List[dict]:
        out = [s for _, s in self.store.list(KIND, org_id=org) if s.get("org") == org and (not status or s["status"] == status) and (not framework or s["framework"] == framework)]
        return sorted(out, key=lambda s: (s["framework"], s["created_at"]))

    def verification(self, org, framework, jurisdiction: Optional[str] = None) -> dict:
        """VERIFIED / REVIEW_OVERDUE / NOT_YET_EFFECTIVE / UNVERIFIED for one framework (and jurisdiction), judged on today's date."""
        today = self.today().isoformat()
        approved = [s for s in self.list_sources(org, "APPROVED", framework) if s["jurisdiction"] in (None, jurisdiction)]
        if not approved:
            return {"framework": framework, "jurisdiction": jurisdiction, "state": "UNVERIFIED", "source": None,
                    "meaning": "No approved source is recorded for this framework. The catalog default is a suggestion only."}
        s = sorted(approved, key=lambda x: (x["jurisdiction"] is not None, x["effective_from"]))[-1]
        if s["review_by"] <= today:
            state, meaning = "REVIEW_OVERDUE", f"The approved source was due for review on {s['review_by']}. Have it re-checked."
        elif s["effective_from"] > today:
            state, meaning = "NOT_YET_EFFECTIVE", f"The approved version takes effect on {s['effective_from']}."
        else:
            state, meaning = "VERIFIED", f"A person approved this source (version {s['version']}); review is due by {s['review_by']}."
        return {"framework": framework, "jurisdiction": jurisdiction, "state": state, "meaning": meaning,
                "source": {k: s[k] for k in ("id", "title", "url", "authority", "version", "effective_from", "review_by", "approved_by")}}

    def coverage(self, org, jurisdiction: Optional[str] = None) -> dict:
        rows = [{**self.verification(org, code, jurisdiction), "name": f["name"]} for code, f in C.FRAMEWORKS.items()]
        counts = {}
        for r in rows:
            counts[r["state"]] = counts.get(r["state"], 0) + 1
        return {"frameworks": rows, "counts": counts, "as_of": self.today().isoformat(),
                "note": "VERIFIED means a person approved an official source for that framework. It does not mean the organisation is compliant, and this is not legal advice."}
