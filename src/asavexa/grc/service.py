"""Governance, Risk and Compliance service.

Records (shared document store, per organisation): grc_risk, grc_action, grc_obligation, grc_setting (appetite and reference counters).
Principles enforced here: scores are likelihood x impact entered by people (no invented formula); a reduction from inherent to residual needs a written
reason; accepting a risk above appetite needs a different person; an action is only VERIFIED by someone other than who completed it; an obligation
is 'met' only as a recorded attestation by a named person. Nothing is deleted, and every step is audited."""
import calendar
import csv
import io
import uuid
from datetime import date, datetime, timezone
from typing import Callable, List, Optional

from .errors import GrcError, GrcForbiddenError, GrcNotFoundError, GrcStateError

CATEGORIES = {"STRATEGIC": "Strategic", "OPERATIONAL": "Operational", "FINANCIAL": "Financial", "COMPLIANCE": "Compliance", "TECHNOLOGY": "Technology",
              "REPUTATIONAL": "Reputational", "FRAUD": "Fraud and integrity", "OTHER": "Other"}
TREATMENTS = {"MITIGATE": "Reduce it (mitigate)", "TRANSFER": "Share or insure it (transfer)", "AVOID": "Stop the activity (avoid)", "ACCEPT": "Accept it"}
SOURCE_TYPES = {"LAW": "Law or statute", "REGULATION": "Regulation or regulator rule", "CONTRACT": "Contract or grant condition", "POLICY": "Internal policy", "STANDARD": "Standard or framework", "OTHER": "Other"}
FREQUENCIES = {"ONE_OFF": 0, "MONTHLY": 1, "QUARTERLY": 3, "SEMI_ANNUAL": 6, "ANNUAL": 12}
DEFAULT_APPETITE = 9
DUE_SOON_DAYS = 30
LIKELIHOOD = {1: "Rare", 2: "Unlikely", 3: "Possible", 4: "Likely", 5: "Almost certain"}
IMPACT = {1: "Negligible", 2: "Minor", 3: "Moderate", 4: "Major", 5: "Severe"}
LIMITATIONS = [
    "Scores are judgements entered by people on a 1 to 5 scale. ASAVEXA multiplies them and applies fixed bands; it does not calculate probabilities or money at risk.",
    "A residual score lower than the inherent score is the owner's stated judgement. It is not tested by ASAVEXA unless a linked control has been run in Controls.",
    "'Met' on an obligation is an attestation recorded by a named person. ASAVEXA does not know whether the law or contract was actually satisfied.",
    "ASAVEXA contains no legal text. Every obligation was entered by a person from their own source, and the link to it is theirs to keep current.",
    "This is a management record, not legal advice, an audit opinion or an assurance report.",
]


def _utc(): return datetime.now(timezone.utc)


def band(score: int) -> str:
    return "LOW" if score <= 4 else "MEDIUM" if score <= 9 else "HIGH" if score <= 16 else "CRITICAL"


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v))).strip()
    if required and len(v) < lo:
        raise GrcError(f"{name} is required (at least {lo} characters).")
    if len(v) > hi:
        raise GrcError(f"{name} is too long (limit {hi} characters).")
    return v


def _scale(v, name) -> int:
    return _scale_range(v, name, 1, 5)


def _date(v, name, required=True) -> Optional[date]:
    if v in (None, ""):
        if required:
            raise GrcError(f"{name} is required (a date written YYYY-MM-DD).")
        return None
    try:
        return date.fromisoformat(str(v).strip())
    except ValueError:
        raise GrcError(f"{name} must be a real date written YYYY-MM-DD.")


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


