"""Payroll and workforce cost (records and evidence): payroll runs worked out from typed pay lines, reviewed by a different person.

Records (shared document store, per organisation): pw_run, pw_setting.

Principles enforced here
  * A payroll run is a set of pay lines a person types in: a staff reference (never a name), a department, base pay, allowances, deductions (each with a label) and employer contributions. ASAVEXA adds them up exactly: gross = base + allowances; net = gross - deductions; cost to the employer = gross + employer contributions.
  * ASAVEXA calculates no tax, pension, social security or any statutory amount, pays nobody and moves no money. Every figure is typed. It holds no names, bank details or national identifiers.
  * A run is prepared, submitted, and approved or returned by a person other than the one who submitted it. An approved run is final. Amounts are kept per currency and never added across currencies.
Nothing is edited after approval or deleted; a line is marked removed with a reason. Every step is audited by reference number only.
"""
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, List

from .errors import PayrollError, PayrollForbiddenError, PayrollNotFoundError, PayrollStateError

DEFAULTS = {"review_limit": "0.00"}
CENT = Decimal("0.01")
MAX_LINES = 500
MAX_DEDUCTIONS = 8
LIMITATIONS = [
    "ASAVEXA adds up the figures people type in. It calculates no tax, pension, social security or other statutory amount, checks no pay against any law or contract, pays nobody and moves no money.",
    "A staff reference is a code a person types. ASAVEXA holds no names, bank details or national identifiers, and cannot tell whether a reference belongs to a real person or whether anyone is paid twice under two references.",
    "Gross is base pay plus allowances; net is gross less the deductions typed; cost to the employer is gross plus the employer contributions typed. Nothing else is included.",
    "The same staff reference in two runs for overlapping periods in the same currency is flagged for a person to look at; it is not blocked, because it can be right (for example a correction).",
    "Amounts in different currencies are never added together. An approved run is final; a correction is a new run.",
]


def _utc(): return datetime.now(timezone.utc)


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v)))
    v = " ".join("".join(c if c >= " " and c != "\x7f" else " " for c in v).split())
    if required and len(v) < lo:
        raise PayrollError(f"{name} is required (at least {lo} characters).")
    if v and len(v) < lo:
        raise PayrollError(f"{name} needs at least {lo} characters.")
    if len(v) > hi:
        raise PayrollError(f"{name} is too long (limit {hi} characters).")
    return v


def _date(v, name) -> date:
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", str(v).strip()): raise ValueError
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise PayrollError(f"{name} must be a real date written YYYY-MM-DD.")


def _amount(v, name, zero_ok=False) -> Decimal:
    """Text or a whole number: ASCII digits, at most two decimals, never a float, commas only as thousands separators."""
    if isinstance(v, bool) or isinstance(v, float) or v is None:
        raise PayrollError(f"{name} must be an amount such as 1500.00.")
    t = str(v).strip()
    if "," in t and not re.fullmatch(r"[0-9]{1,3}(,[0-9]{3})+(\.[0-9]+)?", t):
        raise PayrollError(f"{name} must be an amount such as 1500.00 (commas only between groups of three digits).")
    t = t.replace(",", "")
    if not re.fullmatch(r"[0-9]{1,12}(\.[0-9]{1,2})?", t):
        raise PayrollError(f"{name} must be an amount such as 1500.00 (at most two decimals).")
    d = Decimal(t)
    if d == 0 and not zero_ok:
        raise PayrollError(f"{name} must be more than zero.")
    return d.quantize(CENT)


def _opt_amount(v, name) -> Decimal:
    return Decimal("0.00") if v in (None, "") else _amount(v, name, True)


def refnum(r) -> int:
    try: return int(str(r["ref"]).rsplit("-", 1)[1])
    except (KeyError, IndexError, ValueError): return 0


