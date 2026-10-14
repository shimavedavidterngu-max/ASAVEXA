"""IT audit (records and evidence): change-management records and testing, application-control testing, two-person review.

Records (shared document store, per organisation): ia_change, ia_control, ia_test, ia_setting.

Principles enforced here
  * A change record is what people typed in from the organisation's own change system (ticket, who asked, who approved, when it went live, what testing and rollback
    evidence exists). ASAVEXA applies fixed rules to those typed facts and shows the exceptions. It does not connect to any system and cannot tell whether the
    typed facts are true.
  * A change-management test draws a sample by a rule anyone can repeat (the seed, the population and the size are recorded, so the same sample comes out every time).
    It is not a statistical sample and supports no conclusion about the whole population.
  * The tester concludes on each sampled item. A flagged item can only be called "no exception" with a written explanation; an unflagged item can only be called an
    exception with a note. The tester cannot test a change they recorded or a control they defined.
  * A different person approves the test. That person cannot be the tester, cannot have recorded any sampled change, and cannot have defined the control tested.
    A test with exceptions needs a written note to approve. The result against the tolerable number of exceptions is arithmetic, not an audit opinion.
Nothing is edited or deleted; a change can be voided with a reason. Every step is audited.
"""
import hashlib
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Callable, List

from .errors import ItAuditError, ItAuditForbiddenError, ItAuditNotFoundError, ItAuditStateError

CHANGE_TYPES = ["STANDARD", "NORMAL", "EMERGENCY"]
RISKS = ["LOW", "MEDIUM", "HIGH"]
CONTROL_TYPES = ["INPUT_VALIDATION", "ACCESS", "CALCULATION", "INTERFACE", "SEGREGATION_OF_DUTIES", "REPORTING", "OTHER"]
FREQUENCIES = ["CONTINUOUS", "DAILY", "WEEKLY", "MONTHLY", "ANNUAL", "EVENT_DRIVEN"]
RESULTS = ["NO_EXCEPTION", "EXCEPTION"]
CASE_RESULTS = ["PASS", "FAIL"]
DEFAULTS = {"emergency_ratify_days": 5, "retest_days": 365}
FLAG_TEXT = {
    "NO_APPROVAL": "No approval is recorded (who approved it and when).",
    "APPROVED_AFTER_GO_LIVE": "The approval is dated after the change went live.",
    "EMERGENCY_RATIFIED_LATE": "An emergency change was approved after the allowed number of days.",
    "SELF_APPROVED": "The person who asked for the change is recorded as the person who approved it.",
    "NO_TESTING_EVIDENCE": "No record of testing before go-live (not required for standard changes).",
    "NO_ROLLBACK_PLAN": "No rollback plan is recorded for a medium or high risk change.",
}
LIMITATIONS = [
    "ASAVEXA does not connect to any system, read any ticket or test any application. Everything here is what people typed in, so it is only as true as their records.",
    "A flag is a fixed rule applied to the typed facts. It points at something to look at; it is not a finding and not a conclusion that a change was wrong.",
    "A sample is drawn by a rule anyone can repeat from the seed, the population and the size. It is not a statistical sample and supports no conclusion about every change.",
    "'Within tolerance' or 'above tolerance' compares the exceptions found with the number your own test allowed. It is arithmetic, not an audit opinion or assurance.",
    "The tester cannot test their own records, and a different person approves each test, but ASAVEXA cannot know about relationships that nobody records.",
    "Nothing is deleted. A change record that was entered in error is voided with a reason and left out of later populations.",
]


def _utc(): return datetime.now(timezone.utc)


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v)))
    v = " ".join("".join(c if c >= " " and c != "\x7f" else " " for c in v).split())
    if required and len(v) < lo:
        raise ItAuditError(f"{name} is required (at least {lo} characters).")
    if v and len(v) < lo:
        raise ItAuditError(f"{name} needs at least {lo} characters.")
    if len(v) > hi:
        raise ItAuditError(f"{name} is too long (limit {hi} characters).")
    return v


