"""Health Centre Administration service.

Records (shared document store, per organisation): hc_facility, hc_dept, hc_setting (counters and who may see which facility), hc_budget, hc_supplier, hc_req, hc_po, hc_grn, hc_inv,
hc_item, hc_move (immutable stock movements), hc_adj, hc_payer, hc_fee, hc_rcpt, hc_claim, hc_recon, hc_asset, hc_maint, hc_staff, hc_report.

This is a financial and administrative workspace. It holds NO patient names, identifiers, diagnoses, prescriptions, clinical notes or laboratory results. Claims carry a random
internal reference, a billing category and a month only. Every record belongs to one facility, and a person sees only the facilities they have been given (or all, with the admin
permission); a facility that is not theirs is reported as not found. Whoever raises, records or requests something cannot approve it. Budgets, orders, stock and claims are never
posted to the ledger by this module: it reads the ledger for comparison and tells you which journal to post."""
import csv
import io
from datetime import date
from decimal import Decimal

from .assets import AssetsMixin, ASSET_CATEGORIES, CONDITIONS, MAINT_KINDS
from .base import CATEGORIES, FACILITY_TYPES, OWNERSHIP, P_CLAIMS, P_STAFFING, ZERO, day, safe, s2, sha, txt
from .claims import METHODS, PAYER_KINDS, REJECTION_CODES, SERVICE_CATEGORIES
from .errors import HealthError, HealthNotFoundError, HealthStateError
from .inventory import ADJ_KINDS, ITEM_CATEGORIES

CONFIDENTIAL = "CONFIDENTIAL - ASAVEXA health facility performance report. For the organisation named and people it has authorised. Contains no patient information."
LIMITATIONS = [
    "This module is financial and administrative. It holds no patient names, identifiers, diagnoses, prescriptions or clinical records, and it must not be used to store them.",
    "It does not post to the accounting ledger. Budgets, orders, invoices, stock write-offs, claim payments and asset disposals are recorded here; the matching journals are posted in the ledger by an authorised person. Ledger figures shown are read-only and organisation-wide.",
    "Spending counts verified supplier invoices, approved staffing summaries and completed maintenance bought outside a purchase order. Other expenditure is not seen until it is recorded here.",
    "Stock is costed at a moving weighted average. Quantities are only as accurate as the receipts, issues and physical counts people record.",
    "Claims reconciliation compares recorded payments with the amount a person types in from the payer's statement. There is no connection to any insurer or national scheme.",
    "No depreciation is calculated. Staffing costs are department totals entered or imported by an authorised person, not payroll calculations.",
    "Approval records that a second person reviewed the item. It is not an audit opinion, regulatory certification or legal compliance. Patient-identifiable data must not be added until a documented lawful basis, impact assessment and privacy review exist.",
]


