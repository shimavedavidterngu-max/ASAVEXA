"""Level 5: read invoices and receipts. Every extracted field says where it came from and how sure the reader is.
The reader is rule-based; nothing it finds is treated as true until a person has checked it against the document."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from . import model as M
from .errors import IngestionError
from .util import AmountError, CURRENCY_WORDS, DATE_FORMATS, clean, detect_date_format, money, parse_amount, parse_date_with

ZERO = Decimal("0.00")
NUM = r"[-(]?[₦$£€]?\s?(?:NGN|USD|GBP|EUR|GHS|KES|ZAR)?\s?[\d][\d,\s]*(?:\.\d{1,2})?\)?"
DATE_PAT = r"(\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{1,2}[ -](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*[ -,]*\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? \d{1,2},? \d{4})"
CUR_SYMBOL = {"₦": "NGN", "$": "USD", "£": "GBP", "€": "EUR"}


def _field(value, conf, line=None, note=None):
    d = {"value": value, "confidence": conf}
    if line:
        d["source_line"] = line[:160]
    if note:
        d["note"] = note
    return d


def _amount_after(label_re: str, lines: List[str], last: bool = False, exclude: Optional[str] = None):
    hits = []
    for ln in lines:
        low = ln.lower()
        if exclude and re.search(exclude, low):
            continue
        m = re.search(label_re, ln, re.I)
        if not m:
            continue
        tail = ln[m.end():]
        nums = re.findall(r"[-(]?[₦$£€]?\s?(?:" + CURRENCY_WORDS + r")?\s?\d[\d,\s]*(?:\.\d{1,2})?\)?", tail)
        for raw in nums:
            try:
                v = parse_amount(raw.strip())
            except AmountError:
                continue
            if v is not None:
                hits.append((v, ln))
                break
    if not hits:
        return None
    return hits[-1] if last else hits[0]


def read_document(text: str, forced_type: Optional[str] = None) -> Dict[str, Any]:
    lines = [clean(l) for l in text.splitlines() if clean(l)]
    low = text.lower()
    scores = {"INVOICE": 0, "RECEIPT": 0}
    scores["INVOICE"] += 3 * low.count("invoice") + (2 if re.search(r"due date|payment terms|bill to|amount due", low) else 0)
    scores["RECEIPT"] += 3 * low.count("receipt") + (2 if re.search(r"change|cash tendered|paid by|thank you for (your )?(shopping|purchase)|card payment", low) else 0)
    dtype = forced_type or ("INVOICE" if scores["INVOICE"] > scores["RECEIPT"] else "RECEIPT" if scores["RECEIPT"] > 0 else "UNKNOWN")
    fields: Dict[str, Any] = {}
    # vendor
    for ln in lines[:40]:
        m = re.match(r"^(?:from|supplier|vendor|sold by|issued by|merchant)\s*[:\-]\s*(.+)$", ln, re.I)
        if m:
            fields["vendor"] = _field(clean(m.group(1)), "HIGH", ln)
            break
    if "vendor" not in fields:
        for ln in lines[:6]:
            if len(ln) >= 3 and not re.search(r"invoice|receipt|tax|date|page|bill to|\d{4}", ln, re.I) and not re.match(r"^[\d\W]+$", ln):
                fields["vendor"] = _field(ln, "LOW", ln, "Guessed from the first line of the document. Check it.")
                break
    m = re.search(r"(?:invoice|inv|receipt|bill)\s*(?:no\.?|number|#|ref)?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/]{2,})", text, re.I)
    if m and re.search(r"\d", m.group(1)) and m.group(1).lower() not in ("date", "number"):
        fields["document_number"] = _field(m.group(1), "HIGH", _line_with(lines, m.group(0)))
    m = re.search(r"(?:TIN|tax id|VAT (?:reg(?:istration)?\.? ?)?(?:no|number)|VAT ID)\.?\s*[:#]?\s*([A-Z0-9\-]{6,})", text, re.I)
    if m:
        fields["tax_id"] = _field(m.group(1), "HIGH", _line_with(lines, m.group(0)))
    # dates
    cands = {}
    for key, lab in (("issue_date", r"(?:invoice date|date of issue|date issued|issue date|receipt date|(?<!due )date)\s*[:\-]?\s*"),
                     ("due_date", r"(?:due date|payment due|due on|pay by|due)\s*[:\-]?\s*")):
        m = re.search(lab + DATE_PAT, text, re.I)
        if m:
            cands[key] = m.group(1)
    all_d = [re.sub(r"Sept", "Sep", v) for v in cands.values()]
    label, fits, amb = detect_date_format(all_d) if all_d else (None, [], False)
    for key, raw in cands.items():
        d = parse_date_with(re.sub(r"Sept", "Sep", raw), label) if label else None
        if d is None:   # try each single format for this value
            for _, lb in DATE_FORMATS:
                d = parse_date_with(re.sub(r"Sept", "Sep", raw), lb)
                if d:
                    break
        if d:
            fields[key] = _field(d.isoformat(), "MEDIUM" if amb else "HIGH", raw, "Day/month order is ambiguous in this document; read as day first." if amb else None)
        else:
            fields[key] = _field(None, "LOW", raw, "A date was found but could not be read.")
    # amounts
    sub = _amount_after(r"\b(?:sub\s?-?total|net amount|net total|amount before tax|total before (?:tax|vat))\b[^\d(-]*", lines)
    tax = _amount_after(r"\b(?:vat|tax|gst|sales tax)\b(?: \(?\d{1,2}(?:\.\d+)?\s?%\)?)?[^\d(-]*", lines, exclude=r"(vat|tax)\s*(no|number|id|reg)|\btin\b")
    tot = _amount_after(r"\b(?:grand total|total due|amount due|balance due|total amount|total payable|amount payable|total)\b[^\d(-]*", lines, last=True,
                        exclude=r"sub\s?-?total|total before|total tax")
    for k, v in (("subtotal", sub), ("tax", tax), ("total", tot)):
        if v:
            fields[k] = _field(money(v[0]), "HIGH", v[1])
    cur = None
    m = re.search(r"\b(" + CURRENCY_WORDS + r")\b", text)
    if m:
        cur = m.group(1)
    else:
        for sym, code in CUR_SYMBOL.items():
            if sym in text:
                cur = code
                break
    if cur:
        fields["currency"] = _field(cur, "MEDIUM")
    checks = []
    C = M.check
    if sub and tax and tot:
        ok = sub[0] + tax[0] == tot[0]
        checks.append(C("TOTALS_ADD_UP", "Subtotal + tax = total", "PASS" if ok else "FAIL",
                        f"{money(sub[0])} + {money(tax[0])} = {money(sub[0] + tax[0])}; the document says {money(tot[0])}." if not ok else f"{money(sub[0])} + {money(tax[0])} = {money(tot[0])}."))
    else:
        checks.append(C("TOTALS_ADD_UP", "Subtotal + tax = total", "NOT_APPLICABLE", "Subtotal, tax and total were not all found."))
    checks.append(C("TOTAL_FOUND", "A total amount was found", "PASS" if tot else "FAIL", "Total " + money(tot[0]) if tot else "No total was found; the amount must be typed by a person."))
    if fields.get("issue_date") and fields.get("due_date") and fields["issue_date"]["value"] and fields["due_date"]["value"]:
        ok = fields["due_date"]["value"] >= fields["issue_date"]["value"]
        checks.append(C("DUE_AFTER_ISSUE", "Due date is not before the issue date", "PASS" if ok else "FAIL", f"{fields['issue_date']['value']} then {fields['due_date']['value']}."))
    return {"type": dtype, "type_scores": scores, "fields": fields, "checks": checks, "sums": {"subtotal": sub[0] if sub else None, "tax": tax[0] if tax else None, "total": tot[0] if tot else None}}


def _line_with(lines, snippet):
    first = snippet.split("\n")[0][:20]
    for ln in lines:
        if first in ln:
            return ln
    return None


def stage_document(source: dict, options: dict, text: Optional[str], fmt: str, pages: Optional[int] = None) -> dict:
    batch = M.new_batch("DOCUMENT", source, {k: v for k, v in options.items() if k in ("doc_type",)})
    batch["source"].update({"format": fmt})
    if pages:
        batch["source"]["pages"] = pages
    if text is None:
        batch["document"] = {"type": "UNREAD", "fields": {}, "reason": "This file type cannot be read by ASAVEXA (no OCR). It can still be stored as evidence."}
        batch["checks"] = []
        batch["limits"] = ["Nothing was extracted. A person must type in the details when attaching it."]
        batch["issues"].append(M.issue(M.INFO, "Stored as evidence only; ASAVEXA could not read this file."))
        return M.finalize(batch, core=[batch["source"]["sha256"]])
    forced = options.get("doc_type")
    if forced and forced not in ("INVOICE", "RECEIPT"):
        raise IngestionError("doc_type must be INVOICE or RECEIPT.")
    doc = read_document(text, forced)
    batch["document"] = {"type": doc["type"], "fields": doc["fields"]}
    batch["checks"] = doc["checks"]
    if doc["type"] == "UNKNOWN":
        batch["issues"].append(M.issue(M.WARNING, "I could not tell whether this is an invoice or a receipt. It will be stored as 'Other' unless you choose."))
    if "total" not in doc["fields"]:
        batch["issues"].append(M.issue(M.WARNING, "No total amount was found."))
    low = [k for k, v in doc["fields"].items() if v["confidence"] == "LOW"]
    if low:
        batch["issues"].append(M.issue(M.WARNING, "Low confidence in: " + ", ".join(low) + ". Check these against the document."))
    t = doc["sums"]["total"]
    batch["proposal"] = ({"applied": False, "action": "A person may draft a journal for this document",
                          "needs_account_choice": True,
                          "lines": [{"side": "DEBIT", "account": None, "amount": money(t), "note": "the expense or asset this purchase belongs to"},
                                    {"side": "CREDIT", "account": None, "amount": money(t), "note": "Accounts payable (invoice) or the bank/cash account (receipt)"}],
                          "note": "Nothing is posted. ASAVEXA does not choose accounts."} if t else None)
    batch["limits"] = ["Machine-read fields are unverified. They are saved with the evidence, flagged as machine-read, and a person must still verify the document.",
                       "Only the text of a PDF is read; line items, handwriting and images are not."]
    core = {"type": doc["type"], "fields": {k: v["value"] for k, v in doc["fields"].items()}}
    return M.finalize(batch, core=[core])
