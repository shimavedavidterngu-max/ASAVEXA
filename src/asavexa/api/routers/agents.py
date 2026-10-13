"""Agent registry and policy decision endpoints. Thin: the rules live in asavexa.agents.

Viewing needs audit:read. Proposing an agent, asking for a decision and confirming one need grc:prepare. Activating, suspending, retiring, tightening the
policy and approving or rejecting a request need grc:approve; the service refuses an approver who proposed the agent or made the request."""
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...agents.service import AgentRegistry
from ...identity.domain.permissions import AUDIT_READ, GRC_APPROVE, GRC_PREPARE
from ..deps import get_agent_registry, get_current_actor, get_current_org, require_permission

router = APIRouter(prefix="/agents", tags=["Agent registry"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(GRC_PREPARE))
_approve = Depends(require_permission(GRC_APPROVE))


class AgentBody(BaseModel):
    name: str
    purpose: str
    owner: str
    actions: List[str]
    provider: str = "RULE_BASED"


class NoteBody(BaseModel):
    note: str = ""


class ReasonBody(BaseModel):
    reason: str


class DecideBody(BaseModel):
    agent_id: str
    action: str
    subject: str = ""


class ResolveBody(BaseModel):
    approve: bool
    note: str = ""


class PolicyBody(BaseModel):
    action: str
    decision: str


@router.get("/catalog")
def catalog(org: str = Depends(get_current_org), svc: AgentRegistry = Depends(get_agent_registry)):
    return {"actions": svc.actions(), "policy": svc.policy_table(org)}


@router.get("")
def list_agents(org: str = Depends(get_current_org), svc: AgentRegistry = Depends(get_agent_registry)):
    return {"agents": svc.list_agents(org)}


@router.get("/decisions")
def list_decisions(state: Optional[str] = None, org: str = Depends(get_current_org), svc: AgentRegistry = Depends(get_agent_registry)):
    return {"decisions": svc.list_decisions(org, state)}


@router.get("/{agent_id}")
def get_agent(agent_id: str, org: str = Depends(get_current_org), svc: AgentRegistry = Depends(get_agent_registry)):
    return svc.get_agent(org, agent_id)


@router.post("", status_code=201, dependencies=[_prepare])
def propose(body: AgentBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AgentRegistry = Depends(get_agent_registry)):
    return svc.propose_agent(org, actor, body.name, body.purpose, body.owner, body.actions, body.provider)


@router.post("/policy", dependencies=[_approve])
def tighten(body: PolicyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AgentRegistry = Depends(get_agent_registry)):
    return svc.tighten_policy(org, actor, body.action, body.decision)


@router.post("/decisions", status_code=201, dependencies=[_prepare])
def decide(body: DecideBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AgentRegistry = Depends(get_agent_registry)):
    return svc.request_decision(org, body.agent_id, body.action, actor, body.subject)


@router.post("/decisions/{decision_id}/resolve", dependencies=[_approve])
def resolve(decision_id: str, body: ResolveBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AgentRegistry = Depends(get_agent_registry)):
    return svc.resolve(org, decision_id, actor, body.approve, body.note)


@router.post("/decisions/{decision_id}/confirm", dependencies=[_prepare])
def confirm(decision_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AgentRegistry = Depends(get_agent_registry)):
    return svc.confirm(org, decision_id, actor)


@router.post("/{agent_id}/activate", dependencies=[_approve])
def activate(agent_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AgentRegistry = Depends(get_agent_registry)):
    return svc.activate(org, agent_id, actor, body.note)


@router.post("/{agent_id}/suspend", dependencies=[_approve])
def suspend(agent_id: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AgentRegistry = Depends(get_agent_registry)):
    return svc.suspend(org, agent_id, actor, body.reason)


@router.post("/{agent_id}/retire", dependencies=[_approve])
def retire(agent_id: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AgentRegistry = Depends(get_agent_registry)):
    return svc.retire(org, agent_id, actor, body.reason)
