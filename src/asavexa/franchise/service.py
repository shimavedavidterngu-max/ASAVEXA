"""Franchise and multi-location (records and evidence): locations with a royalty rate, monthly sales reports and royalty payments, each recorded by one person and confirmed by a different person.

Records (shared document store, per organisation): fch_location, fch_setting.

Principles enforced here
  * A location (a franchised outlet or a branch) has a name, a reference code, a currency, a royalty rate in percent (up to two decimals, more than zero and at most 100), the day of the month sales reports fall due (1 to 28), the first reporting month and a description. It is proposed by one person and approved or rejected by a different person. Only an approved location takes records.
  * A monthly sales report (a month, the gross sales and the date submitted) is recorded by one person and confirmed or rejected by a different person. It is due on the due day of the following month; one submitted after that plus your grace days is flagged late. One live report per month. Months past due with no report are listed as missing.
  * The royalty for a report is its gross sales times the location's rate, rounded to two decimals half away from zero, exactly. The royalty due is the sum over confirmed reports.
  * A royalty payment (an amount, the date and a note) is recorded by one person and confirmed or rejected by a different person. The balance is royalty due less confirmed payments (a negative balance means overpaid). The overdue amount is the royalty of confirmed reports whose due date plus grace days has passed, less confirmed payments, never below zero.
  * ASAVEXA reads no franchise agreement, collects no money, audits no sales and applies no franchise law. Currencies are never added together. Location references are codes, never names.
Nothing is edited after a decision or deleted. Every step is audited by reference number only.
"""
import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Callable, List

from ..wscommon import WsMixin, amount, currency, dt, fr, refnum, round2, txt, utc, whole
from .errors import FranchiseError, FranchiseForbiddenError, FranchiseNotFoundError, FranchiseStateError

DEFAULTS = {"grace_days": 0}
KINDS = {"reports": "report", "payments": "payment"}
MAX_LOCATIONS = 1000
MAX_ROWS = 600
MAX_MONTHS = 240
LIMITATIONS = [
    "ASAVEXA keeps a register and works out plain arithmetic. It reads no franchise agreement, collects no money, audits no sales and applies no franchise or consumer law.",
    "The royalty rate, sales and payments are typed by people. A different person confirming them is a review of what was typed, not a check against till records, bank statements or the agreement.",
    "Royalty is gross sales times the rate, exactly, rounded to two decimals per report. Real agreements may use tiers, minimums, fees, deductions or different periods; none of those are applied.",
    "Due dates use the due day and grace days you set. Interest, penalties, set-off between locations and taxes are not calculated. Currencies are never added together.",
    "Location references are codes people choose. Keep names and personal details out of every field.",
]


