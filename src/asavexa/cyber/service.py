"""Cybersecurity service (defensive record-keeping).

Records (shared document store, per organisation): cy_asset, cy_vuln, cy_incident, cy_review, cy_report, cy_setting.

Principles enforced here: a fix is verified by someone other than who marked it fixed; accepting the risk of an open vulnerability needs a written reason, an
expiry date and a second person; an incident is closed by someone other than who resolved it, with lessons learned; an access review is approved by someone
other than who submitted it, and only after every removal is confirmed; reports are frozen, fingerprinted and approved by a second person; every step is
audited. Fix deadlines come from the organisation's own policy at the time the vulnerability is recorded. Nothing here scans or tests any system."""
import csv
import hashlib
import io
import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Callable, List, Optional

from .errors import CyberError, CyberForbiddenError, CyberNotFoundError, CyberStateError

SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
ASSET_TYPES = ["SERVER", "ENDPOINT", "APPLICATION", "DATABASE", "NETWORK", "CLOUD", "OTHER"]
DATA_CLASSES = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
CRITICALITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
INCIDENT_CATEGORIES = ["PHISHING", "MALWARE", "UNAUTHORISED_ACCESS", "DATA_EXPOSURE", "DENIAL_OF_SERVICE", "LOSS_OR_THEFT", "OTHER"]
OPEN_VULN = ("OPEN", "IN_PROGRESS", "ACCEPTANCE_PENDING")
DEFAULT_SLA = {"CRITICAL": 7, "HIGH": 30, "MEDIUM": 90, "LOW": 180}
DEFAULT_ACCEPT_MAX = 90
CONFIDENTIAL = "CONFIDENTIAL - ASAVEXA cybersecurity posture report. For the organisation named and people it has authorised."
LIMITATIONS = [
    "ASAVEXA does not scan, test or connect to any system. Everything here is what people recorded, so the picture is only as complete as the records.",
    "Fix deadlines come from your own policy at the time each vulnerability was recorded. The defaults are placeholders, not a standard or a legal requirement.",
    "Verification records that a second person confirmed the fix. It is not a penetration test or a technical assurance.",
    "Whether an incident must be reported to a regulator or to affected people is a legal question. ASAVEXA records the decision your organisation made; it does not decide it.",
    "Access review entries are typed in by people. ASAVEXA does not read accounts from other systems.",
]


def _utc(): return datetime.now(timezone.utc)
def _sha(o) -> str: return hashlib.sha256(json.dumps(o, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v))).strip()
    if required and len(v) < lo:
        raise CyberError(f"{name} is required (at least {lo} characters).")
    if len(v) > hi:
        raise CyberError(f"{name} is too long (limit {hi} characters).")
    return v


def _date(v, name) -> date:
    try:
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise CyberError(f"{name} must be a real date written YYYY-MM-DD.")


def _enum(v, allowed, name) -> str:
    v = _txt(v, name, 1, 40).upper()
    if v not in allowed:
        raise CyberError(f"{name} must be one of {', '.join(allowed)}.")
    return v


def _int(v, name, lo, hi) -> int:
    if isinstance(v, bool) or not str(v).strip().lstrip("-").isdigit():
        raise CyberError(f"{name} must be a whole number from {lo} to {hi}.")
    n = int(str(v).strip())
    if not lo <= n <= hi:
        raise CyberError(f"{name} must be a whole number from {lo} to {hi}.")
    return n


