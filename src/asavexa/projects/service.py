"""Projects and grants (records and evidence): a project with a typed award and budget lines; spending and receipts reviewed by a different person.

Records (shared document store, per organisation): pj_project, pj_setting.

Principles enforced here
  * A project (for example a grant-funded programme) has a typed award, a currency, a period and budget lines (a category and an amount each). The total of the active budget lines can never be more than the award.
  * A project is prepared, submitted, and approved or returned by a person other than the one who submitted it. Only an approved (ACTIVE) project accepts entries.
  * An entry is either an EXPENSE against a budget line or a RECEIPT (money the funder paid). Each is proposed by one person and approved or rejected by a different person. Only approved entries count. An entry date must fall inside the project period and not be in the future.
  * ASAVEXA moves no money, applies no funder rules and checks no eligibility. Every figure is typed. Overspending a budget line is flagged for a person to look at, not blocked.
  * Amounts are kept per currency and never added across currencies. Nothing is edited after approval or deleted; a line is marked removed with a reason. Every step is audited by reference number only.
"""
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, List

from .errors import ProjectsError, ProjectsForbiddenError, ProjectsNotFoundError, ProjectsStateError

DEFAULTS = {"ending_soon_days": 30}
CENT = Decimal("0.01")
MAX_BUDGET_LINES = 50
MAX_ENTRIES = 2000
MAX_DAYS = 3660
LIMITATIONS = [
    "ASAVEXA adds up the figures people type in. It moves no money, applies no funder or donor rules, checks no eligibility and does not know whether spending is allowed under any agreement.",
    "The award, the budget and every entry are typed by people. A different person approving an entry is a review of what was typed, not a check against receipts, contracts or the real world.",
    "The total of the budget lines cannot be more than the award, but it can be less; the difference is shown as unallocated.",
    "Spending above a budget line, receipts above the award, a project ending soon and a project past its end date still open are flagged for a person to look at. They are not blocked, because they can be right.",
    "Amounts in different currencies are never added together. An approved entry is final; a correction is a new entry that a person explains.",
]


def _utc(): return datetime.now(timezone.utc)


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v)))
    v = " ".join("".join(c if c >= " " and c != "\x7f" else " " for c in v).split())
    if required and len(v) < lo:
        raise ProjectsError(f"{name} is required (at least {lo} characters).")
    if v and len(v) < lo:
        raise ProjectsError(f"{name} needs at least {lo} characters.")
    if len(v) > hi:
        raise ProjectsError(f"{name} is too long (limit {hi} characters).")
    return v


def _date(v, name) -> date:
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", str(v).strip()): raise ValueError
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise ProjectsError(f"{name} must be a real date written YYYY-MM-DD.")


def _amount(v, name, zero_ok=False) -> Decimal:
    """Text or a whole number: ASCII digits, at most two decimals, never a float, commas only as thousands separators."""
    if isinstance(v, bool) or isinstance(v, float) or v is None:
        raise ProjectsError(f"{name} must be an amount such as 1500.00.")
    t = str(v).strip()
    if "," in t and not re.fullmatch(r"[0-9]{1,3}(,[0-9]{3})+(\.[0-9]+)?", t):
        raise ProjectsError(f"{name} must be an amount such as 1500.00 (commas only between groups of three digits).")
    t = t.replace(",", "")
    if not re.fullmatch(r"[0-9]{1,13}(\.[0-9]{1,2})?", t):
        raise ProjectsError(f"{name} must be an amount such as 1500.00 (at most two decimals).")
    d = Decimal(t)
    if d == 0 and not zero_ok:
        raise ProjectsError(f"{name} must be more than zero.")
    return d.quantize(CENT)


def _whole(v, name, lo, hi) -> int:
    if isinstance(v, bool) or isinstance(v, float) or v is None or not re.fullmatch(r"[0-9]{1,4}", str(v).strip()):
        raise ProjectsError(f"{name} must be a whole number from {lo} to {hi}.")
    n = int(str(v).strip())
    if not lo <= n <= hi: raise ProjectsError(f"{name} must be a whole number from {lo} to {hi}.")
    return n


def refnum(r) -> int:
    try: return int(str(r["ref"]).rsplit("-", 1)[1])
    except (KeyError, IndexError, ValueError): return 0


Q = lambda x: str(Decimal(x).quantize(CENT))


