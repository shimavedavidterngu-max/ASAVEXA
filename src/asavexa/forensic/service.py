"""Forensic Accounting and Investigation service.

Records (shared document store, per organisation): forensic_case (with its hash-chained custody log), forensic_run (immutable analytics runs),
forensic_finding, forensic_report. It reads the ledger and the Evidence Vault and never changes either.

Principles enforced here: indicators are not accusations; a second person approves every finding and report; evidence is held by reference plus the hash
seen when it was added, so later tampering is detectable; the custody log is append-only and chained."""
import csv
import hashlib
import io
import json
import uuid
from datetime import date, datetime, timezone
from typing import Callable, List, Optional

from . import analytics
from .errors import ForensicError, ForensicForbiddenError, ForensicNotFoundError, ForensicStateError

CASE_TYPES = {"SUSPECTED_FRAUD": "Suspected fraud or misappropriation", "IRREGULARITY": "Accounting irregularity", "CONTROL_FAILURE": "Control failure review", "DISPUTE": "Dispute or claim support", "OTHER": "Other review"}
SEVERITY = ("LOW", "MEDIUM", "HIGH")
LIMITATIONS = [
    "Analytics flag indicators: patterns that deserve a human look. A flag is not proof of error, fraud or wrongdoing, and most have ordinary explanations.",
    "Findings are the investigator's reasoned conclusions and were approved by a second person. They are not legal findings, not an audit opinion, and not a determination of guilt.",
    "Only posted journals are examined. Drafts are excluded. Amounts in different currencies are not converted.",
    "Evidence is held by reference with the file fingerprint recorded when it was added. ASAVEXA does not judge whether a document is genuine.",
    "Take legal advice before acting on a case, particularly before any disciplinary, employment or criminal step.",
]
GENESIS = "0" * 64


def _utc(): return datetime.now(timezone.utc)
def _sha(o) -> str: return hashlib.sha256(json.dumps(o, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v))).strip()
    if required and len(v) < lo:
        raise ForensicError(f"{name} is required (at least {lo} characters).")
    if len(v) > hi:
        raise ForensicError(f"{name} is too long (limit {hi} characters).")
    return v


