"""Inventory (records and evidence): stock items, receipts, issues, approved adjustments, weighted-average valuation and reorder alerts.

Records (shared document store, per organisation): iv_item, iv_setting.

Principles enforced here
  * This records the stock movements that people type in and works out quantity on hand and a weighted-average value from them, using exact decimal arithmetic. It posts nothing to the ledger and counts nothing.
  * Receipts and issues are recorded as they happen; stock can never go below zero. A correction to the quantity (a count difference, damage, loss) is an adjustment that a person other than the one who proposed it must approve.
  * Values are kept per currency and never added across currencies. Whole units only.
Nothing is edited or deleted; movements are appended and adjustments are approved or rejected with a reason. Every step is audited. No accounting standard is claimed.
"""
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, List

from .errors import InventoryError, InventoryForbiddenError, InventoryNotFoundError, InventoryStateError

REASON_KINDS = ["COUNT_DIFFERENCE", "DAMAGE", "LOSS", "OTHER"]
DIRECTIONS = ["INCREASE", "DECREASE"]
DEFAULTS = {"stale_days": 180}
CENT = Decimal("0.01")
MAX_QTY = 10_000_000
LIMITATIONS = [
    "ASAVEXA records the movements people type in and works out quantity and a weighted-average value from them. It counts no stock, reads no scanner and posts nothing to the ledger.",
    "The value here is arithmetic on typed receipts (average cost method). It is not an accounting or tax valuation and applies no standard, write-down or net realisable value test.",
    "Quantities are whole units. Batches, expiry dates, serial numbers and locations within a site are not tracked.",
    "A receipt or issue is a person's statement. A different person approves a correction to the quantity, but ASAVEXA cannot tell whether the physical stock matches.",
    "Values in different currencies are never added together.",
    "ASAVEXA cannot know about stock or movements nobody records.",
]


def _utc(): return datetime.now(timezone.utc)


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v)))
    v = " ".join("".join(c if c >= " " and c != "\x7f" else " " for c in v).split())
    if required and len(v) < lo:
        raise InventoryError(f"{name} is required (at least {lo} characters).")
    if v and len(v) < lo:
        raise InventoryError(f"{name} needs at least {lo} characters.")
    if len(v) > hi:
        raise InventoryError(f"{name} is too long (limit {hi} characters).")
    return v


def _date(v, name) -> date:
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", str(v).strip()): raise ValueError
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise InventoryError(f"{name} must be a real date written YYYY-MM-DD.")


def _enum(v, allowed, name) -> str:
    v = _txt(v, name, 1, 40).upper()
    if v not in allowed:
        raise InventoryError(f"{name} must be one of {', '.join(allowed)}.")
    return v


def _int(v, name, lo, hi) -> int:
    if isinstance(v, bool) or not re.fullmatch(r"[0-9]{1,15}", str(v).strip()):
        raise InventoryError(f"{name} must be a whole number from {lo} to {hi}.")
    n = int(str(v).strip())
    if not lo <= n <= hi:
        raise InventoryError(f"{name} must be a whole number from {lo} to {hi}.")
    return n


def _money(v, name) -> Decimal:
    """An amount written as text or a whole number, at most two decimals, more than zero. Never a float."""
    if isinstance(v, bool) or isinstance(v, float) or v is None:
        raise InventoryError(f"{name} must be an amount such as 12.50.")
    t = str(v).strip()
    if "," in t and not re.fullmatch(r"[0-9]{1,3}(,[0-9]{3})+(\.[0-9]{1,2})?", t):
        raise InventoryError(f"{name} must be an amount such as 12.50 (commas only between groups of three digits).")
    t = t.replace(",", "")
    if not re.fullmatch(r"[0-9]{1,10}(\.[0-9]{1,2})?", t):
        raise InventoryError(f"{name} must be an amount such as 12.50 (at most two decimals).")
    d = Decimal(t)
    if d == 0:
        raise InventoryError(f"{name} must be more than zero.")
    return d.quantize(CENT)


def refnum(r) -> int:
    try: return int(str(r["ref"]).rsplit("-", 1)[1])
    except (KeyError, IndexError, ValueError): return 0


