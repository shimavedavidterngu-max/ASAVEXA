"""The numbers every analysis starts from, taken straight from the posted ledger (drafts never count).

Definitions (shown to the user with every result):
  * Balance-sheet accounts (asset, liability, equity): balance AS AT the period's end date = every posted entry dated on or before that day.
  * Income-statement accounts (revenue, expense): the movement INSIDE the period = posted entries belonging to that period.
  * Total equity = assets - liabilities, so it includes any profit not yet closed into equity.
Reversed journals stay in (their reversing entry nets them out), exactly as in the ledger."""
from decimal import Decimal
from typing import Dict, List, Optional

from ..accounting.domain.enums import AccountType
from ..reporting.domain import rules as reporting_rules
from .errors import AnalysisNotFoundError
from .numbers import ZERO, r2

ASSET_TAGS = {"CASH": "Cash and bank", "RECEIVABLE": "Trade receivables", "INVENTORY": "Inventory", "CURRENT_ASSET": "Other current asset", "NONCURRENT_ASSET": "Non-current asset"}
LIABILITY_TAGS = {"PAYABLE": "Trade payables", "CURRENT_LIABILITY": "Other current liability", "NONCURRENT_LIABILITY": "Non-current liability"}
EXPENSE_TAGS = {"COST_OF_SALES": "Cost of sales", "OPERATING_EXPENSE": "Operating expense", "FINANCE_COST": "Finance cost"}
TAGS_BY_TYPE = {"ASSET": ASSET_TAGS, "LIABILITY": LIABILITY_TAGS, "EXPENSE": EXPENSE_TAGS}
ALL_TAGS = {**ASSET_TAGS, **LIABILITY_TAGS, **EXPENSE_TAGS}
CURRENT_ASSET_TAGS = {"CASH", "RECEIVABLE", "INVENTORY", "CURRENT_ASSET"}
CURRENT_LIABILITY_TAGS = {"PAYABLE", "CURRENT_LIABILITY"}
BALANCE_SHEET = {"ASSET", "LIABILITY", "EQUITY"}


def _type(a) -> str:
    return a.type.value if hasattr(a.type, "value") else str(a.type)


def previous_period(accounting, org_id: str, period) -> Optional[object]:
    earlier = [p for p in accounting.periods.list_for_org(org_id) if p.end_date < period.start_date]
    return max(earlier, key=lambda p: p.end_date) if earlier else None


def collect_figures(accounting, org_id: str, period_id: str, tags: Dict[str, str]) -> dict:
    period = accounting.periods.get(org_id, period_id)
    if period is None:
        raise AnalysisNotFoundError("That accounting period was not found in this organisation.")
    rows: List[dict] = []
    for a in sorted(accounting.accounts.list_for_org(org_id), key=lambda x: x.code):
        t = _type(a)
        if t in BALANCE_SHEET:
            entries = [e for e in accounting.get_ledger(org_id, a.id) if e["date"] <= period.end_date]
            basis = "AS_AT"
        else:
            entries = accounting.get_ledger(org_id, a.id, period_id=period_id)
            basis = "PERIOD"
        debit = sum((Decimal(e["debit"]) for e in entries), ZERO)
        credit = sum((Decimal(e["credit"]) for e in entries), ZERO)
        amount = r2(reporting_rules.normal_balance_amount(a.type, debit, credit))
        rows.append({"id": a.id, "code": a.code, "name": a.name, "type": t, "currency": a.currency, "amount": amount, "basis": basis, "tag": tags.get(a.id), "entries": len(entries)})
    def tot(kind): return sum((r["amount"] for r in rows if r["type"] == kind), ZERO)
    assets, liabilities, equity_recorded, revenue, expenses = tot("ASSET"), tot("LIABILITY"), tot("EQUITY"), tot("REVENUE"), tot("EXPENSE")
    live = [r for r in rows if r["amount"] != 0]
    return {
        "org_id": org_id,
        "period": {"id": period.id, "name": period.name, "start": str(period.start_date), "end": str(period.end_date), "days": (period.end_date - period.start_date).days + 1,
                   "status": period.status.value if hasattr(period.status, "value") else str(period.status)},
        "accounts": rows,
        "assets": assets, "liabilities": liabilities, "equity_recorded": equity_recorded, "equity_total": r2(assets - liabilities),
        "revenue": revenue, "expenses": expenses, "net_income": r2(revenue - expenses),
        "currencies": sorted({r["currency"] for r in live}),
        "posted_entries": sum(r["entries"] for r in rows),
    }


def refs(rows: List[dict]) -> List[dict]:
    return [{"id": r["id"], "code": r["code"], "name": r["name"], "amount": str(r["amount"])} for r in rows]