class ForensicService:
    def __init__(self, store, accounting, vault, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.accounting, self.vault, self.log, self.now = store, accounting, vault, log, now

    # ------------------------------------------------------------------ helpers
    def _case(self, org, cid, for_update=False) -> dict:
        c = self.store.get("forensic_case", f"{org}:{cid}", for_update=for_update)
        if c is None or c["org"] != org:
            raise ForensicNotFoundError("Case not found.")
        return c

    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)

    def _note(self, org, cid, actor, action, detail=""):
        """Appends one entry to the case's custody chain (allowed even after closure: the chain simply continues)."""
        c = self._case(org, cid, for_update=True)
        self._custody(c, actor, action, detail)
        self._put("forensic_case", org, c)

    def _custody(self, c, actor, action, detail=""):
        prev = c["custody"][-1]["hash"] if c["custody"] else GENESIS
        e = {"seq": len(c["custody"]) + 1, "at": self.now().isoformat(), "actor": actor, "action": action, "detail": detail, "prev": prev}
        e["hash"] = _sha({k: e[k] for k in ("seq", "at", "actor", "action", "detail", "prev")})
        c["custody"].append(e)

    @staticmethod
    def _chain_ok(custody) -> dict:
        prev = GENESIS
        for e in custody:
            if e["prev"] != prev or e["hash"] != _sha({k: e[k] for k in ("seq", "at", "actor", "action", "detail", "prev")}):
                return {"ok": False, "broken_at": e["seq"]}
            prev = e["hash"]
        return {"ok": True, "broken_at": None}

    def _view_case(self, c, brief=False) -> dict:
        v = dict(c)
        v["type_text"] = CASE_TYPES.get(c["case_type"], c["case_type"])
        v["custody_head"] = c["custody"][-1]["hash"] if c["custody"] else GENESIS
        if brief:
            v.pop("custody", None); v.pop("evidence", None)
        return v

    # ------------------------------------------------------------------ cases
    def case_options(self) -> dict:
        return {"case_types": CASE_TYPES, "tests": analytics.TESTS, "defaults": analytics.DEFAULTS, "severities": list(SEVERITY), "limitations": LIMITATIONS}

    def create_case(self, org, title, description, case_type, actor) -> dict:
        if case_type not in CASE_TYPES:
            raise ForensicError("Choose a case type from the list.")
        n = len(self.store.list("forensic_case", org_id=org, prefix=f"{org}:")) + 1
        c = {"id": str(uuid.uuid4()), "org": org, "reference": f"CASE-{n:04d}", "title": _txt(title, "Title", 3, 160), "description": _txt(description, "Description", 0, 2000, required=False),
             "case_type": case_type, "status": "OPEN", "opened_by": actor, "opened_at": self.now().isoformat(), "closed_by": None, "closure_note": "", "evidence": [], "custody": [], "version": 1}
        self._custody(c, actor, "CASE_OPENED", c["title"])
        self._put("forensic_case", org, c)
        self.log("FORENSIC_CASE_OPENED", actor, c["id"], org, f"{c['reference']} {case_type}")
        return self._view_case(c)

    def get_case(self, org, cid) -> dict:
        c = self._case(org, cid)
        v = self._view_case(c)
        v["findings"] = self.list_findings(org, cid); v["runs"] = self.list_runs(org, cid); v["reports"] = self.list_reports(org, cid)
        v["custody_check"] = self._chain_ok(c["custody"])
        return v

    def list_cases(self, org) -> List[dict]:
        rows = [self._view_case(c, brief=True) for _, c in self.store.list("forensic_case", org_id=org, prefix=f"{org}:")]
        for r in rows:
            r["finding_count"] = len(self.list_findings(org, r["id"]))
        return sorted(rows, key=lambda r: r["reference"], reverse=True)

    def update_case(self, org, cid, title, description, actor) -> dict:
        c = self._case(org, cid, for_update=True)
        if c["status"] != "OPEN":
            raise ForensicStateError("A closed case cannot be edited.")
        c["title"], c["description"] = _txt(title, "Title", 3, 160), _txt(description, "Description", 0, 2000, required=False)
        c["version"] += 1
        self._custody(c, actor, "CASE_EDITED", c["title"])
        self._put("forensic_case", org, c)
        self.log("FORENSIC_CASE_EDITED", actor, cid, org, "")
        return self._view_case(c)

    def close_case(self, org, cid, actor, note) -> dict:
        c = self._case(org, cid, for_update=True)
        if c["status"] != "OPEN":
            raise ForensicStateError("This case is already closed.")
        if actor == c["opened_by"]:
            raise ForensicForbiddenError("A different person must close the case. You opened it.")
        open_f = [f for f in self.list_findings(org, cid) if f["status"] in ("DRAFT", "SUBMITTED")]
        if open_f:
            raise ForensicStateError(f"{len(open_f)} finding(s) are still draft or waiting for review. Approve, reject or discard them before closing.")
        c["status"], c["closed_by"], c["closure_note"] = "CLOSED", actor, _txt(note, "Closure note", 3, 1000)
        self._custody(c, actor, "CASE_CLOSED", c["closure_note"])
        self._put("forensic_case", org, c)
        self.log("FORENSIC_CASE_CLOSED", actor, cid, org, c["closure_note"])
        return self._view_case(c)

    def _open(self, org, cid, for_update=True) -> dict:
        c = self._case(org, cid, for_update=for_update)
        if c["status"] != "OPEN":
            raise ForensicStateError("This case is closed; nothing can be added to it.")
        return c

    # ------------------------------------------------------------------ evidence and custody
    def add_evidence(self, org, cid, evidence_id, note, actor) -> dict:
        c = self._open(org, cid)
        e = self.vault.get_evidence(org, evidence_id)
        if any(x["evidence_id"] == e.id for x in c["evidence"]):
            raise ForensicStateError("That evidence is already in this case.")
        item = {"evidence_id": e.id, "filename": e.original_filename, "file_hash": e.file_hash, "status_when_added": e.status.value, "note": _txt(note, "Note", 0, 500, required=False), "added_by": actor, "added_at": self.now().isoformat()}
        c["evidence"].append(item)
        self._custody(c, actor, "EVIDENCE_ADDED", f"{e.original_filename} sha256 {e.file_hash[:16]}...")
        self._put("forensic_case", org, c)
        self.log("FORENSIC_EVIDENCE_ADDED", actor, cid, org, e.original_filename)
        return item

    def verify_custody(self, org, cid) -> dict:
        c = self._case(org, cid)
        chain = self._chain_ok(c["custody"])
        items = []
        for it in c["evidence"]:
            try:
                now = self.vault.get_evidence(org, it["evidence_id"])
                same = now.file_hash == it["file_hash"]
                items.append({"evidence_id": it["evidence_id"], "filename": it["filename"], "hash_matches": same, "status_now": now.status.value, "present": True})
            except Exception:
                items.append({"evidence_id": it["evidence_id"], "filename": it["filename"], "hash_matches": False, "status_now": None, "present": False})
        ok = chain["ok"] and all(i["hash_matches"] for i in items)
        return {"ok": ok, "custody_chain": chain, "evidence": items, "entries": len(c["custody"]), "head": c["custody"][-1]["hash"], "checked_at": self.now().isoformat(),
                "meaning": "The custody log is unbroken and every evidence file still has the fingerprint recorded when it was added." if ok else
                           "Something does not match: the custody log was altered, or an evidence file differs from, or is missing since, the version recorded. Treat the affected items as compromised until explained."}

    # ------------------------------------------------------------------ analytics
    def _rows(self, org, scope: dict) -> (List[dict], dict):
        if scope.get("period_id"):
            p = self.accounting.periods.get(org, scope["period_id"])
            if p is None:
                raise ForensicNotFoundError("That accounting period was not found in this organisation.")
            js = self.accounting.journals.list_for_org(org, period_id=p.id)
            desc = {"kind": "period", "period_id": p.id, "name": p.name, "start": str(p.start_date), "end": str(p.end_date)}
        else:
            try:
                s, e = date.fromisoformat(str(scope.get("start"))), date.fromisoformat(str(scope.get("end")))
            except ValueError:
                raise ForensicError("Choose a period, or enter a start and end date like 2026-01-31.")
            if e < s:
                raise ForensicError("The end date cannot be before the start date.")
            js = [j for j in self.accounting.journals.list_for_org(org) if s <= j.date <= e]
            desc = {"kind": "dates", "start": s.isoformat(), "end": e.isoformat()}
        rows = []
        for j in js:
            st = j.status.value if hasattr(j.status, "value") else str(j.status)
            if st == "DRAFT":
                continue
            rows.append({"id": j.id, "number": j.journal_number, "date": j.date, "description": j.description or "", "created_by": j.created_by, "posted_by": j.posted_by, "posted_at": j.posted_at,
                         "total": j.total_debits(), "lines": [(l.account_id, l.debit_amount, l.credit_amount) for l in j.lines], "evidence_ref": j.evidence_ref,
                         "reversal_of": j.reversal_of_journal_id, "reversed_by": j.reversed_by_journal_id})
        rows.sort(key=lambda r: (r["date"], r["number"]))
        return rows, desc

    def run_analytics(self, org, cid, scope: dict, tests: List[str], params: Optional[dict], actor) -> dict:
        c = self._open(org, cid)
        p = analytics.clean_params(params)
        rows, desc = self._rows(org, scope or {})
        results = analytics.run_tests(rows, list(tests or []), p)
        run = {"id": str(uuid.uuid4()), "org": org, "case_id": cid, "scope": desc, "tests": [r["id"] for r in results], "params": p, "journals_examined": len(rows), "results": results,
               "kind": "INDICATORS ONLY (not proof of wrongdoing)", "limitations": LIMITATIONS, "run_by": actor, "run_at": self.now().isoformat()}
        run["fingerprint"] = _sha({k: run[k] for k in ("scope", "tests", "params", "journals_examined", "results")})
        self._put("forensic_run", org, run)
        self._custody(c, actor, "ANALYTICS_RUN", f"{', '.join(run['tests'])} over {len(rows)} journals; fingerprint {run['fingerprint'][:16]}...")
        self._put("forensic_case", org, c)
        self.log("FORENSIC_ANALYTICS_RUN", actor, cid, org, f"{len(rows)} journals, {len(results)} tests")
        return run

    def list_runs(self, org, cid) -> List[dict]:
        rows = [d for _, d in self.store.list("forensic_run", org_id=org, prefix=f"{org}:") if d["case_id"] == cid]
        out = [{"id": r["id"], "scope": r["scope"], "tests": r["tests"], "journals_examined": r["journals_examined"], "run_by": r["run_by"], "run_at": r["run_at"], "fingerprint": r["fingerprint"],
                "indicator_count": sum(1 for x in r["results"] if x["status"] == "INDICATORS")} for r in rows]
        return sorted(out, key=lambda r: r["run_at"], reverse=True)

    def get_run(self, org, rid) -> dict:
        r = self.store.get("forensic_run", f"{org}:{rid}")
        if r is None or r["org"] != org:
            raise ForensicNotFoundError("Analytics run not found.")
        return r

    # ------------------------------------------------------------------ findings
    def _finding(self, org, fid, for_update=False) -> dict:
        f = self.store.get("forensic_finding", f"{org}:{fid}", for_update=for_update)
        if f is None or f["org"] != org:
            raise ForensicNotFoundError("Finding not found.")
        return f

    @staticmethod
    def _hist(f, actor, action, note="", at=None): f["history"].append({"at": at, "actor": actor, "action": action, "note": note})

    def _journal_refs(self, org, ids) -> List[dict]:
        out = []
        for jid in dict.fromkeys(ids or []):
            j = self.accounting.journals.get(org, jid)
            if j is None:
                raise ForensicNotFoundError("One of the journals was not found in this organisation.")
            out.append({"id": j.id, "number": j.journal_number, "date": j.date.isoformat(), "amount": str(j.total_debits()), "description": (j.description or "")[:120]})
        return out

    def create_finding(self, org, cid, title, description, severity, journal_ids, evidence_ids, run_id, actor) -> dict:
        c = self._open(org, cid, for_update=False)
        if severity not in SEVERITY:
            raise ForensicError("Severity must be low, medium or high.")
        in_case = {e["evidence_id"] for e in c["evidence"]}
        for eid in evidence_ids or []:
            if eid not in in_case:
                raise ForensicError("Evidence on a finding must first be added to the case.")
        if run_id:
            r = self.get_run(org, run_id)
            if r["case_id"] != cid:
                raise ForensicNotFoundError("Analytics run not found in this case.")
        f = {"id": str(uuid.uuid4()), "org": org, "case_id": cid, "title": _txt(title, "Title", 3, 160), "description": _txt(description, "What was found, and what supports it", 20, 3000),
             "severity": severity, "journals": self._journal_refs(org, journal_ids), "evidence_ids": list(dict.fromkeys(evidence_ids or [])), "run_id": run_id or None, "status": "DRAFT", "version": 1,
             "created_by": actor, "created_at": self.now().isoformat(), "submitted_by": None, "decided_by": None, "decision_note": "", "history": []}
        self._hist(f, actor, "CREATED", at=f["created_at"])
        self._put("forensic_finding", org, f)
        c2 = self._case(org, cid, for_update=True); self._custody(c2, actor, "FINDING_DRAFTED", f["title"]); self._put("forensic_case", org, c2)
        self.log("FORENSIC_FINDING_CREATED", actor, f["id"], org, f"{severity}: {f['title']}")
        return f

    def update_finding(self, org, fid, title, description, severity, journal_ids, evidence_ids, actor) -> dict:
        f = self._finding(org, fid, for_update=True)
        self._open(org, f["case_id"], for_update=False)
        if f["status"] not in ("DRAFT", "REJECTED"):
            raise ForensicStateError("Only a draft or a finding that was sent back can be edited.")
        if severity not in SEVERITY:
            raise ForensicError("Severity must be low, medium or high.")
        c = self._case(org, f["case_id"])
        for eid in evidence_ids or []:
            if eid not in {e["evidence_id"] for e in c["evidence"]}:
                raise ForensicError("Evidence on a finding must first be added to the case.")
        f.update(title=_txt(title, "Title", 3, 160), description=_txt(description, "What was found, and what supports it", 20, 3000), severity=severity, journals=self._journal_refs(org, journal_ids), evidence_ids=list(dict.fromkeys(evidence_ids or [])))
        f["version"] += 1; f["status"] = "DRAFT"
        self._hist(f, actor, "EDITED", at=self.now().isoformat())
        self._put("forensic_finding", org, f)
        self.log("FORENSIC_FINDING_EDITED", actor, fid, org, "")
        return f

    def submit_finding(self, org, fid, actor) -> dict:
        f = self._finding(org, fid, for_update=True)
        self._open(org, f["case_id"], for_update=False)
        if f["status"] not in ("DRAFT", "REJECTED"):
            raise ForensicStateError("Only a draft can be submitted for review.")
        f["status"], f["submitted_by"] = "SUBMITTED", actor
        self._hist(f, actor, "SUBMITTED", at=self.now().isoformat())
        self._put("forensic_finding", org, f)
        self._note(org, f["case_id"], actor, "FINDING_SUBMITTED", f["title"])
        self.log("FORENSIC_FINDING_SUBMITTED", actor, fid, org, "")
        return f

    def _decide_finding(self, org, fid, actor, approve, note) -> dict:
        f = self._finding(org, fid, for_update=True)
        if f["status"] != "SUBMITTED":
            raise ForensicStateError("Only a finding waiting for review can be approved or sent back.")
        if actor in (f["created_by"], f["submitted_by"]):
            raise ForensicForbiddenError("A different person must review this finding. You prepared or submitted it.")
        note = _txt(note, "Note", 0 if approve else 3, 1000, required=not approve)
        f["status"], f["decided_by"], f["decision_note"] = ("APPROVED" if approve else "REJECTED"), actor, note
        self._hist(f, actor, f["status"], note, at=self.now().isoformat())
        self._put("forensic_finding", org, f)
        c = self._case(org, f["case_id"], for_update=True); self._custody(c, actor, "FINDING_" + f["status"], f["title"]); self._put("forensic_case", org, c)
        self.log("FORENSIC_FINDING_" + f["status"], actor, fid, org, note)
        return f

    def approve_finding(self, org, fid, actor, note="") -> dict: return self._decide_finding(org, fid, actor, True, note)
    def reject_finding(self, org, fid, actor, reason) -> dict: return self._decide_finding(org, fid, actor, False, reason)

    def discard_finding(self, org, fid, actor) -> dict:
        f = self._finding(org, fid, for_update=True)
        if f["status"] not in ("DRAFT", "REJECTED"):
            raise ForensicStateError("Only a draft can be discarded.")
        f["status"] = "DISCARDED"; self._hist(f, actor, "DISCARDED", at=self.now().isoformat()); self._put("forensic_finding", org, f)
        self.log("FORENSIC_FINDING_DISCARDED", actor, fid, org, "")
        return {"id": fid, "discarded": True}

    def list_findings(self, org, cid) -> List[dict]:
        rows = [d for _, d in self.store.list("forensic_finding", org_id=org, prefix=f"{org}:") if d["case_id"] == cid and d["status"] != "DISCARDED"]
        return sorted(rows, key=lambda r: r["created_at"])

    def get_finding(self, org, fid) -> dict: return self._finding(org, fid)

    # ------------------------------------------------------------------ report
    def create_report(self, org, cid, title, actor) -> dict:
        c = self._case(org, cid)
        approved = [f for f in self.list_findings(org, cid) if f["status"] == "APPROVED"]
        verify = self.verify_custody(org, cid)
        r = {"id": str(uuid.uuid4()), "org": org, "case_id": cid, "title": _txt(title, "Report title", 3, 160), "status": "DRAFT", "created_by": actor, "created_at": self.now().isoformat(),
             "submitted_by": None, "decided_by": None, "decision_note": "", "history": [], "snapshot": {
                 "generated_at": self.now().isoformat(), "case": {"reference": c["reference"], "title": c["title"], "type": CASE_TYPES.get(c["case_type"]), "status": c["status"], "opened_by": c["opened_by"], "opened_at": c["opened_at"], "description": c["description"]},
                 "findings": [{k: f[k] for k in ("id", "title", "description", "severity", "journals", "evidence_ids", "created_by", "decided_by", "decision_note")} for f in approved],
                 "evidence": [{k: e[k] for k in ("evidence_id", "filename", "file_hash", "added_by", "added_at")} for e in c["evidence"]],
                 "runs": self.list_runs(org, cid), "custody_head": verify["head"], "custody_entries": verify["entries"], "integrity": {"ok": verify["ok"], "meaning": verify["meaning"]}, "limitations": LIMITATIONS}}
        r["fingerprint"] = _sha(r["snapshot"])
        r["history"].append({"at": r["created_at"], "actor": actor, "action": "CREATED", "note": f"{len(approved)} approved finding(s)"})
        self._put("forensic_report", org, r)
        self._note(org, cid, actor, "REPORT_FROZEN", f"{r['title']}; fingerprint {r['fingerprint'][:16]}...")
        self.log("FORENSIC_REPORT_CREATED", actor, r["id"], org, c["reference"])
        return r

    def _report(self, org, rid, for_update=False) -> dict:
        r = self.store.get("forensic_report", f"{org}:{rid}", for_update=for_update)
        if r is None or r["org"] != org:
            raise ForensicNotFoundError("Report not found.")
        return r

    def get_report(self, org, rid) -> dict:
        r = dict(self._report(org, rid)); r["intact"] = _sha(r["snapshot"]) == r["fingerprint"]; return r

    def list_reports(self, org, cid) -> List[dict]:
        rows = [d for _, d in self.store.list("forensic_report", org_id=org, prefix=f"{org}:") if d["case_id"] == cid]
        return [{"id": r["id"], "title": r["title"], "status": r["status"], "created_by": r["created_by"], "created_at": r["created_at"], "fingerprint": r["fingerprint"]} for r in sorted(rows, key=lambda r: r["created_at"])]

    def submit_report(self, org, rid, actor) -> dict:
        r = self._report(org, rid, for_update=True)
        if r["status"] not in ("DRAFT", "REJECTED"):
            raise ForensicStateError("Only a draft report can be submitted.")
        r["status"], r["submitted_by"] = "SUBMITTED", actor
        r["history"].append({"at": self.now().isoformat(), "actor": actor, "action": "SUBMITTED", "note": ""})
        self._put("forensic_report", org, r); self._note(org, r["case_id"], actor, "REPORT_SUBMITTED", r["title"]); self.log("FORENSIC_REPORT_SUBMITTED", actor, rid, org, "")
        return r

    def _decide_report(self, org, rid, actor, approve, note) -> dict:
        r = self._report(org, rid, for_update=True)
        if r["status"] != "SUBMITTED":
            raise ForensicStateError("Only a submitted report can be approved or sent back.")
        if actor in (r["created_by"], r["submitted_by"]):
            raise ForensicForbiddenError("A different person must review this report. You prepared or submitted it.")
        if _sha(r["snapshot"]) != r["fingerprint"]:
            raise ForensicStateError("The frozen report no longer matches its fingerprint; it cannot be approved.")
        note = _txt(note, "Note", 0 if approve else 3, 1000, required=not approve)
        r["status"], r["decided_by"], r["decision_note"] = ("APPROVED" if approve else "REJECTED"), actor, note
        r["history"].append({"at": self.now().isoformat(), "actor": actor, "action": r["status"], "note": note})
        self._put("forensic_report", org, r); self._note(org, r["case_id"], actor, "REPORT_" + r["status"], r["title"]); self.log("FORENSIC_REPORT_" + r["status"], actor, rid, org, note)
        return r

    def approve_report(self, org, rid, actor, note="") -> dict: return self._decide_report(org, rid, actor, True, note)
    def reject_report(self, org, rid, actor, reason) -> dict: return self._decide_report(org, rid, actor, False, reason)

    def export_csv(self, org, rid, actor) -> dict:
        r = self._report(org, rid)
        if r["status"] != "APPROVED":
            raise ForensicStateError("Only an approved report can be exported.")
        if _sha(r["snapshot"]) != r["fingerprint"]:
            raise ForensicStateError("The frozen report no longer matches its fingerprint; it cannot be exported.")
        s, buf = r["snapshot"], io.StringIO(); w = csv.writer(buf)
        def safe(v):
            v = "" if v is None else str(v)
            return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v
        w.writerow(["STRICTLY CONFIDENTIAL - ASAVEXA forensic case report. Indicators and findings are not proof of wrongdoing and not legal advice."])
        for k, v in [("Case", s["case"]["reference"]), ("Title", s["case"]["title"]), ("Report", r["title"]), ("Prepared by (user id)", r["created_by"]), ("Approved by (user id)", r["decided_by"]),
                     ("Fingerprint (SHA-256)", r["fingerprint"]), ("Custody log head", s["custody_head"]), ("Integrity at freeze", s["integrity"]["meaning"])]:
            w.writerow([k, safe(v)])
        w.writerow([]); w.writerow(["APPROVED FINDINGS"]); w.writerow(["Severity", "Title", "Description", "Journals", "Reviewer note"])
        for f in s["findings"]:
            w.writerow([f["severity"], safe(f["title"]), safe(f["description"]), safe("; ".join(j["number"] for j in f["journals"])), safe(f["decision_note"])])
        w.writerow([]); w.writerow(["EVIDENCE"]); w.writerow(["File", "SHA-256 when added", "Added by", "Added at"])
        for e in s["evidence"]:
            w.writerow([safe(e["filename"]), e["file_hash"], e["added_by"], e["added_at"]])
        w.writerow([]); w.writerow(["LIMITATIONS"])
        for l in s["limitations"]:
            w.writerow([l])
        self.log("FORENSIC_REPORT_EXPORTED", actor, rid, org, s["case"]["reference"])
        return {"filename": f"{s['case']['reference']}-report.csv", "content": buf.getvalue(), "content_type": "text/csv; charset=utf-8"}
