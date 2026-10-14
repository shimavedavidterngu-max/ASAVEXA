"""Procurement endpoints (records and evidence): suppliers, contracts, purchase orders, deliveries, invoices with three-way matching, and supplier reviews.
Thin: the rules live in asavexa.procurement.

Viewing needs reporting:read. Registering suppliers, drafting contracts, raising orders, recording deliveries and invoices, marking an invoice paid and reviewing suppliers
need procure:prepare. Approving a supplier, contract, order or invoice, suspending or reinstating a supplier and setting the policy need procure:approve; the service
refuses the person who created the thing being decided. The organisation always comes from the signed-in session."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import PROCURE_APPROVE, PROCURE_PREPARE, REPORTING_READ
from ...procurement.service import ProcurementService
from ..deps import get_current_actor, get_current_org, get_procurement, require_permission

router = APIRouter(prefix="/procurement", tags=["Procurement"], dependencies=[Depends(require_permission(REPORTING_READ))])
_prepare = Depends(require_permission(PROCURE_PREPARE))
_approve = Depends(require_permission(PROCURE_APPROVE))


class NoteBody(BaseModel):
    note: str = ""


class SupplierBody(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    country: Optional[str] = None
    contact: Optional[str] = None
    tax_ref: Optional[str] = None
    related_party: Optional[bool] = None
    related_party_note: Optional[str] = None


class ContractBody(BaseModel):
    supplier_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    currency: Optional[str] = None
    ceiling: Optional[Any] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class OrderBody(BaseModel):
    supplier_id: Optional[str] = None
    contract_id: Optional[str] = None
    currency: Optional[str] = None
    expected_date: Optional[str] = None
    purpose: Optional[str] = None
    lines: List[Dict[str, Any]] = []


class DeliveryBody(BaseModel):
    received_date: Optional[str] = None
    note: Optional[str] = None
    lines: List[Dict[str, Any]] = []


class InvoiceBody(BaseModel):
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    currency: Optional[str] = None
    lines: List[Dict[str, Any]] = []


class PaidBody(BaseModel):
    treasury_payment_id: Optional[str] = None
    paid_date: Optional[str] = None
    bank_reference: Optional[str] = None


class ReviewBody(BaseModel):
    period: Optional[str] = None
    scores: Optional[Dict[str, Any]] = None
    comment: Optional[str] = None


class PolicyBody(BaseModel):
    tolerance_pct: Optional[Any] = None
    dual_limits: Optional[Dict[str, Any]] = None
    warning_days: Optional[int] = None


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: ProcurementService = Depends(get_procurement)): return svc.procurement_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: ProcurementService = Depends(get_procurement)): return svc.procurement_overview(org)


@router.get("/policy")
def policy(org: str = Depends(get_current_org), svc: ProcurementService = Depends(get_procurement)): return svc.get_procurement_policy(org)


@router.put("/policy", dependencies=[_approve])
def set_policy(body: PolicyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProcurementService = Depends(get_procurement)):
    return svc.set_procurement_policy(org, _d(body), actor)


@router.get("/suppliers")
def suppliers(status: Optional[str] = None, org: str = Depends(get_current_org), svc: ProcurementService = Depends(get_procurement)): return svc.list_suppliers(org, status)


@router.post("/suppliers", status_code=201, dependencies=[_prepare])
def register_supplier(body: SupplierBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProcurementService = Depends(get_procurement)):
    return svc.register_supplier(org, _d(body), actor)


@router.get("/suppliers/{sid}")
def get_supplier(sid: str, org: str = Depends(get_current_org), svc: ProcurementService = Depends(get_procurement)): return svc.get_supplier(org, sid)


@router.post("/suppliers/{sid}/approve", dependencies=[_approve])
def approve_supplier(sid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProcurementService = Depends(get_procurement)):
    return svc.approve_supplier(org, sid, actor, body.note)


@router.post("/suppliers/{sid}/suspend", dependencies=[_approve])
def suspend_supplier(sid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProcurementService = Depends(get_procurement)):
    return svc.suspend_supplier(org, sid, body.note, actor)


@router.post("/suppliers/{sid}/reinstate", dependencies=[_approve])
def reinstate_supplier(sid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProcurementService = Depends(get_procurement)):
    return svc.reinstate_supplier(org, sid, body.note, actor)


@router.get("/contracts")
def contracts(org: str = Depends(get_current_org), svc: ProcurementService = Depends(get_procurement)): return svc.list_contracts(org)


@router.post("/contracts", status_code=201, dependencies=[_prepare])
def draft_contract(body: ContractBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProcurementService = Depends(get_procurement)):
    return svc.draft_contract(org, _d(body), actor)


@router.get("/contracts/{cid}")
def get_contract(cid: str, org: str = Depends(get_current_org), svc: ProcurementService = Depends(get_procurement)): return svc.get_contract(org, cid)


@router.post("/contracts/{cid}/approve", dependencies=[_approve])
def approve_contract(cid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProcurementService = Depends(get_procurement)):
    return svc.approve_contract(org, cid, actor, body.note)


@router.post("/contracts/{cid}/terminate", dependencies=[_approve])
def terminate_contract(cid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProcurementService = Depends(get_procurement)):
    return svc.terminate_contract(org, cid, body.note, actor)


@router.get("/orders")
def orders(status: Optional[str] = None, supplier_id: Optional[str] = None, org: str = Depends(get_current_org), svc: ProcurementService = Depends(get_procurement)):
    return svc.list_purchase_orders(org, status, supplier_id)


@router.post("/orders", status_code=201, dependencies=[_prepare])
def raise_order(body: OrderBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProcurementService = Depends(get_procurement)):
    return svc.raise_purchase_order(org, _d(body), actor)


@router.get("/orders/{oid}")
def get_order(oid: str, org: str = Depends(get_current_org), svc: ProcurementService = Depends(get_procurement)): return svc.get_purchase_order(org, oid)


@router.post("/orders/{oid}/approve", dependencies=[_approve])
def approve_order(oid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProcurementService = Depends(get_procurement)):
    return svc.approve_purchase_order(org, oid, actor, body.note)


@router.post("/orders/{oid}/reject", dependencies=[_approve])
def reject_order(oid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProcurementService = Depends(get_procurement)):
    return svc.reject_purchase_order(org, oid, body.note, actor)


@router.post("/orders/{oid}/cancel", dependencies=[_prepare])
def cancel_order(oid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProcurementService = Depends(get_procurement)):
    return svc.cancel_purchase_order(org, oid, body.note, actor)


@router.post("/orders/{oid}/close", dependencies=[_prepare])
def close_order(oid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProcurementService = Depends(get_procurement)):
    return svc.close_purchase_order(org, oid, body.note, actor)


@router.get("/deliveries")
def deliveries(order_id: Optional[str] = None, org: str = Depends(get_current_org), svc: ProcurementService = Depends(get_procurement)): return svc.list_deliveries(org, order_id)


@router.post("/orders/{oid}/deliveries", status_code=201, dependencies=[_prepare])
def add_delivery(oid: str, body: DeliveryBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProcurementService = Depends(get_procurement)):
    return svc.record_delivery(org, oid, _d(body), actor)


@router.get("/invoices")
def invoices(status: Optional[str] = None, order_id: Optional[str] = None, org: str = Depends(get_current_org), svc: ProcurementService = Depends(get_procurement)):
    return svc.list_invoices(org, status, order_id)


@router.post("/orders/{oid}/invoices", status_code=201, dependencies=[_prepare])
def add_invoice(oid: str, body: InvoiceBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProcurementService = Depends(get_procurement)):
    return svc.record_invoice(org, oid, _d(body), actor)


@router.get("/invoices/{iid}")
def get_invoice(iid: str, org: str = Depends(get_current_org), svc: ProcurementService = Depends(get_procurement)): return svc.get_invoice(org, iid)


@router.post("/invoices/{iid}/approve", dependencies=[_approve])
def approve_invoice(iid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProcurementService = Depends(get_procurement)):
    return svc.approve_invoice(org, iid, actor, body.note)


@router.post("/invoices/{iid}/reject", dependencies=[_approve])
def reject_invoice(iid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProcurementService = Depends(get_procurement)):
    return svc.reject_invoice(org, iid, body.note, actor)


@router.post("/invoices/{iid}/paid", dependencies=[_prepare])
def pay_invoice(iid: str, body: PaidBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProcurementService = Depends(get_procurement)):
    return svc.mark_invoice_paid(org, iid, _d(body), actor)


@router.get("/reviews")
def reviews(supplier_id: Optional[str] = None, org: str = Depends(get_current_org), svc: ProcurementService = Depends(get_procurement)): return svc.list_supplier_reviews(org, supplier_id)


@router.post("/suppliers/{sid}/reviews", status_code=201, dependencies=[_prepare])
def add_review(sid: str, body: ReviewBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProcurementService = Depends(get_procurement)):
    return svc.review_supplier(org, sid, _d(body), actor)
