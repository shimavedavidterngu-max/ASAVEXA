"""Payers, fee schedule, revenue receipts and claims administration.

Privacy: a claim is identified only by a random internal reference (and, if the payer uses one, an external claim reference). It holds no patient name, identifier,
date of birth, diagnosis or treatment. Service is recorded as a billing category and a month. Claims figures need the claims permission, which operational and
platform roles do not hold by default."""
import secrets
import re
from datetime import date
from decimal import Decimal

from .base import P_APPROVE, P_CLAIMS, ZERO, day, enum, month, money, norm, q2, s2, txt, whole
from .errors import HealthError, HealthNotFoundError, HealthStateError
from .inventory import InventoryMixin
from .procure import AGE_BUCKETS

SERVICE_CATEGORIES = ["OUTPATIENT_SERVICES", "INPATIENT_SERVICES", "MATERNITY_SERVICES", "PROCEDURES", "DIAGNOSTIC_SERVICES", "OTHER_SERVICES"]
PAYER_KINDS = ["INSURER", "GOVERNMENT_SCHEME", "SPONSOR_OR_EMPLOYER", "OTHER"]
REJECTION_CODES = ["INCOMPLETE_DOCUMENTATION", "NOT_COVERED", "DUPLICATE_CLAIM", "LATE_SUBMISSION", "TARIFF_DISPUTE", "OTHER"]
METHODS = ["CASH", "BANK_TRANSFER", "CARD", "MOBILE_MONEY", "OTHER"]
OPEN_CLAIM = ("SUBMITTED", "PARTIALLY_PAID")
REF_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{2,39}$")