def _date(v, name) -> date:
    try:
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise ItAuditError(f"{name} must be a real date written YYYY-MM-DD.")


def _enum(v, allowed, name) -> str:
    v = _txt(v, name, 1, 40).upper()
    if v not in allowed:
        raise ItAuditError(f"{name} must be one of {', '.join(allowed)}.")
    return v


def _int(v, name, lo, hi) -> int:
    if isinstance(v, bool) or not str(v).strip().lstrip("-").isdigit():
        raise ItAuditError(f"{name} must be a whole number from {lo} to {hi}.")
    n = int(str(v).strip())
    if not lo <= n <= hi:
        raise ItAuditError(f"{name} must be a whole number from {lo} to {hi}.")
    return n


def refnum(r) -> int:
    """CH-012 -> 12, so references sort numerically and records made in the same instant keep the order they were made in."""
    try: return int(str(r["ref"]).rsplit("-", 1)[1])
    except (KeyError, IndexError, ValueError): return 0


def _sha(s: str) -> str: return hashlib.sha256(s.encode()).hexdigest()


def select_sample(refs: List[str], seed: str, size: int) -> List[str]:
    """The refs whose hash with the seed sorts lowest. Anyone with the seed, the population and the size gets the same sample."""
    ranked = sorted(refs, key=lambda r: (_sha(f"{seed}|{r}"), r))
    return sorted(ranked[:size], key=lambda r: int(r.rsplit("-", 1)[1]))


def change_flags(c: dict) -> List[str]:
    """Fixed rules over the typed facts of a change record."""
    out = []
    impl = date.fromisoformat(c["implemented_on"])
    if not c["approved_by_name"] or not c["approved_on"]:
        out.append("NO_APPROVAL")
    else:
        appr = date.fromisoformat(c["approved_on"])
        if c["change_type"] == "EMERGENCY":
            if appr > impl + timedelta(days=c["ratify_days"]): out.append("EMERGENCY_RATIFIED_LATE")
        elif appr > impl:
            out.append("APPROVED_AFTER_GO_LIVE")
        if c["requested_by"].casefold() == c["approved_by_name"].casefold(): out.append("SELF_APPROVED")
    if c["change_type"] != "STANDARD" and not c["testing_evidence"]: out.append("NO_TESTING_EVIDENCE")
    if c["risk"] in ("MEDIUM", "HIGH") and not c["rollback_plan"]: out.append("NO_ROLLBACK_PLAN")
    return out


