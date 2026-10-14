"""Quality management (records and evidence): nonconformances and corrective actions.

Records (shared document store, per organisation): ql_nc, ql_action, ql_setting.

Principles enforced here
  * This records what people say about quality problems and what was done. ASAVEXA does not inspect anything, measure any product or process, or check that what was typed is true.
  * A corrective action is not finished when someone says it is done. A different person checks that it worked (an effectiveness check) and records the result.
  * A nonconformance is closed by a person other than the one who raised it, and only when its actions were checked and found effective.
  * A minor nonconformance may be closed with no action only with a written reason; major and critical ones cannot.
Nothing is edited or deleted; records are cancelled, voided or closed with a reason. Every step is audited. No certification or standard is claimed.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Callable, List

from .errors import QualityError, QualityForbiddenError, QualityNotFoundError, QualityStateError

SOURCES = ["INTERNAL_AUDIT", "CUSTOMER_COMPLAINT", "PROCESS_CHECK", "SUPPLIER", "INCIDENT", "OTHER"]
SEVERITIES = ["MINOR", "MAJOR", "CRITICAL"]
ACTION_KINDS = ["CORRECTIVE", "PREVENTIVE"]
RESULTS = ["EFFECTIVE", "NOT_EFFECTIVE"]
DEFAULTS = {"verify_days": 30}
LIMITATIONS = [
    "ASAVEXA inspects nothing and measures nothing. A nonconformance, a root cause or a completed action is what a person typed in.",
    "An effectiveness check is a different person's written judgement. ASAVEXA records it and applies the rules; it does not test whether the problem really went away.",
    "A minor nonconformance can be closed without an action only with a written reason. Major and critical ones always need a verified action.",
    "Closing a nonconformance here is not a certification, an audit result or evidence of compliance with any quality standard.",
    "ASAVEXA cannot know about a problem or an action that nobody records.",
]


def _utc(): return datetime.now(timezone.utc)


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v)))
    v = " ".join("".join(c if c >= " " and c != "\x7f" else " " for c in v).split())
    if required and len(v) < lo:
        raise QualityError(f"{name} is required (at least {lo} characters).")
    if v and len(v) < lo:
        raise QualityError(f"{name} needs at least {lo} characters.")
    if len(v) > hi:
        raise QualityError(f"{name} is too long (limit {hi} characters).")
    return v


def _date(v, name) -> date:
    try:
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise QualityError(f"{name} must be a real date written YYYY-MM-DD.")


def _enum(v, allowed, name) -> str:
    v = _txt(v, name, 1, 40).upper()
    if v not in allowed:
        raise QualityError(f"{name} must be one of {', '.join(allowed)}.")
    return v


def _int(v, name, lo, hi) -> int:
    if isinstance(v, bool) or not str(v).strip().isdigit():
        raise QualityError(f"{name} must be a whole number from {lo} to {hi}.")
    n = int(str(v).strip())
    if not lo <= n <= hi:
        raise QualityError(f"{name} must be a whole number from {lo} to {hi}.")
    return n


def refnum(r) -> int:
    """NC-012 -> 12, so references sort numerically."""
    try: return int(str(r["ref"]).rsplit("-", 1)[1])
    except (KeyError, IndexError, ValueError): return 0


class QualityService:
    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()

    def _not_future(self, d: date, what: str):
        if d > self.today() + timedelta(days=1):
            raise QualityError(f"{what} cannot be in the future.")

    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r.get("org") != org:
            raise QualityNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("ql_setting", f"{org}:settings", for_update=for_update)
        if s and s.get("org") == org:
            return s
        return {"id": "settings", "org": org, **DEFAULTS, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("ql_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other:
            raise QualityForbiddenError(f"You {what}, so you cannot do this. A different person must.")

    def _evidence(self, org, ids) -> List[dict]:
        out = []
        for i in dict.fromkeys(str(i) for i in (ids or [])):
            try:
                if self.vault is None: raise LookupError
                e = self.vault.get_evidence(org, i)
            except Exception:
                raise QualityError("Linked evidence not found in this organisation's Evidence Vault.")
            out.append({"evidence_id": e.id, "filename": e.original_filename, "file_hash": e.file_hash})
        return out

    # ------------------------------------------------------------------ policy
    def ql_get_policy(self, org) -> dict:
        s = self._settings(org)
        return {"verify_days": s["verify_days"], "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"A completed action not checked by a different person within {s['verify_days']} days is flagged. This is your own setting, not a standard."}

    def ql_set_policy(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        if d.get("verify_days") is not None: s["verify_days"] = _int(d["verify_days"], "The days allowed for an effectiveness check", 7, 180)
        s.update(updated_by=actor, updated_at=self.now().isoformat())
        self._put("ql_setting", org, s)
        self.log("QUALITY_POLICY_SET", actor, "settings", org, f"verify {s['verify_days']} days")
        return self.ql_get_policy(org)

    # ------------------------------------------------------------------ actions (views first: nonconformances use them)
    def _aview(self, a) -> dict:
        v = {x: a[x] for x in a if x != "org"}
        t = self.today()
        v["overdue"] = a["status"] == "OPEN" and date.fromisoformat(a["due_on"]) < t
        v["check_overdue"] = a["status"] == "COMPLETED" and date.fromisoformat(a["completed_on"]) + timedelta(days=self._settings(a["org"])["verify_days"]) < t
        return v

    def _actions_of(self, org, nid) -> List[dict]:
        return sorted((a for a in self._all("ql_action", org) if a["nc_id"] == nid), key=refnum)

    def _close_problem(self, nc, actions, no_action_reason=None):
        """Why this nonconformance cannot be closed yet, or None."""
        live = [a for a in actions if a["status"] != "CANCELLED"]
        if not live:
            if nc["severity"] == "MINOR" and no_action_reason: return None
            if nc["severity"] == "MINOR": return "Add an action, or give a written reason why no action is needed."
            return "A major or critical nonconformance needs at least one verified action."
        if any(a["status"] in ("OPEN", "COMPLETED") for a in live): return "Every action must be completed and checked by a different person first."
        last_bad = max((refnum(a) for a in live if a["status"] == "NOT_EFFECTIVE"), default=0)
        if not any(a["status"] == "VERIFIED" and refnum(a) > last_bad for a in live): return "An action that was not effective needs a later action that was checked and found effective."
        return None

    # ------------------------------------------------------------------ nonconformances
    def _nview(self, nc) -> dict:
        v = {x: nc[x] for x in nc if x != "org"}
        acts = [self._aview(a) for a in self._actions_of(nc["org"], nc["id"])]
        v["actions"] = acts; v["age_days"] = (self.today() - datetime.fromisoformat(nc["raised_at"]).date()).days
        v["close_problem"] = self._close_problem(nc, acts) if nc["status"] == "ANALYSED" else None
        return v

    def ql_raise_nc(self, org, d, actor) -> dict:
        title = _txt(d.get("title"), "The title", 5, 150); desc = _txt(d.get("description"), "What was found", 10, 2000); src = _enum(d.get("source"), SOURCES, "The source")
        sev = _enum(d.get("severity"), SEVERITIES, "The severity"); area = _txt(d.get("area"), "The area or process", 2, 150)
        occ = _date(d.get("occurred_on"), "The date it happened"); self._not_future(occ, "The date it happened")
        dis = _date(d.get("discovered_on"), "The date it was found"); self._not_future(dis, "The date it was found")
        if dis < occ: raise QualityError("It cannot have been found before it happened.")
        ev = self._evidence(org, d.get("evidence_ids"))
        nc = {"id": uuid.uuid4().hex, "org": org, "ref": None, "title": title, "description": desc, "source": src, "severity": sev, "area": area, "occurred_on": occ.isoformat(), "discovered_on": dis.isoformat(), "evidence": ev,
              "status": "RAISED", "raised_by": actor, "raised_at": self.now().isoformat(), "root_cause": None, "containment": None, "analysed_by": None, "closed_by": None, "closed_on": None, "closing_note": None,
              "no_action_reason": None, "void_note": None, "history": []}
        nc["ref"] = self._ref(org, "NC"); self._hist(nc, actor, "RAISED")
        self._put("ql_nc", org, nc); self.log("QUALITY_NC_RAISED", actor, nc["id"], org, f"{nc['ref']} {sev}")
        return self._nview(nc)

    def ql_analyse_nc(self, org, nid, d, actor) -> dict:
        nc = self._get("ql_nc", org, nid, "Nonconformance", for_update=True)
        if nc["status"] != "RAISED": raise QualityStateError("Only a nonconformance that has not been analysed can be analysed.")
        cause = _txt(d.get("root_cause"), "The root cause", 20, 2000); cont = _txt(d.get("containment"), "What was done straight away to contain it", 10, 1000)
        nc.update(status="ANALYSED", root_cause=cause, containment=cont, analysed_by=actor); self._hist(nc, actor, "ANALYSED")
        self._put("ql_nc", org, nc); self.log("QUALITY_NC_ANALYSED", actor, nid, org, nc["ref"])
        return self._nview(nc)

    def ql_close_nc(self, org, nid, d, actor) -> dict:
        nc = self._get("ql_nc", org, nid, "Nonconformance", for_update=True)
        if nc["status"] != "ANALYSED": raise QualityStateError("Only an analysed nonconformance can be closed.")
        self._two(actor, nc["raised_by"], "raised this nonconformance")
        note = _txt(d.get("note"), "A closing note", 10, 1000)
        reason = _txt(d.get("no_action_reason"), "The reason no action is needed", 20, 1000, required=False)
        acts = self._actions_of(org, nid); problem = self._close_problem(nc, acts, reason or None)
        if problem: raise QualityStateError(problem)
        none_live = not [a for a in acts if a["status"] != "CANCELLED"]
        nc.update(status="CLOSED", closed_by=actor, closed_on=self.today().isoformat(), closing_note=note, no_action_reason=(reason or None) if none_live else None); self._hist(nc, actor, "CLOSED", note)
        self._put("ql_nc", org, nc); self.log("QUALITY_NC_CLOSED", actor, nid, org, nc["ref"])
        return self._nview(nc)

    def ql_void_nc(self, org, nid, reason, actor) -> dict:
        nc = self._get("ql_nc", org, nid, "Nonconformance", for_update=True)
        if nc["status"] != "RAISED": raise QualityStateError("Only a nonconformance that has not been analysed can be voided.")
        self._two(actor, nc["raised_by"], "raised this nonconformance")
        reason = _txt(reason, "A reason", 10, 500); nc.update(status="VOIDED", void_note=reason); self._hist(nc, actor, "VOIDED", reason)
        self._put("ql_nc", org, nc); self.log("QUALITY_NC_VOIDED", actor, nid, org, nc["ref"])
        return self._nview(nc)

    def ql_list_ncs(self, org, status=None, severity=None) -> List[dict]:
        return [self._nview(n) for n in sorted(self._all("ql_nc", org), key=refnum) if (not status or n["status"] == status) and (not severity or n["severity"] == severity)]

    def ql_get_nc(self, org, nid) -> dict: return self._nview(self._get("ql_nc", org, nid, "Nonconformance"))

    # ------------------------------------------------------------------ corrective actions
    def ql_add_action(self, org, d, actor) -> dict:
        nc = self._get("ql_nc", org, d.get("nc_id"), "Nonconformance", for_update=True)
        if nc["status"] != "ANALYSED": raise QualityStateError("An action can only be added to a nonconformance that has been analysed and is not closed.")
        kind = _enum(d.get("kind"), ACTION_KINDS, "The kind of action"); desc = _txt(d.get("description"), "The action", 10, 1000); owner = _txt(d.get("owner_name"), "The owner", 2, 100)
        due = _date(d.get("due_on"), "The due date")
        if due < date.fromisoformat(nc["discovered_on"]): raise QualityError("The due date cannot be before the problem was found.")
        if due > self.today() + timedelta(days=730): raise QualityError("The due date is more than two years away.")
        a = {"id": uuid.uuid4().hex, "org": org, "ref": None, "nc_id": nc["id"], "nc_ref": nc["ref"], "nc_title": nc["title"], "severity": nc["severity"], "kind": kind, "description": desc, "owner_name": owner, "due_on": due.isoformat(),
             "status": "OPEN", "added_by": actor, "added_at": self.now().isoformat(), "completed_on": None, "completed_by": None, "completion_note": None, "evidence": [], "checked_by": None, "result": None, "check_note": None,
             "cancel_note": None, "history": []}
        a["ref"] = self._ref(org, "CA"); self._hist(a, actor, "ADDED")
        self._put("ql_action", org, a); self.log("QUALITY_ACTION_ADDED", actor, a["id"], org, f"{a['ref']} {nc['ref']}")
        return self._aview(a)

    def ql_complete_action(self, org, aid, d, actor) -> dict:
        a = self._get("ql_action", org, aid, "Action", for_update=True)
        if a["status"] != "OPEN": raise QualityStateError("Only an open action can be recorded as completed.")
        nc = self._get("ql_nc", org, a["nc_id"], "Nonconformance")
        on = _date(d.get("completed_on"), "The date it was completed"); self._not_future(on, "The date it was completed")
        if on < date.fromisoformat(nc["discovered_on"]): raise QualityError("It cannot have been completed before the problem was found.")
        note = _txt(d.get("note"), "What was done", 10, 1000); ev = self._evidence(org, d.get("evidence_ids"))
        a.update(status="COMPLETED", completed_on=on.isoformat(), completed_by=actor, completion_note=note, evidence=ev); self._hist(a, actor, "COMPLETED")
        self._put("ql_action", org, a); self.log("QUALITY_ACTION_COMPLETED", actor, aid, org, a["ref"])
        return self._aview(a)

    def ql_verify_action(self, org, aid, d, actor) -> dict:
        a = self._get("ql_action", org, aid, "Action", for_update=True)
        if a["status"] != "COMPLETED": raise QualityStateError("Only a completed action can be checked for effectiveness.")
        self._two(actor, a["completed_by"], "recorded this action as completed")
        result = _enum(d.get("result"), RESULTS, "The result"); note = _txt(d.get("note"), "The effectiveness check", 20, 1000)
        a.update(status="VERIFIED" if result == "EFFECTIVE" else "NOT_EFFECTIVE", checked_by=actor, result=result, check_note=note); self._hist(a, actor, "VERIFIED" if result == "EFFECTIVE" else "NOT_EFFECTIVE")
        self._put("ql_action", org, a); self.log("QUALITY_ACTION_VERIFIED", actor, aid, org, f"{a['ref']} {result}")
        return self._aview(a)

    def ql_cancel_action(self, org, aid, reason, actor) -> dict:
        a = self._get("ql_action", org, aid, "Action", for_update=True)
        if a["status"] != "OPEN": raise QualityStateError("Only an open action can be cancelled.")
        reason = _txt(reason, "A reason", 10, 500); a.update(status="CANCELLED", cancel_note=reason); self._hist(a, actor, "CANCELLED", reason)
        self._put("ql_action", org, a); self.log("QUALITY_ACTION_CANCELLED", actor, aid, org, a["ref"])
        return self._aview(a)

    def ql_list_actions(self, org, nc_id=None, status=None) -> List[dict]:
        return [self._aview(a) for a in sorted(self._all("ql_action", org), key=refnum) if (not nc_id or a["nc_id"] == nc_id) and (not status or a["status"] == status)]

    def ql_get_action(self, org, aid) -> dict: return self._aview(self._get("ql_action", org, aid, "Action"))

    # ------------------------------------------------------------------ overview
    def ql_overview(self, org) -> dict:
        ncs = self.ql_list_ncs(org); acts = self.ql_list_actions(org); open_nc = [n for n in ncs if n["status"] in ("RAISED", "ANALYSED")]; att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("CRITICAL_OPEN", sum(1 for n in open_nc if n["severity"] == "CRITICAL"), "critical nonconformance(s) are not closed.")
        add("ACTIONS_OVERDUE", sum(1 for a in acts if a["overdue"]), "action(s) are past their due date and not completed.")
        add("CHECKS_OVERDUE", sum(1 for a in acts if a["check_overdue"]), "completed action(s) have waited longer than your window for an effectiveness check.")
        add("NOT_EFFECTIVE", sum(1 for n in open_nc if n["status"] == "ANALYSED" and any(a["status"] == "NOT_EFFECTIVE" for a in n["actions"]) and n["close_problem"]), "open nonconformance(s) have an action that was not effective and no later effective one.")
        add("ACTIONS_TO_CHECK", sum(1 for a in acts if a["status"] == "COMPLETED"), "completed action(s) are waiting for a different person to check them.")
        add("NCS_TO_ANALYSE", sum(1 for n in ncs if n["status"] == "RAISED"), "nonconformance(s) have not been analysed.")
        add("NCS_WITHOUT_ACTIONS", sum(1 for n in ncs if n["status"] == "ANALYSED" and not [a for a in n["actions"] if a["status"] != "CANCELLED"]), "analysed nonconformance(s) have no action yet.")
        add("NCS_READY_TO_CLOSE", sum(1 for n in ncs if n["status"] == "ANALYSED" and n["close_problem"] is None), "nonconformance(s) are ready for a different person to close them.")
        return {"counts": {"open": len(open_nc), "critical_open": sum(1 for n in open_nc if n["severity"] == "CRITICAL"), "major_open": sum(1 for n in open_nc if n["severity"] == "MAJOR"), "minor_open": sum(1 for n in open_nc if n["severity"] == "MINOR"),
                           "closed": sum(1 for n in ncs if n["status"] == "CLOSED"), "actions_open": sum(1 for a in acts if a["status"] == "OPEN"), "actions_verified": sum(1 for a in acts if a["status"] == "VERIFIED"),
                           "actions_not_effective": sum(1 for a in acts if a["status"] == "NOT_EFFECTIVE")},
                "attention": att, "policy": self.ql_get_policy(org), "limitations": LIMITATIONS}

    def ql_options(self, org) -> dict:
        return {"sources": SOURCES, "severities": SEVERITIES, "action_kinds": ACTION_KINDS, "results": RESULTS, "limitations": LIMITATIONS}
