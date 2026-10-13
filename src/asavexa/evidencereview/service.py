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
from datetime import date, datetime, timedelta, timezone
from typing import Callable, List, Optional

from ..compliance.domain.enums import ControlDomain, ControlResult, ControlSeverity
from ..compliance.services.service import CHECK_EVIDENCE_REVIEW_COMPLETE
from .errors import EvidenceReviewError, ReviewForbiddenError, ReviewNotFoundError, ReviewStateError
from .review import build_review, gap_count
from .rules import DEFAULT_RULES, validate_org_rules

KIND = "evr_case"
RULES_KIND = "evr_rules"
CONTROL_CODE = "ER-REVIEW"
STATUSES = ("OPEN", "ACTION_PLANNED", "ACTION_DONE", "VERIFIED", "REOPENED")
RESIDUAL_LEVELS = ("LOW", "MEDIUM", "HIGH")
MAX_TEXT = 2000
MAX_TOLERANCE = 1000
MAX_RECHECK_DAYS = 366


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
                 log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _now, links=None):
        self.store, self.reporting, self.vault, self.compliance, self.is_member, self.log, self.now = store, reporting, vault, compliance, is_member, log, now
        self.links = links  # optional: the stored Proof-to-Action graph. When present, each case records the links it creates, marked as made by the system.

    def _link(self, org, actor, from_ref, to_ref, relation, note):
        """Records a system link in the graph. A graph problem never blocks the case, but it is never silent: it is written to the audit trail."""
        if self.links is None:
            return
        try:
            self.links.record_system_link(org, from_ref, to_ref, relation, actor, note)
        except Exception as exc:
            self.log("GRAPH_LINK_SYNC_FAILED", actor, from_ref[1], org, f"{relation}: {exc}"[:200])

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

    @staticmethod
    def _whole(value, label, lo, hi) -> int:
        if isinstance(value, bool):
            raise EvidenceReviewError(f"{label} must be a whole number.")
        try:
            n = int(value)
            if str(value).strip() != str(n):
                raise ValueError
        except (TypeError, ValueError):
            raise EvidenceReviewError(f"{label} must be a whole number.")
        if not lo <= n <= hi:
            raise EvidenceReviewError(f"{label} must be between {lo} and {hi}.")
        return n

    def _due_from(self, days) -> Optional[str]:
        if not days:
            return None
        return (self.now().date() + timedelta(days=int(days))).isoformat()

    def review(self, org, period_id, report_type, actor, account_id=None, rules=None, rules_version: Optional[int] = None) -> dict:
        """Runs the review. Rules come from, in order: the `rules` passed in, the saved rule-set version asked for, or the organisation's active rule set."""
        if rules is None:
            doc = self.rule_set_version(org, rules_version) if rules_version is not None else self.active_rule_set(org)
            rules, version = doc["rules"], doc["version"]
        else:
            version = None
        out = build_review(self.reporting, org, period_id, report_type, actor, account_id=account_id, rules=rules, vault=self.vault)
        out["rules_version"] = version
        return out

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
        pinned = review["rules_version"]
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
            "id": cid, "org": org, "ref": self._next_ref(org), "status": "OPEN", "rules_version": pinned,
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
        self._link(org, actor, ("outcome", cid), ("finding", execution.finding_id), "ADDRESSES", f"Case {case['ref']} was raised for this finding.")
        self._link(org, actor, ("finding", execution.finding_id), ("control", control.id), "RAISED_BY", "The Evidence Review control found the gaps.")
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
        self._link(org, actor, ("remediation", rem.id), ("finding", c["finding_id"]), "ADDRESSES", f"Planned in case {c['ref']}: {action[:100]}")
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
    def verify_outcome(self, org, case_id, actor, residual_risk, reopen_criteria, note: str = "", *,
                       residual_level: Optional[str] = None, reopen_if_gaps_above: int = 0, recheck_after_days: Optional[int] = None) -> dict:
        c = self._get(org, case_id, for_update=True)
        if c["status"] != "ACTION_DONE":
            raise ReviewStateError(f"Only a case whose action is done can be verified (this one is {c['status']}).")
        if actor == c["completed_by"] or actor == c["owner"]:
            raise ReviewForbiddenError("The person who did the work, or who owns the action, cannot verify it. Someone independent must.")
        residual_risk = _text(residual_risk, "Residual risk")
        reopen_criteria = _text(reopen_criteria, "Reopen criteria")
        note = _text(note, "Note", required=False)
        level = None
        if residual_level not in (None, ""):
            level = str(residual_level).strip().upper()
            if level not in RESIDUAL_LEVELS:
                raise EvidenceReviewError("Residual risk level must be LOW, MEDIUM or HIGH.")
        tolerance = self._whole(reopen_if_gaps_above, "Reopen threshold", 0, MAX_TOLERANCE)
        days = None if recheck_after_days in (None, "") else self._whole(recheck_after_days, "Re-check interval (days)", 1, MAX_RECHECK_DAYS)
        s = c["scope"]
        post = self._measure(self.review(org, s["period_id"], s["report_type"], actor, s["account_id"], rules_version=c.get("rules_version") or 0))
        base = c["baseline"]["gaps"]
        result = "RESOLVED" if post["gaps"] == 0 and post["verdict"] == "SUPPORTED" else ("IMPROVED" if post["gaps"] < base else "NOT_IMPROVED")
        record = {"result": result, "baseline_gaps": base, "post_gaps": post["gaps"], "post": post, "verified_by": actor,
                  "at": self.now().isoformat(), "note": note, "residual_risk": residual_risk, "residual_level": level,
                  "reopen_criteria": reopen_criteria, "reopen_if_gaps_above": tolerance, "recheck_after_days": days}
        if result == "RESOLVED":
            self.compliance.verify_remediation(org, c["remediation_id"], actor, note or f"Re-measured: {base} gap(s) before, 0 after.")
            self.compliance.close_finding(org, c["finding_id"], actor)
            c.update(status="VERIFIED", outcome=record, recheck_due=self._due_from(days))
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
        fresh = self.review(org, s["period_id"], s["report_type"], actor, s["account_id"])
        now = self._measure(fresh)
        tolerance = int(c["outcome"].get("reopen_if_gaps_above") or 0)
        c.setdefault("rechecks", []).append({"at": self.now().isoformat(), "by": actor, "gaps": now["gaps"], "verdict": now["verdict"], "tolerance": tolerance})
        days = c["outcome"].get("recheck_after_days")
        if now["gaps"] <= tolerance:
            c["recheck_due"] = self._due_from(days)
            note = "Still fully supported." if now["gaps"] == 0 else f"{now['gaps']} gap(s), within the agreed tolerance of {tolerance}."
            self._stamp(c, actor, "RECHECKED", note)
            self.log("EVIDENCE_REVIEW_RECHECKED", actor, case_id, org, f"{c['ref']} gaps={now['gaps']} tolerance={tolerance}")
        else:
            reason = f"Gaps returned: {now['gaps']}, above the agreed tolerance of {tolerance} (reopen criteria: {c['outcome']['reopen_criteria']})"
            self.compliance.reopen_finding(org, c["finding_id"], actor, reason)
            self.compliance.start_review(org, c["finding_id"], actor)
            self.compliance.mark_remediation_required(org, c["finding_id"], actor, reason)
            c.update(status="REOPENED", rules_version=fresh["rules_version"], recheck_due=None, completed_by=None, completion_note=None, action=None, owner=None, due_date=None, remediation_id=None,
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
        return self._decorate(c)

    def _decorate(self, c: dict) -> dict:
        due = bool(c["status"] == "VERIFIED" and c.get("recheck_due") and c["recheck_due"] <= self.now().date().isoformat())
        return {**c, "measurements": self.measurements(c), "recheck_due_now": due}

    @staticmethod
    def measurements(c: dict) -> List[dict]:
        """Every measurement taken for this case, oldest first: the baseline, each rejected attempt, the verification and each re-check."""
        rows = [{"kind": "BASELINE", "at": c["baseline"].get("measured_at"), "gaps": c["baseline"]["gaps"], "verdict": c["baseline"]["verdict"]}]
        for a in c.get("attempts", []):
            rows.append({"kind": "REJECTED_ATTEMPT", "at": a["at"], "gaps": a["post_gaps"], "verdict": a["post"]["verdict"]})
        o = c.get("outcome")
        if o:
            rows.append({"kind": "VERIFIED", "at": o["at"], "gaps": o["post_gaps"], "verdict": o["post"]["verdict"]})
        for r in c.get("rechecks", []):
            rows.append({"kind": "RECHECK", "at": r["at"], "gaps": r["gaps"], "verdict": r["verdict"]})
        return sorted(rows, key=lambda r: r["at"] or "")

    def list_cases(self, org, status: Optional[str] = None, due_for_recheck: bool = False) -> List[dict]:
        today = self.now().date().isoformat()
        out = [c for _, c in self.store.list(KIND, org_id=org) if c.get("org") == org and (status is None or c["status"] == status)
               and (not due_for_recheck or (c["status"] == "VERIFIED" and c.get("recheck_due") and c["recheck_due"] <= today))]
        return [self._decorate(c) for c in sorted(out, key=lambda c: c["created_at"], reverse=True)]

    # ---------------------------------------------------------------- expected-record rule sets
    # An organisation's own expectations ("revenue needs an invoice or contract") are saved as numbered versions. A new version is only PROPOSED by one
    # person; a different person approves it before it applies. Cases pin the version they were measured with, so a later change never silently
    # changes an open case's before-and-after comparison.
    def _default_rule_set(self, org) -> dict:
        return {"org": org, "version": 0, "status": "ACTIVE", "source": "DEFAULT", "rules": [dict(r) for r in DEFAULT_RULES],
                "reason": "Built-in defaults. Nothing here is a legal or accounting standard.", "proposed_by": None, "proposed_at": None, "decided_by": None, "decided_at": None}

    def _rule_docs(self, org) -> List[dict]:
        return sorted((d for _, d in self.store.list(RULES_KIND, org_id=org) if d.get("org") == org), key=lambda d: d["version"])

    def active_rule_set(self, org) -> dict:
        for d in self._rule_docs(org):
            if d["status"] == "ACTIVE":
                return d
        return self._default_rule_set(org)

    def rule_set_version(self, org, version: int) -> dict:
        if version == 0:
            return self._default_rule_set(org)
        d = self.store.get(RULES_KIND, f"{org}:v{version}")
        if d is None or d.get("org") != org:
            raise ReviewNotFoundError("Rule set version not found.")
        return d

    def rule_set_overview(self, org) -> dict:
        docs = self._rule_docs(org)
        return {"active": self.active_rule_set(org), "pending": next((d for d in docs if d["status"] == "PENDING"), None),
                "history": [{k: d[k] for k in ("version", "status", "proposed_by", "proposed_at", "decided_by", "decided_at", "reason", "decision_note")} for d in reversed(docs)],
                "note": "These are expectations your organisation chose. They are not a legal or accounting standard."}

    def propose_rule_set(self, org, rules, actor, reason) -> dict:
        try:
            clean = validate_org_rules(rules)
        except ValueError as exc:
            raise EvidenceReviewError(str(exc))
        reason = _text(reason, "Reason for the change")
        docs = self._rule_docs(org)
        if any(d["status"] == "PENDING" for d in docs):
            raise ReviewStateError("A rule change is already waiting for approval. Approve or reject it first.")
        if clean == self.active_rule_set(org)["rules"]:
            raise ReviewStateError("These rules are the same as the ones in use.")
        version = (docs[-1]["version"] if docs else 0) + 1
        doc = {"org": org, "version": version, "status": "PENDING", "source": "ORGANISATION", "rules": clean, "reason": reason, "proposed_by": actor,
               "proposed_at": self.now().isoformat(), "decided_by": None, "decided_at": None, "decision_note": ""}
        self.store.put(RULES_KIND, f"{org}:v{version}", doc, org_id=org)
        self.log("EVIDENCE_RULES_PROPOSED", actor, f"v{version}", org, f"rule set v{version}: {len(clean)} rule(s)")
        return doc

    def approve_rule_set(self, org, version, actor, note="") -> dict:
        d = self._pending_rule_set(org, version)
        if actor == d["proposed_by"]:
            raise ReviewForbiddenError("The person who proposed these rules cannot approve them. Someone else must.")
        for old in self._rule_docs(org):
            if old["status"] == "ACTIVE":
                old["status"] = "SUPERSEDED"
                self.store.put(RULES_KIND, f"{org}:v{old['version']}", old, org_id=org)
        d.update(status="ACTIVE", decided_by=actor, decided_at=self.now().isoformat(), decision_note=_text(note, "Note", required=False))
        self.store.put(RULES_KIND, f"{org}:v{version}", d, org_id=org)
        self.log("EVIDENCE_RULES_APPROVED", actor, f"v{version}", org, f"rule set v{version} now in use")
        return d

    def reject_rule_set(self, org, version, actor, reason) -> dict:
        d = self._pending_rule_set(org, version)
        d.update(status="REJECTED", decided_by=actor, decided_at=self.now().isoformat(), decision_note=_text(reason, "Reason"))
        self.store.put(RULES_KIND, f"{org}:v{version}", d, org_id=org)
        self.log("EVIDENCE_RULES_REJECTED", actor, f"v{version}", org, f"rule set v{version} rejected")
        return d

    def _pending_rule_set(self, org, version) -> dict:
        d = self.store.get(RULES_KIND, f"{org}:v{version}", for_update=True) if isinstance(version, int) and version > 0 else None
        if d is None or d.get("org") != org:
            raise ReviewNotFoundError("Rule set version not found.")
        if d["status"] != "PENDING":
            raise ReviewStateError(f"Only a rule change that is waiting can be decided (this one is {d['status']}).")
        return d