class PayrollService:
    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()

    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r.get("org") != org:
            raise PayrollNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("pw_setting", f"{org}:settings", for_update=for_update)
        if s and s.get("org") == org:
            return s
        return {"id": "settings", "org": org, **DEFAULTS, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("pw_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other:
            raise PayrollForbiddenError(f"You {what}, so you cannot do this. A different person must.")

    # ------------------------------------------------------------------ setting
    def pw_get_setting(self, org) -> dict:
        s = self._settings(org); lim = s["review_limit"]
        return {"review_limit": lim, "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": ("No line is flagged for its size. Set a limit to flag lines whose gross pay is above it." if Decimal(lim) == 0 else f"A line whose gross pay is more than {lim} is flagged for the approver to look at. This is your own setting, not a rule.")}

    def pw_set_setting(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        if d.get("review_limit") is not None: s["review_limit"] = str(_amount(d["review_limit"], "The review limit", True))
        s.update(updated_by=actor, updated_at=self.now().isoformat())
        self._put("pw_setting", org, s)
        self.log("PAYROLL_SETTING_SET", actor, "settings", org, "review limit")
        return self.pw_get_setting(org)

    # ------------------------------------------------------------------ views
    @staticmethod
    def _active(r) -> list: return [l for l in r["lines"] if l["status"] == "ACTIVE"]

    def _totals(self, lines) -> dict:
        z = Decimal(0); g = sum((Decimal(l["gross"]) for l in lines), z); d = sum((Decimal(l["total_deductions"]) for l in lines), z)
        n = sum((Decimal(l["net"]) for l in lines), z); e = sum((Decimal(l["employer_contributions"]) for l in lines), z); c = sum((Decimal(l["employer_cost"]) for l in lines), z)
        q = lambda x: str(x.quantize(CENT))
        return {"gross": q(g), "deductions": q(d), "net": q(n), "employer_contributions": q(e), "employer_cost": q(c), "lines": len(lines)}

    def _overlaps(self, r) -> set:
        """Staff references in this run that also appear in another submitted or approved run in the same currency for an overlapping period."""
        out = set()
        if r["status"] not in ("DRAFT", "RETURNED", "SUBMITTED", "APPROVED"): return out
        mine = {l["staff_ref"].lower() for l in self._active(r)}
        for o in self._all("pw_run", r["org"]):
            if o["id"] == r["id"] or o["status"] not in ("SUBMITTED", "APPROVED") or o["currency"] != r["currency"]: continue
            if o["period_start"] <= r["period_end"] and r["period_start"] <= o["period_end"]:
                out |= mine & {l["staff_ref"].lower() for l in self._active(o)}
        return out

    def _view(self, r) -> dict:
        v = {x: r[x] for x in r if x != "org"}
        limit = Decimal(self._settings(r["org"])["review_limit"]); ov = self._overlaps(r); act = self._active(r)
        lines = []
        for l in r["lines"]:
            l = dict(l); l["above_limit"] = l["status"] == "ACTIVE" and limit > 0 and Decimal(l["gross"]) > limit
            l["overlap"] = l["status"] == "ACTIVE" and l["staff_ref"].lower() in ov; lines.append(l)
        deps = {}
        for l in act: deps.setdefault(l["department"], []).append(l)
        v.update(lines=lines, totals=self._totals(act), active_lines=len(act), overlaps=len(ov), above_limit=sum(1 for l in lines if l["above_limit"]),
                 departments=[{"department": k, **self._totals(deps[k])} for k in sorted(deps, key=str.lower)])
        return v

    # ------------------------------------------------------------------ runs
    def pw_create_run(self, org, d, actor) -> dict:
        label = _txt(d.get("label"), "The label", 3, 150); start = _date(d.get("period_start"), "The start of the pay period"); end = _date(d.get("period_end"), "The end of the pay period")
        if end < start: raise PayrollError("The pay period cannot end before it starts.")
        if (end - start).days > 366: raise PayrollError("A pay period cannot be longer than a year.")
        if end > self.today() + timedelta(days=1): raise PayrollError("The end of the pay period cannot be in the future.")
        cur = _txt(d.get("currency"), "The currency", 3, 3).upper()
        if not re.fullmatch(r"[A-Z]{3}", cur): raise PayrollError("The currency must be a three-letter code such as NGN.")
        r = {"id": uuid.uuid4().hex, "org": org, "ref": None, "label": label, "period_start": start.isoformat(), "period_end": end.isoformat(), "currency": cur, "status": "DRAFT", "created_by": actor, "created_at": self.now().isoformat(),
             "lines": [], "note": None, "submitted_by": None, "submitted_on": None, "decided_by": None, "decided_on": None, "decision_note": None, "withdraw_note": None, "history": []}
        r["ref"] = self._ref(org, "PR"); self._hist(r, actor, "CREATED")
        self._put("pw_run", org, r); self.log("PAYROLL_RUN_CREATED", actor, r["id"], org, r["ref"])
        return self._view(r)

    def pw_list_runs(self, org, status=None) -> List[dict]:
        out = []
        for r in sorted(self._all("pw_run", org), key=refnum):
            if status and r["status"] != status: continue
            v = self._view(r); v["lines"] = []; out.append(v)       # the list carries totals, not the pay lines
        return out

    def pw_get_run(self, org, rid) -> dict: return self._view(self._get("pw_run", org, rid, "Payroll run"))

    def _editable(self, org, rid) -> dict:
        r = self._get("pw_run", org, rid, "Payroll run", for_update=True)
        if r["status"] not in ("DRAFT", "RETURNED"): raise PayrollStateError("Only a draft or returned run can be changed.")
        return r

    def pw_withdraw_run(self, org, rid, reason, actor) -> dict:
        r = self._editable(org, rid); reason = _txt(reason, "A reason", 10, 500); r.update(status="WITHDRAWN", withdraw_note=reason); self._hist(r, actor, "WITHDRAWN", reason)
        self._put("pw_run", org, r); self.log("PAYROLL_RUN_WITHDRAWN", actor, rid, org, r["ref"])
        return self._view(r)

    # ------------------------------------------------------------------ lines
    def pw_add_line(self, org, rid, d, actor) -> dict:
        r = self._editable(org, rid)
        staff = _txt(d.get("staff_ref"), "The staff reference", 2, 30); dept = _txt(d.get("department"), "The department", 2, 60)
        base = _amount(d.get("base_pay"), "The base pay"); allow = _opt_amount(d.get("allowances"), "The allowances"); emp = _opt_amount(d.get("employer_contributions"), "The employer contributions")
        raw = d.get("deductions", [])
        if raw is None: raw = []
        if not isinstance(raw, (list, tuple)) or len(raw) > MAX_DEDUCTIONS: raise PayrollError(f"Deductions must be a list of at most {MAX_DEDUCTIONS}.")
        deds = []
        for i, x in enumerate(raw, start=1):
            if not isinstance(x, dict): raise PayrollError(f"Deduction {i} must have a label and an amount.")
            deds.append({"label": _txt(x.get("label"), f"The label of deduction {i}", 2, 60), "amount": str(_amount(x.get("amount"), f"The amount of deduction {i}"))})
        gross = base + allow; total = sum((Decimal(x["amount"]) for x in deds), Decimal(0)).quantize(CENT)
        if total > gross: raise PayrollError("The deductions cannot be more than the gross pay.")
        if any(l["status"] == "ACTIVE" and l["staff_ref"].lower() == staff.lower() for l in r["lines"]): raise PayrollStateError("That staff reference already has a line in this run.")
        if len(self._active(r)) >= MAX_LINES: raise PayrollStateError(f"A run can have at most {MAX_LINES} lines.")
        r["lines"].append({"no": len(r["lines"]) + 1, "staff_ref": staff, "department": dept, "base_pay": str(base), "allowances": str(allow), "gross": str(gross), "deductions": deds, "total_deductions": str(total), "net": str(gross - total),
                           "employer_contributions": str(emp), "employer_cost": str(gross + emp), "status": "ACTIVE", "by": actor, "at": self.now().isoformat(), "removed_note": None})
        self._hist(r, actor, "LINE_ADDED")
        self._put("pw_run", org, r); self.log("PAYROLL_LINE_ADDED", actor, rid, org, f"{r['ref']} #{len(r['lines'])}")
        return self._view(r)

    def pw_remove_line(self, org, rid, no, reason, actor) -> dict:
        r = self._editable(org, rid)
        if isinstance(no, bool) or not re.fullmatch(r"[0-9]{1,6}", str(no).strip()): raise PayrollError("The line number must be a whole number.")
        n = int(str(no).strip()); l = next((l for l in r["lines"] if l["no"] == n), None)
        if l is None: raise PayrollNotFoundError("Line not found.")
        if l["status"] != "ACTIVE": raise PayrollStateError("That line is already removed.")
        reason = _txt(reason, "A reason", 5, 500); l.update(status="REMOVED", removed_note=reason); self._hist(r, actor, "LINE_REMOVED", reason)
        self._put("pw_run", org, r); self.log("PAYROLL_LINE_REMOVED", actor, rid, org, f"{r['ref']} #{n}")
        return self._view(r)

    # ------------------------------------------------------------------ review
    def pw_submit(self, org, rid, d, actor) -> dict:
        r = self._editable(org, rid)
        if not self._active(r): raise PayrollStateError("Add at least one pay line before submitting.")
        note = _txt(d.get("note"), "The note for the approver", 10, 2000, required=False)
        r.update(status="SUBMITTED", note=note or None, submitted_by=actor, submitted_on=self.today().isoformat(), decided_by=None, decided_on=None, decision_note=None); self._hist(r, actor, "SUBMITTED")
        self._put("pw_run", org, r); self.log("PAYROLL_RUN_SUBMITTED", actor, rid, org, r["ref"])
        return self._view(r)

    def _submitted(self, org, rid) -> dict:
        r = self._get("pw_run", org, rid, "Payroll run", for_update=True)
        if r["status"] != "SUBMITTED": raise PayrollStateError("Only a submitted run can be decided.")
        return r

    def pw_approve_run(self, org, rid, d, actor) -> dict:
        r = self._submitted(org, rid); self._two(actor, r["submitted_by"], "submitted this run")
        note = _txt(d.get("note"), "An approval note", 10, 1000, required=False)
        r.update(status="APPROVED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=note or None); self._hist(r, actor, "APPROVED", note)
        self._put("pw_run", org, r); self.log("PAYROLL_RUN_APPROVED", actor, rid, org, r["ref"])
        return self._view(r)

    def pw_return_run(self, org, rid, reason, actor) -> dict:
        r = self._submitted(org, rid); self._two(actor, r["submitted_by"], "submitted this run")
        reason = _txt(reason, "A reason", 10, 1000); r.update(status="RETURNED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=reason); self._hist(r, actor, "RETURNED", reason)
        self._put("pw_run", org, r); self.log("PAYROLL_RUN_RETURNED", actor, rid, org, r["ref"])
        return self._view(r)

    # ------------------------------------------------------------------ overview
    def pw_overview(self, org) -> dict:
        rs = [self._view(r) for r in sorted(self._all("pw_run", org), key=refnum)]; att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("RUNS_TO_REVIEW", sum(1 for r in rs if r["status"] == "SUBMITTED"), "payroll run(s) are waiting for a different person to review them.")
        add("RUNS_RETURNED", sum(1 for r in rs if r["status"] == "RETURNED"), "payroll run(s) were returned and need changes.")
        add("OVERLAPPING_PAY", sum(1 for r in rs if r["overlaps"] and r["status"] in ("SUBMITTED", "APPROVED")), "run(s) share a staff reference with another run for an overlapping period.")
        add("LINES_ABOVE_LIMIT", sum(r["above_limit"] for r in rs if r["status"] in ("SUBMITTED", "RETURNED", "DRAFT")), "line(s) in open runs are above your review limit.")
        tot = {}
        for r in rs:
            t = tot.setdefault(r["currency"], {"currency": r["currency"], "approved_runs": 0, "waiting_runs": 0, "gross": Decimal(0), "deductions": Decimal(0), "net": Decimal(0), "employer_contributions": Decimal(0), "employer_cost": Decimal(0)})
            if r["status"] == "SUBMITTED": t["waiting_runs"] += 1
            if r["status"] == "APPROVED":
                t["approved_runs"] += 1
                for k in ("gross", "deductions", "net", "employer_contributions", "employer_cost"): t[k] += Decimal(r["totals"][k])
        out = []
        for t in sorted(tot.values(), key=lambda x: x["currency"]):
            t = dict(t)
            for k in ("gross", "deductions", "net", "employer_contributions", "employer_cost"): t[k] = str(t[k].quantize(CENT))
            out.append(t)
        counts = {s.lower(): sum(1 for r in rs if r["status"] == s) for s in ("DRAFT", "SUBMITTED", "APPROVED", "RETURNED", "WITHDRAWN")}
        return {"counts": counts, "totals": out, "attention": att, "setting": self.pw_get_setting(org), "limitations": LIMITATIONS}

    def pw_options(self, org) -> dict:
        return {"max_lines": MAX_LINES, "max_deductions": MAX_DEDUCTIONS, "limitations": LIMITATIONS}
