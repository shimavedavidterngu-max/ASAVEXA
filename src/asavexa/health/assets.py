"""Equipment register, maintenance and downtime, retirement approval, and staffing-cost summaries (aggregate only: no individual salaries or employee records)."""
from datetime import date, timedelta
from decimal import Decimal

from .base import P_STAFFING, ZERO, day, enum, month, money, norm, s2, txt, whole
from .claims import ClaimsMixin
from .errors import HealthError, HealthNotFoundError, HealthStateError

ASSET_CATEGORIES = ["DIAGNOSTIC_EQUIPMENT", "THEATRE_AND_PROCEDURE", "FURNITURE", "VEHICLE", "IT_EQUIPMENT", "BUILDING_AND_PLANT", "OTHER"]
CONDITIONS = ["GOOD", "FAIR", "POOR", "OUT_OF_SERVICE"]
MAINT_KINDS = ["PREVENTIVE", "CORRECTIVE"]


class AssetsMixin(ClaimsMixin):
    def create_asset(self, org, fid, d, actor) -> dict:
        self._fac(org, fid, actor, active=True); tag = txt(d.get("tag"), "Asset tag", 2, 40).upper()
        for a in self._of("hc_asset", org, fid):
            if norm(a["tag"]) == norm(tag): raise HealthError(f"Asset tag {tag} is already used ({a['name']}).")
        dept = self._dept(org, fid, d.get("dept_id")); acq = day(d.get("acquisition_date"), "Acquisition date")
        if acq > self.today(): raise HealthError("The acquisition date cannot be in the future.")
        warranty = day(d["warranty_until"], "Warranty end") if d.get("warranty_until") else None
        interval = whole(d["maintenance_interval_days"], "Maintenance interval (days)", 7, 1825) if d.get("maintenance_interval_days") not in (None, "") else None
        po = None
        if d.get("po_id"):
            po = self._rec("hc_po", org, d["po_id"], "Purchase order", actor)
            if po["facility_id"] != fid: raise HealthError("That purchase order is not at this facility.")
        r = self._new(org, fid, ref=self._ref(org, "EQ", fid), tag=tag, name=txt(d.get("name"), "Name", 2, 200), category=enum(d.get("category"), ASSET_CATEGORIES, "Category"), dept_id=dept["id"], dept=dept["name"],
                      location=txt(d.get("location"), "Location", 0, 100, required=False), acquisition_date=acq.isoformat(), cost=s2(money(d.get("cost"), "Cost")), po_id=po["id"] if po else None, supplier=po["supplier"] if po else txt(d.get("supplier"), "Supplier", 0, 200, required=False),
                      warranty_until=warranty.isoformat() if warranty else None, interval_days=interval, condition=enum(d.get("condition") or "GOOD", CONDITIONS, "Condition"), status="ACTIVE", evidence=self._evidence(org, d.get("evidence_ids")), retirement=None, created_by=actor, history=[])
        self._hist(r, actor, "REGISTERED"); self._put("hc_asset", org, r); self.log("HC_ASSET_ADDED", actor, r["id"], org, f"{r['ref']} {r['cost']}"); return r

    def set_condition(self, org, aid, condition, note, actor) -> dict:
        r = self._rec("hc_asset", org, aid, "Asset", actor, True); self._writable(org, r, actor)
        if r["status"] != "ACTIVE": raise HealthStateError("Only an active asset's condition can be changed.")
        r["condition"] = enum(condition, CONDITIONS, "Condition"); self._hist(r, actor, "CONDITION_" + r["condition"], txt(note, "Note", 0, 300, required=False)); self._put("hc_asset", org, r); self.log("HC_ASSET_CONDITION_SET", actor, aid, org, f"{r['ref']} {r['condition']}"); return r

    def link_asset_evidence(self, org, aid, ids, actor) -> dict:
        r = self._rec("hc_asset", org, aid, "Asset", actor, True); self._writable(org, r, actor)
        have = {e["evidence_id"] for e in r["evidence"]}; r["evidence"] += [e for e in self._evidence(org, ids) if e["evidence_id"] not in have]; self._put("hc_asset", org, r); self.log("HC_ASSET_EVIDENCE_LINKED", actor, aid, org, r["ref"]); return r

    def request_retirement(self, org, aid, reason, actor) -> dict:
        r = self._rec("hc_asset", org, aid, "Asset", actor, True); self._writable(org, r, actor)
        if r["status"] != "ACTIVE": raise HealthStateError("Only an active asset can be put forward for retirement.")
        if any(m["asset_id"] == aid and m["status"] == "REQUESTED" for m in self._of("hc_maint", org, r["facility_id"])): raise HealthStateError("Finish or cancel the open maintenance first.")
        r.update(status="DISPOSAL_PENDING", retirement={"reason": txt(reason, "Reason for retirement or disposal", 10, 500), "requested_by": actor}); self._hist(r, actor, "RETIREMENT_REQUESTED", r["retirement"]["reason"]); self._put("hc_asset", org, r); self.log("HC_ASSET_RETIRE_REQ", actor, aid, org, r["ref"]); return r

    def decide_retirement(self, org, aid, ok, note, actor) -> dict:
        r = self._rec("hc_asset", org, aid, "Asset", actor, True); self._writable(org, r, actor)
        if r["status"] != "DISPOSAL_PENDING": raise HealthStateError("No retirement is waiting for a decision.")
        self._two(actor, r["retirement"]["requested_by"], "asked for this retirement"); n = txt(note, "A note saying why", 0 if ok else 3, 300, required=not ok)
        r["status"] = "RETIRED" if ok else "ACTIVE"; r["retirement"].update(decided_by=actor, decision_note=n, outcome="APPROVED" if ok else "REJECTED")
        self._hist(r, actor, "RETIRED" if ok else "RETIREMENT_REFUSED", n); self._put("hc_asset", org, r); self.log("HC_ASSET_" + ("RETIRED" if ok else "RETIRE_REFUSED"), actor, aid, org, r["ref"])
        return dict(r, accounting_note="Remove the asset from the fixed-asset records and post any disposal gain or loss in the ledger. ASAVEXA does not post it for you." if ok else "")

    def _next_due(self, org, a):
        if not a.get("interval_days"): return None
        done = [m["completed_date"] for m in self._of("hc_maint", org, a["facility_id"]) if m["asset_id"] == a["id"] and m["status"] == "COMPLETED" and m["kind"] == "PREVENTIVE"]
        return (date.fromisoformat(max(done) if done else a["acquisition_date"]) + timedelta(days=a["interval_days"])).isoformat()

    def list_assets(self, org, fid, actor) -> list:
        self._fac(org, fid, actor); t = self.today().isoformat()
        return [dict(a, next_due=self._next_due(org, a), under_warranty=bool(a["warranty_until"] and a["warranty_until"] >= t)) for a in sorted(self._of("hc_asset", org, fid), key=lambda a: a["ref"])]

    # ---- maintenance
    def request_maintenance(self, org, aid, d, actor) -> dict:
        a = self._rec("hc_asset", org, aid, "Asset", actor); self._fac(org, a["facility_id"], actor, active=True)
        if a["status"] != "ACTIVE": raise HealthStateError("Maintenance can only be requested for an active asset.")
        r = self._new(org, a["facility_id"], ref=self._ref(org, "MNT", a["facility_id"]), asset_id=aid, asset=a["name"], tag=a["tag"], kind=enum(d.get("kind"), MAINT_KINDS, "Kind"), description=txt(d.get("description"), "What needs doing", 3, 500),
                      due_date=day(d.get("due_date"), "Due date").isoformat(), status="REQUESTED", requested_by=actor, evidence=self._evidence(org, d.get("evidence_ids")), history=[])
        self._hist(r, actor, "REQUESTED"); self._put("hc_maint", org, r); self.log("HC_MAINT_REQUESTED", actor, r["id"], org, f"{r['ref']} {a['tag']}"); return r

    def complete_maintenance(self, org, mid, d, actor) -> dict:
        r = self._rec("hc_maint", org, mid, "Maintenance", actor, True); self._writable(org, r, actor)
        if r["status"] != "REQUESTED": raise HealthStateError("Only an open maintenance request can be completed.")
        done = day(d.get("completed_date"), "Completed date")
        if done > self.today(): raise HealthError("The completed date cannot be in the future.")
        po = None
        if d.get("po_id"):
            po = self._rec("hc_po", org, d["po_id"], "Purchase order", actor)
            if po["facility_id"] != r["facility_id"]: raise HealthError("That purchase order is not at this facility.")
        r.update(status="COMPLETED", completed_date=done.isoformat(), cost=s2(money(d.get("cost", "0"), "Cost", positive=False)), downtime_days=whole(d.get("downtime_days", 0), "Downtime days", 0, 3650), po_id=po["id"] if po else None,
                 work_note=txt(d.get("work_note"), "What was done", 3, 500), completed_by=actor); r["evidence"] += self._evidence(org, d.get("evidence_ids"))
        self._hist(r, actor, "COMPLETED", f"cost {r['cost']}, downtime {r['downtime_days']} day(s)"); self._put("hc_maint", org, r); self.log("HC_MAINT_COMPLETED", actor, mid, org, f"{r['ref']} {r['cost']}"); return r

    def cancel_maintenance(self, org, mid, note, actor) -> dict:
        r = self._rec("hc_maint", org, mid, "Maintenance", actor, True); self._writable(org, r, actor)
        if r["status"] != "REQUESTED": raise HealthStateError("Only an open maintenance request can be cancelled.")
        r["status"] = "CANCELLED"; self._hist(r, actor, "CANCELLED", txt(note, "Reason", 3, 300)); self._put("hc_maint", org, r); self.log("HC_MAINT_CANCELLED", actor, mid, org, r["ref"]); return r

    def list_maintenance(self, org, fid, actor) -> list:
        self._fac(org, fid, actor); return sorted(self._of("hc_maint", org, fid), key=lambda m: m["ref"])

    def maintenance_due(self, org, fid, actor, within_days=30) -> list:
        self._fac(org, fid, actor); cutoff = (self.today() + timedelta(days=within_days)).isoformat(); out = []
        for m in self._of("hc_maint", org, fid):
            if m["status"] == "REQUESTED" and m["due_date"] <= cutoff: out.append({"kind": "REQUEST", "ref": m["ref"], "tag": m["tag"], "asset": m["asset"], "due": m["due_date"], "overdue": m["due_date"] < self.today().isoformat()})
        pending = {m["asset_id"] for m in self._of("hc_maint", org, fid) if m["status"] == "REQUESTED"}
        for a in self._of("hc_asset", org, fid):
            nd = self._next_due(org, a)
            if a["status"] == "ACTIVE" and nd and nd <= cutoff and a["id"] not in pending: out.append({"kind": "SCHEDULE", "ref": a["ref"], "tag": a["tag"], "asset": a["name"], "due": nd, "overdue": nd < self.today().isoformat()})
        return sorted(out, key=lambda x: x["due"])

    def downtime_summary(self, org, fid, actor) -> list:
        self._fac(org, fid, actor); by = {}
        for m in self._of("hc_maint", org, fid):
            if m["status"] == "COMPLETED": x = by.setdefault(m["asset_id"], {"tag": m["tag"], "asset": m["asset"], "jobs": 0, "downtime_days": 0, "cost": ZERO}); x["jobs"] += 1; x["downtime_days"] += m["downtime_days"]; x["cost"] += Decimal(m["cost"])
        return [dict(v, cost=s2(v["cost"])) for v in sorted(by.values(), key=lambda v: v["tag"])]

    # ------------------------------------------------------------------ staffing costs (aggregate)
    def record_staffing(self, org, fid, d, actor) -> dict:
        self._need(org, actor, P_STAFFING, "record staffing costs"); self._fac(org, fid, actor, active=True); dept = self._dept(org, fid, d.get("dept_id")); m = month(d.get("month"), "Month")
        for s in self._of("hc_staff", org, fid):
            if s["dept_id"] == dept["id"] and s["month"] == m and s["status"] != "REJECTED": raise HealthError(f"Staffing cost for {dept['name']} in {m} is already recorded ({s['ref']}).")
        r = self._new(org, fid, ref=self._ref(org, "STF", fid), dept_id=dept["id"], dept=dept["name"], month=m, headcount=whole(d.get("headcount"), "Number of staff", 0, 100000), gross_cost=s2(money(d.get("gross_cost"), "Gross pay cost", positive=False)),
                      allowances=s2(money(d.get("allowances", "0"), "Allowances", positive=False)), source=txt(d.get("source"), "Source (payroll system or summary reference)", 3, 200), status="SUBMITTED", recorded_by=actor, evidence=self._evidence(org, d.get("evidence_ids")), history=[])
        self._hist(r, actor, "RECORDED"); self._put("hc_staff", org, r); self.log("HC_STAFF_RECORDED", actor, r["id"], org, f"{r['ref']} {dept['name']} {m}"); return r

    def decide_staffing(self, org, sid, ok, note, actor) -> dict:
        self._need(org, actor, P_STAFFING, "decide staffing costs"); r = self._rec("hc_staff", org, sid, "Staffing summary", actor, True); self._writable(org, r, actor)
        if r["status"] != "SUBMITTED": raise HealthStateError("That summary has already been decided.")
        self._two(actor, r["recorded_by"], "recorded this summary"); r["status"] = "APPROVED" if ok else "REJECTED"; n = txt(note, "A note saying why", 0 if ok else 3, 300, required=not ok)
        self._hist(r, actor, r["status"], n); self._put("hc_staff", org, r); self.log("HC_STAFF_" + r["status"], actor, sid, org, r["ref"]); return r

    def list_staffing(self, org, fid, actor) -> dict:
        self._need(org, actor, P_STAFFING, "see staffing costs"); self._fac(org, fid, actor); rows = sorted(self._of("hc_staff", org, fid), key=lambda s: (s["month"], s["dept"]), reverse=True)
        by = {}
        for s in rows:
            if s["status"] == "APPROVED": x = by.setdefault(s["dept"], {"dept": s["dept"], "months": 0, "headcount_months": 0, "total": ZERO}); x["months"] += 1; x["headcount_months"] += s["headcount"]; x["total"] += Decimal(s["gross_cost"]) + Decimal(s["allowances"])
        return {"rows": rows, "by_department": [dict(v, total=s2(v["total"])) for v in sorted(by.values(), key=lambda v: v["dept"])], "note": "Aggregate department figures only. ASAVEXA holds no individual salaries or employee records here. Only approved summaries count toward spending."}
