"""Builds the Proof-to-Report Graph for one organisation and period. Read-only: it reads the ledger and the evidence vault and never writes.

Chain: REPORT -> LINE (an account's figure) -> JOURNAL (posted entries) -> EVIDENCE (the document behind the journal).
Every call recomputes from the ledger, so the graph can never drift from the books. Honest limits: it proves the figure is *traceable* and *ties to the ledger*;
it does not judge whether the attached document is the right document (that is the Evidence Vault's verify step)."""
from decimal import Decimal
from typing import Dict, List, Optional

from ..accounting.domain.enums import AccountType
from ..reporting.domain import rules as reporting_rules

REPORT_TYPES = ("balance_sheet", "income_statement")
MAX_JOURNAL_NODES = 400          # keeps the answer a usable size; the response says so when it truncates
PROVEN, PARTIAL, BROKEN, EMPTY = "PROVEN", "PARTIAL", "BROKEN", "EMPTY"
MISSING = "MISSING"


class ProofGraphError(Exception):
    status = 400


class UnknownReportError(ProofGraphError):
    status = 400


def _lines_of(report, report_type):
    if report_type == "balance_sheet":
        return [("Assets", report.asset_lines), ("Liabilities", report.liability_lines), ("Equity", report.equity_lines)]
    return [("Revenue", report.revenue_lines), ("Expenses", report.expense_lines)]


def _money(x) -> str:
    return str(Decimal(x).quantize(Decimal("0.01")))


def build_graph(reporting, org_id: str, period_id: str, report_type: str, actor: str) -> dict:
    if report_type not in REPORT_TYPES:
        raise UnknownReportError(f"report must be one of {', '.join(REPORT_TYPES)}")
    if report_type == "balance_sheet":
        report = reporting.get_balance_sheet(org_id, period_id, actor)
    else:
        report = reporting.get_income_statement(org_id, period_id, actor)
    vault = reporting.evidence
    accounts = {a.id: a for a in reporting.accounting.accounts.list_for_org(org_id)}

    nodes: List[dict] = []
    edges: List[dict] = []
    root = f"report:{report_type}"
    nodes.append({"id": root, "kind": "report", "label": report_type.replace("_", " ").title(), "period_id": period_id})
    seen: Dict[str, dict] = {}
    evidence_seen: set = set()
    journal_count = 0
    checks: List[dict] = []
    journals_total = 0
    truncated = False
    missing_journals: List[dict] = []
    unverified_journals: List[dict] = []
    tie_failures = 0
    line_count = 0

    for section, lines in _lines_of(report, report_type):
        for line in lines:
            line_count += 1
            account = accounts.get(line.account_id)
            lid = f"line:{line.account_id}"
            nodes.append({"id": lid, "kind": "line", "label": f"{line.account_code} {line.account_name}", "section": section, "amount": _money(line.amount)})
            edges.append({"from": root, "to": lid, "kind": "reports"})
            entries = reporting.trace_line(org_id, line.account_id, period_id=period_id)
            debit = sum((Decimal(e["debit"]) for e in entries), Decimal("0.00"))
            credit = sum((Decimal(e["credit"]) for e in entries), Decimal("0.00"))
            rebuilt = reporting_rules.normal_balance_amount(account.type if account else line.account_type, debit, credit)
            ties = _money(rebuilt) == _money(line.amount)
            if not ties:
                tie_failures += 1
            checks.append({"name": f"{line.account_code} ties to its journals", "ok": ties,
                           "detail": f"report {_money(line.amount)} vs ledger {_money(rebuilt)} from {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}"})
            for e in entries:
                jid = e["journal_id"]
                node_id = f"journal:{jid}"
                if node_id not in seen:
                    if journal_count >= MAX_JOURNAL_NODES:
                        truncated = True
                        continue
                    journals_total += 1
                    journal_count += 1
                    record = vault.find_record_for_reference(org_id, journal_id=jid, transaction_ref=e.get("transaction_ref")) if vault is not None else None
                    status = record.status.value if record is not None else MISSING
                    jn = {"id": node_id, "kind": "journal", "label": e.get("journal_number") or jid, "date": str(e.get("date")), "description": e.get("description") or "",
                          "evidence_status": status, "transaction_ref": e.get("transaction_ref")}
                    seen[node_id] = jn
                    nodes.append(jn)
                    if record is not None:
                        eid = f"evidence:{record.id}"
                        if eid not in evidence_seen:
                            evidence_seen.add(eid)
                            nodes.append({"id": eid, "kind": "evidence", "label": record.original_filename, "status": status, "type": record.type.value, "file_hash": record.file_hash})
                        edges.append({"from": node_id, "to": eid, "kind": "supported_by"})
                    if record is None:
                        missing_journals.append({"journal_id": jid, "journal_number": jn["label"], "description": jn["description"]})
                    elif status != "VERIFIED":
                        unverified_journals.append({"journal_id": jid, "journal_number": jn["label"], "status": status})
                edges.append({"from": lid, "to": node_id, "kind": "built_from", "debit": _money(e["debit"]), "credit": _money(e["credit"])})

    journals = [n for n in nodes if n["kind"] == "journal"]
    with_ev = sum(1 for n in journals if n["evidence_status"] != MISSING)
    verified = sum(1 for n in journals if n["evidence_status"] == "VERIFIED")
    total = len(journals)
    if tie_failures:
        state = BROKEN
    elif total == 0:
        state = EMPTY
    elif verified == total and not truncated:
        state = PROVEN
    else:
        state = PARTIAL
    if truncated:
        checks.append({"name": "graph size", "ok": False, "detail": f"Only the first {MAX_JOURNAL_NODES} journals are drawn; counts below cover the drawn part only."})
    return {
        "report_type": report_type, "period_id": period_id, "org_id": org_id, "state": state,
        "summary": {
            "lines": line_count, "journals": total, "with_evidence": with_ev, "verified": verified, "missing_evidence": total - with_ev,
            "coverage_pct": round(100 * with_ev / total, 1) if total else None, "verified_pct": round(100 * verified / total, 1) if total else None,
            "tie_failures": tie_failures, "truncated": truncated,
        },
        "nodes": nodes, "edges": edges, "checks": checks,
        "missing": missing_journals, "unverified": unverified_journals,
        "meaning": {
            PROVEN: "Every figure ties to its journals, and every journal has verified evidence.",
            PARTIAL: "Every figure ties to its journals, but some journals have no evidence or evidence that is not verified yet.",
            BROKEN: "At least one figure does not tie to its journals. Do not rely on this report until it is explained.",
            EMPTY: "There are no posted journals in this period, so there is nothing to prove yet.",
        }[state],
        "limits": "This proves traceability and that totals tie to the ledger. It does not judge whether a document is the right one; that is the verification step in the Evidence Vault.",
    }
