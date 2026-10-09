"""Level 6: accounting-software exports (Xero, QuickBooks, Sage and generic CSV/Excel).

This reads the FILES those products export. It does not talk to their live APIs (that needs each vendor's OAuth
app and credentials, which cannot be created or tested from here). Imported journals become DRAFTS only."""
from __future__ import annotations

import re
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from . import model as M
from .bank import _to_date
from .errors import IngestionError
from .tabular import Table, norm_header
from .util import AmountError, LABEL_TO_FMT, clean, detect_date_format, money, parse_amount

ZERO = Decimal("0.00")

COA_COLS = {
    "code": ["code", "account code", "account number", "acct no", "account no", "nominal code", "nominal", "number", "no", "account num", "gl code"],
    "name": ["name", "account name", "account", "account title", "nominal name", "title", "description"],
    "type": ["type", "account type", "category", "class", "classification", "account category"],
    "detail": ["detail type", "sub type", "subtype"],
}
JRN_COLS = {
    "date": ["date", "journal date", "transaction date", "posting date", "entry date", "txn date"],
    "number": ["journal number", "journal no", "journal #", "num", "number", "journal", "journal id", "reference", "ref", "txn id", "transaction id", "entry no", "entry number"],
    "account": ["account", "account code", "account name", "gl account", "account number", "nominal code"],
    "description": ["description", "memo", "narration", "details", "line description", "memo description", "memo/description"],
    "debit": ["debit", "debits", "debit amount", "dr"],
    "credit": ["credit", "credits", "credit amount", "cr"],
}
SYSTEM_HINTS = [
    ("XERO", lambda h: any(x.startswith("*") for x in h) or "tax code" in h or "enable payments" in h or "expense claims" in h),
    ("QUICKBOOKS", lambda h: "detail type" in h or "account #" in h or "num" in h and "memo/description" in h),
    ("SAGE", lambda h: "nominal code" in h or "nominal" in h),
]


def _strip(h: str) -> str:
    return norm_header(h.replace("*", "").replace("#", " number "))


def classify_account_type(t: str) -> Optional[str]:
    low = (t or "").lower()
    if not low.strip():
        return None
    for words, out in ((("liabilit", "payable", "credit card", "loan", "overdraft"), "LIABILITY"), (("equity", "capital", "retained", "drawings", "shareholder"), "EQUITY"),
                       (("revenue", "income", "sales", "turnover"), "REVENUE"), (("expense", "cost of", "overhead", "depreciation", "direct cost", "purchases", "cogs"), "EXPENSE"),
                       (("asset", "bank", "receivable", "inventory", "stock", "prepay", "cash", "debtor"), "ASSET")):
        if any(w in low for w in words):
            return out
    return None


