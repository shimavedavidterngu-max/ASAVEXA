"""Financial ratios with their working shown: formula, numerator, denominator, the accounts that make them up, and a plain-words reading.
A ratio that cannot be calculated honestly says why (INCOMPLETE: something is not classified yet; UNDEFINED: the denominator is zero) and never shows a guessed number.
Nothing here is a verdict: a ratio is one input for professional judgement and acceptable levels depend on the industry."""
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, Dict, List, Optional

from .figures import CURRENT_ASSET_TAGS, CURRENT_LIABILITY_TAGS, refs
from .numbers import Q1, Q2, ZERO, r2

CALCULATED, INCOMPLETE, UNDEFINED = "CALCULATED", "INCOMPLETE", "UNDEFINED"


def _sum(rows): return sum((r["amount"] for r in rows), ZERO)


def compute_ratios(fig: dict) -> List[dict]:
    rows = fig["accounts"]
    assets = [r for r in rows if r["type"] == "ASSET"]
    liabs = [r for r in rows if r["type"] == "LIABILITY"]
    exps = [r for r in rows if r["type"] == "EXPENSE"]
    revenue_rows = [r for r in rows if r["type"] == "REVENUE" and r["amount"] != 0]
    multi_currency = len(fig["currencies"]) > 1
    days = fig["period"]["days"]

    unclassified_bs = [r for r in assets + liabs if r["amount"] != 0 and not r["tag"]]
    unclassified_exp = [r for r in exps if r["amount"] != 0 and not r["tag"]]
    ca = [r for r in assets if r["tag"] in CURRENT_ASSET_TAGS and r["amount"] != 0]
    cl = [r for r in liabs if r["tag"] in CURRENT_LIABILITY_TAGS and r["amount"] != 0]
    cash = [r for r in assets if r["tag"] == "CASH" and r["amount"] != 0]
    inv = [r for r in assets if r["tag"] == "INVENTORY" and r["amount"] != 0]
    recv = [r for r in assets if r["tag"] == "RECEIVABLE" and r["amount"] != 0]
    pay = [r for r in liabs if r["tag"] == "PAYABLE" and r["amount"] != 0]
    cogs = [r for r in exps if r["tag"] == "COST_OF_SALES" and r["amount"] != 0]
    opex = [r for r in exps if r["tag"] == "OPERATING_EXPENSE" and r["amount"] != 0]
    all_assets = [r for r in assets if r["amount"] != 0]
    all_liabs = [r for r in liabs if r["amount"] != 0]
    revenue = fig["revenue"]

    def names(rs): return ", ".join(f"{r['code']} {r['name']}" for r in rs)

    def part(label, amount, rs): return {"label": label, "amount": str(r2(amount)), "accounts": refs(rs)}

    def make(rid, name, group, formula, unit, num, den, fn: Callable[[Decimal, Decimal], Decimal], reading, need_bs=False, need_exp=False, need_tag=None, den_label=None, scale=None) -> dict:
        out = {"id": rid, "name": name, "group": group, "formula": formula, "unit": unit, "numerator": num, "denominator": den, "value": None, "status": CALCULATED, "reason": "", "reading": reading}
        if multi_currency:
            out.update(status=INCOMPLETE, reason=f"Accounts with balances use more than one currency ({', '.join(fig['currencies'])}); ASAVEXA does not convert currencies, so ratios would mix them.")
        elif need_bs and unclassified_bs:
            out.update(status=INCOMPLETE, reason=f"Every asset and liability with a balance must be marked current or non-current first. Not yet classified: {names(unclassified_bs)}.")
        elif need_exp and unclassified_exp:
            out.update(status=INCOMPLETE, reason=f"Every expense with a balance must be classified (cost of sales, operating or finance cost) first. Not yet classified: {names(unclassified_exp)}.")
        elif need_tag and not any(r["tag"] == need_tag[0] for r in rows):
            out.update(status=INCOMPLETE, reason=f"No account is marked as {need_tag[1]}. Mark the right account in Setup to calculate this.")
        else:
            n, d = Decimal(num["amount"]), Decimal(den["amount"]) if den else Decimal(1)
            if den is not None and d == 0:
                out.update(status=UNDEFINED, reason=f"{den['label']} is zero, so the ratio has no meaning for this period.")
            else:
                out["value"] = str(fn(n, d).quantize(Q1 if unit == "days" else Q2, rounding=ROUND_HALF_UP))
        return out

    pct = lambda n, d: n / d * 100
    ratio = lambda n, d: n / d
    amount = lambda n, d: n
    net_income = fig["net_income"]
    cogs_t, opex_t = _sum(cogs), _sum(opex)

    out = [
        make("current_ratio", "Current ratio", "Liquidity", "current assets / current liabilities", "ratio", part("Current assets", _sum(ca), ca), part("Current liabilities", _sum(cl), cl), ratio,
             "Short-term assets available for each 1 of short-term obligations. Below 1 means short-term obligations are larger than short-term assets.", need_bs=True),
        make("quick_ratio", "Quick ratio", "Liquidity", "(current assets - inventory) / current liabilities", "ratio", part("Current assets less inventory", _sum(ca) - _sum(inv), ca), part("Current liabilities", _sum(cl), cl), ratio,
             "Like the current ratio but without stock, which can be slow to turn into cash.", need_bs=True),
        make("cash_ratio", "Cash ratio", "Liquidity", "cash and bank / current liabilities", "ratio", part("Cash and bank", _sum(cash), cash), part("Current liabilities", _sum(cl), cl), ratio,
             "Cash on hand for each 1 of short-term obligations.", need_bs=True, need_tag=("CASH", "Cash and bank")),
        make("working_capital", "Working capital", "Liquidity", "current assets - current liabilities", "amount", part("Current assets less current liabilities", _sum(ca) - _sum(cl), ca + cl), None, amount,
             "The amount by which short-term assets exceed (or fall short of) short-term obligations.", need_bs=True),
        make("gross_margin", "Gross margin", "Profitability", "(revenue - cost of sales) / revenue x 100", "percent", part("Revenue less cost of sales", revenue - cogs_t, revenue_rows + cogs), part("Revenue", revenue, revenue_rows), pct,
             "The share of each unit of revenue left after the direct cost of what was sold.", need_exp=True, need_tag=("COST_OF_SALES", "Cost of sales")),
        make("operating_margin", "Operating margin", "Profitability", "(revenue - cost of sales - operating expenses) / revenue x 100", "percent", part("Operating result", revenue - cogs_t - opex_t, revenue_rows + cogs + opex), part("Revenue", revenue, revenue_rows), pct,
             "The share of revenue left after running costs, before finance costs.", need_exp=True, need_tag=("OPERATING_EXPENSE", "Operating expense")),
        make("net_margin", "Net margin", "Profitability", "net income / revenue x 100", "percent", part("Net income for the period", net_income, revenue_rows + [r for r in exps if r["amount"] != 0]), part("Revenue", revenue, revenue_rows), pct,
             "The share of revenue that remains as profit after all expenses in the period."),
        make("return_on_assets", "Return on assets (for the period)", "Profitability", "net income for the period / total assets at period end x 100", "percent", part("Net income for the period", net_income, []), part("Total assets", fig["assets"], all_assets), pct,
             "Profit earned in this period for each 100 of assets held at its end. It is not annualised."),
        make("debt_ratio", "Debt ratio", "Leverage", "total liabilities / total assets", "ratio", part("Total liabilities", fig["liabilities"], all_liabs), part("Total assets", fig["assets"], all_assets), ratio,
             "The share of assets financed by liabilities. Closer to 1 means more of the assets are owed to others."),
        make("debt_to_equity", "Debt to equity", "Leverage", "total liabilities / total equity", "ratio", part("Total liabilities", fig["liabilities"], all_liabs), part("Total equity (assets - liabilities)", fig["equity_total"], all_assets + all_liabs), ratio,
             "Liabilities for each 1 of equity. Equity here includes profit not yet closed into equity."),
        make("equity_ratio", "Equity ratio", "Leverage", "total equity / total assets", "ratio", part("Total equity (assets - liabilities)", fig["equity_total"], all_assets + all_liabs), part("Total assets", fig["assets"], all_assets), ratio,
             "The share of assets owned outright after settling all liabilities."),
        make("receivable_days", "Receivable days", "Working capital", f"trade receivables / revenue x {days} days in the period", "days", part("Trade receivables", _sum(recv), recv), part("Revenue", revenue, revenue_rows), lambda n, d: n / d * days,
             "The average number of days of sales still waiting to be collected.", need_tag=("RECEIVABLE", "Trade receivables")),
        make("payable_days", "Payable days", "Working capital", f"trade payables / cost of sales x {days} days in the period", "days", part("Trade payables", _sum(pay), pay), part("Cost of sales", cogs_t, cogs), lambda n, d: n / d * days,
             "The average number of days of purchases still unpaid.", need_exp=True, need_tag=("PAYABLE", "Trade payables")),
        make("inventory_days", "Inventory days", "Working capital", f"inventory / cost of sales x {days} days in the period", "days", part("Inventory", _sum(inv), inv), part("Cost of sales", cogs_t, cogs), lambda n, d: n / d * days,
             "The average number of days of cost of sales held in stock.", need_exp=True, need_tag=("INVENTORY", "Inventory")),
    ]
    return out


def ratio_values(ratios: List[dict]) -> Dict[str, Optional[str]]:
    return {r["id"]: r["value"] for r in ratios}
