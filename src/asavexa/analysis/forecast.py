"""Cash-flow forecast, sensitivity and break-even. These are FORECASTS built from stated assumptions. They are never posted to the ledger and never presented as actuals or advice.
Method (model 'cashflow-simple-1'): month m revenue = base monthly revenue x (1 + monthly revenue growth)^m, expenses likewise; net cash movement = revenue - expenses (a cash-basis simplification:
timing of receipts and payments is ignored); closing cash = opening cash + running total. Each month is rounded to 2 decimals before it is added, so a hand recalculation gives the same digits."""
from decimal import ROUND_CEILING, Decimal
from typing import List, Optional

from .errors import AnalysisError
from .numbers import ZERO, dec, r2, s2

MODEL = "cashflow-simple-1"
SENSITIVITY_STEPS = (Decimal("-5"), Decimal("-2.5"), Decimal("0"), Decimal("2.5"), Decimal("5"))   # percentage points of monthly revenue growth


def clean_assumptions(a: dict) -> dict:
    if not isinstance(a, dict):
        raise AnalysisError("Assumptions are required.")
    months = a.get("months")
    if isinstance(months, bool) or not str(months).strip().isdigit() or not 1 <= int(months) <= 24:
        raise AnalysisError("Months must be a whole number from 1 to 24.")
    return {"months": int(months),
            "base_monthly_revenue": str(dec(a.get("base_monthly_revenue"), "Base monthly revenue", lo=0)),
            "base_monthly_expenses": str(dec(a.get("base_monthly_expenses"), "Base monthly expenses", lo=0)),
            "revenue_growth_pct": str(dec(a.get("revenue_growth_pct", 0), "Monthly revenue growth (%)", lo=-100, hi=1000)),
            "expense_growth_pct": str(dec(a.get("expense_growth_pct", 0), "Monthly expense growth (%)", lo=-100, hi=1000)),
            "opening_cash": str(dec(a.get("opening_cash"), "Opening cash"))}


def project(a: dict, revenue_growth_override: Optional[Decimal] = None) -> List[dict]:
    rev0, exp0 = Decimal(a["base_monthly_revenue"]), Decimal(a["base_monthly_expenses"])
    gr = Decimal(a["revenue_growth_pct"]) if revenue_growth_override is None else revenue_growth_override
    ge = Decimal(a["expense_growth_pct"])
    cash = Decimal(a["opening_cash"])
    fr, fe = Decimal(1), Decimal(1)
    rows = []
    for m in range(1, int(a["months"]) + 1):
        fr *= 1 + gr / 100
        fe *= 1 + ge / 100
        rev, exp = r2(rev0 * fr), r2(exp0 * fe)
        net = r2(rev - exp)
        cash = r2(cash + net)
        rows.append({"month": m, "revenue": s2(rev), "expenses": s2(exp), "net_cash": s2(net), "closing_cash": s2(cash), "kind": "FORECAST"})
    return rows


def run(a: dict) -> dict:
    rows = project(a)
    low = min(rows, key=lambda r: Decimal(r["closing_cash"]))
    first_neg = next((r["month"] for r in rows if Decimal(r["closing_cash"]) < 0), None)
    sens = []
    for step in SENSITIVITY_STEPS:
        g = Decimal(a["revenue_growth_pct"]) + step
        pr = project(a, g)
        sens.append({"revenue_growth_pct": str(g), "change_points": str(step), "closing_cash": pr[-1]["closing_cash"],
                     "lowest_cash": str(min(Decimal(r["closing_cash"]) for r in pr)), "first_month_negative": next((r["month"] for r in pr if Decimal(r["closing_cash"]) < 0), None)})
    return {"model": MODEL, "kind": "FORECAST", "assumptions": a, "rows": rows, "closing_cash": rows[-1]["closing_cash"], "lowest_cash": low["closing_cash"], "lowest_cash_month": low["month"],
            "first_month_negative": first_neg, "sensitivity": sens,
            "limits": "A forecast from the assumptions above, not an actual result and not advice. Receipt and payment timing, tax, financing and one-off items are not modelled. It is never written to the ledger."}


def breakeven(fixed_costs, price, variable_cost) -> dict:
    fixed = dec(fixed_costs, "Fixed costs", lo=0)
    p = dec(price, "Selling price per unit", lo=0)
    v = dec(variable_cost, "Variable cost per unit", lo=0)
    cm = p - v
    if cm <= 0:
        raise AnalysisError("The selling price must be higher than the variable cost per unit, otherwise each sale loses money and there is no break-even point.")
    units = int((fixed / cm).to_integral_value(rounding=ROUND_CEILING))
    rows = []
    for pct in (Decimal("-10"), Decimal("0"), Decimal("10")):
        pp = r2(p * (1 + pct / 100))
        c = pp - v
        rows.append({"price_change_pct": str(pct), "price": s2(pp), "units": None if c <= 0 else str(int((fixed / c).to_integral_value(rounding=ROUND_CEILING))), "note": "no break-even at this price" if c <= 0 else ""})
    return {"kind": "FORECAST", "fixed_costs": s2(fixed), "price": s2(p), "variable_cost": s2(v), "contribution_per_unit": s2(cm), "contribution_margin_pct": str(r2(cm / p * 100)) if p else None,
            "break_even_units": str(units), "break_even_revenue": s2(Decimal(units) * p), "price_sensitivity": rows,
            "formula": "break-even units = fixed costs / (price - variable cost per unit), rounded up to a whole unit",
            "limits": "Assumes price and variable cost per unit stay the same at every volume and fixed costs do not step up. It is an estimate, not a guarantee."}


def suggest(fig: dict) -> dict:
    """Starting points taken from the period's actuals (monthly = period amount x 30 / days), for the user to review and change."""
    days = fig["period"]["days"]
    cash = [r for r in fig["accounts"] if r["tag"] == "CASH"]
    return {"base_monthly_revenue": s2(fig["revenue"] * 30 / days), "base_monthly_expenses": s2(fig["expenses"] * 30 / days),
            "opening_cash": s2(sum((r["amount"] for r in cash), ZERO)) if cash else None,
            "opening_cash_note": "From accounts marked Cash and bank at the end of the period." if cash else "No account is marked Cash and bank yet, so enter the opening cash yourself.",
            "basis": f"Period actuals scaled to a 30-day month ({days}-day period)."}
