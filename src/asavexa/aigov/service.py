"""AI governance (records and evidence): an inventory of AI systems, model changes and AI incidents.

Records (shared document store, per organisation): aig_system, aig_change, aig_incident, aig_setting.

Principles enforced here
  * This records what people say about their AI systems. ASAVEXA does not connect to any model, measure any output, test any system, or check that what was typed is true.
  * The intended use, the out-of-scope uses and the risk tier cannot be changed once a different person approves a system. To change them, retire the system and propose a new one,
    so a system cannot quietly drift into a use nobody approved.
  * A model change is recorded against an approved system and approved by a different person. A change to a high-risk system needs a linked test document.
  * An incident is reviewed (cause and corrective action) by a different person from the one who recorded it.
  * A periodic review of a system is done by a person other than the one who proposed it.
Nothing is edited or deleted; records are retired, voided or rejected with a reason. Every step is audited. No regulatory classification is claimed.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Callable, List

from .errors import AigovError, AigovForbiddenError, AigovNotFoundError, AigovStateError

ORIGINS = ["IN_HOUSE", "VENDOR", "OPEN_SOURCE"]
TIERS = ["MINIMAL", "LIMITED", "HIGH"]
CHANGE_KINDS = ["MODEL_UPDATE", "PROMPT_CHANGE", "DATA_CHANGE", "CONFIG_CHANGE", "VENDOR_CHANGE"]
INCIDENT_KINDS = ["WRONG_OUTPUT", "BIAS", "DATA_LEAK", "MISUSE", "OUTAGE", "OTHER"]
SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
DEFAULTS = {"review_days": 180, "incident_review_days": 7}
LIMITATIONS = [
    "ASAVEXA does not connect to any AI system, run any test or measure any output. Everything here is what a person typed in.",
    "The risk tier is your own label. It is not a legal classification under any law or standard, and it is not an assessment of how risky the system is.",
    "The intended use, the out-of-scope uses and the risk tier cannot be changed once approved. To change them, retire the system and propose a new one.",
    "A model change record shows who said what changed and who approved it. It does not show the change was tested well, or that it was the only change.",
    "ASAVEXA cannot know about an AI system, a change or an incident that nobody records.",
]


def _utc(): return datetime.now(timezone.utc)


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v)))
    v = " ".join("".join(c if c >= " " and c != "\x7f" else " " for c in v).split())
    if required and len(v) < lo:
        raise AigovError(f"{name} is required (at least {lo} characters).")
    if v and len(v) < lo:
        raise AigovError(f"{name} needs at least {lo} characters.")
    if len(v) > hi:
        raise AigovError(f"{name} is too long (limit {hi} characters).")
    return v


def _date(v, name) -> date:
    try:
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise AigovError(f"{name} must be a real date written YYYY-MM-DD.")


def _enum(v, allowed, name) -> str:
    v = _txt(v, name, 1, 40).upper()
    if v not in allowed:
        raise AigovError(f"{name} must be one of {', '.join(allowed)}.")
    return v


def _int(v, name, lo, hi) -> int:
    if isinstance(v, bool) or not str(v).strip().isdigit():
        raise AigovError(f"{name} must be a whole number from {lo} to {hi}.")
    n = int(str(v).strip())
    if not lo <= n <= hi:
        raise AigovError(f"{name} must be a whole number from {lo} to {hi}.")
    return n


def refnum(r) -> int:
    """AI-012 -> 12, so references sort numerically."""
    try: return int(str(r["ref"]).rsplit("-", 1)[1])
    except (KeyError, IndexError, ValueError): return 0


class AigovService:
    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()

    def _not_future(self, d: date, what: str):
        if d > self.today() + timedelta(days=1):
            raise AigovError(f"{what} cannot be in the future.")

    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r.get("org") != org:
            raise AigovNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("aig_setting", f"{org}:settings", for_update=for_update)
        if s and s.get("org") == org:
            return s
        return {"id": "settings", "org": org, **DEFAULTS, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("aig_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other:
            raise AigovForbiddenError(f"You {what}, so you cannot do this. A different person must.")

    def _evidence(self, org, ids) -> List[dict]:
        out = []
        for i in dict.fromkeys(str(i) for i in (ids or [])):
            try:
                if self.vault is None: raise LookupError
                e = self.vault.get_evidence(org, i)
            except Exception:
                raise AigovError("Linked evidence not found in this organisation's Evidence Vault.")
            out.append({"evidence_id": e.id, "filename": e.original_filename, "file_hash": e.file_hash})
        return out

    def _approved_system(self, org, sid, what) -> dict:
        s = self._get("aig_system", org, sid, "AI system", for_update=True)
        if s["status"] != "APPROVED": raise AigovStateError(f"{what} can only be recorded for an approved AI system.")
        return s

    # ------------------------------------------------------------------ policy
    def aig_get_policy(self, org) -> dict:
        s = self._settings(org)
        return {"review_days": s["review_days"], "incident_review_days": s["incident_review_days"], "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"An approved AI system not reviewed for {s['review_days']} days is flagged as due. An incident not reviewed within {s['incident_review_days']} days is flagged. These are your own settings, not a standard."}

    def aig_set_policy(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        for k, name, lo, hi in (("review_days", "The system review interval", 30, 730), ("incident_review_days", "The incident review window", 1, 60)):
            if d.get(k) is not None: s[k] = _int(d[k], name, lo, hi)
        s.update(updated_by=actor, updated_at=self.now().isoformat())
        self._put("aig_setting", org, s)
        self.log("AIGOV_POLICY_SET", actor, "settings", org, f"review {s['review_days']}, incident review {s['incident_review_days']}")
        return self.aig_get_policy(org)

    # ------------------------------------------------------------------ AI systems
    def _sview(self, s) -> dict:
        v = {x: s[x] for x in s if x != "org"}
        base = s.get("last_reviewed_on") or (s["decided_at"][:10] if s.get("decided_at") else None)
        v["review_due"] = s["status"] == "APPROVED" and base is not None and date.fromisoformat(base) + timedelta(days=self._settings(s["org"])["review_days"]) < self.today()
        chg = [c for c in self._all("aig_change", s["org"]) if c["system_id"] == s["id"]]; inc = [i for i in self._all("aig_incident", s["org"]) if i["system_id"] == s["id"]]
        v["changes"] = sum(1 for c in chg if c["status"] == "APPROVED"); v["pending_changes"] = sum(1 for c in chg if c["status"] == "RECORDED")
        v["incidents"] = sum(1 for i in inc if i["status"] != "VOIDED"); v["open_incidents"] = sum(1 for i in inc if i["status"] == "RECORDED")
        return v

    def aig_propose_system(self, org, d, actor) -> dict:
        name = _txt(d.get("name"), "The system name", 5, 150); desc = _txt(d.get("description"), "What the system does", 10, 1000)
        origin = _enum(d.get("origin"), ORIGINS, "Where it comes from"); vendor = _txt(d.get("vendor_name"), "The vendor or project name", 2, 150, required=origin != "IN_HOUSE")
        use = _txt(d.get("intended_use"), "The intended use", 10, 1000); out = _txt(d.get("out_of_scope"), "The uses that are not allowed", 10, 1000)
        tier = _enum(d.get("risk_tier"), TIERS, "The risk tier"); data = _txt(d.get("data_categories"), "The kinds of data it uses", 3, 500, required=False)
        oversight = _txt(d.get("human_oversight"), "How a person oversees it", 10, 1000, required=tier == "HIGH")
        owner = _txt(d.get("owner_name"), "The owner", 2, 100)
        if any(x["name"].casefold() == name.casefold() and x["status"] in ("PROPOSED", "APPROVED") for x in self._all("aig_system", org)):
            raise AigovStateError("An AI system with that name is already proposed or approved.")
        s = {"id": uuid.uuid4().hex, "org": org, "ref": None, "name": name, "description": desc, "origin": origin, "vendor_name": vendor or None, "intended_use": use, "out_of_scope": out, "risk_tier": tier,
             "data_categories": data or None, "human_oversight": oversight or None, "owner_name": owner, "status": "PROPOSED", "proposed_by": actor, "proposed_at": self.now().isoformat(),
             "decided_by": None, "decided_at": None, "decision_note": None, "last_reviewed_on": None, "last_reviewed_by": None, "history": []}
        s["ref"] = self._ref(org, "AI"); self._hist(s, actor, "PROPOSED")
        self._put("aig_system", org, s); self.log("AIGOV_SYSTEM_PROPOSED", actor, s["id"], org, f"{s['ref']} {tier}")
        return self._sview(s)

    def _sdecide(self, org, sid, actor, ok, note) -> dict:
        s = self._get("aig_system", org, sid, "AI system", for_update=True)
        if s["status"] != "PROPOSED": raise AigovStateError("Only a proposed AI system can be approved or rejected.")
        self._two(actor, s["proposed_by"], "proposed this AI system")
        note = _txt(note, "A reason", 10, 500, required=not ok)
        s.update(status="APPROVED" if ok else "REJECTED", decided_by=actor, decided_at=self.now().isoformat(), decision_note=note or None); self._hist(s, actor, "APPROVED" if ok else "REJECTED", note)
        self._put("aig_system", org, s); self.log("AIGOV_SYSTEM_APPROVED" if ok else "AIGOV_SYSTEM_REJECTED", actor, sid, org, s["ref"])
        return self._sview(s)

    def aig_approve_system(self, org, sid, actor, note="") -> dict: return self._sdecide(org, sid, actor, True, note)
    def aig_reject_system(self, org, sid, reason, actor) -> dict: return self._sdecide(org, sid, actor, False, reason)

    def aig_retire_system(self, org, sid, reason, actor) -> dict:
        s = self._get("aig_system", org, sid, "AI system", for_update=True)
        if s["status"] != "APPROVED": raise AigovStateError("Only an approved AI system can be retired.")
        reason = _txt(reason, "A reason", 10, 500)
        if any(c["system_id"] == sid and c["status"] == "RECORDED" for c in self._all("aig_change", org)): raise AigovStateError("This system has a change waiting for approval. Approve or reject it first.")
        if any(i["system_id"] == sid and i["status"] == "RECORDED" for i in self._all("aig_incident", org)): raise AigovStateError("This system has an incident that has not been reviewed. Review or void it first.")
        s.update(status="RETIRED", decision_note=reason); self._hist(s, actor, "RETIRED", reason)
        self._put("aig_system", org, s); self.log("AIGOV_SYSTEM_RETIRED", actor, sid, org, s["ref"])
        return self._sview(s)

    def aig_review_system(self, org, sid, note, actor) -> dict:
        s = self._get("aig_system", org, sid, "AI system", for_update=True)
        if s["status"] != "APPROVED": raise AigovStateError("Only an approved AI system can be reviewed.")
        self._two(actor, s["proposed_by"], "proposed this AI system")
        note = _txt(note, "The review note", 10, 500)
        s.update(last_reviewed_on=self.today().isoformat(), last_reviewed_by=actor); self._hist(s, actor, "REVIEWED", note)
        self._put("aig_system", org, s); self.log("AIGOV_SYSTEM_REVIEWED", actor, sid, org, s["ref"])
        return self._sview(s)

    def aig_list_systems(self, org, status=None, tier=None) -> List[dict]:
        return [self._sview(s) for s in sorted(self._all("aig_system", org), key=refnum) if (not status or s["status"] == status) and (not tier or s["risk_tier"] == tier)]

    def aig_get_system(self, org, sid) -> dict: return self._sview(self._get("aig_system", org, sid, "AI system"))

    # ------------------------------------------------------------------ model changes
    def aig_record_change(self, org, d, actor) -> dict:
        s = self._approved_system(org, d.get("system_id"), "A change")
        kind = _enum(d.get("change_kind"), CHANGE_KINDS, "The kind of change")
        before = _txt(d.get("from_version"), "The version before", 1, 60); after = _txt(d.get("to_version"), "The version after", 1, 60)
        if before.casefold() == after.casefold(): raise AigovError("The version after must differ from the version before.")
        desc = _txt(d.get("description"), "What changed", 10, 1000); on = _date(d.get("effective_on"), "The date of the change"); self._not_future(on, "The date of the change")
        testing = _txt(d.get("testing_summary"), "How it was tested", 10, 1000); ev = self._evidence(org, d.get("evidence_ids"))
        if s["risk_tier"] == "HIGH" and not ev: raise AigovError("A change to a high-risk AI system needs a linked test document from the Evidence Vault.")
        c = {"id": uuid.uuid4().hex, "org": org, "ref": None, "system_id": s["id"], "system_ref": s["ref"], "system_name": s["name"], "risk_tier": s["risk_tier"], "change_kind": kind, "from_version": before,
             "to_version": after, "description": desc, "effective_on": on.isoformat(), "testing_summary": testing, "evidence": ev, "status": "RECORDED", "recorded_by": actor, "recorded_at": self.now().isoformat(),
             "decided_by": None, "decision_note": None, "history": []}
        c["ref"] = self._ref(org, "MC"); self._hist(c, actor, "RECORDED")
        self._put("aig_change", org, c); self.log("AIGOV_CHANGE_RECORDED", actor, c["id"], org, f"{c['ref']} {s['ref']}")
        return {x: c[x] for x in c if x != "org"}

    def _cdecide(self, org, cid, actor, ok, note) -> dict:
        c = self._get("aig_change", org, cid, "Change", for_update=True)
        if c["status"] != "RECORDED": raise AigovStateError("Only a recorded change can be approved or rejected.")
        self._two(actor, c["recorded_by"], "recorded this change")
        note = _txt(note, "A reason", 10, 500, required=not ok)
        c.update(status="APPROVED" if ok else "REJECTED", decided_by=actor, decision_note=note or None); self._hist(c, actor, "APPROVED" if ok else "REJECTED", note)
        self._put("aig_change", org, c); self.log("AIGOV_CHANGE_APPROVED" if ok else "AIGOV_CHANGE_REJECTED", actor, cid, org, c["ref"])
        return {x: c[x] for x in c if x != "org"}

    def aig_approve_change(self, org, cid, actor, note="") -> dict: return self._cdecide(org, cid, actor, True, note)
    def aig_reject_change(self, org, cid, reason, actor) -> dict: return self._cdecide(org, cid, actor, False, reason)

    def aig_list_changes(self, org, system_id=None, status=None) -> List[dict]:
        return [{x: c[x] for x in c if x != "org"} for c in sorted(self._all("aig_change", org), key=refnum) if (not system_id or c["system_id"] == system_id) and (not status or c["status"] == status)]

    def aig_get_change(self, org, cid) -> dict:
        c = self._get("aig_change", org, cid, "Change"); return {x: c[x] for x in c if x != "org"}

    # ------------------------------------------------------------------ incidents
    def _iview(self, i) -> dict:
        v = {x: i[x] for x in i if x != "org"}
        v["age_days"] = (self.today() - datetime.fromisoformat(i["recorded_at"]).date()).days
        v["review_overdue"] = i["status"] == "RECORDED" and v["age_days"] > self._settings(i["org"])["incident_review_days"]
        return v

    def aig_record_incident(self, org, d, actor) -> dict:
        s = self._get("aig_system", org, d.get("system_id"), "AI system", for_update=True)
        if s["status"] not in ("APPROVED", "RETIRED"): raise AigovStateError("An incident can only be recorded for an AI system that was approved.")
        kind = _enum(d.get("incident_kind"), INCIDENT_KINDS, "The kind of incident"); sev = _enum(d.get("severity"), SEVERITIES, "The severity")
        desc = _txt(d.get("description"), "What happened", 10, 2000); occ = _date(d.get("occurred_on"), "The date it happened"); self._not_future(occ, "The date it happened")
        dis = _date(d.get("discovered_on"), "The date it was found"); self._not_future(dis, "The date it was found")
        if dis < occ: raise AigovError("It cannot have been found before it happened.")
        harm = _txt(d.get("harm"), "The harm done", 10, 1000, required=sev in ("HIGH", "CRITICAL"))
        people = None
        if d.get("people_affected") not in (None, ""): people = _int(d.get("people_affected"), "The number of people affected", 0, 1000000000)
        ev = self._evidence(org, d.get("evidence_ids"))
        i = {"id": uuid.uuid4().hex, "org": org, "ref": None, "system_id": s["id"], "system_ref": s["ref"], "system_name": s["name"], "incident_kind": kind, "severity": sev, "description": desc,
             "occurred_on": occ.isoformat(), "discovered_on": dis.isoformat(), "harm": harm or None, "people_affected": people, "evidence": ev, "status": "RECORDED", "recorded_by": actor,
             "recorded_at": self.now().isoformat(), "reviewed_by": None, "reviewed_on": None, "cause": None, "corrective_action": None, "void_note": None, "history": []}
        i["ref"] = self._ref(org, "AX"); self._hist(i, actor, "RECORDED")
        self._put("aig_incident", org, i); self.log("AIGOV_INCIDENT_RECORDED", actor, i["id"], org, f"{i['ref']} {sev}")
        return self._iview(i)

    def aig_review_incident(self, org, iid, d, actor) -> dict:
        i = self._get("aig_incident", org, iid, "Incident", for_update=True)
        if i["status"] != "RECORDED": raise AigovStateError("Only a recorded incident can be reviewed.")
        self._two(actor, i["recorded_by"], "recorded this incident")
        cause = _txt(d.get("cause"), "The cause", 10, 1000); action = _txt(d.get("corrective_action"), "The corrective action", 20, 1000)
        i.update(status="REVIEWED", reviewed_by=actor, reviewed_on=self.today().isoformat(), cause=cause, corrective_action=action); self._hist(i, actor, "REVIEWED")
        self._put("aig_incident", org, i); self.log("AIGOV_INCIDENT_REVIEWED", actor, iid, org, i["ref"])
        return self._iview(i)

    def aig_void_incident(self, org, iid, reason, actor) -> dict:
        i = self._get("aig_incident", org, iid, "Incident", for_update=True)
        if i["status"] != "RECORDED": raise AigovStateError("Only an incident that has not been reviewed can be voided.")
        self._two(actor, i["recorded_by"], "recorded this incident")
        reason = _txt(reason, "A reason", 10, 500); i.update(status="VOIDED", void_note=reason); self._hist(i, actor, "VOIDED", reason)
        self._put("aig_incident", org, i); self.log("AIGOV_INCIDENT_VOIDED", actor, iid, org, i["ref"])
        return self._iview(i)

    def aig_list_incidents(self, org, system_id=None, status=None) -> List[dict]:
        return [self._iview(i) for i in sorted(self._all("aig_incident", org), key=refnum) if (not system_id or i["system_id"] == system_id) and (not status or i["status"] == status)]

    def aig_get_incident(self, org, iid) -> dict: return self._iview(self._get("aig_incident", org, iid, "Incident"))

    # ------------------------------------------------------------------ overview
    def aig_overview(self, org) -> dict:
        systems = self.aig_list_systems(org); changes = self.aig_list_changes(org); inc = self.aig_list_incidents(org); ap = [s for s in systems if s["status"] == "APPROVED"]; live = [i for i in inc if i["status"] != "VOIDED"]; att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("SEVERE_INCIDENTS_OPEN", sum(1 for i in inc if i["status"] == "RECORDED" and i["severity"] in ("HIGH", "CRITICAL")), "high or critical incident(s) have not been reviewed.")
        add("INCIDENTS_REVIEW_OVERDUE", sum(1 for i in inc if i["review_overdue"]), "incident(s) have waited longer than your review window.")
        add("SYSTEMS_REVIEW_DUE", sum(1 for s in ap if s["review_due"]), "approved AI system(s) are due for a review under your own interval.")
        add("SYSTEMS_TO_APPROVE", sum(1 for s in systems if s["status"] == "PROPOSED"), "AI system(s) are waiting for a different person to approve them.")
        add("CHANGES_TO_APPROVE", sum(1 for c in changes if c["status"] == "RECORDED"), "model change(s) are waiting for a different person to approve them.")
        add("INCIDENTS_TO_REVIEW", sum(1 for i in inc if i["status"] == "RECORDED"), "incident(s) are waiting for a different person to review them.")
        return {"counts": {"systems_approved": len(ap), "systems_high": sum(1 for s in ap if s["risk_tier"] == "HIGH"), "systems_limited": sum(1 for s in ap if s["risk_tier"] == "LIMITED"),
                           "systems_minimal": sum(1 for s in ap if s["risk_tier"] == "MINIMAL"), "changes_approved": sum(1 for c in changes if c["status"] == "APPROVED"),
                           "incidents": len(live), "incidents_open": sum(1 for i in inc if i["status"] == "RECORDED")},
                "attention": att, "policy": self.aig_get_policy(org), "limitations": LIMITATIONS}

    def aig_options(self, org) -> dict:
        return {"origins": ORIGINS, "tiers": TIERS, "change_kinds": CHANGE_KINDS, "incident_kinds": INCIDENT_KINDS, "severities": SEVERITIES, "limitations": LIMITATIONS}
