"""Facilities, departments, who may see which facility, and budgets with versions, transfers and budget-versus-actual."""
from datetime import timedelta
from decimal import Decimal

from .base import CATEGORIES, FACILITY_TYPES, OWNERSHIP, P_ADMIN, P_READ, ZERO, Base, day, dec, enum, money, q2, s2, txt, whole
from .errors import HealthError, HealthForbiddenError, HealthNotFoundError, HealthStateError

SPENT_INVOICE = ("VERIFIED", "PAYMENT_APPROVED", "PAID")
LIVE_PO = ("OPEN", "PARTIAL", "RECEIVED")


class FacilityMixin(Base):
    # ------------------------------------------------------------------ facilities
    def _facility_fields(self, d, cur=None) -> dict:
        c = cur or {}
        f = {"name": txt(d.get("name", c.get("name")), "Name", 2, 200), "type": enum(d.get("type", c.get("type")), FACILITY_TYPES, "Facility type"), "ownership": enum(d.get("ownership", c.get("ownership")), OWNERSHIP, "Ownership"),
             "region": txt(d.get("region", c.get("region")), "Region", 2, 100), "address": txt(d.get("address", c.get("address")), "Address", 0, 300, required=False),
             "currency": txt(d.get("currency", c.get("currency")), "Currency", 3, 3).upper(), "fy_start_month": whole(d.get("fy_start_month", c.get("fy_start_month", 1)), "Financial year start month", 1, 12),
             "tax_note": txt(d.get("tax_note", c.get("tax_note")), "Tax settings", 0, 300, required=False)}
        if not f["currency"].isalpha():
            raise HealthError("Currency must be a three-letter code such as NGN.")
        f["block_overspend"] = bool(d.get("block_overspend", c.get("block_overspend", True)))
        f["min_quotes"] = whole(d.get("min_quotes", c.get("min_quotes", 0)), "Quotes required", 0, 5)
        f["expiry_alert_days"] = whole(d.get("expiry_alert_days", c.get("expiry_alert_days", 90)), "Expiry alert days", 1, 730)
        return f

    def create_facility(self, org, d, actor) -> dict:
        self._need(org, actor, P_ADMIN, "register facilities")
        f = self._facility_fields(d)
        for x in self._all("hc_facility", org):
            if x["status"] == "ACTIVE" and x["name"].strip().lower() == f["name"].lower():
                raise HealthError(f"A facility called {x['name']} already exists ({x['ref']}).")
        r = self._new(org, None, ref=self._ref(org, "F"), **f, status="ACTIVE", created_by=actor, created_at=self.now().isoformat(), history=[])
        r["facility_id"] = r["id"]
        self._hist(r, actor, "CREATED"); self._put("hc_facility", org, r); self.log("HC_FACILITY_CREATED", actor, r["id"], org, r["ref"])
        return self._fview(org, r)

    def update_facility(self, org, fid, d, actor) -> dict:
        self._need(org, actor, P_ADMIN, "change facilities")
        r = self._fac(org, fid, actor); cur = self._raw("hc_facility", org, fid, "Facility", for_update=True)
        cur.update(self._facility_fields(d, cur)); self._hist(cur, actor, "UPDATED"); self._put("hc_facility", org, cur); self.log("HC_FACILITY_UPDATED", actor, fid, org, cur["ref"])
        return self._fview(org, cur)

    def set_facility_status(self, org, fid, active, note, actor) -> dict:
        self._need(org, actor, P_ADMIN, "change facilities")
        self._fac(org, fid, actor); r = self._raw("hc_facility", org, fid, "Facility", for_update=True)
        want = "ACTIVE" if active else "INACTIVE"
        if r["status"] == want: raise HealthStateError(f"This facility is already {want.lower()}.")
        r["status"] = want; self._hist(r, actor, want, txt(note, "Reason", 3, 500)); self._put("hc_facility", org, r); self.log("HC_FACILITY_" + want, actor, fid, org, r["ref"])
        return self._fview(org, r)

    def _fview(self, org, f) -> dict:
        v = dict(f); v["departments"] = sorted(self._of("hc_dept", org, f["id"]), key=lambda d: d["code"]); return v

    def list_facilities(self, org, actor) -> list:
        allowed = None if self._unrestricted(org, actor) else set(self._settings(org)["access"].get(actor, []))
        return [self._fview(org, f) for f in sorted(self._all("hc_facility", org), key=lambda f: f["ref"]) if allowed is None or f["id"] in allowed]

    def get_facility(self, org, fid, actor) -> dict: return self._fview(org, self._fac(org, fid, actor))

    def add_department(self, org, fid, d, actor) -> dict:
        self._need(org, actor, P_ADMIN, "change facilities")
        self._fac(org, fid, actor, active=True)
        code, name = txt(d.get("code"), "Department code", 2, 20).upper(), txt(d.get("name"), "Department name", 2, 120)
        for x in self._of("hc_dept", org, fid):
            if x["code"] == code: raise HealthError(f"Department code {code} is already used in this facility.")
        r = self._new(org, fid, code=code, name=name, active=True, cost_centre=txt(d.get("cost_centre"), "Cost centre", 0, 40, required=False))
        self._put("hc_dept", org, r); self.log("HC_DEPT_ADDED", actor, r["id"], org, code); return r

    def set_department_active(self, org, fid, did, active, actor) -> dict:
        self._need(org, actor, P_ADMIN, "change facilities")
        self._fac(org, fid, actor)
        r = self._raw("hc_dept", org, did, "Department", for_update=True)
        if r["facility_id"] != fid: raise HealthNotFoundError("Department not found.")
        r["active"] = bool(active); self._put("hc_dept", org, r); self.log("HC_DEPT_ACTIVE" if active else "HC_DEPT_INACTIVE", actor, did, org, r["code"]); return r

    # ------------------------------------------------------------------ access
    def set_access(self, org, user_id, facility_ids, actor) -> dict:
        self._need(org, actor, P_ADMIN, "grant facility access")
        user_id = txt(user_id, "User", 1, 100)
        ids = list(dict.fromkeys(str(i) for i in (facility_ids or [])))
        known = user_id in self._settings(org)["access"]
        if not known and not self.can(org, user_id, P_READ):
            # Only people who belong to this organisation (and can use the health workspace) can be given facility access.
            raise HealthNotFoundError("That person was not found in this organisation.")
        for i in ids:
            f = self.store.get("hc_facility", f"{org}:{i}")
            if f is None or f["org"] != org: raise HealthError("A facility in the list was not found in this organisation.")
        s = self._settings(org, for_update=True)
        if ids: s["access"][user_id] = ids
        else: s["access"].pop(user_id, None)
        self._put("hc_setting", org, s); self.log("HC_ACCESS_SET", actor, user_id, org, f"{len(ids)} facilities"); return {"user_id": user_id, "facility_ids": ids}

    def get_access(self, org, actor) -> dict:
        self._need(org, actor, P_ADMIN, "see facility access")
        return self._settings(org)["access"]

    # ------------------------------------------------------------------ budgets
    def _lines(self, org, fid, lines) -> list:
        if not isinstance(lines, list) or not lines: raise HealthError("Add at least one budget line.")
        out, seen = [], set()
        for i, ln in enumerate(lines, 1):
            dept = self._dept(org, fid, ln.get("dept_id"), f"Line {i} department")
            cat = enum(ln.get("category"), CATEGORIES, f"Line {i} category")
            if (dept["id"], cat) in seen: raise HealthError(f"Line {i} repeats {dept['name']} / {cat}.")
            seen.add((dept["id"], cat))
            out.append({"line_id": f"L{i}", "dept_id": dept["id"], "dept": dept["name"], "category": cat, "amount": s2(money(ln.get("amount"), f"Line {i} amount")), "account_id": txt(ln.get("account_id"), "Ledger account", 0, 80, required=False) or None})
        return out

    def _period(self, d):
        s, e = day(d.get("period_start"), "Start date"), day(d.get("period_end"), "End date")
        if e <= s: raise HealthError("The end date must be after the start date.")
        if (e - s).days > 400: raise HealthError("A budget period cannot be longer than about a year.")
        return s, e

    def create_budget(self, org, fid, d, actor) -> dict:
        f = self._fac(org, fid, actor, active=True); s, e = self._period(d)
        r = self._new(org, fid, ref=self._ref(org, "B", fid), name=txt(d.get("name"), "Name", 3, 200), period_start=s.isoformat(), period_end=e.isoformat(), version=1, status="DRAFT", lines=self._lines(org, fid, d.get("lines")),
                      transfers=[], evidence=self._evidence(org, d.get("evidence_ids")), supersedes=None, created_by=actor, created_at=self.now().isoformat(), history=[])
        self._hist(r, actor, "CREATED"); self._put("hc_budget", org, r); self.log("HC_BUDGET_CREATED", actor, r["id"], org, r["ref"]); return r

    def update_budget(self, org, bid, d, actor) -> dict:
        r = self._rec("hc_budget", org, bid, "Budget", actor, True); self._writable(org, r, actor)
        if r["status"] not in ("DRAFT", "REJECTED"): raise HealthStateError("Only a draft or sent-back budget can be edited. Revise an approved budget instead.")
        s, e = self._period(d)
        r.update(name=txt(d.get("name"), "Name", 3, 200), period_start=s.isoformat(), period_end=e.isoformat(), lines=self._lines(org, r["facility_id"], d.get("lines")), evidence=self._evidence(org, d.get("evidence_ids")), status="DRAFT")
        self._hist(r, actor, "EDITED"); self._put("hc_budget", org, r); self.log("HC_BUDGET_EDITED", actor, bid, org, r["ref"]); return r

    def submit_budget(self, org, bid, actor) -> dict:
        r = self._rec("hc_budget", org, bid, "Budget", actor, True); self._writable(org, r, actor)
        if r["status"] not in ("DRAFT", "REJECTED"): raise HealthStateError("Only a draft or sent-back budget can be submitted.")
        r.update(status="SUBMITTED", submitted_by=actor); self._hist(r, actor, "SUBMITTED"); self._put("hc_budget", org, r); self.log("HC_BUDGET_SUBMITTED", actor, bid, org, r["ref"]); return r

    def approve_budget(self, org, bid, actor) -> dict:
        r = self._rec("hc_budget", org, bid, "Budget", actor, True); self._writable(org, r, actor)
        if r["status"] != "SUBMITTED": raise HealthStateError("Only a submitted budget can be approved.")
        self._two(actor, r["submitted_by"], "submitted this budget")
        for o in self._of("hc_budget", org, r["facility_id"]):
            if o["id"] != r["id"] and o["status"] == "APPROVED" and o["id"] != r.get("supersedes") and o["period_start"] <= r["period_end"] and r["period_start"] <= o["period_end"]:
                raise HealthStateError(f"{o['ref']} is already approved for an overlapping period. Revise that budget instead of approving a second one.")
        if r.get("supersedes"):
            old = self._raw("hc_budget", org, r["supersedes"], "Budget", for_update=True); old["status"] = "SUPERSEDED"; self._hist(old, actor, "SUPERSEDED", f"by {r['ref']}"); self._put("hc_budget", org, old)
        r.update(status="APPROVED", decided_by=actor, decided_at=self.now().isoformat()); self._hist(r, actor, "APPROVED"); self._put("hc_budget", org, r); self.log("HC_BUDGET_APPROVED", actor, bid, org, r["ref"]); return r

    def reject_budget(self, org, bid, note, actor) -> dict:
        r = self._rec("hc_budget", org, bid, "Budget", actor, True); self._writable(org, r, actor)
        if r["status"] != "SUBMITTED": raise HealthStateError("Only a submitted budget can be sent back.")
        self._two(actor, r["submitted_by"], "submitted this budget")
        r.update(status="REJECTED", decided_by=actor, decision_note=txt(note, "A note saying why", 3, 500)); self._hist(r, actor, "REJECTED", r["decision_note"]); self._put("hc_budget", org, r); self.log("HC_BUDGET_REJECTED", actor, bid, org, r["ref"]); return r

    def revise_budget(self, org, bid, reason, actor) -> dict:
        old = self._rec("hc_budget", org, bid, "Budget", actor); self._writable(org, old, actor)
        if old["status"] != "APPROVED": raise HealthStateError("Only an approved budget can be revised.")
        for o in self._of("hc_budget", org, old["facility_id"]):
            if o.get("supersedes") == old["id"] and o["status"] in ("DRAFT", "SUBMITTED", "REJECTED"): raise HealthStateError(f"{o['ref']} is already a revision of this budget.")
        r = self._new(org, old["facility_id"], ref=self._ref(org, "B", old["facility_id"]), name=old["name"], period_start=old["period_start"], period_end=old["period_end"], version=old["version"] + 1, status="DRAFT",
                      lines=[dict(x) for x in self._effective_lines(old)], transfers=[], evidence=[], supersedes=old["id"], revision_reason=txt(reason, "Reason for the revision", 10, 500), created_by=actor, created_at=self.now().isoformat(), history=[])
        self._hist(r, actor, "REVISION_STARTED", r["revision_reason"]); self._put("hc_budget", org, r); self.log("HC_BUDGET_REVISED", actor, r["id"], org, f"{r['ref']} revises {old['ref']}"); return r

    @staticmethod
    def _effective_lines(b) -> list:
        """Approved amounts adjusted by approved transfers."""
        out = {ln["line_id"]: dict(ln, base=ln["amount"]) for ln in b["lines"]}
        for t in b.get("transfers", []):
            if t["status"] == "APPROVED":
                out[t["from_line"]]["amount"] = s2(Decimal(out[t["from_line"]]["amount"]) - Decimal(t["amount"]))
                out[t["to_line"]]["amount"] = s2(Decimal(out[t["to_line"]]["amount"]) + Decimal(t["amount"]))
        return list(out.values())

    def get_budget(self, org, bid, actor) -> dict:
        b = self._rec("hc_budget", org, bid, "Budget", actor); v = dict(b); v["effective_lines"] = self._effective_lines(b); return v

    def list_budgets(self, org, fid, actor) -> list:
        self._fac(org, fid, actor); return sorted(self._of("hc_budget", org, fid), key=lambda b: (b["ref"]))

    # ---- transfers between lines
    def request_transfer(self, org, bid, from_line, to_line, amount, reason, actor) -> dict:
        b = self._rec("hc_budget", org, bid, "Budget", actor, True); self._writable(org, b, actor)
        if b["status"] != "APPROVED": raise HealthStateError("Transfers can only be requested on an approved budget.")
        lines = {x["line_id"]: x for x in b["lines"]}
        if from_line not in lines or to_line not in lines or from_line == to_line: raise HealthError("Choose two different lines of this budget.")
        amt = money(amount, "Amount")
        row = next(x for x in self.execution(org, b["facility_id"], bid, actor)["rows"] if x["line_id"] == from_line)
        pending = sum((Decimal(t["amount"]) for t in b["transfers"] if t["status"] == "PENDING" and t["from_line"] == from_line), ZERO)
        if amt + pending > Decimal(row["available"]): raise HealthError(f"Only {row['available']} is available on the source line (after pending transfers), so {s2(amt)} cannot be moved.")
        t = {"id": f"T{len(b['transfers']) + 1}", "from_line": from_line, "to_line": to_line, "amount": s2(amt), "reason": txt(reason, "Reason", 10, 500), "status": "PENDING", "requested_by": actor, "requested_at": self.now().isoformat()}
        b["transfers"].append(t); self._hist(b, actor, "TRANSFER_REQUESTED", f"{t['id']} {t['amount']}"); self._put("hc_budget", org, b); self.log("HC_TRANSFER_REQUESTED", actor, bid, org, f"{b['ref']} {t['id']} {t['amount']}"); return t

    def decide_transfer(self, org, bid, tid, ok, note, actor) -> dict:
        b = self._rec("hc_budget", org, bid, "Budget", actor, True); self._writable(org, b, actor)
        t = next((x for x in b["transfers"] if x["id"] == tid), None)
        if t is None: raise HealthNotFoundError("Transfer not found.")
        if t["status"] != "PENDING": raise HealthStateError("That transfer has already been decided.")
        self._two(actor, t["requested_by"], "asked for this transfer")
        if ok:
            row = next(x for x in self.execution(org, b["facility_id"], bid, actor)["rows"] if x["line_id"] == t["from_line"])
            if Decimal(t["amount"]) > Decimal(row["available"]): raise HealthError("The source line no longer has enough available to move.")
        t.update(status="APPROVED" if ok else "REJECTED", decided_by=actor, decision_note=txt(note, "Note", 3 if not ok else 0, 500, required=not ok))
        self._hist(b, actor, "TRANSFER_APPROVED" if ok else "TRANSFER_REJECTED", tid); self._put("hc_budget", org, b); self.log("HC_TRANSFER_" + ("APPROVED" if ok else "REJECTED"), actor, bid, org, f"{b['ref']} {tid}"); return t

    # ---- spend, commitments, availability
    def _staff_spend(self, org, fid, start, end) -> dict:
        out = {}
        for s in self._of("hc_staff", org, fid):
            if s["status"] == "APPROVED" and start.isoformat()[:7] <= s["month"] <= end.isoformat()[:7]:
                k = (s["dept_id"], "STAFFING"); out[k] = out.get(k, ZERO) + Decimal(s["gross_cost"]) + Decimal(s["allowances"])
        return out

    def _flows(self, org, fid, start, end) -> dict:
        """(dept, category) -> {spent, committed} for the period. Spent = verified invoices (net of credit notes) + approved staffing costs + completed maintenance not bought through a PO.
        Committed = open purchase orders less what has already been verified on invoices, so a commitment is never counted twice."""
        pos = {p["id"]: p for p in self._of("hc_po", org, fid)}
        out = {}
        def slot(k): return out.setdefault(k, {"spent": ZERO, "committed": ZERO})
        verified = {}
        for i in self._of("hc_inv", org, fid):
            net = Decimal(i["amount"]) - sum((Decimal(c["amount"]) for c in i["credits"]), ZERO)
            if i["status"] in SPENT_INVOICE:
                verified[i["po_id"]] = verified.get(i["po_id"], ZERO) + net
                if start.isoformat() <= i["invoice_date"] <= end.isoformat():
                    p = pos[i["po_id"]]; slot((p["dept_id"], p["category"]))["spent"] += net
        for p in pos.values():
            if p["status"] in LIVE_PO and start.isoformat() <= p["date"] <= end.isoformat():
                slot((p["dept_id"], p["category"]))["committed"] += max(ZERO, Decimal(p["total"]) - verified.get(p["id"], ZERO))
        for k, v in self._staff_spend(org, fid, start, end).items(): slot(k)["spent"] += v
        assets = {a["id"]: a for a in self._of("hc_asset", org, fid)}
        for m in self._of("hc_maint", org, fid):
            if m["status"] == "COMPLETED" and not m.get("po_id") and start.isoformat() <= m["completed_date"] <= end.isoformat():
                slot((assets[m["asset_id"]]["dept_id"], "MAINTENANCE"))["spent"] += Decimal(m["cost"])
        return out

    def execution(self, org, fid, bid, actor) -> dict:
        self._fac(org, fid, actor)
        return self._exec(org, fid, bid)

    def _exec(self, org, fid, bid) -> dict:
        b = self._raw("hc_budget", org, bid, "Budget")
        if b["facility_id"] != fid: raise HealthNotFoundError("Budget not found.")
        s, e = day(b["period_start"], "Start"), day(b["period_end"], "End"); flows = self._flows(org, fid, s, e)
        rows, tot = [], {"budget": ZERO, "spent": ZERO, "committed": ZERO, "available": ZERO}
        for ln in self._effective_lines(b):
            fl = flows.get((ln["dept_id"], ln["category"]), {"spent": ZERO, "committed": ZERO}); amt = Decimal(ln["amount"]); av = amt - fl["spent"] - fl["committed"]
            row = {"line_id": ln["line_id"], "dept_id": ln["dept_id"], "dept": ln["dept"], "category": ln["category"], "approved": ln["base"], "budget": ln["amount"], "spent": s2(fl["spent"]), "committed": s2(fl["committed"]),
                   "available": s2(av), "used_pct": s2(fl["spent"] * 100 / amt) if amt else None, "overspent": av < 0, "ledger_actual": None}
            if ln.get("account_id") and self.accounting is not None: row["ledger_actual"] = self._ledger_actual(org, ln["account_id"], s, e)
            rows.append(row)
            for k, v in (("budget", amt), ("spent", fl["spent"]), ("committed", fl["committed"]), ("available", av)): tot[k] += v
        covered = {(r["dept_id"], r["category"]) for r in rows}; names = {d["id"]: d["name"] for d in self._of("hc_dept", org, fid)}; unb = []
        for (did, cat), fl in sorted(flows.items(), key=lambda kv: (names.get(kv[0][0], ""), kv[0][1])):
            if (did, cat) in covered or (fl["spent"] == 0 and fl["committed"] == 0): continue
            unb.append({"dept_id": did, "dept": names.get(did, did), "category": cat, "spent": s2(fl["spent"]), "committed": s2(fl["committed"])})
        un_spent = sum((Decimal(u["spent"]) for u in unb), ZERO); un_com = sum((Decimal(u["committed"]) for u in unb), ZERO)
        return {"budget_id": bid, "ref": b["ref"], "status": b["status"], "period_start": b["period_start"], "period_end": b["period_end"], "rows": rows, "unbudgeted": unb, "totals": {**{k: s2(v) for k, v in tot.items()}, "unbudgeted_spent": s2(un_spent), "unbudgeted_committed": s2(un_com), "total_spent": s2(tot["spent"] + un_spent)},
                "note": "Spent = verified supplier invoices (net of credit notes) + approved staffing costs + completed maintenance bought outside a purchase order. Committed = open purchase orders not yet invoiced. The ledger column is the organisation-wide posted amount for the linked account and is shown for comparison only."}

    def _ledger_actual(self, org, account_id, start, end):
        try:
            tot = ZERO
            for j in self.accounting.journals.list_for_org(org):
                st = j.status.value if hasattr(j.status, "value") else str(j.status)
                if st == "DRAFT" or not (start <= j.date <= end): continue
                for ln in j.lines:
                    if ln.account_id == account_id: tot += ln.debit_amount - ln.credit_amount
            return s2(tot)
        except Exception:
            return None

    def _available(self, org, fid, dept_id, category, on) -> tuple:
        """Available on the approved budget line covering this date, or (None, None) when there is no such line."""
        for b in self._of("hc_budget", org, fid):
            if b["status"] == "APPROVED" and b["period_start"] <= on.isoformat() <= b["period_end"]:
                for r in self._exec(org, fid, b["id"])["rows"]:
                    if r["dept_id"] == dept_id and r["category"] == category: return Decimal(r["available"]), b
        return None, None

