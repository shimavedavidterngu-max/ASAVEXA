"""Risk indicators and resilience (records and evidence): key risk indicators, loss events, business impact analysis, continuity tests.

Records (shared document store, per organisation): rs_kri, rs_loss, rs_process, rs_drill, rs_setting.

Principles enforced here
  * Everything here is typed in by people. ASAVEXA applies fixed arithmetic (a reading against the thresholds, a recovery time against the objective) and shows the
    result. It measures nothing itself, connects to no system and cannot tell whether what was typed is true.
  * Thresholds and recovery objectives cannot be changed once approved, so nobody can move the goalposts after seeing a reading. To change one, retire the record
    and propose a new one; a different person approves it.
  * A reading counts only once a different person confirms it. A loss event is reviewed (cause and lesson) by a different person. A continuity test is approved by
    a different person from the one who carried it out.
  * Amounts are exact decimals per currency; currencies are never added together or converted.
Nothing is edited or deleted; records are retired, voided or rejected with a reason. Every step is audited.
"""
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, List

from .errors import ResilienceError, ResilienceForbiddenError, ResilienceNotFoundError, ResilienceStateError

DIRECTIONS = ["HIGHER_IS_WORSE", "LOWER_IS_WORSE"]
LOSS_KINDS = ["LOSS", "NEAR_MISS"]
LOSS_CATEGORIES = ["PROCESS", "PEOPLE", "SYSTEMS", "EXTERNAL", "FRAUD", "COMPLIANCE", "OTHER"]
IMPACTS = ["LOW", "MEDIUM", "HIGH"]
DRILL_TYPES = ["TABLETOP", "FAILOVER", "RESTORE", "COMMUNICATION", "OTHER"]
DEFAULTS = {"drill_days": 365, "loss_review_days": 14}
LIMITATIONS = [
    "ASAVEXA measures nothing and connects to no system. A reading, a loss or a recovery time is what a person typed in, so it is only as true as their records.",
    "A rating compares a confirmed reading with thresholds your own team set and a different person approved. It is arithmetic, not a forecast and not an assessment of how risky anything is.",
    "Thresholds and recovery objectives cannot be changed once approved. To change one, retire it and propose a new one.",
    "'Met' or 'not met' compares the recovery time someone recorded with the objective in force when they recorded it. It does not show the organisation could recover in a real event.",
    "Loss amounts are kept per currency and are never added together or converted. Near misses carry no amount.",
    "ASAVEXA cannot know about a loss, a breach or a test that nobody records, or about relationships nobody declares.",
]


def _utc(): return datetime.now(timezone.utc)


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v)))
    v = " ".join("".join(c if c >= " " and c != "\x7f" else " " for c in v).split())
    if required and len(v) < lo:
        raise ResilienceError(f"{name} is required (at least {lo} characters).")
    if v and len(v) < lo:
        raise ResilienceError(f"{name} needs at least {lo} characters.")
    if len(v) > hi:
        raise ResilienceError(f"{name} is too long (limit {hi} characters).")
    return v


def _date(v, name) -> date:
    try:
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise ResilienceError(f"{name} must be a real date written YYYY-MM-DD.")


def _enum(v, allowed, name) -> str:
    v = _txt(v, name, 1, 40).upper()
    if v not in allowed:
        raise ResilienceError(f"{name} must be one of {', '.join(allowed)}.")
    return v


def _int(v, name, lo, hi) -> int:
    if isinstance(v, bool) or not str(v).strip().isdigit():
        raise ResilienceError(f"{name} must be a whole number from {lo} to {hi}.")
    n = int(str(v).strip())
    if not lo <= n <= hi:
        raise ResilienceError(f"{name} must be a whole number from {lo} to {hi}.")
    return n


_DEC4 = re.compile(r"^-?\d{1,12}(\.\d{1,4})?$")
_MONEY = re.compile(r"^\d{1,13}(\.\d{1,2})?$")


def _dec(v, name) -> Decimal:
    s = str(v).strip() if v is not None and not isinstance(v, bool) else ""
    if not _DEC4.match(s):
        raise ResilienceError(f"{name} must be a number with at most 4 decimal places.")
    return Decimal(s)


