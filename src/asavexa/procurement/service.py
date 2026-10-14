"""Procurement chain (records and evidence): supplier -> contract -> purchase order -> delivery -> invoice (three-way match) -> payment -> supplier review.

Records (shared document store, per organisation): pc_supplier, pc_contract, pc_order, pc_delivery, pc_invoice, pc_review, pc_setting.

Principles enforced here
  * Nobody decides their own work: a supplier, contract, purchase order or invoice is approved by someone other than who created it; a purchase order at or above the
    organisation's limit needs two different approvers; goods are received by someone other than who ordered them.
  * An order can only go to an approved supplier, and (if it names a contract) only inside that contract's dates, currency and ceiling.
  * A delivery cannot exceed what was ordered. An invoice is matched line by line against the order and what was actually received; anything that does not match is an
    exception that a different person must knowingly override, in writing.
  * The same supplier invoice number is never accepted twice. An invoice is marked paid only against a payment that Treasury shows as released for the same payee, currency and amount,
    or against a bank reference typed in by a person.
  * Money is exact decimal arithmetic (lines are rounded half-up to 2 places). Currencies are never mixed or converted. Nothing is deleted; every step is audited.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Callable, List, Optional

from .errors import ProcurementError, ProcurementForbiddenError, ProcurementNotFoundError, ProcurementStateError

CATEGORIES = ["GOODS", "SERVICES", "WORKS", "CONSULTING", "OTHER"]
DEFAULT_DUAL_LIMIT = "10000.00"
DEFAULT_TOLERANCE = "2"
DEFAULT_WARNING_DAYS = 60
MAX_LINES = 50
MONEY_LIMIT = Decimal("1000000000000")
SCORES = ["delivery", "quality", "price", "service"]
LIMITATIONS = [
    "ASAVEXA records what people type in. It does not read contracts, check a supplier's identity, or verify that goods or services were really received.",
    "A match compares the invoice with the order and with the receipts people recorded. It is only as good as those records and is not an audit opinion.",
    "The approval limit and price tolerance are your own policy settings. The defaults are placeholders, not a standard or a legal requirement.",
    "Marking an invoice paid records a payment; it does not make one. If you link a Treasury payment it must be released, for the same payee, currency and amount.",
    "A supplier review is a person's judgement on a 1 to 5 scale. The average is arithmetic, not a rating issued by ASAVEXA.",
    "Dates are compared with today in UTC, with one day of leeway for people ahead of UTC.",
    "This is a management record. It is not procurement-law advice and does not by itself show compliance with any procurement rule.",
]


def _utc(): return datetime.now(timezone.utc)


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v)))
    v = " ".join("".join(c if c >= " " and c != "\x7f" else " " for c in v).split())
    if required and len(v) < lo:
        raise ProcurementError(f"{name} is required (at least {lo} characters).")
    if v and len(v) < lo:
        raise ProcurementError(f"{name} needs at least {lo} characters.")
    if len(v) > hi:
        raise ProcurementError(f"{name} is too long (limit {hi} characters).")
    return v


def _date(v, name) -> date:
    try:
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise ProcurementError(f"{name} must be a real date written YYYY-MM-DD.")


def _enum(v, allowed, name) -> str:
    v = _txt(v, name, 1, 40).upper()
    if v not in allowed:
        raise ProcurementError(f"{name} must be one of {', '.join(allowed)}.")
    return v


def _currency(v, name="Currency") -> str:
    v = _txt(v, name, 3, 3).upper()
    if not (len(v) == 3 and v.isalpha() and v.isascii()):
        raise ProcurementError(f"{name} must be a three-letter code such as NGN or USD.")
    return v


def _num(v, name, places, positive=False) -> Decimal:
    if isinstance(v, bool) or v is None or (isinstance(v, str) and not v.strip()):
        raise ProcurementError(f"{name} is required (a number).")
    try:
        d = Decimal(str(v).strip().replace(",", ""))
    except InvalidOperation:
        raise ProcurementError(f"{name} must be a number.")
    if not d.is_finite():
        raise ProcurementError(f"{name} must be a number.")
    if abs(d) >= MONEY_LIMIT:
        raise ProcurementError(f"{name} is too large.")
    try:
        exact = d == d.quantize(Decimal(1).scaleb(-places))
    except InvalidOperation:
        exact = False
    if not exact:
        raise ProcurementError(f"{name} can have at most {places} decimal places.")
    if d < 0 or (positive and d == 0):
        raise ProcurementError(f"{name} must be {'more than zero' if positive else 'zero or more'}.")
    return d.quantize(Decimal(1).scaleb(-places))


def money(v, name, positive=True) -> Decimal: return _num(v, name, 2, positive)
def qty(v, name) -> Decimal: return _num(v, name, 3, True)
def s2(d: Decimal) -> str: return f"{d.quantize(Decimal('0.01')):.2f}"
def s3(d: Decimal) -> str: return f"{d.quantize(Decimal('0.001')):.3f}"
def line_total(q: Decimal, p: Decimal) -> Decimal: return (q * p).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _int(v, name, lo, hi) -> int:
    if isinstance(v, bool) or not str(v).strip().lstrip("-").isdigit():
        raise ProcurementError(f"{name} must be a whole number from {lo} to {hi}.")
    n = int(str(v).strip())
    if not lo <= n <= hi:
        raise ProcurementError(f"{name} must be a whole number from {lo} to {hi}.")
    return n


class ProcurementService:
    def __init__(self, store, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.log, self.now = store, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()

    def _not_future(self, d: date, what: str):
        if d > self.today() + timedelta(days=1):
            raise ProcurementError(f"{what} cannot be in the future.")

    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r.get("org") != org:
            raise ProcurementNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("pc_setting", f"{org}:settings", for_update=for_update)
        if s and s.get("org") == org:
            return s
        return {"id": "settings", "org": org, "tolerance_pct": DEFAULT_TOLERANCE, "dual_limits": {"DEFAULT": DEFAULT_DUAL_LIMIT}, "warning_days": DEFAULT_WARNING_DAYS, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("pc_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other:
            raise ProcurementForbiddenError(f"You {what}, so you cannot decide it. A different person must.")

    def _dual_limit(self, s, currency) -> Decimal:
        return Decimal(s["dual_limits"].get(currency) or s["dual_limits"].get("DEFAULT") or DEFAULT_DUAL_LIMIT)

    # ------------------------------------------------------------------ policy
    def get_procurement_policy(self, org) -> dict:
        s = self._settings(org)
        return {"tolerance_pct": s["tolerance_pct"], "dual_limits": dict(s["dual_limits"]), "warning_days": s["warning_days"], "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"An invoice price may be up to {s['tolerance_pct']}% above the order price before it is an exception. A purchase order at or above the limit for its currency (or {s['dual_limits'].get('DEFAULT', DEFAULT_DUAL_LIMIT)} where none is set) needs two different approvers. "
                           f"A contract is flagged {s['warning_days']} days before it ends. These are your own policy settings, not a standard."}

    def set_procurement_policy(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        tol, dl, wd = s["tolerance_pct"], dict(s["dual_limits"]), s["warning_days"]
        if d.get("tolerance_pct") not in (None, ""):
            t = _num(d["tolerance_pct"], "The price tolerance", 1)
            if t > 20: raise ProcurementError("The price tolerance cannot be more than 20 percent.")
            tol = f"{t:.1f}".rstrip("0").rstrip(".") or "0"
        if d.get("dual_limits") is not None:
            if not isinstance(d["dual_limits"], dict): raise ProcurementError("Limits must be an amount per currency.")
            dl = {}
            for k, v in d["dual_limits"].items():
                key = "DEFAULT" if str(k).strip().upper() == "DEFAULT" else _currency(k, "Limit currency")
                dl[key] = s2(money(v, f"The two-approver limit for {k}"))
            dl.setdefault("DEFAULT", DEFAULT_DUAL_LIMIT)
        if d.get("warning_days") is not None: wd = _int(d["warning_days"], "The contract warning period", 1, 365)
        s.update(tolerance_pct=tol, dual_limits=dl, warning_days=wd, updated_by=actor, updated_at=self.now().isoformat())
        self._put("pc_setting", org, s); self.log("PC_POLICY_SET", actor, "settings", org, f"tolerance {tol}, limits {dl}, warning {wd}")
        return self.get_procurement_policy(org)

    # ------------------------------------------------------------------ suppliers
    def register_supplier(self, org, d, actor) -> dict:
        name = _txt(d.get("name"), "The supplier name", 2, 160)
        if any(x["name"].casefold() == name.casefold() for x in self._all("pc_supplier", org)):
            raise ProcurementStateError("A supplier with that name is already registered.")
        related = d.get("related_party")
        if not isinstance(related, bool): raise ProcurementError("Say whether anyone in your organisation is connected to this supplier (yes or no).")
        rnote = _txt(d.get("related_party_note"), "The description of the connection", 10 if related else 0, 500, required=related)
        x = {"id": uuid.uuid4().hex, "org": org, "ref": None, "name": name, "category": _enum(d.get("category") or "GOODS", CATEGORIES, "The category"), "country": _txt(d.get("country"), "The country", 0, 60, required=False),
             "contact": _txt(d.get("contact"), "The contact", 0, 200, required=False), "tax_ref": _txt(d.get("tax_ref"), "The tax or registration number", 0, 40, required=False),
             "related_party": related, "related_party_note": rnote, "status": "PENDING", "history": [], "created_by": actor, "created_at": self.now().isoformat(), "approved_by": None}
        x["ref"] = self._ref(org, "SU"); self._hist(x, actor, "REGISTERED"); self._put("pc_supplier", org, x); self.log("PC_SUPPLIER_REGISTERED", actor, x["id"], org, f"{x['ref']} {name}")
        return self._suview(org, x)

    def approve_supplier(self, org, sid, actor, note="") -> dict:
        x = self._get("pc_supplier", org, sid, "Supplier", for_update=True)
        if x["status"] != "PENDING": raise ProcurementStateError("Only a supplier waiting for approval can be approved.")
        self._two(actor, x["created_by"], "registered this supplier")
        note = _txt(note, "Your note", 5 if x["related_party"] else 0, 500, required=x["related_party"])
        x.update(status="ACTIVE", approved_by=actor); self._hist(x, actor, "APPROVED", note); self._put("pc_supplier", org, x); self.log("PC_SUPPLIER_APPROVED", actor, sid, org, x["ref"])
        return self._suview(org, x)

    def suspend_supplier(self, org, sid, note, actor) -> dict:
        x = self._get("pc_supplier", org, sid, "Supplier", for_update=True)
        if x["status"] not in ("ACTIVE", "PENDING"): raise ProcurementStateError("This supplier is already suspended.")
        note = _txt(note, "The reason", 5, 500); x["status"] = "SUSPENDED"; self._hist(x, actor, "SUSPENDED", note)
        self._put("pc_supplier", org, x); self.log("PC_SUPPLIER_SUSPENDED", actor, sid, org, note)
        return self._suview(org, x)

    def reinstate_supplier(self, org, sid, note, actor) -> dict:
        x = self._get("pc_supplier", org, sid, "Supplier", for_update=True)
        if x["status"] != "SUSPENDED": raise ProcurementStateError("Only a suspended supplier can be reinstated.")
        note = _txt(note, "The reason", 5, 500)
        who = next((h["by"] for h in reversed(x["history"]) if h["event"] == "SUSPENDED"), None); self._two(actor, who, "suspended this supplier")
        x["status"] = "ACTIVE"; self._hist(x, actor, "REINSTATED", note); self._put("pc_supplier", org, x); self.log("PC_SUPPLIER_REINSTATED", actor, sid, org, note)
        return self._suview(org, x)

    def _suview(self, org, x) -> dict:
        orders = [o for o in self._all("pc_order", org) if o["supplier_id"] == x["id"]]
        dels = [d for d in self._all("pc_delivery", org) if d["supplier_id"] == x["id"]]
        invs = [i for i in self._all("pc_invoice", org) if i["supplier_id"] == x["id"]]
        spend: dict = {}
        for i in invs:
            if i["status"] in ("APPROVED", "PAID"): spend[i["currency"]] = spend.get(i["currency"], Decimal(0)) + Decimal(i["total"])
        revs = sorted([r for r in self._all("pc_review", org) if r["supplier_id"] == x["id"]], key=lambda r: (r["created_at"], r["ref"]), reverse=True)
        v = {k: x[k] for k in ("id", "ref", "name", "category", "country", "contact", "tax_ref", "related_party", "related_party_note", "status", "created_by", "created_at", "approved_by")}
        v.update(orders=len(orders), deliveries=len(dels), invoices=len(invs), approved_spend={c: s2(a) for c, a in sorted(spend.items())}, latest_review=revs[0] if revs else None,
                 needs_review=bool(dels) and not revs, history=x["history"][-20:])
        return v

    def list_suppliers(self, org, status=None) -> List[dict]:
        rows = self._all("pc_supplier", org)
        if status: rows = [x for x in rows if x["status"] == status.upper()]
        return [self._suview(org, x) for x in sorted(rows, key=lambda x: x["ref"])]

    def get_supplier(self, org, sid) -> dict: return self._suview(org, self._get("pc_supplier", org, sid, "Supplier"))

    # ------------------------------------------------------------------ contracts
    def draft_contract(self, org, d, actor) -> dict:
        sup = self._get("pc_supplier", org, d.get("supplier_id"), "Supplier")
        if sup["status"] != "ACTIVE": raise ProcurementStateError("A contract can only be drafted for an approved supplier.")
        start, end = _date(d.get("start_date"), "The start date"), _date(d.get("end_date"), "The end date")
        if end <= start: raise ProcurementError("The end date must be after the start date.")
        c = {"id": uuid.uuid4().hex, "org": org, "ref": None, "supplier_id": sup["id"], "supplier_name": sup["name"], "title": _txt(d.get("title"), "The title", 3, 200), "description": _txt(d.get("description"), "The description", 0, 600, required=False),
             "currency": _currency(d.get("currency")), "ceiling": s2(money(d.get("ceiling"), "The ceiling")), "start_date": start.isoformat(), "end_date": end.isoformat(), "status": "PENDING", "history": [],
             "created_by": actor, "created_at": self.now().isoformat(), "approved_by": None}
        c["ref"] = self._ref(org, "CT"); self._hist(c, actor, "DRAFTED"); self._put("pc_contract", org, c); self.log("PC_CONTRACT_DRAFTED", actor, c["id"], org, f"{c['ref']} {c['ceiling']} {c['currency']}")
        return self._cview(org, c)

    def approve_contract(self, org, cid, actor, note="") -> dict:
        c = self._get("pc_contract", org, cid, "Contract", for_update=True)
        if c["status"] != "PENDING": raise ProcurementStateError("Only a contract waiting for approval can be approved.")
        self._two(actor, c["created_by"], "drafted this contract")
        if date.fromisoformat(c["end_date"]) < self.today(): raise ProcurementStateError("This contract has already ended.")
        if self._get("pc_supplier", org, c["supplier_id"], "Supplier")["status"] != "ACTIVE": raise ProcurementStateError("The supplier is no longer approved.")
        note = _txt(note, "Your note", 0, 500, required=False)
        c.update(status="ACTIVE", approved_by=actor); self._hist(c, actor, "APPROVED", note); self._put("pc_contract", org, c); self.log("PC_CONTRACT_APPROVED", actor, cid, org, c["ref"])
        return self._cview(org, c)

    def terminate_contract(self, org, cid, note, actor) -> dict:
        c = self._get("pc_contract", org, cid, "Contract", for_update=True)
        if c["status"] not in ("ACTIVE", "PENDING"): raise ProcurementStateError("This contract is already finished.")
        note = _txt(note, "The reason", 5, 500); c["status"] = "TERMINATED"; self._hist(c, actor, "TERMINATED", note)
        self._put("pc_contract", org, c); self.log("PC_CONTRACT_TERMINATED", actor, cid, org, note)
        return self._cview(org, c)

    def _committed(self, org, cid) -> Decimal:
        return sum((Decimal(o["total"]) for o in self._all("pc_order", org) if o.get("contract_id") == cid and o["status"] in ("APPROVED", "CLOSED")), Decimal(0))

    def _cview(self, org, c) -> dict:
        s = self._settings(org); today = self.today(); start, end = date.fromisoformat(c["start_date"]), date.fromisoformat(c["end_date"])
        committed = self._committed(org, c["id"]); ceiling = Decimal(c["ceiling"])
        state = "NOT_STARTED" if today < start else "EXPIRED" if today > end else "IN_FORCE"
        v = {k: c[k] for k in ("id", "ref", "supplier_id", "supplier_name", "title", "description", "currency", "ceiling", "start_date", "end_date", "status", "created_by", "created_at", "approved_by")}
        v.update(committed=s2(committed), remaining=s2(ceiling - committed), state=state, days_left=(end - today).days if c["status"] == "ACTIVE" and state != "EXPIRED" else None,
                 expiring_soon=c["status"] == "ACTIVE" and state == "IN_FORCE" and (end - today).days <= s["warning_days"], history=c["history"][-20:])
        return v

    def list_contracts(self, org) -> List[dict]: return [self._cview(org, c) for c in sorted(self._all("pc_contract", org), key=lambda c: c["ref"])]
    def get_contract(self, org, cid) -> dict: return self._cview(org, self._get("pc_contract", org, cid, "Contract"))

    # ------------------------------------------------------------------ purchase orders
    @staticmethod
    def _lines(raw, label="line") -> List[dict]:
        if not isinstance(raw, list) or not raw: raise ProcurementError("Add at least one line.")
        if len(raw) > MAX_LINES: raise ProcurementError(f"An order can have at most {MAX_LINES} lines.")
        out = []
        for i, l in enumerate(raw, 1):
            if not isinstance(l, dict): raise ProcurementError(f"Line {i} is not valid.")
            q, p = qty(l.get("qty"), f"Line {i} quantity"), money(l.get("unit_price"), f"Line {i} unit price")
            out.append({"n": i, "description": _txt(l.get("description"), f"Line {i} description", 2, 200), "qty": s3(q), "unit_price": s2(p), "total": s2(line_total(q, p))})
        return out

    def raise_purchase_order(self, org, d, actor) -> dict:
        sup = self._get("pc_supplier", org, d.get("supplier_id"), "Supplier")
        if sup["status"] != "ACTIVE": raise ProcurementStateError("An order can only go to an approved supplier.")
        cur = _currency(d.get("currency")); lines = self._lines(d.get("lines")); total = sum((Decimal(l["total"]) for l in lines), Decimal(0))
        con = None
        if d.get("contract_id"):
            con = self._get("pc_contract", org, d["contract_id"], "Contract")
            if con["status"] != "ACTIVE" or con["supplier_id"] != sup["id"] or con["currency"] != cur:
                raise ProcurementError("The contract must be active, with the same supplier and currency as the order.")
            if not (date.fromisoformat(con["start_date"]) <= self.today() <= date.fromisoformat(con["end_date"])): raise ProcurementStateError("The contract is not in force today.")
        exp = _date(d.get("expected_date"), "The expected delivery date")
        if exp < self.today() - timedelta(days=1): raise ProcurementError("The expected delivery date cannot be in the past.")
        s = self._settings(org)
        o = {"id": uuid.uuid4().hex, "org": org, "ref": None, "supplier_id": sup["id"], "supplier_name": sup["name"], "contract_id": con["id"] if con else None, "contract_ref": con["ref"] if con else None, "currency": cur,
             "lines": lines, "total": s2(total), "expected_date": exp.isoformat(), "purpose": _txt(d.get("purpose"), "The purpose", 5, 500), "approvals_needed": 2 if total >= self._dual_limit(s, cur) else 1, "approvals": [],
             "status": "REQUESTED", "requested_by": actor, "requested_at": self.now().isoformat(), "closed_note": None, "history": []}
        o["ref"] = self._ref(org, "PO"); self._hist(o, actor, "REQUESTED"); self._put("pc_order", org, o); self.log("PC_ORDER_REQUESTED", actor, o["id"], org, f"{o['ref']} {o['total']} {cur}")
        return self._oview(org, o)

    def approve_purchase_order(self, org, oid, actor, note="") -> dict:
        o = self._get("pc_order", org, oid, "Purchase order", for_update=True)
        if o["status"] != "REQUESTED": raise ProcurementStateError("Only an order waiting for approval can be approved.")
        self._two(actor, o["requested_by"], "raised this order")
        if any(a["by"] == actor for a in o["approvals"]): raise ProcurementForbiddenError("You have already approved this order. A different person must give the other approval.")
        sup = self._get("pc_supplier", org, o["supplier_id"], "Supplier")
        if sup["status"] != "ACTIVE": raise ProcurementStateError("The supplier is no longer approved.")
        if o["contract_id"]:
            con = self._get("pc_contract", org, o["contract_id"], "Contract")
            if con["status"] != "ACTIVE" or date.fromisoformat(con["end_date"]) < self.today(): raise ProcurementStateError("The contract is no longer in force.")
            if self._committed(org, con["id"]) + Decimal(o["total"]) > Decimal(con["ceiling"]):
                raise ProcurementStateError(f"Approving this order would take the contract {con['ref']} over its ceiling of {con['ceiling']} {con['currency']}.")
        note = _txt(note, "Your note", 0, 500, required=False)
        o["approvals"].append({"by": actor, "at": self.now().isoformat(), "note": note}); done = len(o["approvals"]) >= o["approvals_needed"]
        if done: o["status"] = "APPROVED"
        self._hist(o, actor, "APPROVED" if done else "FIRST_APPROVAL", note); self._put("pc_order", org, o); self.log("PC_ORDER_APPROVED", actor, oid, org, f"{o['ref']} {len(o['approvals'])}/{o['approvals_needed']}")
        return self._oview(org, o)

    def reject_purchase_order(self, org, oid, note, actor) -> dict:
        o = self._get("pc_order", org, oid, "Purchase order", for_update=True)
        if o["status"] != "REQUESTED": raise ProcurementStateError("Only an order waiting for approval can be rejected.")
        self._two(actor, o["requested_by"], "raised this order")
        note = _txt(note, "The reason", 5, 500); o["status"] = "REJECTED"; self._hist(o, actor, "REJECTED", note); self._put("pc_order", org, o); self.log("PC_ORDER_REJECTED", actor, oid, org, note)
        return self._oview(org, o)

    def cancel_purchase_order(self, org, oid, note, actor) -> dict:
        o = self._get("pc_order", org, oid, "Purchase order", for_update=True)
        if o["status"] not in ("REQUESTED", "APPROVED"): raise ProcurementStateError("Only an order that is not finished can be cancelled.")
        if actor != o["requested_by"]: raise ProcurementForbiddenError("Only the person who raised this order can cancel it. Anyone else who objects should reject it.")
        if any(x["order_id"] == oid for x in self._all("pc_delivery", org)) or any(i["order_id"] == oid and i["status"] != "REJECTED" for i in self._all("pc_invoice", org)):
            raise ProcurementStateError("Goods or an invoice are already recorded against this order. Close it instead, with a reason.")
        note = _txt(note, "The reason", 5, 500); o["status"] = "CANCELLED"; self._hist(o, actor, "CANCELLED", note); self._put("pc_order", org, o); self.log("PC_ORDER_CANCELLED", actor, oid, org, note)
        return self._oview(org, o)

    def close_purchase_order(self, org, oid, note, actor) -> dict:
        o = self._get("pc_order", org, oid, "Purchase order", for_update=True)
        if o["status"] != "APPROVED": raise ProcurementStateError("Only an approved order can be closed.")
        note = _txt(note, "The reason", 5, 500)
        if any(i["order_id"] == oid and i["status"] in ("RECORDED", "EXCEPTION", "MATCHED") for i in self._all("pc_invoice", org)):
            raise ProcurementStateError("An invoice for this order is still waiting for a decision.")
        o["status"] = "CLOSED"; o["closed_note"] = note; self._hist(o, actor, "CLOSED", note); self._put("pc_order", org, o); self.log("PC_ORDER_CLOSED", actor, oid, org, note)
        return self._oview(org, o)

    def _received(self, org, oid) -> dict:
        rec: dict = {}
        for d in self._all("pc_delivery", org):
            if d["order_id"] == oid:
                for l in d["lines"]: rec[l["line"]] = rec.get(l["line"], Decimal(0)) + Decimal(l["qty"])
        return rec

    def _invoiced(self, org, oid, skip=None) -> dict:
        inv: dict = {}
        for i in self._all("pc_invoice", org):
            if i["order_id"] == oid and i["status"] != "REJECTED" and i["id"] != skip:
                for l in i["lines"]: inv[l["line"]] = inv.get(l["line"], Decimal(0)) + Decimal(l["qty"])
        return inv

    def _oview(self, org, o, chain=False) -> dict:
        rec, inv = self._received(org, o["id"]), self._invoiced(org, o["id"])
        lines = [{**l, "received": s3(rec.get(l["n"], Decimal(0))), "invoiced": s3(inv.get(l["n"], Decimal(0))), "outstanding": s3(Decimal(l["qty"]) - rec.get(l["n"], Decimal(0)))} for l in o["lines"]]
        got = sum(rec.values(), Decimal(0)); want = sum((Decimal(l["qty"]) for l in o["lines"]), Decimal(0))
        fulfil = "NOT_RECEIVED" if got == 0 else "RECEIVED" if all(Decimal(l["outstanding"]) <= 0 for l in lines) else "PARTLY_RECEIVED"
        v = {k: o[k] for k in ("id", "ref", "supplier_id", "supplier_name", "contract_id", "contract_ref", "currency", "total", "expected_date", "purpose", "approvals_needed", "approvals", "status", "requested_by", "requested_at", "closed_note")}
        v.update(lines=lines, fulfilment=fulfil if o["status"] in ("APPROVED", "CLOSED") else None, overdue=o["status"] == "APPROVED" and fulfil != "RECEIVED" and date.fromisoformat(o["expected_date"]) < self.today(), history=o["history"][-20:])
        if chain:
            v["deliveries"] = [self._dview(d) for d in sorted((d for d in self._all("pc_delivery", org) if d["order_id"] == o["id"]), key=lambda d: d["ref"])]
            v["invoices"] = [self._ivview(org, i) for i in sorted((i for i in self._all("pc_invoice", org) if i["order_id"] == o["id"]), key=lambda i: i["ref"])]
        return v

    def list_purchase_orders(self, org, status=None, supplier_id=None) -> List[dict]:
        rows = self._all("pc_order", org)
        if status: rows = [o for o in rows if o["status"] == status.upper()]
        if supplier_id: rows = [o for o in rows if o["supplier_id"] == supplier_id]
        return [self._oview(org, o) for o in sorted(rows, key=lambda o: o["ref"])]

    def get_purchase_order(self, org, oid) -> dict: return self._oview(org, self._get("pc_order", org, oid, "Purchase order"), chain=True)

    # ------------------------------------------------------------------ deliveries
    def record_delivery(self, org, oid, d, actor) -> dict:
        o = self._get("pc_order", org, oid, "Purchase order", for_update=True)
        if o["status"] != "APPROVED": raise ProcurementStateError("Goods can only be received against an approved order that is still open.")
        self._two(actor, o["requested_by"], "raised this order")
        when = _date(d.get("received_date"), "The date received"); self._not_future(when, "The date received")
        raw = d.get("lines")
        if not isinstance(raw, list) or not raw: raise ProcurementError("Say what was received.")
        rec = self._received(org, oid); by_n = {l["n"]: l for l in o["lines"]}; lines = []
        for r in raw:
            n = _int(r.get("line"), "The line number", 1, MAX_LINES)
            if n not in by_n: raise ProcurementError(f"The order has no line {n}.")
            if any(x["line"] == n for x in lines): raise ProcurementError(f"Line {n} appears twice.")
            q = qty(r.get("qty"), f"Quantity for line {n}")
            left = Decimal(by_n[n]["qty"]) - rec.get(n, Decimal(0))
            if q > left: raise ProcurementError(f"Line {n}: only {s3(left)} is still outstanding, so {s3(q)} cannot be received.")
            lines.append({"line": n, "description": by_n[n]["description"], "qty": s3(q)})
        x = {"id": uuid.uuid4().hex, "org": org, "ref": None, "order_id": oid, "order_ref": o["ref"], "supplier_id": o["supplier_id"], "supplier_name": o["supplier_name"], "received_date": when.isoformat(), "lines": lines,
             "note": _txt(d.get("note"), "The note", 0, 500, required=False), "received_by": actor, "received_at": self.now().isoformat()}
        x["ref"] = self._ref(org, "DL"); self._put("pc_delivery", org, x); self._hist(o, actor, "DELIVERY_RECORDED", x["ref"]); self._put("pc_order", org, o)
        self.log("PC_DELIVERY_RECORDED", actor, x["id"], org, f"{x['ref']} for {o['ref']}")
        return self._dview(x)

    @staticmethod
    def _dview(d) -> dict: return {k: d[k] for k in ("id", "ref", "order_id", "order_ref", "supplier_id", "supplier_name", "received_date", "lines", "note", "received_by", "received_at")}

    def list_deliveries(self, org, order_id=None) -> List[dict]:
        rows = [d for d in self._all("pc_delivery", org) if not order_id or d["order_id"] == order_id]
        return [self._dview(d) for d in sorted(rows, key=lambda d: d["ref"])]

    # ------------------------------------------------------------------ invoices
    def _match(self, org, o, lines, cur, skip=None) -> List[str]:
        flags = []; s = self._settings(org); tol = Decimal(s["tolerance_pct"]); rec, inv = self._received(org, o["id"]), self._invoiced(org, o["id"], skip)
        if cur != o["currency"]: flags.append("CURRENCY_DIFFERS")
        by_n = {l["n"]: l for l in o["lines"]}
        for l in lines:
            ol = by_n[l["line"]]
            if inv.get(l["line"], Decimal(0)) + Decimal(l["qty"]) > rec.get(l["line"], Decimal(0)): flags.append("NOT_YET_RECEIVED")
            if Decimal(l["unit_price"]) > Decimal(ol["unit_price"]) * (Decimal(100) + tol) / Decimal(100): flags.append("PRICE_ABOVE_ORDER")
        return sorted(set(flags))

    def record_invoice(self, org, oid, d, actor) -> dict:
        o = self._get("pc_order", org, oid, "Purchase order", for_update=True)
        if o["status"] not in ("APPROVED", "CLOSED"): raise ProcurementStateError("An invoice can only be recorded against an approved order.")
        number = _txt(d.get("invoice_number"), "The supplier's invoice number", 1, 60)
        if any(i["supplier_id"] == o["supplier_id"] and i["invoice_number"].casefold() == number.casefold() and i["status"] != "REJECTED" for i in self._all("pc_invoice", org)):
            raise ProcurementStateError("This supplier's invoice number has already been recorded. The same invoice is never accepted twice.")
        idate = _date(d.get("invoice_date"), "The invoice date"); self._not_future(idate, "The invoice date"); due = _date(d.get("due_date"), "The due date")
        if due < idate: raise ProcurementError("The due date cannot be before the invoice date.")
        cur = _currency(d.get("currency") or o["currency"]); raw = d.get("lines")
        if not isinstance(raw, list) or not raw: raise ProcurementError("Add at least one invoice line.")
        by_n = {l["n"]: l for l in o["lines"]}; lines = []
        for r in raw:
            n = _int(r.get("line"), "The line number", 1, MAX_LINES)
            if n not in by_n: raise ProcurementError(f"The order has no line {n}.")
            if any(x["line"] == n for x in lines): raise ProcurementError(f"Line {n} appears twice.")
            q, p = qty(r.get("qty"), f"Invoice quantity for line {n}"), money(r.get("unit_price"), f"Invoice unit price for line {n}")
            lines.append({"line": n, "description": by_n[n]["description"], "qty": s3(q), "unit_price": s2(p), "total": s2(line_total(q, p))})
        total = sum((Decimal(l["total"]) for l in lines), Decimal(0)); flags = self._match(org, o, lines, cur)
        i = {"id": uuid.uuid4().hex, "org": org, "ref": None, "order_id": oid, "order_ref": o["ref"], "supplier_id": o["supplier_id"], "supplier_name": o["supplier_name"], "invoice_number": number, "invoice_date": idate.isoformat(),
             "due_date": due.isoformat(), "currency": cur, "lines": lines, "total": s2(total), "flags": flags, "status": "EXCEPTION" if flags else "MATCHED", "override_note": None, "payment": None, "history": [],
             "recorded_by": actor, "recorded_at": self.now().isoformat(), "decided_by": None}
        i["ref"] = self._ref(org, "IV"); self._hist(i, actor, "RECORDED", ", ".join(flags)); self._put("pc_invoice", org, i); self.log("PC_INVOICE_RECORDED", actor, i["id"], org, f"{i['ref']} {i['total']} {cur} {flags}")
        return self._ivview(org, i)

    def approve_invoice(self, org, iid, actor, note="") -> dict:
        i = self._get("pc_invoice", org, iid, "Invoice", for_update=True)
        if i["status"] not in ("MATCHED", "EXCEPTION"): raise ProcurementStateError("Only an invoice waiting for a decision can be approved.")
        self._two(actor, i["recorded_by"], "recorded this invoice")
        note = _txt(note, "Your note", 10 if i["flags"] else 0, 500, required=bool(i["flags"]))
        if i["flags"]:
            o = self._get("pc_order", org, i["order_id"], "Purchase order"); fresh = self._match(org, o, i["lines"], i["currency"], skip=i["id"])
            if "CURRENCY_DIFFERS" in fresh: raise ProcurementStateError("An invoice in a different currency from the order cannot be approved. Reject it and ask for a corrected one.")
            i["override_note"] = note
        i.update(status="APPROVED", decided_by=actor); self._hist(i, actor, "APPROVED_WITH_OVERRIDE" if i["flags"] else "APPROVED", note); self._put("pc_invoice", org, i)
        self.log("PC_INVOICE_APPROVED", actor, iid, org, f"{i['ref']} override {bool(i['flags'])}")
        return self._ivview(org, i)

    def reject_invoice(self, org, iid, note, actor) -> dict:
        i = self._get("pc_invoice", org, iid, "Invoice", for_update=True)
        if i["status"] not in ("MATCHED", "EXCEPTION"): raise ProcurementStateError("Only an invoice waiting for a decision can be rejected.")
        self._two(actor, i["recorded_by"], "recorded this invoice")
        note = _txt(note, "The reason", 5, 500); i.update(status="REJECTED", decided_by=actor); self._hist(i, actor, "REJECTED", note); self._put("pc_invoice", org, i)
        self.log("PC_INVOICE_REJECTED", actor, iid, org, note)
        return self._ivview(org, i)

    def mark_invoice_paid(self, org, iid, d, actor) -> dict:
        i = self._get("pc_invoice", org, iid, "Invoice", for_update=True)
        if i["status"] != "APPROVED": raise ProcurementStateError("Only an approved invoice can be marked as paid.")
        pay_id = _txt(d.get("treasury_payment_id"), "The Treasury payment", 0, 64, required=False)
        if pay_id:
            p = self.store.get("tr_payment", f"{org}:{pay_id}")
            if p is None or p.get("org") != org: raise ProcurementNotFoundError("That Treasury payment was not found.")
            if p["status"] != "RELEASED": raise ProcurementStateError("That Treasury payment has not been released.")
            if p["currency"] != i["currency"] or Decimal(p["amount"]) != Decimal(i["total"]): raise ProcurementError("The Treasury payment must be for the same currency and exact amount as the invoice.")
            if p["payee"].casefold() != i["supplier_name"].casefold(): raise ProcurementError("The Treasury payment is to a different payee from this supplier.")
            if any(x["id"] != iid and (x.get("payment") or {}).get("treasury_payment_id") == pay_id for x in self._all("pc_invoice", org)): raise ProcurementStateError("That Treasury payment is already used for another invoice.")
            pay = {"treasury_payment_id": pay_id, "treasury_ref": p["ref"], "bank_reference": p["bank_reference"], "paid_date": p["released_date"]}
        else:
            paid = _date(d.get("paid_date"), "The date paid"); self._not_future(paid, "The date paid")
            pay = {"treasury_payment_id": None, "treasury_ref": None, "bank_reference": _txt(d.get("bank_reference"), "The bank's reference", 3, 80), "paid_date": paid.isoformat()}
        i.update(status="PAID", payment={**pay, "marked_by": actor}); self._hist(i, actor, "PAID", pay["bank_reference"]); self._put("pc_invoice", org, i)
        self.log("PC_INVOICE_PAID", actor, iid, org, f"{i['ref']} ref {pay['bank_reference']}")
        return self._ivview(org, i)

    def _ivview(self, org, i) -> dict:
        v = {k: i[k] for k in ("id", "ref", "order_id", "order_ref", "supplier_id", "supplier_name", "invoice_number", "invoice_date", "due_date", "currency", "lines", "total", "flags", "status", "override_note", "payment", "recorded_by", "recorded_at", "decided_by")}
        v["overdue"] = i["status"] == "APPROVED" and date.fromisoformat(i["due_date"]) < self.today(); v["history"] = i["history"][-20:]
        return v

    def list_invoices(self, org, status=None, order_id=None) -> List[dict]:
        rows = self._all("pc_invoice", org)
        if status: rows = [i for i in rows if i["status"] == status.upper()]
        if order_id: rows = [i for i in rows if i["order_id"] == order_id]
        return [self._ivview(org, i) for i in sorted(rows, key=lambda i: i["ref"])]

    def get_invoice(self, org, iid) -> dict: return self._ivview(org, self._get("pc_invoice", org, iid, "Invoice"))

    # ------------------------------------------------------------------ supplier reviews
    def review_supplier(self, org, sid, d, actor) -> dict:
        sup = self._get("pc_supplier", org, sid, "Supplier")
        period = _txt(d.get("period"), "The period", 3, 20)
        if any(r["supplier_id"] == sid and r["period"].casefold() == period.casefold() for r in self._all("pc_review", org)): raise ProcurementStateError("This supplier already has a review for that period.")
        raw = d.get("scores")
        if not isinstance(raw, dict): raise ProcurementError("Give a score from 1 to 5 for delivery, quality, price and service.")
        scores = {k: _int(raw.get(k), f"The {k} score", 1, 5) for k in SCORES}
        avg = (Decimal(sum(scores.values())) / Decimal(len(scores))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        low = min(scores.values()) <= 2
        r = {"id": uuid.uuid4().hex, "org": org, "ref": None, "supplier_id": sid, "supplier_name": sup["name"], "period": period, "scores": scores, "average": str(avg), "low": low,
             "comment": _txt(d.get("comment"), "Your comment (required when any score is 1 or 2)", 10 if low else 0, 800, required=low), "reviewed_by": actor, "created_at": self.now().isoformat()}
        r["ref"] = self._ref(org, "SR"); self._put("pc_review", org, r); self.log("PC_SUPPLIER_REVIEWED", actor, r["id"], org, f"{r['ref']} {sup['name']} {period} avg {avg}")
        return r

    def list_supplier_reviews(self, org, supplier_id=None) -> List[dict]:
        rows = [r for r in self._all("pc_review", org) if not supplier_id or r["supplier_id"] == supplier_id]
        return sorted(rows, key=lambda r: (r["created_at"], r["ref"]), reverse=True)

    # ------------------------------------------------------------------ overview
    def procurement_overview(self, org) -> dict:
        today = self.today(); sup = [self._suview(org, x) for x in self._all("pc_supplier", org)]; con = [self._cview(org, c) for c in self._all("pc_contract", org)]
        orders = [self._oview(org, o) for o in self._all("pc_order", org)]; invs = self._all("pc_invoice", org); att = []
        pend = [x for x in sup if x["status"] == "PENDING"]
        if pend: att.append({"kind": "SUPPLIERS_PENDING", "text": f"{len(pend)} supplier(s) are waiting for approval."})
        cp = [c for c in con if c["status"] == "PENDING"]
        if cp: att.append({"kind": "CONTRACTS_PENDING", "text": f"{len(cp)} contract(s) are waiting for approval."})
        for c in con:
            if c["expiring_soon"]: att.append({"kind": "CONTRACT_ENDING", "text": f"Contract {c['ref']} ({c['title']}) ends in {c['days_left']} days."})
            if c["status"] == "ACTIVE" and c["state"] == "EXPIRED": att.append({"kind": "CONTRACT_EXPIRED", "text": f"Contract {c['ref']} ({c['title']}) has ended but is still marked active."})
            if c["status"] == "ACTIVE" and Decimal(c["ceiling"]) > 0 and Decimal(c["committed"]) * 100 >= Decimal(c["ceiling"]) * 90: att.append({"kind": "CONTRACT_CEILING", "text": f"Contract {c['ref']} has committed {c['committed']} of {c['ceiling']} {c['currency']}."})
        op = [o for o in orders if o["status"] == "REQUESTED"]
        if op: att.append({"kind": "ORDERS_WAITING", "text": f"{len(op)} purchase order(s) are waiting for approval."})
        late = [o for o in orders if o["overdue"]]
        if late: att.append({"kind": "DELIVERIES_LATE", "text": f"{len(late)} approved order(s) are past their expected delivery date and not fully received."})
        ex = [i for i in invs if i["status"] == "EXCEPTION"]
        if ex: att.append({"kind": "INVOICE_EXCEPTIONS", "text": f"{len(ex)} invoice(s) do not match their order and need a decision."})
        mt = [i for i in invs if i["status"] == "MATCHED"]
        if mt: att.append({"kind": "INVOICES_WAITING", "text": f"{len(mt)} matched invoice(s) are waiting for approval."})
        due = [i for i in invs if i["status"] == "APPROVED"]
        if due: att.append({"kind": "INVOICES_UNPAID", "text": f"{len(due)} approved invoice(s) have not been marked as paid" + (f", {sum(1 for i in due if date.fromisoformat(i['due_date']) < today)} past their due date." if any(date.fromisoformat(i['due_date']) < today for i in due) else ".")})
        nr = [x for x in sup if x["needs_review"]]
        if nr: att.append({"kind": "REVIEWS_MISSING", "text": f"{len(nr)} supplier(s) have delivered goods but have never been reviewed."})
        return {"counts": {"suppliers": sum(1 for x in sup if x["status"] == "ACTIVE"), "contracts": sum(1 for c in con if c["status"] == "ACTIVE"), "orders_open": sum(1 for o in orders if o["status"] == "APPROVED"),
                           "orders_waiting": len(op), "invoices_waiting": len(ex) + len(mt), "invoices_unpaid": len(due), "invoices_paid": sum(1 for i in invs if i["status"] == "PAID")},
                "attention": att, "limitations": LIMITATIONS, "policy": self.get_procurement_policy(org)}

    def procurement_options(self, org) -> dict:
        return {"categories": CATEGORIES, "scores": SCORES,
                "suppliers": [{"id": x["id"], "ref": x["ref"], "name": x["name"]} for x in sorted(self._all("pc_supplier", org), key=lambda x: x["ref"]) if x["status"] == "ACTIVE"],
                "contracts": [{"id": c["id"], "ref": c["ref"], "title": c["title"], "supplier_id": c["supplier_id"], "currency": c["currency"]} for c in sorted(self._all("pc_contract", org), key=lambda c: c["ref"]) if c["status"] == "ACTIVE"],
                "limitations": LIMITATIONS}