class FranchiseService(WsMixin):
    SETTING_KIND = "fch_setting"
    DEFAULTS = DEFAULTS
    ERR, NF, ST, FB = FranchiseError, FranchiseNotFoundError, FranchiseStateError, FranchiseForbiddenError

    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ settings
    def fch_get_setting(self, org) -> dict:
        s = self._settings(org); g = s["grace_days"]
        return {"grace_days": g, "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"A report is late, and a month is missing, only after {g} day(s) have passed since its due date. Royalty counts as overdue on the same basis. This is your own setting, not a rule."}

    def fch_set_setting(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        if d.get("grace_days") is not None: s["grace_days"] = whole(FranchiseError, d["grace_days"], "The grace period in days", 0, 60)
        s.update(updated_by=actor, updated_at=self.now().isoformat()); self._put("fch_setting", org, s)
        self.log("FRANCHISE_SETTING_SET", actor, "settings", org, "settings")
        return self.fch_get_setting(org)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _period(v, name):
        t = str(v).strip() if isinstance(v, str) else ""
        m = re.fullmatch(r"([0-9]{4})-([0-9]{2})", t)
        if not m or not 2000 <= int(m.group(1)) <= 2100 or not 1 <= int(m.group(2)) <= 12: raise FranchiseError(f"{name} must be a real month written YYYY-MM.")
        return int(m.group(1)), int(m.group(2))

    @staticmethod
    def _due(y, m, due_day) -> date:
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return date(y, m, due_day)

    @staticmethod
    def _royalty(sales, rate) -> Decimal: return round2(fr(sales) * fr(rate) / 100)

    def _months(self, x):
        y, m = self._period(x["start_period"], "The start month"); today = self.today(); out = []
        while (y, m) <= (today.year, today.month) and len(out) < MAX_MONTHS:
            out.append((y, m)); y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return out

    def _view(self, x) -> dict:
        v = {k: x[k] for k in x if k != "org"}
        for k in KINDS: v[k] = [dict(r) for r in x[k]]
        grace = timedelta(days=self._settings(x["org"])["grace_days"]); today = self.today(); rate = x["royalty_rate_pct"]
        v.update(sales_total="0.00", royalty_due="0.00", paid_total="0.00", balance="0.00", balance_state="SETTLED", overdue_amount="0.00", late_reports=0, missing_periods=[], pending=0)
        for r in v["reports"]:
            r["royalty"] = str(self._royalty(r["gross_sales"], rate)); r["late"] = date.fromisoformat(r["submitted_on"]) > date.fromisoformat(r["due_date"]) + grace
        v["pending"] = sum(1 for k in KINDS for r in v[k] if r["status"] == "PROPOSED")
        if x["status"] not in ("APPROVED", "CLOSED"): return v
        conf = [r for r in v["reports"] if r["status"] == "CONFIRMED"]; paid = sum((Decimal(r["amount"]) for r in v["payments"] if r["status"] == "CONFIRMED"), Decimal("0"))
        sales = sum((Decimal(r["gross_sales"]) for r in conf), Decimal("0")); due = sum((Decimal(r["royalty"]) for r in conf), Decimal("0"))
        past = sum((Decimal(r["royalty"]) for r in conf if date.fromisoformat(r["due_date"]) + grace < today), Decimal("0")); bal = due - paid; q = Decimal("0.01")
        v.update(sales_total=str(sales.quantize(q)), royalty_due=str(due.quantize(q)), paid_total=str(paid.quantize(q)), balance=str(bal.quantize(q)), balance_state="OWED" if bal > 0 else ("OVERPAID" if bal < 0 else "SETTLED"),
                 overdue_amount=str(max(Decimal("0"), past - paid).quantize(q)), late_reports=sum(1 for r in conf if r["late"]))
        have = {r["period"] for r in v["reports"] if r["status"] in ("PROPOSED", "CONFIRMED")}
        v["missing_periods"] = [f"{y:04d}-{m:02d}" for (y, m) in self._months(x) if self._due(y, m, x["due_day"]) + grace < today and f"{y:04d}-{m:02d}" not in have]
        return v

    def _summary(self, x) -> dict:
        v = self._view(x)
        for k in KINDS: v[k] = []
        v["history"] = []
        return v

    # ------------------------------------------------------------------ locations
    def fch_add_location(self, org, d, actor) -> dict:
        E = FranchiseError
        name = txt(E, d.get("name"), "The location name", 3, 150); lref = txt(E, d.get("location_ref"), "The location reference", 2, 40); cur = currency(E, d.get("currency"))
        rate = amount(E, d.get("royalty_rate_pct"), "The royalty rate in percent", dp=2, digits=3)
        if rate > 100: raise E("The royalty rate cannot be more than 100 percent.")
        sp = self._period(d.get("start_period"), "The first reporting month"); today = self.today()
        if (sp[0], sp[1]) > (today.year, today.month): raise E("The first reporting month cannot be in the future.")
        if (today.year - sp[0]) * 12 + today.month - sp[1] >= MAX_MONTHS: raise E("The first reporting month can be at most twenty years ago.")
        dd = whole(E, d.get("due_day"), "The due day of the month", 1, 28); desc = txt(E, d.get("description"), "The description", 10, 1000)
        if len(self._all("fch_location", org)) >= MAX_LOCATIONS: raise FranchiseStateError(f"The register can hold at most {MAX_LOCATIONS} locations.")
        x = {"id": uuid.uuid4().hex, "org": org, "ref": None, "name": name, "location_ref": lref, "currency": cur, "royalty_rate_pct": str(rate), "start_period": f"{sp[0]:04d}-{sp[1]:02d}", "due_day": dd, "description": desc,
             "status": "PROPOSED", "proposed_by": actor, "proposed_at": self.now().isoformat(), "decided_by": None, "decided_on": None, "decision_note": None, "closed_by": None, "closed_on": None, "close_note": None,
             "reports": [], "payments": [], "history": []}
        x["ref"] = self._ref(org, "FL"); self._hist(x, actor, "PROPOSED")
        self._put("fch_location", org, x); self.log("FRANCHISE_LOCATION_PROPOSED", actor, x["id"], org, x["ref"])
        return self._view(x)

    def fch_list_locations(self, org, status=None) -> List[dict]:
        return [self._summary(x) for x in sorted(self._all("fch_location", org), key=refnum) if not status or x["status"] == status]

    def fch_get_location(self, org, lid) -> dict: return self._view(self._get("fch_location", org, lid, "Location"))

    def _proposed(self, org, lid) -> dict:
        x = self._get("fch_location", org, lid, "Location", for_update=True)
        if x["status"] != "PROPOSED": raise FranchiseStateError("Only a proposed location can be decided.")
        return x

    def fch_approve_location(self, org, lid, d, actor) -> dict:
        x = self._proposed(org, lid); self._two(actor, x["proposed_by"], "proposed this location")
        note = txt(FranchiseError, d.get("note"), "An approval note", 10, 1000, required=False)
        x.update(status="APPROVED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=note or None); self._hist(x, actor, "APPROVED", note)
        self._put("fch_location", org, x); self.log("FRANCHISE_LOCATION_APPROVED", actor, lid, org, x["ref"])
        return self._view(x)

    def fch_reject_location(self, org, lid, reason, actor) -> dict:
        x = self._proposed(org, lid); self._two(actor, x["proposed_by"], "proposed this location")
        reason = txt(FranchiseError, reason, "A reason", 10, 1000); x.update(status="REJECTED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=reason); self._hist(x, actor, "REJECTED", reason)
        self._put("fch_location", org, x); self.log("FRANCHISE_LOCATION_REJECTED", actor, lid, org, x["ref"])
        return self._view(x)

    def _approved(self, org, lid) -> dict:
        x = self._get("fch_location", org, lid, "Location", for_update=True)
        if x["status"] != "APPROVED": raise FranchiseStateError("Only an approved location can be changed this way.")
        return x

    def fch_close_location(self, org, lid, reason, actor) -> dict:
        x = self._approved(org, lid)
        if any(r["status"] == "PROPOSED" for k in KINDS for r in x[k]): raise FranchiseStateError("Decide every item waiting for a decision before closing the location.")
        reason = txt(FranchiseError, reason, "A reason", 10, 1000); x.update(status="CLOSED", closed_by=actor, closed_on=self.today().isoformat(), close_note=reason); self._hist(x, actor, "CLOSED", reason)
        self._put("fch_location", org, x); self.log("FRANCHISE_LOCATION_CLOSED", actor, lid, org, x["ref"])
        return self._view(x)

    # ------------------------------------------------------------------ records
    def _append(self, x, kind, row, actor, org, label):
        if len(x[kind]) >= MAX_ROWS: raise FranchiseStateError(f"A location can have at most {MAX_ROWS} {kind}.")
        row["no"] = len(x[kind]) + 1; x[kind].append(row); self._hist(x, actor, f"{label}_RECORDED"); self._put("fch_location", org, x)
        self.log(f"FRANCHISE_{label}_RECORDED", actor, x["id"], org, f"{x['ref']} #{row['no']}")
        return self._view(x)

    def fch_add_report(self, org, lid, d, actor) -> dict:
        E = FranchiseError; x = self._approved(org, lid); y, m = self._period(d.get("period"), "The month"); per = f"{y:04d}-{m:02d}"; today = self.today()
        if per < x["start_period"]: raise E("The month cannot be before the location's first reporting month.")
        if (y, m) > (today.year, today.month): raise E("The month cannot be in the future.")
        sales = amount(E, d.get("gross_sales"), "The gross sales", zero_ok=True, digits=13); sub = dt(E, d.get("submitted_on"), "The date submitted")
        if sub > today + timedelta(days=1): raise E("The date submitted cannot be in the future.")
        if sub.year < 2000: raise E("The date submitted must be in this century.")
        if any(r["period"] == per and r["status"] in ("PROPOSED", "CONFIRMED") for r in x["reports"]): raise FranchiseStateError("There is already a report, or one waiting for a decision, for that month.")
        row = {"period": per, "gross_sales": str(sales), "submitted_on": sub.isoformat(), "due_date": self._due(y, m, x["due_day"]).isoformat(), "status": "PROPOSED", "proposed_by": actor, "decided_by": None, "decided_on": None, "decision_note": None}
        return self._append(x, "reports", row, actor, org, "REPORT")

    def fch_add_payment(self, org, lid, d, actor) -> dict:
        E = FranchiseError; x = self._approved(org, lid); amt = amount(E, d.get("amount"), "The amount", digits=13); on = dt(E, d.get("paid_on"), "The date paid"); today = self.today()
        if on > today + timedelta(days=1): raise E("The date paid cannot be in the future.")
        if on.year < 2000: raise E("The date paid must be in this century.")
        note = txt(E, d.get("note"), "The note", 3, 300)
        row = {"amount": str(amt), "paid_on": on.isoformat(), "note": note, "status": "PROPOSED", "proposed_by": actor, "decided_by": None, "decided_on": None, "decision_note": None}
        return self._append(x, "payments", row, actor, org, "PAYMENT")

    def fch_decide(self, org, lid, kind, no, ok, note, actor) -> dict:
        """Confirm (ok) or reject a sales report or a payment; never the person who recorded it."""
        if not isinstance(kind, str) or kind not in KINDS: raise FranchiseError("That kind of record does not exist.")
        label = KINDS[kind]; x = self._get("fch_location", org, lid, "Location", for_update=True)
        if x["status"] != "APPROVED": raise FranchiseStateError("The location is not open.")
        r, n = self._row(x, no, label, kind)
        if r["status"] != "PROPOSED": raise FranchiseStateError(f"That {label} has already been decided.")
        self._two(actor, r["proposed_by"], f"recorded this {label}")
        if ok:
            text = txt(FranchiseError, note.get("note") if isinstance(note, dict) else note, "A confirmation note", 10, 1000, required=False)
            r.update(status="CONFIRMED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=text or None); ev = f"{label.upper()}_CONFIRMED"
        else:
            text = txt(FranchiseError, note, "A reason", 10, 1000)
            r.update(status="REJECTED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=text); ev = f"{label.upper()}_REJECTED"
        self._hist(x, actor, ev, text); self._put("fch_location", org, x); self.log(f"FRANCHISE_{ev}", actor, lid, org, f"{x['ref']} #{n}")
        return self._view(x)

    # ------------------------------------------------------------------ overview
    def fch_overview(self, org) -> dict:
        vs = [self._view(x) for x in sorted(self._all("fch_location", org), key=refnum)]; ap = [v for v in vs if v["status"] == "APPROVED"]; att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("LOCATIONS_TO_APPROVE", sum(1 for v in vs if v["status"] == "PROPOSED"), "location(s) are waiting for a different person to decide them.")
        add("ITEMS_TO_DECIDE", sum(v["pending"] for v in ap), "recorded item(s) are waiting for a different person to decide them.")
        add("MISSING_REPORTS", sum(len(v["missing_periods"]) for v in ap), "month(s) are past their due date with no sales report recorded.")
        add("LATE_REPORTS", sum(v["late_reports"] for v in ap), "confirmed sales report(s) were submitted after their due date.")
        add("ROYALTY_OVERDUE", sum(1 for v in ap if Decimal(v["overdue_amount"]) > 0), "location(s) have royalty past its due date that confirmed payments do not cover.")
        add("OVERPAID", sum(1 for v in ap if v["balance_state"] == "OVERPAID"), "location(s) have confirmed payments above the royalty due.")
        counts = {s.lower(): sum(1 for v in vs if v["status"] == s) for s in ("PROPOSED", "APPROVED", "REJECTED", "CLOSED")}
        roll = {}
        for v in vs:
            if v["status"] not in ("APPROVED", "CLOSED"): continue
            t = roll.setdefault(v["currency"], {"currency": v["currency"], "locations": 0, "sales_total": Decimal("0"), "royalty_due": Decimal("0"), "paid_total": Decimal("0"), "balance": Decimal("0")}); t["locations"] += 1
            for k in ("sales_total", "royalty_due", "paid_total", "balance"): t[k] += Decimal(v[k])
        q = Decimal("0.01"); by_cur = [{**t, **{k: str(t[k].quantize(q)) for k in ("sales_total", "royalty_due", "paid_total", "balance")}} for t in sorted(roll.values(), key=lambda t: t["currency"])]
        return {"counts": counts, "attention": att, "by_currency": by_cur, "setting": self.fch_get_setting(org), "limitations": LIMITATIONS}

    def fch_options(self, org) -> dict: return {"limitations": LIMITATIONS}
