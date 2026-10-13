"""Agent registry and policy decisions (Stage 7).

An AGENT is a named piece of automation (today only rule-based; no outside model is approved) with an owner, a purpose and a short list of ACTIONS it may
ask to perform. Nothing in ASAVEXA currently runs agents on its own; this is the control point they must pass through. Every request is DECIDED:
  ALLOW             the action is low-risk and permitted for this agent;
  REQUIRE_APPROVAL  a person must approve this one request first, then it can be used ONCE, before it expires;
  DENY              refused (agent not active, action not listed for it, or the policy forbids any agent doing it).
Every decision is recorded, and every step is audited. An agent is activated only by someone other than who proposed it. Approving a request
cannot be done by whoever asked for it. The registry never executes anything; it only says whether an action may go ahead.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

from ..security.errors import SecurityError
from . import policy as P

AGENT_KIND, DECISION_KIND, SETTING_KIND = "agent", "agent_decision", "agent_setting"
APPROVAL_HOURS = 24
MAX_TEXT = 2000


DECISION_STATES = ("NOT_NEEDED", "PENDING", "APPROVED", "REJECTED", "REFUSED", "EXPIRED", "USED")


class AgentError(SecurityError): status = 400
class AgentNotFoundError(AgentError): status = 404
class AgentStateError(AgentError): status = 409
class AgentForbiddenError(AgentError): status = 403


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _text(v, label, required=True, limit=MAX_TEXT) -> str:
    s = (v or "").strip() if isinstance(v, str) or v is None else str(v).strip()
    if required and not s:
        raise AgentError(f"{label} is required.")
    if len(s) > limit:
        raise AgentError(f"{label} must be at most {limit} characters.")
    return s


class AgentRegistry:
    def __init__(self, store, is_member: Callable[[str, str], bool], log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _now):
        self.store, self.is_member, self.log, self.now = store, is_member, log, now

    # ---------------------------------------------------------------- helpers
    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        d = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if d is None or d.get("org") != org:
            raise AgentNotFoundError(f"{label} not found.")
        return d

    def _stamp(self, d, actor, event, note=""):
        d["history"].append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})
        d["updated_at"] = self.now().isoformat()

    def overrides(self, org) -> dict:
        s = self.store.get(SETTING_KIND, f"{org}:policy")
        return dict(s["overrides"]) if s and s.get("org") == org else {}

    def policy_table(self, org) -> List[dict]:
        ov = self.overrides(org)
        return [{"action": a, "label": lab, "builtin": base, "effective": P.effective_decision(a, ov)} for a, (lab, base) in P.ACTIONS.items()]

    # ---------------------------------------------------------------- policy
    def tighten_policy(self, org, actor, action, decision) -> dict:
        if action not in P.ACTIONS:
            raise AgentError("Unknown action.")
        if decision not in P.ORDER:
            raise AgentError("Decision must be ALLOW, REQUIRE_APPROVAL or DENY.")
        current = P.effective_decision(action, self.overrides(org))
        if P.ORDER[decision] <= P.ORDER[current]:
            raise AgentError(f"A policy can only be made stricter. {action} is already {current}.")
        s = self.store.get(SETTING_KIND, f"{org}:policy", for_update=True) or {"id": "policy", "org": org, "overrides": {}, "history": []}
        s["overrides"][action] = decision
        s["history"].append({"at": self.now().isoformat(), "by": actor, "action": action, "decision": decision})
        self._put(SETTING_KIND, org, s)
        self.log("AGENT_POLICY_TIGHTENED", actor, "policy", org, f"{action} -> {decision}")
        return {"action": action, "effective": decision}

    # ---------------------------------------------------------------- agents
    def propose_agent(self, org, actor, name, purpose, owner, actions, provider="RULE_BASED") -> dict:
        name, purpose = _text(name, "Name", limit=100), _text(purpose, "Purpose")
        if provider not in P.ALLOWED_PROVIDERS:
            raise AgentError("Only rule-based agents are approved. An outside model needs a separate security and cost review first.")
        owner = _text(owner, "Owner")
        if not self.is_member(org, owner):
            raise AgentError("The owner must be a member of this organisation.")
        if not isinstance(actions, list) or not actions or len(set(actions)) != len(actions):
            raise AgentError("List at least one action, each once.")
        for a in actions:
            if a not in P.ACTIONS:
                raise AgentError(f"Unknown action {a!r}.")
            if P.base_decision(a) == P.DENY:
                raise AgentError(f"{a} is forbidden for every agent: a person must do it.")
        for _, other in self.store.list(AGENT_KIND, org_id=org):
            if other["name"].lower() == name.lower() and other["status"] != "RETIRED":
                raise AgentStateError("An agent with that name already exists.")
        aid = str(uuid.uuid4())
        a = {"id": aid, "org": org, "name": name, "purpose": purpose, "owner": owner, "provider": provider, "actions": sorted(actions), "status": "PROPOSED",
             "proposed_by": actor, "activated_by": None, "history": [], "created_at": self.now().isoformat(), "updated_at": self.now().isoformat()}
        self._stamp(a, actor, "PROPOSED")
        self._put(AGENT_KIND, org, a)
        self.log("AGENT_PROPOSED", actor, aid, org, name)
        return a

    def activate(self, org, agent_id, actor, note="") -> dict:
        a = self._get(AGENT_KIND, org, agent_id, "Agent", for_update=True)
        if a["status"] not in ("PROPOSED", "SUSPENDED"):
            raise AgentStateError(f"Only a proposed or suspended agent can be activated (this one is {a['status']}).")
        if actor == a["proposed_by"]:
            raise AgentForbiddenError("The person who proposed an agent cannot activate it. Someone else must.")
        a["status"], a["activated_by"] = "ACTIVE", actor
        self._stamp(a, actor, "ACTIVATED", _text(note, "Note", required=False))
        self._put(AGENT_KIND, org, a)
        self.log("AGENT_ACTIVATED", actor, agent_id, org, a["name"])
        return a

    def suspend(self, org, agent_id, actor, reason) -> dict:
        a = self._get(AGENT_KIND, org, agent_id, "Agent", for_update=True)
        if a["status"] != "ACTIVE":
            raise AgentStateError(f"Only an active agent can be suspended (this one is {a['status']}).")
        a["status"] = "SUSPENDED"
        self._stamp(a, actor, "SUSPENDED", _text(reason, "Reason"))
        self._put(AGENT_KIND, org, a)
        self.log("AGENT_SUSPENDED", actor, agent_id, org, a["name"])
        return a

    def retire(self, org, agent_id, actor, reason) -> dict:
        a = self._get(AGENT_KIND, org, agent_id, "Agent", for_update=True)
        if a["status"] == "RETIRED":
            raise AgentStateError("This agent is already retired.")
        a["status"] = "RETIRED"
        self._stamp(a, actor, "RETIRED", _text(reason, "Reason"))
        self._put(AGENT_KIND, org, a)
        self.log("AGENT_RETIRED", actor, agent_id, org, a["name"])
        return a

    # ---------------------------------------------------------------- decisions
    def request_decision(self, org, agent_id, action, actor, subject="") -> dict:
        """Records and returns the decision for one request. Never raises for a refusal: a DENY is a recorded answer."""
        a = self._get(AGENT_KIND, org, agent_id, "Agent")
        subject = _text(subject, "Subject", required=False, limit=300)
        if action not in P.ACTIONS:
            raise AgentError("Unknown action.")
        if a["status"] != "ACTIVE":
            decision, reason = P.DENY, f"The agent is {a['status']}, not active."
        elif action not in a["actions"]:
            decision, reason = P.DENY, "This action is not on the agent's list."
        else:
            decision = P.effective_decision(action, self.overrides(org))
            reason = {P.ALLOW: "Low-risk and permitted for this agent.", P.REQUIRE_APPROVAL: "A person must approve this request first.",
                      P.DENY: "No agent may do this: a person must."}[decision]
        did = str(uuid.uuid4())
        d = {"id": did, "org": org, "agent_id": agent_id, "agent_name": a["name"], "action": action, "subject": subject, "decision": decision, "reason": reason,
             "requested_by": actor, "state": "PENDING" if decision == P.REQUIRE_APPROVAL else ("NOT_NEEDED" if decision == P.ALLOW else "REFUSED"),
             "decided_by": None, "expires_at": (self.now() + timedelta(hours=APPROVAL_HOURS)).isoformat() if decision == P.REQUIRE_APPROVAL else None,
             "history": [], "created_at": self.now().isoformat(), "updated_at": self.now().isoformat()}
        self._stamp(d, actor, decision, reason)
        self._put(DECISION_KIND, org, d)
        self.log("AGENT_DECISION_" + decision, actor, did, org, f"{a['name']} {action}")
        return d

    def _expire(self, d) -> bool:
        if d["state"] in ("PENDING", "APPROVED") and d["expires_at"] and d["expires_at"] <= self.now().isoformat():
            d["state"] = "EXPIRED"
            return True
        return False

    def resolve(self, org, decision_id, actor, approve: bool, note="") -> dict:
        d = self._get(DECISION_KIND, org, decision_id, "Request", for_update=True)
        if self._expire(d):
            self._put(DECISION_KIND, org, d)
        if d["state"] != "PENDING":
            raise AgentStateError(f"Only a pending request can be decided (this one is {d['state']}).")
        if actor == d["requested_by"]:
            raise AgentForbiddenError("The person who made the request cannot approve or reject it. Someone else must.")
        note = _text(note, "Reason", required=not approve)
        d["state"], d["decided_by"] = ("APPROVED" if approve else "REJECTED"), actor
        self._stamp(d, actor, d["state"], note)
        self._put(DECISION_KIND, org, d)
        self.log("AGENT_REQUEST_" + d["state"], actor, decision_id, org, f"{d['agent_name']} {d['action']}")
        return d

    def confirm(self, org, decision_id, actor) -> dict:
        """Called by whatever is about to do the action. An approved request works exactly once and only before it expires; an ALLOW needs no approval."""
        d = self._get(DECISION_KIND, org, decision_id, "Request", for_update=True)
        a = self._get(AGENT_KIND, org, d["agent_id"], "Agent")
        if self._expire(d):
            self._put(DECISION_KIND, org, d)
        if a["status"] != "ACTIVE":
            raise AgentForbiddenError(f"The agent is {a['status']}; nothing may proceed.")
        if d["decision"] == P.DENY or d["state"] == "REFUSED":
            raise AgentForbiddenError("This request was refused.")
        if d["decision"] == P.ALLOW:
            return {"permitted": True, "decision_id": decision_id, "once": False}
        if d["state"] != "APPROVED":
            raise AgentForbiddenError(f"This request is {d['state']}, so the action may not go ahead.")
        d["state"] = "USED"
        self._stamp(d, actor, "USED")
        self._put(DECISION_KIND, org, d)
        self.log("AGENT_REQUEST_USED", actor, decision_id, org, f"{d['agent_name']} {d['action']}")
        return {"permitted": True, "decision_id": decision_id, "once": True}

    # ---------------------------------------------------------------- read
    def get_agent(self, org, agent_id) -> dict: return self._get(AGENT_KIND, org, agent_id, "Agent")

    def list_agents(self, org) -> List[dict]:
        return sorted([a for _, a in self.store.list(AGENT_KIND, org_id=org) if a.get("org") == org], key=lambda a: a["created_at"])

    def list_decisions(self, org, state: Optional[str] = None) -> List[dict]:
        out = []
        for _, d in self.store.list(DECISION_KIND, org_id=org):
            if d.get("org") != org:
                continue
            if self._expire(d):
                self._put(DECISION_KIND, org, d)
            if not state or d["state"] == state:
                out.append(d)
        return sorted(out, key=lambda d: d["created_at"], reverse=True)

    def actions(self) -> List[dict]:
        return [{"action": a, "label": lab, "builtin": base} for a, (lab, base) in P.ACTIONS.items()]
