"""Levels 1-3 for money: turn rows of a bank statement into staged bank transactions and CHECK them.

Direction convention (the same one the Reconciliation module uses): money INTO the bank account is `debit_amount`
(it debits the cash account in the ledger); money OUT is `credit_amount`. The preview always shows plain words
("Money in" / "Money out") so nobody has to think about it.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from . import model as M
from .errors import IngestionError
from .tabular import Table, detect_mapping, find_header_row, resolve_mapping_override
from .util import AmountError, LABEL_TO_FMT, clean, detect_date_format, norm_header, parse_amount, parse_date_with, money

ZERO = Decimal("0.00")
DR_WORDS = {"dr", "debit", "d", "db", "out", "withdrawal", "payment"}
CR_WORDS = {"cr", "credit", "c", "in", "deposit", "lodgement", "receipt"}
FOOTER = re.compile(r"^(total|totals|grand total|sub ?total|closing|opening|balance|brought|carried|page|statement|end of)\b", re.I)
OPENING_WORDS = ("opening balance", "balance brought forward", "balance b/f", "brought forward", "previous balance", "balance b f", "opening bal")
CLOSING_WORDS = ("closing balance", "balance carried forward", "balance c/f", "carried forward", "ending balance", "balance c f", "closing bal")


def _to_date(v, label: Optional[str]) -> Optional[date]:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = clean(v)
    if not s:
        return None
    if label:
        return parse_date_with(s, label)
    return None


def _scan_balances(rows: List[List[Any]], skip: range) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """Opening/closing balances written as 'Opening balance ....... 1,000.00' outside the data rows."""
    opening = closing = None
    for i, row in enumerate(rows):
        if i in skip:
            continue
        cells = [clean(c) for c in row]
        for j, c in enumerate(cells):
            low = c.lower()
            kind = "o" if any(w in low for w in OPENING_WORDS) else "c" if any(w in low for w in CLOSING_WORDS) else None
            if not kind:
                continue
            tail = [x for x in row[j + 1:] if clean(x) != ""]
            m = re.search(r"([-(]?[\d.,]+\)?(?:\s?(?:CR|DR))?)\s*$", c)
            raw = tail[0] if tail else (m.group(1) if m and any(ch.isdigit() for ch in m.group(1)) else None)
            try:
                val = parse_amount(raw) if raw is not None else None
            except AmountError:
                val = None
            if val is not None:
                if kind == "o" and opening is None:
                    opening = val
                if kind == "c" and closing is None:
                    closing = val
    return opening, closing


def stage_bank_table(filename: str, table: Table, source: dict, options: dict) -> dict:
    """options: header_row (0-based), mapping (field->header/index), date_format (label), flip (bool), currency, period, bank_name"""
    rows = table.rows
    batch = M.new_batch("BANK_TRANSACTIONS", source, {k: v for k, v in options.items() if k in ("header_row", "mapping", "date_format", "flip", "sheet", "delimiter", "skip_rows")})
    batch["source"].update(table.source)
    for w in table.warnings:
        batch["issues"].append(M.issue(M.WARNING, w))

    hr = options.get("header_row")
    if hr is None and options.get("mapping"):
        names = [norm_header(v) for v in options["mapping"].values() if isinstance(v, str) and not v.isdigit()]
        for i, row in enumerate(rows[:40]):
            if names and all(n in [norm_header(c) for c in row] for n in names):
                hr = i
                break
    if hr is None:
        hr = find_header_row(rows, need=("date",))
        if hr is None:
            raise IngestionError("I could not find the column headings (a row with Date and amount/debit/credit columns). "
                                 "Tell me which row they are on, or add a heading row to the file.")
    if hr >= len(rows):
        raise IngestionError("The header row you chose is past the end of the file.")
    header = rows[hr]
    mapping = resolve_mapping_override(header, options.get("mapping"))
    has_amount = "amount" in mapping or "debit" in mapping or "credit" in mapping
    columns = [clean(c) or f"column {i + 1}" for i, c in enumerate(header)]
    if "date" not in mapping or not has_amount:
        # Show the columns and let the person say which is which, instead of just failing.
        missing = ("the transaction date" if "date" not in mapping else "") + (" and " if "date" not in mapping and not has_amount else "") + \
                  ("the amount (one Amount column, or Debit and Credit columns)" if not has_amount else "")
        batch["mapping"] = {f: clean(header[i]) or f"column {i + 1}" for f, i in mapping.items()}
        batch["header_row"] = hr
        batch["columns"] = columns
        batch["issues"].append(M.issue(M.ERROR, f"I could not tell which columns hold {missing}. Choose them below."))
        batch["summary"] = {"lines": 0, "valid_lines": 0, "money_in_total": "0.00", "money_out_total": "0.00", "net": "0.00", "first_date": None, "last_date": None,
                            "opening_balance": None, "closing_balance": None}
        return M.finalize(batch, core=[])
    batch["mapping"] = {f: clean(header[i]) or f"column {i + 1}" for f, i in mapping.items()}
    batch["header_row"] = hr
    batch["columns"] = [clean(c) or f"column {i + 1}" for i, c in enumerate(header)]

    data_rows = [(i, r) for i, r in enumerate(rows) if i > hr]
    opening, closing = _scan_balances(rows, range(0))
    # date format: from the date column of rows that have any amount (so footer text never confuses it)
    def cell(r, f):
        i = mapping.get(f)
        return r[i] if i is not None and i < len(r) else None
    def has_amount(r):
        return any(clean(cell(r, f)) != "" for f in ("amount", "debit", "credit") if f in mapping)
    date_cells = [cell(r, "date") for _, r in data_rows if clean(cell(r, "date")) != "" and has_amount(r)
                  and not isinstance(cell(r, "date"), (date, datetime))]
    label = options.get("date_format")
    fmt_info = None
    if label and label not in LABEL_TO_FMT:
        raise IngestionError(f"Unknown date format {label!r}.")
    if not label and date_cells:
        label, fits, ambiguous = detect_date_format([c for c in date_cells])
        fmt_info = {"detected": label, "also_fits": fits, "ambiguous": ambiguous}
        if label is None:
            batch["issues"].append(M.issue(M.WARNING, "The dates are written in more than one style or an unusual style; rows that do not fit are marked as errors. "
                                           "Choose the date format to read them."))
        elif ambiguous:
            batch["issues"].append(M.issue(M.WARNING, f"The dates could be day/month or month/day. They were read as {label}. "
                                           "Check the first few rows, and choose the other format if they look wrong."))
    batch["detected"] = {"date_format": fmt_info or ({"chosen": label} if label else None), "header_row": hr + 1}

    flip = bool(options.get("flip"))
    entries: List[dict] = []
    skipped = 0
    for i, r in data_rows:
        if all(clean(c) == "" for c in r):
            continue
        rownum = i + 1
        d_raw, a_raw = cell(r, "date"), None
        amount_cells = [cell(r, f) for f in ("amount", "debit", "credit") if f in mapping]
        issues: List[dict] = []
        d = None
        try:
            d = _to_date(d_raw, label)
        except Exception:
            d = None
        if d is None and (all(clean(c) == "" for c in amount_cells) or FOOTER.match(clean(d_raw)) or FOOTER.match(clean(cell(r, "description")))):
            skipped += 1          # a note, subtotal label or footer line ("Totals", "Closing balance ...")
            continue
        if d is None:
            issues.append(M.issue(M.ERROR, f"The date {clean(d_raw)!r} could not be read" + (f" as {label}." if label else "."), rownum, "date"))
        vd = None
        if "value_date" in mapping and clean(cell(r, "value_date")) != "":
            vd = _to_date(cell(r, "value_date"), label)
            if vd is None:
                issues.append(M.issue(M.WARNING, f"The value date {clean(cell(r, 'value_date'))!r} could not be read; it was left blank.", rownum, "value_date"))
        money_in = money_out = ZERO
        try:
            money_in, money_out = _amounts(r, mapping, cell, flip, issues, rownum)
        except AmountError as e:
            issues.append(M.issue(M.ERROR, str(e), rownum, "amount"))
        bal = None
        if "balance" in mapping and clean(cell(r, "balance")) != "":
            try:
                bal = parse_amount(cell(r, "balance"))
            except AmountError as e:
                issues.append(M.issue(M.WARNING, f"Balance: {e}", rownum, "balance"))
        if money_in == ZERO and money_out == ZERO and not any(x["level"] == M.ERROR for x in issues):
            skipped += 1
            continue
        desc = clean(cell(r, "description"))
        ref = clean(cell(r, "reference")) or None
        cur = clean(cell(r, "currency")).upper() or None
        entries.append({"row": rownum, "date": d, "value_date": vd, "description": desc, "reference": ref, "money_in": money_in,
                        "money_out": money_out, "balance": bal, "currency": cur, "issues": issues})
    batch["summary"]["skipped_lines"] = skipped
    return finish_bank_batch(batch, entries, opening=opening, closing=closing, period=options.get("period"),
                             expected_currency=options.get("currency"))


def _amounts(r, mapping, cell, flip, issues, rownum) -> Tuple[Decimal, Decimal]:
    amt = deb = cre = None
    if "amount" in mapping:
        amt = parse_amount(cell(r, "amount"))
    if "debit" in mapping:
        deb = parse_amount(cell(r, "debit"))
    if "credit" in mapping:
        cre = parse_amount(cell(r, "credit"))
    if deb is not None or cre is not None:
        out_, in_ = deb or ZERO, cre or ZERO
        if deb is not None and deb < 0:
            issues.append(M.issue(M.WARNING, "A negative number in the Debit column was read as money out.", rownum, "debit"))
            out_ = abs(deb)
        if cre is not None and cre < 0:
            issues.append(M.issue(M.WARNING, "A negative number in the Credit column was read as money in.", rownum, "credit"))
            in_ = abs(cre)
        if out_ > ZERO and in_ > ZERO:
            raise AmountError("both Debit and Credit have an amount on the same line")
        if amt is not None and amt != ZERO and out_ == ZERO and in_ == ZERO:
            pass  # fall through to the single-amount rule
        else:
            if flip:
                in_, out_ = out_, in_
            return in_, out_
    if amt is None:
        return ZERO, ZERO
    sign = None
    if "dr_cr" in mapping:
        w = norm_header(cell(r, "dr_cr"))
        if w in DR_WORDS:
            sign = -1
        elif w in CR_WORDS:
            sign = 1
        elif clean(cell(r, "dr_cr")):
            raise AmountError(f"The debit/credit marker {clean(cell(r, 'dr_cr'))!r} is not understood (use DR/CR)")
    if sign is None:
        sign = 1 if amt >= 0 else -1
    net = abs(amt) * sign
    if flip:
        net = -net
    return (net, ZERO) if net > ZERO else (ZERO, -net)


# ------------------------------------------------------------------ shared by every statement-like source
def finish_bank_batch(batch: dict, entries: List[dict], *, opening: Optional[Decimal] = None, closing: Optional[Decimal] = None,
                      period: Optional[Tuple[date, date]] = None, expected_currency: Optional[str] = None) -> dict:
    """entries: dicts with row, date, value_date, description, reference, money_in, money_out, balance, currency, issues.
    Adds duplicate handling, currency/period checks, balance checks, summary and fingerprint."""
    seen: Dict[tuple, int] = {}
    out_rows: List[dict] = []
    core: List[list] = []
    for e in entries:
        issues = list(e["issues"])
        desc = e["description"]
        if not desc and not any(x["level"] == M.ERROR for x in issues):
            desc = e["reference"] or "Bank transaction"
            issues.append(M.issue(M.WARNING, "No description; the reference was used instead.", e["row"], "description"))
        if e["currency"] and expected_currency and e["currency"] != expected_currency.upper():
            issues.append(M.issue(M.ERROR, f"This line is in {e['currency']} but the bank account is in {expected_currency.upper()}.", e["row"], "currency"))
        d = e["date"]
        if d is not None:
            if period and not (period[0] <= d <= period[1]):
                issues.append(M.issue(M.WARNING, f"{d.isoformat()} is outside the reconciliation period ({period[0].isoformat()} to {period[1].isoformat()}).", e["row"], "date"))
            if d > date.today():
                issues.append(M.issue(M.WARNING, f"{d.isoformat()} is in the future.", e["row"], "date"))
        ext = e["reference"]
        key = (d, re.sub(r"\s+", " ", desc.lower()), e["money_in"], e["money_out"], ext)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            ext = f"{ext or ''}#DUP{seen[key]}"
            issues.append(M.issue(M.WARNING, f"An identical line already appears earlier in this file. It was kept as a separate transaction (marked {ext}); "
                                  "confirm it is real and not a repeated export.", e["row"]))
        level = "ERROR" if any(x["level"] == M.ERROR for x in issues) else "WARNING" if any(x["level"] == M.WARNING for x in issues) else "OK"
        row = {"row": e["row"], "status": level, "date": d.isoformat() if d else None, "value_date": e["value_date"].isoformat() if e.get("value_date") else None,
               "description": desc, "reference": ext, "money_in": money(e["money_in"]), "money_out": money(e["money_out"]),
               "balance": money(e["balance"]) if e.get("balance") is not None else None, "currency": e["currency"], "issues": issues}
        out_rows.append(row)
        if level != "ERROR":
            core.append([d.isoformat(), row["value_date"], desc, ext, money(e["money_in"]), money(e["money_out"])])
    batch["rows"] = out_rows
    good = [r for r in out_rows if r["status"] != "ERROR"]
    tin = sum((Decimal(r["money_in"]) for r in good), ZERO)
    tout = sum((Decimal(r["money_out"]) for r in good), ZERO)
    dates = sorted(r["date"] for r in good if r["date"])
    s = batch["summary"]
    s.update({"lines": len(out_rows), "valid_lines": len(good), "money_in_total": money(tin), "money_out_total": money(tout),
              "net": money(tin - tout), "first_date": dates[0] if dates else None, "last_date": dates[-1] if dates else None,
              "opening_balance": money(opening) if opening is not None else None, "closing_balance": money(closing) if closing is not None else None})
    if not out_rows:
        batch["issues"].append(M.issue(M.ERROR, "No transactions were found in the file."))
    batch["checks"] = bank_checks(entries, out_rows, opening, closing, tin, tout)
    if any(r["status"] == "ERROR" for r in out_rows):
        batch["issues"].append(M.issue(M.INFO, "Fix the lines marked ERROR in the file (or choose the right columns / date format) and preview again. "
                                       "Nothing is imported while any line has an error."))
    batch["limits"] = ["This is a reading of the file, not proof the bank issued it. Attach the original statement as evidence.",
                       "Money in/out is decided from the column names or signs. Check the totals against the statement."]
    return M.finalize(batch, core=core)


def bank_checks(entries, rows, opening, closing, tin, tout) -> List[dict]:
    C = M.check
    out = []
    # 1) running balance continuity (file order first; newest-first files are detected)
    seq = [(e, r) for e, r in zip(entries, rows) if e.get("balance") is not None and r["status"] != "ERROR"]
    if len(seq) >= 2:
        def breaks(pairs):
            bad = []
            for (pe, _), (ce, cr) in zip(pairs, pairs[1:]):
                if pe["balance"] + ce["money_in"] - ce["money_out"] != ce["balance"]:
                    bad.append(cr["row"])
            return bad
        fwd, rev = breaks(seq), breaks(list(reversed(seq)))
        use, direction = (fwd, "oldest first") if len(fwd) <= len(rev) else (rev, "newest first")
        if not use:
            out.append(C("BALANCE_CONTINUITY", "Running balance adds up line by line", "PASS", f"All {len(seq) - 1} steps agree ({direction})."))
        else:
            out.append(C("BALANCE_CONTINUITY", "Running balance adds up line by line", "FAIL",
                         f"{len(use)} line(s) do not follow from the one before ({direction}); first at file row {use[0]}. A line may be missing, repeated or misread."))
    else:
        out.append(C("BALANCE_CONTINUITY", "Running balance adds up line by line", "NOT_APPLICABLE", "The file has no running balance column."))
    # 2) opening + movement = closing
    if opening is not None and closing is not None:
        ok = opening + tin - tout == closing
        out.append(C("OPENING_CLOSING", "Opening balance + movement = closing balance", "PASS" if ok else "FAIL",
                     f"{money(opening)} + {money(tin)} - {money(tout)} = {money(opening + tin - tout)}; the statement says {money(closing)}." if not ok
                     else f"{money(opening)} + {money(tin)} - {money(tout)} = {money(closing)}."))
    else:
        out.append(C("OPENING_CLOSING", "Opening balance + movement = closing balance", "NOT_APPLICABLE", "The file does not state both an opening and a closing balance."))
    return out
