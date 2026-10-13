"""Evidence Review cases: from "this figure is not fully supported" to an independently verified, re-measured outcome.

A case is opened only when the Evidence Review finds gaps. Opening it measures a BASELINE, runs the `EVIDENCE_REVIEW_COMPLETE`
control (a failing control creates a Finding), and takes the finding to REMEDIATION_REQUIRED. The action is planned with an owner,
carried out, and then VERIFIED by someone else: the verifier is re-measured against the same scope and the outcome is recorded
as IMPROVED / NOT_IMPROVED / RESOLVED. A case is only VERIFIED when the re-measurement shows no gaps. Verification can never be
done by the person who completed the action or by the action's owner. A verified case can be re-checked, and reopens if gaps return.

Findings and remediations are the existing Compliance records; this module drives them and keeps the measurements beside them.
Every lookup is scoped to the organisation; every step writes an audit event. It never changes the ledger or the Evidence Vault.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Callable, List, Optional

from ..compliance.domain.enums import ControlDomain, ControlResult, ControlSeverity
from ..compliance.services.service import CHECK_EVIDENCE_REVIEW_COMPLETE
from .errors import EvidenceReviewError, ReviewForbiddenError, ReviewNotFoundError, ReviewStateError
from .review import build_review, gap_count

KIND = "evr_case"
CONTROL_CODE = "ER-REVIEW"
STATUSES = ("OPEN", "ACTION_PLANNED", "ACTION_DONE", "VERIFIED", "REOPENED")
MAX_TEXT = 2000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _text(value, label, required=True) -> str:
    v = (value or "").strip() if isinstance(value, str) or value is None else str(value).strip()
    if required and not v:
        raise EvidenceReviewError(f"{label} is required.")
    if len(v) > MAX_TEXT:
        raise EvidenceReviewError(f"{label} must be at most {MAX_TEXT} characters.")
    return v


class EvidenceReviewService:
    def __init__(self, store, reporting, vault, compliance, is_member: Callable[[str, str], bool],
                 log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _now):
        self.store, self.reporting, self.vault, self.compliance, self.is_member, self.log, self.now = store, reporting, vault, compliance, is_member, log, now

    # ---------------------------------------------------------------- helpers
    def _put(self, org, c): self.store.put(KIND, f"{org}:{c['id']}", c, org_id=org)

    def _get(self, org, case_id, for_update=False) -> dict:
        c = self.store.get(KIND, f"{org}:{case_id}", for_update=for_update)
        if c is None or c.get("org") != org:
            raise ReviewNotFoundError("Case not found.")
        return c

    def _next_ref(self, org) -> str:
        n = len(self.store.list(KIND, org_id=org)) + 1
        return f"EVR-{n:03d}"

    def _stamp(self, c, actor, event, note="", **extra):
        c["history"].append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note, **extra})
        c["updated_at"] = self.now().isoformat()

    def review(self, org, period_id, report_type, actor, account_id=None, rules=None) -> dict:
        return build_review(self.reporting, org, period_id, report_type, actor, account_id=account_id, rules=rules, vault=self.vault)

    @staticmethod
    def _measure(review: dict) -> dict:
        return {"verdict": review["verdict"], "metrics": review["metrics"], "gaps": gap_count(review), "fingerprint": review["fingerprint"]}

    def _control(self, org, actor):
        existing = self.compliance.definitions.get_by_code(org, CONTROL_CODE)
        if existing is not None:
            return existing
        return self.compliance.define_control(
            org, CONTROL_CODE, "Evidence Review complete",
            "Every journal behind a reported figure has complete, verified, consistent evidence of the expected kind.",
            "A reported figure can be proved from its records.", ControlSeverity.HIGH, ControlDomain.EVIDENCE, CHECK_EVIDENCE_REVIEW_COMPLETE, actor)

    # ---------------------------------------------------------------- open
    def open_case(self, org, period_id, report_type, actor, account_id=None, title: str = "") -> dict:
        review = self.review(org, period_id, report_type, actor, account_id)
        baseline = self._measure(review)
        if baseline["gaps"] == 0:
            raise ReviewStateError("There is nothing to raise: the evidence fully supports this figure.")
        for _, other in self.store.list(KIND, org_id=org):
            if other["scope"] == {"period_id": period_id, "report_type": report_type, "account_id": account_id} and other["status"] != "VERIFIED":
                raise ReviewStateError(f"Case {other['ref']} is already open for this figure.")
        control = self._control(org, actor)
        execution = self.compliance.execute_control(org, control.id, actor, period_id=period_id,
                                                    params={"report_type": report_type, "account_id": account_id})
        if execution.finding_id is None:
            raise ReviewStateError("The control did not record a finding for this figure.")
        self.compliance.start_review(org, execution.finding_id, actor)
        self.compliance.mark_remediation_required(org, execution.finding_id, actor, "Evidence Review found gaps.")
        cid = str(uuid.uuid4())
        case = {
            "id": cid, "org": org, "ref": self._next_ref(org), "status": "OPEN",
            "title": _text(title, "Title", required=False) or f"{report_type.replace('_', ' ').title()}: evidence gaps",
            "scope": {"period_id": period_id, "report_type": report_type, "account_id": account_id},
            "baseline": {**baseline, "measured_at": self.now().isoformat(), "measured_by": actor},
            "control_id": control.id, "execution_id": execution.id, "finding_id": execution.finding_id, "remediation_id": None,
            "action": None, "owner": None, "due_date": None, "opened_by": actor, "completed_by": None, "completion_note": None,
            "outcome": None, "attempts": [], "history": [], "created_at": self.now().isoformat(), "updated_at": self.now().isoformat(),
        }
        self._stamp(case, actor, "OPENED", f"baseline: {baseline['gaps']} gap(s), verdict {baseline['verdict']}")
        self._put(org, case)
        self.log("EVIDENCE_REVIEW_CASE_OPENED", actor, cid, org, f"{case['ref']} baseline gaps={baseline['gaps']}")
        return case

    # ---------------------------------------------------------------- plan / do
    def plan_action(self, org, case_id, action, owner, actor, due_date: Optional[str] = None) -> dict:
        c = self._get(org, case_id, for_update=True)
        if c["status"] not in ("OPEN", "REOPENED"):
            raise ReviewStateError(f"An action can only be planned for an open case (this one is {c['status']}).")
        action = _text(action, "Action")
        owner = _text(owner, "Owner")
        if not self.is_member(org, owner):
            raise EvidenceReviewError("The owner must be a member of this organisation.")
        due = None
        if due_date:
            try:
                due = date.fromisoformat(str(due_date))
            except ValueError:
                raise EvidenceReviewError("Due date must be a date like 2026-12-31.")
        rem = self.compliance.create_remediation(org, c["finding_id"], action, owner, actor, due_date=due)
        self.compliance.start_remediation(org, rem.id, actor)
        c.update(remediation_id=rem.id, action=action, owner=owner, due_date=due.isoformat() if due else None, status="ACTION_PLANNED")
        self._stamp(c, actor, "ACTION_PLANNED", action, owner=owner)
        self._put(org, c)
        self.log("EVIDENCE_REVIEW_ACTION_PLANNED", actor, case_id, org, f"{c['ref']} owner={owner}")
        return c

    def complete_action(self, org, case_id, actor, note, evidence_ref: Optional[str] = None) -> dict:
        c = self._get(org, case_id, for_update=True)
        if c["status"] != "ACTION_PLANNED":
            raise ReviewStateError(f"There is no planned action to complete (this case is {c['status']}).")
        note = _text(note, "Completion note")
        self.compliance.complete_remediation(org, c["remediation_id"], actor, completion_evidence_ref=_text(evidence_ref, "Evidence reference", required=False) or None)
        c.update(completed_by=actor, completion_note=note, status="ACTION_DONE")
        self._stamp(c, actor, "ACTION_DONE", note)
        self._put(org, c)
        self.log("EVIDENCE_REVIEW_ACTION_COMPLETED", actor, case_id, org, c["ref"])
        return c

    # ---------------------------------------------------------------- verify
    def verify_outcome(self, org, case_id, actor, residual_risk, reopen_criteria, note: str = "") -> dict:
        c = self._get(org, case_id, for_update=True)
        if c["status"] != "ACTION_DONE":
            raise ReviewStateError(f"Only a case whose action is done can be verified (this one is {c['status']}).")
        if actor == c["completed_by"] or actor == c["owner"]:
            raise ReviewForbiddenError("The person who did the work, or who owns the action, cannot verify it. Someone independent must.")
        residual_risk = _text(residual_risk, "Residual risk")
        reopen_criteria = _text(reopen_criteria, "Reopen criteria")
        note = _text(note, "Note", required=False)
        s = c["scope"]
        post = self._measure(self.review(org, s["period_id"], s["report_type"], actor, s["account_id"]))
        base = c["baseline"]["gaps"]
        result = "RESOLVED" if post["gaps"] == 0 and post["verdict"] == "SUPPORTED" else ("IMPROVED" if post["gaps"] < base else "NOT_IMPROVED")
        record = {"result": result, "baseline_gaps": base, "post_gaps": post["gaps"], "post": post, "verified_by": actor,
                  "at": self.now().isoformat(), "note": note, "residual_risk": residual_risk, "reopen_criteria": reopen_criteria}
        if result == "RESOLVED":
            self.compliance.verify_remediation(org, c["remediation_id"], actor, note or f"Re-measured: {base} gap(s) before, 0 after.")
            self.compliance.close_finding(org, c["finding_id"], actor)
            c.update(status="VERIFIED", outcome=record)
            self._stamp(c, actor, "VERIFIED", f"gaps {base} -> 0", result=result)
        else:
            reason = f"Re-measured: {post['gaps']} gap(s) remain (was {base}); {result}."
            self.compliance.reject_remediation(org, c["remediation_id"], actor, reason)
            c["attempts"].append(record)
            c.update(status="ACTION_PLANNED", completed_by=None, completion_note=None)
            self._stamp(c, actor, "VERIFICATION_REJECTED", reason, result=result)
        self._put(org, c)
        self.log("EVIDENCE_REVIEW_OUTCOME_VERIFIED" if result == "RESOLVED" else "EVIDENCE_REVIEW_OUTCOME_REJECTED", actor, case_id, org, f"{c['ref']} {result}")
        return c

    # ---------------------------------------------------------------- monitor
    def recheck(self, org, case_id, actor) -> dict:
        """Re-measures a verified case. If gaps have come back, the case and its finding reopen."""
        c = self._get(org, case_id, for_update=True)
        if c["status"] != "VERIFIED":
            raise ReviewStateError(f"Only a verified case can be re-checked (this one is {c['status']}).")
        s = c["scope"]
        now = self._measure(self.review(org, s["period_id"], s["report_type"], actor, s["account_id"]))
        c.setdefault("rechecks", []).append({"at": self.now().isoformat(), "by": actor, "gaps": now["gaps"], "verdict": now["verdict"]})
        if now["gaps"] == 0:
            self._stamp(c, actor, "RECHECKED", "Still fully supported.")
            self.log("EVIDENCE_REVIEW_RECHECKED", actor, case_id, org, f"{c['ref']} clean")
        else:
            reason = f"Gaps returned: {now['gaps']} (reopen criteria: {c['outcome']['reopen_criteria']})"
            self.compliance.reopen_finding(org, c["finding_id"], actor, reason)
            self.compliance.start_review(org, c["finding_id"], actor)
            self.compliance.mark_remediation_required(org, c["finding_id"], actor, reason)
            c.update(status="REOPENED", completed_by=None, completion_note=None, action=None, owner=None, due_date=None, remediation_id=None,
                     baseline={**now, "measured_at": self.now().isoformat(), "measured_by": actor})
            self._stamp(c, actor, "REOPENED", reason)
            self.log("EVIDENCE_REVIEW_CASE_REOPENED", actor, case_id, org, f"{c['ref']} gaps={now['gaps']}")
        self._put(org, c)
        return c

    # ---------------------------------------------------------------- read
    def get_case(self, org, case_id) -> dict:
        c = self._get(org, case_id)
        try:
            c = {**c, "finding_status": self.compliance.get_finding(org, c["finding_id"]).status.value}
        except Exception:
            c = {**c, "finding_status": None}
        return c

    def list_cases(self, org, status: Optional[str] = None) -> List[dict]:
        out = [c for _, c in self.store.list(KIND, org_id=org) if c.get("org") == org and (status is None or c["status"] == status)]
        return sorted(out, key=lambda c: c["created_at"], reverse=True)
