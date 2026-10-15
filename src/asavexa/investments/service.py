"""Investments (records and evidence): holdings, typed purchases, sales approved by a different person, weighted-average cost, typed price marks and gain or loss arithmetic.

Records (shared document store, per organisation): im_holding, im_setting.

Principles enforced here
  * This records the purchases, sales and prices that people type in and works out units held, cost basis, market value and gains or losses from them with exact decimal arithmetic. It reads no market data, gives no advice, posts nothing to the ledger and holds no money.
  * Purchases are recorded as they happen. A sale is proposed and a person other than the one who proposed it approves or rejects it. A price is a typed statement with a date and a source; an old one is flagged, not replaced.
  * Values are kept per currency and never added across currencies.
Nothing is edited or deleted; trades and marks are appended and sales are approved or rejected with a reason. Every step is audited. No accounting standard is claimed.
"""
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, List

from .errors import InvestmentsError, InvestmentsForbiddenError, InvestmentsNotFoundError, InvestmentsStateError

ASSET_CLASSES = ["EQUITY", "BOND", "FUND", "DEPOSIT", "PROPERTY", "OTHER"]
DEFAULTS = {"stale_days": 30}
CENT = Decimal("0.01")
UNIT = Decimal("0.0001")
MAX_MARKS = 500
LIMITATIONS = [
    "ASAVEXA records the purchases, sales and prices people type in and works out units, cost and gain or loss from them. It reads no market data, gives no investment advice and holds or moves no money.",
    "A price is a typed statement with a date and a source. ASAVEXA cannot check it and does not fetch prices. A price older than your window is flagged, not replaced.",
    "Cost is a weighted average. Tax lots, FIFO, accrued interest, dividends, splits, fees other than the one typed per trade, and currency conversion are not handled.",
    "The gain or loss is arithmetic on typed figures. It is not an accounting, tax or performance result and applies no standard, impairment or fair-value rule.",
    "Values in different currencies are never added together.",
    "ASAVEXA cannot know about holdings or trades nobody records.",
]


def _utc(): return datetime.now(timezone.utc)


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v)))
    v = " ".join("".join(c if c >= " " and c != "\x7f" else " " for c in v).split())
    if required and len(v) < lo:
        raise InvestmentsError(f"{name} is required (at least {lo} characters).")
    if v and len(v) < lo:
        raise InvestmentsError(f"{name} needs at least {lo} characters.")
    if len(v) > hi:
        raise InvestmentsError(f"{name} is too long (limit {hi} characters).")
    return v


def _date(v, name) -> date:
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", str(v).strip()): raise ValueError
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise InvestmentsError(f"{name} must be a real date written YYYY-MM-DD.")


def _enum(v, allowed, name) -> str:
    v = _txt(v, name, 1, 40).upper()
    if v not in allowed:
        raise InvestmentsError(f"{name} must be one of {', '.join(allowed)}.")
    return v


def _int(v, name, lo, hi) -> int:
    if isinstance(v, bool) or not re.fullmatch(r"[0-9]{1,15}", str(v).strip()):
        raise InvestmentsError(f"{name} must be a whole number from {lo} to {hi}.")
    n = int(str(v).strip())
    if not lo <= n <= hi:
        raise InvestmentsError(f"{name} must be a whole number from {lo} to {hi}.")
    return n


def _plain(v, name, places, example) -> Decimal:
    """A number written as text or a whole number, at most `places` decimals, ASCII digits, more than zero. Never a float."""
    if isinstance(v, bool) or isinstance(v, float) or v is None:
        raise InvestmentsError(f"{name} must be a number such as {example}.")
    t = str(v).strip()
    if not re.fullmatch(r"[0-9]{1,9}(\.[0-9]{1,%d})?" % places, t):
        raise InvestmentsError(f"{name} must be a number such as {example} (at most {places} decimals).")
    d = Decimal(t)
    if d == 0:
        raise InvestmentsError(f"{name} must be more than zero.")
    return d


def _units(v, name) -> Decimal: return _plain(v, name, 4, "12.5").quantize(UNIT)
def _price(v, name) -> Decimal: return _plain(v, name, 4, "101.25").quantize(UNIT)


def _money(v, name, zero_ok=False) -> Decimal:
    """An amount written as text or a whole number, at most two decimals. Never a float."""
    if isinstance(v, bool) or isinstance(v, float) or v is None:
        raise InvestmentsError(f"{name} must be an amount such as 12.50.")
    t = str(v).strip()
    if "," in t and not re.fullmatch(r"[0-9]{1,3}(,[0-9]{3})+(\.[0-9]{1,2})?", t):
        raise InvestmentsError(f"{name} must be an amount such as 12.50 (commas only between groups of three digits).")
    t = t.replace(",", "")
    if not re.fullmatch(r"[0-9]{1,10}(\.[0-9]{1,2})?", t):
        raise InvestmentsError(f"{name} must be an amount such as 12.50 (at most two decimals).")
    d = Decimal(t)
    if d == 0 and not zero_ok:
        raise InvestmentsError(f"{name} must be more than zero.")
    return d.quantize(CENT)


