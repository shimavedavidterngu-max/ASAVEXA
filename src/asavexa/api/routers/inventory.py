"""Inventory endpoints (records and evidence): stock items, receipts, issues, approved adjustments and weighted-average valuation. Thin: the rules live in asavexa.inventory.

Viewing needs audit:read. Adding items, recording receipts and issues and proposing adjustments need inventory:prepare. Discontinuing items, approving or rejecting adjustments and setting the policy need inventory:approve;
the service refuses the person whose work is being decided. The organisation always comes from the signed-in session. Nothing here posts to a ledger or counts stock."""
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, INV_APPROVE, INV_PREPARE
from ...inventory.service import InventoryService
from ..deps import get_current_actor, get_current_org, get_inventory, require_permission

router = APIRouter(prefix="/inventory", tags=["Inventory"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(INV_PREPARE))
_approve = Depends(require_permission(INV_APPROVE))


class ReasonBody(BaseModel):
    reason: str = ""


class NoteBody(BaseModel):
    note: Optional[str] = None


class PolicyBody(BaseModel):
    stale_days: Optional[Any] = None


class ItemBody(BaseModel):
    sku: Optional[str] = None
    name: Optional[str] = None
    unit: Optional[str] = None
    currency: Optional[str] = None
    reorder_level: Optional[Any] = None
    location: Optional[str] = None


class MoveBody(BaseModel):
    qty: Optional[Any] = None
    unit_cost: Optional[Any] = None
    moved_on: Optional[str] = None
    reference: Optional[str] = None


class AdjustBody(BaseModel):
    direction: Optional[str] = None
    qty: Optional[Any] = None
    unit_cost: Optional[Any] = None
    reason_kind: Optional[str] = None
    reason: Optional[str] = None


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: InventoryService = Depends(get_inventory)): return svc.iv_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: InventoryService = Depends(get_inventory)): return svc.iv_overview(org)


@router.get("/policy")
def policy(org: str = Depends(get_current_org), svc: InventoryService = Depends(get_inventory)): return svc.iv_get_policy(org)


@router.put("/policy", dependencies=[_approve])
def set_policy(body: PolicyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InventoryService = Depends(get_inventory)):
    return svc.iv_set_policy(org, _d(body), actor)


@router.get("/items")
def items(status: Optional[str] = None, org: str = Depends(get_current_org), svc: InventoryService = Depends(get_inventory)): return svc.iv_list_items(org, status)


@router.post("/items", status_code=201, dependencies=[_prepare])
def add_item(body: ItemBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InventoryService = Depends(get_inventory)):
    return svc.iv_add_item(org, _d(body), actor)


@router.get("/items/{iid}")
def get_item(iid: str, org: str = Depends(get_current_org), svc: InventoryService = Depends(get_inventory)): return svc.iv_get_item(org, iid)


@router.post("/items/{iid}/discontinue", dependencies=[_approve])
def discontinue_item(iid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InventoryService = Depends(get_inventory)):
    return svc.iv_discontinue_item(org, iid, body.reason, actor)


@router.post("/items/{iid}/receive", dependencies=[_prepare])
def receive(iid: str, body: MoveBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InventoryService = Depends(get_inventory)):
    return svc.iv_receive(org, iid, _d(body), actor)


@router.post("/items/{iid}/issue", dependencies=[_prepare])
def issue(iid: str, body: MoveBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InventoryService = Depends(get_inventory)):
    return svc.iv_issue(org, iid, _d(body), actor)


@router.post("/items/{iid}/adjustments", dependencies=[_prepare])
def propose_adjustment(iid: str, body: AdjustBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InventoryService = Depends(get_inventory)):
    return svc.iv_propose_adjustment(org, iid, _d(body), actor)


@router.post("/items/{iid}/adjustments/{no}/approve", dependencies=[_approve])
def approve_adjustment(iid: str, no: int, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InventoryService = Depends(get_inventory)):
    return svc.iv_approve_adjustment(org, iid, no, _d(body), actor)


@router.post("/items/{iid}/adjustments/{no}/reject", dependencies=[_approve])
def reject_adjustment(iid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InventoryService = Depends(get_inventory)):
    return svc.iv_reject_adjustment(org, iid, no, body.reason, actor)
