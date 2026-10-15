"""Valuation (records and evidence): workpapers whose methods are worked out from typed inputs, weighted into a concluded value, and reviewed by a different person.

Records (shared document store, per organisation): vl_case, vl_setting.

Principles enforced here
  * This works out a value from the inputs people type in (a multiple of a metric, discounted cash flows, assets less liabilities) with exact decimal arithmetic and combines the methods by the weights they type. It reads no market data, chooses no inputs, gives no opinion of value and is not a valuation report.
  * A workpaper is prepared, submitted with a written rationale, and approved or returned by a person other than the one who submitted it. An approved workpaper is final; a changed view is a new workpaper.
  * Values are kept per currency and never added across currencies.
Nothing is edited after approval or deleted; a method is marked removed with a reason. Every step is audited. No valuation standard is claimed.
"""
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Callable, List

from .errors import ValuationError, ValuationForbiddenError, ValuationNotFoundError, ValuationStateError

SUBJECT_KINDS = ["BUSINESS", "SHARES", "PROPERTY", "EQUIPMENT", "INTANGIBLE", "OTHER"]
PURPOSES = ["TRANSACTION", "REPORTING", "TAX", "LENDING", "INTERNAL", "OTHER"]
BASES = ["MARKET_VALUE", "FAIR_VALUE", "INVESTMENT_VALUE", "LIQUIDATION_VALUE", "OTHER"]
METHOD_KINDS = ["MULTIPLE", "DCF", "ASSET_BASED"]
DEFAULTS = {"review_days": 365}
CENT = Decimal("0.01")
MAX_METHODS = 5
MAX_PERIODS = 15
LIMITATIONS = [
    "ASAVEXA works out a value from the inputs people type in. It reads no market data, chooses no multiples, rates or cash flows, and gives no opinion of value. It is not a valuation report.",
    "Every input is a person's statement. ASAVEXA cannot tell whether a multiple is comparable, a forecast is reasonable or a discount rate is appropriate.",
    "Discounted cash flow uses end-of-period cash flows, one discount rate for every period and an optional growth-in-perpetuity terminal value on the last cash flow. Mid-year timing, changing rates, tax and working-capital adjustments are not handled.",
    "The concluded value is the typed weights applied to the method results. The range shown is only the lowest and highest method result.",
    "No valuation standard (IVS, IFRS 13 or any other) is applied or claimed, and the basis of value is a label that a person types.",
    "Values in different currencies are never added together. A workpaper that is approved is final; a changed view needs a new workpaper.",
]


def _utc(): return datetime.now(timezone.utc)


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v)))
    v = " ".join("".join(c if c >= " " and c != "\x7f" else " " for c in v).split())
    if required and len(v) < lo:
        raise ValuationError(f"{name} is required (at least {lo} characters).")
    if v and len(v) < lo:
        raise ValuationError(f"{name} needs at least {lo} characters.")
    if len(v) > hi:
        raise ValuationError(f"{name} is too long (limit {hi} characters).")
    return v


def _date(v, name) -> date:
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", str(v).strip()): raise ValueError
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise ValuationError(f"{name} must be a real date written YYYY-MM-DD.")


def _enum(v, allowed, name) -> str:
    v = _txt(v, name, 1, 40).upper()
    if v not in allowed:
        raise ValuationError(f"{name} must be one of {', '.join(allowed)}.")
    return v


def _int(v, name, lo, hi) -> int:
    if isinstance(v, bool) or not re.fullmatch(r"[0-9]{1,15}", str(v).strip()):
        raise ValuationError(f"{name} must be a whole number from {lo} to {hi}.")
    n = int(str(v).strip())
    if not lo <= n <= hi:
        raise ValuationError(f"{name} must be a whole number from {lo} to {hi}.")
    return n


