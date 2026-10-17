"""Pension and fiduciary (records and evidence): a register of pension schemes with contributions, funding valuations, a fiduciary calendar and a conflict-of-interest register, each recorded by one person and confirmed by a different person.

Records (shared document store, per organisation): pen_scheme, pen_setting.

Principles enforced here
  * A scheme has a name, a reference code, a currency, a type, the first contribution month, the day of the month contributions fall due (1 to 28) and a description. It is proposed by one person and approved or rejected by a different person. Only an approved scheme takes records.
  * A contribution (a month, an employer amount, an employee amount and the date paid) is recorded by one person and confirmed or rejected by a different person. A month's contribution is due on the due day of the following month; one paid after that is flagged late. Months that are due and have no confirmed contribution are listed as missing. Totals are exact and only cover confirmed contributions.
  * A valuation (an "as of" date, the assets and the liabilities, both typed from the actuary's and the custodian's reports) is recorded by one person and confirmed or rejected by a different person. The funding ratio and the surplus or deficit are plain exact arithmetic on those typed numbers. ASAVEXA values nothing.
  * An obligation on the fiduciary calendar (a title and a due date) is marked done by one person and confirmed by a different person; a rejection sends it back to open. Overdue and due-soon flags use your own settings.
  * A conflict-of-interest declaration (a person reference code, the date declared and its nature) is recorded by one person and reviewed by a different person.
  * ASAVEXA holds no member data, calculates no benefit or contribution rate and applies no pension or trust law. Person references are codes, never names.
Nothing is edited after a decision or deleted. Every step is audited by reference number only.
"""
import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import Callable, List

from ..wscommon import WsMixin, amount, code, currency, dt, fr, refnum, round2, txt, utc, whole
from .errors import PensionError, PensionForbiddenError, PensionNotFoundError, PensionStateError

DEFAULTS = {"funding_floor_pct": 90, "valuation_stale_days": 365, "due_soon_days": 30}
TYPES = ["DEFINED_BENEFIT", "DEFINED_CONTRIBUTION", "HYBRID", "OTHER"]
KINDS = {"contributions": "contribution", "valuations": "valuation", "obligations": "obligation", "conflicts": "conflict"}
MAX_SCHEMES = 200
MAX_ROWS = 1000
MAX_MONTHS = 240
LIMITATIONS = [
    "ASAVEXA keeps a register and works out plain arithmetic. It holds no member data, calculates no benefit or contribution rate, values nothing and applies no pension or trust law.",
    "Contributions, assets and liabilities are typed by people from the reports they hold. A different person confirming them is a review of what was typed, not a check against bank, custodian or actuary records.",
    "The funding ratio is assets divided by liabilities as typed. Liabilities depend on actuarial assumptions that ASAVEXA does not see; a ratio is not a statutory funding test.",
    "Due dates and the late flag use the due day you set for the scheme. Real rules about when contributions are due, and what happens when they are late, may differ.",
    "The calendar and the conflict register are records of what people typed. They do not tell you which duties apply to you. Keep names and personal details out of every field; use codes.",
]