def _fee(v) -> Decimal:
    return Decimal("0.00") if v is None or (isinstance(v, str) and not v.strip()) else _money(v, "The fee", zero_ok=True)


def _u(d: Decimal) -> str:
    s = f"{d.quantize(UNIT):f}".rstrip("0").rstrip(".")
    return s or "0"


def _r2(d: Decimal) -> Decimal: return d.quantize(CENT, rounding=ROUND_HALF_UP)


def refnum(r) -> int:
    try: return int(str(r["ref"]).rsplit("-", 1)[1])
    except (KeyError, IndexError, ValueError): return 0


class InvestmentsService:
    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()

    def _not_future(self, d: date, what: str):
        if d > self.today() + timedelta(days=1):
            raise InvestmentsError(f"{what} cannot be in the future.")

    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r.get("org") != org:
            raise InvestmentsNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("im_setting", f"{org}:settings", for_update=for_update)
        if s and s.get("org") == org:
            return s
        return {"id": "settings", "org": org, **DEFAULTS, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("im_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other:
            raise InvestmentsForbiddenError(f"You {what}, so you cannot do this. A different person must.")

    # ------------------------------------------------------------------ policy
    def im_get_policy(self, org) -> dict:
        s = self._settings(org)
        return {"stale_days": s["stale_days"], "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"A price older than {s['stale_days']} days is flagged as out of date. This is your own setting, not a rule."}

    def im_set_policy(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        if d.get("stale_days") is not None: s["stale_days"] = _int(d["stale_days"], "The days before a price is out of date", 7, 365)
        s.update(updated_by=actor, updated_at=self.now().isoformat())
        self._put("im_setting", org, s)
        self.log("INVESTMENTS_POLICY_SET", actor, "settings", org, f"stale {s['stale_days']} days")
        return self.im_get_policy(org)

    # ------------------------------------------------------------------ views
    def _view(self, h) -> dict:
        v = {x: h[x] for x in h if x != "org"}
        units, basis = Decimal(h["units"]), Decimal(h["cost_basis"])
        mk = max(h["marks"], key=lambda m: (m["as_of"], m["no"]), default=None)
        mv = _r2(units * Decimal(mk["price"])) if mk else None
        stale_days = self._settings(h["org"])["stale_days"]
        v.update(average_cost=str((basis / units).quantize(UNIT, rounding=ROUND_HALF_UP)) if units else "0.0000",
                 pending_sells=sum(1 for t in h["trades"] if t["status"] == "PENDING"), latest_mark=mk,
                 market_value=str(mv) if mv is not None else None, unrealised=str(mv - basis) if mv is not None else None,
                 no_mark=h["status"] == "ACTIVE" and units > 0 and mk is None,
                 mark_stale=h["status"] == "ACTIVE" and units > 0 and mk is not None and date.fromisoformat(mk["as_of"]) + timedelta(days=stale_days) < self.today())
        return v

    # ------------------------------------------------------------------ holdings
    def im_add_holding(self, org, d, actor) -> dict:
        name = _txt(d.get("name"), "The holding name", 3, 150); ident = _txt(d.get("identifier"), "The identifier", 2, 40, required=False).upper()
        cls = _enum(d.get("asset_class"), ASSET_CLASSES, "The asset class"); cur = _txt(d.get("currency"), "The currency", 3, 3).upper()
        if not re.fullmatch(r"[A-Z]{3}", cur): raise InvestmentsError("The currency must be a three-letter code such as NGN.")
        acct = _txt(d.get("account"), "The account or custodian", 2, 150)
        if ident and any(o["identifier"] == ident and o["status"] == "ACTIVE" for o in self._all("im_holding", org)): raise InvestmentsStateError(f"An active holding with identifier {ident} already exists.")
        h = {"id": uuid.uuid4().hex, "org": org, "ref": None, "name": name, "identifier": ident or None, "asset_class": cls, "currency": cur, "account": acct, "status": "ACTIVE", "created_by": actor, "created_at": self.now().isoformat(),
             "units": "0", "cost_basis": "0.00", "realised_total": "0.00", "trades": [], "marks": [], "close_note": None, "history": []}
        h["ref"] = self._ref(org, "HD"); self._hist(h, actor, "ADDED")
        self._put("im_holding", org, h); self.log("INVESTMENTS_HOLDING_ADDED", actor, h["id"], org, h["ref"])
        return self._view(h)

    def im_close_holding(self, org, hid, reason, actor) -> dict:
        h = self._get("im_holding", org, hid, "Holding", for_update=True)
        if h["status"] != "ACTIVE": raise InvestmentsStateError("Only an active holding can be closed.")
        if Decimal(h["units"]) != 0: raise InvestmentsStateError("A holding can only be closed when no units are left.")
        if any(t["status"] == "PENDING" for t in h["trades"]): raise InvestmentsStateError("Decide the sales waiting for this holding first.")
        reason = _txt(reason, "A reason", 10, 500); h.update(status="CLOSED", close_note=reason); self._hist(h, actor, "CLOSED", reason)
        self._put("im_holding", org, h); self.log("INVESTMENTS_HOLDING_CLOSED", actor, hid, org, h["ref"])
        return self._view(h)

    def im_list_holdings(self, org, status=None) -> List[dict]:
        return [self._view(h) for h in sorted(self._all("im_holding", org), key=refnum) if not status or h["status"] == status]

    def im_get_holding(self, org, hid) -> dict: return self._view(self._get("im_holding", org, hid, "Holding"))

    def _active(self, org, hid) -> dict:
        h = self._get("im_holding", org, hid, "Holding", for_update=True)
        if h["status"] != "ACTIVE": raise InvestmentsStateError("This holding is closed.")
        return h

    def _new_trade(self, h, kind, units, **kw):
        return {"no": len(h["trades"]) + 1, "kind": kind, "units": _u(units), "price": None, "fee": "0.00", "gross": None, "amount": None, "proceeds": None, "cost_removed": None, "realised": None, "reference": None,
                "traded_on": None, "applied_on": None, "status": "PENDING", "by": None, "decided_by": None, "decision_note": None, "units_after": None, "basis_after": None, **kw}

    def _trade_figures(self, d):
        units = _units(d.get("units"), "The units"); price = _price(d.get("price"), "The price per unit"); fee = _fee(d.get("fee"))
        on = _date(d.get("traded_on"), "The trade date"); self._not_future(on, "The trade date"); ref = _txt(d.get("reference"), "The contract note or reference", 2, 100)
        gross = _r2(units * price)
        if gross == 0: raise InvestmentsError("Units times price is less than 0.01. Check the figures.")
        return units, price, fee, on, ref, gross

    # ------------------------------------------------------------------ purchases
    def im_buy(self, org, hid, d, actor) -> dict:
        h = self._active(org, hid); units, price, fee, on, ref, gross = self._trade_figures(d); cost = gross + fee
        t = self._new_trade(h, "BUY", units, price=str(price), fee=str(fee), gross=str(gross), amount=str(cost), reference=ref, traded_on=on.isoformat(), by=actor)
        h["units"] = _u(Decimal(h["units"]) + units); h["cost_basis"] = str(Decimal(h["cost_basis"]) + cost)
        t.update(status="APPLIED", applied_on=self.today().isoformat(), units_after=h["units"], basis_after=h["cost_basis"]); h["trades"].append(t); self._hist(h, actor, "BOUGHT")
        self._put("im_holding", org, h); self.log("INVESTMENTS_BUY_RECORDED", actor, hid, org, f"{h['ref']} #{t['no']}")
        return self._view(h)

    # ------------------------------------------------------------------ sales (two-person)
    def im_propose_sell(self, org, hid, d, actor) -> dict:
        h = self._active(org, hid); units, price, fee, on, ref, gross = self._trade_figures(d)
        if units > Decimal(h["units"]): raise InvestmentsStateError(f"Only {h['units']} units held. You cannot sell more than that.")
        if fee > gross: raise InvestmentsError("The fee cannot be more than units times price.")
        if sum(1 for t in h["trades"] if t["status"] == "PENDING") >= 5: raise InvestmentsStateError("Five sales are already waiting. Decide them first.")
        t = self._new_trade(h, "SELL", units, price=str(price), fee=str(fee), gross=str(gross), reference=ref, traded_on=on.isoformat(), by=actor)
        h["trades"].append(t); self._hist(h, actor, "SALE_PROPOSED")
        self._put("im_holding", org, h); self.log("INVESTMENTS_SELL_PROPOSED", actor, hid, org, f"{h['ref']} #{t['no']}")
        return self._view(h)

    def _pending(self, h, no) -> dict:
        t = next((t for t in h["trades"] if t["no"] == _int(no, "The trade number", 1, 1000000)), None)
        if t is None: raise InvestmentsNotFoundError("Sale not found.")
        if t["status"] != "PENDING" or t["kind"] != "SELL": raise InvestmentsStateError("Only a sale that is waiting can be decided.")
        return t

    def im_approve_sell(self, org, hid, no, d, actor) -> dict:
        h = self._get("im_holding", org, hid, "Holding", for_update=True); t = self._pending(h, no)
        self._two(actor, t["by"], "proposed this sale")
        note = _txt(d.get("note"), "An approval note", 10, 1000, required=False)
        if h["status"] != "ACTIVE": raise InvestmentsStateError("This holding is closed.")
        held, units, basis = Decimal(h["units"]), Decimal(t["units"]), Decimal(h["cost_basis"])
        if units > held: raise InvestmentsStateError(f"Only {h['units']} units held now. Reject this sale and propose a new one.")
        removed = basis if units == held else _r2(basis * units / held); proceeds = Decimal(t["gross"]) - Decimal(t["fee"]); realised = proceeds - removed
        h["units"] = _u(held - units); h["cost_basis"] = str(basis - removed); h["realised_total"] = str(Decimal(h["realised_total"]) + realised)
        t.update(status="APPLIED", decided_by=actor, decision_note=note or None, applied_on=self.today().isoformat(), proceeds=str(proceeds), cost_removed=str(removed), realised=str(realised), amount=str(proceeds), units_after=h["units"], basis_after=h["cost_basis"])
        self._hist(h, actor, "SALE_APPROVED", note)
        self._put("im_holding", org, h); self.log("INVESTMENTS_SELL_APPROVED", actor, hid, org, f"{h['ref']} #{t['no']}")
        return self._view(h)

    def im_reject_sell(self, org, hid, no, reason, actor) -> dict:
        h = self._get("im_holding", org, hid, "Holding", for_update=True); t = self._pending(h, no)
        self._two(actor, t["by"], "proposed this sale")
        reason = _txt(reason, "A reason", 10, 500); t.update(status="REJECTED", decided_by=actor, decision_note=reason); self._hist(h, actor, "SALE_REJECTED", reason)
        self._put("im_holding", org, h); self.log("INVESTMENTS_SELL_REJECTED", actor, hid, org, f"{h['ref']} #{t['no']}")
        return self._view(h)

    # ------------------------------------------------------------------ price marks
    def im_record_mark(self, org, hid, d, actor) -> dict:
        h = self._active(org, hid); price = _price(d.get("price"), "The price per unit"); on = _date(d.get("as_of"), "The price date"); self._not_future(on, "The price date")
        src = _txt(d.get("source"), "The source of the price", 2, 150)
        if len(h["marks"]) >= MAX_MARKS: raise InvestmentsStateError("This holding already has the most prices that can be kept.")
        h["marks"].append({"no": len(h["marks"]) + 1, "price": str(price), "as_of": on.isoformat(), "source": src, "by": actor, "recorded_at": self.now().isoformat()}); self._hist(h, actor, "PRICE_RECORDED")
        self._put("im_holding", org, h); self.log("INVESTMENTS_MARK_RECORDED", actor, hid, org, h["ref"])
        return self._view(h)

    # ------------------------------------------------------------------ overview
    def im_overview(self, org) -> dict:
        hs = self.im_list_holdings(org); act = [h for h in hs if h["status"] == "ACTIVE"]; att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("SELLS_TO_APPROVE", sum(h["pending_sells"] for h in hs), "sale(s) are waiting for a different person to decide them.")
        add("NO_PRICE", sum(1 for h in act if h["no_mark"]), "holding(s) with units have no price recorded.")
        add("PRICES_STALE", sum(1 for h in act if h["mark_stale"]), "holding(s) have a price older than your window.")
        tot = {}
        for h in hs:
            t = tot.setdefault(h["currency"], {"currency": h["currency"], "holdings": 0, "cost": Decimal("0"), "valued": 0, "unvalued": 0, "market_value": Decimal("0"), "unrealised": Decimal("0"), "realised": Decimal("0")})
            t["realised"] += Decimal(h["realised_total"])
            if h["status"] != "ACTIVE": continue
            t["holdings"] += 1; t["cost"] += Decimal(h["cost_basis"])
            if Decimal(h["units"]) == 0: continue
            if h["market_value"] is None: t["unvalued"] += 1
            else: t["valued"] += 1; t["market_value"] += Decimal(h["market_value"]); t["unrealised"] += Decimal(h["unrealised"])
        totals = [{**t, **{k: str(t[k]) for k in ("cost", "market_value", "unrealised", "realised")}} for t in sorted(tot.values(), key=lambda x: x["currency"])]
        return {"counts": {"active": len(act), "closed": sum(1 for h in hs if h["status"] == "CLOSED"), "no_price": sum(1 for h in act if h["no_mark"]), "stale": sum(1 for h in act if h["mark_stale"])},
                "totals": totals, "attention": att, "policy": self.im_get_policy(org), "limitations": LIMITATIONS}

    def im_options(self, org) -> dict:
        return {"asset_classes": ASSET_CLASSES, "limitations": LIMITATIONS}
