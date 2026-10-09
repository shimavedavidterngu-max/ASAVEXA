"""Level 4: read the TEXT of a PDF. Scanned/photographed PDFs have no text and are reported as unreadable (no OCR)."""
from __future__ import annotations

import io
import re
from datetime import date
from decimal import Decimal
from typing import List, Optional, Tuple

from . import model as M
from .bank import finish_bank_batch
from .errors import IngestionError, NoTextError, UnsupportedFileError
from .util import AmountError, DATE_FORMATS, clean, detect_date_format, parse_amount, parse_date_with

MAX_PAGES = 60
ZERO = Decimal("0.00")


def extract_pdf_text(content: bytes) -> Tuple[str, int]:
    if content[:5] != b"%PDF-":
        raise UnsupportedFileError("This is not a PDF file.")
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError:  # pragma: no cover
        raise IngestionError("PDF support is not installed on this server (pypdf).")
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            try:
                ok = reader.decrypt("")
            except Exception:
                ok = 0
            if not ok:
                raise UnsupportedFileError("This PDF is password protected. Remove the password and upload it again.")
        n = len(reader.pages)
        if n > MAX_PAGES:
            raise IngestionError(f"This PDF has {n} pages; the limit is {MAX_PAGES}. Split it and import each part.")
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
    except (IngestionError, UnsupportedFileError):
        raise
    except PdfReadError as e:
        raise UnsupportedFileError(f"The PDF could not be read: {e}")
    except Exception as e:
        raise UnsupportedFileError(f"The PDF could not be read: {type(e).__name__}")
    if len(re.sub(r"\s+", "", text)) < 20:
        raise NoTextError("This PDF has no readable text; it looks like a scan or photo. ASAVEXA does not read images (no OCR). "
                                   "Upload the bank's CSV/Excel/OFX file, or keep this PDF as evidence only.")
    return text, n


