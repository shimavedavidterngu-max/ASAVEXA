"""Treasury service (records and evidence; it never moves money and never connects to a bank).

Records (shared document store, per organisation): tr_account, tr_flow, tr_payment, tr_covenant, tr_setting.

Principles enforced here
  * A balance is typed in by one person from a named source and can be CONFIRMED only by a different person.
  * The cash position is the latest balance per account, shown per currency. Different currencies are never added together or converted.
  * The liquidity forecast is arithmetic over what people recorded: the latest balances, open expected cash flows and approved payments. It predicts nothing.
  * A payment request is approved by someone other than who asked for it; at or above the organisation's limit two different approvers are needed; it is
    released (recorded as paid) by someone other than the requester, with the bank's own reference. Payee, amount and account cannot be edited after the request.
  * A covenant result is judged against the threshold by fixed arithmetic. A breach needs a written explanation and is acknowledged by someone other than who
    recorded it. Acknowledging a breach never hides it.
  * Nothing is deleted, every step is audited, and every lookup re-checks the organisation.
"""
import calendar
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable, List, Optional

from .errors import TreasuryError, TreasuryForbiddenError, TreasuryNotFoundError, TreasuryStateError

DIRECTIONS = ["IN", "OUT"]
FLOW_CATEGORIES = ["CUSTOMER_RECEIPT", "GRANT_OR_DONATION", "LOAN_DRAWDOWN", "OTHER_RECEIPT", "SUPPLIER_PAYMENT", "PAYROLL", "TAX_AND_LEVIES", "RENT_AND_UTILITIES",
                   "LOAN_REPAYMENT", "CAPITAL_SPEND", "OTHER_PAYMENT"]
CERTAINTIES = ["CONFIRMED", "EXPECTED", "POSSIBLE"]
FLOW_OPEN, FLOW_REALISED, FLOW_CANCELLED = "OPEN", "REALISED", "CANCELLED"
COMPARATORS = {"MIN": "must stay at or above", "MAX": "must stay at or below"}
UNITS = ["RATIO", "PERCENT", "AMOUNT"]
FREQUENCIES = {"MONTHLY": 1, "QUARTERLY": 3, "SEMI_ANNUAL": 6, "ANNUAL": 12}
PAY_OPEN = ("REQUESTED", "APPROVED")
DEFAULT_DUAL_LIMIT = "10000.00"
DEFAULT_STALE_DAYS = 7
TEST_GRACE_DAYS = 30
DUPLICATE_WINDOW_DAYS = 30
MAX_WEEKS = 26
MONEY_LIMIT = Decimal("1000000000000")
LIMITATIONS = [
    "ASAVEXA never moves money and is not connected to any bank. 'Released' records that a named person made the payment in the bank and gave the bank's own reference.",
    "Balances, expected cash flows and covenant values are typed in by people. The position and the forecast are only as complete and as current as those records.",
    "Amounts in different currencies are never added together or converted. Each currency has its own position and forecast.",
    "Dates are compared with today in UTC, with one day of leeway so a person ahead of UTC can record something dated today where they are.",
    "The forecast is arithmetic: latest balance, plus open expected receipts, minus open expected payments and approved payments. It is not a prediction or advice.",
    "The default payment limit and balance-age warning are placeholders for you to set. They are not a standard, a bank rule or a legal requirement.",
    "A covenant result is judged against the threshold your organisation typed in. ASAVEXA has not read the loan agreement and cannot tell you what it says or whether a waiver is valid.",
    "This is a management record. It is not treasury advice, a credit facility, an audit opinion or a licensed financial service.",
]


def _utc(): return datetime.now(timezone.utc)


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v)))
    v = " ".join("".join(c if c >= " " and c != "\x7f" else " " for c in v).split())
    if required and len(v) < lo:
        raise TreasuryError(f"{name} is required (at least {lo} characters).")
    if v and len(v) < lo:
        raise TreasuryError(f"{name} needs at least {lo} characters.")
    if len(v) > hi:
        raise TreasuryError(f"{name} is too long (limit {hi} characters).")
    return v


def _date(v, name) -> date:
    try:
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise TreasuryError(f"{name} must be a real date written YYYY-MM-DD.")


def _enum(v, allowed, name) -> str:
    v = _txt(v, name, 1, 40).upper()
    if v not in allowed:
        raise TreasuryError(f"{name} must be one of {', '.join(allowed)}.")
    return v


def _currency(v, name="Currency") -> str:
    v = _txt(v, name, 3, 3).upper()
    if not (len(v) == 3 and v.isalpha() and v.isascii()):
        raise TreasuryError(f"{name} must be a three-letter code such as NGN or USD.")
    return v


def _num(v, name, places, positive=False, allow_zero=True) -> Decimal:
    if isinstance(v, bool) or v is None or (isinstance(v, str) and not v.strip()):
        raise TreasuryError(f"{name} is required (a number).")
    try:
        d = Decimal(str(v).strip().replace(",", ""))
    except InvalidOperation:
        raise TreasuryError(f"{name} must be a number.")
    if not d.is_finite():
        raise TreasuryError(f"{name} must be a number.")
    if abs(d) >= MONEY_LIMIT:
        raise TreasuryError(f"{name} is too large.")
    try:
        exact = d == d.quantize(Decimal(1).scaleb(-places))
    except InvalidOperation:
        exact = False
    if not exact:
        raise TreasuryError(f"{name} can have at most {places} decimal places.")
    if positive and (d < 0 or (d == 0 and not allow_zero)):
        raise TreasuryError(f"{name} must be {'more than zero' if not allow_zero else 'zero or more'}.")
    return d.quantize(Decimal(1).scaleb(-places))


def money(v, name, positive=False) -> Decimal: return _num(v, name, 2, positive=positive, allow_zero=not positive)
def s2(d: Decimal) -> str: return f"{d.quantize(Decimal('0.01')):.2f}"
def s4(d: Decimal) -> str: return f"{d.quantize(Decimal('0.0001')):.4f}"


