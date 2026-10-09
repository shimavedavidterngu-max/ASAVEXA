"""Level 3: real bank-statement file formats. OFX/QFX (SGML 1.x and XML 2.x) and SWIFT MT940."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from . import model as M
from .bank import finish_bank_batch
from .errors import IngestionError, UnsupportedFileError
from .tabular import decode_text
from .util import AmountError, clean, parse_amount

ZERO = Decimal("0.00")


def _ofx_date(s: str) -> Optional[date]:
    m = re.match(r"^(\d{4})(\d{2})(\d{2})", clean(s))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _tag(block: str, name: str) -> Optional[str]:
    m = re.search(rf"<{name}>([^<\r\n]*)", block, re.I)
    return clean(m.group(1)) if m else None


def _entities(s: Optional[str]) -> str:
    return (s or "").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'")


def stage_ofx(filename: str, content: bytes, source: dict, options: dict) -> dict:
    text, enc, warns = decode_text(content)
    if "<OFX" not in text.upper():
        raise UnsupportedFileError("This does not look like an OFX/QFX file.")
    body = text[text.upper().index("<OFX"):]
    batch = M.new_batch("BANK_TRANSACTIONS", source, {k: v for k, v in options.items() if k in ("flip",)})
    batch["source"].update({"format": "OFX", "encoding": enc})
    for w in warns:
        batch["issues"].append(M.issue(M.WARNING, w))
    cur = (_tag(body, "CURDEF") or "").upper() or None
    acct = _tag(body, "ACCTID")
    if acct:
        batch["source"]["account_hint"] = "…" + acct[-4:]
    entries = []
    blocks = re.findall(r"<STMTTRN>(.*?)(?=</STMTTRN>|<STMTTRN>|</BANKTRANLIST>|$)", body, re.S | re.I)
    for n, blk in enumerate(blocks, 1):
        issues: List[dict] = []
        d = _ofx_date(_tag(blk, "DTPOSTED") or "")
        if d is None:
            issues.append(M.issue(M.ERROR, f"Transaction {n}: the posting date is missing or unreadable.", n, "date"))
        amt = ZERO
        try:
            a = parse_amount((_tag(blk, "TRNAMT") or "").replace(",", "."))
            if a is None:
                raise AmountError("the amount is missing")
            amt = a
        except AmountError as e:
            issues.append(M.issue(M.ERROR, f"Transaction {n}: {e}", n, "amount"))
        if options.get("flip"):
            amt = -amt
        name, memo = _entities(_tag(blk, "NAME")), _entities(_tag(blk, "MEMO"))
        desc = clean(f"{name} {memo}" if memo and memo != name else name or memo)
        if amt == ZERO and not issues:
            continue
        entries.append({"row": n, "date": d, "value_date": _ofx_date(_tag(blk, "DTUSER") or ""), "description": desc,
                        "reference": _tag(blk, "FITID") or _tag(blk, "CHECKNUM"), "money_in": amt if amt > 0 else ZERO,
                        "money_out": -amt if amt < 0 else ZERO, "balance": None, "currency": cur, "issues": issues})
    closing = None
    m = re.search(r"<LEDGERBAL>.*?<BALAMT>([^<\r\n]*)", body, re.S | re.I)
    if m:
        try:
            closing = parse_amount(m.group(1).strip())
        except AmountError:
            closing = None
    batch["mapping"] = {"format": "OFX statement lines (STMTTRN)"}
    batch["limits"] = []
    out = finish_bank_batch(batch, entries, opening=None, closing=None, period=options.get("period"), expected_currency=options.get("currency"))
    if closing is not None:
        out["summary"]["closing_balance"] = f"{closing:.2f}"
    return out


# --------------------------------------------------------------------- MT940
def _mt_amount(s: str) -> Decimal:
    return parse_amount(s.replace(",", ".") if "," in s and "." not in s else s)


def _mt_date(yymmdd: str) -> Optional[date]:
    try:
        yy = int(yymmdd[0:2])
        return date(2000 + yy if yy < 70 else 1900 + yy, int(yymmdd[2:4]), int(yymmdd[4:6]))
    except (ValueError, IndexError):
        return None


def stage_mt940(filename: str, content: bytes, source: dict, options: dict) -> dict:
    text, enc, warns = decode_text(content)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if ":61:" not in text and ":60F:" not in text and ":60M:" not in text:
        raise UnsupportedFileError("This does not look like an MT940 statement.")
    batch = M.new_batch("BANK_TRANSACTIONS", source, {k: v for k, v in options.items() if k in ("flip",)})
    batch["source"].update({"format": "MT940", "encoding": enc})
    for w in warns:
        batch["issues"].append(M.issue(M.WARNING, w))
    fields = re.split(r"\n(?=:\d{2}[A-Z]?:)", "\n" + text)
    entries: List[dict] = []
    opening = closing = None
    cur: Optional[str] = None
    last: Optional[dict] = None
    n = 0
    for f in fields:
        m = re.match(r"^\n?:(\d{2}[A-Z]?):(.*)$", f, re.S)
        if not m:
            continue
        tag, val = m.group(1), m.group(2).strip("\n")
        if tag in ("60F", "60M"):
            mm = re.match(r"^([CD])(\d{6})([A-Z]{3})([\d,\.]+)", val)
            if mm and opening is None:
                opening = _mt_amount(mm.group(4)) * (1 if mm.group(1) == "C" else -1)
                cur = cur or mm.group(3)
        elif tag in ("62F", "62M"):
            mm = re.match(r"^([CD])(\d{6})([A-Z]{3})([\d,\.]+)", val)
            if mm:
                closing = _mt_amount(mm.group(4)) * (1 if mm.group(1) == "C" else -1)
                cur = cur or mm.group(3)
        elif tag == "61":
            n += 1
            issues: List[dict] = []
            mm = re.match(r"^(\d{6})(\d{4})?(R?[CD])([A-Z])?([\d,\.]+)([A-Z][A-Z0-9]{3})([^\n]*?)(?://([^\n]*))?(?:\n.*)?$", val, re.S)
            if not mm:
                entries.append({"row": n, "date": None, "value_date": None, "description": "", "reference": None, "money_in": ZERO, "money_out": ZERO,
                                "balance": None, "currency": cur, "issues": [M.issue(M.ERROR, f"Statement line {n} is not in a readable MT940 format.", n)]})
                last = None
                continue
            vd = _mt_date(mm.group(1))
            dc = mm.group(3)
            try:
                a = _mt_amount(mm.group(5))
            except AmountError as e:
                a = ZERO
                issues.append(M.issue(M.ERROR, f"Statement line {n}: {e}", n, "amount"))
            credit = dc.endswith("C") and not dc.startswith("R") or (dc == "RD")   # reversal of a debit is money in
            signed = a if credit else -a
            if options.get("flip"):
                signed = -signed
            bank_ref = (mm.group(7) or "").strip()
            last = {"row": n, "date": vd, "value_date": vd, "description": "", "reference": clean(mm.group(8)) or clean(bank_ref) or None,
                    "money_in": signed if signed > 0 else ZERO, "money_out": -signed if signed < 0 else ZERO, "balance": None, "currency": cur, "issues": issues}
            entries.append(last)
        elif tag == "86" and last is not None:
            desc = clean(re.sub(r"\n?\?\d{2}", " ", val)) if "?" in val else clean(val.replace("\n", " "))
            last["description"] = (last["description"] + " " + desc).strip()
    if opening is None and closing is None and not entries:
        raise IngestionError("No statement lines (:61:) were found.")
    batch["mapping"] = {"format": "MT940 statement lines (:61: with :86: narrative)"}
    out = finish_bank_batch(batch, entries, opening=opening, closing=closing, period=options.get("period"), expected_currency=options.get("currency"))
    return out