class ProjectsService:
    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()

    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r.get("org") != org:
            raise ProjectsNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("pj_setting", f"{org}:settings", for_update=for_update)
        if s and s.get("org") == org:
            return s
        return {"id": "settings", "org": org, **DEFAULTS, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("pj_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other:
            raise ProjectsForbiddenError(f"You {what}, so you cannot do this. A different person must.")

    # ------------------------------------------------------------------ setting
    def pj_get_setting(self, org) -> dict:
        s = self._settings(org); n = s["ending_soon_days"]
        return {"ending_soon_days": n, "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"An open project whose end date is within {n} day(s) is flagged for a person to look at. This is your own setting, not a rule."}

    def pj_set_setting(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        if d.get("ending_soon_days") is not None: s["ending_soon_days"] = _whole(d["ending_soon_days"], "The number of days", 1, 365)
        s.update(updated_by=actor, updated_at=self.now().isoformat())
        self._put("pj_setting", org, s)
        self.log("PROJECTS_SETTING_SET", actor, "settings", org, "ending soon days")
        return self.pj_get_setting(org)

    # ------------------------------------------------------------------ views
    @staticmethod
    def _active(r) -> list: return [l for l in r["budget"] if l["status"] == "ACTIVE"]

    def _view(self, r) -> dict:
        v = {x: r[x] for x in r if x != "org"}
        z = Decimal(0); act = self._active(r); budget = sum((Decimal(l["amount"]) for l in act), z); award = Decimal(r["award"])
        approved = [e for e in r["entries"] if e["status"] == "APPROVED"]
        spent_by = {}
        for e in approved:
            if e["entry_type"] == "EXPENSE": spent_by[e["budget_no"]] = spent_by.get(e["budget_no"], z) + Decimal(e["amount"])
        spent = sum(spent_by.values(), z); received = sum((Decimal(e["amount"]) for e in approved if e["entry_type"] == "RECEIPT"), z)
        lines = []
        for l in r["budget"]:
            l = dict(l); sp = spent_by.get(l["no"], z); bud = Decimal(l["amount"])
            l.update(spent=Q(sp), remaining=Q(bud - sp), over_budget=sp > bud)
            lines.append(l)
        today = self.today(); end = date.fromisoformat(r["period_end"]); days_left = (end - today).days
        open_ = r["status"] == "ACTIVE"; soon = self._settings(r["org"])["ending_soon_days"]
        burn = (spent * 100 / award).quantize(CENT) if award > 0 else Decimal("0.00")
        v.update(budget=lines, entries=[dict(e) for e in r["entries"]], award=Q(award), budgeted=Q(budget), unallocated=Q(award - budget), spent=Q(spent), remaining=Q(award - spent), received=Q(received), still_to_receive=Q(award - received),
                 spent_pct=str(burn), active_lines=len(act), pending_entries=sum(1 for e in r["entries"] if e["status"] == "PROPOSED"), over_budget_lines=sum(1 for l in lines if l["status"] == "ACTIVE" and l["over_budget"]),
                 received_above_award=received > award, days_left=days_left, ending_soon=open_ and 0 <= days_left <= soon, ended_still_open=open_ and days_left < 0)
        return v

    # ------------------------------------------------------------------ projects
    def pj_create_project(self, org, d, actor) -> dict:
        title = _txt(d.get("title"), "The title", 3, 150); fref = _txt(d.get("funder_ref"), "The funder reference", 2, 40)
        start = _date(d.get("period_start"), "The start of the project"); end = _date(d.get("period_end"), "The end of the project")
        if end < start: raise ProjectsError("The project cannot end before it starts.")
        if (end - start).days > MAX_DAYS: raise ProjectsError("A project cannot be longer than ten years.")
        cur = _txt(d.get("currency"), "The currency", 3, 3).upper()
        if not re.fullmatch(r"[A-Z]{3}", cur): raise ProjectsError("The currency must be a three-letter code such as NGN.")
        award = _amount(d.get("award"), "The award")
        r = {"id": uuid.uuid4().hex, "org": org, "ref": None, "title": title, "funder_ref": fref, "currency": cur, "award": str(award), "period_start": start.isoformat(), "period_end": end.isoformat(), "status": "DRAFT",
             "created_by": actor, "created_at": self.now().isoformat(), "budget": [], "entries": [], "note": None, "submitted_by": None, "submitted_on": None, "decided_by": None, "decided_on": None, "decision_note": None,
             "withdraw_note": None, "closed_by": None, "closed_on": None, "close_note": None, "history": []}
        r["ref"] = self._ref(org, "PJ"); self._hist(r, actor, "CREATED")
        self._put("pj_project", org, r); self.log("PROJECTS_PROJECT_CREATED", actor, r["id"], org, r["ref"])
        return self._view(r)

    def pj_list_projects(self, org, status=None) -> List[dict]:
        out = []
        for r in sorted(self._all("pj_project", org), key=refnum):
            if status and r["status"] != status: continue
            v = self._view(r); v["budget"] = []; v["entries"] = []; out.append(v)     # the list carries totals, not the lines
        return out

    def pj_get_project(self, org, pid) -> dict: return self._view(self._get("pj_project", org, pid, "Project"))

    def _editable(self, org, pid) -> dict:
        r = self._get("pj_project", org, pid, "Project", for_update=True)
        if r["status"] not in ("DRAFT", "RETURNED"): raise ProjectsStateError("Only a draft or returned project can be changed.")
        return r

    def pj_withdraw_project(self, org, pid, reason, actor) -> dict:
        r = self._editable(org, pid); reason = _txt(reason, "A reason", 10, 500); r.update(status="WITHDRAWN", withdraw_note=reason); self._hist(r, actor, "WITHDRAWN", reason)
        self._put("pj_project", org, r); self.log("PROJECTS_PROJECT_WITHDRAWN", actor, pid, org, r["ref"])
        return self._view(r)

    # ------------------------------------------------------------------ budget lines
    def pj_add_budget(self, org, pid, d, actor) -> dict:
        r = self._editable(org, pid); cat = _txt(d.get("category"), "The category", 2, 80); amount = _amount(d.get("amount"), "The budget amount")
        act = self._active(r)
        if any(l["category"].lower() == cat.lower() for l in act): raise ProjectsStateError("That category already has a budget line in this project.")
        if len(act) >= MAX_BUDGET_LINES: raise ProjectsStateError(f"A project can have at most {MAX_BUDGET_LINES} budget lines.")
        if sum((Decimal(l["amount"]) for l in act), Decimal(0)) + amount > Decimal(r["award"]): raise ProjectsError("The budget lines cannot add up to more than the award.")
        r["budget"].append({"no": len(r["budget"]) + 1, "category": cat, "amount": str(amount), "status": "ACTIVE", "by": actor, "at": self.now().isoformat(), "removed_note": None})
        self._hist(r, actor, "BUDGET_LINE_ADDED")
        self._put("pj_project", org, r); self.log("PROJECTS_BUDGET_ADDED", actor, pid, org, f"{r['ref']} #{len(r['budget'])}")
        return self._view(r)

    def pj_remove_budget(self, org, pid, no, reason, actor) -> dict:
        r = self._editable(org, pid)
        if isinstance(no, bool) or not re.fullmatch(r"[0-9]{1,6}", str(no).strip()): raise ProjectsError("The line number must be a whole number.")
        n = int(str(no).strip()); l = next((l for l in r["budget"] if l["no"] == n), None)
        if l is None: raise ProjectsNotFoundError("Budget line not found.")
        if l["status"] != "ACTIVE": raise ProjectsStateError("That budget line is already removed.")
        reason = _txt(reason, "A reason", 5, 500); l.update(status="REMOVED", removed_note=reason); self._hist(r, actor, "BUDGET_LINE_REMOVED", reason)
        self._put("pj_project", org, r); self.log("PROJECTS_BUDGET_REMOVED", actor, pid, org, f"{r['ref']} #{n}")
        return self._view(r)

    # ------------------------------------------------------------------ review of the project
    def pj_submit(self, org, pid, d, actor) -> dict:
        r = self._editable(org, pid)
        if not self._active(r): raise ProjectsStateError("Add at least one budget line before submitting.")
        note = _txt(d.get("note"), "The note for the approver", 10, 2000, required=False)
        r.update(status="SUBMITTED", note=note or None, submitted_by=actor, submitted_on=self.today().isoformat(), decided_by=None, decided_on=None, decision_note=None); self._hist(r, actor, "SUBMITTED")
        self._put("pj_project", org, r); self.log("PROJECTS_PROJECT_SUBMITTED", actor, pid, org, r["ref"])
        return self._view(r)

    def _submitted(self, org, pid) -> dict:
        r = self._get("pj_project", org, pid, "Project", for_update=True)
        if r["status"] != "SUBMITTED": raise ProjectsStateError("Only a submitted project can be decided.")
        return r

    def pj_approve_project(self, org, pid, d, actor) -> dict:
        r = self._submitted(org, pid); self._two(actor, r["submitted_by"], "submitted this project")
        note = _txt(d.get("note"), "An approval note", 10, 1000, required=False)
        r.update(status="ACTIVE", decided_by=actor, decided_on=self.today().isoformat(), decision_note=note or None); self._hist(r, actor, "APPROVED", note)
        self._put("pj_project", org, r); self.log("PROJECTS_PROJECT_APPROVED", actor, pid, org, r["ref"])
        return self._view(r)

    def pj_return_project(self, org, pid, reason, actor) -> dict:
        r = self._submitted(org, pid); self._two(actor, r["submitted_by"], "submitted this project")
        reason = _txt(reason, "A reason", 10, 1000); r.update(status="RETURNED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=reason); self._hist(r, actor, "RETURNED", reason)
        self._put("pj_project", org, r); self.log("PROJECTS_PROJECT_RETURNED", actor, pid, org, r["ref"])
        return self._view(r)

    def pj_close_project(self, org, pid, note, actor) -> dict:
        r = self._get("pj_project", org, pid, "Project", for_update=True)
        if r["status"] != "ACTIVE": raise ProjectsStateError("Only an active project can be closed.")
        if any(e["status"] == "PROPOSED" for e in r["entries"]): raise ProjectsStateError("Decide every proposed entry before closing the project.")
        note = _txt(note, "A closing note", 10, 1000)
        r.update(status="CLOSED", closed_by=actor, closed_on=self.today().isoformat(), close_note=note); self._hist(r, actor, "CLOSED", note)
        self._put("pj_project", org, r); self.log("PROJECTS_PROJECT_CLOSED", actor, pid, org, r["ref"])
        return self._view(r)

    # ------------------------------------------------------------------ entries
    def pj_add_entry(self, org, pid, d, actor) -> dict:
        r = self._get("pj_project", org, pid, "Project", for_update=True)
        if r["status"] != "ACTIVE": raise ProjectsStateError("Entries can only be added to an approved, open project.")
        et = d.get("entry_type"); et = et.strip().upper() if isinstance(et, str) else ""
        if et not in ("EXPENSE", "RECEIPT"): raise ProjectsError("The entry type must be EXPENSE or RECEIPT.")
        amount = _amount(d.get("amount"), "The amount"); when = _date(d.get("entry_date"), "The date")
        if when < date.fromisoformat(r["period_start"]) or when > date.fromisoformat(r["period_end"]): raise ProjectsError("The date must fall inside the project period.")
        if when > self.today() + timedelta(days=1): raise ProjectsError("The date cannot be in the future.")
        desc = _txt(d.get("description"), "The description", 3, 300); bno = None
        if et == "EXPENSE":
            raw = d.get("budget_no")
            if isinstance(raw, bool) or raw is None or not re.fullmatch(r"[0-9]{1,6}", str(raw).strip()): raise ProjectsError("Choose the budget line the expense belongs to.")
            bno = int(str(raw).strip()); l = next((l for l in r["budget"] if l["no"] == bno), None)
            if l is None or l["status"] != "ACTIVE": raise ProjectsError("Choose a budget line that is in use.")
        elif d.get("budget_no") not in (None, ""): raise ProjectsError("A receipt does not belong to a budget line.")
        if len(r["entries"]) >= MAX_ENTRIES: raise ProjectsStateError(f"A project can have at most {MAX_ENTRIES} entries.")
        r["entries"].append({"no": len(r["entries"]) + 1, "entry_type": et, "budget_no": bno, "amount": str(amount), "entry_date": when.isoformat(), "description": desc, "status": "PROPOSED", "proposed_by": actor, "proposed_at": self.now().isoformat(),
                             "decided_by": None, "decided_on": None, "decision_note": None})
        self._hist(r, actor, "ENTRY_PROPOSED")
        self._put("pj_project", org, r); self.log("PROJECTS_ENTRY_PROPOSED", actor, pid, org, f"{r['ref']} #{len(r['entries'])}")
        return self._view(r)

    def _entry(self, org, pid, no) -> tuple:
        r = self._get("pj_project", org, pid, "Project", for_update=True)
        if isinstance(no, bool) or not re.fullmatch(r"[0-9]{1,6}", str(no).strip()): raise ProjectsError("The entry number must be a whole number.")
        n = int(str(no).strip()); e = next((e for e in r["entries"] if e["no"] == n), None)
        if e is None: raise ProjectsNotFoundError("Entry not found.")
        if e["status"] != "PROPOSED": raise ProjectsStateError("That entry has already been decided.")
        if r["status"] != "ACTIVE": raise ProjectsStateError("The project is not open.")
        return r, e, n

    def pj_approve_entry(self, org, pid, no, d, actor) -> dict:
        r, e, n = self._entry(org, pid, no); self._two(actor, e["proposed_by"], "proposed this entry")
        note = _txt(d.get("note"), "An approval note", 10, 1000, required=False)
        e.update(status="APPROVED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=note or None); self._hist(r, actor, "ENTRY_APPROVED", note)
        self._put("pj_project", org, r); self.log("PROJECTS_ENTRY_APPROVED", actor, pid, org, f"{r['ref']} #{n}")
        return self._view(r)

    def pj_reject_entry(self, org, pid, no, reason, actor) -> dict:
        r, e, n = self._entry(org, pid, no); self._two(actor, e["proposed_by"], "proposed this entry")
        reason = _txt(reason, "A reason", 10, 1000)
        e.update(status="REJECTED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=reason); self._hist(r, actor, "ENTRY_REJECTED", reason)
        self._put("pj_project", org, r); self.log("PROJECTS_ENTRY_REJECTED", actor, pid, org, f"{r['ref']} #{n}")
        return self._view(r)

    # ------------------------------------------------------------------ overview
    def pj_overview(self, org) -> dict:
        ps = [self._view(r) for r in sorted(self._all("pj_project", org), key=refnum)]; att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("PROJECTS_TO_REVIEW", sum(1 for p in ps if p["status"] == "SUBMITTED"), "project(s) are waiting for a different person to review them.")
        add("PROJECTS_RETURNED", sum(1 for p in ps if p["status"] == "RETURNED"), "project(s) were returned and need changes.")
        add("ENTRIES_TO_REVIEW", sum(p["pending_entries"] for p in ps if p["status"] == "ACTIVE"), "spending or receipt entr(ies) are waiting for a different person to decide them.")
        add("OVER_BUDGET", sum(p["over_budget_lines"] for p in ps if p["status"] in ("ACTIVE", "CLOSED")), "budget line(s) have more approved spending than their budget.")
        add("RECEIVED_ABOVE_AWARD", sum(1 for p in ps if p["received_above_award"] and p["status"] in ("ACTIVE", "CLOSED")), "project(s) have approved receipts above the award.")
        add("ENDING_SOON", sum(1 for p in ps if p["ending_soon"]), "open project(s) end soon.")
        add("ENDED_STILL_OPEN", sum(1 for p in ps if p["ended_still_open"]), "project(s) are past their end date and still open.")
        tot = {}
        for p in ps:
            if p["status"] not in ("ACTIVE", "CLOSED"): continue
            t = tot.setdefault(p["currency"], {"currency": p["currency"], "projects": 0, "award": Decimal(0), "budgeted": Decimal(0), "spent": Decimal(0), "received": Decimal(0)})
            t["projects"] += 1
            for k in ("award", "budgeted", "spent", "received"): t[k] += Decimal(p[k])
        out = []
        for t in sorted(tot.values(), key=lambda x: x["currency"]):
            t = dict(t)
            for k in ("award", "budgeted", "spent", "received"): t[k] = str(t[k].quantize(CENT))
            t["remaining"] = Q(Decimal(t["award"]) - Decimal(t["spent"])); t["still_to_receive"] = Q(Decimal(t["award"]) - Decimal(t["received"])); out.append(t)
        counts = {s.lower(): sum(1 for p in ps if p["status"] == s) for s in ("DRAFT", "SUBMITTED", "ACTIVE", "RETURNED", "CLOSED", "WITHDRAWN")}
        return {"counts": counts, "totals": out, "attention": att, "setting": self.pj_get_setting(org), "limitations": LIMITATIONS}

    def pj_options(self, org) -> dict:
        return {"max_budget_lines": MAX_BUDGET_LINES, "max_entries": MAX_ENTRIES, "entry_types": ["EXPENSE", "RECEIPT"], "limitations": LIMITATIONS}