def _money(v, name) -> str:
    s = str(v).strip() if v is not None and not isinstance(v, bool) else ""
    if not _MONEY.match(s):
        raise ResilienceError(f"{name} must be a number with at most 2 decimal places.")
    d = Decimal(s)
    if d <= 0:
        raise ResilienceError(f"{name} must be more than zero.")
    return f"{d:.2f}"


def _fmt(d: Decimal) -> str: return format(d.normalize(), "f") if d != d.to_integral() else str(int(d))


def refnum(r) -> int:
    """KR-012 -> 12, so references sort numerically and records made in the same instant keep the order they were made in."""
    try: return int(str(r["ref"]).rsplit("-", 1)[1])
    except (KeyError, IndexError, ValueError): return 0


def rate(direction: str, amber: Decimal, red: Decimal, value: Decimal) -> str:
    """GREEN, AMBER or RED. Fixed arithmetic over the thresholds; the first threshold reached wins."""
    if direction == "HIGHER_IS_WORSE":
        return "RED" if value >= red else "AMBER" if value >= amber else "GREEN"
    return "RED" if value <= red else "AMBER" if value <= amber else "GREEN"


def criticality(imp: dict) -> str:
    vals = set(imp.values())
    return "HIGH" if "HIGH" in vals else "MEDIUM" if "MEDIUM" in vals else "LOW"