class PensionService(WsMixin):
    SETTING_KIND = "pen_setting"
    DEFAULTS = DEFAULTS
    ERR, NF, ST, FB = PensionError, PensionNotFoundError, PensionStateError, PensionForbiddenError

    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ settings
    def pen_get_setting(self, org) -> dict:
        s = self._settings(org); f, v, d = s["funding_floor_pct"], s["valuation_stale_days"], s["due_soon_days"]
        return {"funding_floor_pct": f, "valuation_stale_days": v, "due_soon_days": d, "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"A scheme is flagged when its latest confirmed funding ratio is below {f}%, when that valuation is older than {v} day(s), and an open obligation is flagged as due soon when it falls due within {d} day(s). These are your own settings, not rules."}

    def pen_set_setting(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        if d.get("funding_floor_pct") is not None: s["funding_floor_pct"] = whole(PensionError, d["funding_floor_pct"], "The funding floor in percent", 1, 300)
        if d.get("valuation_stale_days") is not None: s["valuation_stale_days"] = whole(PensionError, d["valuation_stale_days"], "The days before a valuation is stale", 1, 1500)
        if d.get("due_soon_days") is not None: s["due_soon_days"] = whole(PensionError, d["due_soon_days"], "The days that count as due soon", 1, 365)
        s.update(updated_by=actor, updated_at=self.now().isoformat()); self._put("pen_setting", org, s)
        self.log("PENSION_SETTING_SET", actor, "settings", org, "settings")
        return self.pen_get_setting(org)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _period(v, name):
        t = str(v).strip() if isinstance(v, str) else ""
        m = re.fullmatch(r"([0-9]{4})-([0-9]{2})", t)
        if not m or not 2000 <= int(m.group(1)) <= 2100 or not 1 <= int(m.group(2)) <= 12: raise PensionError(f"{name} must be a real month written YYYY-MM.")
        return int(m.group(1)), int(m.group(2))

    @staticmethod
    def _due(y, m, due_day) -> date:
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return date(y, m, due_day)

    def _months(self, x):
        """Every month from the start month up to the current month."""
        y, m = self._period(x["start_period"], "The start month"); today = self.today(); out = []
        while (y, m) <= (today.year, today.month) and len(out) < MAX_MONTHS:
            out.append((y, m)); y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return out

    def _view(self, x) -> dict:
        v = {k: x[k] for k in x if k != "org"}
        for k in KINDS: v[k] = [dict(r) for r in x[k]]
        s = self._settings(x["org"]); today = self.today(); cur = x["currency"]
        v.update(currency=cur, employer_total="0.00", employee_total="0.00", total_contributions="0.00", late_contributions=0, missing_periods=[], latest_valuation=None, funding_ratio_pct=None, position=None, position_amount=None,
                 below_floor=False, valuation_stale=False, overdue_obligations=0, due_soon_obligations=0, pending=0)
        for r in v["contributions"]:
            r["late"] = date.fromisoformat(r["paid_on"]) > date.fromisoformat(r["due_date"])
            r["total"] = str((Decimal(r["employer_amount"]) + Decimal(r["employee_amount"])).quantize(Decimal("0.01")))
        for r in v["obligations"]:
            r["overdue"] = r["status"] == "OPEN" and date.fromisoformat(r["due_date"]) < today
            r["due_soon"] = r["status"] == "OPEN" and not r["overdue"] and (date.fromisoformat(r["due_date"]) - today).days <= s["due_soon_days"]
            r["done_late"] = bool(r["completed_on"]) and date.fromisoformat(r["completed_on"]) > date.fromisoformat(r["due_date"])
        v["pending"] = sum(1 for k in KINDS for r in v[k] if r["status"] in ("PROPOSED", "DONE"))
        if x["status"] != "APPROVED" and x["status"] != "CLOSED": return v
        conf = [r for r in v["contributions"] if r["status"] == "CONFIRMED"]
        e = sum((Decimal(r["employer_amount"]) for r in conf), Decimal("0")); p = sum((Decimal(r["employee_amount"]) for r in conf), Decimal("0"))
        v.update(employer_total=str(e.quantize(Decimal("0.01"))), employee_total=str(p.quantize(Decimal("0.01"))), total_contributions=str((e + p).quantize(Decimal("0.01"))), late_contributions=sum(1 for r in conf if r["late"]))
        have = {r["period"] for r in v["contributions"] if r["status"] in ("PROPOSED", "CONFIRMED")}
        v["missing_periods"] = [f"{y:04d}-{m:02d}" for (y, m) in self._months(x) if self._due(y, m, x["due_day"]) < today and f"{y:04d}-{m:02d}" not in have]
        vals = [r for r in v["valuations"] if r["status"] == "CONFIRMED"]
        if vals:
            last = max(vals, key=lambda r: (r["as_of"], r["no"])); a, l = fr(last["assets"]), fr(last["liabilities"]); ratio = a / l * 100
            diff = a - l; v.update(latest_valuation=last, funding_ratio_pct=str(round2(ratio)), position="SURPLUS" if diff > 0 else ("DEFICIT" if diff < 0 else "BALANCED"), position_amount=str(round2(abs(diff))),
                                   below_floor=ratio < s["funding_floor_pct"], valuation_stale=(today - date.fromisoformat(last["as_of"])).days > s["valuation_stale_days"])
        v["overdue_obligations"] = sum(1 for r in v["obligations"] if r["overdue"]); v["due_soon_obligations"] = sum(1 for r in v["obligations"] if r["due_soon"])
        return v

    def _summary(self, x) -> dict:
        v = self._view(x)
        for k in KINDS: v[k] = []
        v["history"] = []
        return v

    # ------------------------------------------------------------------ schemes
    def pen_add_scheme(self, org, d, actor) -> dict:
        E = PensionError
        name = txt(E, d.get("name"), "The scheme name", 3, 150); sref = txt(E, d.get("scheme_ref"), "The scheme reference", 2, 40); cur = currency(E, d.get("currency"))
        stype = code(E, d.get("scheme_type"), "The scheme type", TYPES); sp = self._period(d.get("start_period"), "The first contribution month")
        today = self.today()
        if (sp[0], sp[1]) > (today.year, today.month): raise E("The first contribution month cannot be in the future.")
        if (today.year - sp[0]) * 12 + today.month - sp[1] >= MAX_MONTHS: raise E("The first contribution month can be at most twenty years ago.")
        dd = whole(E, d.get("due_day"), "The due day of the month", 1, 28); desc = txt(E, d.get("description"), "The description", 10, 1000)
        if len(self._all("pen_scheme", org)) >= MAX_SCHEMES: raise PensionStateError(f"The register can hold at most {MAX_SCHEMES} schemes.")
        x = {"id": uuid.uuid4().hex, "org": org, "ref": None, "name": name, "scheme_ref": sref, "currency": cur, "scheme_type": stype, "start_period": f"{sp[0]:04d}-{sp[1]:02d}", "due_day": dd, "description": desc,
             "status": "PROPOSED", "proposed_by": actor, "proposed_at": self.now().isoformat(), "decided_by": None, "decided_on": None, "decision_note": None, "closed_by": None, "closed_on": None, "close_note": None,
             "contributions": [], "valuations": [], "obligations": [], "conflicts": [], "history": []}
        x["ref"] = self._ref(org, "PS"); self._hist(x, actor, "PROPOSED")
        self._put("pen_scheme", org, x); self.log("PENSION_SCHEME_PROPOSED", actor, x["id"], org, x["ref"])
        return self._view(x)

    def pen_list_schemes(self, org, status=None) -> List[dict]:
        return [self._summary(x) for x in sorted(self._all("pen_scheme", org), key=refnum) if not status or x["status"] == status]

    def pen_get_scheme(self, org, sid) -> dict: return self._view(self._get("pen_scheme", org, sid, "Scheme"))

    def _proposed(self, org, sid) -> dict:
        x = self._get("pen_scheme", org, sid, "Scheme", for_update=True)
        if x["status"] != "PROPOSED": raise PensionStateError("Only a proposed scheme can be decided.")
        return x

    def pen_approve_scheme(self, org, sid, d, actor) -> dict:
        x = self._proposed(org, sid); self._two(actor, x["proposed_by"], "proposed this scheme")
        note = txt(PensionError, d.get("note"), "An approval note", 10, 1000, required=False)
        x.update(status="APPROVED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=note or None); self._hist(x, actor, "APPROVED", note)
        self._put("pen_scheme", org, x); self.log("PENSION_SCHEME_APPROVED", actor, sid, org, x["ref"])
        return self._view(x)

    def pen_reject_scheme(self, org, sid, reason, actor) -> dict:
        x = self._proposed(org, sid); self._two(actor, x["proposed_by"], "proposed this scheme")
        reason = txt(PensionError, reason, "A reason", 10, 1000); x.update(status="REJECTED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=reason); self._hist(x, actor, "REJECTED", reason)
        self._put("pen_scheme", org, x); self.log("PENSION_SCHEME_REJECTED", actor, sid, org, x["ref"])
        return self._view(x)

    def _approved(self, org, sid) -> dict:
        x = self._get("pen_scheme", org, sid, "Scheme", for_update=True)
        if x["status"] != "APPROVED": raise PensionStateError("Only an approved scheme can be changed this way.")
        return x

    def pen_close_scheme(self, org, sid, reason, actor) -> dict:
        x = self._approved(org, sid)
        if any(r["status"] in ("PROPOSED", "DONE") for k in KINDS for r in x[k]): raise PensionStateError("Decide every item waiting for a decision before closing the scheme.")
        reason = txt(PensionError, reason, "A reason", 10, 1000); x.update(status="CLOSED", closed_by=actor, closed_on=self.today().isoformat(), close_note=reason); self._hist(x, actor, "CLOSED", reason)
        self._put("pen_scheme", org, x); self.log("PENSION_SCHEME_CLOSED", actor, sid, org, x["ref"])
        return self._view(x)

    # ------------------------------------------------------------------ records
    def _append(self, x, kind, row, actor, org, label):
        if len(x[kind]) >= MAX_ROWS: raise PensionStateError(f"A scheme can have at most {MAX_ROWS} {kind}.")
        row["no"] = len(x[kind]) + 1; x[kind].append(row); self._hist(x, actor, f"{label}_RECORDED"); self._put("pen_scheme", org, x)
        self.log(f"PENSION_{label}_RECORDED", actor, x["id"], org, f"{x['ref']} #{row['no']}")
        return self._view(x)

    def pen_add_contribution(self, org, sid, d, actor) -> dict:
        E = PensionError; x = self._approved(org, sid); y, m = self._period(d.get("period"), "The month"); per = f"{y:04d}-{m:02d}"; today = self.today()
        if per < x["start_period"]: raise E("The month cannot be before the scheme's first contribution month.")
        if (y, m) > (today.year, today.month): raise E("The month cannot be in the future.")
        emp = amount(E, d.get("employer_amount"), "The employer amount", zero_ok=True, digits=13); ee = amount(E, d.get("employee_amount"), "The employee amount", zero_ok=True, digits=13)
        if emp == 0 and ee == 0: raise E("At least one of the employer and employee amounts must be more than zero.")
        paid = dt(E, d.get("paid_on"), "The date paid")
        if paid > today + timedelta(days=1): raise E("The date paid cannot be in the future.")
        if paid.year < 2000: raise E("The date paid must be in this century.")
        if any(r["period"] == per and r["status"] in ("PROPOSED", "CONFIRMED") for r in x["contributions"]): raise PensionStateError("There is already a contribution, or one waiting for a decision, for that month.")
        row = {"period": per, "employer_amount": str(emp), "employee_amount": str(ee), "paid_on": paid.isoformat(), "due_date": self._due(y, m, x["due_day"]).isoformat(), "status": "PROPOSED", "proposed_by": actor, "decided_by": None, "decided_on": None, "decision_note": None}
        return self._append(x, "contributions", row, actor, org, "CONTRIBUTION")

    def pen_add_valuation(self, org, sid, d, actor) -> dict:
        E = PensionError; x = self._approved(org, sid); as_of = dt(E, d.get("as_of"), "The valuation date"); today = self.today()
        if as_of > today + timedelta(days=1): raise E("The valuation date cannot be in the future.")
        if as_of.year < 2000: raise E("The valuation date must be in this century.")
        a = amount(E, d.get("assets"), "The assets", zero_ok=True, digits=15); l = amount(E, d.get("liabilities"), "The liabilities", digits=15); src = txt(E, d.get("source_note"), "The source note", 10, 500)
        if any(r["as_of"] == as_of.isoformat() and r["status"] in ("PROPOSED", "CONFIRMED") for r in x["valuations"]): raise PensionStateError("There is already a valuation, or one waiting for a decision, for that date.")
        row = {"as_of": as_of.isoformat(), "assets": str(a), "liabilities": str(l), "source_note": src, "status": "PROPOSED", "proposed_by": actor, "decided_by": None, "decided_on": None, "decision_note": None}
        return self._append(x, "valuations", row, actor, org, "VALUATION")

    def pen_add_obligation(self, org, sid, d, actor) -> dict:
        E = PensionError; x = self._approved(org, sid); title = txt(E, d.get("title"), "The title", 3, 200); due = dt(E, d.get("due_date"), "The due date")
        if due.year < 2000 or due.year > 2100: raise E("The due date must be between 2000 and 2100.")
        if any(r["title"].lower() == title.lower() and r["due_date"] == due.isoformat() and r["status"] != "CONFIRMED" for r in x["obligations"]): raise PensionStateError("That obligation is already on the calendar for that date.")
        row = {"title": title, "due_date": due.isoformat(), "status": "OPEN", "proposed_by": actor, "completed_on": None, "completed_by": None, "completion_note": None, "decided_by": None, "decided_on": None, "decision_note": None}
        return self._append(x, "obligations", row, actor, org, "OBLIGATION")

    def pen_complete_obligation(self, org, sid, no, d, actor) -> dict:
        E = PensionError; x = self._approved(org, sid); r, n = self._row(x, no, "obligation", "obligations")
        if r["status"] != "OPEN": raise PensionStateError("Only an open obligation can be marked as done.")
        on = dt(E, d.get("completed_on"), "The date done")
        if on > self.today() + timedelta(days=1): raise E("The date done cannot be in the future.")
        note = txt(E, d.get("note"), "A note", 10, 500)
        r.update(status="DONE", completed_on=on.isoformat(), completed_by=actor, completion_note=note); self._hist(x, actor, "OBLIGATION_DONE", note)
        self._put("pen_scheme", org, x); self.log("PENSION_OBLIGATION_DONE", actor, sid, org, f"{x['ref']} #{n}")
        return self._view(x)

    def pen_add_conflict(self, org, sid, d, actor) -> dict:
        E = PensionError; x = self._approved(org, sid); who = txt(E, d.get("person_ref"), "The person reference", 2, 40); on = dt(E, d.get("declared_on"), "The date declared")
        if on > self.today() + timedelta(days=1): raise E("The date declared cannot be in the future.")
        if on.year < 2000: raise E("The date declared must be in this century.")
        nature = txt(E, d.get("nature"), "The nature of the interest", 10, 1000)
        row = {"person_ref": who, "declared_on": on.isoformat(), "nature": nature, "status": "PROPOSED", "proposed_by": actor, "decided_by": None, "decided_on": None, "decision_note": None}
        return self._append(x, "conflicts", row, actor, org, "CONFLICT")

    def pen_decide(self, org, sid, kind, no, ok, note, actor) -> dict:
        """Confirm (ok) or reject a contribution, valuation, completed obligation or conflict declaration; never the person who recorded it."""
        if not isinstance(kind, str) or kind not in KINDS: raise PensionError("That kind of record does not exist.")
        label = KINDS[kind]; x = self._get("pen_scheme", org, sid, "Scheme", for_update=True)
        if x["status"] != "APPROVED": raise PensionStateError("The scheme is not open.")
        r, n = self._row(x, no, label, kind); waiting = "DONE" if kind == "obligations" else "PROPOSED"
        if r["status"] != waiting: raise PensionStateError(f"That {label} is not waiting for a decision.")
        by, what = (r["completed_by"], "marked this obligation as done") if kind == "obligations" else (r["proposed_by"], f"recorded this {label}")
        self._two(actor, by, what)
        if ok:
            text = txt(PensionError, note.get("note") if isinstance(note, dict) else note, "A confirmation note", 10, 1000, required=False)
            r.update(status="CONFIRMED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=text or None); ev = f"{label.upper()}_CONFIRMED"
        else:
            text = txt(PensionError, note, "A reason", 10, 1000)
            r.update(status="OPEN" if kind == "obligations" else "REJECTED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=text); ev = f"{label.upper()}_REJECTED"
            if kind == "obligations": r.update(completed_on=None, completed_by=None, completion_note=None)
        self._hist(x, actor, ev, text); self._put("pen_scheme", org, x); self.log(f"PENSION_{ev}", actor, sid, org, f"{x['ref']} #{n}")
        return self._view(x)

    # ------------------------------------------------------------------ overview
    def pen_overview(self, org) -> dict:
        vs = [self._view(x) for x in sorted(self._all("pen_scheme", org), key=refnum)]; ap = [v for v in vs if v["status"] == "APPROVED"]; att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("SCHEMES_TO_APPROVE", sum(1 for v in vs if v["status"] == "PROPOSED"), "scheme(s) are waiting for a different person to decide them.")
        add("ITEMS_TO_DECIDE", sum(v["pending"] for v in ap), "recorded item(s) are waiting for a different person to decide them.")
        add("MISSING_CONTRIBUTIONS", sum(len(v["missing_periods"]) for v in ap), "month(s) are past their due date with no contribution recorded.")
        add("LATE_CONTRIBUTIONS", sum(v["late_contributions"] for v in ap), "confirmed contribution(s) were paid after their due date.")
        add("BELOW_FUNDING_FLOOR", sum(1 for v in ap if v["below_floor"]), "scheme(s) have a latest confirmed funding ratio below your floor.")
        add("VALUATIONS_STALE", sum(1 for v in ap if v["valuation_stale"]), "scheme(s) have a latest confirmed valuation older than your limit.")
        add("NO_VALUATION", sum(1 for v in ap if v["latest_valuation"] is None), "approved scheme(s) have no confirmed valuation yet.")
        add("OBLIGATIONS_OVERDUE", sum(v["overdue_obligations"] for v in ap), "calendar obligation(s) are open and past their due date.")
        add("OBLIGATIONS_DUE_SOON", sum(v["due_soon_obligations"] for v in ap), "calendar obligation(s) fall due soon.")
        counts = {s.lower(): sum(1 for v in vs if v["status"] == s) for s in ("PROPOSED", "APPROVED", "REJECTED", "CLOSED")}
        totals = {}
        for v in ap:
            t = totals.setdefault(v["currency"], {"currency": v["currency"], "schemes": 0, "total_contributions": Decimal("0")}); t["schemes"] += 1; t["total_contributions"] += Decimal(v["total_contributions"])
        by_cur = [{**t, "total_contributions": str(t["total_contributions"].quantize(Decimal("0.01")))} for t in sorted(totals.values(), key=lambda t: t["currency"])]
        return {"counts": counts, "attention": att, "by_currency": by_cur, "setting": self.pen_get_setting(org), "limitations": LIMITATIONS}

    def pen_options(self, org) -> dict: return {"scheme_types": TYPES, "limitations": LIMITATIONS}
