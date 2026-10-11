"""Variance analysis: this period against the previous one, and against a budget someone entered. A material variance is a prompt to ask why, not a conclusion."""
from decimal import Decimal
from typing import Dict, List, Optional

from .numbers import ZERO, r1, r2, s2

DEFAULT_THRESHOLDS = {"percent": "10", "amount": "0"}
IS_TYPES = {"REVENUE", "EXPENSE"}


def _pct(change: Decimal, base: Decimal) -> Optional[Decimal]:
    return None if base == 0 else r1(change / abs(base) * 100)


def _material(change: Decimal, pct: Optional[Decimal], th: dict) -> bool:
    if change == 0:
        return False
    if abs(change) < Decimal(th["amount"]):
        return False
    return pct is None or abs(pct) >= Decimal(th["percent"])


def period_variance(cur: dict, prior: Optional[dict], th: dict, comments: Dict[str, List[dict]]) -> dict:
    if prior is None:
        return {"status": "NO_PRIOR_PERIOD", "message": "There is no earlier period to compare with.", "rows": [], "thresholds": th}
    before = {r["id"]: r for r in prior["accounts"]}
    rows = []
    for r in cur["accounts"]:
        p = before.get(r["id"])
        prev = p["amount"] if p else ZERO
        if r["amount"] == 0 and prev == 0:
            continue
        change = r2(r["amount"] - prev)
        pct = _pct(change, prev)
        rows.append({"account_id": r["id"], "code": r["code"], "name": r["name"], "type": r["type"], "basis": r["basis"], "current": s2(r["amount"]), "prior": s2(prev), "change": s2(change),
                     "change_pct": None if pct is None else str(pct), "is_new": prev == 0, "material": _material(change, pct, th), "comments": comments.get(r["id"], [])})
    return {"status": "OK", "current_period": cur["period"], "prior_period": prior["period"], "rows": rows, "material_count": sum(1 for x in rows if x["material"]), "thresholds": th,
            "basis_note": "Revenue and expenses are the movement inside each period. Assets, liabilities and equity are balances at each period's end."}


def budget_variance(cur: dict, lines: Optional[Dict[str, Decimal]], th: dict, meta: Optional[dict], comments: Dict[str, List[dict]]) -> dict:
    if not lines:
        return {"status": "NO_BUDGET", "message": "No comparison budget has been entered for this period.", "rows": [], "thresholds": th}
    by_id = {r["id"]: r for r in cur["accounts"] if r["type"] in IS_TYPES}
    rows = []
    for aid in sorted(set(by_id) | set(lines), key=lambda x: by_id[x]["code"] if x in by_id else x):
        acc = by_id.get(aid)
        if acc is None:
            continue
        budget, actual = Decimal(lines.get(aid, ZERO)), acc["amount"]
        if budget == 0 and actual == 0:
            continue
        var = r2(actual - budget)
        pct = _pct(var, budget)
        favourable = None if var == 0 else (var > 0 if acc["type"] == "REVENUE" else var < 0)
        rows.append({"account_id": aid, "code": acc["code"], "name": acc["name"], "type": acc["type"], "budget": s2(budget), "actual": s2(actual), "variance": s2(var),
                     "variance_pct": None if pct is None else str(pct), "favourable": favourable, "material": _material(var, pct, th), "comments": comments.get(aid, [])})
    return {"status": "OK", "period": cur["period"], "budget": meta, "rows": rows, "material_count": sum(1 for x in rows if x["material"]), "thresholds": th,
            "basis_note": "BUDGET is a figure entered by a person for comparison. It is not an approved budget from a budgeting module. Actual is the posted ledger."}
