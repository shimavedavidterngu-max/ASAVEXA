"""Company secretarial (records and evidence): meetings and minutes, resolutions, and a register of statutory filings.

Records (shared document store, per organisation): cs_meeting, cs_resolution, cs_filing, cs_setting.

Principles enforced here
  * This records what people say happened at a meeting, what was voted and what was filed. ASAVEXA does not check company law, the articles of association, quorum, notice periods or whether anything was really filed.
  * Minutes are approved by a person other than the one who recorded them. A resolution is decided by a person other than the one who proposed it. A filing is confirmed by a person other than the one who recorded it as filed.
  * A resolution put to a meeting can be decided only after minutes of that meeting exist.
Nothing is edited or deleted; records are cancelled, withdrawn or decided with a reason. Every step is audited. No legal compliance is claimed.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Callable, List

from .errors import SecretarialError, SecretarialForbiddenError, SecretarialNotFoundError, SecretarialStateError

MEETING_KINDS = ["BOARD", "COMMITTEE", "ANNUAL_GENERAL", "GENERAL", "OTHER"]
RESOLUTION_KINDS = ["ORDINARY", "SPECIAL", "WRITTEN"]
FILING_KINDS = ["ANNUAL_RETURN", "ACCOUNTS", "CHANGE_OF_DIRECTORS", "CHANGE_OF_ADDRESS", "SHARE_CHANGE", "TAX_RETURN", "LICENCE_RENEWAL", "OTHER"]
DEFAULTS = {"due_soon_days": 14}
LIMITATIONS = [
    "ASAVEXA records what people type in. It does not check company law, your articles of association, who may attend or vote, quorum, or notice periods.",
    "A resolution is marked passed only if more votes were recorded for than against. Any higher threshold your articles or the law require (for example for a special resolution) is not checked.",
    "A filing marked filed or confirmed is a person's statement and a reference they typed. ASAVEXA does not contact any registry and cannot tell whether it was really filed or accepted.",
    "Approved minutes are not a signed statutory record. Keep the signed originals in the Evidence Vault or wherever your law requires.",
    "ASAVEXA cannot know about a meeting, resolution or filing obligation that nobody records.",
]


def _utc(): return datetime.now(timezone.utc)


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v)))
    v = " ".join("".join(c if c >= " " and c != "\x7f" else " " for c in v).split())
    if required and len(v) < lo:
        raise SecretarialError(f"{name} is required (at least {lo} characters).")
    if v and len(v) < lo:
        raise SecretarialError(f"{name} needs at least {lo} characters.")
    if len(v) > hi:
        raise SecretarialError(f"{name} is too long (limit {hi} characters).")
    return v


def _date(v, name) -> date:
    try:
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise SecretarialError(f"{name} must be a real date written YYYY-MM-DD.")


def _enum(v, allowed, name) -> str:
    v = _txt(v, name, 1, 40).upper()
    if v not in allowed:
        raise SecretarialError(f"{name} must be one of {', '.join(allowed)}.")
    return v


def _int(v, name, lo, hi) -> int:
    if isinstance(v, bool) or not str(v).strip().isdigit():
        raise SecretarialError(f"{name} must be a whole number from {lo} to {hi}.")
    n = int(str(v).strip())
    if not lo <= n <= hi:
        raise SecretarialError(f"{name} must be a whole number from {lo} to {hi}.")
    return n


def refnum(r) -> int:
    try: return int(str(r["ref"]).rsplit("-", 1)[1])
    except (KeyError, IndexError, ValueError): return 0


class SecretarialService:
    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()

    def _not_future(self, d: date, what: str):
        if d > self.today() + timedelta(days=1):
            raise SecretarialError(f"{what} cannot be in the future.")

    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r.get("org") != org:
            raise SecretarialNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("cs_setting", f"{org}:settings", for_update=for_update)
        if s and s.get("org") == org:
            return s
        return {"id": "settings", "org": org, **DEFAULTS, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("cs_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other:
            raise SecretarialForbiddenError(f"You {what}, so you cannot do this. A different person must.")

    def _evidence(self, org, ids) -> List[dict]:
        out = []
        for i in dict.fromkeys(str(i) for i in (ids or [])):
            try:
                if self.vault is None: raise LookupError
                e = self.vault.get_evidence(org, i)
            except Exception:
                raise SecretarialError("Linked evidence not found in this organisation's Evidence Vault.")
            out.append({"evidence_id": e.id, "filename": e.original_filename, "file_hash": e.file_hash})
        return out

    # ------------------------------------------------------------------ policy
    def cs_get_policy(self, org) -> dict:
        s = self._settings(org)
        return {"due_soon_days": s["due_soon_days"], "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"An open filing due within {s['due_soon_days']} days is flagged as due soon. This is your own setting, not a legal deadline."}

    def cs_set_policy(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        if d.get("due_soon_days") is not None: s["due_soon_days"] = _int(d["due_soon_days"], "The days before a filing is due soon", 1, 90)
        s.update(updated_by=actor, updated_at=self.now().isoformat())
        self._put("cs_setting", org, s)
        self.log("SECRETARIAL_POLICY_SET", actor, "settings", org, f"due soon {s['due_soon_days']} days")
        return self.cs_get_policy(org)

    # ------------------------------------------------------------------ meetings
    def _mview(self, m) -> dict:
        v = {x: m[x] for x in m if x != "org"}
        v["record_due"] = m["status"] == "SCHEDULED" and date.fromisoformat(m["held_on"]) < self.today()
        v["resolutions"] = [self._rview(r) for r in sorted((r for r in self._all("cs_resolution", m["org"]) if r.get("meeting_id") == m["id"]), key=refnum)]
        return v

    def cs_schedule_meeting(self, org, d, actor) -> dict:
        kind = _enum(d.get("kind"), MEETING_KINDS, "The kind of meeting"); title = _txt(d.get("title"), "The title", 5, 150); on = _date(d.get("held_on"), "The meeting date")
        if on > self.today() + timedelta(days=730): raise SecretarialError("The meeting date is more than two years away.")
        place = _txt(d.get("location"), "The location", 2, 150); agenda = _txt(d.get("agenda"), "The agenda", 10, 2000)
        m = {"id": uuid.uuid4().hex, "org": org, "ref": None, "kind": kind, "title": title, "held_on": on.isoformat(), "location": place, "agenda": agenda, "status": "SCHEDULED", "scheduled_by": actor, "scheduled_at": self.now().isoformat(),
             "attendees": None, "minutes": None, "minutes_by": None, "evidence": [], "approved_by": None, "approve_note": None, "cancel_note": None, "history": []}
        m["ref"] = self._ref(org, "MT"); self._hist(m, actor, "SCHEDULED")
        self._put("cs_meeting", org, m); self.log("SECRETARIAL_MEETING_SCHEDULED", actor, m["id"], org, f"{m['ref']} {kind}")
        return self._mview(m)

    def cs_record_minutes(self, org, mid, d, actor) -> dict:
        m = self._get("cs_meeting", org, mid, "Meeting", for_update=True)
        if m["status"] != "SCHEDULED": raise SecretarialStateError("Minutes can only be recorded for a meeting that is scheduled.")
        if date.fromisoformat(m["held_on"]) > self.today() + timedelta(days=1): raise SecretarialError("Minutes cannot be recorded before the meeting date.")
        att = _txt(d.get("attendees"), "Who attended", 3, 1000); minutes = _txt(d.get("minutes"), "The minutes", 20, 8000); ev = self._evidence(org, d.get("evidence_ids"))
        m.update(status="HELD", attendees=att, minutes=minutes, minutes_by=actor, evidence=ev); self._hist(m, actor, "MINUTES_RECORDED")
        self._put("cs_meeting", org, m); self.log("SECRETARIAL_MINUTES_RECORDED", actor, mid, org, m["ref"])
        return self._mview(m)

    def cs_approve_minutes(self, org, mid, d, actor) -> dict:
        m = self._get("cs_meeting", org, mid, "Meeting", for_update=True)
        if m["status"] != "HELD": raise SecretarialStateError("Only minutes that were recorded and not yet approved can be approved.")
        self._two(actor, m["minutes_by"], "recorded these minutes")
        note = _txt(d.get("note"), "An approval note", 10, 1000, required=False)
        m.update(status="MINUTES_APPROVED", approved_by=actor, approve_note=note or None); self._hist(m, actor, "MINUTES_APPROVED", note)
        self._put("cs_meeting", org, m); self.log("SECRETARIAL_MINUTES_APPROVED", actor, mid, org, m["ref"])
        return self._mview(m)

    def cs_cancel_meeting(self, org, mid, reason, actor) -> dict:
        m = self._get("cs_meeting", org, mid, "Meeting", for_update=True)
        if m["status"] != "SCHEDULED": raise SecretarialStateError("Only a meeting that is still scheduled can be cancelled.")
        if any(r["status"] == "PROPOSED" for r in self._all("cs_resolution", org) if r.get("meeting_id") == mid):
            raise SecretarialStateError("Withdraw or decide the resolutions put to this meeting first.")
        reason = _txt(reason, "A reason", 10, 500); m.update(status="CANCELLED", cancel_note=reason); self._hist(m, actor, "CANCELLED", reason)
        self._put("cs_meeting", org, m); self.log("SECRETARIAL_MEETING_CANCELLED", actor, mid, org, m["ref"])
        return self._mview(m)

    def cs_list_meetings(self, org, status=None) -> List[dict]:
        return [self._mview(m) for m in sorted(self._all("cs_meeting", org), key=refnum) if not status or m["status"] == status]

    def cs_get_meeting(self, org, mid) -> dict: return self._mview(self._get("cs_meeting", org, mid, "Meeting"))

    # ------------------------------------------------------------------ resolutions
    def _rview(self, r) -> dict:
        v = {x: r[x] for x in r if x != "org"}
        m = self.store.get("cs_meeting", f"{r['org']}:{r['meeting_id']}") if r.get("meeting_id") else None
        v["meeting_ref"] = m["ref"] if m else None
        v["meeting_status"] = m["status"] if m else None
        v["can_decide"] = r["status"] == "PROPOSED" and (r["kind"] == "WRITTEN" or (m is not None and m["status"] in ("HELD", "MINUTES_APPROVED")))
        return v

    def cs_propose_resolution(self, org, d, actor) -> dict:
        kind = _enum(d.get("kind"), RESOLUTION_KINDS, "The kind of resolution"); text = _txt(d.get("text"), "The resolution", 20, 3000)
        mid = d.get("meeting_id")
        if kind == "WRITTEN":
            if mid: raise SecretarialError("A written resolution is not put to a meeting.")
            m = None
        else:
            m = self._get("cs_meeting", org, mid, "Meeting")
            if m["status"] not in ("SCHEDULED", "HELD"): raise SecretarialStateError("A resolution can only be put to a meeting that is scheduled or held and not yet approved.")
        r = {"id": uuid.uuid4().hex, "org": org, "ref": None, "kind": kind, "text": text, "meeting_id": m["id"] if m else None, "status": "PROPOSED", "proposed_by": actor, "proposed_at": self.now().isoformat(),
             "votes_for": None, "votes_against": None, "abstentions": None, "decided_by": None, "decided_on": None, "decision_note": None, "withdraw_note": None, "history": []}
        r["ref"] = self._ref(org, "RS"); self._hist(r, actor, "PROPOSED")
        self._put("cs_resolution", org, r); self.log("SECRETARIAL_RESOLUTION_PROPOSED", actor, r["id"], org, f"{r['ref']} {kind}")
        return self._rview(r)

    def cs_decide_resolution(self, org, rid, d, actor) -> dict:
        r = self._get("cs_resolution", org, rid, "Resolution", for_update=True)
        if r["status"] != "PROPOSED": raise SecretarialStateError("Only a resolution that is still proposed can be decided.")
        if not self._rview(r)["can_decide"]: raise SecretarialStateError("Minutes of the meeting must be recorded before its resolutions can be decided.")
        self._two(actor, r["proposed_by"], "proposed this resolution")
        vf = _int(d.get("votes_for"), "Votes for", 0, 100000); va = _int(d.get("votes_against"), "Votes against", 0, 100000); ab = _int(d.get("abstentions"), "Abstentions", 0, 100000)
        outcome = _enum(d.get("outcome"), ["PASSED", "FAILED"], "The outcome"); note = _txt(d.get("note"), "A decision note", 10, 1000)
        if vf + va + ab == 0: raise SecretarialError("Record how many voted. At least one vote or abstention is needed.")
        if outcome == "PASSED" and vf <= va: raise SecretarialError("A resolution cannot be recorded as passed unless more votes were for than against.")
        r.update(status=outcome, votes_for=vf, votes_against=va, abstentions=ab, decided_by=actor, decided_on=self.today().isoformat(), decision_note=note); self._hist(r, actor, outcome, note)
        self._put("cs_resolution", org, r); self.log("SECRETARIAL_RESOLUTION_DECIDED", actor, rid, org, f"{r['ref']} {outcome}")
        return self._rview(r)

    def cs_withdraw_resolution(self, org, rid, reason, actor) -> dict:
        r = self._get("cs_resolution", org, rid, "Resolution", for_update=True)
        if r["status"] != "PROPOSED": raise SecretarialStateError("Only a resolution that is still proposed can be withdrawn.")
        reason = _txt(reason, "A reason", 10, 500); r.update(status="WITHDRAWN", withdraw_note=reason); self._hist(r, actor, "WITHDRAWN", reason)
        self._put("cs_resolution", org, r); self.log("SECRETARIAL_RESOLUTION_WITHDRAWN", actor, rid, org, r["ref"])
        return self._rview(r)

    def cs_list_resolutions(self, org, meeting_id=None, status=None) -> List[dict]:
        return [self._rview(r) for r in sorted(self._all("cs_resolution", org), key=refnum) if (not meeting_id or r.get("meeting_id") == meeting_id) and (not status or r["status"] == status)]

    def cs_get_resolution(self, org, rid) -> dict: return self._rview(self._get("cs_resolution", org, rid, "Resolution"))

    # ------------------------------------------------------------------ filings register
    def _fview(self, f) -> dict:
        v = {x: f[x] for x in f if x != "org"}
        t = self.today(); due = date.fromisoformat(f["due_on"])
        v["overdue"] = f["status"] == "OPEN" and due < t
        v["due_soon"] = f["status"] == "OPEN" and t <= due <= t + timedelta(days=self._settings(f["org"])["due_soon_days"])
        return v

    def cs_add_filing(self, org, d, actor) -> dict:
        kind = _enum(d.get("kind"), FILING_KINDS, "The kind of filing"); title = _txt(d.get("title"), "The title", 5, 150); auth = _txt(d.get("authority"), "The authority or registry", 2, 150)
        due = _date(d.get("due_on"), "The due date")
        if due > self.today() + timedelta(days=1825): raise SecretarialError("The due date is more than five years away.")
        owner = _txt(d.get("owner_name"), "The owner", 2, 100)
        f = {"id": uuid.uuid4().hex, "org": org, "ref": None, "kind": kind, "title": title, "authority": auth, "due_on": due.isoformat(), "owner_name": owner, "status": "OPEN", "added_by": actor, "added_at": self.now().isoformat(),
             "filed_on": None, "filed_by": None, "receipt_ref": None, "evidence": [], "confirmed_by": None, "confirm_note": None, "withdraw_note": None, "history": []}
        f["ref"] = self._ref(org, "FL"); self._hist(f, actor, "ADDED")
        self._put("cs_filing", org, f); self.log("SECRETARIAL_FILING_ADDED", actor, f["id"], org, f"{f['ref']} {kind}")
        return self._fview(f)

    def cs_file_filing(self, org, fid, d, actor) -> dict:
        f = self._get("cs_filing", org, fid, "Filing", for_update=True)
        if f["status"] != "OPEN": raise SecretarialStateError("Only an open filing can be recorded as filed.")
        on = _date(d.get("filed_on"), "The date it was filed"); self._not_future(on, "The date it was filed")
        if on < date.fromisoformat(f["added_at"][:10]) - timedelta(days=365): raise SecretarialError("The filing date is more than a year before this record was made.")
        receipt = _txt(d.get("receipt_ref"), "The receipt or reference from the authority", 3, 150); ev = self._evidence(org, d.get("evidence_ids"))
        f.update(status="FILED", filed_on=on.isoformat(), filed_by=actor, receipt_ref=receipt, evidence=ev); self._hist(f, actor, "FILED")
        self._put("cs_filing", org, f); self.log("SECRETARIAL_FILING_FILED", actor, fid, org, f["ref"])
        return self._fview(f)

    def cs_confirm_filing(self, org, fid, d, actor) -> dict:
        f = self._get("cs_filing", org, fid, "Filing", for_update=True)
        if f["status"] != "FILED": raise SecretarialStateError("Only a filing that was recorded as filed can be confirmed.")
        self._two(actor, f["filed_by"], "recorded this filing as filed")
        note = _txt(d.get("note"), "A confirmation note", 10, 1000)
        f.update(status="CONFIRMED", confirmed_by=actor, confirm_note=note); self._hist(f, actor, "CONFIRMED", note)
        self._put("cs_filing", org, f); self.log("SECRETARIAL_FILING_CONFIRMED", actor, fid, org, f["ref"])
        return self._fview(f)

    def cs_withdraw_filing(self, org, fid, reason, actor) -> dict:
        f = self._get("cs_filing", org, fid, "Filing", for_update=True)
        if f["status"] != "OPEN": raise SecretarialStateError("Only an open filing can be withdrawn.")
        reason = _txt(reason, "A reason", 10, 500); f.update(status="WITHDRAWN", withdraw_note=reason); self._hist(f, actor, "WITHDRAWN", reason)
        self._put("cs_filing", org, f); self.log("SECRETARIAL_FILING_WITHDRAWN", actor, fid, org, f["ref"])
        return self._fview(f)

    def cs_list_filings(self, org, status=None) -> List[dict]:
        return [self._fview(f) for f in sorted(self._all("cs_filing", org), key=refnum) if not status or f["status"] == status]

    def cs_get_filing(self, org, fid) -> dict: return self._fview(self._get("cs_filing", org, fid, "Filing"))

    # ------------------------------------------------------------------ overview
    def cs_overview(self, org) -> dict:
        ms = self.cs_list_meetings(org); rs = self.cs_list_resolutions(org); fs = self.cs_list_filings(org); att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("FILINGS_OVERDUE", sum(1 for f in fs if f["overdue"]), "filing(s) are past their due date and not recorded as filed.")
        add("FILINGS_DUE_SOON", sum(1 for f in fs if f["due_soon"]), "filing(s) are due soon.")
        add("FILINGS_TO_CONFIRM", sum(1 for f in fs if f["status"] == "FILED"), "filing(s) are waiting for a different person to confirm them.")
        add("MEETINGS_TO_RECORD", sum(1 for m in ms if m["record_due"]), "meeting(s) have passed their date and have no minutes yet.")
        add("MINUTES_TO_APPROVE", sum(1 for m in ms if m["status"] == "HELD"), "set(s) of minutes are waiting for a different person to approve them.")
        add("RESOLUTIONS_TO_DECIDE", sum(1 for r in rs if r["can_decide"]), "resolution(s) are ready for a different person to decide.")
        return {"counts": {"meetings_scheduled": sum(1 for m in ms if m["status"] == "SCHEDULED"), "meetings_held": sum(1 for m in ms if m["status"] in ("HELD", "MINUTES_APPROVED")),
                           "resolutions_passed": sum(1 for r in rs if r["status"] == "PASSED"), "resolutions_failed": sum(1 for r in rs if r["status"] == "FAILED"), "resolutions_open": sum(1 for r in rs if r["status"] == "PROPOSED"),
                           "filings_open": sum(1 for f in fs if f["status"] == "OPEN"), "filings_filed": sum(1 for f in fs if f["status"] == "FILED"), "filings_confirmed": sum(1 for f in fs if f["status"] == "CONFIRMED")},
                "attention": att, "policy": self.cs_get_policy(org), "limitations": LIMITATIONS}

    def cs_options(self, org) -> dict:
        return {"meeting_kinds": MEETING_KINDS, "resolution_kinds": RESOLUTION_KINDS, "filing_kinds": FILING_KINDS, "limitations": LIMITATIONS}
