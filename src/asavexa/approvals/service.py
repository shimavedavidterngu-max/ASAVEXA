"""Approval workflows (records and evidence): named approval policies with up to three steps, and requests that move through those steps.

Records (shared document store, per organisation): apw_policy, apw_request, apw_setting.

Principles enforced here
  * A policy has a name, a kind of request it is meant for, a description and one to three steps. Each step has a label and the number of different people (one to five) who must approve it. A policy is proposed by one person and activated or rejected by a different person. Only an active policy takes requests. A policy is never edited; an approver can retire it with a reason.
  * A request is submitted by one person against an active policy, with a title, a reference code, an optional amount (exact, never a float, with its currency) and a description. The policy's steps are copied into the request when it is submitted, so retiring a policy never changes a request already under way.
  * The steps run in order. A step is passed when the required number of different people have approved it. After the last step the request is APPROVED. Anyone who decides can reject instead, with a reason, and the request ends as REJECTED.
  * The person who submitted a request can never decide it, and one person can decide a request only once, across all its steps. The submitter, and only the submitter, can withdraw a pending request, with a reason.
  * Amounts of different currencies are never added together.
  * Approvals here are a record. Nothing is paid, bought, signed or changed anywhere else because of them, and no other part of ASAVEXA is blocked by them.
Nothing is edited after a decision or deleted. Every step is audited by reference number only.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Callable, List

from ..wscommon import WsMixin, amount, code, currency, refnum, txt, utc, whole
from .errors import ApprovalsError, ApprovalsForbiddenError, ApprovalsNotFoundError, ApprovalsStateError

DEFAULTS = {"stale_days": 5}
KINDS = ["PAYMENT", "PURCHASE", "CONTRACT", "EXPENSE", "ACCESS", "EXCEPTION", "OTHER"]
MAX_STEPS = 3
MAX_REQUIRED = 5
MAX_POLICIES = 200
MAX_REQUESTS = 5000
LIMITATIONS = [
    "An approval here is a record. Nothing is paid, bought, signed or changed anywhere else because of it, and no other part of ASAVEXA waits for it.",
    "ASAVEXA checks that different people approved, not that they were the right people. Who may approve what is decided by the organisation and its roles, not by the policy text.",
    "A policy's steps are copied into each request when it is submitted. Retiring a policy does not change a request already under way.",
    "Amounts and descriptions are typed by people and are not checked against any invoice, contract or payment system.",
    "Keep names, personal details, bank details and confidential terms out of every field. Use reference codes.",
]


class ApprovalsService(WsMixin):
    SETTING_KIND = "apw_setting"
    DEFAULTS = DEFAULTS
    ERR, NF, ST, FB = ApprovalsError, ApprovalsNotFoundError, ApprovalsStateError, ApprovalsForbiddenError

    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ settings
    def apw_get_setting(self, org) -> dict:
        s = self._settings(org); d = s["stale_days"]
        return {"stale_days": d, "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"A pending request is flagged as waiting too long once it has waited {d} day(s) or more. This is your own setting, not a rule."}

    def apw_set_setting(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        if d.get("stale_days") is not None: s["stale_days"] = whole(ApprovalsError, d["stale_days"], "The days that count as waiting too long", 1, 365)
        s.update(updated_by=actor, updated_at=self.now().isoformat()); self._put("apw_setting", org, s)
        self.log("APPROVALS_SETTING_SET", actor, "settings", org, "settings")
        return self.apw_get_setting(org)

    # ------------------------------------------------------------------ policies
    @staticmethod
    def _steps(raw) -> list:
        E = ApprovalsError
        if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_STEPS: raise E(f"A policy needs between 1 and {MAX_STEPS} steps.")
        out = []
        for i, s in enumerate(raw, 1):
            if not isinstance(s, dict): raise E(f"Step {i} must have a label and a number of approvals.")
            label = txt(E, s.get("label"), f"The label of step {i}", 3, 80); need = whole(E, s.get("required"), f"The approvals needed at step {i}", 1, MAX_REQUIRED)
            if any(o["label"].lower() == label.lower() for o in out): raise E("Each step needs a different label.")
            out.append({"no": i, "label": label, "required": need})
        return out

    def apw_add_policy(self, org, d, actor) -> dict:
        E = ApprovalsError
        name = txt(E, d.get("name"), "The policy name", 3, 120); kind = code(E, d.get("request_kind"), "The kind of request", KINDS); steps = self._steps(d.get("steps")); desc = txt(E, d.get("description"), "The description", 10, 1000)
        if any(p["name"].lower() == name.lower() and p["status"] in ("PROPOSED", "ACTIVE") for p in self._all("apw_policy", org)): raise ApprovalsStateError("A policy with that name is already proposed or active.")
        if len(self._all("apw_policy", org)) >= MAX_POLICIES: raise ApprovalsStateError(f"The register can hold at most {MAX_POLICIES} policies.")
        x = {"id": uuid.uuid4().hex, "org": org, "ref": None, "name": name, "request_kind": kind, "steps": steps, "description": desc, "status": "PROPOSED", "proposed_by": actor, "proposed_at": self.now().isoformat(),
             "decided_by": None, "decided_on": None, "decision_note": None, "retired_by": None, "retired_on": None, "retire_note": None, "history": []}
        x["ref"] = self._ref(org, "AP"); self._hist(x, actor, "PROPOSED")
        self._put("apw_policy", org, x); self.log("APPROVALS_POLICY_PROPOSED", actor, x["id"], org, x["ref"])
        return self._pview(org, x)

    def _pview(self, org, x) -> dict:
        v = {k: x[k] for k in x if k != "org"}
        v["requests_under_way"] = sum(1 for r in self._all("apw_request", org) if r["policy_id"] == x["id"] and r["status"] == "PENDING")
        v["people_per_request"] = sum(s["required"] for s in x["steps"])
        return v

    def apw_list_policies(self, org, status=None) -> List[dict]:
        out = []
        for x in sorted(self._all("apw_policy", org), key=refnum):
            if status and x["status"] != status: continue
            v = self._pview(org, x); v["history"] = []; out.append(v)
        return out

    def apw_get_policy(self, org, pid) -> dict: return self._pview(org, self._get("apw_policy", org, pid, "Policy"))

    def _proposed_policy(self, org, pid) -> dict:
        x = self._get("apw_policy", org, pid, "Policy", for_update=True)
        if x["status"] != "PROPOSED": raise ApprovalsStateError("Only a proposed policy can be decided.")
        return x

    def apw_activate_policy(self, org, pid, d, actor) -> dict:
        x = self._proposed_policy(org, pid); self._two(actor, x["proposed_by"], "proposed this policy")
        note = txt(ApprovalsError, d.get("note"), "An approval note", 10, 1000, required=False)
        x.update(status="ACTIVE", decided_by=actor, decided_on=self.today().isoformat(), decision_note=note or None); self._hist(x, actor, "ACTIVATED", note)
        self._put("apw_policy", org, x); self.log("APPROVALS_POLICY_ACTIVATED", actor, pid, org, x["ref"])
        return self._pview(org, x)

    def apw_reject_policy(self, org, pid, reason, actor) -> dict:
        x = self._proposed_policy(org, pid); self._two(actor, x["proposed_by"], "proposed this policy")
        reason = txt(ApprovalsError, reason, "A reason", 10, 1000)
        x.update(status="REJECTED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=reason); self._hist(x, actor, "REJECTED", reason)
        self._put("apw_policy", org, x); self.log("APPROVALS_POLICY_REJECTED", actor, pid, org, x["ref"])
        return self._pview(org, x)

    def apw_retire_policy(self, org, pid, reason, actor) -> dict:
        x = self._get("apw_policy", org, pid, "Policy", for_update=True)
        if x["status"] != "ACTIVE": raise ApprovalsStateError("Only an active policy can be retired.")
        reason = txt(ApprovalsError, reason, "A reason", 10, 1000)
        x.update(status="RETIRED", retired_by=actor, retired_on=self.today().isoformat(), retire_note=reason); self._hist(x, actor, "RETIRED", reason)
        self._put("apw_policy", org, x); self.log("APPROVALS_POLICY_RETIRED", actor, pid, org, x["ref"])
        return self._pview(org, x)

    # ------------------------------------------------------------------ requests
    def _rview(self, x) -> dict:
        v = {k: x[k] for k in x if k != "org"}
        v["steps"] = [dict(s, decisions=[dict(d) for d in s["decisions"]]) for s in x["steps"]]
        step = next((s for s in v["steps"] if s["no"] == x["current_step"]), None) if x["status"] == "PENDING" else None
        v["current_label"] = step["label"] if step else None
        v["still_needed"] = (step["required"] - len(step["decisions"])) if step else 0
        v["step_count"] = len(x["steps"])
        v["approvals_so_far"] = sum(len(s["decisions"]) for s in x["steps"])
        v["approvals_in_total"] = sum(s["required"] for s in x["steps"])
        if x["status"] == "PENDING":
            days = (self.today() - datetime.fromisoformat(x["submitted_at"]).date()).days
            v["waiting_days"] = max(days, 0); v["stale"] = v["waiting_days"] >= self._settings(x["org"])["stale_days"]
        else:
            v["waiting_days"] = None; v["stale"] = False
        return v

    def _rsummary(self, x) -> dict:
        v = self._rview(x); v["history"] = []; v["steps"] = [dict(s, decisions=[]) for s in v["steps"]]
        return v

    def apw_submit_request(self, org, d, actor) -> dict:
        E = ApprovalsError
        pid = d.get("policy_id")
        if not isinstance(pid, str) or not pid.strip(): raise E("Choose the policy this request follows.")
        pol = self._get("apw_policy", org, pid.strip(), "Policy")
        if pol["status"] != "ACTIVE": raise ApprovalsStateError("Only an active policy takes requests.")
        title = txt(E, d.get("title"), "The title", 3, 150); rref = txt(E, d.get("request_ref"), "The request reference", 2, 40); desc = txt(E, d.get("description"), "The description", 10, 1000)
        raw_amt = d.get("amount"); raw_cur = d.get("currency"); has_amt = raw_amt not in (None, ""); has_cur = raw_cur not in (None, "")
        amt = cur = None
        if has_amt or has_cur:
            if not (has_amt and has_cur): raise E("Give both the amount and its currency, or neither.")
            amt = str(amount(E, raw_amt, "The amount", digits=15)); cur = currency(E, raw_cur)
        if len(self._all("apw_request", org)) >= MAX_REQUESTS: raise ApprovalsStateError(f"The register can hold at most {MAX_REQUESTS} requests.")
        x = {"id": uuid.uuid4().hex, "org": org, "ref": None, "policy_id": pol["id"], "policy_ref": pol["ref"], "policy_name": pol["name"], "request_kind": pol["request_kind"],
             "steps": [{"no": s["no"], "label": s["label"], "required": s["required"], "decisions": []} for s in pol["steps"]], "current_step": 1,
             "title": title, "request_ref": rref, "amount": amt, "currency": cur, "description": desc, "status": "PENDING", "submitted_by": actor, "submitted_at": self.now().isoformat(),
             "decided_by": None, "decided_on": None, "decision_note": None, "withdrawn_on": None, "withdraw_note": None, "history": []}
        x["ref"] = self._ref(org, "AR"); self._hist(x, actor, "SUBMITTED")
        self._put("apw_request", org, x); self.log("APPROVALS_REQUEST_SUBMITTED", actor, x["id"], org, f"{x['ref']} {pol['ref']}")
        return self._rview(x)

    def apw_list_requests(self, org, status=None) -> List[dict]:
        return [self._rsummary(x) for x in sorted(self._all("apw_request", org), key=refnum) if not status or x["status"] == status]

    def apw_get_request(self, org, rid) -> dict: return self._rview(self._get("apw_request", org, rid, "Request"))

    def apw_decide(self, org, rid, ok, note, actor) -> dict:
        """Approve the current step of a request (ok) or reject the whole request. Never the submitter, and never twice by one person."""
        E = ApprovalsError; x = self._get("apw_request", org, rid, "Request", for_update=True)
        if x["status"] != "PENDING": raise ApprovalsStateError("Only a pending request can be decided.")
        self._two(actor, x["submitted_by"], "submitted this request")
        if any(dc["by"] == actor for s in x["steps"] for dc in s["decisions"]): raise ApprovalsForbiddenError("You have already decided this request. A different person must decide the next step.")
        step = next(s for s in x["steps"] if s["no"] == x["current_step"]); on = self.today().isoformat()
        if ok:
            text = txt(E, note.get("note") if isinstance(note, dict) else note, "An approval note", 10, 1000, required=False)
            step["decisions"].append({"by": actor, "decision": "APPROVED", "on": on, "note": text or None})
            if len(step["decisions"]) >= step["required"]:
                if x["current_step"] >= len(x["steps"]):
                    x.update(status="APPROVED", current_step=None, decided_by=actor, decided_on=on, decision_note=text or None); ev = "APPROVED"
                else:
                    x["current_step"] += 1; ev = f"STEP_{step['no']}_PASSED"
            else:
                ev = f"STEP_{step['no']}_APPROVAL"
        else:
            text = txt(E, note, "A reason", 10, 1000)
            step["decisions"].append({"by": actor, "decision": "REJECTED", "on": on, "note": text})
            x.update(status="REJECTED", current_step=None, decided_by=actor, decided_on=on, decision_note=text); ev = "REJECTED"
        self._hist(x, actor, ev, text); self._put("apw_request", org, x); self.log(f"APPROVALS_REQUEST_{'REJECTED' if not ok else 'APPROVED' if ev == 'APPROVED' else 'STEP_APPROVED'}", actor, rid, org, f"{x['ref']} step {step['no']}")
        return self._rview(x)

    def apw_withdraw(self, org, rid, reason, actor) -> dict:
        x = self._get("apw_request", org, rid, "Request", for_update=True)
        if x["status"] != "PENDING": raise ApprovalsStateError("Only a pending request can be withdrawn.")
        if x["submitted_by"] != actor: raise ApprovalsForbiddenError("Only the person who submitted a request can withdraw it.")
        reason = txt(ApprovalsError, reason, "A reason", 10, 1000)
        x.update(status="WITHDRAWN", current_step=None, withdrawn_on=self.today().isoformat(), withdraw_note=reason); self._hist(x, actor, "WITHDRAWN", reason)
        self._put("apw_request", org, x); self.log("APPROVALS_REQUEST_WITHDRAWN", actor, rid, org, x["ref"])
        return self._rview(x)

    # ------------------------------------------------------------------ overview
    def apw_overview(self, org) -> dict:
        ps = self._all("apw_policy", org); rs = [self._rview(x) for x in sorted(self._all("apw_request", org), key=refnum)]; att = []
        pend = [r for r in rs if r["status"] == "PENDING"]

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("POLICIES_TO_DECIDE", sum(1 for p in ps if p["status"] == "PROPOSED"), "polic(ies) are waiting for a different person to decide them.")
        add("REQUESTS_WAITING", len(pend), "request(s) are waiting for an approval.")
        add("REQUESTS_STALE", sum(1 for r in pend if r["stale"]), "request(s) have waited too long.")
        add("NO_ACTIVE_POLICY", 0 if any(p["status"] == "ACTIVE" for p in ps) else 1, "No policy is active yet, so no request can be submitted.")
        pcount = {s.lower(): sum(1 for p in ps if p["status"] == s) for s in ("PROPOSED", "ACTIVE", "REJECTED", "RETIRED")}
        rcount = {s.lower(): sum(1 for r in rs if r["status"] == s) for s in ("PENDING", "APPROVED", "REJECTED", "WITHDRAWN")}
        by_kind = {k: sum(1 for r in pend if r["request_kind"] == k) for k in KINDS if any(r["request_kind"] == k for r in pend)}
        roll = {}
        for r in rs:
            if r["amount"] is None or r["status"] not in ("PENDING", "APPROVED"): continue
            t = roll.setdefault(r["currency"], {"currency": r["currency"], "pending": Decimal("0"), "approved": Decimal("0")}); t["pending" if r["status"] == "PENDING" else "approved"] += Decimal(r["amount"])
        q = Decimal("0.01"); by_cur = [{**t, "pending": str(t["pending"].quantize(q)), "approved": str(t["approved"].quantize(q))} for t in sorted(roll.values(), key=lambda t: t["currency"])]
        return {"policies": pcount, "requests": rcount, "attention": att, "pending_by_kind": by_kind, "by_currency": by_cur, "setting": self.apw_get_setting(org), "limitations": LIMITATIONS}

    def apw_options(self, org) -> dict: return {"kinds": KINDS, "max_steps": MAX_STEPS, "max_required": MAX_REQUIRED, "limitations": LIMITATIONS}
