"""
Pure Passport assembly. No database, no web framework: the API layer
fetches domain objects and hands them in as `PassportInputs`; this
module only reads them. Every figure is derived from posted ledger data,
evidence records, reconciliations, controls and the shared audit trail.

Six sections: identity, financial_history, evidence_quality, governance,
reporting, audit_trail. Each carries a `status` ("ok" | "attention" |
"incomplete") and a list of plain-English `attention` messages, so a
reader can see what is weak without reading every number.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from ..accounting.domain.enums import AccountType, JournalStatus
from ..identity.domain.permissions import JOURNAL_CREATE, JOURNAL_POST, role_has_permission

SCHEMA_VERSION = "vera-passport/1"
ZERO = Decimal("0.00")
LIST_CAP = 25

OWNER_KINDS = ("INDIVIDUAL", "COMPANY", "FUND", "GOVERNMENT", "OTHER")
RELATIONSHIPS = ("SUBSIDIARY", "ASSOCIATE", "JOINT_VENTURE", "BRANCH")

IDENTITY_FIELDS = (
    ("legal_name", "legal name"), ("registration_number", "registration number"),
    ("tax_id", "tax ID"), ("country", "country"), ("base_currency", "base currency"),
)


@dataclass
class PassportInputs:
    org_id: str
    org_name: str = ""
    profile: dict = field(default_factory=dict)
    structure: Optional[dict] = None            # None = never recorded
    standards: dict = field(default_factory=lambda: {"configured": False})
    periods: list = field(default_factory=list)
    accounts: list = field(default_factory=list)
    journals: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    reconciliations: list = field(default_factory=list)
    bank_transactions: list = field(default_factory=list)
    controls: list = field(default_factory=list)
    executions: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    close_processes: list = field(default_factory=list)
    memberships: list = field(default_factory=list)
    audit_events: list = field(default_factory=list)
    audit_total: int = 0
    user_labels: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------- helpers
def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _aware(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _money(value: Decimal) -> str:
    return str(Decimal(value).quantize(Decimal("0.01")))


def _val(x: Any) -> Any:
    """Enum -> its value; everything else unchanged."""
    return getattr(x, "value", x)


def _section(attention: List[str], has_data: bool) -> str:
    if not has_data:
        return "incomplete"
    return "attention" if attention else "ok"


def _who(inp: PassportInputs, actor: Optional[str]) -> Optional[str]:
    if not actor:
        return None
    return inp.user_labels.get(actor, actor)


def _pct(part: int, whole: int) -> Optional[float]:
    return round(part * 100.0 / whole, 1) if whole else None


def _periods_sorted(periods: Iterable) -> list:
    return sorted(periods, key=lambda p: (p.start_date, p.end_date))


# --------------------------------------------------------------- identity
def build_identity(inp: PassportInputs) -> dict:
    p = inp.profile or {}
    s = inp.structure or {}
    owners = list(s.get("owners") or [])
    subs = list(s.get("subsidiaries") or [])
    attention: List[str] = []

    def _has(key: str) -> bool:
        if key == "legal_name":
            return bool(p.get(key) or inp.org_name)
        return bool(p.get(key))

    missing = [label for key, label in IDENTITY_FIELDS if not _has(key)]
    if missing:
        attention.append("Organisation profile is missing: " + ", ".join(missing) + ".")
    owner_total = sum((Decimal(str(o["ownership_percent"])) for o in owners
                       if o.get("ownership_percent") is not None), Decimal("0"))
    if inp.structure is None:
        attention.append("Ownership and subsidiaries have not been recorded yet.")
    else:
        if not owners:
            attention.append("No owners recorded.")
        if owner_total > 100:
            attention.append(f"Recorded ownership adds up to {owner_total}%, which is more than 100%.")
        elif owners and owner_total < 100 and all(o.get("ownership_percent") is not None for o in owners):
            attention.append(f"Recorded ownership adds up to {owner_total}%, not 100%.")

    periods = [{
        "id": pr.id, "name": pr.name, "start_date": _iso(pr.start_date), "end_date": _iso(pr.end_date),
        "status": _val(pr.status),
    } for pr in _periods_sorted(inp.periods)]

    return {
        "status": _section(attention, True),
        "attention": attention,
        "legal_entity": {
            "legal_name": p.get("legal_name") or inp.org_name or None,
            "trading_name": p.get("trading_name"),
            "registration_number": p.get("registration_number"),
            "tax_id": p.get("tax_id"),
            "organisation_type": p.get("organisation_type"),
            "industry": p.get("industry"),
            "country": p.get("country"),
            "address": p.get("address"),
            "base_currency": p.get("base_currency"),
            "fiscal_year_start_month": p.get("fiscal_year_start_month"),
            "website": p.get("website"),
        },
        "ownership": {
            "recorded": inp.structure is not None,
            "owners": owners,
            "total_percent": str(owner_total) if owners else None,
            "updated_at": _iso(s.get("updated_at")),
            "updated_by": _who(inp, s.get("updated_by")),
        },
        "subsidiaries": {"recorded": inp.structure is not None, "items": subs, "count": len(subs)},
        "reporting_periods": periods,
    }


# ------------------------------------------------------ financial history
def _posted(journals: Iterable) -> list:
    return [j for j in journals if j.status != JournalStatus.DRAFT]


def build_financial_history(inp: PassportInputs) -> dict:
    accounts = {a.id: a for a in inp.accounts}
    posted = _posted(inp.journals)
    attention: List[str] = []

    by_period: Dict[str, dict] = {}

    def bucket(pid: str) -> dict:
        return by_period.setdefault(pid, {
            "revenue": ZERO, "expenses": ZERO, "assets": ZERO, "liabilities": ZERO, "equity": ZERO,
            "debits": ZERO, "credits": ZERO, "journals": 0,
        })

    currencies = set()
    for j in posted:
        b = bucket(j.period_id)
        b["journals"] += 1
        currencies.add(j.currency)
        for line in j.lines:
            acct = accounts.get(line.account_id)
            b["debits"] += line.debit_amount
            b["credits"] += line.credit_amount
            if acct is None:
                continue
            net_dr = line.debit_amount - line.credit_amount
            t = acct.type
            if t == AccountType.REVENUE:
                b["revenue"] -= net_dr
            elif t == AccountType.EXPENSE:
                b["expenses"] += net_dr
            elif t == AccountType.ASSET:
                b["assets"] += net_dr
            elif t == AccountType.LIABILITY:
                b["liabilities"] -= net_dr
            elif t == AccountType.EQUITY:
                b["equity"] -= net_dr

    rows = []
    tot = {k: ZERO for k in ("revenue", "expenses", "assets", "liabilities", "equity")}
    for pr in _periods_sorted(inp.periods):
        b = by_period.get(pr.id)
        if b is None:
            rows.append({"period_id": pr.id, "period_name": pr.name, "status": _val(pr.status),
                         "journal_count": 0, "has_activity": False})
            continue
        net = b["revenue"] - b["expenses"]
        balanced = b["debits"].quantize(Decimal("0.01")) == b["credits"].quantize(Decimal("0.01"))
        if not balanced:
            attention.append(f"Period {pr.name} does not balance (debits differ from credits).")
        for k in tot:
            tot[k] += b[k]
        rows.append({
            "period_id": pr.id, "period_name": pr.name, "status": _val(pr.status), "has_activity": True,
            "journal_count": b["journals"],
            "revenue": _money(b["revenue"]), "expenses": _money(b["expenses"]), "net_income": _money(net),
            "profit_margin_percent": (round(float(net) * 100.0 / float(b["revenue"]), 1)
                                      if b["revenue"] > 0 else None),
            "assets": _money(b["assets"]), "liabilities": _money(b["liabilities"]),
            "equity": _money(b["equity"]), "is_balanced": balanced,
        })
    unknown_periods = set(by_period) - {p.id for p in inp.periods}
    if unknown_periods:
        attention.append("Some journals belong to a period that no longer exists.")

    net_total = tot["revenue"] - tot["expenses"]
    totals = {
        "revenue": _money(tot["revenue"]), "expenses": _money(tot["expenses"]),
        "net_income": _money(net_total),
        "profit_margin_percent": (round(float(net_total) * 100.0 / float(tot["revenue"]), 1)
                                  if tot["revenue"] > 0 else None),
        "assets": _money(tot["assets"]), "liabilities": _money(tot["liabilities"]),
        "equity": _money(tot["equity"]),
        "profitability": ("profit" if net_total > 0 else "loss" if net_total < 0 else "break-even")
                         if by_period else None,
    }

    cash = _cash_flows(inp, accounts, posted)

    currency_list = sorted(c for c in currencies if c)
    base = (inp.profile or {}).get("base_currency")
    if len(currency_list) > 1:
        attention.append("Journals use more than one currency (" + ", ".join(currency_list)
                         + "); totals add the numbers without conversion.")
    elif base and currency_list and currency_list[0] != base:
        attention.append(f"Journals are in {currency_list[0]} but the profile base currency is {base}.")
    if not posted:
        attention.append("No posted journals yet, so there is no financial history to show.")

    return {
        "status": _section(attention, bool(posted)),
        "attention": attention,
        "currency": base or (currency_list[0] if len(currency_list) == 1 else None),
        "currencies_seen": currency_list,
        "periods": rows,
        "totals": totals,
        "totals_note": "Totals add every posted period. Assets, liabilities and equity are the sum of "
                       "period movements, which equals the closing position when the ledger starts empty.",
        "cash_flows": cash,
    }


def _cash_flows(inp: PassportInputs, accounts: dict, posted: list) -> dict:
    """Net movement on the accounts that have been bank-reconciled. This is NOT
    a statement of cash flows (operating/investing/financing): ASAVEXA does not
    classify cash flows, and the response says so."""
    cash_ids = {r.bank_account_id for r in inp.reconciliations} | {t.bank_account_id for t in inp.bank_transactions}
    cash_ids = {a for a in cash_ids if a in accounts}
    base = {
        "statement_available": False,
        "note": "ASAVEXA does not yet produce a classified cash-flow statement (operating, investing, "
                "financing). Below is the movement on bank accounts that have been reconciled.",
    }
    if not cash_ids:
        return {**base, "available": False,
                "reason": "No bank account has been reconciled yet, so ASAVEXA cannot tell which accounts hold cash."}
    per: Dict[str, dict] = {}
    for j in posted:
        for line in j.lines:
            if line.account_id in cash_ids:
                b = per.setdefault(j.period_id, {"inflow": ZERO, "outflow": ZERO})
                b["inflow"] += line.debit_amount
                b["outflow"] += line.credit_amount
    rows, ti, to = [], ZERO, ZERO
    for pr in _periods_sorted(inp.periods):
        b = per.get(pr.id)
        if b is None:
            continue
        ti += b["inflow"]
        to += b["outflow"]
        rows.append({"period_id": pr.id, "period_name": pr.name, "inflow": _money(b["inflow"]),
                     "outflow": _money(b["outflow"]), "net": _money(b["inflow"] - b["outflow"])})
    return {
        **base, "available": True,
        "accounts": [{"id": a, "code": accounts[a].code, "name": accounts[a].name} for a in sorted(cash_ids)],
        "periods": rows,
        "totals": {"inflow": _money(ti), "outflow": _money(to), "net": _money(ti - to)},
    }


# -------------------------------------------------------- evidence quality
def _best_evidence(candidates: list):
    if not candidates:
        return None
    for c in candidates:
        if _val(c.status) == "VERIFIED":
            return c
    return candidates[0]


def evidence_for_journal(j, by_journal: dict, by_id: dict, by_tx: dict):
    cands = list(by_journal.get(j.id, []))
    if j.evidence_ref and j.evidence_ref in by_id:
        cands.append(by_id[j.evidence_ref])
    if j.transaction_ref:
        cands.extend(by_tx.get(j.transaction_ref, []))
    return _best_evidence(cands)


def build_evidence_quality(inp: PassportInputs) -> dict:
    by_journal: Dict[str, list] = {}
    by_tx: Dict[str, list] = {}
    by_id = {e.id: e for e in inp.evidence}
    for e in inp.evidence:
        if e.linked_journal_id:
            by_journal.setdefault(e.linked_journal_id, []).append(e)
        if e.linked_transaction_ref:
            by_tx.setdefault(e.linked_transaction_ref, []).append(e)

    posted = sorted(_posted(inp.journals), key=lambda j: (j.date, j.journal_number))
    verified = unverified = problem = 0
    missing_rows, problem_rows = [], []
    for j in posted:
        rec = evidence_for_journal(j, by_journal, by_id, by_tx)
        row = {"journal_id": j.id, "journal_number": j.journal_number, "date": _iso(j.date),
               "description": j.description, "amount": _money(j.total_debits()), "currency": j.currency}
        if rec is None:
            missing_rows.append(row)
        elif _val(rec.status) == "VERIFIED":
            verified += 1
        elif _val(rec.status) == "UPLOADED":
            unverified += 1
        else:
            problem += 1
            problem_rows.append({**row, "evidence_status": _val(rec.status)})
    total = len(posted)
    missing = len(missing_rows)

    txs = inp.bank_transactions
    by_status: Dict[str, int] = {}
    for t in txs:
        by_status[_val(t.status)] = by_status.get(_val(t.status), 0) + 1
    unreconciled = [t for t in txs if _val(t.status) != "RECONCILED"]
    unrec_rows = [{
        "id": t.id, "date": _iso(t.transaction_date), "description": t.description,
        "amount": _money(t.debit_amount if t.debit_amount else t.credit_amount),
        "direction": "debit" if t.debit_amount else "credit", "status": _val(t.status),
        "currency": t.currency,
    } for t in sorted(unreconciled, key=lambda t: (t.transaction_date, t.id))[:LIST_CAP]]

    recon_status: Dict[str, int] = {}
    for r in inp.reconciliations:
        recon_status[_val(r.status)] = recon_status.get(_val(r.status), 0) + 1

    exceptions = []
    for t in unreconciled:
        if _val(t.status) in ("UNMATCHED", "REVIEW_REQUIRED", "REJECTED"):
            exceptions.append({
                "kind": "BANK_TRANSACTION_" + _val(t.status), "reference": t.id,
                "detail": f"{t.description} ({_val(t.status).replace('_', ' ').lower()})",
                "date": _iso(t.transaction_date),
            })
    for e in inp.evidence:
        if _val(e.status) in ("REJECTED", "CONFLICTING", "DUPLICATE", "EXPIRED", "INCOMPLETE"):
            exceptions.append({
                "kind": "EVIDENCE_" + _val(e.status), "reference": e.id,
                "detail": f"{e.original_filename} is {_val(e.status).lower()}",
                "date": _iso(e.uploaded_at),
            })
    for row in problem_rows:
        exceptions.append({
            "kind": "JOURNAL_EVIDENCE_" + row["evidence_status"], "reference": row["journal_id"],
            "detail": f"Journal {row['journal_number']} is supported only by {row['evidence_status'].lower()} evidence",
            "date": row["date"],
        })

    attention: List[str] = []
    if total == 0:
        pass
    else:
        if missing:
            attention.append(f"{missing} posted journal(s) have no evidence attached.")
        if unverified:
            attention.append(f"{unverified} journal(s) have evidence that has not been verified.")
        if problem:
            attention.append(f"{problem} journal(s) rely on rejected or defective evidence.")
    if unreconciled:
        attention.append(f"{len(unreconciled)} bank transaction(s) are not reconciled.")
    if exceptions:
        attention.append(f"{len(exceptions)} exception(s) need attention.")

    return {
        "status": _section(attention, total > 0 or bool(txs) or bool(inp.evidence)),
        "attention": attention,
        "transactions": {
            "total_posted": total, "supported_verified": verified, "evidence_unverified": unverified,
            "evidence_defective": problem, "missing_evidence": missing,
            "supported_percent": _pct(verified, total), "with_any_evidence_percent": _pct(total - missing, total),
        },
        "missing_evidence": {"count": missing, "items": missing_rows[:LIST_CAP], "truncated": missing > LIST_CAP},
        "bank_reconciliation": {
            "bank_transactions": len(txs), "reconciled": by_status.get("RECONCILED", 0),
            "unreconciled": len(unreconciled), "by_status": by_status,
            "reconciliations_by_status": recon_status,
            "unreconciled_items": unrec_rows, "truncated": len(unreconciled) > LIST_CAP,
        },
        "exceptions": {"count": len(exceptions), "items": exceptions[:LIST_CAP], "truncated": len(exceptions) > LIST_CAP},
        "evidence_records": len(inp.evidence),
    }


# -------------------------------------------------------------- governance
APPROVAL_MARKERS = ("APPROVED", "VERIFIED", "REVIEWED")
APPROVAL_EXACT = ("JOURNAL_POSTED", "PERIOD_LOCKED")


def is_approval_action(action: str) -> bool:
    return action in APPROVAL_EXACT or any(m in action for m in APPROVAL_MARKERS)


def _sod_check(key, label, rule, pairs):
    """pairs: iterable of (reference, maker, checker). A check is 'tested' on
    every pair that has both people recorded."""
    tested = [(ref, a, b) for ref, a, b in pairs if a and b]
    violations = [(ref, a) for ref, a, b in tested if a == b]
    return {
        "key": key, "label": label, "rule": rule, "tested": len(tested), "violations": len(violations),
        "status": "not_tested" if not tested else ("fail" if violations else "pass"),
        "_examples": violations[:10],
    }


def build_governance(inp: PassportInputs) -> dict:
    attention: List[str] = []
    posted = _posted(inp.journals)
    approved_recs = [r for r in inp.reconciliations if getattr(r, "approved_by", None)]

    checks = [
        _sod_check("journal_post", "Journals: creator is not the poster",
                   "The person who drafted a journal must not be the person who posted it.",
                   [(j.journal_number, j.created_by, j.posted_by) for j in posted]),
        _sod_check("evidence_verify", "Evidence: uploader is not the verifier",
                   "The person who uploaded evidence must not be the person who verified it.",
                   [(e.original_filename, e.uploaded_by, e.verified_by) for e in inp.evidence if e.verified_by]),
        _sod_check("reconciliation_approve", "Reconciliations: preparer is not the approver",
                   "The person who prepared a reconciliation must not approve it.",
                   [(r.name, r.created_by, r.approved_by) for r in approved_recs]),
        _sod_check("reconciliation_submit", "Reconciliations: submitter is not the approver",
                   "The person who submitted a reconciliation must not approve it.",
                   [(r.name, r.submitted_by, r.approved_by) for r in approved_recs]),
        _sod_check("period_close", "Period close: requester is not the approver",
                   "The person who requested a period close must not approve it.",
                   [(c.period_id, c.requested_by, c.approved_by) for c in inp.close_processes if c.approved_by]),
        _sod_check("control_review", "Controls: executor is not the reviewer",
                   "The person who ran a control must not be the one who reviews the result.",
                   [(x.id, x.executed_by, x.reviewed_by) for x in inp.executions if x.reviewed_by]),
    ]
    for c in checks:
        c["examples"] = [{"reference": str(ref), "person": _who(inp, who)} for ref, who in c.pop("_examples")]
        if c["status"] == "fail":
            attention.append(f"Segregation of duties: {c['label']} — {c['violations']} case(s) where one person did both.")
    sod_status = ("fail" if any(c["status"] == "fail" for c in checks)
                  else "not_tested" if all(c["status"] == "not_tested" for c in checks) else "pass")

    conflicts = []
    for m in inp.memberships:
        if _val(m.status) != "ACTIVE":
            continue
        role = m.role
        if role_has_permission(role, JOURNAL_CREATE) and role_has_permission(role, JOURNAL_POST):
            conflicts.append({"person": _who(inp, m.user_id), "role": _val(role),
                              "conflict": "Can both create and post journals"})
    if conflicts:
        attention.append(f"{len(conflicts)} active member(s) hold a role that can both create and post journals.")

    # approvals, from the audit trail
    approvals = [e for e in inp.audit_events if is_approval_action(e.action)]
    counts: Dict[str, int] = {}
    for e in approvals:
        counts[e.action] = counts.get(e.action, 0) + 1
    recent = sorted(approvals, key=lambda e: _aware(e.timestamp), reverse=True)[:LIST_CAP]
    approvals_out = {
        "count": len(approvals), "by_action": counts,
        "recent": [{"when": _iso(e.timestamp), "who": _who(inp, e.actor), "action": e.action,
                    "entity_type": e.entity_type, "entity_id": e.entity_id} for e in recent],
    }

    # controls
    active = [c for c in inp.controls if c.is_active]
    last_by_control: Dict[str, Any] = {}
    for x in sorted(inp.executions, key=lambda x: _aware(x.executed_at)):
        last_by_control[x.control_id] = x
    result_counts: Dict[str, int] = {}
    for x in last_by_control.values():
        result_counts[_val(x.result)] = result_counts.get(_val(x.result), 0) + 1
    never_run = [c for c in active if c.id not in last_by_control]
    controls_out = {
        "defined": len(inp.controls), "active": len(active), "executions": len(inp.executions),
        "latest_result_by_control": result_counts, "never_executed": len(never_run),
        "last_executed_at": _iso(max((x.executed_at for x in inp.executions), key=_aware)) if inp.executions else None,
    }
    if not inp.controls:
        attention.append("No controls are defined.")
    elif never_run:
        attention.append(f"{len(never_run)} active control(s) have never been executed.")

    ctl_by_id = {c.id: c for c in inp.controls}
    exc_items = []
    for cid, x in last_by_control.items():
        if _val(x.result) in ("FAIL", "WARNING", "REQUIRES_REVIEW"):
            c = ctl_by_id.get(cid)
            exc_items.append({
                "kind": "CONTROL_" + _val(x.result), "control": c.code if c else cid,
                "name": c.name if c else None, "severity": _val(c.severity) if c else None,
                "detail": x.explanation, "when": _iso(x.executed_at),
            })
    open_findings = [f for f in inp.findings if _val(f.status) not in ("VERIFIED", "CLOSED")]
    for f in open_findings:
        c = ctl_by_id.get(f.control_id)
        exc_items.append({
            "kind": "FINDING_" + _val(f.status), "control": c.code if c else f.control_id,
            "name": c.name if c else None, "severity": _val(f.severity), "detail": f.description,
            "when": _iso(f.created_at),
        })
    if exc_items:
        attention.append(f"{len(exc_items)} control exception(s): failing controls or unresolved findings.")

    has_data = bool(inp.controls or inp.audit_events or posted or inp.memberships)
    return {
        "status": _section(attention, has_data),
        "attention": attention,
        "approvals": approvals_out,
        "controls": controls_out,
        "segregation_of_duties": {
            "status": sod_status, "checks": checks, "role_conflicts": conflicts,
            "note": "A violation is a recorded fact: the same person appears as both maker and checker. "
                    "In a one-person organisation this is expected, and it is still reported.",
        },
        "control_exceptions": {
            "count": len(exc_items), "items": exc_items[:LIST_CAP], "truncated": len(exc_items) > LIST_CAP,
            "findings_total": len(inp.findings), "findings_open": len(open_findings),
        },
    }


# --------------------------------------------------------------- reporting
def build_reporting(inp: PassportInputs) -> dict:
    p = inp.profile or {}
    st = inp.standards or {"configured": False}
    configured = bool(st.get("configured"))
    chain = {c["step"]: c["value"] for c in (st.get("chain") or [])}
    attention: List[str] = []
    framework = st.get("framework") if configured else p.get("reporting_framework")
    if not configured:
        attention.append("No standards configuration has been saved (Standards & Policies page).")
    if not framework:
        attention.append("No applicable reporting framework is set.")
    jurisdiction = chain.get("Jurisdiction") or p.get("country")
    if not jurisdiction:
        attention.append("No reporting jurisdiction is set.")
    readiness = st.get("readiness") if configured else None
    if readiness and readiness.get("missing"):
        attention.append("ASAVEXA cannot yet produce: " + "; ".join(readiness["missing"]) + ".")
    return {
        "status": _section(attention, configured or bool(framework) or bool(jurisdiction)),
        "attention": attention,
        "configured": configured,
        "framework": framework,
        "framework_name": chain.get("Reporting framework"),
        "jurisdiction": jurisdiction,
        "jurisdiction_code": st.get("jurisdiction") if configured else None,
        "entity_type": chain.get("Entity type"),
        "fiscal_year_start_month": p.get("fiscal_year_start_month"),
        "base_currency": p.get("base_currency"),
        "readiness": readiness,
        "reporting_periods": [{
            "id": pr.id, "name": pr.name, "start_date": _iso(pr.start_date), "end_date": _iso(pr.end_date),
            "status": _val(pr.status),
        } for pr in _periods_sorted(inp.periods)],
        "disclaimer": st.get("disclaimer"),
    }


# ------------------------------------------------------------- audit trail
_CREATED = ("_CREATED", "_DRAFTED", "_OPENED", "_UPLOADED", "_DEFINED", "_IMPORTED", "_REQUESTED", "_EXECUTED")
_APPROVED = ("APPROVED", "VERIFIED", "REVIEWED", "_POSTED", "_CLOSED")
_CHANGED = ("UPDATED", "CHANGED", "DELETED", "REVERSED", "LOCKED", "DEACTIVATED", "REOPENED", "REJECTED",
            "STARTED", "COMPLETED", "MATCHED", "SUBMITTED", "SENT_BACK", "RESOLVED")


def classify_action(action: str) -> str:
    if any(m in action for m in _APPROVED):
        return "approved"
    if any(action.endswith(s) for s in _CREATED):
        return "created"
    if any(m in action for m in _CHANGED):
        return "changed"
    return "other"


def build_audit_trail(inp: PassportInputs) -> dict:
    events = sorted(inp.audit_events, key=lambda e: _aware(e.timestamp))
    attention: List[str] = []
    actors: Dict[str, dict] = {}
    cats = {"created": 0, "changed": 0, "approved": 0, "other": 0}
    for e in events:
        cat = classify_action(e.action)
        cats[cat] += 1
        a = actors.setdefault(e.actor, {"created": 0, "changed": 0, "approved": 0, "other": 0,
                                        "first_at": e.timestamp, "last_at": e.timestamp})
        a[cat] += 1
        a["last_at"] = e.timestamp
    by_actor = sorted((
        {"who": _who(inp, k), "created": v["created"], "changed": v["changed"], "approved": v["approved"],
         "other": v["other"], "total": v["created"] + v["changed"] + v["approved"] + v["other"],
         "first_at": _iso(v["first_at"]), "last_at": _iso(v["last_at"])}
        for k, v in actors.items()), key=lambda r: -r["total"])

    recent = [{
        "when": _iso(e.timestamp), "who": _who(inp, e.actor), "action": e.action,
        "category": classify_action(e.action), "entity_type": e.entity_type, "entity_id": e.entity_id,
        "reason": e.reason,
    } for e in reversed(events[-50:])]

    journals = sorted(_posted(inp.journals) + [j for j in inp.journals if j.status == JournalStatus.DRAFT],
                      key=lambda j: _aware(j.created_at), reverse=True)[:LIST_CAP]
    provenance = [{
        "journal_id": j.id, "journal_number": j.journal_number, "status": _val(j.status),
        "created_by": _who(inp, j.created_by), "created_at": _iso(j.created_at),
        "posted_by": _who(inp, j.posted_by), "posted_at": _iso(j.posted_at),
    } for j in journals]
    locks = [{"period": pr.name, "locked_by": _who(inp, pr.locked_by), "locked_at": _iso(pr.locked_at)}
             for pr in _periods_sorted(inp.periods) if pr.locked_at]

    truncated = inp.audit_total > len(inp.audit_events)
    if truncated:
        attention.append(f"Only the most recent {len(inp.audit_events)} of {inp.audit_total} audit events were analysed.")
    return {
        "status": _section(attention, bool(events)),
        "attention": attention,
        "total_events": inp.audit_total or len(events),
        "events_analysed": len(events),
        "truncated": truncated,
        "first_event_at": _iso(events[0].timestamp) if events else None,
        "last_event_at": _iso(events[-1].timestamp) if events else None,
        "by_category": cats,
        "by_person": by_actor[:50],
        "recent_events": recent,
        "journal_provenance": provenance,
        "period_locks": locks,
    }


# ------------------------------------------------------------------ whole
def fingerprint(sections: dict) -> str:
    blob = json.dumps(sections, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_passport(inp: PassportInputs, generated_by_label: Optional[str], now: datetime) -> dict:
    sections = {
        "identity": build_identity(inp),
        "financial_history": build_financial_history(inp),
        "evidence_quality": build_evidence_quality(inp),
        "governance": build_governance(inp),
        "reporting": build_reporting(inp),
        "audit_trail": build_audit_trail(inp),
    }
    statuses = {k: v["status"] for k, v in sections.items()}
    return {
        "schema_version": SCHEMA_VERSION,
        "org_id": inp.org_id,
        "generated_at": _iso(now),
        "generated_by": generated_by_label,
        "fingerprint": fingerprint(sections),
        "fingerprint_note": "SHA-256 of the six sections. It changes whenever any underlying record changes, "
                            "so two copies with the same fingerprint show the same data.",
        "summary": {
            "sections": statuses,
            "attention_count": sum(len(v["attention"]) for v in sections.values()),
            "complete_sections": sum(1 for s in statuses.values() if s == "ok"),
        },
        **sections,
    }