def _num(v, name, int_digits, places, example, zero_ok=False) -> Decimal:
    """A number written as text or a whole number: ASCII digits, at most `places` decimals, never a float, commas only as thousands separators."""
    if isinstance(v, bool) or isinstance(v, float) or v is None:
        raise ValuationError(f"{name} must be a number such as {example}.")
    t = str(v).strip()
    if "," in t and not re.fullmatch(r"[0-9]{1,3}(,[0-9]{3})+(\.[0-9]+)?", t):
        raise ValuationError(f"{name} must be a number such as {example} (commas only between groups of three digits).")
    t = t.replace(",", "")
    if not re.fullmatch(r"[0-9]{1,%d}(\.[0-9]{1,%d})?" % (int_digits, places), t):
        raise ValuationError(f"{name} must be a number such as {example} (at most {places} decimals).")
    d = Decimal(t)
    if d == 0 and not zero_ok:
        raise ValuationError(f"{name} must be more than zero.")
    return d


def _amount(v, name, zero_ok=False) -> Decimal: return _num(v, name, 12, 2, "1500.00", zero_ok).quantize(CENT)
def _rate(v, name, zero_ok=False) -> Decimal:
    d = _num(v, name, 3, 2, "12.5", zero_ok)
    if d > 100: raise ValuationError(f"{name} cannot be more than 100 percent.")
    return d.quantize(CENT)


def _r2(d: Decimal) -> Decimal: return d.quantize(CENT, rounding=ROUND_HALF_UP)


def refnum(r) -> int:
    try: return int(str(r["ref"]).rsplit("-", 1)[1])
    except (KeyError, IndexError, ValueError): return 0


def dcf_value(flows: List[Decimal], rate_pct: Decimal, growth_pct, net_debt: Decimal) -> Decimal:
    """Present value of end-of-period cash flows, plus an optional growth-in-perpetuity terminal value on the last flow, less net debt. Exact decimal arithmetic, rounded once at the end."""
    with localcontext() as ctx:
        ctx.prec = 80
        r = rate_pct / 100; total = Decimal(0)
        for t, cf in enumerate(flows, start=1): total += cf / ((1 + r) ** t)
        if growth_pct is not None:
            g = Decimal(growth_pct) / 100; total += (flows[-1] * (1 + g) / (r - g)) / ((1 + r) ** len(flows))
        return _r2(total - net_debt)