def _int(v, name, lo, hi) -> int:
    if isinstance(v, bool) or not str(v).strip().lstrip("-").isdigit():
        raise TreasuryError(f"{name} must be a whole number from {lo} to {hi}.")
    n = int(str(v).strip())
    if not lo <= n <= hi:
        raise TreasuryError(f"{name} must be a whole number from {lo} to {hi}.")
    return n


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


class TreasuryService:
    def __init__(self, store, vault, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()

    def _not_future(self, d: date, what: str):
        """Dates are compared with today in UTC. One day of leeway means a person ahead of UTC can still record something dated 'today' where they are."""
        if d > self.today() + timedelta(days=1):
            raise TreasuryError(f"{what} cannot be in the future.")
    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r.get("org") != org:
            raise TreasuryNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("tr_setting", f"{org}:settings", for_update=for_update)
        if s and s.get("org") == org:
            return s
        return {"id": "settings", "org": org, "minimum_cash": {}, "dual_limits": {"DEFAULT": DEFAULT_DUAL_LIMIT}, "stale_days": DEFAULT_STALE_DAYS, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("tr_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other:
            raise TreasuryForbiddenError(f"You {what}, so you cannot decide it. A different person must.")

    def _evidence(self, org, ids) -> List[dict]:
        out = []
        for i in dict.fromkeys(str(i) for i in (ids or [])):
            try:
                e = self.vault.get_evidence(org, i)
            except Exception:
                raise TreasuryError("Linked evidence not found in this organisation's Evidence Vault.")
            out.append({"evidence_id": e.id, "filename": e.original_filename, "file_hash": e.file_hash})
        return out

    # ------------------------------------------------------------------ policy
    def get_treasury_policy(self, org) -> dict:
        s = self._settings(org)
        return {"minimum_cash": dict(s["minimum_cash"]), "dual_limits": dict(s["dual_limits"]), "stale_days": s["stale_days"], "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"Payments at or above the limit for their currency (or {s['dual_limits'].get('DEFAULT', DEFAULT_DUAL_LIMIT)} where none is set) need two different approvers. "
                           f"A balance older than {s['stale_days']} days is shown as out of date. A currency with a minimum cash amount is flagged in any forecast week that ends below it. "
                           "These are your own policy settings, not a standard or a bank rule."}

    def set_treasury_policy(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        mc, dl = dict(s["minimum_cash"]), dict(s["dual_limits"])
        if d.get("minimum_cash") is not None:
            if not isinstance(d["minimum_cash"], dict): raise TreasuryError("Minimum cash must be an amount per currency.")
            mc = {_currency(k, "Minimum cash currency"): s2(money(v, f"The minimum cash for {k}", positive=True)) for k, v in d["minimum_cash"].items()}
        if d.get("dual_limits") is not None:
            if not isinstance(d["dual_limits"], dict): raise TreasuryError("Limits must be an amount per currency.")
            dl = {}
            for k, v in d["dual_limits"].items():
                key = "DEFAULT" if str(k).strip().upper() == "DEFAULT" else _currency(k, "Limit currency")
                dl[key] = s2(money(v, f"The two-approver limit for {k}", positive=True))
            dl.setdefault("DEFAULT", DEFAULT_DUAL_LIMIT)
        sd = s["stale_days"]
        if d.get("stale_days") is not None: sd = _int(d["stale_days"], "The balance age limit", 1, 90)
        s.update(minimum_cash=mc, dual_limits=dl, stale_days=sd, updated_by=actor, updated_at=self.now().isoformat())
        self._put("tr_setting", org, s); self.log("TR_POLICY_SET", actor, "settings", org, f"minimum cash {mc}, limits {dl}, stale {sd}")
        return self.get_treasury_policy(org)

    def _dual_limit(self, s, currency) -> Decimal:
        return Decimal(s["dual_limits"].get(currency) or s["dual_limits"].get("DEFAULT") or DEFAULT_DUAL_LIMIT)

    # ------------------------------------------------------------------ accounts and balances
    def open_cash_account(self, org, d, actor) -> dict:
        name = _txt(d.get("name"), "The account name", 2, 120)
        last4 = _txt(d.get("last4"), "The last four characters", 0, 4, required=False)
        if last4 and not last4.isalnum():
            raise TreasuryError("Give at most the last four letters or digits of the account number. Never the whole number.")
        cur = _currency(d.get("currency"))
        for a in self._all("tr_account", org):
            if a["status"] == "ACTIVE" and a["name"].casefold() == name.casefold():
                raise TreasuryStateError("An open account with that name already exists.")
        a = {"id": uuid.uuid4().hex, "org": org, "ref": None, "name": name, "bank_name": _txt(d.get("bank_name"), "The bank name", 0, 120, required=False),
             "currency": cur, "last4": last4, "purpose": _txt(d.get("purpose"), "The purpose", 0, 300, required=False), "status": "ACTIVE", "balances": [], "history": [],
             "created_by": actor, "created_at": self.now().isoformat()}
        a["ref"] = self._ref(org, "CA"); self._hist(a, actor, "OPENED"); self._put("tr_account", org, a); self.log("TR_ACCOUNT_OPENED", actor, a["id"], org, f"{a['ref']} {cur}")
        return self._aview(org, a)

    def close_cash_account(self, org, aid, note, actor) -> dict:
        a = self._get("tr_account", org, aid, "Cash account", for_update=True)
        if a["status"] != "ACTIVE": raise TreasuryStateError("This account is already closed.")
        note = _txt(note, "The reason", 5, 500)
        if any(f["status"] == FLOW_OPEN and f.get("account_id") == aid for f in self._all("tr_flow", org)):
            raise TreasuryStateError("Open expected cash flows still point at this account. Cancel or realise them first.")
        if any(p["status"] in PAY_OPEN and p["account_id"] == aid for p in self._all("tr_payment", org)):
            raise TreasuryStateError("Payment requests that are not finished still point at this account.")
        a["status"] = "CLOSED"; self._hist(a, actor, "CLOSED", note)
        self._put("tr_account", org, a); self.log("TR_ACCOUNT_CLOSED", actor, aid, org, note)
        return self._aview(org, a)

    @staticmethod
    def _latest(a) -> Optional[dict]:
        return max(a["balances"], key=lambda b: b["as_at"]) if a["balances"] else None

    def _aview(self, org, a) -> dict:
        lb = self._latest(a); s = self._settings(org); age = (self.today() - date.fromisoformat(lb["as_at"])).days if lb else None
        return {"id": a["id"], "ref": a["ref"], "name": a["name"], "bank_name": a["bank_name"], "currency": a["currency"], "last4": a["last4"], "purpose": a["purpose"], "status": a["status"],
                "latest_balance": lb, "age_days": age, "stale": (age is None or age > s["stale_days"]) if a["status"] == "ACTIVE" else False,
                "balances": sorted(a["balances"], key=lambda b: b["as_at"], reverse=True)[:12], "history": a["history"][-20:], "created_by": a["created_by"], "created_at": a["created_at"]}

    def list_cash_accounts(self, org) -> List[dict]:
        return [self._aview(org, a) for a in sorted(self._all("tr_account", org), key=lambda a: a["ref"])]

    def get_cash_account(self, org, aid) -> dict: return self._aview(org, self._get("tr_account", org, aid, "Cash account"))

    def record_balance(self, org, aid, d, actor) -> dict:
        a = self._get("tr_account", org, aid, "Cash account", for_update=True)
        if a["status"] != "ACTIVE": raise TreasuryStateError("This account is closed.")
        as_at = _date(d.get("as_at"), "The balance date")
        self._not_future(as_at, "A balance date")
        if any(b["as_at"] == as_at.isoformat() for b in a["balances"]):
            raise TreasuryStateError("A balance for that date is already recorded. Record a later one if it has changed.")
        amount = money(d.get("amount"), "The balance")
        b = {"id": f"b{len(a['balances']) + 1:04d}", "as_at": as_at.isoformat(), "amount": s2(amount), "source": _txt(d.get("source"), "Where the balance came from", 3, 200),
             "evidence": self._evidence(org, d.get("evidence_ids")), "status": "RECORDED", "recorded_by": actor, "recorded_at": self.now().isoformat(), "confirmed_by": None, "confirmed_at": None}
        a["balances"].append(b); self._hist(a, actor, "BALANCE_RECORDED", f"{b['as_at']} {b['amount']}")
        self._put("tr_account", org, a); self.log("TR_BALANCE_RECORDED", actor, a["id"], org, f"{a['ref']} {b['as_at']} {b['amount']}")
        return self._aview(org, a)

    def confirm_balance(self, org, aid, bid, actor) -> dict:
        a = self._get("tr_account", org, aid, "Cash account", for_update=True)
        b = next((x for x in a["balances"] if x["id"] == bid), None)
        if b is None: raise TreasuryNotFoundError("Balance not found.")
        if b["status"] == "CONFIRMED": raise TreasuryStateError("This balance is already confirmed.")
        self._two(actor, b["recorded_by"], "recorded this balance")
        b.update(status="CONFIRMED", confirmed_by=actor, confirmed_at=self.now().isoformat())
        self._hist(a, actor, "BALANCE_CONFIRMED", f"{b['as_at']} {b['amount']}")
        self._put("tr_account", org, a); self.log("TR_BALANCE_CONFIRMED", actor, a["id"], org, f"{a['ref']} {b['as_at']}")
        return self._aview(org, a)

    def cash_position(self, org) -> dict:
        s = self._settings(org); by: dict = {}
        for a in sorted(self._all("tr_account", org), key=lambda a: a["ref"]):
            if a["status"] != "ACTIVE": continue
            v = self._aview(org, a); lb = v["latest_balance"]
            g = by.setdefault(a["currency"], {"currency": a["currency"], "total": Decimal(0), "accounts": [], "accounts_without_balance": 0, "unconfirmed": 0, "stale": 0})
            row = {"id": a["id"], "ref": a["ref"], "name": a["name"], "bank_name": a["bank_name"], "balance": lb["amount"] if lb else None, "as_at": lb["as_at"] if lb else None,
                   "status": lb["status"] if lb else None, "age_days": v["age_days"], "stale": v["stale"]}
            g["accounts"].append(row)
            if lb is None: g["accounts_without_balance"] += 1
            else:
                g["total"] += Decimal(lb["amount"])
                if lb["status"] != "CONFIRMED": g["unconfirmed"] += 1
            if v["stale"] and lb is not None: g["stale"] += 1
        out = []
        for cur in sorted(by):
            g = by[cur]; g["total"] = s2(g["total"]); g["minimum_cash"] = s["minimum_cash"].get(cur)
            g["complete"] = g["accounts_without_balance"] == 0 and g["stale"] == 0
            out.append(g)
        return {"currencies": out, "stale_days": s["stale_days"], "note": "Each currency is shown on its own. Nothing is converted or added across currencies."}

    # ------------------------------------------------------------------ expected cash flows
    def add_cash_flow(self, org, d, actor) -> dict:
        direction = _enum(d.get("direction"), DIRECTIONS, "The direction")
        acc = None
        if d.get("account_id"):
            acc = self._get("tr_account", org, d["account_id"], "Cash account")
            if acc["status"] != "ACTIVE": raise TreasuryStateError("That account is closed.")
        cur = _currency(d.get("currency") or (acc["currency"] if acc else None))
        if acc and acc["currency"] != cur: raise TreasuryError("The currency must match the account's currency.")
        f = {"id": uuid.uuid4().hex, "org": org, "ref": None, "direction": direction, "flow_date": _date(d.get("flow_date"), "The expected date").isoformat(),
             "amount": s2(money(d.get("amount"), "The amount", positive=True)),
             "currency": cur, "category": _enum(d.get("category"), FLOW_CATEGORIES, "The category"), "description": _txt(d.get("description"), "The description", 3, 300),
             "certainty": _enum(d.get("certainty") or "EXPECTED", CERTAINTIES, "How sure you are"), "account_id": acc["id"] if acc else None, "status": FLOW_OPEN,
             "actual_amount": None, "actual_date": None, "history": [], "created_by": actor, "created_at": self.now().isoformat()}
        f["ref"] = self._ref(org, "CF"); self._hist(f, actor, "ADDED"); self._put("tr_flow", org, f); self.log("TR_FLOW_ADDED", actor, f["id"], org, f"{f['ref']} {direction} {f['amount']} {cur}")
        return self._fview(org, f)

    def change_cash_flow(self, org, fid, d, actor) -> dict:
        f = self._get("tr_flow", org, fid, "Expected cash flow", for_update=True)
        if f["status"] != FLOW_OPEN: raise TreasuryStateError("Only an open expected cash flow can be changed.")
        note = _txt(d.get("note"), "The reason for the change", 5, 500)
        changes = {}
        if d.get("flow_date") not in (None, ""): changes["flow_date"] = _date(d["flow_date"], "The expected date").isoformat()
        if d.get("amount") not in (None, ""): changes["amount"] = s2(money(d["amount"], "The amount", positive=True))
        if d.get("certainty") not in (None, ""): changes["certainty"] = _enum(d["certainty"], CERTAINTIES, "How sure you are")
        if d.get("description") not in (None, ""): changes["description"] = _txt(d["description"], "The description", 3, 300)
        changes = {k: v for k, v in changes.items() if f[k] != v}
        if not changes: raise TreasuryStateError("Nothing has changed.")
        self._hist(f, actor, "CHANGED", note + " | " + "; ".join(f"{k}: {f[k]} -> {v}" for k, v in changes.items()))
        f.update(changes); self._put("tr_flow", org, f); self.log("TR_FLOW_CHANGED", actor, fid, org, note)
        return self._fview(org, f)

    def realise_cash_flow(self, org, fid, d, actor) -> dict:
        f = self._get("tr_flow", org, fid, "Expected cash flow", for_update=True)
        if f["status"] != FLOW_OPEN: raise TreasuryStateError("Only an open expected cash flow can be marked as happened.")
        when = _date(d.get("actual_date"), "The date it happened")
        self._not_future(when, "The date it happened")
        f.update(status=FLOW_REALISED, actual_amount=s2(money(d.get("actual_amount"), "The amount that actually moved", positive=True)), actual_date=when.isoformat())
        self._hist(f, actor, "REALISED", f"{f['actual_amount']} on {f['actual_date']}"); self._put("tr_flow", org, f)
        self.log("TR_FLOW_REALISED", actor, fid, org, f"{f['ref']} {f['actual_amount']}")
        return self._fview(org, f)

    def cancel_cash_flow(self, org, fid, note, actor) -> dict:
        f = self._get("tr_flow", org, fid, "Expected cash flow", for_update=True)
        if f["status"] != FLOW_OPEN: raise TreasuryStateError("Only an open expected cash flow can be cancelled.")
        note = _txt(note, "The reason", 5, 500)
        if any(p["status"] in PAY_OPEN and p.get("flow_id") == fid for p in self._all("tr_payment", org)):
            raise TreasuryStateError("A payment request that is not finished is linked to this cash flow.")
        f["status"] = FLOW_CANCELLED; self._hist(f, actor, "CANCELLED", note); self._put("tr_flow", org, f)
        self.log("TR_FLOW_CANCELLED", actor, fid, org, note)
        return self._fview(org, f)

    def _fview(self, org, f) -> dict:
        late = f["status"] == FLOW_OPEN and date.fromisoformat(f["flow_date"]) < self.today()
        v = {k: f[k] for k in ("id", "ref", "direction", "flow_date", "amount", "currency", "category", "description", "certainty", "account_id", "status", "actual_amount", "actual_date", "created_by", "created_at")}
        v["overdue"] = late; v["history"] = f["history"][-20:]
        if f["status"] == FLOW_REALISED:
            v["variance"] = s2(Decimal(f["actual_amount"]) - Decimal(f["amount"])); v["days_late"] = (date.fromisoformat(f["actual_date"]) - date.fromisoformat(f["flow_date"])).days
        return v

    def list_cash_flows(self, org, status=None, currency=None) -> List[dict]:
        rows = self._all("tr_flow", org)
        if status: rows = [f for f in rows if f["status"] == status.upper()]
        if currency: rows = [f for f in rows if f["currency"] == currency.upper()]
        return [self._fview(org, f) for f in sorted(rows, key=lambda f: (f["flow_date"], f["ref"]))]

    def get_cash_flow(self, org, fid) -> dict: return self._fview(org, self._get("tr_flow", org, fid, "Expected cash flow"))

    def forecast_accuracy(self, org) -> dict:
        done = [f for f in self._all("tr_flow", org) if f["status"] == FLOW_REALISED]
        by: dict = {}
        for f in done:
            g = by.setdefault(f["currency"], {"currency": f["currency"], "count": 0, "on_time": 0, "forecast": Decimal(0), "actual": Decimal(0), "days_late_total": 0})
            g["count"] += 1; g["forecast"] += Decimal(f["amount"]); g["actual"] += Decimal(f["actual_amount"])
            late = (date.fromisoformat(f["actual_date"]) - date.fromisoformat(f["flow_date"])).days
            g["on_time"] += 1 if late <= 0 else 0; g["days_late_total"] += max(late, 0)
        out = []
        for cur in sorted(by):
            g = by[cur]
            out.append({"currency": cur, "count": g["count"], "on_time": g["on_time"], "forecast_total": s2(g["forecast"]), "actual_total": s2(g["actual"]), "difference": s2(g["actual"] - g["forecast"]),
                        "average_days_late": round(g["days_late_total"] / g["count"], 1)})
        return {"currencies": out, "note": "This compares what people expected with what they recorded as having happened. It measures their forecasting, nothing more."}

    # ------------------------------------------------------------------ liquidity forecast
    def liquidity_forecast(self, org, weeks=13, include_possible=False) -> dict:
        weeks = _int(weeks, "The number of weeks", 1, MAX_WEEKS)
        s = self._settings(org); today = self.today(); pos = {g["currency"]: g for g in self.cash_position(org)["currencies"]}
        flows = [f for f in self._all("tr_flow", org) if f["status"] == FLOW_OPEN and (include_possible or f["certainty"] != "POSSIBLE")]
        pays = [p for p in self._all("tr_payment", org) if p["status"] == "APPROVED" and not p.get("flow_id")]
        pending = [p for p in self._all("tr_payment", org) if p["status"] == "REQUESTED"]
        cur_all = sorted(set(pos) | {f["currency"] for f in flows} | {p["currency"] for p in pays})
        end = today + timedelta(days=7 * weeks)

        def bucket(d: date) -> int: return max(0, (d - today).days // 7)
        out = []
        for cur in cur_all:
            g = pos.get(cur); opening = Decimal(g["total"]) if g else Decimal(0)
            rows = [{"week": k + 1, "start": (today + timedelta(days=7 * k)).isoformat(), "end": (today + timedelta(days=7 * k + 6)).isoformat(), "in": Decimal(0), "out": Decimal(0), "overdue_included": 0} for k in range(weeks)]
            beyond = 0; overdue = 0
            for f in (x for x in flows if x["currency"] == cur):
                d = date.fromisoformat(f["flow_date"])
                if d >= end: beyond += 1; continue
                k = bucket(d); late = d < today; overdue += 1 if late else 0
                rows[k]["overdue_included"] += 1 if late else 0
                rows[k]["in" if f["direction"] == "IN" else "out"] += Decimal(f["amount"])
            for p in (x for x in pays if x["currency"] == cur):
                d = date.fromisoformat(p["due_date"])
                if d >= end: beyond += 1; continue
                k = bucket(d); late = d < today; overdue += 1 if late else 0
                rows[k]["overdue_included"] += 1 if late else 0
                rows[k]["out"] += Decimal(p["amount"])
            floor = Decimal(s["minimum_cash"][cur]) if cur in s["minimum_cash"] else None
            bal = opening; low = None; shortfall = 0; table = []
            for r in rows:
                bal = bal + r["in"] - r["out"]
                below = (bal < floor) if floor is not None else (bal < 0)
                shortfall += 1 if below else 0
                if low is None or bal < low[0]: low = (bal, r["week"])
                table.append({"week": r["week"], "start": r["start"], "end": r["end"], "inflow": s2(r["in"]), "outflow": s2(r["out"]), "closing": s2(bal), "below_floor": below, "overdue_included": r["overdue_included"]})
            warn = []
            if g is None: warn.append("No cash account is open in this currency, so the opening balance is zero.")
            else:
                if g["accounts_without_balance"]: warn.append(f"{g['accounts_without_balance']} account(s) have no balance recorded and are left out of the opening cash.")
                if g["stale"]: warn.append(f"{g['stale']} account balance(s) are older than {s['stale_days']} days.")
                if g["unconfirmed"]: warn.append(f"{g['unconfirmed']} balance(s) have not been confirmed by a second person.")
            if overdue: warn.append(f"{overdue} item(s) dated before today are still open. They are counted in week 1.")
            if beyond: warn.append(f"{beyond} item(s) fall after the last week shown and are not counted.")
            pr = [p for p in pending if p["currency"] == cur]
            if pr: warn.append(f"{len(pr)} payment request(s) totalling {s2(sum(Decimal(p['amount']) for p in pr))} are not yet approved and are not counted.")
            out.append({"currency": cur, "opening": s2(opening), "floor": s2(floor) if floor is not None else None, "floor_basis": "your minimum cash setting" if floor is not None else "zero (no minimum cash is set)",
                        "weeks": table, "lowest_closing": s2(low[0]), "lowest_week": low[1], "shortfall_weeks": shortfall, "warnings": warn})
        return {"as_of": today.isoformat(), "weeks": weeks, "include_possible": bool(include_possible), "currencies": out,
                "note": "Arithmetic over the balances and expected cash flows people recorded, plus approved payments. It is not a prediction and not advice."}

    # ------------------------------------------------------------------ payment requests
    def request_payment(self, org, d, actor) -> dict:
        acc = self._get("tr_account", org, d.get("account_id"), "Cash account")
        if acc["status"] != "ACTIVE": raise TreasuryStateError("That account is closed.")
        payee = _txt(d.get("payee"), "The payee", 2, 160); amount = money(d.get("amount"), "The amount", positive=True)
        due = _date(d.get("due_date"), "The due date"); invoice = _txt(d.get("invoice_ref"), "The invoice or reference", 0, 80, required=False)
        flow_id = d.get("flow_id") or None
        if flow_id:
            fl = self._get("tr_flow", org, flow_id, "Expected cash flow")
            if fl["status"] != FLOW_OPEN or fl["direction"] != "OUT" or fl["currency"] != acc["currency"]:
                raise TreasuryError("The linked cash flow must be an open payment in the same currency as the account.")
            if any(p["status"] in PAY_OPEN + ("RELEASED",) and p.get("flow_id") == flow_id for p in self._all("tr_payment", org)):
                raise TreasuryStateError("That cash flow already has a payment request.")
        mine = [p for p in self._all("tr_payment", org) if p["status"] in PAY_OPEN + ("RELEASED",)]
        same_payee = [p for p in mine if p["payee"].casefold() == payee.casefold()]
        if invoice and any(p.get("invoice_ref", "").casefold() == invoice.casefold() for p in same_payee):
            raise TreasuryStateError("A payment for this payee and invoice reference already exists. Paying the same invoice twice is refused.")
        flags = []
        if not any(p["status"] == "RELEASED" for p in same_payee): flags.append("NEW_PAYEE")
        if any(p["currency"] == acc["currency"] and Decimal(p["amount"]) == amount and abs((date.fromisoformat(p["due_date"]) - due).days) <= DUPLICATE_WINDOW_DAYS for p in same_payee):
            flags.append("POSSIBLE_DUPLICATE")
        lb = self._latest(acc)
        if lb is None or Decimal(lb["amount"]) < amount: flags.append("BALANCE_BELOW_AMOUNT")
        ev = self._evidence(org, d.get("evidence_ids"))
        if not ev: flags.append("NO_EVIDENCE")
        s = self._settings(org)
        p = {"id": uuid.uuid4().hex, "org": org, "ref": None, "account_id": acc["id"], "account_name": acc["name"], "currency": acc["currency"], "payee": payee, "amount": s2(amount),
             "due_date": due.isoformat(), "reason": _txt(d.get("reason"), "The reason for the payment", 5, 500), "invoice_ref": invoice, "flow_id": flow_id, "evidence": ev, "flags": flags,
             "approvals_needed": 2 if amount >= self._dual_limit(s, acc["currency"]) else 1, "approvals": [], "status": "REQUESTED", "requested_by": actor, "requested_at": self.now().isoformat(),
             "released_by": None, "released_at": None, "released_date": None, "bank_reference": None, "history": []}
        p["ref"] = self._ref(org, "PR"); self._hist(p, actor, "REQUESTED"); self._put("tr_payment", org, p); self.log("TR_PAYMENT_REQUESTED", actor, p["id"], org, f"{p['ref']} {p['amount']} {p['currency']} flags {flags}")
        return self._pview(p)

    def _p(self, org, pid) -> dict: return self._get("tr_payment", org, pid, "Payment request", for_update=True)

    def approve_payment(self, org, pid, actor, note="") -> dict:
        p = self._p(org, pid)
        if p["status"] != "REQUESTED": raise TreasuryStateError("Only a payment request that is waiting for approval can be approved.")
        self._two(actor, p["requested_by"], "asked for this payment")
        if any(a["by"] == actor for a in p["approvals"]): raise TreasuryForbiddenError("You have already approved this payment. A different person must give the other approval.")
        note = _txt(note, "Your note", 0, 500, required=False)
        if p["flags"] and len(note) < 5: raise TreasuryError(f"This request carries warnings ({', '.join(p['flags'])}). Say in your note why you are satisfied.")
        p["approvals"].append({"by": actor, "at": self.now().isoformat(), "note": note})
        done = len(p["approvals"]) >= p["approvals_needed"]
        if done: p["status"] = "APPROVED"
        self._hist(p, actor, "APPROVED" if done else "FIRST_APPROVAL", note); self._put("tr_payment", org, p)
        self.log("TR_PAYMENT_APPROVED", actor, pid, org, f"{p['ref']} {len(p['approvals'])}/{p['approvals_needed']}")
        return self._pview(p)

    def reject_payment(self, org, pid, actor, note) -> dict:
        p = self._p(org, pid)
        if p["status"] not in PAY_OPEN: raise TreasuryStateError("Only a payment that has not been released can be rejected.")
        self._two(actor, p["requested_by"], "asked for this payment")
        note = _txt(note, "The reason", 5, 500)
        p["status"] = "REJECTED"; self._hist(p, actor, "REJECTED", note); self._put("tr_payment", org, p)
        self.log("TR_PAYMENT_REJECTED", actor, pid, org, note)
        return self._pview(p)

    def cancel_payment(self, org, pid, actor, note) -> dict:
        p = self._p(org, pid)
        if p["status"] not in PAY_OPEN: raise TreasuryStateError("Only a payment that has not been released can be cancelled.")
        if actor != p["requested_by"]: raise TreasuryForbiddenError("Only the person who asked for this payment can cancel it. Anyone else who objects should reject it.")
        note = _txt(note, "The reason", 5, 500)
        p["status"] = "CANCELLED"; self._hist(p, actor, "CANCELLED", note); self._put("tr_payment", org, p)
        self.log("TR_PAYMENT_CANCELLED", actor, pid, org, note)
        return self._pview(p)

    def release_payment(self, org, pid, d, actor) -> dict:
        p = self._p(org, pid)
        if p["status"] != "APPROVED": raise TreasuryStateError("Only a fully approved payment can be recorded as released.")
        self._two(actor, p["requested_by"], "asked for this payment")
        when = _date(d.get("released_date"), "The date it was released")
        self._not_future(when, "The date it was released")
        ref = _txt(d.get("bank_reference"), "The bank's reference", 3, 80)
        p.update(status="RELEASED", released_by=actor, released_at=self.now().isoformat(), released_date=when.isoformat(), bank_reference=ref)
        self._hist(p, actor, "RELEASED", f"{when.isoformat()} {ref}")
        if p.get("flow_id"):
            f = self.store.get("tr_flow", f"{org}:{p['flow_id']}", for_update=True)
            if f and f.get("org") == org and f["status"] == FLOW_OPEN:
                f.update(status=FLOW_REALISED, actual_amount=p["amount"], actual_date=when.isoformat()); self._hist(f, actor, "REALISED", f"by payment {p['ref']}"); self._put("tr_flow", org, f)
        self._put("tr_payment", org, p); self.log("TR_PAYMENT_RELEASED", actor, pid, org, f"{p['ref']} {p['amount']} {p['currency']} ref {ref}")
        return self._pview(p)

    def _pview(self, p) -> dict:
        v = {k: p[k] for k in ("id", "ref", "account_id", "account_name", "currency", "payee", "amount", "due_date", "reason", "invoice_ref", "flow_id", "evidence", "flags", "approvals_needed", "approvals", "status",
                               "requested_by", "requested_at", "released_by", "released_at", "released_date", "bank_reference")}
        v["history"] = p["history"][-20:]; v["overdue"] = p["status"] in PAY_OPEN and date.fromisoformat(p["due_date"]) < self.today()
        return v

    def list_payment_requests(self, org, status=None) -> List[dict]:
        rows = self._all("tr_payment", org)
        if status: rows = [p for p in rows if p["status"] == status.upper()]
        return [self._pview(p) for p in sorted(rows, key=lambda p: p["ref"])]

    def get_payment_request(self, org, pid) -> dict: return self._pview(self._get("tr_payment", org, pid, "Payment request"))

    # ------------------------------------------------------------------ covenants
    def add_covenant(self, org, d, actor) -> dict:
        unit = _enum(d.get("unit"), UNITS, "The unit")
        cur = _currency(d.get("currency")) if unit == "AMOUNT" else None
        name = _txt(d.get("name"), "The covenant name", 3, 160)
        if any(c["status"] == "ACTIVE" and c["name"].casefold() == name.casefold() and c.get("lender", "").casefold() == _txt(d.get("lender"), "The lender", 0, 160, required=False).casefold() for c in self._all("tr_covenant", org)):
            raise TreasuryStateError("An active covenant with that name and lender already exists.")
        c = {"id": uuid.uuid4().hex, "org": org, "ref": None, "name": name, "lender": _txt(d.get("lender"), "The lender", 0, 160, required=False),
             "description": _txt(d.get("description"), "What the covenant measures", 3, 500), "comparator": _enum(d.get("comparator"), list(COMPARATORS), "The comparison"),
             "threshold": s4(_num(d.get("threshold"), "The threshold", 4)), "unit": unit, "currency": cur, "frequency": _enum(d.get("frequency"), list(FREQUENCIES), "How often it is tested"),
             "watch_pct": _int(d.get("watch_pct", 10), "The warning margin", 0, 50), "effective_from": _date(d.get("effective_from"), "The date it starts").isoformat(),
             "status": "ACTIVE", "results": [], "history": [], "created_by": actor, "created_at": self.now().isoformat()}
        c["ref"] = self._ref(org, "CV"); self._hist(c, actor, "ADDED"); self._put("tr_covenant", org, c); self.log("TR_COVENANT_ADDED", actor, c["id"], org, f"{c['ref']} {c['name']}")
        return self._cview(c)

    def retire_covenant(self, org, cid, note, actor) -> dict:
        c = self._get("tr_covenant", org, cid, "Covenant", for_update=True)
        if c["status"] != "ACTIVE": raise TreasuryStateError("This covenant is already retired.")
        note = _txt(note, "The reason", 5, 500)
        c["status"] = "RETIRED"; self._hist(c, actor, "RETIRED", note); self._put("tr_covenant", org, c); self.log("TR_COVENANT_RETIRED", actor, cid, org, note)
        return self._cview(c)

    @staticmethod
    def judge(c, value: Decimal):
        thr = Decimal(c["threshold"])
        head = (value - thr) if c["comparator"] == "MIN" else (thr - value)
        pct = None if thr == 0 else head / abs(thr) * 100
        if head < 0: status = "BREACHED"
        elif pct is not None and pct < c["watch_pct"]: status = "WATCH"
        else: status = "MET"
        return status, (None if pct is None else Decimal(pct).quantize(Decimal("0.1"))), head

    def record_covenant_result(self, org, cid, d, actor) -> dict:
        c = self._get("tr_covenant", org, cid, "Covenant", for_update=True)
        if c["status"] != "ACTIVE": raise TreasuryStateError("This covenant is retired.")
        pe = _date(d.get("period_end"), "The period end")
        self._not_future(pe, "The end of the period tested")
        if pe < date.fromisoformat(c["effective_from"]): raise TreasuryError("That period ended before the covenant started.")
        if any(r["period_end"] >= pe.isoformat() for r in c["results"]): raise TreasuryStateError("A result for that period or a later one is already recorded.")
        value = _num(d.get("value"), "The measured value", 4)
        status, pct, head = self.judge(c, value)
        note = _txt(d.get("note"), "Your explanation", 10 if status == "BREACHED" else 0, 800, required=status == "BREACHED")
        r = {"id": f"r{len(c['results']) + 1:04d}", "period_end": pe.isoformat(), "value": s4(value), "source": _txt(d.get("source"), "Where the figure came from", 3, 200), "note": note, "status": status,
             "headroom_pct": None if pct is None else str(pct), "headroom": s4(head), "recorded_by": actor, "recorded_at": self.now().isoformat(), "acknowledged_by": None, "acknowledged_at": None,
             "waiver_obtained": None, "acknowledgement": None}
        c["results"].append(r); self._hist(c, actor, "RESULT_RECORDED", f"{pe.isoformat()} {r['value']} {status}"); self._put("tr_covenant", org, c)
        self.log("TR_COVENANT_RESULT", actor, cid, org, f"{c['ref']} {pe.isoformat()} {status}")
        return self._cview(c)

    def acknowledge_covenant_breach(self, org, cid, rid, d, actor) -> dict:
        c = self._get("tr_covenant", org, cid, "Covenant", for_update=True)
        r = next((x for x in c["results"] if x["id"] == rid), None)
        if r is None: raise TreasuryNotFoundError("Result not found.")
        if r["status"] != "BREACHED": raise TreasuryStateError("Only a breach can be acknowledged.")
        if r["acknowledged_by"]: raise TreasuryStateError("This breach has already been acknowledged.")
        self._two(actor, r["recorded_by"], "recorded this result")
        if not isinstance(d.get("waiver_obtained"), bool): raise TreasuryError("Say whether a written waiver or amendment was obtained from the lender (yes or no).")
        note = _txt(d.get("note"), "Your note on what happens next", 10, 800)
        r.update(acknowledged_by=actor, acknowledged_at=self.now().isoformat(), waiver_obtained=d["waiver_obtained"], acknowledgement=note)
        self._hist(c, actor, "BREACH_ACKNOWLEDGED", f"{r['period_end']} waiver {'yes' if d['waiver_obtained'] else 'no'}"); self._put("tr_covenant", org, c)
        self.log("TR_COVENANT_ACKNOWLEDGED", actor, cid, org, f"{c['ref']} {r['period_end']} waiver {d['waiver_obtained']}")
        return self._cview(c)

    def _cview(self, c) -> dict:
        res = sorted(c["results"], key=lambda r: r["period_end"], reverse=True); last = res[0] if res else None
        if last:
            nxt_end = add_months(date.fromisoformat(last["period_end"]), FREQUENCIES[c["frequency"]])
        else:
            nxt_end = add_months(date.fromisoformat(c["effective_from"]), FREQUENCIES[c["frequency"]])
        due = nxt_end + timedelta(days=TEST_GRACE_DAYS)
        v = {k: c[k] for k in ("id", "ref", "name", "lender", "description", "comparator", "threshold", "unit", "currency", "frequency", "watch_pct", "effective_from", "status", "created_by", "created_at")}
        v.update(meaning=f"The measured value {COMPARATORS[c['comparator']]} {c['threshold']}.", latest=last, latest_status=last["status"] if last else "NOT_TESTED", results=res[:12], history=c["history"][-20:],
                 next_period_end=nxt_end.isoformat(), next_due=due.isoformat(), test_overdue=c["status"] == "ACTIVE" and self.today() > due,
                 unacknowledged_breach=any(r["status"] == "BREACHED" and not r["acknowledged_by"] for r in c["results"]))
        return v

    def list_covenants(self, org) -> List[dict]: return [self._cview(c) for c in sorted(self._all("tr_covenant", org), key=lambda c: c["ref"])]
    def get_covenant(self, org, cid) -> dict: return self._cview(self._get("tr_covenant", org, cid, "Covenant"))

    # ------------------------------------------------------------------ overview
    def treasury_overview(self, org) -> dict:
        pos = self.cash_position(org); fc = self.liquidity_forecast(org); pays = self._all("tr_payment", org); cov = [self._cview(c) for c in self._all("tr_covenant", org) if c["status"] == "ACTIVE"]
        flows = [f for f in self._all("tr_flow", org) if f["status"] == FLOW_OPEN]; today = self.today()
        attention = []
        for g in pos["currencies"]:
            if g["accounts_without_balance"]: attention.append({"kind": "NO_BALANCE", "text": f"{g['accounts_without_balance']} {g['currency']} account(s) have no balance recorded."})
            if g["stale"]: attention.append({"kind": "STALE_BALANCE", "text": f"{g['stale']} {g['currency']} balance(s) are out of date."})
        for c in fc["currencies"]:
            if c["shortfall_weeks"]: attention.append({"kind": "SHORTFALL", "text": f"{c['currency']}: cash is below {c['floor_basis']} in {c['shortfall_weeks']} of the next {fc['weeks']} weeks (lowest {c['lowest_closing']} in week {c['lowest_week']})."})
        waiting = [p for p in pays if p["status"] == "REQUESTED"]; ready = [p for p in pays if p["status"] == "APPROVED"]
        if waiting: attention.append({"kind": "PAYMENTS_WAITING", "text": f"{len(waiting)} payment request(s) are waiting for approval."})
        if ready: attention.append({"kind": "PAYMENTS_READY", "text": f"{len(ready)} approved payment(s) are waiting to be released."})
        for c in cov:
            if c["unacknowledged_breach"]: attention.append({"kind": "COVENANT_BREACH", "text": f"Covenant {c['ref']} ({c['name']}) has a breach nobody has acknowledged."})
            elif c["latest_status"] == "BREACHED": attention.append({"kind": "COVENANT_BREACH_ACKNOWLEDGED", "text": f"Covenant {c['ref']} ({c['name']}) is in breach (acknowledged)."})
            elif c["latest_status"] == "WATCH": attention.append({"kind": "COVENANT_WATCH", "text": f"Covenant {c['ref']} ({c['name']}) is close to its threshold."})
            if c["test_overdue"]: attention.append({"kind": "COVENANT_TEST_OVERDUE", "text": f"Covenant {c['ref']} ({c['name']}) was due to be tested by {c['next_due']}."})
        late = [f for f in flows if date.fromisoformat(f["flow_date"]) < today]
        if late: attention.append({"kind": "FLOWS_OVERDUE", "text": f"{len(late)} expected cash flow(s) are past their date and still open."})
        return {"counts": {"accounts": sum(1 for a in self._all("tr_account", org) if a["status"] == "ACTIVE"), "open_flows": len(flows), "payments_waiting": len(waiting), "payments_ready": len(ready),
                           "payments_released": sum(1 for p in pays if p["status"] == "RELEASED"), "covenants": len(cov), "covenants_breached": sum(1 for c in cov if c["latest_status"] == "BREACHED")},
                "position": pos["currencies"], "attention": attention, "limitations": LIMITATIONS, "policy": self.get_treasury_policy(org)}

    def treasury_options(self, org) -> dict:
        return {"directions": DIRECTIONS, "flow_categories": FLOW_CATEGORIES, "certainties": CERTAINTIES, "comparators": COMPARATORS, "units": UNITS, "frequencies": list(FREQUENCIES),
                "accounts": [{"id": a["id"], "ref": a["ref"], "name": a["name"], "currency": a["currency"]} for a in sorted(self._all("tr_account", org), key=lambda a: a["ref"]) if a["status"] == "ACTIVE"],
                "open_payment_flows": [{"id": f["id"], "ref": f["ref"], "description": f["description"], "amount": f["amount"], "currency": f["currency"]} for f in self._all("tr_flow", org)
                                       if f["status"] == FLOW_OPEN and f["direction"] == "OUT"], "limitations": LIMITATIONS}
