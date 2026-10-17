"""Data governance (records and evidence): a register of data assets with an owner, a classification and a retention period, reviewed and access-controlled by different people.

Records (shared document store, per organisation): dg_asset, dg_setting.

Principles enforced here
  * An asset is a kind of data an organisation holds (a name, an owner reference, a classification, whether it holds personal data, a retention period in months and how often it must be reviewed). It is proposed by one person and approved or rejected by a different person. Only an approved asset can be reviewed or have access granted.
  * A review is recorded by one person and confirmed or rejected by a different person. The next review is due the chosen number of months after the last confirmed review (or after approval).
  * An access grant (a person reference, a level, a purpose, start and expiry dates) is proposed by one person and approved or rejected by a different person, and can be revoked with a reason. Every grant has an expiry date: at most three years, and at most one year for a RESTRICTED asset.
  * ASAVEXA holds no data itself, enforces no access and applies no law. It keeps the register, dates and decisions; a person must do the real work. Person references are codes, never names.
Nothing is edited after a decision or deleted. Every step is audited by reference number only.
"""
import calendar
import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Callable, List

from ..wscommon import WsMixin, code, dt, refnum, txt, utc, whole
from .errors import DatagovError, DatagovForbiddenError, DatagovNotFoundError, DatagovStateError

DEFAULTS = {"expiry_warning_days": 30, "max_restricted_grants": 5}
CLASSES = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
LEVELS = ["READ", "WRITE"]
MAX_ASSETS = 2000
MAX_ROWS = 500
LIMITATIONS = [
    "ASAVEXA keeps a register and the dates and decisions around it. It holds none of the data, enforces no access, scans nothing and applies no law or standard (data-protection law, ISO 27001 and similar are not checked).",
    "Classification, the personal-data flag and retention periods are typed by people. ASAVEXA cannot tell whether they are right.",
    "A grant that has passed its expiry date is shown as expired; ASAVEXA does not remove anyone's real access. A person must do that in the real system.",
    "Person and owner references are codes people choose. Keep names and personal details out of every field.",
    "A decision by a different person is a review of what was typed, not a check against the real systems.",
]


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.year * 12 + (d.month - 1) + n, 12)
    return date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