def _pick(header: List[Any], spec: Dict[str, List[str]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    hs = [_strip(clean(h)) for h in header]
    for fld, syns in spec.items():
        for syn in syns:
            if syn in hs:
                i = hs.index(syn)
                if i not in out.values():
                    out[fld] = i
                    break
    return out


def _find_header(rows, spec, need) -> int:
    for i, row in enumerate(rows[:30]):
        m = _pick(row, spec)
        if all(n in m for n in need) and len(m) >= len(need):
            return i
    raise IngestionError("I could not find the column headings. " + ("For a chart of accounts I need Code, Name and Type columns." if "code" in need else
                         "For journals I need Date, Account, Debit and Credit columns."))


def stage_chart_of_accounts(table: Table, source: dict, options: dict, existing_codes: Optional[Dict[str, str]] = None) -> dict:
    rows = table.rows
    hr = _find_header(rows, COA_COLS, ("code", "name", "type"))
    header = rows[hr]
    cols = _pick(header, COA_COLS)
    hs = [_strip(clean(h)) for h in header]
    system = next((n for n, f in SYSTEM_HINTS if f(hs) or f([clean(h).lower() for h in header])), "GENERIC")
    batch = M.new_batch("CHART_OF_ACCOUNTS", source, {k: v for k, v in options.items() if k in ("sheet",)})
    batch["source"].update(table.source)
    batch["source"]["looks_like"] = system
    batch["mapping"] = {k: clean(header[i]) for k, i in cols.items()}
    for w in table.warnings:
        batch["issues"].append(M.issue(M.WARNING, w))
    seen: Dict[str, int] = {}
    out_rows, core = [], []
    for i, r in enumerate(rows[hr + 1:], hr + 2):
        if all(clean(c) == "" for c in r):
            continue
        g = lambda f: clean(r[cols[f]]) if f in cols and cols[f] < len(r) else ""
        code, name, typ = g("code"), g("name"), g("type")
        detail = g("detail")
        issues = []
        if not code:
            issues.append(M.issue(M.ERROR, "No account code. ASAVEXA needs a code for every account; add one in the file.", i, "code"))
        if not name:
            issues.append(M.issue(M.ERROR, "No account name.", i, "name"))
        at = classify_account_type(typ) or classify_account_type(detail)
        if at is None:
            issues.append(M.issue(M.ERROR, f"The account type {typ!r} is not one I can map to Asset, Liability, Equity, Revenue or Expense. Change it in the file.", i, "type"))
        if code and code in seen:
            issues.append(M.issue(M.ERROR, f"The code {code} is used twice (also on file row {seen[code]}).", i, "code"))
        seen.setdefault(code, i)
        exists = bool(existing_codes and code in existing_codes)
        if exists:
            issues.append(M.issue(M.INFO, f"An account with code {code} already exists; it will be left unchanged.", i, "code"))
        st = "ERROR" if any(x["level"] == M.ERROR for x in issues) else "OK"
        out_rows.append({"row": i, "status": st, "code": code, "name": name, "source_type": typ, "type": at, "already_exists": exists, "issues": issues})
        if st == "OK" and not exists:
            core.append([code, name, at])
    if not out_rows:
        batch["issues"].append(M.issue(M.ERROR, "No accounts were found in the file."))
    batch["rows"] = out_rows
    batch["summary"] = {"accounts": len(out_rows), "new": len(core), "already_exist": sum(1 for r in out_rows if r["already_exists"])}
    batch["limits"] = ["Account types were mapped by name (e.g. 'Fixed Assets' -> Asset). Check them: ASAVEXA statements depend on the type.",
                       "Opening balances in the file are NOT imported. Bring balances in as an opening journal that a person approves."]
    return M.finalize(batch, core=core)


def stage_journals(table: Table, source: dict, options: dict, accounts: List[dict], periods: List[dict], currency: str) -> dict:
    """accounts: [{id, code, name}]; periods: [{start, end, status}] (dates as date)."""
    rows = table.rows
    hr = _find_header(rows, JRN_COLS, ("date", "account", "debit", "credit"))
    header = rows[hr]
    cols = _pick(header, JRN_COLS)
    batch = M.new_batch("JOURNALS", source, {k: v for k, v in options.items() if k in ("sheet", "date_format")})
    batch["source"].update(table.source)
    batch["mapping"] = {k: clean(header[i]) for k, i in cols.items()}
    for w in table.warnings:
        batch["issues"].append(M.issue(M.WARNING, w))
    by_code = {a["code"].lower(): a for a in accounts}
    by_name = {}
    for a in accounts:
        by_name.setdefault(a["name"].lower(), []).append(a)
    cells = lambda r, f: r[cols[f]] if f in cols and cols[f] < len(r) else None
    data = [(i, r) for i, r in enumerate(rows[hr + 1:], hr + 2) if not all(clean(c) == "" for c in r)]
    label = options.get("date_format")
    if not label:
        raw = [cells(r, "date") for _, r in data if not isinstance(cells(r, "date"), (date, datetime)) and clean(cells(r, "date"))]
        label, fits, amb = detect_date_format(raw) if raw else (None, [], False)
        if amb and label:
            batch["issues"].append(M.issue(M.WARNING, f"The dates could be day/month or month/day. They were read as {label}."))
    groups: "OrderedDict[str, dict]" = OrderedDict()
    prev_key = None
    out_lines = []
    for i, r in data:
        issues = []
        d = _to_date(cells(r, "date"), label)
        if d is None:
            issues.append(M.issue(M.ERROR, f"The date {clean(cells(r, 'date'))!r} could not be read.", i, "date"))
        acct_ref = clean(cells(r, "account"))
        acct = by_code.get(acct_ref.lower()) or (by_name.get(acct_ref.lower()) or [None])[0] if acct_ref else None
        if acct_ref and len(by_name.get(acct_ref.lower(), [])) > 1 and acct_ref.lower() not in by_code:
            acct = None
            issues.append(M.issue(M.ERROR, f"More than one account is called {acct_ref!r}. Use the account code.", i, "account"))
        elif not acct:
            issues.append(M.issue(M.ERROR, f"There is no account {acct_ref!r} in ASAVEXA. Import the chart of accounts first.", i, "account"))
        try:
            dr = parse_amount(cells(r, "debit")) or ZERO
            cr = parse_amount(cells(r, "credit")) or ZERO
        except AmountError as e:
            dr = cr = ZERO
            issues.append(M.issue(M.ERROR, str(e), i, "amount"))
        if dr < ZERO or cr < ZERO:
            issues.append(M.issue(M.ERROR, "Negative debit/credit amounts are not accepted; put the amount on the other side.", i, "amount"))
        if (dr > ZERO) == (cr > ZERO) and not any(x["level"] == M.ERROR for x in issues):
            issues.append(M.issue(M.ERROR, "A journal line needs exactly one of debit or credit.", i, "amount"))
        num = clean(cells(r, "number")) if "number" in cols else ""
        key = num or prev_key or "unnumbered"
        out_lines.append({"row": i, "journal": key, "date": d, "account_ref": acct_ref, "account": acct, "debit": dr, "credit": cr,
                          "description": clean(cells(r, "description")), "issues": issues})
        prev_key = key
    # no number column: split into journals whenever the running group balances
    if "number" not in cols:
        n, run_d, run_c, cur = 0, ZERO, ZERO, None
        for ln in out_lines:
            if cur is None:
                n += 1
                cur = f"J{n}"
            ln["journal"] = cur
            run_d += ln["debit"]; run_c += ln["credit"]
            if run_d == run_c and run_d > ZERO:
                cur, run_d, run_c = None, ZERO, ZERO
    for ln in out_lines:
        g = groups.setdefault(ln["journal"], {"lines": []})
        g["lines"].append(ln)
    journals, core = [], []
    open_periods = [p for p in periods if p.get("status") == "OPEN"]
    for key, g in groups.items():
        ls = g["lines"]
        dates = {l["date"] for l in ls if l["date"]}
        jd = min(dates) if dates else None
        td, tc = sum((l["debit"] for l in ls), ZERO), sum((l["credit"] for l in ls), ZERO)
        jissues = []
        if len(dates) > 1:
            jissues.append(M.issue(M.ERROR, f"Journal {key} has lines on different dates.", ls[0]["row"], "date"))
        if td != tc:
            jissues.append(M.issue(M.ERROR, f"Journal {key} does not balance: debits {money(td)}, credits {money(tc)}.", ls[0]["row"]))
        if len(ls) < 2:
            jissues.append(M.issue(M.ERROR, f"Journal {key} has only one line.", ls[0]["row"]))
        if jd and periods is not None and not any(p["start"] <= jd <= p["end"] for p in open_periods):
            jissues.append(M.issue(M.ERROR, f"{jd.isoformat()} is not inside an OPEN accounting period. Open the period first.", ls[0]["row"], "date"))
        bad = any(x["level"] == M.ERROR for l in ls for x in l["issues"]) or any(x["level"] == M.ERROR for x in jissues)
        j = {"journal": key, "date": jd.isoformat() if jd else None, "status": "ERROR" if bad else "OK", "total": money(td), "currency": currency, "issues": jissues,
             "description": next((l["description"] for l in ls if l["description"]), f"Imported journal {key}"),
             "lines": [{"row": l["row"], "account_ref": l["account_ref"], "account_id": l["account"]["id"] if l["account"] else None,
                        "account": f"{l['account']['code']} {l['account']['name']}" if l["account"] else None, "debit": money(l["debit"]), "credit": money(l["credit"]),
                        "description": l["description"], "issues": l["issues"]} for l in ls]}
        journals.append(j)
        if not bad:
            core.append([key, j["date"], j["description"], [[l["account_id"], l["debit"], l["credit"]] for l in j["lines"]]])
    batch["rows"] = journals
    batch["summary"] = {"journals": len(journals), "valid": len(core), "lines": len(out_lines)}
    if not journals:
        batch["issues"].append(M.issue(M.ERROR, "No journal lines were found in the file."))
    batch["checks"] = [M.check("ALL_BALANCED", "Every journal balances", "PASS" if all(not any("does not balance" in x["message"] for x in j["issues"]) for j in journals) else "FAIL",
                               "Debits equal credits in each journal." if journals else "No journals.")]
    batch["limits"] = ["Journals are imported as DRAFTS. A different person must still post them; ASAVEXA will not post imported journals for you.",
                       "Lines are matched to ASAVEXA accounts by code or exact name; nothing is guessed."]
    return M.finalize(batch, core=core)