class GrcService:
    def __init__(self, store, controls: Callable[[str], list], vault, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.controls, self.vault, self.log, self.now = store, controls, vault, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()

    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r["org"] != org:
            raise GrcNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("grc_setting", f"{org}:settings", for_update=for_update)
        return s if s else {"id": "settings", "org": org, "appetite": DEFAULT_APPETITE, "counters": {}, "updated_by": None, "updated_at": None}

    def _next_ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("grc_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _control_map(self, org) -> dict:
        out = {}
        for c in self.controls(org) or []:
            g = (lambda k: c.get(k) if isinstance(c, dict) else getattr(c, k, None))
            out[str(g("id"))] = {"id": str(g("id")), "code": g("code"), "name": g("name")}
        return out

    def _clean_controls(self, org, ids) -> List[str]:
        ids = list(dict.fromkeys(str(i) for i in (ids or [])))
        known = self._control_map(org)
        bad = [i for i in ids if i not in known]
        if bad:
            raise GrcError("Linked control not found in this organisation's Controls.")
        return ids

    def _clean_evidence(self, org, ids) -> List[dict]:
        out = []
        for i in dict.fromkeys(str(i) for i in (ids or [])):
            try:
                e = self.vault.get_evidence(org, i)
            except Exception:
                raise GrcError("Linked evidence not found in this organisation's Evidence Vault.")
            out.append({"evidence_id": e.id, "filename": e.original_filename, "file_hash": e.file_hash})
        return out

    # ------------------------------------------------------------------ settings
    def get_settings(self, org) -> dict:
        s = self._settings(org)
        return {"appetite": s["appetite"], "updated_by": s["updated_by"], "updated_at": s["updated_at"], "default": DEFAULT_APPETITE,
                "meaning": f"A residual score above {s['appetite']} (of 25) is outside the organisation's stated risk appetite."}

    def set_appetite(self, org, appetite, actor) -> dict:
        n = _scale_range(appetite, "Risk appetite", 1, 25)
        s = self._settings(org, for_update=True)
        old = s["appetite"]
        s["appetite"], s["updated_by"], s["updated_at"] = n, actor, self.now().isoformat()
        self._put("grc_setting", org, s)
        self.log("GRC_APPETITE_SET", actor, "settings", org, f"{old} -> {n}")
        return self.get_settings(org)

    # ------------------------------------------------------------------ risks
    def _risk_view(self, r, today=None, appetite=None, ctl=None, acts=None) -> dict:
        today = today or self.today()
        appetite = appetite if appetite is not None else self._settings(r["org"])["appetite"]
        v = dict(r)
        v["inherent_score"] = r["inherent_l"] * r["inherent_i"]
        v["residual_score"] = r["residual_l"] * r["residual_i"]
        v["inherent_band"], v["residual_band"] = band(v["inherent_score"]), band(v["residual_score"])
        v["category_text"] = CATEGORIES.get(r["category"], r["category"])
        v["treatment_text"] = TREATMENTS.get(r["treatment"], r["treatment"])
        v["above_appetite"] = v["residual_score"] > appetite
        live = r["status"] != "CLOSED"
        v["review_overdue"] = bool(live and r.get("next_review") and r["next_review"] < today.isoformat())
        ctl = ctl if ctl is not None else self._control_map(r["org"])
        v["controls"] = [ctl.get(i, {"id": i, "code": "?", "name": "(control no longer found)"}) for i in r.get("control_ids", [])]
        acts = [a for a in (acts if acts is not None else self._all("grc_action", r["org"])) if a["risk_id"] == r["id"]]
        v["action_counts"] = {s: sum(1 for a in acts if a["status"] == s) for s in ("OPEN", "DONE", "VERIFIED", "CANCELLED")}
        return v

    def _all(self, kind, org) -> list:
        return [x for _, x in self.store.list(kind, org_id=org, prefix=f"{org}:") if x.get("org") == org]

    def _fields(self, org, d, partial=False, cur=None) -> dict:
        """Validates risk fields; with partial=True only the supplied ones are checked."""
        out = {}
        has = lambda k: (k in d) if partial else True
        if has("title"): out["title"] = _txt(d.get("title"), "Title", 3, 200)
        if has("description"): out["description"] = _txt(d.get("description"), "Description", 0, 2000, required=False)
        if has("category"):
            c = (d.get("category") or "OTHER").upper()
            if c not in CATEGORIES: raise GrcError("Choose a risk category from the list.")
            out["category"] = c
        if has("owner"): out["owner"] = _txt(d.get("owner"), "Risk owner", 2, 100)
        for k in ("inherent_l", "inherent_i"):
            if has(k): out[k] = _scale(d.get(k), {"inherent_l": "Inherent likelihood", "inherent_i": "Inherent impact"}[k])
        for k in ("residual_l", "residual_i"):
            if k in d and d.get(k) not in (None, ""): out[k] = _scale(d.get(k), {"residual_l": "Residual likelihood", "residual_i": "Residual impact"}[k])
        if has("treatment"):
            t = (d.get("treatment") or "MITIGATE").upper()
            if t not in TREATMENTS: raise GrcError("Choose a treatment from the list.")
            out["treatment"] = t
        if "residual_justification" in d: out["residual_justification"] = _txt(d.get("residual_justification"), "Reason for the lower residual score", 0, 1000, required=False)
        if has("next_review"):
            nr = _date(d.get("next_review"), "Next review date", required=not partial)
            out["next_review"] = nr.isoformat() if nr else None
        if "control_ids" in d: out["control_ids"] = self._clean_controls(org, d.get("control_ids"))
        return out

    def _check_residual(self, r):
        r["residual_l"], r["residual_i"] = r.get("residual_l") or r["inherent_l"], r.get("residual_i") or r["inherent_i"]
        if r["residual_l"] * r["residual_i"] < r["inherent_l"] * r["inherent_i"] and len(r.get("residual_justification", "")) < 10:
            raise GrcError("A residual score lower than the inherent score needs a written reason (at least 10 characters) saying what reduces the risk.")
        if r["residual_l"] * r["residual_i"] > r["inherent_l"] * r["inherent_i"]:
            raise GrcError("The residual score cannot be higher than the inherent score. Raise the inherent score if the underlying risk is greater.")

    def create_risk(self, org, data, actor) -> dict:
        f = self._fields(org, data)
        f.setdefault("control_ids", [])
        f.setdefault("residual_justification", "")
        r = {"id": uuid.uuid4().hex, "org": org, "ref": self._next_ref(org, "R"), "status": "ASSESSED", "created_by": actor, "created_at": self.now().isoformat(), "updated_at": self.now().isoformat(),
             "acceptance": None, "closed_by": None, "close_note": "", "history": [], **f}
        r["residual_l"], r["residual_i"] = f.get("residual_l"), f.get("residual_i")
        self._check_residual(r)
        r["history"].append({"at": r["created_at"], "by": actor, "event": "CREATED", "note": f"inherent {r['inherent_l']}x{r['inherent_i']}, residual {r['residual_l']}x{r['residual_i']}"})
        self._put("grc_risk", org, r)
        self.log("GRC_RISK_CREATED", actor, r["id"], org, r["ref"])
        return self._risk_view(r)

    def _editable(self, r):
        if r["status"] not in ("ASSESSED", "TREATING"):
            raise GrcStateError(f"A risk that is {r['status'].replace('_', ' ').lower()} cannot be edited.")

    def update_risk(self, org, rid, data, actor) -> dict:
        r = self._get("grc_risk", org, rid, "Risk", for_update=True)
        self._editable(r)
        before = (r["inherent_l"], r["inherent_i"], r["residual_l"], r["residual_i"])
        f = self._fields(org, data, partial=True)
        if ("inherent_l" in f or "inherent_i" in f) and not ("residual_l" in f or "residual_i" in f) and before[2:] == before[:2]:
            f.setdefault("residual_l", f.get("inherent_l", r["inherent_l"])); f.setdefault("residual_i", f.get("inherent_i", r["inherent_i"]))
        r.update(f)
        self._check_residual(r)
        after = (r["inherent_l"], r["inherent_i"], r["residual_l"], r["residual_i"])
        r["updated_at"] = self.now().isoformat()
        r["history"].append({"at": r["updated_at"], "by": actor, "event": "UPDATED", "note": ("scores changed " + str(before) + " -> " + str(after)) if before != after else "details updated"})
        self._put("grc_risk", org, r)
        self.log("GRC_RISK_UPDATED", actor, rid, org, r["ref"])
        return self._risk_view(r)

    def _step(self, r, actor, event, note=""):
        r["updated_at"] = self.now().isoformat()
        r["history"].append({"at": r["updated_at"], "by": actor, "event": event, "note": note})

    def start_treatment(self, org, rid, actor) -> dict:
        r = self._get("grc_risk", org, rid, "Risk", for_update=True)
        if r["status"] != "ASSESSED":
            raise GrcStateError("Only an assessed risk can move to treatment.")
        if r["treatment"] == "ACCEPT":
            raise GrcStateError("This risk's chosen treatment is to accept it. Use 'accept' instead, or change the treatment first.")
        r["status"] = "TREATING"; self._step(r, actor, "TREATMENT_STARTED", TREATMENTS[r["treatment"]])
        self._put("grc_risk", org, r); self.log("GRC_RISK_TREATING", actor, rid, org, r["ref"])
        return self._risk_view(r)

    def request_acceptance(self, org, rid, justification, review_by, actor) -> dict:
        r = self._get("grc_risk", org, rid, "Risk", for_update=True)
        if r["status"] not in ("ASSESSED", "TREATING"):
            raise GrcStateError("Only an assessed or treating risk can be put forward for acceptance.")
        j = _txt(justification, "Reason for accepting the risk", 20, 1500)
        rb = _date(review_by, "Review-by date")
        if rb <= self.today():
            raise GrcError("The review-by date must be in the future: an accepted risk has to be looked at again.")
        score, appetite = r["residual_l"] * r["residual_i"], self._settings(org)["appetite"]
        within = score <= appetite
        r["acceptance"] = {"requested_by": actor, "requested_at": self.now().isoformat(), "justification": j, "review_by": rb.isoformat(), "residual_score": score, "appetite": appetite,
                           "within_appetite": within, "decided_by": actor if within else None, "decided_at": self.now().isoformat() if within else None, "decision_note": "Within the stated risk appetite." if within else ""}
        if within:
            r["status"] = "ACCEPTED"; r["next_review"] = rb.isoformat()
            self._step(r, actor, "ACCEPTED", f"within appetite ({score} of {appetite}); review by {rb}")
        else:
            r["status"] = "ACCEPTANCE_REQUESTED"
            self._step(r, actor, "ACCEPTANCE_REQUESTED", f"above appetite ({score} of {appetite}); needs a second person")
        self._put("grc_risk", org, r); self.log("GRC_RISK_ACCEPTED" if within else "GRC_ACCEPTANCE_REQUESTED", actor, rid, org, r["ref"])
        return self._risk_view(r)

    def _decide_acceptance(self, org, rid, actor, approve, note):
        r = self._get("grc_risk", org, rid, "Risk", for_update=True)
        if r["status"] != "ACCEPTANCE_REQUESTED":
            raise GrcStateError("This risk is not waiting for an acceptance decision.")
        a = r["acceptance"]
        if actor == a["requested_by"]:
            raise GrcForbiddenError("You asked for this acceptance, so you cannot decide it. A different person must.")
        note = _txt(note, "Decision note", 5 if not approve else 0, 1000, required=not approve)
        a.update(decided_by=actor, decided_at=self.now().isoformat(), decision_note=note)
        if approve:
            r["status"] = "ACCEPTED"; r["next_review"] = a["review_by"]; self._step(r, actor, "ACCEPTANCE_APPROVED", note)
        else:
            r["status"] = "ASSESSED"; self._step(r, actor, "ACCEPTANCE_REJECTED", note)
        self._put("grc_risk", org, r); self.log("GRC_ACCEPTANCE_APPROVED" if approve else "GRC_ACCEPTANCE_REJECTED", actor, rid, org, r["ref"])
        return self._risk_view(r)

    def approve_acceptance(self, org, rid, actor, note="") -> dict: return self._decide_acceptance(org, rid, actor, True, note)
    def reject_acceptance(self, org, rid, actor, note) -> dict: return self._decide_acceptance(org, rid, actor, False, note)

    def reopen_risk(self, org, rid, reason, actor) -> dict:
        """An accepted risk whose review has come round (or whose circumstances changed) goes back to ASSESSED so it can be re-scored, treated or re-accepted."""
        r = self._get("grc_risk", org, rid, "Risk", for_update=True)
        if r["status"] not in ("ACCEPTED", "CLOSED"):
            raise GrcStateError("Only an accepted or closed risk needs reopening.")
        reason = _txt(reason, "Reason for reopening", 5, 500)
        r["status"] = "ASSESSED"; r["acceptance"] = None; r["closed_by"] = None; r["close_note"] = ""
        self._step(r, actor, "REOPENED", reason)
        self._put("grc_risk", org, r); self.log("GRC_RISK_REOPENED", actor, rid, org, r["ref"])
        return self._risk_view(r)

    def close_risk(self, org, rid, note, actor) -> dict:
        r = self._get("grc_risk", org, rid, "Risk", for_update=True)
        if r["status"] == "CLOSED":
            raise GrcStateError("This risk is already closed.")
        if r["status"] == "ACCEPTANCE_REQUESTED":
            raise GrcStateError("Decide the pending acceptance first.")
        open_actions = [a for a in self._all("grc_action", org) if a["risk_id"] == rid and a["status"] in ("OPEN", "DONE")]
        if open_actions:
            raise GrcStateError("This risk still has actions that are open or not yet verified. Verify or cancel them first.")
        note = _txt(note, "Reason for closing", 10, 1000)
        r["status"], r["closed_by"], r["close_note"] = "CLOSED", actor, note
        self._step(r, actor, "CLOSED", note)
        self._put("grc_risk", org, r); self.log("GRC_RISK_CLOSED", actor, rid, org, r["ref"])
        return self._risk_view(r)

    def get_risk(self, org, rid) -> dict:
        v = self._risk_view(self._get("grc_risk", org, rid, "Risk"))
        v["actions"] = [self._action_view(a) for a in sorted(self._all("grc_action", org), key=lambda a: a["ref"]) if a["risk_id"] == rid]
        return v

    def list_risks(self, org, status=None, category=None) -> List[dict]:
        t, ap, ctl = self.today(), self._settings(org)["appetite"], self._control_map(org)
        acts = self._all("grc_action", org)
        out = []
        for r in sorted(self._all("grc_risk", org), key=lambda r: r["ref"]):
            if status and r["status"] != status: continue
            if category and r["category"] != category: continue
            v = self._risk_view(r, t, ap, ctl, acts)
            out.append(v)
        return out

    # ------------------------------------------------------------------ actions
    def _action_view(self, a) -> dict:
        v = dict(a)
        v["overdue"] = a["status"] == "OPEN" and a["due"] < self.today().isoformat()
        return v

    def create_action(self, org, data, actor) -> dict:
        r = self._get("grc_risk", org, data.get("risk_id"), "Risk")
        if r["status"] == "CLOSED":
            raise GrcStateError("This risk is closed. Reopen it before adding actions.")
        due = _date(data.get("due"), "Due date")
        a = {"id": uuid.uuid4().hex, "org": org, "ref": self._next_ref(org, "A"), "risk_id": r["id"], "risk_ref": r["ref"], "title": _txt(data.get("title"), "Title", 3, 200),
             "description": _txt(data.get("description"), "Description", 0, 2000, required=False), "owner": _txt(data.get("owner"), "Action owner", 2, 100), "due": due.isoformat(),
             "status": "OPEN", "created_by": actor, "created_at": self.now().isoformat(), "completed_by": None, "completed_at": None, "completion_note": "", "evidence": [],
             "verified_by": None, "verified_at": None, "verify_note": "", "cancel_note": ""}
        self._put("grc_action", org, a); self.log("GRC_ACTION_CREATED", actor, a["id"], org, f"{a['ref']} for {r['ref']}")
        return self._action_view(a)

    def update_action(self, org, aid, data, actor) -> dict:
        a = self._get("grc_action", org, aid, "Action", for_update=True)
        if a["status"] != "OPEN":
            raise GrcStateError("Only an open action can be edited.")
        if "title" in data: a["title"] = _txt(data["title"], "Title", 3, 200)
        if "description" in data: a["description"] = _txt(data["description"], "Description", 0, 2000, required=False)
        if "owner" in data: a["owner"] = _txt(data["owner"], "Action owner", 2, 100)
        if "due" in data: a["due"] = _date(data["due"], "Due date").isoformat()
        self._put("grc_action", org, a); self.log("GRC_ACTION_UPDATED", actor, aid, org, a["ref"])
        return self._action_view(a)

    def complete_action(self, org, aid, note, evidence_ids, actor) -> dict:
        a = self._get("grc_action", org, aid, "Action", for_update=True)
        if a["status"] != "OPEN":
            raise GrcStateError("Only an open action can be marked done.")
        a["completion_note"] = _txt(note, "What was done", 10, 1500)
        a["evidence"] = self._clean_evidence(org, evidence_ids)
        a.update(status="DONE", completed_by=actor, completed_at=self.now().isoformat())
        self._put("grc_action", org, a); self.log("GRC_ACTION_DONE", actor, aid, org, a["ref"])
        return self._action_view(a)

    def _verify(self, org, aid, actor, ok, note):
        a = self._get("grc_action", org, aid, "Action", for_update=True)
        if a["status"] != "DONE":
            raise GrcStateError("Only an action marked done can be verified or sent back.")
        if actor == a["completed_by"]:
            raise GrcForbiddenError("You completed this action, so you cannot verify it. A different person must.")
        note = _txt(note, "Verification note", 0 if ok else 5, 1000, required=not ok)
        if ok:
            a.update(status="VERIFIED", verified_by=actor, verified_at=self.now().isoformat(), verify_note=note)
        else:
            a.update(status="OPEN", verify_note=note, completed_by=None, completed_at=None)
        self._put("grc_action", org, a); self.log("GRC_ACTION_VERIFIED" if ok else "GRC_ACTION_SENT_BACK", actor, aid, org, a["ref"])
        return self._action_view(a)

    def verify_action(self, org, aid, actor, note="") -> dict: return self._verify(org, aid, actor, True, note)
    def reject_action(self, org, aid, actor, note) -> dict: return self._verify(org, aid, actor, False, note)

    def cancel_action(self, org, aid, note, actor) -> dict:
        a = self._get("grc_action", org, aid, "Action", for_update=True)
        if a["status"] != "OPEN":
            raise GrcStateError("Only an open action can be cancelled.")
        a["cancel_note"] = _txt(note, "Reason for cancelling", 5, 500); a["status"] = "CANCELLED"
        self._put("grc_action", org, a); self.log("GRC_ACTION_CANCELLED", actor, aid, org, a["ref"])
        return self._action_view(a)

    def list_actions(self, org, risk_id=None, status=None) -> List[dict]:
        return [self._action_view(a) for a in sorted(self._all("grc_action", org), key=lambda a: a["ref"]) if (not risk_id or a["risk_id"] == risk_id) and (not status or a["status"] == status)]

    # ------------------------------------------------------------------ obligations
    def _ob_view(self, o) -> dict:
        v = dict(o)
        t = self.today()
        v["source_text"] = SOURCE_TYPES.get(o["source_type"], o["source_type"])
        if o["status"] == "RETIRED": v["state"] = "RETIRED"
        elif o["next_due"] is None: v["state"] = "MET"
        else:
            d = date.fromisoformat(o["next_due"])
            v["state"] = "OVERDUE" if d < t else "DUE_SOON" if (d - t).days <= DUE_SOON_DAYS else "ON_TRACK"
            v["days_to_due"] = (d - t).days
        ctl = self._control_map(o["org"])
        v["controls"] = [ctl.get(i, {"id": i, "code": "?", "name": "(control no longer found)"}) for i in o.get("control_ids", [])]
        return v

    def create_obligation(self, org, data, actor) -> dict:
        st = (data.get("source_type") or "OTHER").upper()
        fq = (data.get("frequency") or "ONE_OFF").upper()
        if st not in SOURCE_TYPES: raise GrcError("Choose where the obligation comes from.")
        if fq not in FREQUENCIES: raise GrcError("Choose how often the obligation recurs.")
        url = _txt(data.get("source_url"), "Source link", 0, 500, required=False)
        if url and not url.lower().startswith(("http://", "https://")):
            raise GrcError("The source link must start with http:// or https://.")
        o = {"id": uuid.uuid4().hex, "org": org, "ref": self._next_ref(org, "O"), "title": _txt(data.get("title"), "Title", 3, 200), "source_type": st,
             "authority": _txt(data.get("authority"), "Authority or counterparty", 2, 200), "source_ref": _txt(data.get("source_ref"), "Where in the source (section, clause)", 0, 300, required=False),
             "source_url": url, "description": _txt(data.get("description"), "What must be done", 5, 2000), "owner": _txt(data.get("owner"), "Obligation owner", 2, 100),
             "frequency": fq, "next_due": _date(data.get("next_due"), "Next due date").isoformat(), "control_ids": self._clean_controls(org, data.get("control_ids")),
             "status": "ACTIVE", "created_by": actor, "created_at": self.now().isoformat(), "history": [], "retire_note": ""}
        self._put("grc_obligation", org, o); self.log("GRC_OBLIGATION_CREATED", actor, o["id"], org, o["ref"])
        return self._ob_view(o)

    def update_obligation(self, org, oid, data, actor) -> dict:
        o = self._get("grc_obligation", org, oid, "Obligation", for_update=True)
        if o["status"] == "RETIRED": raise GrcStateError("A retired obligation cannot be edited.")
        for k, lo, hi, req in [("title", 3, 200, True), ("authority", 2, 200, True), ("owner", 2, 100, True), ("description", 5, 2000, True), ("source_ref", 0, 300, False)]:
            if k in data: o[k] = _txt(data[k], k.replace("_", " ").capitalize(), lo, hi, required=req)
        if "source_url" in data:
            url = _txt(data["source_url"], "Source link", 0, 500, required=False)
            if url and not url.lower().startswith(("http://", "https://")): raise GrcError("The source link must start with http:// or https://.")
            o["source_url"] = url
        if "next_due" in data and o["next_due"] is not None: o["next_due"] = _date(data["next_due"], "Next due date").isoformat()
        if "frequency" in data:
            fq = (data["frequency"] or "").upper()
            if fq not in FREQUENCIES: raise GrcError("Choose how often the obligation recurs.")
            o["frequency"] = fq
        if "control_ids" in data: o["control_ids"] = self._clean_controls(org, data["control_ids"])
        self._put("grc_obligation", org, o); self.log("GRC_OBLIGATION_UPDATED", actor, oid, org, o["ref"])
        return self._ob_view(o)

    def mark_met(self, org, oid, met_on, note, evidence_ids, actor) -> dict:
        o = self._get("grc_obligation", org, oid, "Obligation", for_update=True)
        if o["status"] == "RETIRED": raise GrcStateError("A retired obligation cannot be marked as met.")
        if o["next_due"] is None: raise GrcStateError("This one-off obligation has already been marked as met.")
        m = _date(met_on, "Date met")
        if m > self.today(): raise GrcError("The date met cannot be in the future.")
        due = date.fromisoformat(o["next_due"])
        o["history"].append({"due": o["next_due"], "met_on": m.isoformat(), "late": m > due, "by": actor, "at": self.now().isoformat(), "note": _txt(note, "Note on how it was met", 5, 1000),
                             "evidence": self._clean_evidence(org, evidence_ids)})
        months = FREQUENCIES[o["frequency"]]
        o["next_due"] = add_months(due, months).isoformat() if months else None
        self._put("grc_obligation", org, o); self.log("GRC_OBLIGATION_MET", actor, oid, org, f"{o['ref']} due {due}")
        return self._ob_view(o)

    def retire_obligation(self, org, oid, note, actor) -> dict:
        o = self._get("grc_obligation", org, oid, "Obligation", for_update=True)
        if o["status"] == "RETIRED": raise GrcStateError("This obligation is already retired.")
        o["status"], o["retire_note"] = "RETIRED", _txt(note, "Reason for retiring", 5, 500)
        self._put("grc_obligation", org, o); self.log("GRC_OBLIGATION_RETIRED", actor, oid, org, o["ref"])
        return self._ob_view(o)

    def list_obligations(self, org, state=None) -> List[dict]:
        out = [self._ob_view(o) for o in sorted(self._all("grc_obligation", org), key=lambda o: o["ref"])]
        return [o for o in out if not state or o["state"] == state]

    def get_obligation(self, org, oid) -> dict: return self._ob_view(self._get("grc_obligation", org, oid, "Obligation"))

    def options(self, org) -> dict:
        return {"categories": CATEGORIES, "treatments": TREATMENTS, "source_types": SOURCE_TYPES, "frequencies": list(FREQUENCIES), "likelihood": LIKELIHOOD, "impact": IMPACT,
                "bands": {"LOW": "1 to 4", "MEDIUM": "5 to 9", "HIGH": "10 to 16", "CRITICAL": "17 to 25"}, "controls": self.controls_available(org), "settings": self.get_settings(org), "limitations": LIMITATIONS}

    def controls_available(self, org) -> List[dict]: return sorted(self._control_map(org).values(), key=lambda c: str(c["code"]))

    # ------------------------------------------------------------------ dashboard and export
    def dashboard(self, org) -> dict:
        t = self.today()
        risks = self.list_risks(org)
        live = [r for r in risks if r["status"] != "CLOSED"]
        acts, obs = self.list_actions(org), [o for o in self.list_obligations(org) if o["state"] != "RETIRED"]
        heat = [[0] * 5 for _ in range(5)]
        for r in live: heat[r["residual_l"] - 1][r["residual_i"] - 1] += 1
        has_plan = lambda r: r["action_counts"]["OPEN"] + r["action_counts"]["DONE"] + r["action_counts"]["VERIFIED"] > 0
        top = lambda r: {k: r[k] for k in ("id", "ref", "title", "owner", "residual_score", "residual_band", "status", "category_text")}
        return {
            "as_of": t.isoformat(), "appetite": self._settings(org)["appetite"],
            "counts": {"risks": len(risks), "live_risks": len(live), "critical_or_high": sum(1 for r in live if r["residual_band"] in ("HIGH", "CRITICAL")), "above_appetite": sum(1 for r in live if r["above_appetite"]),
                       "actions_open": sum(1 for a in acts if a["status"] == "OPEN"), "actions_awaiting_verification": sum(1 for a in acts if a["status"] == "DONE"),
                       "obligations": len(obs), "obligations_overdue": sum(1 for o in obs if o["state"] == "OVERDUE"), "obligations_due_soon": sum(1 for o in obs if o["state"] == "DUE_SOON")},
            "heatmap": {"likelihood_labels": LIKELIHOOD, "impact_labels": IMPACT, "cells": heat, "meaning": "Rows are residual likelihood (1 at top), columns residual impact. Counts are live (not closed) risks."},
            "by_band": {b: sum(1 for r in live if r["residual_band"] == b) for b in ("LOW", "MEDIUM", "HIGH", "CRITICAL")},
            "by_category": {CATEGORIES[c]: n for c in CATEGORIES if (n := sum(1 for r in live if r["category"] == c))},
            "top_risks": [top(r) for r in sorted(live, key=lambda r: (-r["residual_score"], r["ref"]))[:8]],
            "attention": {
                "above_appetite_without_plan": [top(r) for r in live if r["above_appetite"] and r["status"] in ("ASSESSED", "TREATING") and not has_plan(r)],
                "acceptances_waiting": [top(r) for r in live if r["status"] == "ACCEPTANCE_REQUESTED"],
                "reviews_overdue": [dict(top(r), next_review=r["next_review"]) for r in live if r["review_overdue"]],
                "actions_overdue": [{k: a[k] for k in ("id", "ref", "title", "owner", "due", "risk_ref")} for a in acts if a["overdue"]],
                "actions_to_verify": [{k: a[k] for k in ("id", "ref", "title", "owner", "completed_by", "risk_ref")} for a in acts if a["status"] == "DONE"],
                "obligations_overdue": [{k: o[k] for k in ("id", "ref", "title", "owner", "next_due")} for o in obs if o["state"] == "OVERDUE"],
                "obligations_due_soon": [{k: o[k] for k in ("id", "ref", "title", "owner", "next_due")} for o in obs if o["state"] == "DUE_SOON"],
            },
            "limitations": LIMITATIONS,
        }

    def export_csv(self, org, actor) -> dict:
        d = self.dashboard(org); buf = io.StringIO(); w = csv.writer(buf)
        def safe(v):
            v = "" if v is None else str(v)
            return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v
        w.writerow(["CONFIDENTIAL - ASAVEXA governance, risk and compliance register. Scores are people's judgements; not legal advice or an audit opinion."])
        w.writerow(["As of", d["as_of"], "Risk appetite (max residual score)", d["appetite"]]); w.writerow([])
        w.writerow(["RISKS"]); w.writerow(["Ref", "Title", "Category", "Owner", "Inherent", "Residual", "Band", "Above appetite", "Treatment", "Status", "Next review", "Linked controls"])
        for r in self.list_risks(org):
            w.writerow([r["ref"], safe(r["title"]), r["category_text"], safe(r["owner"]), r["inherent_score"], r["residual_score"], r["residual_band"], "yes" if r["above_appetite"] else "no",
                        r["treatment_text"], r["status"], r.get("next_review") or "", safe("; ".join(c["code"] or "" for c in r["controls"]))])
        w.writerow([]); w.writerow(["ACTIONS"]); w.writerow(["Ref", "Risk", "Title", "Owner", "Due", "Status", "Completed by", "Verified by"])
        for a in self.list_actions(org):
            w.writerow([a["ref"], a["risk_ref"], safe(a["title"]), safe(a["owner"]), a["due"], a["status"] + (" (overdue)" if a["overdue"] else ""), a["completed_by"] or "", a["verified_by"] or ""])
        w.writerow([]); w.writerow(["OBLIGATIONS"]); w.writerow(["Ref", "Title", "Source type", "Authority", "Where in source", "Owner", "Frequency", "Next due", "State"])
        for o in self.list_obligations(org):
            w.writerow([o["ref"], safe(o["title"]), o["source_text"], safe(o["authority"]), safe(o["source_ref"]), safe(o["owner"]), o["frequency"], o["next_due"] or "", o["state"]])
        w.writerow([]); w.writerow(["LIMITATIONS"])
        for l in LIMITATIONS: w.writerow([l])
        self.log("GRC_REGISTER_EXPORTED", actor, "register", org, "")
        return {"filename": f"asavexa-grc-register-{d['as_of']}.csv", "content": buf.getvalue(), "content_type": "text/csv; charset=utf-8"}


def _scale_range(v, name, lo, hi) -> int:
    try:
        if isinstance(v, bool): raise ValueError
        n = int(str(v).strip())
    except (TypeError, ValueError):
        raise GrcError(f"{name} must be a whole number from {lo} to {hi}.")
    if not lo <= n <= hi:
        raise GrcError(f"{name} must be a whole number from {lo} to {hi}.")
    return n