AMT = r"\(?-?[\d]{1,3}(?:,\d{3})*(?:\.\d{2})\)?(?:\s?(?:CR|DR|Cr|Dr))?|\(?-?\d+\.\d{2}\)?(?:\s?(?:CR|DR|Cr|Dr))?"
AMT_RE = re.compile(rf"(?<![\w.,/-])({AMT})(?![\w/])")
DATE_RES = [
    r"\d{4}-\d{2}-\d{2}", r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", r"\d{1,2}[ -](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*[ -,]*\d{2,4}",
]
LEAD_DATE = re.compile(r"^\s*(" + "|".join(DATE_RES) + r")\b\s*(.*)$", re.I)
SKIP_LINE = re.compile(r"^(page\s+\d+|statement of account|account (number|no|name)|date\s+(description|details|narration)|continued|\*+|--+)", re.I)
BALANCE_LINE = re.compile(r"(opening|closing|balance (b/f|c/f|brought|carried)|brought forward|carried forward)", re.I)


def _norm_date_text(s: str) -> str:
    s = s.replace("Sept", "Sep")
    s = re.sub(r"(?<=\d)[ ]+(?=[A-Za-z])", " ", s)
    return s


def stage_pdf_statement(filename: str, text: str, pages: int, source: dict, options: dict) -> dict:
    batch = M.new_batch("BANK_TRANSACTIONS", source, {k: v for k, v in options.items() if k in ("date_format", "flip")})
    batch["source"].update({"format": "PDF", "pages": pages})
    lines = [clean(l) for l in text.splitlines()]
    opening = closing = None
    raw: List[dict] = []
    for ln, line in enumerate(lines, 1):
        if not line:
            continue
        if BALANCE_LINE.search(line) and not LEAD_DATE.match(line):
            amts = AMT_RE.findall(line)
            if amts:
                try:
                    v = parse_amount(amts[-1])
                except AmountError:
                    v = None
                if v is not None:
                    low = line.lower()
                    if any(w in low for w in ("opening", "b/f", "brought")) and opening is None:
                        opening = v
                    elif any(w in low for w in ("closing", "c/f", "carried")):
                        closing = v
            continue
        m = LEAD_DATE.match(line)
        if m:
            rest = m.group(2)
            amts = [(mm.start(), mm.group(1)) for mm in AMT_RE.finditer(rest)]
            if not amts:
                raw.append({"line": ln, "date": m.group(1), "desc": rest, "amts": [], "pending": True})
                continue
            cut = amts[0][0] if len(amts) <= 3 else amts[-3][0]
            raw.append({"line": ln, "date": m.group(1), "desc": rest[:cut].strip(), "amts": [a for _, a in (amts if len(amts) <= 3 else amts[-3:])],
                        "pending": False})
        elif raw and not SKIP_LINE.match(line):
            amts = AMT_RE.findall(line)
            last = raw[-1]
            if last["pending"] and amts and len(amts) <= 3 and len(AMT_RE.sub("", line).strip()) < 40:
                last["amts"] = amts
                last["pending"] = False
            elif not amts:
                last["desc"] = (last["desc"] + " " + line).strip()
    raw = [r for r in raw if r["amts"]]
    if not raw:
        raise IngestionError("I could not find transaction lines (a date followed by amounts) in this PDF. Use the bank's CSV, Excel or OFX export instead.")
    label = options.get("date_format")
    amb = None
    if not label:
        label, fits, amb = detect_date_format([_norm_date_text(r["date"]) for r in raw])
    if label is None:
        batch["issues"].append(M.issue(M.WARNING, "The dates in this PDF use more than one style; lines that do not fit are marked as errors."))
    elif amb:
        batch["issues"].append(M.issue(M.WARNING, f"The dates could be day/month or month/day. They were read as {label}; choose the other format if they look wrong."))
    # direction from the running balance wherever it exists
    entries = []
    prev_bal = opening
    for k, r in enumerate(raw, 1):
        issues: List[dict] = []
        d = parse_date_with(_norm_date_text(r["date"]), label) if label else None
        if d is None:
            issues.append(M.issue(M.ERROR, f"The date {r['date']!r} could not be read.", r["line"], "date"))
        vals: List[Optional[Decimal]] = []
        try:
            vals = [parse_amount(a) for a in r["amts"]]
        except AmountError as e:
            issues.append(M.issue(M.ERROR, str(e), r["line"], "amount"))
            vals = []
        in_ = out = ZERO
        bal = None
        if vals:
            if len(vals) >= 2:
                bal = vals[-1]
                movers = [abs(v) for v in vals[:-1] if v is not None and v != ZERO]
                amount = movers[0] if len(movers) == 1 else None
                if amount is None:
                    issues.append(M.issue(M.ERROR, "Could not tell which amount is the transaction (there is more than one non-zero amount before the balance).", r["line"], "amount"))
                elif prev_bal is not None and prev_bal + amount == bal and prev_bal - amount != bal:
                    in_ = amount
                elif prev_bal is not None and prev_bal - amount == bal and prev_bal + amount != bal:
                    out = amount
                else:
                    sign = _hint(r["amts"][:-1], r["desc"])
                    if sign is None:
                        issues.append(M.issue(M.ERROR, "Could not tell whether this line is money in or out (no previous balance to compare with).", r["line"], "amount"))
                    elif sign > 0:
                        in_ = amount
                    else:
                        out = amount
                        # first-line guess is verified by the balance check below
                prev_bal = bal
            else:
                sign = _hint(r["amts"], r["desc"])
                amount = abs(vals[0])
                if sign is None:
                    issues.append(M.issue(M.ERROR, "Could not tell whether this line is money in or out (no balance, CR/DR marker or sign).", r["line"], "amount"))
                elif sign > 0:
                    in_ = amount
                else:
                    out = amount
        if options.get("flip"):
            in_, out = out, in_
        entries.append({"row": r["line"], "date": d, "value_date": None, "description": r["desc"], "reference": None, "money_in": in_,
                        "money_out": out, "balance": bal, "currency": None, "issues": issues})
    batch["mapping"] = {"format": "Text lines of the PDF: date, description, amount(s), balance"}
    batch["limits"] = ["PDF layouts vary. Money in/out is worked out from the running balance where there is one; otherwise from CR/DR or signs.",
                       "Check every total against the printed statement before importing."]
    return finish_bank_batch(batch, entries, opening=opening, closing=closing, period=options.get("period"), expected_currency=options.get("currency"))


def _hint(amount_tokens: List[str], desc: str) -> Optional[int]:
    for t in amount_tokens:
        up = t.upper().replace(" ", "")
        if up.endswith("CR"):
            return 1
        if up.endswith("DR"):
            return -1
        if t.startswith("(") or t.startswith("-"):
            return -1
    return None
