"""Pure tax arithmetic. It knows nothing about any country: every rate and band is passed in from a reviewed rule. Decimal only; the rounding mode is part of the rule."""
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import List, Optional

from .errors import TaxError

Q2 = Decimal("0.01")
ROUNDING = {"HALF_UP": ROUND_HALF_UP, "DOWN": ROUND_DOWN, "HALF_EVEN": ROUND_HALF_EVEN}


def dec(v, name="value", lo=None, hi=None) -> Decimal:
    if v is None or isinstance(v, bool) or (isinstance(v, str) and not v.strip()):
        raise TaxError(f"{name} is required and must be a number.")
    try:
        x = Decimal(str(v).strip())
    except (InvalidOperation, ValueError):
        raise TaxError(f"{name} must be a number.")
    if not x.is_finite():
        raise TaxError(f"{name} must be a number.")
    if lo is not None and x < Decimal(str(lo)):
        raise TaxError(f"{name} must be at least {lo}.")
    if hi is not None and x > Decimal(str(hi)):
        raise TaxError(f"{name} must be at most {hi}.")
    return x


def q2(x: Decimal, mode: str = "HALF_UP") -> Decimal:
    return Decimal(x).quantize(Q2, rounding=ROUNDING[mode])


def clean_brackets(brackets) -> List[dict]:
    """Validates progressive bands: start at 0, each band begins where the last ended, only the last may be open-ended, rates 0 to 100."""
    if not isinstance(brackets, list) or not brackets:
        raise TaxError("Enter at least one tax band.")
    if len(brackets) > 30:
        raise TaxError("Too many bands (limit 30).")
    out, expect = [], Decimal(0)
    for i, b in enumerate(brackets):
        if not isinstance(b, dict):
            raise TaxError("Each band must have a start, an end and a rate.")
        lo = dec(b.get("from"), f"Band {i + 1} start", lo=0)
        up = b.get("up_to")
        hi = None if up in (None, "") else dec(up, f"Band {i + 1} end", lo=0)
        rate = dec(b.get("rate"), f"Band {i + 1} rate", lo=0, hi=100)
        if lo != expect:
            raise TaxError(f"Band {i + 1} must start at {expect} (where the previous band ends); it starts at {lo}.")
        if hi is None and i != len(brackets) - 1:
            raise TaxError("Only the last band can be open-ended.")
        if hi is not None and hi <= lo:
            raise TaxError(f"Band {i + 1} must end above where it starts.")
        out.append({"from": str(lo), "up_to": None if hi is None else str(hi), "rate": str(rate)})
        expect = hi if hi is not None else expect
    return out


def flat(amount: Decimal, rate_pct: Decimal, inclusive: bool, mode: str) -> dict:
    """Exclusive: tax = amount x rate. Inclusive: the amount already contains tax, so net = amount / (1 + rate) and tax = amount - net."""
    if inclusive:
        net = q2(amount / (1 + rate_pct / 100), mode)
        tax = q2(amount - net, mode)
        return {"net": net, "tax": tax, "gross": q2(amount, mode), "steps": [f"Net = {amount} / (1 + {rate_pct}/100) = {net}", f"Tax = {amount} - {net} = {tax}"]}
    tax = q2(amount * rate_pct / 100, mode)
    return {"net": q2(amount, mode), "tax": tax, "gross": q2(amount + tax, mode), "steps": [f"Tax = {amount} x {rate_pct}% = {tax}", f"Gross = {amount} + {tax} = {q2(amount + tax, mode)}"]}


def progressive(amount: Decimal, brackets: List[dict], mode: str) -> dict:
    total, steps, bands = Decimal(0), [], []
    for b in brackets:
        lo, hi, rate = Decimal(b["from"]), (None if b["up_to"] is None else Decimal(b["up_to"])), Decimal(b["rate"])
        if amount <= lo:
            break
        slice_ = (amount if hi is None else min(amount, hi)) - lo
        part = slice_ * rate / 100
        total += part
        bands.append({"from": b["from"], "up_to": b["up_to"], "rate": b["rate"], "taxed": str(q2(slice_, mode)), "tax": str(q2(part, mode))})
        steps.append(f"{q2(slice_, mode)} taxed at {rate}% = {q2(part, mode)}")
    tax = q2(total, mode)
    steps.append(f"Total tax = {tax}")
    top = amount > Decimal(brackets[-1]["up_to"]) if brackets[-1]["up_to"] is not None else False
    return {"net": q2(amount, mode), "tax": tax, "gross": None, "bands": bands, "steps": steps, "above_last_band": top,
            "effective_rate_pct": None if amount == 0 else str((tax / amount * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))}
