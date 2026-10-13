"""Evidence Review: for one reported figure (or a whole report), what is asserted, what supports it, what is expected but missing,
what conflicts or is stale, which links are recorded and which are only inferred, what is uncertain, and what to do next.

Read-only and deterministic: it reads the ledger and the Evidence Vault and writes nothing, and the same records always give the same
`fingerprint`. It says whether the *records* support the figure. It does not say the figure is right, and it does not judge whether
a document is the correct document: that is a human verification step in the Evidence Vault."""
import hashlib
import json
from decimal import Decimal
from typing import Dict, List, Optional

from ..proofgraph.graph import MAX_JOURNAL_NODES, REPORT_TYPES, UnknownReportError, _lines_of, _money
from ..reporting.domain import rules as reporting_rules
from .errors import EvidenceReviewError
from .rules import DEFAULT_RULES, validate_rules

SUPPORTED, PARTLY, NOT_SUPPORTED, CONTRADICTED, NOTHING = "SUPPORTED", "PARTLY_SUPPORTED", "NOT_SUPPORTED", "CONTRADICTED", "NOTHING_TO_REVIEW"
GAP_KINDS = ("MISSING", "UNVERIFIED", "CONFLICT", "STALE", "WRONG_TYPE", "SELF_VERIFIED", "DOCUMENT_REUSED")
CONFLICT_STATUSES = ("CONFLICTING", "DUPLICATE", "REJECTED", "INCOMPLETE")
ACTION_TEXT = {
    "MISSING": "Attach supporting evidence to this journal, then have someone else verify it.",
    "UNVERIFIED": "Have a second person verify the attached evidence in the Evidence Vault.",
    "CONFLICT": "Resolve the problem with the attached evidence (replace it or correct its record), then verify it.",
    "STALE": "The evidence has expired; obtain a current document and verify it.",
    "WRONG_TYPE": "The attached document is not the kind this rule expects; attach the expected kind.",
    "SELF_VERIFIED": "The person who uploaded this evidence also verified it; have a different person verify it.",
    "DOCUMENT_REUSED": "The same file supports more than one journal; confirm that is right or attach the correct document to each.",
}
LIMITS = ("This shows whether the records support the figure: that each journal behind it has evidence, that the evidence is verified and of the expected kind, "
          "and that nothing conflicts. It does not prove the figure is correct and does not judge whether a document is the right one; "
          "a person must verify that in the Evidence Vault.")


def _applicable(rule, types) -> bool:
    return rule["account_types"] is None or bool(set(rule["account_types"]) & set(types))