class ResilienceService:
    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()

    def _not_future(self, d: date, what: str):
        if d > self.today() + timedelta(days=1):
            raise ResilienceError(f"{what} cannot be in the future.")

    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r.get("org") != org:
            raise ResilienceNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("rs_setting", f"{org}:settings", for_update=for_update)
        if s and s.get("org") == org:
            return s
        return {"id": "settings", "org": org, **DEFAULTS, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("rs_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other:
            raise ResilienceForbiddenError(f"You {what}, so you cannot do this. A different person must.")

    def _evidence(self, org, ids) -> List[dict]:
        out = []
        for i in dict.fromkeys(str(i) for i in (ids or [])):
            try:
                if self.vault is None: raise LookupError
                e = self.vault.get_evidence(org, i)
            except Exception:
                raise ResilienceError("Linked evidence not found in this organisation's Evidence Vault.")
            out.append({"evidence_id": e.id, "filename": e.original_filename, "file_hash": e.file_hash})
        return out

    def _risk(self, org, rid):
        """An optional link to a risk in the Governance, Risk and Compliance register of the same organisation: (id, ref) or (None, None)."""
        if rid in (None, ""): return None, None
        r = self.store.get("grc_risk", f"{org}:{rid}")
        if r is None or r.get("org") != org: raise ResilienceError("Linked risk not found in this organisation's risk register.")
        return r["id"], r.get("ref")

    # ------------------------------------------------------------------ policy
    def rs_get_policy(self, org) -> dict:
        s = self._settings(org)
        return {"drill_days": s["drill_days"], "loss_review_days": s["loss_review_days"], "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"A process not tested for {s['drill_days']} days is flagged as due. A loss event not reviewed within {s['loss_review_days']} days is flagged. These are your own settings, not a standard."}

    def rs_set_policy(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        for k, name, lo, hi in (("drill_days", "The test interval", 30, 1095), ("loss_review_days", "The loss review window", 1, 90)):
            if d.get(k) is not None: s[k] = _int(d[k], name, lo, hi)
        s.update(updated_by=actor, updated_at=self.now().isoformat())
        self._put("rs_setting", org, s)
        self.log("RESILIENCE_POLICY_SET", actor, "settings", org, f"drills {s['drill_days']}, loss review {s['loss_review_days']}")
        return self.rs_get_policy(org)

    # ------------------------------------------------------------------ key risk indicators
    def _rview(self, k, rd) -> dict:
        v = {x: rd[x] for x in ("id", "seq", "value", "as_of", "note", "status", "recorded_by", "recorded_at", "decided_by", "decision_note")}
        v["rating"] = rate(k["direction"], Decimal(k["amber"]), Decimal(k["red"]), Decimal(rd["value"]))
        return v

    def _kview(self, k) -> dict:
        v = {x: k[x] for x in ("id", "ref", "name", "description", "unit", "direction", "amber", "red", "owner_name", "review_days", "risk_id", "risk_ref", "status", "proposed_by", "proposed_at",
                               "decided_by", "decision_note", "history")}
        reads = sorted((self._rview(k, r) for r in k["readings"]), key=lambda r: (r["as_of"], r["seq"]))
        v["readings"] = reads
        conf = [r for r in reads if r["status"] == "CONFIRMED"]
        last = conf[-1] if conf else None
        v["latest"] = last; v["rating"] = last["rating"] if last else None
        v["stale"] = k["status"] == "ACTIVE" and (last is None or date.fromisoformat(last["as_of"]) + timedelta(days=k["review_days"]) < self.today())
        v["pending_readings"] = sum(1 for r in reads if r["status"] == "RECORDED")
        return v

    def rs_propose_kri(self, org, d, actor) -> dict:
        name = _txt(d.get("name"), "The indicator name", 5, 150); desc = _txt(d.get("description"), "What it measures", 10, 1000)
        unit = _txt(d.get("unit"), "The unit", 1, 30); direction = _enum(d.get("direction"), DIRECTIONS, "The direction")
        amber, red = _dec(d.get("amber"), "The amber threshold"), _dec(d.get("red"), "The red threshold")
        if (direction == "HIGHER_IS_WORSE" and not amber < red) or (direction == "LOWER_IS_WORSE" and not amber > red):
            raise ResilienceError("The amber threshold must be reached before the red one: lower than red when higher is worse, higher than red when lower is worse.")
        owner = _txt(d.get("owner_name"), "The owner", 2, 100); days = _int(d.get("review_days"), "How often a reading is expected (days)", 1, 365)
        rid, rref = self._risk(org, d.get("risk_id"))
        if any(x["name"].casefold() == name.casefold() and x["status"] in ("PROPOSED", "ACTIVE") for x in self._all("rs_kri", org)):
            raise ResilienceStateError("An indicator with that name is already proposed or active.")
        k = {"id": uuid.uuid4().hex, "org": org, "ref": None, "name": name, "description": desc, "unit": unit, "direction": direction, "amber": _fmt(amber), "red": _fmt(red), "owner_name": owner,
             "review_days": days, "risk_id": rid, "risk_ref": rref, "status": "PROPOSED", "proposed_by": actor, "proposed_at": self.now().isoformat(), "decided_by": None, "decision_note": None, "readings": [], "history": []}
        k["ref"] = self._ref(org, "KR"); self._hist(k, actor, "PROPOSED")
        self._put("rs_kri", org, k); self.log("RESILIENCE_KRI_PROPOSED", actor, k["id"], org, k["ref"])
        return self._kview(k)

    def _kdecide(self, org, kid, actor, ok, note) -> dict:
        k = self._get("rs_kri", org, kid, "Indicator", for_update=True)
        if k["status"] != "PROPOSED": raise ResilienceStateError("Only a proposed indicator can be approved or rejected.")
        self._two(actor, k["proposed_by"], "proposed this indicator")
        note = _txt(note, "A reason", 10, 500, required=not ok)
        k.update(status="ACTIVE" if ok else "REJECTED", decided_by=actor, decision_note=note or None); self._hist(k, actor, "APPROVED" if ok else "REJECTED", note)
        self._put("rs_kri", org, k); self.log("RESILIENCE_KRI_APPROVED" if ok else "RESILIENCE_KRI_REJECTED", actor, kid, org, k["ref"])
        return self._kview(k)

    def rs_approve_kri(self, org, kid, actor, note="") -> dict: return self._kdecide(org, kid, actor, True, note)
    def rs_reject_kri(self, org, kid, reason, actor) -> dict: return self._kdecide(org, kid, actor, False, reason)

    def rs_retire_kri(self, org, kid, reason, actor) -> dict:
        k = self._get("rs_kri", org, kid, "Indicator", for_update=True)
        if k["status"] != "ACTIVE": raise ResilienceStateError("Only an active indicator can be retired.")
        reason = _txt(reason, "A reason", 10, 500)
        if any(r["status"] == "RECORDED" for r in k["readings"]): raise ResilienceStateError("This indicator has a reading waiting for confirmation. Confirm or reject it first.")
        k.update(status="RETIRED", decision_note=reason); self._hist(k, actor, "RETIRED", reason)
        self._put("rs_kri", org, k); self.log("RESILIENCE_KRI_RETIRED", actor, kid, org, k["ref"])
        return self._kview(k)

    def rs_record_reading(self, org, kid, d, actor) -> dict:
        k = self._get("rs_kri", org, kid, "Indicator", for_update=True)
        if k["status"] != "ACTIVE": raise ResilienceStateError("Readings can only be recorded for an active indicator.")
        val = _dec(d.get("value"), "The reading"); on = _date(d.get("as_of"), "The date of the reading"); self._not_future(on, "The date of the reading")
        if any(r["as_of"] == on.isoformat() and r["status"] != "REJECTED" for r in k["readings"]): raise ResilienceStateError(f"A reading for {on.isoformat()} is already recorded.")
        r = rate(k["direction"], Decimal(k["amber"]), Decimal(k["red"]), val)
        note = _txt(d.get("note"), "A note on the reading", 10, 1000) if r != "GREEN" else _txt(d.get("note"), "A note", 5, 1000, required=False)
        k["readings"].append({"id": uuid.uuid4().hex, "seq": len(k["readings"]) + 1, "value": _fmt(val), "as_of": on.isoformat(), "note": note, "status": "RECORDED", "recorded_by": actor,
                              "recorded_at": self.now().isoformat(), "decided_by": None, "decision_note": None})
        self._hist(k, actor, "READING_RECORDED", f"#{len(k['readings'])}")
        self._put("rs_kri", org, k); self.log("RESILIENCE_READING_RECORDED", actor, kid, org, f"{k['ref']} #{len(k['readings'])} {r}")
        return self._kview(k)

    def _rdecide(self, org, kid, rid, actor, ok, note) -> dict:
        k = self._get("rs_kri", org, kid, "Indicator", for_update=True)
        rd = next((r for r in k["readings"] if r["id"] == rid), None)
        if rd is None: raise ResilienceNotFoundError("Reading not found.")
        if rd["status"] != "RECORDED": raise ResilienceStateError("Only a reading waiting for confirmation can be confirmed or rejected.")
        self._two(actor, rd["recorded_by"], "recorded this reading")
        note = _txt(note, "A reason", 10, 500, required=not ok)
        rd.update(status="CONFIRMED" if ok else "REJECTED", decided_by=actor, decision_note=note or None); self._hist(k, actor, "READING_CONFIRMED" if ok else "READING_REJECTED", f"#{rd['seq']}")
        self._put("rs_kri", org, k); self.log("RESILIENCE_READING_CONFIRMED" if ok else "RESILIENCE_READING_REJECTED", actor, kid, org, f"{k['ref']} #{rd['seq']}")
        return self._kview(k)

    def rs_confirm_reading(self, org, kid, rid, actor) -> dict: return self._rdecide(org, kid, rid, actor, True, "")
    def rs_reject_reading(self, org, kid, rid, reason, actor) -> dict: return self._rdecide(org, kid, rid, actor, False, reason)

    def rs_list_kris(self, org, status=None) -> List[dict]:
        out = []
        for k in sorted(self._all("rs_kri", org), key=refnum):
            if status and k["status"] != status: continue
            v = self._kview(k); v["readings_count"] = len(v["readings"]); out.append(v)
        return out

    def rs_get_kri(self, org, kid) -> dict: return self._kview(self._get("rs_kri", org, kid, "Indicator"))

    # ------------------------------------------------------------------ loss events
    def rs_record_loss(self, org, d, actor) -> dict:
        title = _txt(d.get("title"), "The title", 5, 150); desc = _txt(d.get("description"), "What happened", 10, 2000); cat = _enum(d.get("category"), LOSS_CATEGORIES, "The category")
        kind = _enum(d.get("kind"), LOSS_KINDS, "The kind")
        occ = _date(d.get("occurred_on"), "The date it happened"); self._not_future(occ, "The date it happened")
        dis = _date(d.get("discovered_on"), "The date it was found"); self._not_future(dis, "The date it was found")
        if dis < occ: raise ResilienceError("It cannot have been found before it happened.")
        amount = cur = None
        if kind == "LOSS":
            amount = _money(d.get("amount"), "The amount lost"); cur = _txt(d.get("currency"), "The currency", 3, 3).upper()
            if not cur.isalpha(): raise ResilienceError("The currency is a three-letter code such as NGN or USD.")
        elif d.get("amount") not in (None, "") or d.get("currency") not in (None, ""):
            raise ResilienceError("A near miss has no amount. Record it as a loss if money was lost.")
        rid, rref = self._risk(org, d.get("risk_id")); ev = self._evidence(org, d.get("evidence_ids"))
        e = {"id": uuid.uuid4().hex, "org": org, "ref": None, "title": title, "description": desc, "category": cat, "kind": kind, "occurred_on": occ.isoformat(), "discovered_on": dis.isoformat(),
             "amount": amount, "currency": cur, "risk_id": rid, "risk_ref": rref, "evidence": ev, "status": "RECORDED", "recorded_by": actor, "recorded_at": self.now().isoformat(),
             "reviewed_by": None, "reviewed_on": None, "cause": None, "lesson": None, "void_note": None, "history": []}
        e["ref"] = self._ref(org, "LE"); self._hist(e, actor, "RECORDED")
        self._put("rs_loss", org, e); self.log("RESILIENCE_LOSS_RECORDED", actor, e["id"], org, f"{e['ref']} {kind}")
        return self._lview(e)

    def _lview(self, e) -> dict:
        v = {x: e[x] for x in e if x != "org"}
        v["age_days"] = (self.today() - datetime.fromisoformat(e["recorded_at"]).date()).days
        v["review_overdue"] = e["status"] == "RECORDED" and v["age_days"] > self._settings(e["org"])["loss_review_days"]
        return v

    def rs_review_loss(self, org, lid, d, actor) -> dict:
        e = self._get("rs_loss", org, lid, "Loss event", for_update=True)
        if e["status"] != "RECORDED": raise ResilienceStateError("Only a recorded loss event can be reviewed.")
        self._two(actor, e["recorded_by"], "recorded this loss event")
        cause = _txt(d.get("cause"), "The cause", 10, 1000); lesson = _txt(d.get("lesson"), "What was learned or changed", 20, 1000)
        e.update(status="REVIEWED", reviewed_by=actor, reviewed_on=self.today().isoformat(), cause=cause, lesson=lesson); self._hist(e, actor, "REVIEWED")
        self._put("rs_loss", org, e); self.log("RESILIENCE_LOSS_REVIEWED", actor, lid, org, e["ref"])
        return self._lview(e)

    def rs_void_loss(self, org, lid, reason, actor) -> dict:
        e = self._get("rs_loss", org, lid, "Loss event", for_update=True)
        if e["status"] != "RECORDED": raise ResilienceStateError("Only a loss event that has not been reviewed can be voided.")
        self._two(actor, e["recorded_by"], "recorded this loss event")
        reason = _txt(reason, "A reason", 10, 500); e.update(status="VOIDED", void_note=reason); self._hist(e, actor, "VOIDED", reason)
        self._put("rs_loss", org, e); self.log("RESILIENCE_LOSS_VOIDED", actor, lid, org, e["ref"])
        return self._lview(e)

    def rs_list_losses(self, org, status=None, kind=None) -> List[dict]:
        return [self._lview(e) for e in sorted(self._all("rs_loss", org), key=refnum) if (not status or e["status"] == status) and (not kind or e["kind"] == kind)]

    def rs_get_loss(self, org, lid) -> dict: return self._lview(self._get("rs_loss", org, lid, "Loss event"))

    def _totals(self, org) -> list:
        tot = {}
        for e in self._all("rs_loss", org):
            if e["kind"] == "LOSS" and e["status"] != "VOIDED": tot[e["currency"]] = tot.get(e["currency"], Decimal("0")) + Decimal(e["amount"])
        return [{"currency": c, "total": f"{t:.2f}"} for c, t in sorted(tot.items())]

    # ------------------------------------------------------------------ business processes (impact analysis)
    def _pview(self, org, p, drills=None) -> dict:
        v = {x: p[x] for x in p if x != "org"}
        drills = self._all("rs_drill", org) if drills is None else drills
        done = sorted([d for d in drills if d["process_id"] == p["id"] and d["status"] == "APPROVED"], key=refnum)
        v["drills"] = sum(1 for d in drills if d["process_id"] == p["id"]); v["last_tested_on"] = done[-1]["performed_on"] if done else None
        v["last_result"] = done[-1]["result"] if done else None
        days = self._settings(org)["drill_days"]
        v["drill_due"] = p["status"] == "APPROVED" and (not done or date.fromisoformat(done[-1]["performed_on"]) + timedelta(days=days) < self.today())
        return v

    def rs_propose_process(self, org, d, actor) -> dict:
        name = _txt(d.get("name"), "The process name", 5, 150); desc = _txt(d.get("description"), "What the process does", 10, 1000); owner = _txt(d.get("owner_name"), "The owner", 2, 100)
        rto = _int(d.get("rto_hours"), "The recovery time objective (hours)", 1, 8760); rpo = _int(d.get("rpo_hours"), "The data loss tolerance (hours)", 0, 8760)
        imp = {k: _enum(d.get(f"impact_{k}"), IMPACTS, f"The {k} impact") for k in ("financial", "legal", "reputation")}
        deps = _txt(d.get("dependencies"), "The dependencies", 5, 1000, required=False)
        if any(x["name"].casefold() == name.casefold() and x["status"] in ("PROPOSED", "APPROVED") for x in self._all("rs_process", org)):
            raise ResilienceStateError("A process with that name is already proposed or approved.")
        p = {"id": uuid.uuid4().hex, "org": org, "ref": None, "name": name, "description": desc, "owner_name": owner, "rto_hours": rto, "rpo_hours": rpo, "impacts": imp, "criticality": criticality(imp),
             "dependencies": deps, "status": "PROPOSED", "proposed_by": actor, "proposed_at": self.now().isoformat(), "decided_by": None, "decision_note": None, "history": []}
        p["ref"] = self._ref(org, "BP"); self._hist(p, actor, "PROPOSED")
        self._put("rs_process", org, p); self.log("RESILIENCE_PROCESS_PROPOSED", actor, p["id"], org, f"{p['ref']} {p['criticality']}")
        return self._pview(org, p)

    def _pdecide(self, org, pid, actor, ok, note) -> dict:
        p = self._get("rs_process", org, pid, "Process", for_update=True)
        if p["status"] != "PROPOSED": raise ResilienceStateError("Only a proposed process can be approved or rejected.")
        self._two(actor, p["proposed_by"], "proposed this process")
        note = _txt(note, "A reason", 10, 500, required=not ok)
        p.update(status="APPROVED" if ok else "REJECTED", decided_by=actor, decision_note=note or None); self._hist(p, actor, "APPROVED" if ok else "REJECTED", note)
        self._put("rs_process", org, p); self.log("RESILIENCE_PROCESS_APPROVED" if ok else "RESILIENCE_PROCESS_REJECTED", actor, pid, org, p["ref"])
        return self._pview(org, p)

    def rs_approve_process(self, org, pid, actor, note="") -> dict: return self._pdecide(org, pid, actor, True, note)
    def rs_reject_process(self, org, pid, reason, actor) -> dict: return self._pdecide(org, pid, actor, False, reason)

    def rs_retire_process(self, org, pid, reason, actor) -> dict:
        p = self._get("rs_process", org, pid, "Process", for_update=True)
        if p["status"] != "APPROVED": raise ResilienceStateError("Only an approved process can be retired.")
        reason = _txt(reason, "A reason", 10, 500)
        if any(d["process_id"] == pid and d["status"] == "RECORDED" for d in self._all("rs_drill", org)): raise ResilienceStateError("This process has a test waiting for approval. Approve or reject it first.")
        p.update(status="RETIRED", decision_note=reason); self._hist(p, actor, "RETIRED", reason)
        self._put("rs_process", org, p); self.log("RESILIENCE_PROCESS_RETIRED", actor, pid, org, p["ref"])
        return self._pview(org, p)

    def rs_list_processes(self, org, status=None) -> List[dict]:
        drills = self._all("rs_drill", org)
        return [self._pview(org, p, drills) for p in sorted(self._all("rs_process", org), key=refnum) if not status or p["status"] == status]

    def rs_get_process(self, org, pid) -> dict: return self._pview(org, self._get("rs_process", org, pid, "Process"))

    # ------------------------------------------------------------------ continuity tests
    def rs_record_drill(self, org, d, actor) -> dict:
        p = self._get("rs_process", org, str(d.get("process_id") or ""), "Process")
        if p["status"] != "APPROVED": raise ResilienceStateError("Only an approved process can be tested.")
        dtype = _enum(d.get("drill_type"), DRILL_TYPES, "The type of test"); scenario = _txt(d.get("scenario"), "The scenario", 10, 1000)
        on = _date(d.get("performed_on"), "The date of the test"); self._not_future(on, "The date of the test")
        rec = _int(d.get("achieved_recovery_hours"), "The recovery time achieved (hours)", 0, 8760); loss = _int(d.get("achieved_data_loss_hours"), "The data lost (hours of work)", 0, 8760)
        outcome = _txt(d.get("outcome"), "What happened", 10, 1000)
        rto_met, rpo_met = rec <= p["rto_hours"], loss <= p["rpo_hours"]
        follow = _txt(d.get("follow_up"), "What will be done about it", 10, 1000, required=not (rto_met and rpo_met))
        ev = self._evidence(org, d.get("evidence_ids"))
        t = {"id": uuid.uuid4().hex, "org": org, "ref": None, "process_id": p["id"], "process_ref": p["ref"], "process_name": p["name"], "drill_type": dtype, "scenario": scenario, "performed_on": on.isoformat(),
             "rto_hours": p["rto_hours"], "rpo_hours": p["rpo_hours"], "achieved_recovery_hours": rec, "achieved_data_loss_hours": loss, "rto_met": rto_met, "rpo_met": rpo_met,
             "result": "MET" if rto_met and rpo_met else "NOT_MET", "outcome": outcome, "follow_up": follow, "evidence": ev, "status": "RECORDED", "recorded_by": actor, "recorded_at": self.now().isoformat(),
             "decided_by": None, "decision_note": None, "history": []}
        t["ref"] = self._ref(org, "DR"); self._hist(t, actor, "RECORDED")
        self._put("rs_drill", org, t); self.log("RESILIENCE_DRILL_RECORDED", actor, t["id"], org, f"{t['ref']} {t['result']}")
        return {x: t[x] for x in t if x != "org"}

    def _ddecide(self, org, did, actor, ok, note) -> dict:
        t = self._get("rs_drill", org, did, "Test", for_update=True)
        if t["status"] != "RECORDED": raise ResilienceStateError("Only a recorded test can be approved or rejected.")
        self._two(actor, t["recorded_by"], "carried out this test")
        note = _txt(note, "A note", 10, 500, required=(not ok) or t["result"] == "NOT_MET")
        t.update(status="APPROVED" if ok else "REJECTED", decided_by=actor, decision_note=note or None); self._hist(t, actor, "APPROVED" if ok else "REJECTED", note)
        self._put("rs_drill", org, t); self.log("RESILIENCE_DRILL_APPROVED" if ok else "RESILIENCE_DRILL_REJECTED", actor, did, org, f"{t['ref']} {t['result']}")
        return {x: t[x] for x in t if x != "org"}

    def rs_approve_drill(self, org, did, actor, note="") -> dict: return self._ddecide(org, did, actor, True, note)
    def rs_reject_drill(self, org, did, reason, actor) -> dict: return self._ddecide(org, did, actor, False, reason)

    def rs_list_drills(self, org, process_id=None, status=None) -> List[dict]:
        return [{x: t[x] for x in t if x != "org"} for t in sorted(self._all("rs_drill", org), key=refnum) if (not process_id or t["process_id"] == process_id) and (not status or t["status"] == status)]

    def rs_get_drill(self, org, did) -> dict:
        t = self._get("rs_drill", org, did, "Test"); return {x: t[x] for x in t if x != "org"}

    # ------------------------------------------------------------------ overview
    def rs_overview(self, org) -> dict:
        kris = [self._kview(k) for k in sorted(self._all("rs_kri", org), key=refnum)]; active = [k for k in kris if k["status"] == "ACTIVE"]
        losses = self.rs_list_losses(org); procs = self.rs_list_processes(org); drills = self.rs_list_drills(org); ap = [p for p in procs if p["status"] == "APPROVED"]; att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("KRIS_RED", sum(1 for k in active if k["rating"] == "RED"), "indicator(s) are red on their latest confirmed reading.")
        add("KRIS_AMBER", sum(1 for k in active if k["rating"] == "AMBER"), "indicator(s) are amber on their latest confirmed reading.")
        add("KRIS_STALE", sum(1 for k in active if k["stale"]), "active indicator(s) have no confirmed reading within the interval you set.")
        add("READINGS_TO_CONFIRM", sum(k["pending_readings"] for k in active), "reading(s) are waiting for a different person to confirm them.")
        add("PROPOSALS_TO_APPROVE", sum(1 for k in kris if k["status"] == "PROPOSED") + sum(1 for p in procs if p["status"] == "PROPOSED"), "indicator(s) or process(es) are waiting for a different person to approve them.")
        add("LOSSES_REVIEW_OVERDUE", sum(1 for e in losses if e["review_overdue"]), "loss event(s) have waited longer than your review window.")
        add("PROCESSES_NEVER_TESTED", sum(1 for p in ap if not p["last_tested_on"]), "approved process(es) have never had an approved continuity test.")
        add("PROCESSES_TEST_DUE", sum(1 for p in ap if p["drill_due"] and p["last_tested_on"]), "process(es) are due for a continuity test under your own interval.")
        add("TESTS_NOT_MET", sum(1 for p in ap if p["last_result"] == "NOT_MET"), "process(es) did not meet their recovery objective in their latest approved test.")
        add("TESTS_TO_APPROVE", sum(1 for t in drills if t["status"] == "RECORDED"), "continuity test(s) are waiting for a different person to approve them.")
        live = [e for e in losses if e["status"] != "VOIDED"]
        return {"counts": {"kris_active": len(active), "kris_red": sum(1 for k in active if k["rating"] == "RED"), "kris_amber": sum(1 for k in active if k["rating"] == "AMBER"), "kris_green": sum(1 for k in active if k["rating"] == "GREEN"),
                           "losses": sum(1 for e in live if e["kind"] == "LOSS"), "near_misses": sum(1 for e in live if e["kind"] == "NEAR_MISS"), "processes_approved": len(ap),
                           "processes_high": sum(1 for p in ap if p["criticality"] == "HIGH"), "drills_approved": sum(1 for t in drills if t["status"] == "APPROVED")},
                "loss_totals": self._totals(org), "attention": att, "policy": self.rs_get_policy(org), "limitations": LIMITATIONS}

    def rs_options(self, org) -> dict:
        risks = sorted((r for r in self._all("grc_risk", org) if r.get("status") != "CLOSED"), key=lambda r: r.get("ref", ""))
        return {"directions": DIRECTIONS, "loss_kinds": LOSS_KINDS, "loss_categories": LOSS_CATEGORIES, "impacts": IMPACTS, "drill_types": DRILL_TYPES,
                "risks": [{"id": r["id"], "ref": r.get("ref"), "title": r.get("title") or r.get("name") or r.get("ref")} for r in risks], "limitations": LIMITATIONS}
