"""What records a figure is EXPECTED to have, as plain data. Nothing here is a legal or accounting standard: these are
sensible defaults an organisation can replace by passing its own rules to the review. The review reports each rule it applied.

A rule applies to a posted journal when it touches an account of one of `account_types` (or any journal if that is None).
`expects_any` lists the evidence types of which at least one should be attached (None means any attached document will do).
Every rule needs the attached evidence to be VERIFIED, by a different person from the one who uploaded it."""
import re
from typing import Dict, List

DEFAULT_RULES: List[Dict] = [
    {"id": "ER-001", "name": "Every posted journal has linked evidence", "account_types": None, "expects_any": None, "severity": "HIGH"},
    {"id": "ER-002", "name": "Revenue is supported by an invoice or a contract", "account_types": ["REVENUE"],
     "expects_any": ["INVOICE", "CONTRACT"], "severity": "HIGH"},
    {"id": "ER-003", "name": "Expenses are supported by an invoice, a receipt or payroll evidence", "account_types": ["EXPENSE"],
     "expects_any": ["INVOICE", "RECEIPT", "PAYROLL_EVIDENCE", "CONTRACT"], "severity": "MEDIUM"},
]

EVIDENCE_TYPES = ("INVOICE", "RECEIPT", "CONTRACT", "BANK_STATEMENT", "PURCHASE_ORDER", "DELIVERY_NOTE", "PAYROLL_EVIDENCE",
                  "TAX_DOCUMENT", "APPROVAL_RECORD", "OTHER")
ACCOUNT_TYPES = ("ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE")


def validate_rules(rules):
    """Returns the rules as a clean list, or raises ValueError saying exactly what is wrong."""
    if not isinstance(rules, list) or not rules:
        raise ValueError("rules must be a non-empty list")
    out, seen = [], set()
    for r in rules:
        if not isinstance(r, dict):
            raise ValueError("each rule must be an object")
        rid = str(r.get("id") or "").strip()
        if not rid or rid in seen:
            raise ValueError(f"rule id {rid!r} is missing or repeated")
        seen.add(rid)
        types = r.get("account_types")
        if types is not None and (not isinstance(types, list) or any(t not in ACCOUNT_TYPES for t in types)):
            raise ValueError(f"{rid}: account_types must be a list drawn from {', '.join(ACCOUNT_TYPES)}")
        exp = r.get("expects_any")
        if exp is not None and (not isinstance(exp, list) or not exp or any(t not in EVIDENCE_TYPES for t in exp)):
            raise ValueError(f"{rid}: expects_any must be a non-empty list drawn from the evidence types")
        sev = r.get("severity", "MEDIUM")
        if sev not in ("HIGH", "MEDIUM", "LOW"):
            raise ValueError(f"{rid}: severity must be HIGH, MEDIUM or LOW")
        out.append({"id": rid, "name": str(r.get("name") or rid)[:200], "account_types": types, "expects_any": exp, "severity": sev})
    return out


MAX_RULES = 25
BASELINE_RULE = "ER-001"


def validate_org_rules(rules):
    """The stricter check for a rule set an organisation saves. Same shape rules as `validate_rules`, plus: at most 25 rules, simple ids, and the
    baseline rule ER-001 ("every posted journal has linked evidence") must stay and must still apply to every journal. An organisation can add
    rules and make any rule stricter, but cannot switch the baseline off, because then 'fully supported' would stop meaning anything."""
    out = validate_rules(rules)
    if len(out) > MAX_RULES:
        raise ValueError(f"a rule set can have at most {MAX_RULES} rules")
    for r in out:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,30}", r["id"]):
            raise ValueError(f"rule id {r['id']!r} must be 1 to 30 letters, numbers, dashes or underscores")
    base = next((r for r in out if r["id"] == BASELINE_RULE), None)
    if base is None or base["account_types"] is not None:
        raise ValueError(f"The baseline rule {BASELINE_RULE} (every posted journal has linked evidence) must stay, and it must apply to every journal.")
    return out