class CyberService:
    def __init__(self, store, vault, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()
    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r["org"] != org:
            raise CyberNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("cy_setting", f"{org}:settings", for_update=for_update)
        return s if s else {"id": "settings", "org": org, "sla_days": dict(DEFAULT_SLA), "acceptance_max_days": DEFAULT_ACCEPT_MAX, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("cy_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other:
            raise CyberForbiddenError(f"You {what}, so you cannot decide it. A different person must.")

    def _evidence(self, org, ids) -> List[dict]:
        out = []
        for i in dict.fromkeys(str(i) for i in (ids or [])):
            try:
                e = self.vault.get_evidence(org, i)
            except Exception:
                raise CyberError("Linked evidence not found in this organisation's Evidence Vault.")
            out.append({"evidence_id": e.id, "filename": e.original_filename, "file_hash": e.file_hash})
        return out

    # ------------------------------------------------------------------ policy
    def get_policy(self, org) -> dict:
        s = self._settings(org)
        sla = s["sla_days"]
        return {"sla_days": sla, "acceptance_max_days": s["acceptance_max_days"], "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"Vulnerabilities should be fixed within {sla['CRITICAL']} days (critical), {sla['HIGH']} (high), {sla['MEDIUM']} (medium) and {sla['LOW']} (low) of being found. "
                           f"A risk can be accepted for at most {s['acceptance_max_days']} days at a time. These are your policy settings, not a standard or law."}

    def set_policy(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        sla = dict(s["sla_days"])
        if d.get("sla_days") is not None:
            if not isinstance(d["sla_days"], dict): raise CyberError("Deadlines must be a list of days per severity.")
            for k, v in d["sla_days"].items():
                if k not in SEVERITIES: raise CyberError(f"{k} is not a severity.")
                sla[k] = _int(v, f"The {k.lower()} deadline", 1, 730)
            vals = [sla[k] for k in SEVERITIES]
            if vals != sorted(vals): raise CyberError("A more severe vulnerability cannot be given a longer deadline than a less severe one.")
        mx = s["acceptance_max_days"]
        if d.get("acceptance_max_days") is not None: mx = _int(d["acceptance_max_days"], "The longest risk acceptance", 1, 365)
        s.update(sla_days=sla, acceptance_max_days=mx, updated_by=actor, updated_at=self.now().isoformat())
        self._put("cy_setting", org, s); self.log("CY_POLICY_SET", actor, "settings", org, f"sla {sla}, acceptance max {mx}")
        return self.get_policy(org)

    # ------------------------------------------------------------------ assets
    def _asset_fields(self, d) -> dict:
        return {"name": _txt(d.get("name"), "Name", 2, 200), "type": _enum(d.get("type") or "OTHER", ASSET_TYPES, "Type"), "owner": _txt(d.get("owner"), "Owner", 2, 200),
                "criticality": _enum(d.get("criticality") or "MEDIUM", CRITICALITIES, "Criticality"), "data_class": _enum(d.get("data_class") or "INTERNAL", DATA_CLASSES, "Data class"),
                "location": _txt(d.get("location"), "Location", 0, 200, required=False), "notes": _txt(d.get("notes"), "Notes", 0, 2000, required=False)}

    def _dup_asset(self, org, name, skip=None):
        for a in self._all("cy_asset", org):
            if a["id"] != skip and a["status"] == "ACTIVE" and a["name"].strip().lower() == name.strip().lower():
                raise CyberError(f"An active asset called {a['name']} already exists ({a['ref']}).")

    def create_asset(self, org, d, actor) -> dict:
        f = self._asset_fields(d); self._dup_asset(org, f["name"])
        a = {"id": uuid.uuid4().hex, "org": org, "ref": self._ref(org, "AS"), **f, "status": "ACTIVE", "created_by": actor, "created_at": self.now().isoformat(), "history": []}
        self._hist(a, actor, "CREATED"); self._put("cy_asset", org, a); self.log("CY_ASSET_CREATED", actor, a["id"], org, f"{a['ref']} {a['name']}")
        return self._aview(org, a)

    def update_asset(self, org, aid, d, actor) -> dict:
        a = self._get("cy_asset", org, aid, "Asset", for_update=True)
        if a["status"] != "ACTIVE": raise CyberStateError("A retired asset cannot be changed.")
        f = self._asset_fields({**a, **{k: v for k, v in d.items() if v is not None}}); self._dup_asset(org, f["name"], skip=aid)
        a.update(f); self._hist(a, actor, "UPDATED"); self._put("cy_asset", org, a); self.log("CY_ASSET_UPDATED", actor, aid, org, a["ref"])
        return self._aview(org, a)

    def retire_asset(self, org, aid, note, actor) -> dict:
        a = self._get("cy_asset", org, aid, "Asset", for_update=True)
        if a["status"] != "ACTIVE": raise CyberStateError("This asset is already retired.")
        open_ = sorted(v["ref"] for v in self._all("cy_vuln", org) if v["asset_id"] == aid and v["status"] in OPEN_VULN + ("ACCEPTED", "FIXED"))
        if open_: raise CyberStateError(f"This asset still has unresolved vulnerabilities ({', '.join(open_)}). Resolve them first.")
        a.update(status="RETIRED", retire_note=_txt(note, "Reason", 3, 500)); self._hist(a, actor, "RETIRED", a["retire_note"]); self._put("cy_asset", org, a); self.log("CY_ASSET_RETIRED", actor, aid, org, a["ref"])
        return self._aview(org, a)

    def _aview(self, org, a, vulns=None) -> dict:
        vulns = self._all("cy_vuln", org) if vulns is None else vulns
        mine = [v for v in vulns if v["asset_id"] == a["id"]]
        return {**a, "open_vulnerabilities": sum(1 for v in mine if v["status"] in OPEN_VULN), "total_vulnerabilities": len(mine)}

    def list_assets(self, org) -> List[dict]:
        vulns = self._all("cy_vuln", org)
        return [self._aview(org, a, vulns) for a in sorted(self._all("cy_asset", org), key=lambda a: a["ref"])]

    def get_asset(self, org, aid) -> dict:
        a = self._get("cy_asset", org, aid, "Asset")
        v = self._aview(org, a); v["vulnerabilities"] = [self._vview(x, asset=a["name"]) for x in sorted(self._all("cy_vuln", org), key=lambda x: x["ref"]) if x["asset_id"] == aid]
        return v

    # ------------------------------------------------------------------ vulnerabilities
    def _vview(self, v, asset=None) -> dict:
        r = dict(v); flags = []
        t = self.today()
        if v["status"] in OPEN_VULN and date.fromisoformat(v["due"]) < t: flags.append("OVERDUE")
        if v["status"] == "ACCEPTED" and date.fromisoformat(v["accepted_until"]) < t: flags.append("ACCEPTANCE_EXPIRED")
        r["flags"] = flags; r["days_overdue"] = (t - date.fromisoformat(v["due"])).days if "OVERDUE" in flags else 0
        if asset is not None: r["asset_name"] = asset
        return r

    def create_vulnerability(self, org, d, actor) -> dict:
        a = self._get("cy_asset", org, str(d.get("asset_id") or ""), "Asset")
        if a["status"] != "ACTIVE": raise CyberStateError("A vulnerability cannot be recorded against a retired asset.")
        sev = _enum(d.get("severity"), SEVERITIES, "Severity"); found = _date(d.get("found_date") or self.today().isoformat(), "Found date")
        if found > self.today(): raise CyberError("The found date cannot be in the future.")
        cve = _txt(d.get("cve"), "CVE", 0, 30, required=False).upper()
        if cve and not re.fullmatch(r"CVE-\d{4}-\d{4,7}", cve): raise CyberError("A CVE looks like CVE-2024-12345.")
        sla = self._settings(org)["sla_days"][sev]
        v = {"id": uuid.uuid4().hex, "org": org, "ref": self._ref(org, "V"), "asset_id": a["id"], "title": _txt(d.get("title"), "Title", 3, 200), "description": _txt(d.get("description"), "Description", 0, 2000, required=False),
             "severity": sev, "cve": cve, "source": _txt(d.get("source"), "Where it was found (scan, review, report...)", 2, 200), "found_date": found.isoformat(), "sla_days": sla, "due": (found + timedelta(days=sla)).isoformat(),
             "status": "OPEN", "created_by": actor, "created_at": self.now().isoformat(), "fixed_by": None, "fix_note": "", "fix_evidence": [], "verified_by": None, "accept_requested_by": None, "accept_reason": "", "accepted_until": None,
             "history": []}
        self._hist(v, actor, "CREATED", f"due {v['due']}"); self._put("cy_vuln", org, v); self.log("CY_VULN_CREATED", actor, v["id"], org, f"{v['ref']} {sev} on {a['ref']}")
        return self._vview(v, a["name"])

    def _v(self, org, vid) -> dict: return self._get("cy_vuln", org, vid, "Vulnerability", for_update=True)

    def _vsave(self, org, v, actor, event, note="", log=None):
        self._hist(v, actor, event, note); self._put("cy_vuln", org, v); self.log(log or f"CY_VULN_{event}", actor, v["id"], org, v["ref"])
        a = self.store.get("cy_asset", f"{org}:{v['asset_id']}"); return self._vview(v, a["name"] if a else "")

    def start_vulnerability(self, org, vid, note, actor) -> dict:
        v = self._v(org, vid)
        if v["status"] != "OPEN": raise CyberStateError("Only an open vulnerability can be started.")
        v["status"] = "IN_PROGRESS"; return self._vsave(org, v, actor, "STARTED", _txt(note, "Note", 0, 500, required=False))

    def mark_fixed(self, org, vid, note, evidence_ids, actor) -> dict:
        v = self._v(org, vid)
        if v["status"] not in ("OPEN", "IN_PROGRESS", "ACCEPTED"): raise CyberStateError("Only an unresolved vulnerability can be marked fixed.")
        v.update(status="FIXED", fixed_by=actor, fixed_date=self.today().isoformat(), fix_note=_txt(note, "What was done to fix it", 5, 1000), fix_evidence=self._evidence(org, evidence_ids), verified_by=None, verify_note="")
        return self._vsave(org, v, actor, "FIXED", v["fix_note"])

    def verify_fix(self, org, vid, actor, note="") -> dict:
        v = self._v(org, vid)
        if v["status"] != "FIXED": raise CyberStateError("Only a vulnerability marked fixed can be verified.")
        self._two(actor, v["fixed_by"], "marked this vulnerability fixed")
        v.update(status="VERIFIED", verified_by=actor, verified_date=self.today().isoformat(), verify_note=_txt(note, "Note", 0, 500, required=False)); return self._vsave(org, v, actor, "VERIFIED", v["verify_note"])

    def reject_fix(self, org, vid, actor, note) -> dict:
        v = self._v(org, vid)
        if v["status"] != "FIXED": raise CyberStateError("Only a vulnerability marked fixed can be sent back.")
        self._two(actor, v["fixed_by"], "marked this vulnerability fixed")
        v.update(status="OPEN", verify_note=_txt(note, "A reason", 5, 500), fixed_by=None); return self._vsave(org, v, actor, "FIX_REJECTED", v["verify_note"])

    def request_acceptance(self, org, vid, reason, until, actor) -> dict:
        v = self._v(org, vid)
        if v["status"] not in ("OPEN", "IN_PROGRESS"): raise CyberStateError("Only an open vulnerability can be put forward for risk acceptance.")
        reason = _txt(reason, "The reason for accepting the risk", 20, 1000); u = _date(until, "Accepted until"); mx = self._settings(org)["acceptance_max_days"]
        if u <= self.today(): raise CyberError("The acceptance must end in the future.")
        if u > self.today() + timedelta(days=mx): raise CyberError(f"A risk can be accepted for at most {mx} days at a time (policy). Choose an earlier date.")
        v.update(status="ACCEPTANCE_PENDING", accept_requested_by=actor, accept_reason=reason, accept_until_requested=u.isoformat()); return self._vsave(org, v, actor, "ACCEPTANCE_REQUESTED", f"until {u.isoformat()}: {reason}")

    def approve_acceptance(self, org, vid, actor, note="") -> dict:
        v = self._v(org, vid)
        if v["status"] != "ACCEPTANCE_PENDING": raise CyberStateError("This vulnerability has no risk acceptance waiting for a decision.")
        self._two(actor, v["accept_requested_by"], "asked for this risk to be accepted")
        u = date.fromisoformat(v["accept_until_requested"])
        if u <= self.today(): raise CyberStateError("The requested acceptance period has already passed. Ask again with a new date.")
        v.update(status="ACCEPTED", accepted_until=u.isoformat(), accepted_by=actor, accept_decision_note=_txt(note, "Note", 0, 500, required=False)); return self._vsave(org, v, actor, "ACCEPTED", f"until {u.isoformat()}")

    def reject_acceptance(self, org, vid, actor, note) -> dict:
        v = self._v(org, vid)
        if v["status"] != "ACCEPTANCE_PENDING": raise CyberStateError("This vulnerability has no risk acceptance waiting for a decision.")
        self._two(actor, v["accept_requested_by"], "asked for this risk to be accepted")
        v.update(status="OPEN", accept_decision_note=_txt(note, "A reason", 3, 500), accept_requested_by=None); return self._vsave(org, v, actor, "ACCEPTANCE_REJECTED", v["accept_decision_note"])

    def reopen_vulnerability(self, org, vid, note, actor) -> dict:
        v = self._v(org, vid)
        if v["status"] != "ACCEPTED": raise CyberStateError("Only a vulnerability with an accepted risk can be reopened.")
        v.update(status="OPEN", accepted_until=None, accepted_by=None); return self._vsave(org, v, actor, "REOPENED", _txt(note, "A reason", 3, 500))

    def list_vulnerabilities(self, org, status=None, severity=None, asset_id=None) -> List[dict]:
        names = {a["id"]: a["name"] for a in self._all("cy_asset", org)}
        out = []
        for v in sorted(self._all("cy_vuln", org), key=lambda v: v["ref"]):
            if status and v["status"] != status.upper(): continue
            if severity and v["severity"] != severity.upper(): continue
            if asset_id and v["asset_id"] != asset_id: continue
            out.append(self._vview(v, names.get(v["asset_id"], "")))
        return out

    def get_vulnerability(self, org, vid) -> dict:
        v = self._get("cy_vuln", org, vid, "Vulnerability"); a = self.store.get("cy_asset", f"{org}:{v['asset_id']}")
        return self._vview(v, a["name"] if a else "")

    # ------------------------------------------------------------------ incidents
    def create_incident(self, org, d, actor) -> dict:
        det = _date(d.get("detected_date") or self.today().isoformat(), "Detected date")
        if det > self.today(): raise CyberError("The detected date cannot be in the future.")
        ids = list(dict.fromkeys(str(i) for i in (d.get("asset_ids") or [])))
        for i in ids: self._get("cy_asset", org, i, "Affected asset")
        pd = d.get("personal_data_involved")
        if not isinstance(pd, bool): raise CyberError("Say whether personal data may be involved (yes or no).")
        n = {"id": uuid.uuid4().hex, "org": org, "ref": self._ref(org, "I"), "title": _txt(d.get("title"), "Title", 3, 200), "description": _txt(d.get("description"), "What happened", 5, 2000),
             "category": _enum(d.get("category"), INCIDENT_CATEGORIES, "Category"), "severity": _enum(d.get("severity"), SEVERITIES, "Severity"), "detected_date": det.isoformat(), "asset_ids": ids,
             "personal_data_involved": pd, "status": "REPORTED", "reported_by": actor, "created_at": self.now().isoformat(), "timeline": [], "contained_date": None, "resolved_date": None, "resolved_by": None,
             "root_cause": "", "lessons_learned": "", "notification_decision": "", "closed_by": None, "history": []}
        self._tl(n, actor, "REPORTED", n["description"]); self._hist(n, actor, "CREATED"); self._put("cy_incident", org, n); self.log("CY_INCIDENT_CREATED", actor, n["id"], org, f"{n['ref']} {n['severity']} {n['category']}")
        return self._iview(org, n)

    def _tl(self, n, actor, event, note, when=None):
        n["timeline"].append({"at": self.now().isoformat(), "date": (when or self.today()).isoformat(), "by": actor, "event": event, "note": note})

    def _i(self, org, iid) -> dict: return self._get("cy_incident", org, iid, "Incident", for_update=True)

    def _iview(self, org, n) -> dict:
        r = dict(n); names = {a["id"]: a["name"] for a in self._all("cy_asset", org)}
        r["asset_names"] = [names.get(i, "(unknown)") for i in n["asset_ids"]]
        det = date.fromisoformat(n["detected_date"])
        r["days_to_contain"] = (date.fromisoformat(n["contained_date"]) - det).days if n["contained_date"] else None
        r["days_to_resolve"] = (date.fromisoformat(n["resolved_date"]) - det).days if n["resolved_date"] else None
        r["days_open"] = (self.today() - det).days if n["status"] not in ("RESOLVED", "CLOSED") else None
        return r

    def _isave(self, org, n, actor, event, note, log):
        self._tl(n, actor, event, note); self._hist(n, actor, event, note); self._put("cy_incident", org, n); self.log(log, actor, n["id"], org, f"{n['ref']} {event}")
        return self._iview(org, n)

    def add_timeline(self, org, iid, note, when, actor) -> dict:
        n = self._i(org, iid)
        if n["status"] == "CLOSED": raise CyberStateError("A closed incident cannot be changed.")
        w = _date(when or self.today().isoformat(), "Date")
        if w > self.today(): raise CyberError("A timeline entry cannot be dated in the future.")
        self._tl(n, actor, "NOTE", _txt(note, "Note", 3, 1000), w); self._put("cy_incident", org, n); self.log("CY_INCIDENT_NOTE", actor, iid, org, n["ref"])
        return self._iview(org, n)

    def investigate_incident(self, org, iid, note, actor) -> dict:
        n = self._i(org, iid)
        if n["status"] != "REPORTED": raise CyberStateError("Only a reported incident can move to investigating.")
        n["status"] = "INVESTIGATING"; return self._isave(org, n, actor, "INVESTIGATING", _txt(note, "Note", 0, 500, required=False), "CY_INCIDENT_INVESTIGATING")

    def contain_incident(self, org, iid, note, actor) -> dict:
        n = self._i(org, iid)
        if n["status"] != "INVESTIGATING": raise CyberStateError("Only an incident being investigated can be marked contained.")
        n.update(status="CONTAINED", contained_date=self.today().isoformat()); return self._isave(org, n, actor, "CONTAINED", _txt(note, "How it was contained", 5, 1000), "CY_INCIDENT_CONTAINED")

    def resolve_incident(self, org, iid, root_cause, actor) -> dict:
        n = self._i(org, iid)
        if n["status"] != "CONTAINED": raise CyberStateError("Only a contained incident can be resolved.")
        rc = _txt(root_cause, "The root cause", 10, 2000)
        n.update(status="RESOLVED", resolved_date=self.today().isoformat(), resolved_by=actor, root_cause=rc); return self._isave(org, n, actor, "RESOLVED", rc, "CY_INCIDENT_RESOLVED")

    def close_incident(self, org, iid, lessons, notification_decision, actor) -> dict:
        n = self._i(org, iid)
        if n["status"] != "RESOLVED": raise CyberStateError("Only a resolved incident can be closed.")
        self._two(actor, n["resolved_by"], "resolved this incident")
        ll = _txt(lessons, "Lessons learned", 20, 2000); nd = _txt(notification_decision, "The notification decision", 10 if n["personal_data_involved"] else 0, 1000, required=n["personal_data_involved"])
        n.update(status="CLOSED", lessons_learned=ll, notification_decision=nd, closed_by=actor, closed_date=self.today().isoformat()); return self._isave(org, n, actor, "CLOSED", ll, "CY_INCIDENT_CLOSED")

    def reopen_incident(self, org, iid, actor, note) -> dict:
        n = self._i(org, iid)
        if n["status"] != "RESOLVED": raise CyberStateError("Only a resolved incident can be sent back for more investigation.")
        self._two(actor, n["resolved_by"], "resolved this incident")
        n.update(status="INVESTIGATING", resolved_date=None, resolved_by=None); return self._isave(org, n, actor, "REOPENED", _txt(note, "A reason", 5, 500), "CY_INCIDENT_REOPENED")

    def list_incidents(self, org, status=None) -> List[dict]:
        return [self._iview(org, n) for n in sorted(self._all("cy_incident", org), key=lambda n: n["ref"]) if not status or n["status"] == status.upper()]

    def get_incident(self, org, iid) -> dict: return self._iview(org, self._get("cy_incident", org, iid, "Incident"))

    # ------------------------------------------------------------------ access reviews
    def create_review(self, org, d, actor) -> dict:
        due = _date(d.get("due_date"), "Due date")
        if due < self.today(): raise CyberError("The due date cannot be in the past.")
        r = {"id": uuid.uuid4().hex, "org": org, "ref": self._ref(org, "AR"), "name": _txt(d.get("name"), "Name", 3, 200), "scope": _txt(d.get("scope"), "What is being reviewed (system or group)", 3, 500), "due_date": due.isoformat(),
             "status": "OPEN", "entries": [], "created_by": actor, "created_at": self.now().isoformat(), "submitted_by": None, "decided_by": None, "decision_note": "", "history": []}
        self._hist(r, actor, "CREATED"); self._put("cy_review", org, r); self.log("CY_REVIEW_CREATED", actor, r["id"], org, r["ref"])
        return self._rvview(r)

    def _rv(self, org, rid) -> dict: return self._get("cy_review", org, rid, "Access review", for_update=True)

    def _rvview(self, r) -> dict:
        v = dict(r); e = r["entries"]
        v["counts"] = {"entries": len(e), "pending": sum(1 for x in e if x["decision"] == "PENDING"), "keep": sum(1 for x in e if x["decision"] == "KEEP"), "remove": sum(1 for x in e if x["decision"] == "REMOVE"),
                       "removed_confirmed": sum(1 for x in e if x["decision"] == "REMOVE" and x["removed_by"])}
        v["overdue"] = r["status"] in ("OPEN", "SUBMITTED", "REJECTED") and date.fromisoformat(r["due_date"]) < self.today()
        return v

    def add_entry(self, org, rid, d, actor) -> dict:
        r = self._rv(org, rid)
        if r["status"] not in ("OPEN", "REJECTED"): raise CyberStateError("Entries can be added only while the review is open.")
        if len(r["entries"]) >= 500: raise CyberError("A review can hold at most 500 entries.")
        r["entries"].append({"id": uuid.uuid4().hex, "subject": _txt(d.get("subject"), "Person or account", 2, 200), "system": _txt(d.get("system"), "System", 2, 200), "access": _txt(d.get("access"), "Access held", 2, 300),
                             "decision": "PENDING", "note": "", "decided_by": None, "removed_by": None, "removed_date": None})
        self._hist(r, actor, "ENTRY_ADDED", r["entries"][-1]["subject"]); self._put("cy_review", org, r); self.log("CY_REVIEW_ENTRY_ADDED", actor, rid, org, r["ref"])
        return self._rvview(r)

    def _entry(self, r, eid):
        e = next((x for x in r["entries"] if x["id"] == eid), None)
        if not e: raise CyberNotFoundError("Review entry not found.")
        return e

    def decide_entry(self, org, rid, eid, decision, note, actor) -> dict:
        r = self._rv(org, rid)
        if r["status"] not in ("OPEN", "REJECTED"): raise CyberStateError("Decisions can be made only while the review is open.")
        e = self._entry(r, eid); dec = _enum(decision, ["KEEP", "REMOVE"], "Decision")
        if e["removed_by"]: raise CyberStateError("This access was already removed; its decision cannot change.")
        e.update(decision=dec, note=_txt(note, "A reason", 3 if dec == "REMOVE" else 0, 500, required=dec == "REMOVE"), decided_by=actor)
        self._hist(r, actor, "ENTRY_DECIDED", f"{e['subject']}: {dec}"); self._put("cy_review", org, r); self.log("CY_REVIEW_ENTRY_DECIDED", actor, rid, org, f"{r['ref']} {dec}")
        return self._rvview(r)

    def confirm_removed(self, org, rid, eid, actor) -> dict:
        r = self._rv(org, rid)
        if r["status"] not in ("OPEN", "REJECTED", "SUBMITTED"): raise CyberStateError("Removal can be confirmed only on a review that is not yet completed.")
        e = self._entry(r, eid)
        if e["decision"] != "REMOVE": raise CyberStateError("Only an entry decided REMOVE can be confirmed as removed.")
        if e["removed_by"]: raise CyberStateError("This removal is already confirmed.")
        e.update(removed_by=actor, removed_date=self.today().isoformat()); self._hist(r, actor, "REMOVAL_CONFIRMED", e["subject"]); self._put("cy_review", org, r); self.log("CY_REVIEW_REMOVAL_CONFIRMED", actor, rid, org, r["ref"])
        return self._rvview(r)

    def submit_review(self, org, rid, actor) -> dict:
        r = self._rv(org, rid)
        if r["status"] not in ("OPEN", "REJECTED"): raise CyberStateError(f"A {r['status'].lower()} review cannot be submitted.")
        c = self._rvview(r)["counts"]
        if not c["entries"]: raise CyberError("Add at least one entry before submitting.")
        if c["pending"]: raise CyberError(f"{c['pending']} entr{'y is' if c['pending'] == 1 else 'ies are'} still undecided.")
        r.update(status="SUBMITTED", submitted_by=actor, decided_by=None, decision_note=""); self._hist(r, actor, "SUBMITTED"); self._put("cy_review", org, r); self.log("CY_REVIEW_SUBMITTED", actor, rid, org, r["ref"])
        return self._rvview(r)

    def approve_review(self, org, rid, actor, note="") -> dict:
        r = self._rv(org, rid)
        if r["status"] != "SUBMITTED": raise CyberStateError("Only a submitted review can be approved.")
        self._two(actor, r["submitted_by"], "submitted this review")
        c = self._rvview(r)["counts"]
        if c["remove"] != c["removed_confirmed"]: raise CyberStateError(f"{c['remove'] - c['removed_confirmed']} removal(s) are not yet confirmed as done.")
        r.update(status="COMPLETED", decided_by=actor, decision_note=_txt(note, "Note", 0, 500, required=False), completed_date=self.today().isoformat()); self._hist(r, actor, "COMPLETED", r["decision_note"]); self._put("cy_review", org, r); self.log("CY_REVIEW_COMPLETED", actor, rid, org, r["ref"])
        return self._rvview(r)

    def reject_review(self, org, rid, actor, note) -> dict:
        r = self._rv(org, rid)
        if r["status"] != "SUBMITTED": raise CyberStateError("Only a submitted review can be sent back.")
        self._two(actor, r["submitted_by"], "submitted this review")
        r.update(status="REJECTED", decided_by=actor, decision_note=_txt(note, "A reason", 3, 1000)); self._hist(r, actor, "REJECTED", r["decision_note"]); self._put("cy_review", org, r); self.log("CY_REVIEW_REJECTED", actor, rid, org, r["ref"])
        return self._rvview(r)

    def list_reviews(self, org) -> List[dict]:
        return [{k: x for k, x in self._rvview(r).items() if k != "entries"} for r in sorted(self._all("cy_review", org), key=lambda r: r["ref"])]

    def get_review(self, org, rid) -> dict: return self._rvview(self._get("cy_review", org, rid, "Access review"))

    # ------------------------------------------------------------------ overview and posture
    def _posture(self, org) -> dict:
        assets = [a for a in self._all("cy_asset", org) if a["status"] == "ACTIVE"]; vulns = [self._vview(v) for v in self._all("cy_vuln", org)]
        incs = [self._iview(org, n) for n in self._all("cy_incident", org)]; revs = [self._rvview(r) for r in self._all("cy_review", org)]; t = self.today()
        by_sev = []
        for s in SEVERITIES:
            xs = [v for v in vulns if v["severity"] == s]; op = [v for v in xs if v["status"] in OPEN_VULN]
            by_sev.append({"severity": s, "open": len(op), "overdue": sum(1 for v in op if "OVERDUE" in v["flags"]), "accepted": sum(1 for v in xs if v["status"] == "ACCEPTED"), "verified": sum(1 for v in xs if v["status"] == "VERIFIED"),
                           "awaiting_verification": sum(1 for v in xs if v["status"] == "FIXED")})
        times = [(date.fromisoformat(v["fixed_date"]) - date.fromisoformat(v["found_date"])).days for v in vulns if v["status"] == "VERIFIED" and v.get("fixed_date")]
        crit = {c: sum(1 for a in assets if a["criticality"] == c) for c in CRITICALITIES}
        exposed = sorted(a["ref"] for a in assets if a["criticality"] in ("HIGH", "CRITICAL") and any(v["asset_id"] == a["id"] and v["status"] in OPEN_VULN and v["severity"] in ("CRITICAL", "HIGH") and "OVERDUE" in v["flags"] for v in vulns))
        open_inc = [n for n in incs if n["status"] in ("REPORTED", "INVESTIGATING", "CONTAINED")]
        contain = [n["days_to_contain"] for n in incs if n["days_to_contain"] is not None]
        return {"as_of": t.isoformat(), "assets": {"active": len(assets), "by_criticality": crit, "high_value_with_overdue_serious_vulns": exposed},
                "vulnerabilities": {"by_severity": by_sev, "open": sum(r["open"] for r in by_sev), "overdue": sum(r["overdue"] for r in by_sev), "accepted_active": sum(1 for v in vulns if v["status"] == "ACCEPTED" and "ACCEPTANCE_EXPIRED" not in v["flags"]),
                                    "acceptance_expired": sum(1 for v in vulns if "ACCEPTANCE_EXPIRED" in v["flags"]), "awaiting_verification": sum(1 for v in vulns if v["status"] == "FIXED"), "pending_acceptance": sum(1 for v in vulns if v["status"] == "ACCEPTANCE_PENDING"),
                                    "average_days_to_fix": round(sum(times) / len(times), 1) if times else None, "fixed_and_verified": len(times)},
                "incidents": {"total": len(incs), "open": len(open_inc), "open_critical_or_high": sum(1 for n in open_inc if n["severity"] in ("CRITICAL", "HIGH")), "awaiting_closure": sum(1 for n in incs if n["status"] == "RESOLVED"),
                              "closed": sum(1 for n in incs if n["status"] == "CLOSED"), "average_days_to_contain": round(sum(contain) / len(contain), 1) if contain else None},
                "reviews": {"total": len(revs), "open": sum(1 for r in revs if r["status"] in ("OPEN", "REJECTED", "SUBMITTED")), "overdue": sum(1 for r in revs if r["overdue"]), "completed": sum(1 for r in revs if r["status"] == "COMPLETED")}}

    def overview(self, org) -> dict:
        p = self._posture(org); vulns = self._all("cy_vuln", org); names = {a["id"]: a["name"] for a in self._all("cy_asset", org)}
        att = [self._vview(v, names.get(v["asset_id"], "")) for v in sorted(vulns, key=lambda v: v["ref"])]
        return {**p, "attention": {"overdue": [v for v in att if "OVERDUE" in v["flags"]], "acceptance_expired": [v for v in att if "ACCEPTANCE_EXPIRED" in v["flags"]]},
                "counts": {"assets": p["assets"]["active"], "vulnerabilities_open": p["vulnerabilities"]["open"], "incidents_open": p["incidents"]["open"], "reviews_open": p["reviews"]["open"],
                           "acceptances_waiting": p["vulnerabilities"]["pending_acceptance"], "fixes_waiting": p["vulnerabilities"]["awaiting_verification"], "closures_waiting": p["incidents"]["awaiting_closure"],
                           "reports": len(self._all("cy_report", org))}, "policy": self.get_policy(org), "limitations": LIMITATIONS}

    def options(self, org) -> dict:
        return {"severities": SEVERITIES, "asset_types": ASSET_TYPES, "data_classes": DATA_CLASSES, "criticalities": CRITICALITIES, "incident_categories": INCIDENT_CATEGORIES, "policy": self.get_policy(org),
                "assets": [{"id": a["id"], "ref": a["ref"], "name": a["name"], "criticality": a["criticality"]} for a in sorted(self._all("cy_asset", org), key=lambda a: a["ref"]) if a["status"] == "ACTIVE"]}

    # ------------------------------------------------------------------ reports
    def _report(self, org, rid, for_update=False) -> dict: return self._get("cy_report", org, rid, "Report", for_update=for_update)

    def create_report(self, org, title, actor) -> dict:
        r = {"id": uuid.uuid4().hex, "org": org, "ref": self._ref(org, "R"), "title": _txt(title, "Report title", 3, 200), "status": "DRAFT", "created_by": actor, "created_at": self.now().isoformat(),
             "submitted_by": None, "decided_by": None, "decision_note": "", "snapshot": None, "fingerprint": None, "version": 0, "history": []}
        self._hist(r, actor, "CREATED"); self._put("cy_report", org, r); self.log("CY_REPORT_CREATED", actor, r["id"], org, r["ref"])
        return self._rview(r)

    def submit_report(self, org, rid, actor) -> dict:
        r = self._report(org, rid, for_update=True)
        if r["status"] not in ("DRAFT", "REJECTED"): raise CyberStateError(f"A {r['status'].lower()} report cannot be submitted.")
        snap = {"generated_at": self.now().isoformat(), "posture": self._posture(org), "policy": self.get_policy(org), "limitations": LIMITATIONS}
        r.update(snapshot=snap, fingerprint=_sha(snap), status="SUBMITTED", version=r["version"] + 1, submitted_by=actor, decided_by=None, decision_note="")
        self._hist(r, actor, "SUBMITTED", f"version {r['version']}"); self._put("cy_report", org, r); self.log("CY_REPORT_SUBMITTED", actor, rid, org, r["ref"])
        return self._rview(r)

    def _decide_report(self, org, rid, actor, ok, note):
        r = self._report(org, rid, for_update=True)
        if r["status"] != "SUBMITTED": raise CyberStateError("Only a submitted report can be approved or sent back.")
        self._two(actor, r["submitted_by"], "submitted this report")
        if ok and _sha(r["snapshot"]) != r["fingerprint"]: raise CyberStateError("The stored report no longer matches its fingerprint. Submit it again.")
        note = _txt(note, "A reason", 0 if ok else 3, 1000, required=not ok)
        r.update(status="APPROVED" if ok else "REJECTED", decided_by=actor, decision_note=note, decided_at=self.now().isoformat())
        self._hist(r, actor, r["status"], note); self._put("cy_report", org, r); self.log("CY_REPORT_APPROVED" if ok else "CY_REPORT_REJECTED", actor, rid, org, r["ref"])
        return self._rview(r)

    def approve_report(self, org, rid, actor, note="") -> dict: return self._decide_report(org, rid, actor, True, note)
    def reject_report(self, org, rid, actor, note) -> dict: return self._decide_report(org, rid, actor, False, note)

    def _rview(self, r, full=True) -> dict:
        v = {k: x for k, x in r.items() if k != "snapshot"}
        v["has_snapshot"] = r["snapshot"] is not None
        if full: v["snapshot"] = r["snapshot"]
        v["confidentiality"] = CONFIDENTIAL
        return v

    def get_report(self, org, rid) -> dict: return self._rview(self._report(org, rid))
    def list_reports(self, org) -> List[dict]: return [self._rview(r, False) for r in sorted(self._all("cy_report", org), key=lambda r: r["ref"])]

    def export_csv(self, org, rid, actor) -> dict:
        r = self._report(org, rid)
        if r["status"] != "APPROVED": raise CyberStateError("Only an approved report can be exported.")
        if _sha(r["snapshot"]) != r["fingerprint"]: raise CyberStateError("The frozen report no longer matches its fingerprint; it cannot be exported.")
        s, buf = r["snapshot"], io.StringIO(); w = csv.writer(buf, lineterminator="\n"); p = s["posture"]
        def safe(v):
            v = "" if v is None else str(v)
            return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v
        w.writerow([CONFIDENTIAL])
        for k, v in [("Report", r["title"]), ("As of", p["as_of"]), ("Version", r["version"]), ("Prepared by (user id)", r["submitted_by"]), ("Approved by (user id)", r["decided_by"]), ("Generated at", s["generated_at"]),
                     ("Fingerprint (SHA-256)", r["fingerprint"]), ("Active assets", p["assets"]["active"]), ("Open vulnerabilities", p["vulnerabilities"]["open"]), ("Overdue vulnerabilities", p["vulnerabilities"]["overdue"]),
                     ("Average days to fix (verified)", p["vulnerabilities"]["average_days_to_fix"] if p["vulnerabilities"]["average_days_to_fix"] is not None else "n/a"), ("Open incidents", p["incidents"]["open"]),
                     ("Average days to contain", p["incidents"]["average_days_to_contain"] if p["incidents"]["average_days_to_contain"] is not None else "n/a")]:
            w.writerow([k, safe(v)])
        w.writerow([]); w.writerow(["VULNERABILITIES BY SEVERITY"]); w.writerow(["Severity", "Open", "Overdue", "Accepted", "Awaiting verification", "Verified"])
        for x in p["vulnerabilities"]["by_severity"]: w.writerow([x["severity"], x["open"], x["overdue"], x["accepted"], x["awaiting_verification"], x["verified"]])
        w.writerow([]); w.writerow(["ASSETS BY CRITICALITY"]); w.writerow(["Criticality", "Active assets"])
        for k, v in p["assets"]["by_criticality"].items(): w.writerow([k, v])
        w.writerow([]); w.writerow(["HIGH-VALUE ASSETS WITH OVERDUE SERIOUS VULNERABILITIES"]); [w.writerow([safe(x)]) for x in p["assets"]["high_value_with_overdue_serious_vulns"]]
        w.writerow([]); w.writerow(["INCIDENTS"]); w.writerow(["Total", "Open", "Open critical or high", "Awaiting closure", "Closed"]); i = p["incidents"]; w.writerow([i["total"], i["open"], i["open_critical_or_high"], i["awaiting_closure"], i["closed"]])
        w.writerow([]); w.writerow(["ACCESS REVIEWS"]); w.writerow(["Total", "Open", "Overdue", "Completed"]); rv = p["reviews"]; w.writerow([rv["total"], rv["open"], rv["overdue"], rv["completed"]])
        w.writerow([]); w.writerow(["POLICY IN FORCE"]); w.writerow([safe(s["policy"]["meaning"])])
        w.writerow([]); w.writerow(["LIMITATIONS"]); [w.writerow([x]) for x in s["limitations"]]
        self.log("CY_REPORT_EXPORTED", actor, rid, org, r["ref"])
        return {"filename": f"{r['ref']}-posture-v{r['version']}.csv", "content": buf.getvalue(), "content_type": "text/csv; charset=utf-8"}