def build_review(reporting, org_id: str, period_id: str, report_type: str, actor: str, account_id: Optional[str] = None,
                 rules: Optional[List[dict]] = None, vault=None) -> dict:
    if report_type not in REPORT_TYPES:
        raise UnknownReportError(f"report must be one of {', '.join(REPORT_TYPES)}")
    try:
        rule_set = validate_rules(rules) if rules is not None else [dict(r) for r in DEFAULT_RULES]
    except ValueError as exc:
        raise EvidenceReviewError(str(exc))
    report = reporting.get_balance_sheet(org_id, period_id, actor) if report_type == "balance_sheet" else reporting.get_income_statement(org_id, period_id, actor)
    if vault is None:
        vault = getattr(reporting, "evidence", None)
    accounts = {a.id: a for a in reporting.accounting.accounts.list_for_org(org_id)}

    scope_lines = []
    for section, lines in _lines_of(report, report_type):
        for line in lines:
            if account_id is None or line.account_id == account_id:
                scope_lines.append((section, line))
    if account_id is not None and not scope_lines:
        raise EvidenceReviewError("That account has no figure in this report and period.")

    journals: Dict[str, dict] = {}
    tie_failures, truncated, figure_total = [], False, Decimal("0.00")
    for section, line in scope_lines:
        account = accounts.get(line.account_id)
        a_type = getattr(account.type, "value", account.type) if account else str(line.account_type)
        entries = reporting.trace_line(org_id, line.account_id, period_id=period_id)
        debit = sum((Decimal(e["debit"]) for e in entries), Decimal("0.00"))
        credit = sum((Decimal(e["credit"]) for e in entries), Decimal("0.00"))
        rebuilt = reporting_rules.normal_balance_amount(account.type if account else line.account_type, debit, credit)
        if _money(rebuilt) != _money(line.amount):
            tie_failures.append({"account": f"{line.account_code} {line.account_name}", "reported": _money(line.amount), "ledger": _money(rebuilt)})
        figure_total += Decimal(line.amount)
        for e in entries:
            jid = e["journal_id"]
            if jid not in journals:
                if len(journals) >= MAX_JOURNAL_NODES:
                    truncated = True
                    continue
                journals[jid] = {"journal_id": jid, "journal_number": e.get("journal_number") or jid, "date": str(e.get("date")),
                                 "description": e.get("description") or "", "transaction_ref": e.get("transaction_ref"),
                                 "account_types": set(), "accounts": set(), "debit": Decimal("0.00"), "credit": Decimal("0.00")}
            j = journals[jid]
            j["account_types"].add(a_type); j["accounts"].add(f"{line.account_code} {line.account_name}")
            j["debit"] += Decimal(e["debit"]); j["credit"] += Decimal(e["credit"])

    records: Dict[str, object] = {}
    hash_users: Dict[str, set] = {}
    for jid, j in journals.items():
        rec = vault.find_record_for_reference(org_id, journal_id=jid, transaction_ref=j["transaction_ref"]) if vault is not None else None
        records[jid] = rec
        if rec is not None:
            hash_users.setdefault(rec.file_hash, set()).add(jid)

    supporting: List[dict] = []
    issues: List[dict] = []
    recorded = inferred = 0
    for jid in sorted(journals, key=lambda k: (journals[k]["date"], journals[k]["journal_number"])):
        j, rec = journals[jid], records[jid]
        base = {"journal_id": jid, "journal_number": j["journal_number"], "date": j["date"], "description": j["description"]}
        applicable = [r for r in rule_set if _applicable(r, j["account_types"])]
        if rec is None:
            expected = sorted({t for r in applicable for t in (r["expects_any"] or [])})
            issues.append({**base, "kind": "MISSING", "rule_id": applicable[0]["id"] if applicable else None,
                           "detail": "No evidence is linked to this journal." + (f" Expected one of: {', '.join(expected)}." if expected else ""), "expected": expected})
            continue
        status = rec.status.value
        link = "RECORDED" if rec.linked_journal_id == jid else "INFERRED"
        recorded += link == "RECORDED"; inferred += link == "INFERRED"
        ev = {"id": rec.id, "filename": rec.original_filename, "type": rec.type.value, "status": status, "file_hash": rec.file_hash,
              "uploaded_by": rec.uploaded_by, "verified_by": rec.verified_by}
        supporting.append({**base, "debit": _money(j["debit"]), "credit": _money(j["credit"]), "evidence": ev,
                           "link": {"kind": link, "basis": "evidence is linked to this journal" if link == "RECORDED" else "matched only by the transaction reference; nobody linked it to the journal"}})
        if status == "UPLOADED":
            issues.append({**base, "kind": "UNVERIFIED", "rule_id": "ER-001", "evidence_id": rec.id, "detail": "The evidence is attached but nobody has verified it yet."})
        elif status in CONFLICT_STATUSES:
            issues.append({**base, "kind": "CONFLICT", "rule_id": "ER-001", "evidence_id": rec.id, "detail": f"The attached evidence is marked {status}."})
        elif status == "EXPIRED":
            issues.append({**base, "kind": "STALE", "rule_id": "ER-001", "evidence_id": rec.id, "detail": "The attached evidence has expired."})
        elif status == "VERIFIED" and rec.verified_by and rec.verified_by == rec.uploaded_by:
            issues.append({**base, "kind": "SELF_VERIFIED", "rule_id": "ER-001", "evidence_id": rec.id, "detail": "The same person uploaded and verified this evidence."})
        for r in applicable:
            if r["expects_any"] and rec.type.value not in r["expects_any"]:
                issues.append({**base, "kind": "WRONG_TYPE", "rule_id": r["id"], "evidence_id": rec.id, "expected": r["expects_any"],
                               "detail": f"{r['name']}: expected {' or '.join(r['expects_any'])}, found {rec.type.value}."})
        if len(hash_users.get(rec.file_hash, ())) > 1:
            issues.append({**base, "kind": "DOCUMENT_REUSED", "rule_id": "ER-001", "evidence_id": rec.id,
                           "detail": f"The same file supports {len(hash_users[rec.file_hash])} journals in this scope."})

    gap_journals = {i["journal_id"] for i in issues if i["kind"] in GAP_KINDS}
    counts = {k: sum(1 for i in issues if i["kind"] == k) for k in GAP_KINDS}
    total = len(journals)
    if tie_failures:
        verdict = CONTRADICTED
    elif total == 0:
        verdict = NOTHING
    elif not gap_journals and not truncated:
        verdict = SUPPORTED
    elif len(gap_journals) < total:
        verdict = PARTLY
    else:
        verdict = NOT_SUPPORTED

    uncertain: List[str] = []
    if inferred:
        uncertain.append(f"{inferred} link(s) are inferred from a transaction reference only; nobody linked the evidence to the journal.")
    if counts["UNVERIFIED"]:
        uncertain.append(f"{counts['UNVERIFIED']} journal(s) have evidence that nobody has verified yet.")
    if counts["SELF_VERIFIED"]:
        uncertain.append(f"{counts['SELF_VERIFIED']} piece(s) of evidence were verified by the person who uploaded them.")
    if truncated:
        uncertain.append(f"Only the first {MAX_JOURNAL_NODES} journals were reviewed; the result covers that part only.")
    if vault is None:
        uncertain.append("The Evidence Vault is not connected, so no evidence could be checked.")
    uncertain.append("A verified document is still not proof the figure is right; a person has judged only that the document is what it claims to be.")

    actions, seen_a = [], set()
    for i in issues:
        key = (i["journal_id"], i["kind"])
        if key in seen_a:
            continue
        seen_a.add(key)
        actions.append({"code": i["kind"], "journal_id": i["journal_id"], "journal_number": i["journal_number"], "text": ACTION_TEXT[i["kind"]]})
    for t in tie_failures:
        actions.insert(0, {"code": "TIE_FAILURE", "journal_id": None, "journal_number": None,
                           "text": f"{t['account']}: the reported figure {t['reported']} does not equal the ledger {t['ledger']}. Do not rely on it until explained."})

    metrics = {"journals": total, "journals_with_gaps": len(gap_journals), "gap_issues": sum(counts.values()), "tie_failures": len(tie_failures),
               "recorded_links": recorded, "inferred_links": inferred, **{k.lower(): v for k, v in counts.items()}}
    canon = json.dumps({"scope": [org_id, period_id, report_type, account_id], "rules": sorted(json.dumps(r, sort_keys=True) for r in rule_set),
                        "j": sorted((i["journal_id"], i["kind"], i.get("evidence_id") or "") for i in issues),
                        "s": sorted((s["journal_id"], s["evidence"]["id"], s["evidence"]["status"], s["link"]["kind"]) for s in supporting), "t": tie_failures},
                       sort_keys=True)
    label = (f"{scope_lines[0][1].account_code} {scope_lines[0][1].account_name}" if account_id else report_type.replace("_", " ").title())
    return {
        "schema": "evidence_review/1", "org_id": org_id, "period_id": period_id, "report_type": report_type, "account_id": account_id,
        "assertion": {"statement": (f"The {report_type.replace('_', ' ')} for this period shows {label} at {_money(figure_total)}." if account_id
                                    else f"The {report_type.replace('_', ' ')} for this period shows {len(scope_lines)} figure(s), traced to journals below."),
                      "figure": _money(figure_total) if account_id else None, "lines": len(scope_lines)},
        "verdict": verdict, "metrics": metrics,
        "supporting": supporting, "missing": [i for i in issues if i["kind"] in ("MISSING", "WRONG_TYPE")],
        "conflicting": [i for i in issues if i["kind"] in ("CONFLICT", "DOCUMENT_REUSED")], "stale": [i for i in issues if i["kind"] == "STALE"],
        "unverified": [i for i in issues if i["kind"] in ("UNVERIFIED", "SELF_VERIFIED")],
        "links": {"recorded": recorded, "inferred": inferred, "missing": counts["MISSING"]},
        "tie_failures": tie_failures, "uncertain": uncertain, "action_needed": actions,
        "rules": [{"id": r["id"], "name": r["name"], "severity": r["severity"], "expects_any": r["expects_any"], "account_types": r["account_types"]} for r in rule_set],
        "fingerprint": hashlib.sha256(canon.encode()).hexdigest(), "limits": LIMITS, "truncated": truncated,
    }


def gap_count(review: dict) -> int:
    """The single number outcome verification compares: journals with a problem, plus any figure that does not tie."""
    return review["metrics"]["journals_with_gaps"] + review["metrics"]["tie_failures"]
