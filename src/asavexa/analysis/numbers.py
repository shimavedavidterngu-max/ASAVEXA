"""Decimal helpers. Money and ratios are never floats. Rounding is always ROUND_HALF_UP so an independent recalculation gives the same digits."""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .errors import AnalysisError

ZERO = Decimal("0.00")
Q2, Q1, Q4 = Decimal("0.01"), Decimal("0.1"), Decimal("0.0001")


def dec(v, name="value", lo=None, hi=None, required=True):
    if v is None or (isinstance(v, str) and not v.strip()):
        if required:
            raise AnalysisError(f"{name} is required.")
        return None
    if isinstance(v, bool):
        raise AnalysisError(f"{name} must be a number.")
    try:
        x = Decimal(str(v).strip())
    except (InvalidOperation, ValueError):
        raise AnalysisError(f"{name} must be a number.")
    if not x.is_finite():
        raise AnalysisError(f"{name} must be a number.")
    if lo is not None and x < Decimal(str(lo)):
        raise AnalysisError(f"{name} must be at least {lo}.")
    if hi is not None and x > Decimal(str(hi)):
        raise AnalysisError(f"{name} must be at most {hi}.")
    return x


def r2(x) -> Decimal: return Decimal(x).quantize(Q2, rounding=ROUND_HALF_UP)
def r1(x) -> Decimal: return Decimal(x).quantize(Q1, rounding=ROUND_HALF_UP)
def s2(x) -> str: return str(r2(x))
def s_or_none(x, q=Q2):
    return None if x is None else str(Decimal(x).quantize(q, rounding=ROUND_HALF_UP))
