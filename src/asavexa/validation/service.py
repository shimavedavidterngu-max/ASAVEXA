"""Professional validation: independent professionals review the pipeline
   Accounting treatment -> Controls -> Evidence -> Reporting -> Audit workflow -> Security -> Professional judgement
and the platform records WHO concluded WHAT, on WHICH snapshot of the data, and whether the rules for a valid review were met.

Principles (each is enforced in code and tested):
  * Software never validates. Outcomes are computed only from reviews SIGNED by identified reviewers.
  * A review counts only if the reviewer was assigned, declared independence, is active, and holds a specialism relevant to the stage.
  * Credentials are 'declared' until someone records how they were verified; the platform never claims to have checked them itself.
  * A signed review is immutable; a changed mind is a new version that supersedes the old one, and the old one stays on record.
  * Reviews attest to a frozen snapshot of the data; if the data changes afterwards the statement says so.
  * Major and critical observations need a management response before an engagement can complete.
  * The completed statement carries a hash (and a key-signed MAC when keys exist) so tampering is detectable."""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import date, datetime, timezone
from typing import Callable, Dict, List, Optional

from .catalog import BODIES, CONCLUSIONS, DISCLAIMER, RESPONSES, SEVERITIES, SPECIALISMS, STAGE_IDS, STAGES
from .errors import ProfessionalValidationError as VError, ReviewForbiddenError, ReviewNotFoundError, ReviewStateError


def _utc():
    return datetime.now(timezone.utc)


def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False).encode()


def sha(obj) -> str:
    return hashlib.sha256(canon(obj)).hexdigest()


def _txt(v, name, lo=1, hi=2000, required=True) -> str:
    v = (v or "").strip() if isinstance(v, str) or v is None else str(v).strip()
    if required and len(v) < lo:
        raise VError(f"{name} is required.")
    if len(v) > hi:
        raise VError(f"{name} is too long (limit {hi} characters).")
    return v


