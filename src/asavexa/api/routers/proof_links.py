"""Stored Proof-to-Action links (Stage 13): who recorded that one record relates to another, who confirmed or disputed it, and which expected links are missing.
Reading needs audit:read. Recording, disputing, retiring and noting a missing link need grc:prepare; confirming, reinstating and waiving need grc:approve.
The organisation always comes from the signed-in session, never from the request."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, GRC_APPROVE, GRC_PREPARE
from ...proofgraph.links import GraphLinkError, ProofLinks
from ..deps import get_current_actor, get_current_org, get_proof_links, require_permission

router = APIRouter(prefix="/proof-links", tags=["Proof links"])


class Ref(BaseModel):
    type: str
    id: str


class LinkBody(BaseModel):
    from_ref: Ref
    to_ref: Ref
    relation: str
    note: str = ""


class ReasonBody(BaseModel):
    reason: str


class NoteBody(BaseModel):
    note: str = ""


class GapBody(BaseModel):
    from_ref: Ref
    relation: str
    note: str
    expected_type: Optional[str] = None


def _run(fn):
    try:
        return fn()
    except GraphLinkError as exc:
        raise HTTPException(status_code=getattr(exc, "status", 400), detail=str(exc))


@router.get("/vocabulary", dependencies=[Depends(require_permission(AUDIT_READ))])
def vocabulary():
    return ProofLinks.link_vocabulary()


@router.get("/choices", dependencies=[Depends(require_permission(AUDIT_READ))])
def choices(type: str, org: str = Depends(get_current_org), svc: ProofLinks = Depends(get_proof_links)):
    return {"type": type, "choices": _run(lambda: svc.link_choices(org, type))}


@router.get("/graph", dependencies=[Depends(require_permission(AUDIT_READ))])
def graph(type: str, id: str, depth: int = 1, include_retired: bool = False, org: str = Depends(get_current_org), svc: ProofLinks = Depends(get_proof_links)):
    return _run(lambda: svc.neighbourhood(org, type, id, depth, include_retired))


@router.get("", dependencies=[Depends(require_permission(AUDIT_READ))])
def list_all(status: Optional[str] = None, org: str = Depends(get_current_org), svc: ProofLinks = Depends(get_proof_links)):
    return {"links": svc.list_links(org, status)}


@router.post("", status_code=201, dependencies=[Depends(require_permission(GRC_PREPARE))])
def add(body: LinkBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProofLinks = Depends(get_proof_links)):
    return _run(lambda: svc.link_records(org, (body.from_ref.type, body.from_ref.id), (body.to_ref.type, body.to_ref.id), body.relation, actor, body.note))


@router.post("/gaps", status_code=201, dependencies=[Depends(require_permission(GRC_PREPARE))])
def expect(body: GapBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProofLinks = Depends(get_proof_links)):
    return _run(lambda: svc.expect_link(org, (body.from_ref.type, body.from_ref.id), body.relation, actor, body.note, body.expected_type))


@router.post("/gaps/{gap_id}/waive", dependencies=[Depends(require_permission(GRC_APPROVE))])
def waive(gap_id: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProofLinks = Depends(get_proof_links)):
    return _run(lambda: svc.waive_gap(org, gap_id, actor, body.reason))


@router.get("/{link_id}", dependencies=[Depends(require_permission(AUDIT_READ))])
def get_one(link_id: str, org: str = Depends(get_current_org), svc: ProofLinks = Depends(get_proof_links)):
    return _run(lambda: svc.get_link(org, link_id))


@router.post("/{link_id}/retire", dependencies=[Depends(require_permission(GRC_PREPARE))])
def retire(link_id: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProofLinks = Depends(get_proof_links)):
    return _run(lambda: svc.retire_link(org, link_id, actor, body.reason))


@router.post("/{link_id}/dispute", dependencies=[Depends(require_permission(GRC_PREPARE))])
def dispute(link_id: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProofLinks = Depends(get_proof_links)):
    return _run(lambda: svc.dispute_link(org, link_id, actor, body.reason))


@router.post("/{link_id}/confirm", dependencies=[Depends(require_permission(GRC_APPROVE))])
def confirm(link_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProofLinks = Depends(get_proof_links)):
    return _run(lambda: svc.confirm_link(org, link_id, actor, body.note))


@router.post("/{link_id}/reinstate", dependencies=[Depends(require_permission(GRC_APPROVE))])
def reinstate(link_id: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProofLinks = Depends(get_proof_links)):
    return _run(lambda: svc.reinstate_link(org, link_id, actor, body.reason))