class ValuationService:
    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()

    def _not_future(self, d: date, what: str):
        if d > self.today() + timedelta(days=1):
            raise ValuationError(f"{what} cannot be in the future.")

    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r.get("org") != org:
            raise ValuationNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("vl_setting", f"{org}:settings", for_update=for_update)
        if s and s.get("org") == org:
            return s
        return {"id": "settings", "org": org, **DEFAULTS, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("vl_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other:
            raise ValuationForbiddenError(f"You {what}, so you cannot do this. A different person must.")

    # ------------------------------------------------------------------ policy
    def vl_get_policy(self, org) -> dict:
        s = self._settings(org)
        return {"review_days": s["review_days"], "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"An approved valuation whose valuation date is more than {s['review_days']} days old is flagged as due for review. This is your own setting, not a rule."}

    def vl_set_policy(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        if d.get("review_days") is not None: s["review_days"] = _int(d["review_days"], "The days before a valuation is due for review", 30, 1095)
        s.update(updated_by=actor, updated_at=self.now().isoformat())
        self._put("vl_setting", org, s)
        self.log("VALUATION_POLICY_SET", actor, "settings", org, f"review {s['review_days']} days")
        return self.vl_get_policy(org)

    # ------------------------------------------------------------------ views
    def _active_methods(self, c) -> list: return [m for m in c["methods"] if m["status"] == "ACTIVE"]

    def _view(self, c) -> dict:
        v = {x: c[x] for x in c if x != "org"}
        act = self._active_methods(c); results = [Decimal(m["result"]) for m in act]
        v.update(active_methods=len(act), weight_total=sum(m["weight"] for m in act), low=str(min(results)) if results else None, high=str(max(results)) if results else None,
                 due_for_review=c["status"] == "APPROVED" and date.fromisoformat(c["valuation_date"]) + timedelta(days=self._settings(c["org"])["review_days"]) < self.today())
        return v

    # ------------------------------------------------------------------ cases
    def vl_create_case(self, org, d, actor) -> dict:
        subject = _txt(d.get("subject"), "The subject", 3, 200); kind = _enum(d.get("subject_kind"), SUBJECT_KINDS, "The kind of subject"); purpose = _enum(d.get("purpose"), PURPOSES, "The purpose")
        basis = _enum(d.get("basis"), BASES, "The basis of value"); on = _date(d.get("valuation_date"), "The valuation date"); self._not_future(on, "The valuation date")
        cur = _txt(d.get("currency"), "The currency", 3, 3).upper()
        if not re.fullmatch(r"[A-Z]{3}", cur): raise ValuationError("The currency must be a three-letter code such as NGN.")
        c = {"id": uuid.uuid4().hex, "org": org, "ref": None, "subject": subject, "subject_kind": kind, "purpose": purpose, "basis": basis, "valuation_date": on.isoformat(), "currency": cur, "status": "DRAFT",
             "created_by": actor, "created_at": self.now().isoformat(), "methods": [], "rationale": None, "concluded_value": None, "submitted_by": None, "submitted_on": None, "decided_by": None, "decided_on": None,
             "decision_note": None, "withdraw_note": None, "history": []}
        c["ref"] = self._ref(org, "VL"); self._hist(c, actor, "CREATED")
        self._put("vl_case", org, c); self.log("VALUATION_CASE_CREATED", actor, c["id"], org, c["ref"])
        return self._view(c)

    def vl_list_cases(self, org, status=None) -> List[dict]:
        return [self._view(c) for c in sorted(self._all("vl_case", org), key=refnum) if not status or c["status"] == status]

    def vl_get_case(self, org, cid) -> dict: return self._view(self._get("vl_case", org, cid, "Valuation"))

    def _editable(self, org, cid) -> dict:
        c = self._get("vl_case", org, cid, "Valuation", for_update=True)
        if c["status"] not in ("DRAFT", "RETURNED"): raise ValuationStateError("Only a draft or returned valuation can be changed.")
        return c

    def vl_withdraw_case(self, org, cid, reason, actor) -> dict:
        c = self._editable(org, cid); reason = _txt(reason, "A reason", 10, 500); c.update(status="WITHDRAWN", withdraw_note=reason); self._hist(c, actor, "WITHDRAWN", reason)
        self._put("vl_case", org, c); self.log("VALUATION_CASE_WITHDRAWN", actor, cid, org, c["ref"])
        return self._view(c)

    # ------------------------------------------------------------------ methods
    def _compute(self, kind, d):
        """Returns (inputs as strings, result) for one method. Raises ValuationError on any bad input."""
        if kind == "MULTIPLE":
            metric = _amount(d.get("metric"), "The metric (for example earnings)"); mult = _num(d.get("multiple"), "The multiple", 6, 4, "6.5"); nd = _amount(d.get("net_debt"), "The net debt", True) if d.get("net_debt") not in (None, "") else Decimal("0.00")
            res = _r2(metric * mult - nd); inputs = {"metric": str(metric), "multiple": (f"{mult:f}".rstrip("0").rstrip(".") if "." in f"{mult:f}" else f"{mult:f}"), "net_debt": str(nd)}
        elif kind == "DCF":
            raw = d.get("cash_flows")
            if not isinstance(raw, (list, tuple)) or not 1 <= len(raw) <= MAX_PERIODS: raise ValuationError(f"Give 1 to {MAX_PERIODS} yearly cash flows as a list.")
            flows = [_amount(x, f"Cash flow {i}", True) for i, x in enumerate(raw, start=1)]
            if not any(f > 0 for f in flows): raise ValuationError("At least one cash flow must be more than zero.")
            rate = _rate(d.get("discount_rate"), "The discount rate"); g = d.get("terminal_growth"); gv = None
            if g not in (None, ""):
                gv = _rate(g, "The terminal growth", True)
                if gv >= rate: raise ValuationError("The terminal growth must be less than the discount rate.")
            nd = _amount(d.get("net_debt"), "The net debt", True) if d.get("net_debt") not in (None, "") else Decimal("0.00")
            res = dcf_value(flows, rate, gv, nd); inputs = {"cash_flows": [str(f) for f in flows], "discount_rate": str(rate), "terminal_growth": str(gv) if gv is not None else None, "net_debt": str(nd)}
        else:
            a = _amount(d.get("total_assets"), "The total assets"); l = _amount(d.get("total_liabilities"), "The total liabilities", True); res = a - l; inputs = {"total_assets": str(a), "total_liabilities": str(l)}
        if res <= 0: raise ValuationError("The result is zero or negative. Check the inputs.")
        return inputs, res

    def vl_add_method(self, org, cid, d, actor) -> dict:
        c = self._editable(org, cid); kind = _enum(d.get("kind"), METHOD_KINDS, "The method"); label = _txt(d.get("label"), "The label (for example the peer group)", 2, 150); weight = _int(d.get("weight"), "The weight in percent", 0, 100)
        inputs, res = self._compute(kind, d)
        if len(self._active_methods(c)) >= MAX_METHODS: raise ValuationStateError(f"A valuation can have at most {MAX_METHODS} methods. Remove one first.")
        c["methods"].append({"no": len(c["methods"]) + 1, "kind": kind, "label": label, "weight": weight, "inputs": inputs, "result": str(res), "status": "ACTIVE", "by": actor, "at": self.now().isoformat(), "removed_note": None})
        self._hist(c, actor, "METHOD_ADDED")
        self._put("vl_case", org, c); self.log("VALUATION_METHOD_ADDED", actor, cid, org, f"{c['ref']} #{len(c['methods'])}")
        return self._view(c)

    def vl_remove_method(self, org, cid, no, reason, actor) -> dict:
        c = self._editable(org, cid); n = _int(no, "The method number", 1, 1000)
        m = next((m for m in c["methods"] if m["no"] == n), None)
        if m is None: raise ValuationNotFoundError("Method not found.")
        if m["status"] != "ACTIVE": raise ValuationStateError("That method is already removed.")
        reason = _txt(reason, "A reason", 5, 500); m.update(status="REMOVED", removed_note=reason); self._hist(c, actor, "METHOD_REMOVED", reason)
        self._put("vl_case", org, c); self.log("VALUATION_METHOD_REMOVED", actor, cid, org, f"{c['ref']} #{n}")
        return self._view(c)

    def vl_sensitivity(self, org, cid, no) -> dict:
        c = self._get("vl_case", org, cid, "Valuation"); n = _int(no, "The method number", 1, 1000)
        m = next((m for m in c["methods"] if m["no"] == n), None)
        if m is None: raise ValuationNotFoundError("Method not found.")
        if m["kind"] != "DCF": raise ValuationStateError("A sensitivity is only worked out for a discounted cash flow method.")
        i = m["inputs"]; flows = [Decimal(x) for x in i["cash_flows"]]; rate = Decimal(i["discount_rate"]); g = Decimal(i["terminal_growth"]) if i["terminal_growth"] is not None else None; nd = Decimal(i["net_debt"]); rows = []
        for delta in (Decimal(-1), Decimal(0), Decimal(1)):
            r = rate + delta
            if r <= 0 or r > 100 or (g is not None and r <= g): rows.append({"discount_rate": str(r), "result": None}); continue
            rows.append({"discount_rate": str(r), "result": str(dcf_value(flows, r, g, nd))})
        return {"method": n, "rows": rows, "meaning": "The same cash flows at the discount rate one percentage point lower and higher. A blank means that rate is not usable with the growth typed."}

    # ------------------------------------------------------------------ review
    def vl_submit(self, org, cid, d, actor) -> dict:
        c = self._editable(org, cid); act = self._active_methods(c)
        if not act: raise ValuationStateError("Add at least one method before submitting.")
        total = sum(m["weight"] for m in act)
        if total != 100: raise ValuationStateError(f"The method weights add up to {total} percent. They must add up to 100.")
        rationale = _txt(d.get("rationale"), "The rationale for the weights and inputs", 20, 3000)
        conc = _r2(sum((Decimal(m["result"]) * m["weight"] / 100 for m in act), Decimal(0)))
        c.update(status="SUBMITTED", rationale=rationale, concluded_value=str(conc), submitted_by=actor, submitted_on=self.today().isoformat(), decided_by=None, decided_on=None, decision_note=None)
        self._hist(c, actor, "SUBMITTED")
        self._put("vl_case", org, c); self.log("VALUATION_CASE_SUBMITTED", actor, cid, org, c["ref"])
        return self._view(c)

    def _submitted(self, org, cid) -> dict:
        c = self._get("vl_case", org, cid, "Valuation", for_update=True)
        if c["status"] != "SUBMITTED": raise ValuationStateError("Only a submitted valuation can be decided.")
        return c

    def vl_approve_case(self, org, cid, d, actor) -> dict:
        c = self._submitted(org, cid); self._two(actor, c["submitted_by"], "submitted this valuation")
        note = _txt(d.get("note"), "An approval note", 10, 1000, required=False)
        c.update(status="APPROVED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=note or None); self._hist(c, actor, "APPROVED", note)
        self._put("vl_case", org, c); self.log("VALUATION_CASE_APPROVED", actor, cid, org, c["ref"])
        return self._view(c)

    def vl_return_case(self, org, cid, reason, actor) -> dict:
        c = self._submitted(org, cid); self._two(actor, c["submitted_by"], "submitted this valuation")
        reason = _txt(reason, "A reason", 10, 1000); c.update(status="RETURNED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=reason, concluded_value=None); self._hist(c, actor, "RETURNED", reason)
        self._put("vl_case", org, c); self.log("VALUATION_CASE_RETURNED", actor, cid, org, c["ref"])
        return self._view(c)

    # ------------------------------------------------------------------ overview
    def vl_overview(self, org) -> dict:
        cs = self.vl_list_cases(org); att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("CASES_TO_REVIEW", sum(1 for c in cs if c["status"] == "SUBMITTED"), "valuation(s) are waiting for a different person to review them.")
        add("CASES_RETURNED", sum(1 for c in cs if c["status"] == "RETURNED"), "valuation(s) were returned and need changes.")
        add("DUE_FOR_REVIEW", sum(1 for c in cs if c["due_for_review"]), "approved valuation(s) have a valuation date older than your window.")
        tot = {}
        for c in cs:
            t = tot.setdefault(c["currency"], {"currency": c["currency"], "approved": 0, "in_progress": 0, "waiting": 0})
            if c["status"] == "APPROVED": t["approved"] += 1
            elif c["status"] == "SUBMITTED": t["waiting"] += 1
            elif c["status"] in ("DRAFT", "RETURNED"): t["in_progress"] += 1
        counts = {s: sum(1 for c in cs if c["status"] == s) for s in ("DRAFT", "SUBMITTED", "APPROVED", "RETURNED", "WITHDRAWN")}
        return {"counts": counts, "totals": sorted(tot.values(), key=lambda x: x["currency"]), "attention": att, "policy": self.vl_get_policy(org), "limitations": LIMITATIONS}

    def vl_options(self, org) -> dict:
        return {"subject_kinds": SUBJECT_KINDS, "purposes": PURPOSES, "bases": BASES, "method_kinds": METHOD_KINDS, "limitations": LIMITATIONS}