class ValidationService:
    def __init__(self, store, log: Callable[..., None] = lambda *a, **k: None, keys=None, now: Callable[[], datetime] = _utc):
        self.store, self.log, self.keys, self.now = store, log, keys, now

    # ------------------------------------------------------------------ panel
    def _rkey(self, org, rid): return f"{org}:{rid}"

    def add_reviewer(self, org: str, actor: str, name: str, email: str, credentials: List[dict], specialisms: List[str],
                     affiliation: str = "", user_id: Optional[str] = None) -> dict:
        name, email = _txt(name, "Name", hi=120), _txt(email, "Email", hi=200).lower()
        if "@" not in email:
            raise VError("Give a valid email address.")
        creds = [self._cred(c) for c in (credentials or [])]
        if not creds:
            raise VError("Record at least one professional or academic credential (it stays 'declared' until someone verifies it).")
        specs = self._specs(specialisms)
        if any(r["email"] == email and r["active"] for _, r in self.store.list("val_reviewer", org_id=org)):
            raise ReviewStateError("A reviewer with this email is already on the panel.")
        if user_id and any(r.get("user_id") == user_id and r["active"] for _, r in self.store.list("val_reviewer", org_id=org)):
            raise ReviewStateError("That user is already linked to a reviewer on the panel.")
        rid = str(uuid.uuid4())
        r = {"id": rid, "org_id": org, "name": name, "email": email, "user_id": user_id or None, "affiliation": _txt(affiliation, "Affiliation", hi=200, required=False),
             "credentials": creds, "specialisms": specs, "active": True, "created_by": actor, "created_at": self.now().isoformat()}
        self.store.put("val_reviewer", self._rkey(org, rid), r, org_id=org)
        self.log("VALIDATION_REVIEWER_ADDED", actor, rid, org, f"{name}")
        return self._reviewer_out(r)

    def _cred(self, c: dict) -> dict:
        body = (c.get("body") or "").upper()
        if body not in BODIES:
            raise VError(f"Unknown professional body '{c.get('body')}'. Use one of: {', '.join(BODIES)}.")
        year = c.get("year_admitted")
        if year not in (None, "") and (not str(year).isdigit() or not 1950 <= int(year) <= self.now().year):
            raise VError("Year admitted must be a real year.")
        return {"body": body, "membership_no": _txt(c.get("membership_no"), "Membership number", hi=60), "jurisdiction": _txt(c.get("jurisdiction"), "Jurisdiction", hi=60, required=False),
                "year_admitted": int(year) if year not in (None, "") else None, "status": "DECLARED", "verified_by": None, "verified_at": None, "method": None, "note": None}

    def _specs(self, specialisms) -> List[str]:
        specs = sorted({str(s).upper() for s in (specialisms or [])})
        bad = [s for s in specs if s not in SPECIALISMS]
        if bad:
            raise VError(f"Unknown specialism(s): {', '.join(bad)}.")
        if not specs:
            raise VError("Choose at least one specialism the reviewer is competent in.")
        return specs

    def update_reviewer(self, org: str, actor: str, rid: str, **fields) -> dict:
        r = self._reviewer(org, rid, for_update=True)
        if "specialisms" in fields and fields["specialisms"] is not None:
            r["specialisms"] = self._specs(fields["specialisms"])
        if fields.get("affiliation") is not None:
            r["affiliation"] = _txt(fields["affiliation"], "Affiliation", hi=200, required=False)
        if fields.get("name"):
            r["name"] = _txt(fields["name"], "Name", hi=120)
        if fields.get("user_id") is not None:
            r["user_id"] = fields["user_id"] or None
        if fields.get("add_credential"):
            r["credentials"].append(self._cred(fields["add_credential"]))
        self.store.put("val_reviewer", self._rkey(org, rid), r, org_id=org)
        self.log("VALIDATION_REVIEWER_UPDATED", actor, rid, org, r["name"])
        return self._reviewer_out(r)

    def verify_credential(self, org: str, actor: str, rid: str, idx: int, accepted: bool, method: str, note: str = "") -> dict:
        """Records HOW someone checked a credential (e.g. 'looked up on the ACCA public register on 2026-10-01'). The platform checks nothing itself."""
        r = self._reviewer(org, rid, for_update=True)
        if not isinstance(idx, int) or not 0 <= idx < len(r["credentials"]):
            raise ReviewNotFoundError("That credential was not found.")
        if r.get("user_id") and r["user_id"] == actor:
            raise ReviewForbiddenError("A reviewer cannot verify their own credentials.")
        c = r["credentials"][idx]
        c.update(status="VERIFIED" if accepted else "REJECTED", verified_by=actor, verified_at=self.now().isoformat(),
                 method=_txt(method, "How it was verified", hi=300), note=_txt(note, "Note", hi=500, required=not accepted))
        self.store.put("val_reviewer", self._rkey(org, rid), r, org_id=org)
        self.log("VALIDATION_CREDENTIAL_VERIFIED" if accepted else "VALIDATION_CREDENTIAL_REJECTED", actor, rid, org, f"{c['body']} {c['membership_no']}: {c['method']}")
        return self._reviewer_out(r)

    def set_active(self, org: str, actor: str, rid: str, active: bool) -> dict:
        r = self._reviewer(org, rid, for_update=True)
        r["active"] = bool(active)
        self.store.put("val_reviewer", self._rkey(org, rid), r, org_id=org)
        self.log("VALIDATION_REVIEWER_ACTIVATED" if active else "VALIDATION_REVIEWER_DEACTIVATED", actor, rid, org, r["name"])
        return self._reviewer_out(r)

    def _reviewer(self, org, rid, for_update=False) -> dict:
        r = self.store.get("val_reviewer", self._rkey(org, rid), for_update=for_update)
        if r is None:
            raise ReviewNotFoundError("Reviewer not found on this organisation's panel.")
        return r

    @staticmethod
    def _reviewer_out(r: dict) -> dict:
        st = [c["status"] for c in r["credentials"]]
        return {**r, "credential_state": "VERIFIED" if st and all(s == "VERIFIED" for s in st) else "PARTLY_VERIFIED" if "VERIFIED" in st else "DECLARED_ONLY"}

    def panel(self, org: str) -> List[dict]:
        return sorted((self._reviewer_out(r) for _, r in self.store.list("val_reviewer", org_id=org)), key=lambda r: (not r["active"], r["name"].lower()))

    def reviewer_for_user(self, org: str, user_id: str) -> Optional[dict]:
        for _, r in self.store.list("val_reviewer", org_id=org):
            if r.get("user_id") == user_id and r["active"]:
                return r
        return None

    # ------------------------------------------------------------------ engagements
    def _ekey(self, org, eid): return f"{org}:{eid}"

    def _eng(self, org, eid, for_update=False) -> dict:
        e = self.store.get("val_engagement", self._ekey(org, eid), for_update=for_update)
        if e is None:
            raise ReviewNotFoundError("Validation engagement not found.")
        return e

    def _save(self, org, e):
        self.store.put("val_engagement", self._ekey(org, e["id"]), e, org_id=org)

    def create_engagement(self, org: str, actor: str, title: str, description: str, as_of: str, snapshot: dict, stages: Optional[List[str]] = None,
                          min_reviewers: Optional[Dict[str, int]] = None) -> dict:
        title = _txt(title, "Title", hi=160)
        try:
            as_of = date.fromisoformat(as_of).isoformat()
        except (TypeError, ValueError):
            raise VError("'As of' must be a date like 2026-09-30: the date the reviewed figures are as at.")
        stage_ids = [s.upper() for s in (stages or STAGE_IDS)]
        if not stage_ids or any(s not in STAGE_IDS for s in stage_ids):
            raise VError(f"Stages must be chosen from: {', '.join(STAGE_IDS)}.")
        stage_ids = [s for s in STAGE_IDS if s in stage_ids]
        mins = {s: 1 for s in stage_ids}
        for k, v in (min_reviewers or {}).items():
            if k.upper() in mins:
                if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 5:
                    raise VError("Reviewers needed per stage must be a whole number from 1 to 5.")
                mins[k.upper()] = v
        eid = str(uuid.uuid4())
        e = {"id": eid, "org_id": org, "title": title, "description": _txt(description, "Description", hi=1500, required=False), "as_of": as_of, "status": "DRAFT",
             "stages": stage_ids, "min_reviewers": mins, "snapshot": snapshot, "snapshot_hash": sha(snapshot), "assignments": [], "declarations": {}, "reviews": [],
             "created_by": actor, "created_at": self.now().isoformat(), "opened_at": None, "completed_at": None, "withdrawn": None, "statement": None}
        self._save(org, e)
        self.log("VALIDATION_ENGAGEMENT_CREATED", actor, eid, org, title)
        return self.detail(org, eid)

    def refresh_snapshot(self, org: str, actor: str, eid: str, snapshot: dict) -> dict:
        e = self._eng(org, eid, True)
        self._must(e, ("DRAFT", "OPEN"), "refresh the snapshot")
        if any(r["status"] == "SIGNED" for r in e["reviews"]):
            raise ReviewStateError("A reviewer has already signed against this snapshot. Start a new engagement to review newer data.")
        e["snapshot"], e["snapshot_hash"] = snapshot, sha(snapshot)
        self._save(org, e)
        self.log("VALIDATION_SNAPSHOT_REFRESHED", actor, eid, org, e["snapshot_hash"][:12])
        return self.detail(org, eid)

    def open(self, org: str, actor: str, eid: str) -> dict:
        e = self._eng(org, eid, True)
        self._must(e, ("DRAFT",), "open")
        e.update(status="OPEN", opened_at=self.now().isoformat())
        self._save(org, e)
        self.log("VALIDATION_ENGAGEMENT_OPENED", actor, eid, org, e["title"])
        return self.detail(org, eid)

    def withdraw(self, org: str, actor: str, eid: str, reason: str) -> dict:
        e = self._eng(org, eid, True)
        self._must(e, ("DRAFT", "OPEN"), "withdraw")
        e["status"] = "WITHDRAWN"
        e["withdrawn"] = {"by": actor, "at": self.now().isoformat(), "reason": _txt(reason, "Reason", hi=500)}
        self._save(org, e)
        self.log("VALIDATION_ENGAGEMENT_WITHDRAWN", actor, eid, org, e["withdrawn"]["reason"])
        return self.detail(org, eid)

    @staticmethod
    def _must(e, states, what):
        if e["status"] not in states:
            raise ReviewStateError(f"This engagement is {e['status'].lower()}, so you cannot {what}.")

    def assign(self, org: str, actor: str, eid: str, stage: str, reviewer_id: str) -> dict:
        e = self._eng(org, eid, True)
        self._must(e, ("DRAFT", "OPEN"), "assign reviewers")
        stage = (stage or "").upper()
        if stage not in e["stages"]:
            raise VError("That stage is not in this engagement's scope.")
        r = self._reviewer(org, reviewer_id)
        if not r["active"]:
            raise ReviewStateError("That reviewer is not active on the panel.")
        if any(a["stage"] == stage and a["reviewer_id"] == reviewer_id for a in e["assignments"]):
            raise ReviewStateError("That reviewer is already assigned to this stage.")
        needed = next(s["specialisms"] for s in STAGES if s["id"] == stage)
        if not set(r["specialisms"]) & set(needed):
            raise VError(f"{r['name']} has not declared a specialism relevant to this stage ({', '.join(needed)}). Add one to their profile if it is true, or choose someone else.")
        e["assignments"].append({"id": str(uuid.uuid4()), "stage": stage, "reviewer_id": reviewer_id, "assigned_by": actor, "assigned_at": self.now().isoformat()})
        self._save(org, e)
        self.log("VALIDATION_REVIEWER_ASSIGNED", actor, eid, org, f"{r['name']} -> {stage}")
        return self.detail(org, eid)

    def unassign(self, org: str, actor: str, eid: str, assignment_id: str) -> dict:
        e = self._eng(org, eid, True)
        self._must(e, ("DRAFT", "OPEN"), "change assignments")
        a = next((a for a in e["assignments"] if a["id"] == assignment_id), None)
        if a is None:
            raise ReviewNotFoundError("Assignment not found.")
        if any(r["status"] == "SIGNED" and r["stage"] == a["stage"] and r["reviewer_id"] == a["reviewer_id"] for r in e["reviews"]):
            raise ReviewStateError("This reviewer has already signed for this stage, so the assignment cannot be removed.")
        e["assignments"] = [x for x in e["assignments"] if x["id"] != assignment_id]
        e["reviews"] = [r for r in e["reviews"] if not (r["stage"] == a["stage"] and r["reviewer_id"] == a["reviewer_id"] and r["status"] == "DRAFT")]
        self._save(org, e)
        self.log("VALIDATION_REVIEWER_UNASSIGNED", actor, eid, org, f"{a['reviewer_id']} from {a['stage']}")
        return self.detail(org, eid)

    # ------------------------------------------------------------------ independence
    def declare_independence(self, org: str, actor: str, eid: str, reviewer_id: str, independent: bool, details: str, confirmations: Dict[str, bool],
                             can_manage: bool = False, source_reference: Optional[str] = None) -> dict:
        """The reviewer's own declaration. Every confirmation must be true for the review to count; otherwise the reviewer cannot sign."""
        e = self._eng(org, eid, True)
        self._must(e, ("DRAFT", "OPEN"), "record a declaration")
        r = self._reviewer(org, reviewer_id)
        on_behalf = self._authority(r, actor, can_manage, source_reference)
        required = ["no_financial_interest", "not_involved_in_preparing_records", "no_close_personal_relationship", "no_other_threat_to_objectivity"]
        conf = {k: bool((confirmations or {}).get(k)) for k in required}
        ok = bool(independent) and all(conf.values())
        if not ok and not (details or "").strip():
            raise VError("If any confirmation is not true, describe the relationship or interest. The reviewer will not be able to sign.")
        e["declarations"][reviewer_id] = {"independent": ok, "confirmations": conf, "details": _txt(details, "Details", hi=800, required=False),
                                          "declared_by": actor, "on_behalf": on_behalf, "source_reference": (source_reference or "").strip()[:300] or None, "declared_at": self.now().isoformat()}
        self._save(org, e)
        self.log("VALIDATION_INDEPENDENCE_DECLARED", actor, eid, org, f"{r['name']}: {'independent' if ok else 'NOT independent'}")
        return self.detail(org, eid)

    def _authority(self, reviewer: dict, actor: str, can_manage: bool, source_reference: Optional[str]) -> bool:
        """Returns True if the action is recorded on the reviewer's behalf. A reviewer linked to a platform user acts only as that user."""
        if reviewer.get("user_id"):
            if reviewer["user_id"] != actor:
                raise ReviewForbiddenError(f"{reviewer['name']} is linked to their own account and must sign in to do this themselves.")
            return False
        if not can_manage:
            raise ReviewForbiddenError(f"{reviewer['name']} is not linked to an account. Only an owner or administrator can record on their behalf.")
        if not (source_reference or "").strip():
            raise VError("Recording on someone's behalf needs a reference to their signed document (for example 'signed PDF received 2026-10-02, ref ABC-17').")
        return True

    # ------------------------------------------------------------------ reviews
    def save_review(self, org: str, actor: str, eid: str, stage: str, reviewer_id: str, content: dict, can_manage: bool = False) -> dict:
        e = self._eng(org, eid, True)
        self._must(e, ("OPEN",), "record reviews")
        stage = (stage or "").upper()
        r = self._reviewer(org, reviewer_id)
        if not any(a["stage"] == stage and a["reviewer_id"] == reviewer_id for a in e["assignments"]):
            raise ReviewForbiddenError("That reviewer is not assigned to this stage.")
        d = e["declarations"].get(reviewer_id)
        if not d:
            raise ReviewStateError("The reviewer must declare independence for this engagement first.")
        if not d["independent"]:
            raise ReviewForbiddenError("The reviewer declared a conflict, so cannot review in this engagement.")
        on_behalf = self._authority(r, actor, can_manage, content.get("source_reference"))
        clean = self._content(content)
        draft = next((x for x in e["reviews"] if x["stage"] == stage and x["reviewer_id"] == reviewer_id and x["status"] == "DRAFT"), None)
        prior = [x for x in e["reviews"] if x["stage"] == stage and x["reviewer_id"] == reviewer_id and x["status"] in ("SIGNED", "SUPERSEDED")]
        if draft is None:
            draft = {"id": str(uuid.uuid4()), "stage": stage, "reviewer_id": reviewer_id, "version": len(prior) + 1, "status": "DRAFT", "created_at": self.now().isoformat()}
            e["reviews"].append(draft)
        draft.update(clean, on_behalf=on_behalf, source_reference=(content.get("source_reference") or "").strip()[:300] or None, recorded_by=actor, updated_at=self.now().isoformat())
        self._save(org, e)
        return self.detail(org, eid)

    def _content(self, c: dict) -> dict:
        concl = (c.get("conclusion") or "").upper()
        if concl and concl not in CONCLUSIONS:
            raise VError(f"Conclusion must be one of: {', '.join(CONCLUSIONS)}.")
        obs = []
        for o in c.get("observations") or []:
            sev = (o.get("severity") or "").upper()
            if sev not in SEVERITIES:
                raise VError(f"Observation severity must be one of: {', '.join(SEVERITIES)}.")
            obs.append({"id": o.get("id") or str(uuid.uuid4()), "severity": sev, "text": _txt(o.get("text"), "Observation", hi=2000), "recommendation": _txt(o.get("recommendation"), "Recommendation", hi=1000, required=False), "response": None})
        return {"conclusion": concl or None, "scope_reviewed": _txt(c.get("scope_reviewed"), "Scope reviewed", hi=1500, required=False),
                "basis": _txt(c.get("basis"), "Basis (framework and standards applied)", hi=800, required=False), "limitations": _txt(c.get("limitations"), "Limitations", hi=1500, required=False),
                "competence_confirmed": bool(c.get("competence_confirmed")), "observations": obs}

    def sign_review(self, org: str, actor: str, eid: str, review_id: str, can_manage: bool = False, current_snapshot_hash: Optional[str] = None) -> dict:
        e = self._eng(org, eid, True)
        self._must(e, ("OPEN",), "sign reviews")
        rv = next((x for x in e["reviews"] if x["id"] == review_id), None)
        if rv is None:
            raise ReviewNotFoundError("Review not found.")
        if rv["status"] != "DRAFT":
            raise ReviewStateError("Only a draft can be signed; a signed review cannot be changed.")
        r = self._reviewer(org, rv["reviewer_id"])
        if not r["active"]:
            raise ReviewStateError("The reviewer is not active on the panel.")
        d = e["declarations"].get(rv["reviewer_id"])
        if not d or not d["independent"]:
            raise ReviewForbiddenError("No valid independence declaration for this reviewer.")
        on_behalf = self._authority(r, actor, can_manage, rv.get("source_reference"))
        needed = next(s["specialisms"] for s in STAGES if s["id"] == rv["stage"])
        if not set(r["specialisms"]) & set(needed):
            raise VError("The reviewer's declared specialisms no longer cover this stage.")
        for field, label in (("conclusion", "a conclusion"), ("scope_reviewed", "what was reviewed"), ("basis", "the basis (framework/standards)")):
            if not rv.get(field):
                raise VError(f"A review needs {label} before it can be signed.")
        if not rv["competence_confirmed"]:
            raise VError("The reviewer must confirm they are competent to give a conclusion on this stage.")
        obs = rv["observations"]
        if rv["conclusion"] in ("CONCURS_WITH_COMMENTS", "DISAGREES") and not obs:
            raise VError("A conclusion with comments or a disagreement must list at least one observation.")
        if rv["conclusion"] == "DISAGREES" and not any(o["severity"] in ("CRITICAL", "MAJOR") for o in obs):
            raise VError("A disagreement must include at least one major or critical observation explaining why.")
        if rv["conclusion"] == "UNABLE_TO_ASSESS" and not rv["limitations"]:
            raise VError("If the reviewer was unable to assess, they must describe the limitation.")
        if current_snapshot_hash and current_snapshot_hash != e["snapshot_hash"]:
            pass   # allowed: the statement will show the data has moved since the snapshot; the review still attests to the snapshot
        for old in e["reviews"]:
            if old["stage"] == rv["stage"] and old["reviewer_id"] == rv["reviewer_id"] and old["status"] == "SIGNED":
                old["status"] = "SUPERSEDED"
                old["superseded_at"] = self.now().isoformat()
        rv.update(status="SIGNED", signed_at=self.now().isoformat(), signed_by=actor, on_behalf=on_behalf,
                  reviewer_snapshot={"name": r["name"], "credentials": [{k: c[k] for k in ("body", "membership_no", "jurisdiction", "status", "method")} for c in r["credentials"]], "specialisms": r["specialisms"]},
                  snapshot_hash=e["snapshot_hash"])
        rv["hash"] = sha({k: rv[k] for k in rv if k not in ("hash",)})
        self._save(org, e)
        self.log("VALIDATION_REVIEW_SIGNED", actor, eid, org, f"{r['name']} / {rv['stage']} / {rv['conclusion']}" + (" (on behalf)" if on_behalf else ""))
        return self.detail(org, eid)

    def respond(self, org: str, actor: str, eid: str, review_id: str, observation_id: str, status: str, note: str) -> dict:
        e = self._eng(org, eid, True)
        self._must(e, ("OPEN",), "respond to observations")
        rv = next((x for x in e["reviews"] if x["id"] == review_id), None)
        o = next((o for o in (rv or {}).get("observations", []) if o["id"] == observation_id), None)
        if rv is None or o is None:
            raise ReviewNotFoundError("Observation not found.")
        if rv["status"] != "SIGNED":
            raise ReviewStateError("Management responds to signed reviews only.")
        status = (status or "").upper()
        if status not in RESPONSES:
            raise VError(f"Response must be one of: {', '.join(RESPONSES)}.")
        o["response"] = {"status": status, "note": _txt(note, "Response note", hi=1000), "by": actor, "at": self.now().isoformat()}
        self._save(org, e)
        self.log("VALIDATION_OBSERVATION_RESPONDED", actor, eid, org, f"{o['severity']}: {status}")
        return self.detail(org, eid)

    # ------------------------------------------------------------------ computed picture
    def _effective(self, e: dict) -> List[dict]:
        """Signed reviews that actually count."""
        out = []
        for rv in e["reviews"]:
            if rv["status"] != "SIGNED":
                continue
            r = self.store.get("val_reviewer", self._rkey(e["org_id"], rv["reviewer_id"]))
            d = e["declarations"].get(rv["reviewer_id"])
            if r and r["active"] and d and d["independent"] and any(a["stage"] == rv["stage"] and a["reviewer_id"] == rv["reviewer_id"] for a in e["assignments"]):
                out.append(rv)
        return out

    def coverage(self, e: dict) -> dict:
        eff = self._effective(e)
        stages, unresolved = [], 0
        for s in STAGES:
            if s["id"] not in e["stages"]:
                continue
            sid, need = s["id"], e["min_reviewers"][s["id"]]
            rvs = [x for x in eff if x["stage"] == sid]
            concl = [x["conclusion"] for x in rvs]
            drafts = [x for x in e["reviews"] if x["stage"] == sid and x["status"] == "DRAFT"]
            assigned = [a for a in e["assignments"] if a["stage"] == sid]
            open_obs = [o for x in rvs for o in x["observations"] if o["severity"] in ("CRITICAL", "MAJOR") and not o["response"]]
            unresolved += len(open_obs)
            if "DISAGREES" in concl:
                st = "COVERED_ADVERSE"
            elif len(rvs) < need:
                st = "IN_PROGRESS" if (rvs or drafts or assigned) else "UNCOVERED"
            elif "UNABLE_TO_ASSESS" in concl:
                st = "COVERED_LIMITED"
            elif "CONCURS_WITH_COMMENTS" in concl:
                st = "COVERED_WITH_COMMENTS"
            else:
                st = "COVERED_CONCUR"
            stages.append({"stage": sid, "label": s["label"], "status": st, "reviewers_needed": need, "signed": len(rvs), "assigned": len(assigned), "drafts": len(drafts),
                           "open_serious_observations": len(open_obs), "meets_minimum": len(rvs) >= need and "UNABLE_TO_ASSESS" not in concl})
        complete = all(s["meets_minimum"] for s in stages)
        adverse = any(s["status"] == "COVERED_ADVERSE" for s in stages)
        reserv = any(s["status"] in ("COVERED_WITH_COMMENTS",) for s in stages) or any(o["severity"] in ("CRITICAL", "MAJOR") for x in eff for o in x["observations"])
        outcome = "INCOMPLETE" if not complete else "NOT_VALIDATED" if adverse else "VALIDATED_WITH_RESERVATIONS" if reserv else "VALIDATED"
        creds = [c["status"] for x in eff for c in x["reviewer_snapshot"]["credentials"]]
        cred_state = "NONE_SIGNED" if not creds else "ALL_VERIFIED" if all(c == "VERIFIED" for c in creds) else "SOME_UNVERIFIED"
        return {"stages": stages, "complete": complete, "outcome": outcome, "unresolved_serious_observations": unresolved, "credential_verification": cred_state}

    def detail(self, org: str, eid: str, current_snapshot_hash: Optional[str] = None) -> dict:
        e = copy.deepcopy(self._eng(org, eid))
        cov = self.coverage(e)
        panel = {rid: self._reviewer_out(r) for rid, r in ((k.split(":", 1)[1], v) for k, v in self.store.list("val_reviewer", org_id=org))}
        e["coverage"] = cov
        e["reviewers"] = {a["reviewer_id"]: panel.get(a["reviewer_id"]) for a in e["assignments"]}
        e["snapshot_is_current"] = None if current_snapshot_hash is None else current_snapshot_hash == e["snapshot_hash"]
        e["disclaimer"] = DISCLAIMER
        return e

    def list_engagements(self, org: str) -> List[dict]:
        out = []
        for _, e in self.store.list("val_engagement", org_id=org):
            cov = self.coverage(e)
            out.append({"id": e["id"], "title": e["title"], "as_of": e["as_of"], "status": e["status"], "created_at": e["created_at"], "outcome": e["statement"]["outcome"] if e.get("statement") else cov["outcome"],
                        "stages_covered": sum(1 for s in cov["stages"] if s["meets_minimum"]), "stages_total": len(cov["stages"])})
        return sorted(out, key=lambda x: x["created_at"], reverse=True)

    # ------------------------------------------------------------------ completion and statement
    def complete(self, org: str, actor: str, eid: str) -> dict:
        e = self._eng(org, eid, True)
        self._must(e, ("OPEN",), "complete")
        cov = self.coverage(e)
        gaps = [s["label"] for s in cov["stages"] if not s["meets_minimum"]]
        if gaps:
            raise ReviewStateError(f"These stages do not yet have enough signed reviews with a conclusion: {', '.join(gaps)}.")
        if cov["unresolved_serious_observations"]:
            raise ReviewStateError(f"{cov['unresolved_serious_observations']} major or critical observation(s) still need a management response.")
        eff = self._effective(e)
        stmt = {"engagement_id": eid, "organisation_id": org, "title": e["title"], "as_of": e["as_of"], "outcome": cov["outcome"], "credential_verification": cov["credential_verification"],
                "snapshot": e["snapshot"], "snapshot_hash": e["snapshot_hash"], "generated_at": self.now().isoformat(), "completed_by": actor, "disclaimer": DISCLAIMER,
                "stages": [{"stage": s["stage"], "label": s["label"], "status": s["status"], "reviews": [
                    {"reviewer": x["reviewer_snapshot"]["name"], "credentials": x["reviewer_snapshot"]["credentials"], "specialisms": x["reviewer_snapshot"]["specialisms"], "conclusion": x["conclusion"],
                     "basis": x["basis"], "scope_reviewed": x["scope_reviewed"], "limitations": x["limitations"], "observations": x["observations"], "signed_at": x["signed_at"],
                     "recorded_on_behalf": x["on_behalf"], "source_reference": x.get("source_reference"), "review_hash": x["hash"]} for x in eff if x["stage"] == s["stage"]]} for s in cov["stages"]],
                "limitations_noted": sorted({x["limitations"] for x in eff if x["limitations"]})}
        stmt["statement_hash"] = sha(stmt)
        if self.keys is not None:
            stmt["mac_key_id"], stmt["mac"] = self.keys.mac("validation-statement", stmt["statement_hash"].encode())
        e.update(status="COMPLETED", completed_at=self.now().isoformat(), statement=stmt)
        self._save(org, e)
        self.log("VALIDATION_ENGAGEMENT_COMPLETED", actor, eid, org, f"{cov['outcome']} ({stmt['statement_hash'][:12]})")
        return self.detail(org, eid)

    def statement(self, org: str, eid: str, current_snapshot_hash: Optional[str] = None) -> dict:
        e = self._eng(org, eid)
        if not e.get("statement"):
            raise ReviewStateError("The statement exists only after the engagement is completed.")
        s = copy.deepcopy(e["statement"])
        s["verification"] = self.verify_statement(s)
        if current_snapshot_hash is not None:
            s["data_unchanged_since_review"] = current_snapshot_hash == s["snapshot_hash"]
        return s

    def verify_statement(self, stmt: dict) -> dict:
        body = {k: v for k, v in stmt.items() if k not in ("statement_hash", "mac", "mac_key_id", "verification", "data_unchanged_since_review")}
        hash_ok = sha(body) == stmt.get("statement_hash")
        mac_ok = None
        if stmt.get("mac"):
            mac_ok = bool(self.keys is not None and self.keys.verify_mac("validation-statement", (stmt.get("statement_hash") or "").encode(), stmt.get("mac_key_id", ""), stmt["mac"]))
        return {"hash_ok": hash_ok, "signature_ok": mac_ok, "ok": hash_ok and mac_ok is not False,
                "note": "The hash proves the statement was not edited. The signature (when present) proves it was issued by this platform's keys. Neither says the reviewers' conclusions are right."}