class InventoryService:
    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()

    def _not_future(self, d: date, what: str):
        if d > self.today() + timedelta(days=1):
            raise InventoryError(f"{what} cannot be in the future.")

    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r.get("org") != org:
            raise InventoryNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("iv_setting", f"{org}:settings", for_update=for_update)
        if s and s.get("org") == org:
            return s
        return {"id": "settings", "org": org, **DEFAULTS, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("iv_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other:
            raise InventoryForbiddenError(f"You {what}, so you cannot do this. A different person must.")

    # ------------------------------------------------------------------ policy
    def iv_get_policy(self, org) -> dict:
        s = self._settings(org)
        return {"stale_days": s["stale_days"], "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"An item with stock but no movement for {s['stale_days']} days is flagged as not moving. This is your own setting, not a rule."}

    def iv_set_policy(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        if d.get("stale_days") is not None: s["stale_days"] = _int(d["stale_days"], "The days without movement", 30, 730)
        s.update(updated_by=actor, updated_at=self.now().isoformat())
        self._put("iv_setting", org, s)
        self.log("INVENTORY_POLICY_SET", actor, "settings", org, f"stale {s['stale_days']} days")
        return self.iv_get_policy(org)

    # ------------------------------------------------------------------ views
    def _view(self, it) -> dict:
        v = {x: it[x] for x in it if x != "org"}
        qty, val = it["on_hand"], Decimal(it["value"])
        applied = [m for m in it["moves"] if m["status"] == "APPLIED"]
        last = max((m["applied_on"] for m in applied), default=None)
        v.update(average_cost=str((val / qty).quantize(CENT, rounding=ROUND_HALF_UP)) if qty else "0.00", last_moved_on=last,
                 pending_adjustments=sum(1 for m in it["moves"] if m["status"] == "PENDING"),
                 low_stock=it["status"] == "ACTIVE" and it["reorder_level"] > 0 and qty <= it["reorder_level"], out_of_stock=it["status"] == "ACTIVE" and qty == 0,
                 not_moving=it["status"] == "ACTIVE" and qty > 0 and date.fromisoformat(last or it["created_at"][:10]) + timedelta(days=self._settings(it["org"])["stale_days"]) < self.today())
        return v

    # ------------------------------------------------------------------ items
    def iv_add_item(self, org, d, actor) -> dict:
        sku = _txt(d.get("sku"), "The item code", 2, 40).upper(); name = _txt(d.get("name"), "The item name", 3, 150); unit = _txt(d.get("unit"), "The unit", 1, 20)
        cur = _txt(d.get("currency"), "The currency", 3, 3).upper()
        if not re.fullmatch(r"[A-Z]{3}", cur): raise InventoryError("The currency must be a three-letter code such as NGN.")
        reorder = _int(d.get("reorder_level") if d.get("reorder_level") not in (None, "") else 0, "The reorder level", 0, MAX_QTY); loc = _txt(d.get("location"), "The location", 2, 150)
        if any(o["sku"] == sku and o["status"] == "ACTIVE" for o in self._all("iv_item", org)): raise InventoryStateError(f"An active item with code {sku} already exists.")
        it = {"id": uuid.uuid4().hex, "org": org, "ref": None, "sku": sku, "name": name, "unit": unit, "currency": cur, "reorder_level": reorder, "location": loc, "status": "ACTIVE", "created_by": actor, "created_at": self.now().isoformat(),
              "on_hand": 0, "value": "0.00", "moves": [], "discontinue_note": None, "history": []}
        it["ref"] = self._ref(org, "IT"); self._hist(it, actor, "ADDED")
        self._put("iv_item", org, it); self.log("INVENTORY_ITEM_ADDED", actor, it["id"], org, it["ref"])
        return self._view(it)

    def iv_discontinue_item(self, org, iid, reason, actor) -> dict:
        it = self._get("iv_item", org, iid, "Item", for_update=True)
        if it["status"] != "ACTIVE": raise InventoryStateError("Only an active item can be discontinued.")
        if it["on_hand"] != 0: raise InventoryStateError("An item can only be discontinued when no stock is left.")
        if any(m["status"] == "PENDING" for m in it["moves"]): raise InventoryStateError("Decide the adjustments waiting for this item first.")
        reason = _txt(reason, "A reason", 10, 500); it.update(status="DISCONTINUED", discontinue_note=reason); self._hist(it, actor, "DISCONTINUED", reason)
        self._put("iv_item", org, it); self.log("INVENTORY_ITEM_DISCONTINUED", actor, iid, org, it["ref"])
        return self._view(it)

    def iv_list_items(self, org, status=None) -> List[dict]:
        return [self._view(i) for i in sorted(self._all("iv_item", org), key=refnum) if not status or i["status"] == status]

    def iv_get_item(self, org, iid) -> dict: return self._view(self._get("iv_item", org, iid, "Item"))

    # ------------------------------------------------------------------ movements
    def _apply(self, it, m, actor):
        """Apply a movement to quantity and value. Callers have already checked the rules."""
        qty, val = it["on_hand"], Decimal(it["value"])
        if m["kind"] in ("RECEIPT", "ADJUST_UP"):
            add = (Decimal(m["unit_cost"]) * m["qty"]).quantize(CENT, rounding=ROUND_HALF_UP); it["on_hand"] = qty + m["qty"]; it["value"] = str(val + add); m["value"] = str(add)
        else:
            out = val if m["qty"] == qty else (val * m["qty"] / qty).quantize(CENT, rounding=ROUND_HALF_UP)
            it["on_hand"] = qty - m["qty"]; it["value"] = str(val - out); m["value"] = str(out); m["unit_cost"] = str((out / m["qty"]).quantize(CENT, rounding=ROUND_HALF_UP))
        m.update(status="APPLIED", applied_on=self.today().isoformat(), qty_after=it["on_hand"], value_after=it["value"])

    def _new_move(self, it, kind, qty, **kw):
        return {"no": len(it["moves"]) + 1, "kind": kind, "qty": qty, "unit_cost": None, "value": None, "reference": None, "moved_on": None, "applied_on": None, "status": "PENDING", "by": None, "decided_by": None, "decision_note": None,
                "reason_kind": None, "reason": None, "qty_after": None, "value_after": None, **kw}

    def _active(self, org, iid) -> dict:
        it = self._get("iv_item", org, iid, "Item", for_update=True)
        if it["status"] != "ACTIVE": raise InventoryStateError("This item is discontinued.")
        return it

    def iv_receive(self, org, iid, d, actor) -> dict:
        it = self._active(org, iid); qty = _int(d.get("qty"), "The quantity", 1, MAX_QTY); cost = _money(d.get("unit_cost"), "The unit cost")
        on = _date(d.get("moved_on"), "The receipt date"); self._not_future(on, "The receipt date"); ref = _txt(d.get("reference"), "The delivery or document reference", 2, 100)
        m = self._new_move(it, "RECEIPT", qty, unit_cost=str(cost), reference=ref, moved_on=on.isoformat(), by=actor); self._apply(it, m, actor); it["moves"].append(m); self._hist(it, actor, "RECEIVED")
        self._put("iv_item", org, it); self.log("INVENTORY_RECEIPT_RECORDED", actor, iid, org, f"{it['ref']} +{qty}")
        return self._view(it)

    def iv_issue(self, org, iid, d, actor) -> dict:
        it = self._active(org, iid); qty = _int(d.get("qty"), "The quantity", 1, MAX_QTY)
        on = _date(d.get("moved_on"), "The issue date"); self._not_future(on, "The issue date"); ref = _txt(d.get("reference"), "The issue note or reference", 2, 100)
        if qty > it["on_hand"]: raise InventoryStateError(f"Only {it['on_hand']} {it['unit']} on hand. Stock cannot go below zero.")
        m = self._new_move(it, "ISSUE", qty, reference=ref, moved_on=on.isoformat(), by=actor); self._apply(it, m, actor); it["moves"].append(m); self._hist(it, actor, "ISSUED")
        self._put("iv_item", org, it); self.log("INVENTORY_ISSUE_RECORDED", actor, iid, org, f"{it['ref']} -{qty}")
        return self._view(it)

    # ------------------------------------------------------------------ adjustments (two-person)
    def iv_propose_adjustment(self, org, iid, d, actor) -> dict:
        it = self._active(org, iid); direction = _enum(d.get("direction"), DIRECTIONS, "The direction"); qty = _int(d.get("qty"), "The quantity", 1, MAX_QTY)
        rk = _enum(d.get("reason_kind"), REASON_KINDS, "The reason"); reason = _txt(d.get("reason"), "The explanation", 10, 1000); cost = None
        if direction == "DECREASE":
            if qty > it["on_hand"]: raise InventoryStateError(f"Only {it['on_hand']} {it['unit']} on hand. Stock cannot go below zero.")
        elif it["on_hand"] == 0 or d.get("unit_cost") not in (None, ""):
            cost = str(_money(d.get("unit_cost"), "The unit cost (needed when no stock is on hand)"))
        if sum(1 for m in it["moves"] if m["status"] == "PENDING") >= 5: raise InventoryStateError("Five adjustments are already waiting. Decide them first.")
        m = self._new_move(it, "ADJUST_UP" if direction == "INCREASE" else "ADJUST_DOWN", qty, unit_cost=cost, reason_kind=rk, reason=reason, moved_on=self.today().isoformat(), by=actor)
        it["moves"].append(m); self._hist(it, actor, "ADJUSTMENT_PROPOSED")
        self._put("iv_item", org, it); self.log("INVENTORY_ADJUSTMENT_PROPOSED", actor, iid, org, f"{it['ref']} #{m['no']}")
        return self._view(it)

    def _pending(self, it, no) -> dict:
        m = next((m for m in it["moves"] if m["no"] == _int(no, "The movement number", 1, 1000000)), None)
        if m is None: raise InventoryNotFoundError("Adjustment not found.")
        if m["status"] != "PENDING" or not m["kind"].startswith("ADJUST"): raise InventoryStateError("Only an adjustment that is waiting can be decided.")
        return m

    def iv_approve_adjustment(self, org, iid, no, d, actor) -> dict:
        it = self._get("iv_item", org, iid, "Item", for_update=True); m = self._pending(it, no)
        self._two(actor, m["by"], "proposed this adjustment")
        note = _txt(d.get("note"), "An approval note", 10, 1000, required=False)
        if it["status"] != "ACTIVE": raise InventoryStateError("This item is discontinued.")
        if m["kind"] == "ADJUST_DOWN" and m["qty"] > it["on_hand"]: raise InventoryStateError(f"Only {it['on_hand']} {it['unit']} on hand now. Reject this adjustment and propose a new one.")
        if m["kind"] == "ADJUST_UP" and m["unit_cost"] is None:
            if it["on_hand"] == 0: raise InventoryStateError("No stock is on hand and no unit cost was given. Reject this adjustment and propose a new one with a unit cost.")
            m["unit_cost"] = str((Decimal(it["value"]) / it["on_hand"]).quantize(CENT, rounding=ROUND_HALF_UP))
            if Decimal(m["unit_cost"]) == 0: raise InventoryStateError("The average cost is zero. Reject this adjustment and propose a new one with a unit cost.")
        m.update(decided_by=actor, decision_note=note or None); self._apply(it, m, actor); self._hist(it, actor, "ADJUSTMENT_APPROVED", note)
        self._put("iv_item", org, it); self.log("INVENTORY_ADJUSTMENT_APPROVED", actor, iid, org, f"{it['ref']} #{m['no']}")
        return self._view(it)

    def iv_reject_adjustment(self, org, iid, no, reason, actor) -> dict:
        it = self._get("iv_item", org, iid, "Item", for_update=True); m = self._pending(it, no)
        self._two(actor, m["by"], "proposed this adjustment")
        reason = _txt(reason, "A reason", 10, 500); m.update(status="REJECTED", decided_by=actor, decision_note=reason); self._hist(it, actor, "ADJUSTMENT_REJECTED", reason)
        self._put("iv_item", org, it); self.log("INVENTORY_ADJUSTMENT_REJECTED", actor, iid, org, f"{it['ref']} #{m['no']}")
        return self._view(it)

    # ------------------------------------------------------------------ overview
    def iv_overview(self, org) -> dict:
        items = self.iv_list_items(org); act = [i for i in items if i["status"] == "ACTIVE"]; att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("OUT_OF_STOCK", sum(1 for i in act if i["out_of_stock"] and i["reorder_level"] > 0), "item(s) with a reorder level are out of stock.")
        add("LOW_STOCK", sum(1 for i in act if i["low_stock"] and not i["out_of_stock"]), "item(s) are at or below their reorder level.")
        add("ADJUSTMENTS_TO_APPROVE", sum(i["pending_adjustments"] for i in items), "adjustment(s) are waiting for a different person to decide them.")
        add("ITEMS_NOT_MOVING", sum(1 for i in act if i["not_moving"]), "item(s) with stock have not moved within your window.")
        totals = {}
        for i in act:
            t = totals.setdefault(i["currency"], {"currency": i["currency"], "items": 0, "units": 0, "value": Decimal("0")}); t["items"] += 1; t["units"] += i["on_hand"]; t["value"] += Decimal(i["value"])
        totals = [{**t, "value": str(t["value"])} for t in sorted(totals.values(), key=lambda x: x["currency"])]
        return {"counts": {"active": len(act), "discontinued": sum(1 for i in items if i["status"] == "DISCONTINUED"), "low_stock": sum(1 for i in act if i["low_stock"]), "out_of_stock": sum(1 for i in act if i["out_of_stock"])},
                "totals": totals, "attention": att, "policy": self.iv_get_policy(org), "limitations": LIMITATIONS}

    def iv_options(self, org) -> dict:
        return {"directions": DIRECTIONS, "reason_kinds": REASON_KINDS, "limitations": LIMITATIONS}