class HealthService(AssetsMixin):
    def options(self, org, actor) -> dict:
        return {"categories": CATEGORIES, "facility_types": FACILITY_TYPES, "ownership": OWNERSHIP, "item_categories": ITEM_CATEGORIES, "adjustment_kinds": ADJ_KINDS, "payer_kinds": PAYER_KINDS, "service_categories": SERVICE_CATEGORIES,
                "rejection_codes": REJECTION_CODES, "payment_methods": METHODS, "asset_categories": ASSET_CATEGORIES, "conditions": CONDITIONS, "maintenance_kinds": MAINT_KINDS, "facilities": self.list_facilities(org, actor), "limitations": LIMITATIONS}

    # ------------------------------------------------------------------ dashboard
    def _metric(self, label, value, formula, source, drill, state="OK", note=""):
        return {"label": label, "value": value, "state": state, "formula": formula, "source": source, "drill": drill, "note": note}

    def dashboard(self, org, fid, actor, start=None, end=None) -> dict:
        f = self._fac(org, fid, actor); t = self.today()
        s = start or date(t.year, 1, 1); e = end or date(t.year, 12, 31)
        if e < s: raise HealthError("The end date cannot be before the start date.")
        claims = bool(self.can(org, actor, P_CLAIMS)); m = {}
        bud = next((b for b in sorted(self._of("hc_budget", org, fid), key=lambda b: b["ref"], reverse=True) if b["status"] == "APPROVED" and b["period_start"] <= e.isoformat() and s.isoformat() <= b["period_end"]), None)
        if bud:
            x = self._exec(org, fid, bud["id"])["totals"]; spent, com, bt = Decimal(x["total_spent"]), Decimal(x["committed"]) + Decimal(x["unbudgeted_committed"]), Decimal(x["budget"])
            src = f"Approved budget {bud['ref']} (version {bud['version']}), {bud['period_start']} to {bud['period_end']}"
            m["budget_total"] = self._metric("Total approved budget", s2(bt), "Sum of approved budget lines plus approved transfers", src, "budgets")
            m["spent"] = self._metric("Actual expenditure", s2(spent), "Verified supplier invoices (net of credits) + approved staffing + completed maintenance outside purchase orders, including spending on lines that have no budget", "Procurement, staffing and maintenance records in the budget period", "budgets")
            m["committed"] = self._metric("Committed (open orders)", s2(com), "Open purchase orders less what has been invoiced and verified", "Purchase orders", "procurement")
            m["utilisation"] = self._metric("Budget utilisation", None if bt == 0 else s2(spent * 100 / bt), "Actual expenditure / total approved budget x 100", src, "budgets", state="OK" if bt else "UNAVAILABLE", note="percent")
            m["available"] = self._metric("Available budget", s2(bt - spent - com), "Budget - actual expenditure - committed", src, "budgets")
        else:
            for k, l in (("budget_total", "Total approved budget"), ("spent", "Actual expenditure"), ("committed", "Committed (open orders)"), ("utilisation", "Budget utilisation"), ("available", "Available budget")):
                m[k] = self._metric(l, None, "", "No approved budget covers this period", "budgets", state="UNAVAILABLE", note="Approve a budget for this period to see this figure.")
        rv = self.revenue_summary(org, fid, actor, s, e); m["receipts"] = self._metric("Receipts collected (net of refunds)", rv["net_total"], "Receipts dated in the period less approved refunds", "Revenue receipts", "revenue")
        pay = self.payables_ageing(org, fid, actor); m["payables"] = self._metric("Outstanding supplier payables", pay["totals"]["total"], "Recorded supplier invoices not yet paid, net of credit notes", "Supplier invoices", "procurement")
        if claims:
            cs = self.claims_summary(org, fid, actor, s, e); ar = self.receivables_ageing(org, fid, actor)
            m["claim_payments"] = self._metric("Claim payments received", cs["payments_received"], "Payer payments recorded on claims in the period", "Claims", "claims")
            m["receivables"] = self._metric("Outstanding receivables", ar["totals"]["total"], "Claimed less paid less written off, on submitted and part-paid claims", "Claims", "claims")
            for k, l, v in (("claims_submitted", "Claims submitted", cs["submitted"]), ("claims_pending", "Claims pending", cs["pending"]), ("claims_rejected", "Claims rejected", cs["rejected"]), ("claims_paid", "Claims paid in full", cs["paid"])):
                m[k] = self._metric(l, v, "Count of claims by status", "Claims", "claims")
            m["unreconciled"] = self._metric("Payer reconciliations with a difference", sum(1 for r in self._of("hc_recon", org, fid) if r["status"] == "DIFFERENCE"), "Reconciliations whose difference is not yet explained", "Payer reconciliations", "claims")
        else:
            for k, l in (("claim_payments", "Claim payments received"), ("receivables", "Outstanding receivables"), ("claims_submitted", "Claims submitted"), ("claims_pending", "Claims pending"), ("claims_rejected", "Claims rejected"), ("claims_paid", "Claims paid in full"), ("unreconciled", "Payer reconciliations with a difference")):
                m[k] = self._metric(l, None, "", "Claims", "claims", state="RESTRICTED", note="You do not have access to claims information.")
        st = self.stock_levels(org, fid, actor); al = st["alerts"]
        m["inventory_value"] = self._metric("Inventory stock value", st["total_value"], "Sum of quantity on hand x average cost", "Stock movements", "inventory")
        m["low_stock"] = self._metric("Items at or below reorder level", len(al["low_stock"]), "On hand <= reorder level (only where a level is set)", "Stock movements", "inventory")
        m["expiry"] = self._metric("Lots expired or expiring soon", len(al["expired"]) + len(al["expiring_soon"]), f"Lots with stock that expired, or expire within {al['expiry_window_days']} days", "Stock lots", "inventory", note=f"{len(al['expired'])} already expired")
        m["maintenance_due"] = self._metric("Equipment maintenance due", len(self.maintenance_due(org, fid, actor)), "Open requests and scheduled maintenance due within 30 days", "Assets and maintenance", "assets")
        m["awaiting_approval"] = self._metric("Purchase requests awaiting approval", sum(1 for r in self._of("hc_req", org, fid) if r["status"] == "SUBMITTED") + sum(1 for p in self._of("hc_po", org, fid) if p["status"] == "PENDING_APPROVAL"), "Submitted requisitions + purchase orders not yet approved", "Procurement", "procurement")
        ex = self.procurement_exceptions(org, fid, actor); m["exceptions"] = self._metric("Open procurement exceptions", len(ex["budget_exceptions"]) + len(ex["invoice_mismatches"]), "Orders approved over budget + invoices that did not match the goods received", "Procurement", "procurement",
                                                                                                    note="Findings raised in the Controls workspace are not linked here.")
        return {"facility": f["name"], "facility_ref": f["ref"], "currency": f["currency"], "period_start": s.isoformat(), "period_end": e.isoformat(), "generated_at": self.now().isoformat(), "metrics": m}

    # ------------------------------------------------------------------ reports
    def _snapshot(self, org, fid, actor, s, e) -> dict:
        d = self.dashboard(org, fid, actor, s, e); claims = bool(self.can(org, actor, P_CLAIMS))
        bud = next((b for b in sorted(self._of("hc_budget", org, fid), key=lambda b: b["ref"], reverse=True) if b["status"] == "APPROVED" and b["period_start"] <= e.isoformat() and s.isoformat() <= b["period_end"]), None)
        st = self.stock_levels(org, fid, actor)
        snap = {"generated_at": self.now().isoformat(), "period_start": s.isoformat(), "period_end": e.isoformat(), "dashboard": d, "budget": self._exec(org, fid, bud["id"]) if bud else None, "payables": self.payables_ageing(org, fid, actor), "revenue": self.revenue_summary(org, fid, actor, s, e),
                "inventory": {"total_value": st["total_value"], "alerts": st["alerts"], "costing": st["costing"]}, "maintenance_due": self.maintenance_due(org, fid, actor), "exceptions": self.procurement_exceptions(org, fid, actor), "limitations": LIMITATIONS, "includes_claims": claims}
        if claims: snap["claims"] = self.claims_summary(org, fid, actor, s, e); snap["receivables"] = self.receivables_ageing(org, fid, actor)
        return snap

    def create_report(self, org, fid, d, actor) -> dict:
        self._fac(org, fid, actor, active=True); s, e = day(d.get("period_start"), "Start date"), day(d.get("period_end"), "End date")
        if e < s: raise HealthError("The end date cannot be before the start date.")
        r = self._new(org, fid, ref=self._ref(org, "R", fid), title=txt(d.get("title"), "Title", 3, 200), period_start=s.isoformat(), period_end=e.isoformat(), status="DRAFT", version=0, snapshot=None, fingerprint=None, confidentiality=CONFIDENTIAL, created_by=actor, history=[])
        self._hist(r, actor, "CREATED"); self._put("hc_report", org, r); self.log("HC_REPORT_CREATED", actor, r["id"], org, r["ref"]); return r

    def submit_report(self, org, rid, actor) -> dict:
        r = self._rec("hc_report", org, rid, "Report", actor, True); self._writable(org, r, actor)
        if r["status"] not in ("DRAFT", "REJECTED"): raise HealthStateError("Only a draft or sent-back report can be submitted.")
        snap = self._snapshot(org, r["facility_id"], actor, day(r["period_start"], "s"), day(r["period_end"], "e"))
        r.update(status="SUBMITTED", snapshot=snap, fingerprint=sha(snap), version=r["version"] + 1, submitted_by=actor); self._hist(r, actor, "SUBMITTED", f"v{r['version']}"); self._put("hc_report", org, r); self.log("HC_REPORT_SUBMITTED", actor, rid, org, f"{r['ref']} v{r['version']}"); return self._redact(org, r, actor)

    def decide_report(self, org, rid, ok, note, actor) -> dict:
        r = self._rec("hc_report", org, rid, "Report", actor, True); self._writable(org, r, actor)
        if r["status"] != "SUBMITTED": raise HealthStateError("Only a submitted report can be decided.")
        self._two(actor, r["submitted_by"], "submitted this report"); n = txt(note, "A note saying why", 0 if ok else 3, 500, required=not ok)
        r.update(status="APPROVED" if ok else "REJECTED", decided_by=actor, decision_note=n); self._hist(r, actor, r["status"], n); self._put("hc_report", org, r); self.log("HC_REPORT_" + r["status"], actor, rid, org, r["ref"]); return self._redact(org, r, actor)

    def _redact(self, org, r, actor) -> dict:
        v = dict(r)
        if r.get("snapshot") and r["snapshot"].get("includes_claims") and not self.can(org, actor, P_CLAIMS):
            snap = {k: x for k, x in r["snapshot"].items() if k not in ("claims", "receivables")}; snap["dashboard"] = dict(snap["dashboard"], metrics={k: x for k, x in snap["dashboard"]["metrics"].items() if not (x["source"] == "Claims" or k == "unreconciled" or k == "claim_payments")})
            snap["claims_restricted"] = True; v["snapshot"] = snap
        return v

    def get_report(self, org, rid, actor) -> dict: return self._redact(org, self._rec("hc_report", org, rid, "Report", actor), actor)

    def list_reports(self, org, fid, actor) -> list:
        self._fac(org, fid, actor); return [{k: v for k, v in r.items() if k != "snapshot"} for r in sorted(self._of("hc_report", org, fid), key=lambda r: r["ref"])]

    def export_csv(self, org, rid, actor) -> dict:
        r = self._rec("hc_report", org, rid, "Report", actor)
        if r["status"] != "APPROVED": raise HealthStateError("Only an approved report can be exported.")
        if sha(r["snapshot"]) != r["fingerprint"]: raise HealthStateError("The frozen report no longer matches its fingerprint; it cannot be exported.")
        v = self._redact(org, r, actor); s = v["snapshot"]; fac = self._raw("hc_facility", org, r["facility_id"], "Facility"); buf = io.StringIO(); w = csv.writer(buf, lineterminator="\n"); w.writerow([CONFIDENTIAL])
        for k, x in [("Facility", fac["name"]), ("Report", r["title"]), ("Period", f"{r['period_start']} to {r['period_end']}"), ("Currency", fac["currency"]), ("Version", r["version"]), ("Prepared by (user id)", r["submitted_by"]), ("Approved by (user id)", r["decided_by"]),
                     ("Generated at", s["generated_at"]), ("Fingerprint (SHA-256)", r["fingerprint"])]: w.writerow([k, safe(x)])
        w.writerow([]); w.writerow(["KEY FIGURES"]); w.writerow(["Measure", "Value", "State", "Formula", "Source"])
        for m in s["dashboard"]["metrics"].values(): w.writerow([safe(m["label"]), "" if m["value"] is None else m["value"], m["state"], safe(m["formula"]), safe(m["source"])])
        if s.get("budget"):
            w.writerow([]); w.writerow(["BUDGET VERSUS ACTUAL", s["budget"]["ref"]]); w.writerow(["Department", "Category", "Budget", "Spent", "Committed", "Available", "Used %"])
            for x in s["budget"]["rows"]: w.writerow([safe(x["dept"]), x["category"], x["budget"], x["spent"], x["committed"], x["available"], x["used_pct"] or ""])
        w.writerow([]); w.writerow(["SUPPLIER PAYABLES AGEING"]); w.writerow(["Supplier", "0-30", "31-60", "61-90", "over 90", "Total"])
        for x in s["payables"]["rows"]: w.writerow([safe(x["supplier"]), x["0-30"], x["31-60"], x["61-90"], x["over 90"], x["total"]])
        w.writerow([]); w.writerow(["REVENUE BY SERVICE CATEGORY"]); w.writerow(["Category", "Collected", "Refunded", "Net"])
        for x in s["revenue"]["rows"]: w.writerow([x["category"], x["collected"], x["refunded"], x["net"]])
        if s.get("receivables"):
            w.writerow([]); w.writerow(["PAYER RECEIVABLES AGEING"]); w.writerow(["Payer", "0-30", "31-60", "61-90", "over 90", "Total"])
            for x in s["receivables"]["rows"]: w.writerow([safe(x["payer"]), x["0-30"], x["31-60"], x["61-90"], x["over 90"], x["total"]])
        w.writerow([]); w.writerow(["INVENTORY"]); w.writerow(["Stock value", s["inventory"]["total_value"]]); w.writerow(["Low stock items", len(s["inventory"]["alerts"]["low_stock"])]); w.writerow(["Expired lots", len(s["inventory"]["alerts"]["expired"])]); w.writerow(["Expiring soon", len(s["inventory"]["alerts"]["expiring_soon"])])
        w.writerow([]); w.writerow(["LIMITATIONS"]); [w.writerow([x]) for x in s["limitations"]]
        self.log("HC_REPORT_EXPORTED", actor, rid, org, r["ref"])
        return {"content": buf.getvalue(), "content_type": "text/csv; charset=utf-8", "filename": f"{r['ref']}-facility-report.csv"}