class ClaimsMixin(InventoryMixin):
    # ------------------------------------------------------------------ payers and fees (not patient data)
    def create_payer(self, org, fid, d, actor) -> dict:
        self._fac(org, fid, actor, active=True); name = txt(d.get("name"), "Payer name", 2, 200)
        for p in self._of("hc_payer", org, fid):
            if p["name"].strip().lower() == name.lower(): raise HealthError(f"Payer {p['name']} already exists ({p['ref']}).")
        r = self._new(org, fid, ref=self._ref(org, "PAY", fid), name=name, kind=enum(d.get("kind"), PAYER_KINDS, "Payer type"), status="ACTIVE", created_by=actor)
        self._put("hc_payer", org, r); self.log("HC_PAYER_ADDED", actor, r["id"], org, r["ref"]); return r

    def list_payers(self, org, fid, actor) -> list:
        self._fac(org, fid, actor); return sorted(self._of("hc_payer", org, fid), key=lambda p: p["ref"])

    def create_fee(self, org, fid, d, actor) -> dict:
        self._fac(org, fid, actor, active=True); name = txt(d.get("name"), "Billing item", 2, 200); eff = day(d.get("effective_from"), "Effective from")
        for x in self._of("hc_fee", org, fid):
            if x["name"].lower() == name.lower() and x["effective_from"] == eff.isoformat() and x["status"] == "ACTIVE": raise HealthError(f"{name} already has a price from {eff.isoformat()}.")
        r = self._new(org, fid, ref=self._ref(org, "FEE", fid), name=name, service_category=enum(d.get("service_category"), SERVICE_CATEGORIES, "Service category"), price=s2(money(d.get("price"), "Price")), effective_from=eff.isoformat(), status="ACTIVE", created_by=actor)
        self._put("hc_fee", org, r); self.log("HC_FEE_ADDED", actor, r["id"], org, f"{r['ref']} {r['price']}"); return r

    def retire_fee(self, org, feeid, note, actor) -> dict:
        r = self._rec("hc_fee", org, feeid, "Billing item", actor, True); self._writable(org, r, actor); r["status"] = "RETIRED"; r["retire_note"] = txt(note, "Reason", 3, 300)
        self._put("hc_fee", org, r); self.log("HC_FEE_RETIRED", actor, feeid, org, r["ref"]); return r

    def list_fees(self, org, fid, actor) -> list:
        self._fac(org, fid, actor); return sorted(self._of("hc_fee", org, fid), key=lambda x: (x["name"], x["effective_from"]))

    # ------------------------------------------------------------------ revenue receipts
    def record_receipt(self, org, fid, d, actor) -> dict:
        self._fac(org, fid, actor, active=True); fee = None
        if d.get("fee_id"):
            fee = self._rec("hc_fee", org, d["fee_id"], "Billing item", actor)
            if fee["facility_id"] != fid: raise HealthError("That billing item is not at this facility.")
        cat = enum(d.get("service_category") or (fee or {}).get("service_category"), SERVICE_CATEGORIES, "Service category"); on = day(d.get("date"), "Date")
        if on > self.today(): raise HealthError("A receipt cannot be dated in the future.")
        r = self._new(org, fid, ref="RCT-" + secrets.token_hex(4).upper(), service_category=cat, fee_id=fee["id"] if fee else None, amount=s2(money(d.get("amount"), "Amount")), date=on.isoformat(), method=enum(d.get("method"), METHODS, "Payment method"),
                      refunded="0.00", refunds=[], recorded_by=actor, history=[])
        self._hist(r, actor, "RECORDED"); self._put("hc_rcpt", org, r); self.log("HC_RECEIPT", actor, r["id"], org, f"{r['ref']} {r['amount']}"); return r

    def request_refund(self, org, rid, amount, reason, actor) -> dict:
        r = self._rec("hc_rcpt", org, rid, "Receipt", actor, True); self._writable(org, r, actor); amt = money(amount, "Refund amount")
        pending = sum((Decimal(x["amount"]) for x in r["refunds"] if x["status"] == "PENDING"), ZERO)
        if Decimal(r["refunded"]) + pending + amt > Decimal(r["amount"]): raise HealthError(f"Refunds cannot exceed the {r['amount']} received (already refunded or waiting: {s2(Decimal(r['refunded']) + pending)}).")
        x = {"id": f"R{len(r['refunds']) + 1}", "amount": s2(amt), "reason": txt(reason, "Reason", 10, 300), "status": "PENDING", "requested_by": actor}
        r["refunds"].append(x); self._hist(r, actor, "REFUND_REQUESTED", x["amount"]); self._put("hc_rcpt", org, r); self.log("HC_REFUND_REQUESTED", actor, rid, org, f"{r['ref']} {x['amount']}"); return x

    def decide_refund(self, org, rid, xid, ok, note, actor) -> dict:
        r = self._rec("hc_rcpt", org, rid, "Receipt", actor, True); self._writable(org, r, actor); x = next((y for y in r["refunds"] if y["id"] == xid), None)
        if x is None: raise HealthNotFoundError("Refund not found.")
        if x["status"] != "PENDING": raise HealthStateError("That refund has already been decided.")
        self._two(actor, x["requested_by"], "asked for this refund")
        n = txt(note, "A note saying why", 0 if ok else 3, 300, required=not ok)
        if ok:
            if Decimal(r["refunded"]) + Decimal(x["amount"]) > Decimal(r["amount"]): raise HealthError("The refund would exceed the amount received.")
            r["refunded"] = s2(Decimal(r["refunded"]) + Decimal(x["amount"]))
        x.update(status="APPROVED" if ok else "REJECTED", decided_by=actor, decision_note=n); self._hist(r, actor, "REFUND_" + x["status"], x["amount"]); self._put("hc_rcpt", org, r); self.log("HC_REFUND_" + x["status"], actor, rid, org, r["ref"]); return x

    def list_receipts_revenue(self, org, fid, actor) -> list:
        self._fac(org, fid, actor); return sorted(self._of("hc_rcpt", org, fid), key=lambda r: (r["date"], r["ref"]), reverse=True)

    def revenue_summary(self, org, fid, actor, start=None, end=None) -> dict:
        self._fac(org, fid, actor); rows = {}
        for r in self._of("hc_rcpt", org, fid):
            if (start and r["date"] < start.isoformat()) or (end and r["date"] > end.isoformat()): continue
            x = rows.setdefault(r["service_category"], {"collected": ZERO, "refunded": ZERO}); x["collected"] += Decimal(r["amount"]); x["refunded"] += Decimal(r["refunded"])
        out = [{"category": k, "collected": s2(v["collected"]), "refunded": s2(v["refunded"]), "net": s2(v["collected"] - v["refunded"])} for k, v in sorted(rows.items())]
        return {"rows": out, "net_total": s2(sum((Decimal(x["net"]) for x in out), ZERO)), "basis": "Receipts by date received, less approved refunds. Insurer and scheme payments on claims are reported under claims."}

    # ------------------------------------------------------------------ claims (claims permission)
    def _claim(self, org, cid, actor, for_update=False) -> dict:
        self._need(org, actor, P_CLAIMS, "see or change claims"); return self._rec("hc_claim", org, cid, "Claim", actor, for_update)

    def create_claim(self, org, fid, d, actor) -> dict:
        self._need(org, actor, P_CLAIMS, "work on claims"); self._fac(org, fid, actor, active=True)
        payer = self._rec("hc_payer", org, d.get("payer_id"), "Payer", actor)
        if payer["facility_id"] != fid or payer["status"] != "ACTIVE": raise HealthError("Choose an active payer registered at this facility.")
        ext = txt(d.get("external_ref"), "Payer claim reference", 0, 40, required=False)
        if ext:
            if not REF_OK.match(ext): raise HealthError("The payer claim reference may use letters, numbers and . _ / - only (3 to 40 characters). Never enter a person's name.")
            for c in self._of("hc_claim", org, fid):
                if c["payer_id"] == payer["id"] and c.get("external_ref") and norm(c["external_ref"]) == norm(ext): raise HealthError(f"This payer reference was already used on claim {c['ref']}. Duplicate claims are not accepted.")
        r = self._new(org, fid, ref="CLM-" + secrets.token_hex(4).upper(), payer_id=payer["id"], payer=payer["name"], external_ref=ext or None, service_category=enum(d.get("service_category"), SERVICE_CATEGORIES, "Service category"),
                      service_month=month(d.get("service_month"), "Service month"), amount=s2(money(d.get("amount"), "Claim amount")), status="DRAFT", payments=[], resubmissions=0, rejection=None, written_off="0.00", writeoff=None, submitted_on=None, created_by=actor, history=[])
        self._hist(r, actor, "CREATED"); self._put("hc_claim", org, r); self.log("HC_CLAIM_CREATED", actor, r["id"], org, f"{r['ref']} {r['amount']}"); return self._cv(r)

    def submit_claim(self, org, cid, actor) -> dict:
        r = self._claim(org, cid, actor, True); self._writable(org, r, actor)
        if r["status"] != "DRAFT": raise HealthStateError(f"{r['ref']} is {r['status'].lower().replace('_', ' ')}; only a draft claim can be submitted. A second submission is refused.")
        r.update(status="SUBMITTED", submitted_on=self.today().isoformat()); self._hist(r, actor, "SUBMITTED"); self._put("hc_claim", org, r); self.log("HC_CLAIM_SUBMITTED", actor, cid, org, r["ref"]); return self._cv(r)

    def reject_claim(self, org, cid, code, note, actor) -> dict:
        r = self._claim(org, cid, actor, True); self._writable(org, r, actor)
        if r["status"] != "SUBMITTED": raise HealthStateError("Only a submitted claim with nothing paid can be marked rejected.")
        r.update(status="REJECTED", rejection={"code": enum(code, REJECTION_CODES, "Rejection reason"), "note": txt(note, "Note (no patient names)", 0, 100, required=False), "at": self.now().isoformat()})
        self._hist(r, actor, "REJECTED", r["rejection"]["code"]); self._put("hc_claim", org, r); self.log("HC_CLAIM_REJECTED", actor, cid, org, f"{r['ref']} {r['rejection']['code']}"); return self._cv(r)

    def resubmit_claim(self, org, cid, new_amount, note, actor) -> dict:
        r = self._claim(org, cid, actor, True); self._writable(org, r, actor)
        if r["status"] != "REJECTED": raise HealthStateError("Only a rejected claim can be resubmitted.")
        if r["resubmissions"] >= 3: raise HealthStateError("This claim has been resubmitted three times. Write it off or escalate it instead.")
        if new_amount not in (None, ""): r["amount"] = s2(money(new_amount, "Corrected amount"))
        r.update(status="SUBMITTED", resubmissions=r["resubmissions"] + 1, submitted_on=self.today().isoformat(), rejection=None); self._hist(r, actor, "RESUBMITTED", txt(note, "What was corrected", 3, 200)); self._put("hc_claim", org, r); self.log("HC_CLAIM_RESUBMITTED", actor, cid, org, r["ref"]); return self._cv(r)

    @staticmethod
    def _paid(c) -> Decimal: return sum((Decimal(p["amount"]) for p in c["payments"]), ZERO)
    def _outstanding(self, c) -> Decimal: return Decimal(c["amount"]) - self._paid(c) - Decimal(c["written_off"])

    def pay_claim(self, org, cid, d, actor) -> dict:
        r = self._claim(org, cid, actor, True); self._writable(org, r, actor)
        if r["status"] not in OPEN_CLAIM: raise HealthStateError(f"A payment can only be recorded against a submitted or part-paid claim ({r['ref']} is {r['status'].lower().replace('_', ' ')}).")
        amt = money(d.get("amount"), "Payment amount"); ref = txt(d.get("payment_ref"), "Payer payment reference", 3, 60); on = day(d.get("date"), "Payment date")
        if on > self.today(): raise HealthError("A payment cannot be dated in the future.")
        for c in self._of("hc_claim", org, r["facility_id"]):
            if c["payer_id"] == r["payer_id"] and any(norm(p["ref"]) == norm(ref) and c["id"] != cid for p in c["payments"]): raise HealthError(f"Payment reference {ref} was already allocated to claim {c['ref']}.")
        if any(norm(p["ref"]) == norm(ref) for p in r["payments"]): raise HealthError(f"Payment reference {ref} was already recorded on this claim. A repeated payment is refused.")
        if amt > self._outstanding(r): raise HealthError(f"The payment of {s2(amt)} is more than the {s2(self._outstanding(r))} still outstanding on {r['ref']}.")
        r["payments"].append({"id": f"P{len(r['payments']) + 1}", "amount": s2(amt), "ref": ref, "date": on.isoformat(), "by": actor, "evidence": self._evidence(org, d.get("evidence_ids"))})
        r["status"] = "PAID" if self._outstanding(r) == 0 else "PARTIALLY_PAID"; self._hist(r, actor, "PAYMENT", s2(amt)); self._put("hc_claim", org, r); self.log("HC_CLAIM_PAYMENT", actor, cid, org, f"{r['ref']} {s2(amt)}"); return self._cv(r)

    def request_writeoff(self, org, cid, reason, actor) -> dict:
        r = self._claim(org, cid, actor, True); self._writable(org, r, actor)
        if r["status"] not in OPEN_CLAIM + ("REJECTED",): raise HealthStateError("Only an unpaid or part-paid claim can be written off.")
        if r["writeoff"] and r["writeoff"]["status"] == "PENDING": raise HealthStateError("A write-off is already waiting for a decision.")
        r["writeoff"] = {"status": "PENDING", "reason": txt(reason, "Reason", 10, 300), "amount": s2(self._outstanding(r)), "requested_by": actor}; self._hist(r, actor, "WRITEOFF_REQUESTED", r["writeoff"]["amount"]); self._put("hc_claim", org, r); self.log("HC_WRITEOFF_REQUESTED", actor, cid, org, r["ref"]); return self._cv(r)

    def decide_writeoff(self, org, cid, ok, note, actor) -> dict:
        r = self._claim(org, cid, actor, True); self._writable(org, r, actor); w = r["writeoff"]
        if not w or w["status"] != "PENDING": raise HealthStateError("No write-off is waiting for a decision.")
        self._two(actor, w["requested_by"], "asked for this write-off"); n = txt(note, "A note saying why", 0 if ok else 3, 300, required=not ok)
        w.update(status="APPROVED" if ok else "REJECTED", decided_by=actor, decision_note=n)
        if ok: r["written_off"] = s2(Decimal(r["written_off"]) + Decimal(w["amount"])); r["status"] = "WRITTEN_OFF"
        self._hist(r, actor, "WRITEOFF_" + w["status"], w["amount"]); self._put("hc_claim", org, r); self.log("HC_WRITEOFF_" + w["status"], actor, cid, org, r["ref"]); return self._cv(r)

    def _cv(self, c) -> dict: return dict(c, paid=s2(self._paid(c)), outstanding=s2(self._outstanding(c)))

    def list_claims(self, org, fid, actor, status=None) -> list:
        self._need(org, actor, P_CLAIMS, "see claims"); self._fac(org, fid, actor)
        return [self._cv(c) for c in sorted(self._of("hc_claim", org, fid), key=lambda c: c["ref"]) if not status or c["status"] == status]

    def get_claim(self, org, cid, actor) -> dict:
        return self._cv(self._claim(org, cid, actor))

    def receivables_ageing(self, org, fid, actor, as_of=None) -> dict:
        self._need(org, actor, P_CLAIMS, "see claims"); self._fac(org, fid, actor); t = as_of or self.today(); rows, tot = {}, {b[0]: ZERO for b in AGE_BUCKETS}
        for c in self._of("hc_claim", org, fid):
            if c["status"] not in OPEN_CLAIM: continue
            out = self._outstanding(c)
            if out <= 0: continue
            age = max(0, (t - date.fromisoformat(c["submitted_on"])).days); b = next(n for n, lo, hi in AGE_BUCKETS if lo <= age <= hi)
            r = rows.setdefault(c["payer_id"], {"payer": c["payer"], **{n: ZERO for n, _, _ in AGE_BUCKETS}, "total": ZERO}); r[b] += out; r["total"] += out; tot[b] += out
        return {"as_of": t.isoformat(), "rows": [{k: (s2(v) if isinstance(v, Decimal) else v) for k, v in r.items()} for r in sorted(rows.values(), key=lambda r: r["payer"])],
                "totals": {**{k: s2(v) for k, v in tot.items()}, "total": s2(sum(tot.values(), ZERO))}, "basis": "Outstanding on submitted and part-paid claims, aged from the (latest) submission date. Rejected claims are listed separately."}

    def claims_summary(self, org, fid, actor, start=None, end=None) -> dict:
        self._need(org, actor, P_CLAIMS, "see claims"); self._fac(org, fid, actor); cs = self._of("hc_claim", org, fid)
        def n(*st): return [c for c in cs if c["status"] in st]
        paid_in = sum((Decimal(p["amount"]) for c in cs for p in c["payments"] if (not start or p["date"] >= start.isoformat()) and (not end or p["date"] <= end.isoformat())), ZERO)
        return {"submitted": len(n("SUBMITTED", "PARTIALLY_PAID", "PAID", "REJECTED", "WRITTEN_OFF")), "pending": len(n("SUBMITTED", "PARTIALLY_PAID")), "rejected": len(n("REJECTED")), "paid": len(n("PAID")), "draft": len(n("DRAFT")),
                "outstanding": s2(sum((self._outstanding(c) for c in n("SUBMITTED", "PARTIALLY_PAID")), ZERO)), "payments_received": s2(paid_in)}

    def payer_reconciliation(self, org, fid, payer_id, d, actor) -> dict:
        self._need(org, actor, P_CLAIMS, "reconcile claims"); self._fac(org, fid, actor, active=True); payer = self._rec("hc_payer", org, payer_id, "Payer", actor)
        s, e = day(d.get("start"), "Start"), day(d.get("end"), "End")
        if e < s: raise HealthError("The end date cannot be before the start date.")
        statement = money(d.get("statement_amount"), "Amount on the payer's statement", positive=False)
        ours = sum((Decimal(p["amount"]) for c in self._of("hc_claim", org, fid) if c["payer_id"] == payer["id"] for p in c["payments"] if s.isoformat() <= p["date"] <= e.isoformat()), ZERO)
        diff = statement - ours
        r = self._new(org, fid, ref=self._ref(org, "REC", fid), payer_id=payer["id"], payer=payer["name"], start=s.isoformat(), end=e.isoformat(), statement_amount=s2(statement), recorded_amount=s2(ours), difference=s2(diff),
                      status="RECONCILED" if diff == 0 else "DIFFERENCE", note=txt(d.get("note"), "Note", 0, 300, required=False), by=actor, at=self.now().isoformat())
        self._put("hc_recon", org, r); self.log("HC_RECON", actor, r["id"], org, f"{r['ref']} difference {r['difference']}"); return r

    def resolve_reconciliation(self, org, rid, note, actor) -> dict:
        self._need(org, actor, P_CLAIMS, "reconcile claims"); r = self._rec("hc_recon", org, rid, "Reconciliation", actor, True)
        if r["status"] != "DIFFERENCE": raise HealthStateError("Only a reconciliation with a difference needs resolving.")
        r.update(status="RESOLVED", resolution=txt(note, "How the difference was explained", 10, 300), resolved_by=actor); self._put("hc_recon", org, r); self.log("HC_RECON_RESOLVED", actor, rid, org, r["ref"]); return r

    def list_reconciliations(self, org, fid, actor) -> list:
        self._need(org, actor, P_CLAIMS, "see claims"); self._fac(org, fid, actor); return sorted(self._of("hc_recon", org, fid), key=lambda r: r["ref"])
