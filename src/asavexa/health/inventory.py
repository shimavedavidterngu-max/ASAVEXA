"""Stock items, lots, receipts, issues, transfers, approved adjustments and write-offs, physical counts, valuation and alerts.

Costing: moving weighted-average cost per item. A receipt re-averages; an issue, transfer or write-off leaves the average unchanged and is valued at it.
Issues use the lot that expires first (FEFO). Stock never goes below zero and expired stock cannot be issued; it must be written off with a second person's approval.
Every change is an immutable movement, and the quantity on hand is always the sum of movements. This is financial stock control, not prescribing or dispensing."""
from datetime import timedelta
from decimal import Decimal

from .base import P_PREPARE, ZERO, day, enum, norm, q2, q3, q4, qty, s2, s3, txt
from .errors import HealthError, HealthNotFoundError, HealthStateError
from .procure import ProcureMixin

ITEM_CATEGORIES = ["MEDICAL_SUPPLIES", "PHARMACEUTICAL_STOCK", "LABORATORY_CONSUMABLES", "CLEANING_AND_LINEN", "OFFICE_AND_OTHER"]
ADJ_KINDS = ["COUNT_VARIANCE", "DAMAGED", "EXPIRED", "CORRECTION"]


class InventoryMixin(ProcureMixin):
    def create_item(self, org, fid, d, actor) -> dict:
        self._fac(org, fid, actor, active=True); sku = txt(d.get("sku"), "SKU", 2, 40).upper()
        for i in self._of("hc_item", org, fid):
            if norm(i["sku"]) == norm(sku): raise HealthError(f"SKU {sku} already exists ({i['name']}).")
        sup = None
        if d.get("supplier_id"):
            sup = self._rec("hc_supplier", org, d["supplier_id"], "Supplier", actor)
            if sup["facility_id"] != fid: raise HealthError("That supplier is not registered at this facility.")
        r = self._new(org, fid, sku=sku, name=txt(d.get("name"), "Item name", 2, 200), category=enum(d.get("category"), ITEM_CATEGORIES, "Category"), uom=txt(d.get("uom"), "Unit of measure", 1, 30), reorder_level=s3(qty(d.get("reorder_level", 0), "Reorder level", positive=False)),
                      tracks_expiry=bool(d.get("tracks_expiry")), supplier_id=sup["id"] if sup else None, avg_cost="0.0000", status="ACTIVE", created_by=actor)
        self._put("hc_item", org, r); self.log("HC_ITEM_ADDED", actor, r["id"], org, sku); return r

    def update_item(self, org, iid, d, actor) -> dict:
        r = self._rec("hc_item", org, iid, "Stock item", actor, True); self._writable(org, r, actor)
        r.update(name=txt(d.get("name", r["name"]), "Item name", 2, 200), uom=txt(d.get("uom", r["uom"]), "Unit of measure", 1, 30), reorder_level=s3(qty(d.get("reorder_level", r["reorder_level"]), "Reorder level", positive=False)))
        self._put("hc_item", org, r); self.log("HC_ITEM_UPDATED", actor, iid, org, r["sku"]); return r

    # ---- lots and movements
    def _moves(self, org, item_id) -> list:
        return sorted((m for m in self._all("hc_move", org) if m["item_id"] == item_id), key=lambda m: (m["at"], m["seq"]))

    def _lots(self, org, item_id) -> dict:
        lots = {}
        for m in self._moves(org, item_id):
            k = (m["batch"], m["expiry"], m["location"]); lots[k] = lots.get(k, Decimal("0.000")) + Decimal(m["qty"])
        return lots

    def _lot_input(self, item, ln) -> tuple:
        batch = txt(ln.get("batch"), "Batch or lot number", 0, 60, required=False) or None
        loc = txt(ln.get("location"), "Storage location", 0, 60, required=False) or "MAIN"
        expiry = None
        if item["tracks_expiry"]:
            if not batch: raise HealthError(f"{item['name']} tracks expiry, so a batch or lot number is required.")
            e = day(ln.get("expiry"), "Expiry date")
            if e < self.today(): raise HealthError(f"{item['name']} batch {batch} has already expired ({e.isoformat()}) and cannot be received into stock.")
            expiry = e.isoformat()
        return batch, expiry, loc

    def _write_move(self, org, item, mtype, q, batch, expiry, loc, cost, ref, actor, reason):
        s = self._settings(org, for_update=True); s["counters"]["__move"] = s["counters"].get("__move", 0) + 1; self._put("hc_setting", org, s)
        m = self._new(org, item["facility_id"], item_id=item["id"], sku=item["sku"], type=mtype, qty=s3(q), batch=batch, expiry=expiry, location=loc, unit_cost=str(q4(cost)), value=s2(q2(q * cost)), ref=ref, reason=reason, by=actor, at=self.now().isoformat(), seq=s["counters"]["__move"])
        self._put("hc_move", org, m); return m

    def _stock_in(self, org, item, q, unit_cost, batch, expiry, loc, mtype, ref, actor, reason):
        on = sum(self._lots(org, item["id"]).values(), Decimal("0.000")); avg = Decimal(item["avg_cost"])
        new_avg = q4((on * avg + q * unit_cost) / (on + q)) if on + q > 0 else avg
        item["avg_cost"] = str(new_avg); self._put("hc_item", org, item)
        return self._write_move(org, item, mtype, q, batch, expiry, loc, new_avg if mtype != "RECEIPT" else unit_cost, ref, actor, reason)

    def _plan_out(self, org, item, q, loc) -> list:
        """Which lots to take from, earliest expiry first; expired lots are never used."""
        t = self.today().isoformat(); cands = []
        for (b, e, l), have in self._lots(org, item["id"]).items():
            if l == loc and have > 0 and (e is None or e >= t): cands.append((e is None, e or "", b or "", b, e, have))
        cands.sort(); avail = sum((c[5] for c in cands), Decimal("0.000"))
        if q > avail: raise HealthError(f"Only {s3(avail)} {item['uom']} of {item['name']} is available (not expired) at {loc}; {s3(q)} was requested. Stock cannot go negative.")
        plan, need = [], q
        for *_, b, e, have in cands:
            if need <= 0: break
            take = min(have, need); plan.append((b, e, take)); need -= take
        return plan

    def issue_stock(self, org, iid, d, actor) -> list:
        item = self._rec("hc_item", org, iid, "Stock item", actor, True); self._writable(org, item, actor)
        q = qty(d.get("qty"), "Quantity"); loc = txt(d.get("location"), "Storage location", 0, 60, required=False) or "MAIN"; why = txt(d.get("purpose"), "Purpose (a department or activity, never a patient)", 3, 200)
        dept = self._dept(org, item["facility_id"], d.get("dept_id")) if d.get("dept_id") else None
        plan = self._plan_out(org, item, q, loc); ref = self._ref(org, "ISS", item["facility_id"]); cost = Decimal(item["avg_cost"])
        moves = [self._write_move(org, item, "ISSUE", -t, b, e, loc, cost, ref, actor, why + (f" ({dept['name']})" if dept else "")) for b, e, t in plan]
        self.log("HC_STOCK_ISSUED", actor, iid, org, f"{ref} {item['sku']} x{q}")
        return moves

    def transfer_stock(self, org, iid, d, actor) -> list:
        item = self._rec("hc_item", org, iid, "Stock item", actor, True); self._writable(org, item, actor)
        q = qty(d.get("qty"), "Quantity"); a = txt(d.get("from_location"), "From location", 1, 60); b2 = txt(d.get("to_location"), "To location", 1, 60)
        if a == b2: raise HealthError("The two locations must be different.")
        plan = self._plan_out(org, item, q, a); ref = self._ref(org, "TRF", item["facility_id"]); cost = Decimal(item["avg_cost"]); out = []
        for b, e, t in plan:
            out.append(self._write_move(org, item, "TRANSFER_OUT", -t, b, e, a, cost, ref, actor, f"to {b2}")); out.append(self._write_move(org, item, "TRANSFER_IN", t, b, e, b2, cost, ref, actor, f"from {a}"))
        self.log("HC_STOCK_TRANSFERRED", actor, iid, org, f"{ref} {item['sku']} x{q} {a} to {b2}")
        return out

    # ---- adjustments, write-offs and counts
    def _lot_qty(self, org, item_id, batch, expiry, loc):
        k = (batch or None, expiry or None, loc); lots = self._lots(org, item_id)
        if k not in lots: raise HealthError("No stock history exists for that batch, expiry date and location.")
        return lots[k]

    def request_adjustment(self, org, iid, d, actor) -> dict:
        item = self._rec("hc_item", org, iid, "Stock item", actor, True); self._writable(org, item, actor)
        delta = qty(d.get("qty_delta"), "Quantity change", positive=False)
        if delta == 0: raise HealthError("The quantity change cannot be zero.")
        kind = enum(d.get("kind"), ADJ_KINDS, "Kind"); loc = txt(d.get("location"), "Storage location", 0, 60, required=False) or "MAIN"
        batch = txt(d.get("batch"), "Batch", 0, 60, required=False) or None; expiry = txt(d.get("expiry"), "Expiry", 0, 10, required=False) or None
        if kind in ("DAMAGED", "EXPIRED") and delta > 0: raise HealthError("Damaged or expired stock can only be written off (a negative change).")
        have = self._lot_qty(org, iid, batch, expiry, loc)
        pending = sum((Decimal(a["qty_delta"]) for a in self._of("hc_adj", org, item["facility_id"]) if a["item_id"] == iid and a["status"] == "PENDING" and (a["batch"], a["expiry"], a["location"]) == (batch, expiry, loc)), Decimal("0.000"))
        if have + pending + delta < 0: raise HealthError(f"That would take the lot below zero (it holds {s3(have)}; {s3(pending)} change already waiting).")
        a = self._new(org, item["facility_id"], ref=self._ref(org, "ADJ", item["facility_id"]), item_id=iid, sku=item["sku"], item=item["name"], batch=batch, expiry=expiry, location=loc, qty_delta=s3(delta), kind=kind,
                      reason=txt(d.get("reason"), "Reason", 10, 500), evidence=self._evidence(org, d.get("evidence_ids")), status="PENDING", requested_by=actor, requested_at=self.now().isoformat(), history=[])
        self._hist(a, actor, "REQUESTED"); self._put("hc_adj", org, a); self.log("HC_ADJ_REQUESTED", actor, a["id"], org, f"{a['ref']} {a['sku']} {a['qty_delta']}"); return a

    def decide_adjustment(self, org, aid, ok, note, actor) -> dict:
        a = self._rec("hc_adj", org, aid, "Adjustment", actor, True); self._writable(org, a, actor)
        if a["status"] != "PENDING": raise HealthStateError("That adjustment has already been decided.")
        self._two(actor, a["requested_by"], "asked for this adjustment")
        n = txt(note, "A note saying why", 0 if ok else 3, 500, required=not ok)
        if ok:
            item = self._raw("hc_item", org, a["item_id"], "Stock item", for_update=True); delta = Decimal(a["qty_delta"])
            if self._lot_qty(org, a["item_id"], a["batch"], a["expiry"], a["location"]) + delta < 0: raise HealthError("The lot no longer holds enough stock for this change.")
            cost = Decimal(item["avg_cost"]); m = self._write_move(org, item, "ADJUSTMENT" if a["kind"] != "EXPIRED" and a["kind"] != "DAMAGED" else "WRITE_OFF", delta, a["batch"], a["expiry"], a["location"], cost, a["ref"], actor, f"{a['kind']}: {a['reason']}")
            a.update(status="APPROVED", movement_id=m["id"], value_effect=m["value"], accounting_note="This changes stock value. Post the matching journal in the ledger; ASAVEXA does not post it for you." if delta < 0 else "")
        else:
            a["status"] = "REJECTED"
        a.update(decided_by=actor, decision_note=n); self._hist(a, actor, a["status"], n); self._put("hc_adj", org, a); self.log("HC_ADJ_" + a["status"], actor, aid, org, a["ref"]); return a

    def record_count(self, org, iid, d, actor) -> dict:
        item = self._rec("hc_item", org, iid, "Stock item", actor, True); self._writable(org, item, actor)
        counted = qty(d.get("counted_qty"), "Counted quantity", positive=False)
        if counted < 0: raise HealthError("The counted quantity cannot be negative.")
        loc = txt(d.get("location"), "Storage location", 0, 60, required=False) or "MAIN"; batch = txt(d.get("batch"), "Batch", 0, 60, required=False) or None; expiry = txt(d.get("expiry"), "Expiry", 0, 10, required=False) or None
        system = self._lot_qty(org, iid, batch, expiry, loc); var = counted - system
        out = {"item": item["name"], "system_qty": s3(system), "counted_qty": s3(counted), "variance": s3(var), "adjustment": None}
        if var != 0: out["adjustment"] = self.request_adjustment(org, iid, {"batch": batch, "expiry": expiry, "location": loc, "qty_delta": str(var), "kind": "COUNT_VARIANCE", "reason": f"Physical count found {s3(counted)}; the system showed {s3(system)}.", "evidence_ids": d.get("evidence_ids")}, actor)
        self.log("HC_COUNT", actor, iid, org, f"{item['sku']} variance {s3(var)}"); return out

    def list_adjustments(self, org, fid, actor) -> list:
        self._fac(org, fid, actor); return sorted(self._of("hc_adj", org, fid), key=lambda a: a["ref"])

    # ---- reading
    def list_items(self, org, fid, actor) -> list:
        self._fac(org, fid, actor); return sorted(self._of("hc_item", org, fid), key=lambda i: i["sku"])

    def movements(self, org, iid, actor) -> list:
        self._rec("hc_item", org, iid, "Stock item", actor); return self._moves(org, iid)

    def stock_levels(self, org, fid, actor) -> dict:
        f = self._fac(org, fid, actor); t = self.today(); soon = (t + timedelta(days=f["expiry_alert_days"])).isoformat(); rows, total = [], ZERO
        low, expiring, expired = [], [], []
        for it in sorted(self._of("hc_item", org, fid), key=lambda i: i["sku"]):
            lots = {k: v for k, v in self._lots(org, it["id"]).items() if v > 0}; on = sum(lots.values(), Decimal("0.000")); val = q2(on * Decimal(it["avg_cost"])); total += val
            row = {"item_id": it["id"], "sku": it["sku"], "name": it["name"], "uom": it["uom"], "on_hand": s3(on), "avg_cost": it["avg_cost"], "value": s2(val), "reorder_level": it["reorder_level"], "low": on <= Decimal(it["reorder_level"]) and Decimal(it["reorder_level"]) > 0,
                   "lots": [{"batch": b, "expiry": e, "location": l, "qty": s3(v)} for (b, e, l), v in sorted(lots.items(), key=lambda kv: (kv[0][1] or "9999", kv[0][0] or "", kv[0][2]))]}
            rows.append(row)
            if row["low"]: low.append({"sku": it["sku"], "name": it["name"], "on_hand": row["on_hand"], "reorder_level": it["reorder_level"]})
            for l in row["lots"]:
                if l["expiry"] and l["expiry"] < t.isoformat(): expired.append({"sku": it["sku"], "name": it["name"], **l})
                elif l["expiry"] and l["expiry"] <= soon: expiring.append({"sku": it["sku"], "name": it["name"], **l})
        return {"items": rows, "total_value": s2(total), "alerts": {"low_stock": low, "expiring_soon": expiring, "expired": expired, "expiry_window_days": f["expiry_alert_days"]},
                "costing": "Moving weighted-average cost. Receipts re-average; issues and write-offs are valued at the current average. Value = quantity on hand x average cost."}