class ItAuditService:
    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()

    def _not_future(self, d: date, what: str):
        if d > self.today() + timedelta(days=1):
            raise ItAuditError(f"{what} cannot be in the future.")

    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r.get("org") != org:
            raise ItAuditNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("ia_setting", f"{org}:settings", for_update=for_update)
        if s and s.get("org") == org:
            return s
        return {"id": "settings", "org": org, **DEFAULTS, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("ia_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other:
            raise ItAuditForbiddenError(f"You {what}, so you cannot do this. A different person must.")

    def _evidence(self, org, ids) -> List[dict]:
        out = []
        for i in dict.fromkeys(str(i) for i in (ids or [])):
            try:
                if self.vault is None: raise LookupError
                e = self.vault.get_evidence(org, i)
            except Exception:
                raise ItAuditError("Linked evidence not found in this organisation's Evidence Vault.")
            out.append({"evidence_id": e.id, "filename": e.original_filename, "file_hash": e.file_hash})
        return out

    def _asset(self, org, aid):
        """An optional link to a Cybersecurity asset of the same organisation: (id, name) or (None, None)."""
        if aid in (None, ""): return None, None
        a = self.store.get("cy_asset", f"{org}:{aid}")
        if a is None or a.get("org") != org: raise ItAuditError("Linked asset not found in this organisation's Cybersecurity assets.")
        return a["id"], a["name"]

    # ------------------------------------------------------------------ policy
    def ia_get_policy(self, org) -> dict:
        s = self._settings(org)
        return {"emergency_ratify_days": s["emergency_ratify_days"], "retest_days": s["retest_days"], "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"An emergency change should be approved within {s['emergency_ratify_days']} days of going live (fixed on each change record when it is recorded). A control not tested for {s['retest_days']} days is flagged. These are your own settings, not a standard."}

    def ia_set_policy(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        for k, name, lo, hi in (("emergency_ratify_days", "The emergency approval window", 0, 60), ("retest_days", "The retest interval", 30, 1095)):
            if d.get(k) is not None: s[k] = _int(d[k], name, lo, hi)
        s.update(updated_by=actor, updated_at=self.now().isoformat())
        self._put("ia_setting", org, s)
        self.log("ITAUDIT_POLICY_SET", actor, "settings", org, f"emergency window {s['emergency_ratify_days']}, retest {s['retest_days']}")
        return self.ia_get_policy(org)

    # ------------------------------------------------------------------ changes
    def _chview(self, c) -> dict:
        v = {x: c[x] for x in ("id", "ref", "system", "asset_id", "asset_name", "title", "description", "change_type", "risk", "requested_by", "approved_by_name", "approved_on", "ticket_ref", "implemented_on",
                               "testing_evidence", "rollback_plan", "evidence", "ratify_days", "status", "recorded_by", "recorded_at", "void_note", "history")}
        v["flags"] = change_flags(c); v["flag_texts"] = [FLAG_TEXT[f] for f in v["flags"]]
        return v

    def ia_record_change(self, org, d, actor) -> dict:
        system = _txt(d.get("system"), "The system", 2, 150)
        asset_id, asset_name = self._asset(org, d.get("asset_id"))
        ctype = _enum(d.get("change_type"), CHANGE_TYPES, "The change type"); risk = _enum(d.get("risk"), RISKS, "The risk")
        title = _txt(d.get("title"), "The change title", 5, 150); desc = _txt(d.get("description"), "What was changed", 10, 2000)
        requested = _txt(d.get("requested_by"), "Who asked for the change", 2, 100)
        appr_name = _txt(d.get("approved_by_name"), "Who approved it", 2, 100, required=False); appr_on = _txt(d.get("approved_on"), "The approval date", 0, 10, required=False)
        if bool(appr_name) != bool(appr_on): raise ItAuditError("Give both who approved the change and when, or neither.")
        if appr_on:
            ad = _date(appr_on, "The approval date"); self._not_future(ad, "The approval date")
        ticket = _txt(d.get("ticket_ref"), "The ticket or change number", 2, 60)
        impl = _date(d.get("implemented_on"), "The go-live date"); self._not_future(impl, "The go-live date")
        if any(x["ticket_ref"].casefold() == ticket.casefold() and x["system"].casefold() == system.casefold() and x["status"] == "RECORDED" for x in self._all("ia_change", org)):
            raise ItAuditStateError(f"A change with ticket {ticket} is already recorded for {system}.")
        test = _txt(d.get("testing_evidence"), "The testing evidence", 10, 1000, required=False); roll = _txt(d.get("rollback_plan"), "The rollback plan", 10, 1000, required=False)
        ev = self._evidence(org, d.get("evidence_ids"))
        c = {"id": uuid.uuid4().hex, "org": org, "ref": None, "system": system, "asset_id": asset_id, "asset_name": asset_name, "title": title, "description": desc, "change_type": ctype, "risk": risk,
             "requested_by": requested, "approved_by_name": appr_name or None, "approved_on": appr_on or None, "ticket_ref": ticket, "implemented_on": impl.isoformat(), "testing_evidence": test, "rollback_plan": roll,
             "evidence": ev, "ratify_days": self._settings(org)["emergency_ratify_days"], "status": "RECORDED", "recorded_by": actor, "recorded_at": self.now().isoformat(), "void_note": None, "history": []}
        c["ref"] = self._ref(org, "CH"); self._hist(c, actor, "RECORDED")
        self._put("ia_change", org, c); self.log("ITAUDIT_CHANGE_RECORDED", actor, c["id"], org, f"{c['ref']} {ctype}")
        return self._chview(c)

    def ia_void_change(self, org, cid, reason, actor) -> dict:
        c = self._get("ia_change", org, cid, "Change", for_update=True)
        if c["status"] != "RECORDED": raise ItAuditStateError("This change record is already voided.")
        self._two(actor, c["recorded_by"], "recorded this change")
        reason = _txt(reason, "A reason", 10, 500)
        if any(t["status"] in ("DRAFT", "SUBMITTED", "APPROVED") and any(i["change_id"] == cid for i in t.get("items", [])) for t in self._all("ia_test", org)):
            raise ItAuditStateError("This change is part of a test sample, so it cannot be voided. Reject or finish that test first.")
        c.update(status="VOIDED", void_note=reason); self._hist(c, actor, "VOIDED", reason)
        self._put("ia_change", org, c); self.log("ITAUDIT_CHANGE_VOIDED", actor, cid, org, c["ref"])
        return self._chview(c)

    def ia_list_changes(self, org, system=None, flagged=None, status=None) -> List[dict]:
        out = []
        for c in sorted(self._all("ia_change", org), key=refnum):
            if status and c["status"] != status: continue
            if system and c["system"].casefold() != system.casefold(): continue
            v = self._chview(c)
            if flagged is not None and bool(v["flags"]) != flagged: continue
            out.append(v)
        return out

    def ia_get_change(self, org, cid) -> dict: return self._chview(self._get("ia_change", org, cid, "Change"))

    # ------------------------------------------------------------------ controls
    def _ctview(self, org, c, tests=None) -> dict:
        tests = self._all("ia_test", org) if tests is None else tests
        mine = [t for t in tests if t["kind"] == "CONTROL" and t["control_id"] == c["id"]]
        done = sorted([t for t in mine if t["status"] == "APPROVED"], key=refnum)
        v = {x: c[x] for x in ("id", "ref", "system", "asset_id", "asset_name", "name", "control_type", "description", "expected_result", "frequency", "tolerable", "status", "created_by", "created_at", "retire_note", "history")}
        v["tests"] = len(mine); v["last_tested_on"] = done[-1]["approved_on"] if done else None; v["last_conclusion"] = done[-1]["conclusion"] if done else None
        days = self._settings(org)["retest_days"]
        v["retest_due"] = c["status"] == "ACTIVE" and (not done or date.fromisoformat(done[-1]["approved_on"]) + timedelta(days=days) < self.today())
        return v

    def ia_define_control(self, org, d, actor) -> dict:
        system = _txt(d.get("system"), "The system", 2, 150); asset_id, asset_name = self._asset(org, d.get("asset_id"))
        name = _txt(d.get("name"), "The control name", 5, 150)
        if any(x["name"].casefold() == name.casefold() and x["system"].casefold() == system.casefold() and x["status"] == "ACTIVE" for x in self._all("ia_control", org)):
            raise ItAuditStateError("That control is already defined for this system.")
        tol = _int(d["tolerable"], "The tolerable number of exceptions", 0, 20) if d.get("tolerable") not in (None, "") else 0
        c = {"id": uuid.uuid4().hex, "org": org, "ref": None, "system": system, "asset_id": asset_id, "asset_name": asset_name, "name": name, "control_type": _enum(d.get("control_type"), CONTROL_TYPES, "The control type"),
             "description": _txt(d.get("description"), "What the control does", 10, 1000), "expected_result": _txt(d.get("expected_result"), "The expected result", 5, 500), "frequency": _enum(d.get("frequency"), FREQUENCIES, "How often it operates"),
             "tolerable": tol, "status": "ACTIVE", "created_by": actor, "created_at": self.now().isoformat(), "retire_note": None, "history": []}
        c["ref"] = self._ref(org, "AC"); self._hist(c, actor, "DEFINED")
        self._put("ia_control", org, c); self.log("ITAUDIT_CONTROL_DEFINED", actor, c["id"], org, c["ref"])
        return self._ctview(org, c)

    def ia_retire_control(self, org, cid, reason, actor) -> dict:
        c = self._get("ia_control", org, cid, "Control", for_update=True)
        if c["status"] != "ACTIVE": raise ItAuditStateError("This control is already retired.")
        reason = _txt(reason, "A reason", 10, 500)
        if any(t["kind"] == "CONTROL" and t["control_id"] == cid and t["status"] in ("DRAFT", "SUBMITTED") for t in self._all("ia_test", org)):
            raise ItAuditStateError("This control has a test in progress. Finish or reject it first.")
        c.update(status="RETIRED", retire_note=reason); self._hist(c, actor, "RETIRED", reason)
        self._put("ia_control", org, c); self.log("ITAUDIT_CONTROL_RETIRED", actor, cid, org, c["ref"])
        return self._ctview(org, c)

    def ia_list_controls(self, org, system=None) -> List[dict]:
        tests = self._all("ia_test", org)
        return [self._ctview(org, c, tests) for c in sorted(self._all("ia_control", org), key=refnum) if not system or c["system"].casefold() == system.casefold()]

    def ia_get_control(self, org, cid) -> dict: return self._ctview(org, self._get("ia_control", org, cid, "Control"))

    # ------------------------------------------------------------------ tests
    def _tview(self, t) -> dict:
        v = {x: t[x] for x in t if x not in ("org",)}
        its = t.get("items", []); cs = t.get("cases", [])
        if t["kind"] == "CHANGE":
            v["concluded"] = sum(1 for i in its if i["result"]); v["exceptions"] = sum(1 for i in its if i["result"] == "EXCEPTION"); v["overrides"] = sum(1 for i in its if i.get("overrode_flags"))
        else:
            v["concluded"] = len(cs); v["exceptions"] = sum(1 for x in cs if x["result"] == "FAIL"); v["overrides"] = 0
        return v

    def _new_test(self, org, kind, d, actor, extra) -> dict:
        t = {"id": uuid.uuid4().hex, "org": org, "ref": None, "kind": kind, "title": _txt(d.get("title"), "The test title", 5, 150), "status": "DRAFT", "prepared_by": actor, "prepared_at": self.now().isoformat(),
             "submitted_at": None, "approved_by": None, "approved_on": None, "conclusion": None, "approval_note": None, "rejected_note": None, "history": [], **extra}
        t["ref"] = self._ref(org, "TS"); self._hist(t, actor, "PLANNED")
        return t

    def ia_plan_change_test(self, org, d, actor) -> dict:
        pf = _date(d.get("period_from"), "The period start"); pt = _date(d.get("period_to"), "The period end")
        if pt < pf: raise ItAuditError("The period cannot end before it starts.")
        self._not_future(pt, "The period end")
        system = _txt(d.get("system"), "The system", 2, 150, required=False)
        size = _int(d.get("sample_size"), "The sample size", 1, 100); seed = _txt(d.get("seed"), "The seed", 3, 60)
        tol = _int(d["tolerable"], "The tolerable number of exceptions", 0, 20) if d.get("tolerable") not in (None, "") else 0
        pop = [c for c in self._all("ia_change", org) if c["status"] == "RECORDED" and pf <= date.fromisoformat(c["implemented_on"]) <= pt and (not system or c["system"].casefold() == system.casefold())]
        if not pop: raise ItAuditError("No recorded change went live in that period" + (f" for {system}." if system else "."))
        by_ref = {c["ref"]: c for c in pop}; picked = select_sample(list(by_ref), seed, min(size, len(pop)))
        own = [r for r in picked if by_ref[r]["recorded_by"] == actor]
        if own: raise ItAuditForbiddenError(f"The sample includes {len(own)} change(s) you recorded ({', '.join(own)}), so you cannot test them. A different person must plan this test.")
        items = []
        for r in picked:
            c = by_ref[r]; v = self._chview(c)
            items.append({"id": uuid.uuid4().hex, "change_id": c["id"], "ref": r, "snapshot": {k: v[k] for k in ("system", "title", "change_type", "risk", "requested_by", "approved_by_name", "approved_on", "ticket_ref", "implemented_on", "recorded_by")} | {"recorded_by": c["recorded_by"]},
                          "flags": v["flags"], "result": None, "note": None, "overrode_flags": False, "concluded_by": None, "concluded_at": None})
        t = self._new_test(org, "CHANGE", d, actor, {"system": system or None, "period_from": pf.isoformat(), "period_to": pt.isoformat(), "sample_size": size, "seed": seed, "tolerable": tol,
                                                    "population_count": len(pop), "population_fingerprint": _sha(",".join(sorted(by_ref, key=lambda r: int(r.rsplit("-", 1)[1])))), "items": items, "control_id": None, "control_ref": None, "cases": []})
        self._put("ia_test", org, t); self.log("ITAUDIT_TEST_PLANNED", actor, t["id"], org, f"{t['ref']} change sample {len(items)} of {len(pop)}")
        return self._tview(t)

    def ia_plan_control_test(self, org, d, actor) -> dict:
        c = self._get("ia_control", org, str(d.get("control_id") or ""), "Control")
        if c["status"] != "ACTIVE": raise ItAuditStateError("A retired control cannot be tested.")
        self._two(actor, c["created_by"], "defined this control")
        if any(t["kind"] == "CONTROL" and t["control_id"] == c["id"] and t["status"] in ("DRAFT", "SUBMITTED") for t in self._all("ia_test", org)):
            raise ItAuditStateError("This control already has a test in progress.")
        t = self._new_test(org, "CONTROL", d, actor, {"system": c["system"], "period_from": None, "period_to": None, "sample_size": None, "seed": None, "tolerable": c["tolerable"], "population_count": None,
                                                     "population_fingerprint": None, "items": [], "control_id": c["id"], "control_ref": c["ref"], "control_name": c["name"], "control_expected": c["expected_result"], "control_created_by": c["created_by"], "cases": []})
        self._put("ia_test", org, t); self.log("ITAUDIT_TEST_PLANNED", actor, t["id"], org, f"{t['ref']} control {c['ref']}")
        return self._tview(t)

    def _mine(self, org, tid, actor, kind=None) -> dict:
        t = self._get("ia_test", org, tid, "Test", for_update=True)
        if kind and t["kind"] != kind: raise ItAuditStateError(f"This is a {'change-management' if t['kind'] == 'CHANGE' else 'control'} test.")
        if t["status"] != "DRAFT": raise ItAuditStateError("Only a test being worked on can be changed.")
        if t["prepared_by"] != actor: raise ItAuditForbiddenError("Only the person who planned this test can work on it.")
        return t

    def ia_conclude_item(self, org, tid, iid, d, actor) -> dict:
        t = self._mine(org, tid, actor, "CHANGE")
        it = next((i for i in t["items"] if i["id"] == iid), None)
        if it is None: raise ItAuditNotFoundError("Sampled change not found in this test.")
        if it["snapshot"]["recorded_by"] == actor: raise ItAuditForbiddenError("You recorded this change, so you cannot test it. A different person must.")
        result = _enum(d.get("result"), RESULTS, "The result")
        if result == "NO_EXCEPTION" and it["flags"]: note = _txt(d.get("note"), "An explanation of why the flagged items are not an exception", 20, 1000)
        elif result == "EXCEPTION": note = _txt(d.get("note"), "A note on the exception", 10, 1000)
        else: note = _txt(d.get("note"), "A note", 5, 1000, required=False)
        it.update(result=result, note=note, overrode_flags=bool(result == "NO_EXCEPTION" and it["flags"]), concluded_by=actor, concluded_at=self.now().isoformat())
        self._hist(t, actor, "ITEM_CONCLUDED", f"{it['ref']} {result}")
        self._put("ia_test", org, t); self.log("ITAUDIT_ITEM_CONCLUDED", actor, tid, org, f"{t['ref']} {it['ref']} {result}")
        return self._tview(t)

    def ia_add_case(self, org, tid, d, actor) -> dict:
        t = self._mine(org, tid, actor, "CONTROL")
        on = _date(d.get("performed_on"), "The date performed"); self._not_future(on, "The date performed")
        result = _enum(d.get("result"), CASE_RESULTS, "The result")
        note = _txt(d.get("note"), "A note on the failure", 10, 1000) if result == "FAIL" else _txt(d.get("note"), "A note", 5, 1000, required=False)
        x = {"id": uuid.uuid4().hex, "seq": len(t["cases"]) + 1, "description": _txt(d.get("description"), "What was tried", 10, 1000), "expected": _txt(d.get("expected"), "The expected result", 5, 500),
             "actual": _txt(d.get("actual"), "The actual result", 3, 500), "result": result, "note": note, "performed_on": on.isoformat(), "evidence": self._evidence(org, d.get("evidence_ids")), "recorded_by": actor, "recorded_at": self.now().isoformat()}
        t["cases"].append(x); self._hist(t, actor, "CASE_ADDED", result)
        self._put("ia_test", org, t); self.log("ITAUDIT_CASE_ADDED", actor, tid, org, f"{t['ref']} case {x['seq']} {result}")
        return self._tview(t)

    def ia_submit_test(self, org, tid, actor) -> dict:
        t = self._mine(org, tid, actor)
        if t["kind"] == "CHANGE":
            left = sum(1 for i in t["items"] if not i["result"])
            if left: raise ItAuditStateError(f"{left} sampled change(s) have no conclusion yet.")
        elif not t["cases"]: raise ItAuditStateError("Record at least one test case before submitting.")
        t.update(status="SUBMITTED", submitted_at=self.now().isoformat()); self._hist(t, actor, "SUBMITTED")
        self._put("ia_test", org, t); self.log("ITAUDIT_TEST_SUBMITTED", actor, tid, org, t["ref"])
        return self._tview(t)

    def _approver_checks(self, org, t, actor):
        if t["status"] != "SUBMITTED": raise ItAuditStateError("Only a submitted test can be approved or sent back.")
        self._two(actor, t["prepared_by"], "carried out this test")
        if t["kind"] == "CHANGE":
            if any(i["snapshot"]["recorded_by"] == actor for i in t["items"]): raise ItAuditForbiddenError("You recorded one of the sampled changes, so you cannot approve this test. A different person must.")
        elif t.get("control_created_by") == actor: raise ItAuditForbiddenError("You defined this control, so you cannot approve its test. A different person must.")

    def ia_approve_test(self, org, tid, actor, note="") -> dict:
        t = self._get("ia_test", org, tid, "Test", for_update=True); self._approver_checks(org, t, actor)
        v = self._tview(t); note = _txt(note, "A note on the exceptions", 10, 1000, required=bool(v["exceptions"] or v["overrides"]))
        t.update(status="APPROVED", approved_by=actor, approved_on=self.today().isoformat(), approval_note=note or None,
                 conclusion="WITHIN_TOLERANCE" if v["exceptions"] <= t["tolerable"] else "ABOVE_TOLERANCE"); self._hist(t, actor, "APPROVED", note)
        self._put("ia_test", org, t); self.log("ITAUDIT_TEST_APPROVED", actor, tid, org, f"{t['ref']} {t['conclusion']}")
        return self._tview(t)

    def ia_reject_test(self, org, tid, reason, actor) -> dict:
        t = self._get("ia_test", org, tid, "Test", for_update=True); self._approver_checks(org, t, actor)
        reason = _txt(reason, "A reason", 10, 500); t.update(status="DRAFT", rejected_note=reason, submitted_at=None); self._hist(t, actor, "SENT_BACK", reason)
        self._put("ia_test", org, t); self.log("ITAUDIT_TEST_REJECTED", actor, tid, org, t["ref"])
        return self._tview(t)

    def ia_withdraw_test(self, org, tid, reason, actor) -> dict:
        """The person who planned a test being worked on can withdraw it, with a reason. Its sample and cases are kept; its changes and control are released."""
        t = self._mine(org, tid, actor); reason = _txt(reason, "A reason", 10, 500)
        t.update(status="WITHDRAWN", rejected_note=reason); self._hist(t, actor, "WITHDRAWN", reason)
        self._put("ia_test", org, t); self.log("ITAUDIT_TEST_WITHDRAWN", actor, tid, org, t["ref"])
        return self._tview(t)

    def ia_list_tests(self, org, kind=None, status=None) -> List[dict]:
        out = []
        for t in sorted(self._all("ia_test", org), key=refnum):
            if (kind and t["kind"] != kind) or (status and t["status"] != status): continue
            v = self._tview(t); v["items_count"] = len(v.pop("items")); v["cases_count"] = len(v.pop("cases")); v.pop("history"); out.append(v)
        return out

    def ia_get_test(self, org, tid) -> dict: return self._tview(self._get("ia_test", org, tid, "Test"))

    # ------------------------------------------------------------------ overview
    def ia_overview(self, org) -> dict:
        changes = [self._chview(c) for c in sorted(self._all("ia_change", org), key=refnum)]; live = [c for c in changes if c["status"] == "RECORDED"]
        tests = self._all("ia_test", org); controls = self.ia_list_controls(org); active = [c for c in controls if c["status"] == "ACTIVE"]; att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        sampled = {i["change_id"] for t in tests if t["status"] in ("SUBMITTED", "APPROVED") for i in t.get("items", [])}
        add("CHANGES_FLAGGED_UNTESTED", sum(1 for c in live if c["flags"] and c["id"] not in sampled), "recorded change(s) have a flag and have not been part of an approved or submitted test.")
        add("EMERGENCY_CHANGES_FLAGGED", sum(1 for c in live if c["change_type"] == "EMERGENCY" and c["flags"]), "emergency change(s) have a flag.")
        add("TESTS_TO_APPROVE", sum(1 for t in tests if t["status"] == "SUBMITTED"), "test(s) are waiting for a different person to approve them.")
        add("TESTS_ABOVE_TOLERANCE", sum(1 for t in tests if t["conclusion"] == "ABOVE_TOLERANCE"), "approved test(s) found more exceptions than the tolerable number.")
        add("CONTROLS_NEVER_TESTED", sum(1 for c in active if not c["tests"]), "active control(s) have never been tested.")
        add("CONTROLS_RETEST_DUE", sum(1 for c in active if c["retest_due"] and c["tests"]), "control(s) are due for a retest under your own interval.")
        by_type = {k: sum(1 for c in live if c["change_type"] == k) for k in CHANGE_TYPES}
        return {"counts": {"changes": len(changes), "changes_live": len(live), "changes_flagged": sum(1 for c in live if c["flags"]), "changes_by_type": by_type, "controls": len(controls), "controls_active": len(active),
                           "tests": len(tests), "tests_approved": sum(1 for t in tests if t["status"] == "APPROVED")}, "attention": att, "policy": self.ia_get_policy(org), "limitations": LIMITATIONS, "flag_texts": FLAG_TEXT}

    def ia_options(self, org) -> dict:
        assets = sorted((a for a in self._all("cy_asset", org) if a.get("status") == "ACTIVE"), key=lambda a: a.get("ref", ""))
        return {"change_types": CHANGE_TYPES, "risks": RISKS, "control_types": CONTROL_TYPES, "frequencies": FREQUENCIES, "results": RESULTS, "case_results": CASE_RESULTS,
                "assets": [{"id": a["id"], "ref": a["ref"], "name": a["name"]} for a in assets], "flag_texts": FLAG_TEXT, "limitations": LIMITATIONS}
