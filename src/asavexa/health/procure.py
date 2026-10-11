"""Suppliers, requisitions, quotes, purchase orders, goods receipts, supplier invoices with three-way matching, credit notes and payment."""
from datetime import date
from decimal import Decimal

from .base import CATEGORIES, P_APPROVE, P_PREPARE, ZERO, day, enum, money, norm, q2, qty, s2, s3, txt
from .errors import HealthError, HealthNotFoundError, HealthStateError
from .facility import LIVE_PO, SPENT_INVOICE, FacilityMixin

AGE_BUCKETS = [("0-30", 0, 30), ("31-60", 31, 60), ("61-90", 61, 90), ("over 90", 91, 10 ** 6)]


class ProcureMixin(FacilityMixin):
    # ------------------------------------------------------------------ suppliers
    def create_supplier(self, org, fid, d, actor) -> dict:
        self._fac(org, fid, actor, active=True); name = txt(d.get("name"), "Supplier name", 2, 200)
        for s in self._of("hc_supplier", org, fid):
            if s["name"].strip().lower() == name.lower(): raise HealthError(f"Supplier {s['name']} already exists ({s['ref']}).")
        r = self._new(org, fid, ref=self._ref(org, "S", fid), name=name, contact=txt(d.get("contact"), "Contact (business details only)", 0, 300, required=False), status="AUTHORISED", history=[])
        self._hist(r, actor, "AUTHORISED"); self._put("hc_supplier", org, r); self.log("HC_SUPPLIER_ADDED", actor, r["id"], org, r["ref"]); return r

    def set_supplier_status(self, org, sid, authorised, note, actor) -> dict:
        r = self._rec("hc_supplier", org, sid, "Supplier", actor, True); self._writable(org, r, actor)
        r["status"] = "AUTHORISED" if authorised else "SUSPENDED"; self._hist(r, actor, r["status"], txt(note, "Reason", 3, 500)); self._put("hc_supplier", org, r); self.log("HC_SUPPLIER_" + r["status"], actor, sid, org, r["ref"]); return r

    def list_suppliers(self, org, fid, actor) -> list:
        self._fac(org, fid, actor); return sorted(self._of("hc_supplier", org, fid), key=lambda s: s["ref"])

    # ------------------------------------------------------------------ requisitions
    def _req_lines(self, org, fid, lines) -> tuple:
        if not isinstance(lines, list) or not lines: raise HealthError("Add at least one item to the requisition.")
        out, total = [], ZERO
        for i, ln in enumerate(lines, 1):
            item = None
            if ln.get("item_id"):
                item = self._raw("hc_item", org, ln["item_id"], "Stock item")
                if item["facility_id"] != fid: raise HealthError(f"Line {i}: stock item not found in this facility.")
            q, p = qty(ln.get("qty"), f"Line {i} quantity"), money(ln.get("unit_price"), f"Line {i} unit price")
            out.append({"line_no": i, "description": txt(ln.get("description") or (item or {}).get("name"), f"Line {i} description", 2, 200), "item_id": item["id"] if item else None, "qty": s3(q), "unit_price": s2(p), "received_qty": "0.000"})
            total += q2(q * p)
        return out, total

    def create_requisition(self, org, fid, d, actor) -> dict:
        self._fac(org, fid, actor, active=True); dept = self._dept(org, fid, d.get("dept_id")); lines, total = self._req_lines(org, fid, d.get("lines"))
        r = self._new(org, fid, ref=self._ref(org, "REQ", fid), dept_id=dept["id"], dept=dept["name"], category=enum(d.get("category"), CATEGORIES, "Category"), lines=lines, total=s2(total), justification=txt(d.get("justification"), "Justification", 5, 1000),
                      status="DRAFT", quotes=[], evidence=self._evidence(org, d.get("evidence_ids")), requested_by=actor, created_at=self.now().isoformat(), history=[])
        self._hist(r, actor, "CREATED"); self._put("hc_req", org, r); self.log("HC_REQ_CREATED", actor, r["id"], org, f"{r['ref']} {r['total']}"); return r

    def update_requisition(self, org, rid, d, actor) -> dict:
        r = self._rec("hc_req", org, rid, "Requisition", actor, True); self._writable(org, r, actor)
        if r["status"] not in ("DRAFT", "REJECTED"): raise HealthStateError("Only a draft or sent-back requisition can be edited.")
        dept = self._dept(org, r["facility_id"], d.get("dept_id")); lines, total = self._req_lines(org, r["facility_id"], d.get("lines"))
        r.update(dept_id=dept["id"], dept=dept["name"], category=enum(d.get("category"), CATEGORIES, "Category"), lines=lines, total=s2(total), justification=txt(d.get("justification"), "Justification", 5, 1000), status="DRAFT",
                 evidence=self._evidence(org, d.get("evidence_ids")))
        self._hist(r, actor, "EDITED"); self._put("hc_req", org, r); return r

    def submit_requisition(self, org, rid, actor) -> dict:
        r = self._rec("hc_req", org, rid, "Requisition", actor, True); self._writable(org, r, actor)
        if r["status"] not in ("DRAFT", "REJECTED"): raise HealthStateError("Only a draft or sent-back requisition can be submitted.")
        r["status"] = "SUBMITTED"; self._hist(r, actor, "SUBMITTED"); self._put("hc_req", org, r); self.log("HC_REQ_SUBMITTED", actor, rid, org, r["ref"]); return r

    def decide_requisition(self, org, rid, ok, note, actor) -> dict:
        r = self._rec("hc_req", org, rid, "Requisition", actor, True); self._writable(org, r, actor)
        if r["status"] != "SUBMITTED": raise HealthStateError("Only a submitted requisition can be decided.")
        self._two(actor, r["requested_by"], "raised this requisition")
        r["status"] = "APPROVED" if ok else "REJECTED"; r["decided_by"] = actor; n = txt(note, "A note saying why", 0 if ok else 3, 500, required=not ok)
        self._hist(r, actor, r["status"], n); self._put("hc_req", org, r); self.log("HC_REQ_" + r["status"], actor, rid, org, r["ref"]); return r

    def add_quote(self, org, rid, d, actor) -> dict:
        r = self._rec("hc_req", org, rid, "Requisition", actor, True); self._writable(org, r, actor)
        if r["status"] not in ("DRAFT", "SUBMITTED", "APPROVED"): raise HealthStateError("Quotes can only be added before an order is placed.")
        sup = self._rec("hc_supplier", org, d.get("supplier_id"), "Supplier", actor)
        if sup["facility_id"] != r["facility_id"]: raise HealthError("That supplier is not registered at this facility.")
        if any(q["supplier_id"] == sup["id"] for q in r["quotes"]): raise HealthError(f"{sup['name']} already has a quote on this requisition.")
        q = {"id": f"Q{len(r['quotes']) + 1}", "supplier_id": sup["id"], "supplier": sup["name"], "amount": s2(money(d.get("amount"), "Quoted amount")), "note": txt(d.get("note"), "Note", 0, 300, required=False), "evidence": self._evidence(org, d.get("evidence_ids")), "by": actor}
        r["quotes"].append(q); self._hist(r, actor, "QUOTE_ADDED", f"{sup['name']} {q['amount']}"); self._put("hc_req", org, r); return q

    def list_requisitions(self, org, fid, actor) -> list:
        self._fac(org, fid, actor)
        out = []
        for r in sorted(self._of("hc_req", org, fid), key=lambda r: r["ref"]):
            v = dict(r); qs = sorted(r["quotes"], key=lambda q: Decimal(q["amount"]))
            v["quote_comparison"] = [dict(q, lowest=(i == 0 and len(qs) > 1)) for i, q in enumerate(qs)]; out.append(v)
        return out

    # ------------------------------------------------------------------ purchase orders
    def create_po(self, org, rid, supplier_id, actor) -> dict:
        req = self._rec("hc_req", org, rid, "Requisition", actor, True); f = self._fac(org, req["facility_id"], actor, active=True)
        if req["status"] != "APPROVED": raise HealthStateError("A purchase order can only be raised from an approved requisition.")
        sup = self._rec("hc_supplier", org, supplier_id, "Supplier", actor)
        if sup["facility_id"] != req["facility_id"] or sup["status"] != "AUTHORISED": raise HealthError("Choose an authorised supplier registered at this facility.")
        if len(req["quotes"]) < f["min_quotes"]: raise HealthError(f"This facility requires {f['min_quotes']} quote(s); {len(req['quotes'])} recorded.")
        p = self._new(org, req["facility_id"], ref=self._ref(org, "PO", req["facility_id"]), req_id=rid, req_ref=req["ref"], supplier_id=sup["id"], supplier=sup["name"], dept_id=req["dept_id"], category=req["category"],
                      lines=[dict(x) for x in req["lines"]], total=req["total"], date=self.today().isoformat(), status="PENDING_APPROVAL", created_by=actor, exception=None, evidence=list(req["evidence"]), history=[])
        req["status"] = "ORDERED"; self._hist(req, actor, "ORDERED", p["ref"]); self._put("hc_req", org, req)
        self._hist(p, actor, "CREATED"); self._put("hc_po", org, p); self.log("HC_PO_CREATED", actor, p["id"], org, f"{p['ref']} {p['total']}"); return p

    def approve_po(self, org, pid, exception_note, actor) -> dict:
        p = self._rec("hc_po", org, pid, "Purchase order", actor, True); f = self._fac(org, p["facility_id"], actor, active=True)
        if p["status"] != "PENDING_APPROVAL": raise HealthStateError("Only a purchase order waiting for approval can be approved.")
        self._two(actor, p["created_by"], "raised this purchase order")
        av, b = self._available(org, p["facility_id"], p["dept_id"], p["category"], day(p["date"], "date"))
        total = Decimal(p["total"]); over = av is None or total > av
        if over and f["block_overspend"]:
            ex = (exception_note or "").strip()
            if len(ex) < 20:
                raise HealthError("There is no approved budget line with enough available for this order (" + ("no approved budget covers this department and category" if av is None else f"{s2(av)} available, {p['total']} needed") + "). To approve it anyway, record the exception reason (at least 20 characters).")
            p["exception"] = {"note": ex, "available": None if av is None else s2(av), "by": actor, "at": self.now().isoformat()}
        p.update(status="OPEN", approved_by=actor); self._hist(p, actor, "APPROVED", "budget exception recorded" if p["exception"] else ""); self._put("hc_po", org, p); self.log("HC_PO_APPROVED", actor, pid, org, p["ref"]); return p

    def cancel_po(self, org, pid, note, actor) -> dict:
        p = self._rec("hc_po", org, pid, "Purchase order", actor, True); self._writable(org, p, actor)
        if p["status"] not in ("PENDING_APPROVAL", "OPEN"): raise HealthStateError("Only an order with nothing received can be cancelled.")
        if any(Decimal(x["received_qty"]) > 0 for x in p["lines"]): raise HealthStateError("Goods have been received on this order, so it cannot be cancelled.")
        if any(i["po_id"] == pid and i["status"] != "CANCELLED" for i in self._of("hc_inv", org, p["facility_id"])): raise HealthStateError("An invoice is recorded against this order.")
        p["status"] = "CANCELLED"; self._hist(p, actor, "CANCELLED", txt(note, "Reason", 3, 500)); self._put("hc_po", org, p); self.log("HC_PO_CANCELLED", actor, pid, org, p["ref"]); return p

    def list_pos(self, org, fid, actor) -> list:
        self._fac(org, fid, actor); return sorted(self._of("hc_po", org, fid), key=lambda p: p["ref"])

    # ------------------------------------------------------------------ goods receipt (and stock)
    def receive_goods(self, org, pid, d, actor) -> dict:
        p = self._rec("hc_po", org, pid, "Purchase order", actor, True); f = self._fac(org, p["facility_id"], actor, active=True)
        if p["status"] not in ("OPEN", "PARTIAL"): raise HealthStateError("Goods can only be received on an approved order that is not yet fully received.")
        lines = d.get("lines")
        if not isinstance(lines, list) or not lines: raise HealthError("Enter at least one line received.")
        by_no = {x["line_no"]: x for x in p["lines"]}; plan, seen = [], set()
        for ln in lines:
            try: no = int(ln.get("line_no"))
            except (TypeError, ValueError): raise HealthError("Each received line needs the order line number.")
            if no not in by_no: raise HealthError(f"The order has no line {no}.")
            if no in seen: raise HealthError(f"Line {no} appears twice.")
            seen.add(no); pl = by_no[no]; q = qty(ln.get("qty"), f"Line {no} quantity received")
            remaining = Decimal(pl["qty"]) - Decimal(pl["received_qty"])
            if q > remaining: raise HealthError(f"Line {no}: {s3(q)} received is more than the {s3(remaining)} still to come.")
            plan.append((pl, q, ln))
        dn = txt(d.get("delivery_note"), "Delivery note number", 2, 80)
        for g in self._of("hc_grn", org, p["facility_id"]):
            if g["po_id"] == pid and norm(g["delivery_note"]) == norm(dn): raise HealthError(f"Delivery note {dn} was already recorded on this order ({g['ref']}).")
        # validate every stock line before changing anything
        stock = []
        for pl, q, ln in plan:
            if pl["item_id"]:
                item = self._raw("hc_item", org, pl["item_id"], "Stock item", for_update=True)
                batch, expiry, loc = self._lot_input(item, ln)
                stock.append((item, q, pl, batch, expiry, loc))
        ev = self._evidence(org, d.get("evidence_ids"))
        g = self._new(org, p["facility_id"], ref=self._ref(org, "GRN", p["facility_id"]), po_id=pid, po_ref=p["ref"], delivery_note=dn, date=self.today().isoformat(), received_by=actor,
                      lines=[{"line_no": pl["line_no"], "qty": s3(q)} for pl, q, _ in plan], evidence=ev)
        for item, q, pl, batch, expiry, loc in stock:
            self._stock_in(org, item, q, Decimal(pl["unit_price"]), batch, expiry, loc, "RECEIPT", g["ref"], actor, f"Goods received on {p['ref']}")
        for pl, q, _ in plan: pl["received_qty"] = s3(Decimal(pl["received_qty"]) + q)
        full = all(Decimal(x["received_qty"]) >= Decimal(x["qty"]) for x in p["lines"]); p["status"] = "RECEIVED" if full else "PARTIAL"
        self._hist(p, actor, "RECEIVED" if full else "PARTLY_RECEIVED", g["ref"]); self._put("hc_po", org, p); self._put("hc_grn", org, g); self.log("HC_GOODS_RECEIVED", actor, g["id"], org, f"{g['ref']} on {p['ref']}"); return g

    def list_receipts(self, org, fid, actor) -> list:
        self._fac(org, fid, actor); return sorted(self._of("hc_grn", org, fid), key=lambda g: g["ref"])

    # ------------------------------------------------------------------ supplier invoices
    @staticmethod
    def _net(i) -> Decimal: return Decimal(i["amount"]) - sum((Decimal(c["amount"]) for c in i["credits"]), ZERO)

    def record_invoice(self, org, pid, d, actor) -> dict:
        p = self._rec("hc_po", org, pid, "Purchase order", actor); self._fac(org, p["facility_id"], actor, active=True)
        if p["status"] not in ("PARTIAL", "RECEIVED"): raise HealthStateError("An invoice can only be recorded once some of the goods have been received.")
        no = txt(d.get("invoice_no"), "Supplier invoice number", 1, 80); amount = money(d.get("amount"), "Invoice amount"); idate = day(d.get("invoice_date"), "Invoice date")
        due = day(d.get("due_date"), "Due date") if d.get("due_date") else None
        if due and due < idate: raise HealthError("The due date cannot be before the invoice date.")
        invs = self._of("hc_inv", org, p["facility_id"])
        for i in invs:
            if i["supplier_id"] == p["supplier_id"] and norm(i["invoice_no"]) == norm(no) and i["status"] != "CANCELLED":
                raise HealthError(f"This invoice number was already recorded for {p['supplier']} ({i['ref']}). Duplicate invoices are not processed.")
        received = sum((q2(Decimal(x["received_qty"]) * Decimal(x["unit_price"])) for x in p["lines"]), ZERO)
        already = sum((self._net(i) for i in invs if i["po_id"] == pid and i["status"] != "CANCELLED"), ZERO)
        allowed = received - already; ok = amount <= allowed
        r = self._new(org, p["facility_id"], ref=self._ref(org, "INV", p["facility_id"]), po_id=pid, po_ref=p["ref"], supplier_id=p["supplier_id"], supplier=p["supplier"], invoice_no=no, invoice_date=idate.isoformat(), due_date=due.isoformat() if due else None,
                      amount=s2(amount), status="MATCHED" if ok else "EXCEPTION", match={"received_value": s2(received), "invoiced_before": s2(already), "allowed": s2(allowed), "matched": ok}, credits=[], exception_note=None,
                      evidence=self._evidence(org, d.get("evidence_ids")), recorded_by=actor, created_at=self.now().isoformat(), history=[])
        self._hist(r, actor, "RECORDED", "three-way match ok" if ok else f"does not match: more than the {s2(allowed)} received and not yet invoiced"); self._put("hc_inv", org, r); self.log("HC_INVOICE_RECORDED", actor, r["id"], org, f"{r['ref']} {r['amount']} {r['status']}"); return r

    def verify_invoice(self, org, iid, exception_note, actor) -> dict:
        r = self._rec("hc_inv", org, iid, "Invoice", actor, True); self._writable(org, r, actor)
        if r["status"] not in ("MATCHED", "EXCEPTION"): raise HealthStateError("Only a recorded invoice can be verified.")
        self._two(actor, r["recorded_by"], "recorded this invoice")
        if r["status"] == "EXCEPTION":
            ex = (exception_note or "").strip()
            if len(ex) < 20: raise HealthError("This invoice does not match the order and goods received. To verify it anyway, record the exception reason (at least 20 characters).")
            r["exception_note"] = ex
        r.update(status="VERIFIED", verified_by=actor); self._hist(r, actor, "VERIFIED", r["exception_note"] or ""); self._put("hc_inv", org, r); self.log("HC_INVOICE_VERIFIED", actor, iid, org, r["ref"]); return r

    def approve_payment(self, org, iid, actor) -> dict:
        r = self._rec("hc_inv", org, iid, "Invoice", actor, True); self._writable(org, r, actor)
        if r["status"] != "VERIFIED": raise HealthStateError("Only a verified invoice can be approved for payment.")
        self._two(actor, r["recorded_by"], "recorded this invoice"); self._two(actor, r["verified_by"], "verified this invoice")
        if self._net(r) <= 0: raise HealthStateError("Nothing is payable on this invoice after credit notes.")
        r.update(status="PAYMENT_APPROVED", payment_approved_by=actor); self._hist(r, actor, "PAYMENT_APPROVED", s2(self._net(r))); self._put("hc_inv", org, r); self.log("HC_PAYMENT_APPROVED", actor, iid, org, f"{r['ref']} {s2(self._net(r))}"); return r

    def pay_invoice(self, org, iid, payment_ref, actor) -> dict:
        r = self._rec("hc_inv", org, iid, "Invoice", actor, True); self._writable(org, r, actor)
        if r["status"] == "PAID": raise HealthStateError(f"{r['ref']} has already been paid. A second payment request is refused.")
        if r["status"] != "PAYMENT_APPROVED": raise HealthStateError("Only an invoice approved for payment can be paid.")
        ref = txt(payment_ref, "Payment reference", 3, 80)
        for i in self._of("hc_inv", org, r["facility_id"]):
            if i["id"] != iid and i.get("payment") and norm(i["payment"]["ref"]) == norm(ref): raise HealthError(f"Payment reference {ref} was already used for {i['ref']}.")
        r.update(status="PAID", payment={"ref": ref, "amount": s2(self._net(r)), "date": self.today().isoformat(), "by": actor})
        self._hist(r, actor, "PAID", f"{ref} {r['payment']['amount']}"); self._put("hc_inv", org, r); self.log("HC_INVOICE_PAID", actor, iid, org, f"{r['ref']} {r['payment']['amount']}"); return r

    def credit_note(self, org, iid, amount, reason, actor) -> dict:
        r = self._rec("hc_inv", org, iid, "Invoice", actor, True); self._writable(org, r, actor)
        if r["status"] in ("PAID", "CANCELLED"): raise HealthStateError("A credit note cannot be applied to a paid or cancelled invoice.")
        amt = money(amount, "Credit amount")
        if amt > self._net(r): raise HealthError(f"The credit cannot be more than the {s2(self._net(r))} still payable on this invoice.")
        r["credits"].append({"amount": s2(amt), "reason": txt(reason, "Reason", 5, 300), "by": actor, "at": self.now().isoformat()})
        self._hist(r, actor, "CREDIT_NOTE", s2(amt)); self._put("hc_inv", org, r); self.log("HC_CREDIT_NOTE", actor, iid, org, f"{r['ref']} {s2(amt)}"); return r

    def cancel_invoice(self, org, iid, note, actor) -> dict:
        r = self._rec("hc_inv", org, iid, "Invoice", actor, True); self._writable(org, r, actor)
        if r["status"] in ("PAID", "CANCELLED"): raise HealthStateError("A paid or cancelled invoice cannot be cancelled.")
        r["status"] = "CANCELLED"; self._hist(r, actor, "CANCELLED", txt(note, "Reason", 3, 500)); self._put("hc_inv", org, r); self.log("HC_INVOICE_CANCELLED", actor, iid, org, r["ref"]); return r

    def list_invoices(self, org, fid, actor) -> list:
        self._fac(org, fid, actor)
        return [dict(i, net_payable=s2(self._net(i))) for i in sorted(self._of("hc_inv", org, fid), key=lambda i: i["ref"])]

    # ------------------------------------------------------------------ ageing and exceptions
    def payables_ageing(self, org, fid, actor, as_of=None) -> dict:
        self._fac(org, fid, actor); t = as_of or self.today(); rows, tot = {}, {b[0]: ZERO for b in AGE_BUCKETS}
        for i in self._of("hc_inv", org, fid):
            if i["status"] in ("CANCELLED", "PAID"): continue
            net = self._net(i)
            if net <= 0: continue
            age = max(0, (t - date.fromisoformat(i["invoice_date"])).days); b = next(n for n, lo, hi in AGE_BUCKETS if lo <= age <= hi)
            r = rows.setdefault(i["supplier_id"], {"supplier": i["supplier"], **{n: ZERO for n, _, _ in AGE_BUCKETS}, "total": ZERO}); r[b] += net; r["total"] += net; tot[b] += net
        out = [{k: (s2(v) if isinstance(v, Decimal) else v) for k, v in r.items()} for r in sorted(rows.values(), key=lambda r: r["supplier"])]
        return {"as_of": t.isoformat(), "rows": out, "totals": {**{k: s2(v) for k, v in tot.items()}, "total": s2(sum(tot.values(), ZERO))}, "basis": "Recorded supplier invoices not yet paid, net of credit notes, aged from the invoice date."}

    def procurement_exceptions(self, org, fid, actor) -> dict:
        self._fac(org, fid, actor)
        return {"budget_exceptions": [{"po": p["ref"], "total": p["total"], **p["exception"]} for p in self._of("hc_po", org, fid) if p.get("exception")],
                "invoice_mismatches": [{"invoice": i["ref"], "supplier": i["supplier"], "amount": i["amount"], "status": i["status"], "note": i["exception_note"]} for i in self._of("hc_inv", org, fid) if not i["match"]["matched"] and i["status"] != "CANCELLED"],
                "part_received_orders": [{"po": p["ref"], "supplier": p["supplier"]} for p in self._of("hc_po", org, fid) if p["status"] == "PARTIAL"]}
