"""Small, strict parsers for dates, amounts and headers. Every failure is explicit; nothing is guessed silently."""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable, List, Optional, Tuple

CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("999999999999.99")

DATE_FORMATS = [
    ("%Y-%m-%d", "YYYY-MM-DD"), ("%Y/%m/%d", "YYYY/MM/DD"), ("%d/%m/%Y", "DD/MM/YYYY"), ("%m/%d/%Y", "MM/DD/YYYY"),
    ("%d-%m-%Y", "DD-MM-YYYY"), ("%m-%d-%Y", "MM-DD-YYYY"), ("%d.%m.%Y", "DD.MM.YYYY"),
    ("%d/%m/%y", "DD/MM/YY"), ("%m/%d/%y", "MM/DD/YY"), ("%d-%b-%Y", "DD-Mon-YYYY"), ("%d %b %Y", "DD Mon YYYY"),
    ("%d %B %Y", "DD Month YYYY"), ("%b %d, %Y", "Mon DD, YYYY"), ("%B %d, %Y", "Month DD, YYYY"), ("%d-%b-%y", "DD-Mon-YY"),
    ("%Y%m%d", "YYYYMMDD"),
]
LABEL_TO_FMT = {label: fmt for fmt, label in DATE_FORMATS}
PLAUSIBLE = (date(1990, 1, 1), date(2100, 12, 31))

CURRENCY_WORDS = r"(?:NGN|USD|GBP|EUR|GHS|KES|ZAR|XOF|CAD|AUD|INR|UGX|TZS|RWF)"


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def clean(v) -> str:
    if v is None:
        return ""
    return re.sub(r"\s+", " ", str(v).replace(" ", " ")).strip()


def norm_header(v) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(v).lower()).strip()


# ---------------------------------------------------------------- dates
def _try(fmt: str, text: str) -> Optional[date]:
    try:
        d = datetime.strptime(text, fmt).date()
    except ValueError:
        return None
    return d if PLAUSIBLE[0] <= d <= PLAUSIBLE[1] else None


def parse_date_with(text: str, label: str) -> Optional[date]:
    return _try(LABEL_TO_FMT[label], clean(text).split(" 00:00")[0].split("T")[0] if label.startswith("YYYY-") else clean(text))


def detect_date_format(values: Iterable[str]) -> Tuple[Optional[str], List[str], bool]:
    """Returns (best label, every label that ties for best, ambiguous?).
    The format must read a clear MAJORITY of the values (the rest become row errors). Day/month vs month/day is
    ambiguous when both read exactly as many values as each other; the caller must warn."""
    vals = []
    for v in values:
        v = clean(v)
        if v:
            vals.append(v.split("T")[0] if re.match(r"^\d{4}-\d{2}-\d{2}T", v) else (v[:10] if re.match(r"^\d{4}-\d{2}-\d{2} \d", v) else v))
    if not vals:
        return None, [], False
    counts = [(label, sum(1 for v in vals if _try(fmt, v))) for fmt, label in DATE_FORMATS]
    best = max(c for _, c in counts)
    if best == 0 or best * 2 <= len(vals):
        return None, [], False
    fits = [label for label, c in counts if c == best]
    ambiguous = any(a in fits and b in fits for a, b in (("DD/MM/YYYY", "MM/DD/YYYY"), ("DD-MM-YYYY", "MM-DD-YYYY"), ("DD/MM/YY", "MM/DD/YY")))
    return fits[0], fits, ambiguous


# ---------------------------------------------------------------- amounts
class AmountError(ValueError):
    pass


_SYMBOLS = re.compile(r"[₦$£€¢]|" + CURRENCY_WORDS, re.I)


def parse_amount(raw) -> Optional[Decimal]:
    """Blank -> None. Handles (1,234.50), -1,234.50, 1.234,50, 1 234,50, 1,234.50CR/DR, trailing minus.
    Returns a signed Decimal rounded to cents only if no precision is lost; otherwise raises AmountError."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise AmountError("a yes/no value is not an amount")
    if isinstance(raw, Decimal):
        d = raw
    elif isinstance(raw, int):
        d = Decimal(raw)
    elif isinstance(raw, float):
        if raw != raw or raw in (float("inf"), float("-inf")):
            raise AmountError("not a number")
        d = Decimal(repr(raw))
    else:
        s = clean(raw)
        if s in ("", "-", "--", "—", "n/a", "N/A", "nil", "NIL"):
            return None
        neg = False
        if s.startswith("(") and s.endswith(")"):
            neg, s = True, s[1:-1]
        m = re.search(r"\s*(CR|DR)\.?$", s, re.I)
        suffix = None
        if m:
            suffix, s = m.group(1).upper(), s[:m.start()]
        s = _SYMBOLS.sub("", s).replace(" ", "").replace("'", "")
        if s.endswith("-"):
            neg, s = not neg, s[:-1]
        if s.startswith("+"):
            s = s[1:]
        if s.startswith("-"):
            neg, s = not neg, s[1:]
        if not re.match(r"^[0-9.,]+$", s) or not re.search(r"\d", s):
            raise AmountError(f"{clean(raw)!r} is not an amount")
        if "," in s and "." in s:
            dec = "," if s.rfind(",") > s.rfind(".") else "."
            thou = "." if dec == "," else ","
            s = s.replace(thou, "").replace(dec, ".")
        elif "," in s:
            if re.match(r"^\d{1,3}(,\d{3})+$", s):
                s = s.replace(",", "")
            elif re.match(r"^\d+,\d{1,2}$", s):
                s = s.replace(",", ".")
            else:
                raise AmountError(f"{clean(raw)!r} has commas in an unclear place")
        elif s.count(".") > 1:
            if re.match(r"^\d{1,3}(\.\d{3})+$", s):
                s = s.replace(".", "")
            else:
                raise AmountError(f"{clean(raw)!r} has more than one decimal point")
        try:
            d = Decimal(s)
        except InvalidOperation:
            raise AmountError(f"{clean(raw)!r} is not an amount")
        if neg:
            d = -d
        if suffix == "DR":
            d = -abs(d)          # caller decides what DR means; we only report a sign marker
        elif suffix == "CR":
            d = abs(d)
    if d.is_nan() or d.is_infinite():
        raise AmountError("not a number")
    q = d.quantize(CENT)
    if q != d and abs(q - d) > Decimal("0.0000001"):
        raise AmountError(f"{d} has more than two decimal places; refusing to round money silently")
    if abs(q) > MAX_AMOUNT:
        raise AmountError("amount is implausibly large")
    return q


def money(d: Decimal) -> str:
    return f"{d:.2f}"