class DatagovService(WsMixin):
    SETTING_KIND = "dg_setting"
    DEFAULTS = DEFAULTS
    ERR, NF, ST, FB = DatagovError, DatagovNotFoundError, DatagovStateError, DatagovForbiddenError

    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ settings
    def dg_get_setting(self, org) -> dict:
        s = self._settings(org); w, m = s["expiry_warning_days"], s["max_restricted_grants"]
        return {"expiry_warning_days": w, "max_restricted_grants": m, "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"An approved grant that expires within {w} day(s) is flagged. A RESTRICTED asset with more than {m} active grant(s) is flagged. These are your own settings, not rules."}

    def dg_set_setting(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        if d.get("expiry_warning_days") is not None: s["expiry_warning_days"] = whole(DatagovError, d["expiry_warning_days"], "The warning days", 1, 365)
        if d.get("max_restricted_grants") is not None: s["max_restricted_grants"] = whole(DatagovError, d["max_restricted_grants"], "The most grants on a restricted asset", 1, 1000)
        s.update(updated_by=actor, updated_at=self.now().isoformat()); self._put("dg_setting", org, s)
        self.log("DATAGOV_SETTING_SET", actor, "settings", org, "settings")
        return self.dg_get_setting(org)

    # ------------------------------------------------------------------ views
    def _grant_state(self, g, today, warn) -> str:
        if g["status"] != "APPROVED": return g["status"]
        ex = date.fromisoformat(g["expires_on"]); st = date.fromisoformat(g["starts_on"])
        if ex < today: return "EXPIRED"
        if st > today: return "NOT_YET_ACTIVE"
        return "EXPIRING" if (ex - today).days <= warn else "ACTIVE"

    def _view(self, a) -> dict:
        v = {x: a[x] for x in a if x != "org"}; today = self.today(); s = self._settings(a["org"]); warn = s["expiry_warning_days"]
        grants = []
        for g in a["grants"]:
            g = dict(g); g["state"] = self._grant_state(g, today, warn); g["days_to_expiry"] = (date.fromisoformat(g["expires_on"]) - today).days; grants.append(g)
        live = [g for g in grants if g["state"] in ("ACTIVE", "EXPIRING")]
        nxt = None; overdue = False
        if a["status"] == "APPROVED":
            confirmed = [r["review_date"] for r in a["reviews"] if r["status"] == "CONFIRMED"]
            base = date.fromisoformat(max(confirmed)) if confirmed else date.fromisoformat(a["approved_on"])
            nd = add_months(base, a["review_every_months"]); nxt = nd.isoformat(); overdue = nd < today
        v.update(grants=grants, reviews=[dict(r) for r in a["reviews"]], next_review_due=nxt, review_overdue=overdue, active_grants=len(live), expiring_grants=sum(1 for g in grants if g["state"] == "EXPIRING"),
                 pending_grants=sum(1 for g in grants if g["status"] == "PROPOSED"), pending_reviews=sum(1 for r in a["reviews"] if r["status"] == "PROPOSED"),
                 too_many_grants=a["classification"] == "RESTRICTED" and len(live) > s["max_restricted_grants"])
        return v

    # ------------------------------------------------------------------ assets
    def dg_add_asset(self, org, d, actor) -> dict:
        E = DatagovError
        name = txt(E, d.get("name"), "The name", 3, 150); owner = txt(E, d.get("owner_ref"), "The owner reference", 2, 40); cl = code(E, d.get("classification"), "The classification", CLASSES)
        pd = code(E, d.get("personal_data"), "Whether it holds personal data", ["YES", "NO"]); ret = whole(E, d.get("retention_months"), "The retention period in months", 1, 1200); rev = whole(E, d.get("review_every_months"), "The review interval in months", 1, 60)
        desc = txt(E, d.get("description"), "The description", 10, 500)
        if len(self._all("dg_asset", org)) >= MAX_ASSETS: raise DatagovStateError(f"The register can hold at most {MAX_ASSETS} assets.")
        a = {"id": uuid.uuid4().hex, "org": org, "ref": None, "name": name, "owner_ref": owner, "classification": cl, "personal_data": pd, "retention_months": ret, "review_every_months": rev, "description": desc, "status": "PROPOSED",
             "proposed_by": actor, "proposed_at": self.now().isoformat(), "decided_by": None, "approved_on": None, "decided_on": None, "decision_note": None, "retired_by": None, "retired_on": None, "retire_note": None, "reviews": [], "grants": [], "history": []}
        a["ref"] = self._ref(org, "DA"); self._hist(a, actor, "PROPOSED")
        self._put("dg_asset", org, a); self.log("DATAGOV_ASSET_PROPOSED", actor, a["id"], org, a["ref"])
        return self._view(a)

    def dg_list_assets(self, org, status=None) -> List[dict]:
        out = []
        for a in sorted(self._all("dg_asset", org), key=refnum):
            if status and a["status"] != status: continue
            v = self._view(a); v["grants"] = []; v["reviews"] = []; v["history"] = []; out.append(v)
        return out

    def dg_get_asset(self, org, aid) -> dict: return self._view(self._get("dg_asset", org, aid, "Asset"))

    def _proposed(self, org, aid) -> dict:
        a = self._get("dg_asset", org, aid, "Asset", for_update=True)
        if a["status"] != "PROPOSED": raise DatagovStateError("Only a proposed asset can be decided.")
        return a

    def dg_approve_asset(self, org, aid, d, actor) -> dict:
        a = self._proposed(org, aid); self._two(actor, a["proposed_by"], "proposed this asset")
        note = txt(DatagovError, d.get("note"), "An approval note", 10, 1000, required=False)
        a.update(status="APPROVED", decided_by=actor, approved_on=self.today().isoformat(), decided_on=self.today().isoformat(), decision_note=note or None); self._hist(a, actor, "APPROVED", note)
        self._put("dg_asset", org, a); self.log("DATAGOV_ASSET_APPROVED", actor, aid, org, a["ref"])
        return self._view(a)

    def dg_reject_asset(self, org, aid, reason, actor) -> dict:
        a = self._proposed(org, aid); self._two(actor, a["proposed_by"], "proposed this asset")
        reason = txt(DatagovError, reason, "A reason", 10, 1000); a.update(status="REJECTED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=reason); self._hist(a, actor, "REJECTED", reason)
        self._put("dg_asset", org, a); self.log("DATAGOV_ASSET_REJECTED", actor, aid, org, a["ref"])
        return self._view(a)

    def _approved(self, org, aid) -> dict:
        a = self._get("dg_asset", org, aid, "Asset", for_update=True)
        if a["status"] != "APPROVED": raise DatagovStateError("Only an approved asset can be changed this way.")
        return a

    def dg_retire_asset(self, org, aid, reason, actor) -> dict:
        a = self._approved(org, aid); v = self._view(a)
        if v["active_grants"] or v["pending_grants"] or any(g["state"] == "NOT_YET_ACTIVE" for g in v["grants"]): raise DatagovStateError("Revoke or decide every grant before retiring the asset.")
        if v["pending_reviews"]: raise DatagovStateError("Decide every proposed review before retiring the asset.")
        reason = txt(DatagovError, reason, "A reason", 10, 1000); a.update(status="RETIRED", retired_by=actor, retired_on=self.today().isoformat(), retire_note=reason); self._hist(a, actor, "RETIRED", reason)
        self._put("dg_asset", org, a); self.log("DATAGOV_ASSET_RETIRED", actor, aid, org, a["ref"])
        return self._view(a)

    # ------------------------------------------------------------------ reviews
    def dg_add_review(self, org, aid, d, actor) -> dict:
        a = self._approved(org, aid); when = dt(DatagovError, d.get("review_date"), "The review date")
        if when > self.today() + timedelta(days=1): raise DatagovError("The review date cannot be in the future.")
        if when < date.fromisoformat(a["approved_on"]): raise DatagovError("The review date cannot be before the asset was approved.")
        outcome = txt(DatagovError, d.get("outcome"), "The outcome", 10, 500)
        if len(a["reviews"]) >= MAX_ROWS: raise DatagovStateError(f"An asset can have at most {MAX_ROWS} reviews.")
        a["reviews"].append({"no": len(a["reviews"]) + 1, "review_date": when.isoformat(), "outcome": outcome, "status": "PROPOSED", "proposed_by": actor, "decided_by": None, "decided_on": None, "decision_note": None})
        self._hist(a, actor, "REVIEW_RECORDED"); self._put("dg_asset", org, a); self.log("DATAGOV_REVIEW_RECORDED", actor, aid, org, f"{a['ref']} #{len(a['reviews'])}")
        return self._view(a)

    def _review(self, org, aid, no):
        a = self._get("dg_asset", org, aid, "Asset", for_update=True); r, n = self._row(a, no, "review", "reviews")
        if r["status"] != "PROPOSED": raise DatagovStateError("That review has already been decided.")
        if a["status"] != "APPROVED": raise DatagovStateError("The asset is not in use.")
        return a, r, n

    def dg_confirm_review(self, org, aid, no, d, actor) -> dict:
        a, r, n = self._review(org, aid, no); self._two(actor, r["proposed_by"], "recorded this review")
        note = txt(DatagovError, d.get("note"), "A confirmation note", 10, 1000, required=False)
        r.update(status="CONFIRMED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=note or None); self._hist(a, actor, "REVIEW_CONFIRMED", note)
        self._put("dg_asset", org, a); self.log("DATAGOV_REVIEW_CONFIRMED", actor, aid, org, f"{a['ref']} #{n}")
        return self._view(a)

    def dg_reject_review(self, org, aid, no, reason, actor) -> dict:
        a, r, n = self._review(org, aid, no); self._two(actor, r["proposed_by"], "recorded this review")
        reason = txt(DatagovError, reason, "A reason", 10, 1000); r.update(status="REJECTED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=reason); self._hist(a, actor, "REVIEW_REJECTED", reason)
        self._put("dg_asset", org, a); self.log("DATAGOV_REVIEW_REJECTED", actor, aid, org, f"{a['ref']} #{n}")
        return self._view(a)

    # ------------------------------------------------------------------ access grants
    def dg_add_grant(self, org, aid, d, actor) -> dict:
        E = DatagovError; a = self._approved(org, aid)
        person = txt(E, d.get("person_ref"), "The person reference", 2, 40); level = code(E, d.get("access_level"), "The access level", LEVELS); purpose = txt(E, d.get("purpose"), "The purpose", 10, 300)
        start = dt(E, d.get("starts_on"), "The start date"); end = dt(E, d.get("expires_on"), "The expiry date")
        if end < start: raise E("The expiry date cannot be before the start date.")
        limit = 366 if a["classification"] == "RESTRICTED" else 1096
        if (end - start).days > limit: raise E(f"Access to a {a['classification']} asset can last at most {'one year' if limit == 366 else 'three years'}.")
        if end < self.today(): raise E("The expiry date has already passed.")
        v = self._view(a)
        if any(g["person_ref"].lower() == person.lower() and g["access_level"] == level and g["state"] in ("PROPOSED", "ACTIVE", "EXPIRING", "NOT_YET_ACTIVE") for g in v["grants"]):
            raise DatagovStateError("That person already has this access, or it is waiting for a decision.")
        if len(a["grants"]) >= MAX_ROWS: raise DatagovStateError(f"An asset can have at most {MAX_ROWS} grants.")
        a["grants"].append({"no": len(a["grants"]) + 1, "person_ref": person, "access_level": level, "purpose": purpose, "starts_on": start.isoformat(), "expires_on": end.isoformat(), "status": "PROPOSED", "proposed_by": actor, "decided_by": None, "decided_on": None, "decision_note": None, "revoked_by": None, "revoke_note": None})
        self._hist(a, actor, "GRANT_PROPOSED"); self._put("dg_asset", org, a); self.log("DATAGOV_GRANT_PROPOSED", actor, aid, org, f"{a['ref']} #{len(a['grants'])}")
        return self._view(a)

    def _grant(self, org, aid, no, want="PROPOSED"):
        a = self._get("dg_asset", org, aid, "Asset", for_update=True); g, n = self._row(a, no, "grant", "grants")
        if g["status"] != want: raise DatagovStateError("That grant has already been decided." if want == "PROPOSED" else "Only an approved grant can be revoked.")
        if a["status"] != "APPROVED": raise DatagovStateError("The asset is not in use.")
        return a, g, n

    def dg_approve_grant(self, org, aid, no, d, actor) -> dict:
        a, g, n = self._grant(org, aid, no); self._two(actor, g["proposed_by"], "proposed this grant")
        if date.fromisoformat(g["expires_on"]) < self.today(): raise DatagovStateError("This grant has already expired; propose a new one.")
        note = txt(DatagovError, d.get("note"), "An approval note", 10, 1000, required=False)
        g.update(status="APPROVED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=note or None); self._hist(a, actor, "GRANT_APPROVED", note)
        self._put("dg_asset", org, a); self.log("DATAGOV_GRANT_APPROVED", actor, aid, org, f"{a['ref']} #{n}")
        return self._view(a)

    def dg_reject_grant(self, org, aid, no, reason, actor) -> dict:
        a, g, n = self._grant(org, aid, no); self._two(actor, g["proposed_by"], "proposed this grant")
        reason = txt(DatagovError, reason, "A reason", 10, 1000); g.update(status="REJECTED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=reason); self._hist(a, actor, "GRANT_REJECTED", reason)
        self._put("dg_asset", org, a); self.log("DATAGOV_GRANT_REJECTED", actor, aid, org, f"{a['ref']} #{n}")
        return self._view(a)

    def dg_revoke_grant(self, org, aid, no, reason, actor) -> dict:
        a, g, n = self._grant(org, aid, no, want="APPROVED")
        reason = txt(DatagovError, reason, "A reason", 10, 1000); g.update(status="REVOKED", revoked_by=actor, revoke_note=reason); self._hist(a, actor, "GRANT_REVOKED", reason)
        self._put("dg_asset", org, a); self.log("DATAGOV_GRANT_REVOKED", actor, aid, org, f"{a['ref']} #{n}")
        return self._view(a)

    # ------------------------------------------------------------------ overview
    def dg_overview(self, org) -> dict:
        vs = [self._view(a) for a in sorted(self._all("dg_asset", org), key=refnum)]; att = []; ap = [v for v in vs if v["status"] == "APPROVED"]

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("ASSETS_TO_APPROVE", sum(1 for v in vs if v["status"] == "PROPOSED"), "asset(s) are waiting for a different person to decide them.")
        add("GRANTS_TO_DECIDE", sum(v["pending_grants"] for v in ap), "access grant(s) are waiting for a different person to decide them.")
        add("REVIEWS_TO_CONFIRM", sum(v["pending_reviews"] for v in ap), "review(s) are waiting for a different person to confirm them.")
        add("REVIEWS_OVERDUE", sum(1 for v in ap if v["review_overdue"]), "approved asset(s) are past their next review date.")
        add("GRANTS_EXPIRING_SOON", sum(v["expiring_grants"] for v in ap), "access grant(s) expire soon.")
        add("TOO_MANY_GRANTS", sum(1 for v in ap if v["too_many_grants"]), "restricted asset(s) have more active grants than your limit.")
        by = {c: sum(1 for v in ap if v["classification"] == c) for c in CLASSES}
        on_time = sum(1 for v in ap if not v["review_overdue"])
        pct = (Decimal(on_time) * 100 / Decimal(len(ap))).quantize(Decimal("0.01")) if ap else Decimal("0.00")
        counts = {s.lower(): sum(1 for v in vs if v["status"] == s) for s in ("PROPOSED", "APPROVED", "REJECTED", "RETIRED")}
        return {"counts": counts, "by_classification": by, "personal_data_assets": sum(1 for v in ap if v["personal_data"] == "YES"), "active_grants": sum(v["active_grants"] for v in ap), "reviews_on_time_pct": str(pct),
                "attention": att, "setting": self.dg_get_setting(org), "limitations": LIMITATIONS}

    def dg_options(self, org) -> dict:
        return {"classifications": CLASSES, "access_levels": LEVELS, "limitations": LIMITATIONS}
