"""Level 8 (payroll): a payroll register (CSV/Excel export from a payroll platform) is read, CHECKED, and turned into a
PROPOSED journal. Nothing is posted and ASAVEXA does not choose accounts."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from . import model as M
from .errors import IngestionError
from .tabular import Table
from .util import AmountError, clean, money, norm_header, parse_amount

ZERO = Decimal("0.00")
COLS = {
    "employee": ["employee", "employee name", "name", "staff", "staff name", "worker"],
    "gross": ["gross", "gross pay", "gross salary", "gross earnings", "total earnings", "gross wages"],
    "tax": ["paye", "tax", "income tax", "withholding tax", "wht", "paye tax", "tax deducted"],
    "pension": ["pension", "employee pension", "pension employee", "employee pension contribution", "pension contribution"],
    "other_deductions": ["other deductions", "deductions", "loan", "loan repayment", "other deduction", "total other deductions"],
    "net": ["net", "net pay", "net salary", "take home", "net wages", "amount paid"],
    "employer_cost": ["employer pension", "employer contribution", "employer contributions", "employer cost", "nsitf", "employer nhf", "employer pension contribution"],
}


def stage_payroll(table: Table, source: dict, options: dict) -> dict:
    rows = table.rows
    hr = None
    for i, r in enumerate(rows[:30]):
        hs = [norm_header(c) for c in r]
        if any(h in COLS["gross"] for h in hs) and any(h in COLS["net"] for h in hs):
            hr = i
            break
    if hr is None:
        raise IngestionError("I could not find the payroll column headings. I need at least Gross pay and Net pay columns.")
    header = [norm_header(c) for c in rows[hr]]
    cols: Dict[str, int] = {}
    for f, syns in COLS.items():
        for s in syns:
            if s in header and header.index(s) not in cols.values():
                cols[f] = header.index(s)
                break
    batch = M.new_batch("PAYROLL", source, {k: v for k, v in options.items() if k in ("sheet",)})
    batch["source"].update(table.source)
    batch["mapping"] = {f: clean(rows[hr][i]) for f, i in cols.items()}
    out, tot = [], {k: ZERO for k in ("gross", "tax", "pension", "other_deductions", "net", "employer_cost")}
    core = []
    for i, r in enumerate(rows[hr + 1:], hr + 2):
        if all(clean(c) == "" for c in r):
            continue
        g = lambda f: r[cols[f]] if f in cols and cols[f] < len(r) else None
        name = clean(g("employee"))
        if name.lower() in ("total", "totals", "grand total") or (not name and clean(g("gross")) == ""):
            continue
        issues: List[dict] = []
        v: Dict[str, Decimal] = {}
        for f in ("gross", "tax", "pension", "other_deductions", "net", "employer_cost"):
            try:
                v[f] = parse_amount(g(f)) or ZERO
            except AmountError as e:
                v[f] = ZERO
                issues.append(M.issue(M.ERROR, f"{f}: {e}", i, f))
            if v[f] < ZERO:
                issues.append(M.issue(M.ERROR, f"{f} is negative.", i, f))
        if not name:
            issues.append(M.issue(M.WARNING, "No employee name.", i, "employee"))
        if not any(x["level"] == M.ERROR for x in issues):
            exp = v["gross"] - v["tax"] - v["pension"] - v["other_deductions"]
            if exp != v["net"]:
                issues.append(M.issue(M.ERROR, f"Gross {money(v['gross'])} less deductions {money(v['tax'] + v['pension'] + v['other_deductions'])} is {money(exp)}, but net pay is {money(v['net'])}.", i, "net"))
        st = "ERROR" if any(x["level"] == M.ERROR for x in issues) else "WARNING" if issues else "OK"
        out.append({"row": i, "status": st, "employee": name, **{k: money(x) for k, x in v.items()}, "issues": issues})
        if st != "ERROR":
            for k in tot:
                tot[k] += v[k]
            core.append([name, *[money(v[k]) for k in tot]])
    batch["rows"] = out
    batch["summary"] = {"employees": len(out), **{f"total_{k}": money(x) for k, x in tot.items()}}
    if not out:
        batch["issues"].append(M.issue(M.ERROR, "No employee lines were found."))
    ok = tot["gross"] - tot["tax"] - tot["pension"] - tot["other_deductions"] == tot["net"]
    batch["checks"] = [M.check("NET_PAY_ADDS_UP", "Gross - deductions = net pay (every employee and in total)",
                               "PASS" if ok and not any(r["status"] == "ERROR" for r in out) else "FAIL", "Totals agree." if ok else "Totals do not agree.")]
    expense = tot["gross"] + tot["employer_cost"]
    lines = [{"side": "DEBIT", "account": None, "amount": money(expense), "note": "Salaries and wages expense (gross pay + employer contributions)"}]
    for key, label in (("net", "Net pay payable (or the bank account if paid directly)"), ("tax", "PAYE / income tax payable"),
                       ("pension", "Pension payable (employee share)"), ("other_deductions", "Other deductions payable")):
        if tot[key] > ZERO:
            lines.append({"side": "CREDIT", "account": None, "amount": money(tot[key]), "note": label})
    if tot["employer_cost"] > ZERO:
        lines.append({"side": "CREDIT", "account": None, "amount": money(tot["employer_cost"]), "note": "Employer contributions payable (pension / NSITF etc.)"})
    bal = sum((Decimal(l["amount"]) for l in lines if l["side"] == "DEBIT"), ZERO) == sum((Decimal(l["amount"]) for l in lines if l["side"] == "CREDIT"), ZERO)
    batch["proposal"] = {"applied": False, "action": "A person may draft this payroll journal", "needs_account_choice": True, "balances": bal, "lines": lines,
                         "note": "Nothing is posted and ASAVEXA does not choose accounts. The register is stored as evidence when you confirm."} if out else None
    batch["limits"] = ["This register contains personal pay data. It is stored in the Evidence Vault, visible only to roles that can read evidence.",
                       "ASAVEXA checks the arithmetic; it cannot check the PAYE rates, pension rules or that the people exist."]
    return M.finalize(batch, core=core)
