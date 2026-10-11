"""Health Centre Administration endpoints (financial and administrative; no patient information). Thin: the rules live in asavexa.health.

Everything is scoped to a facility the caller has been given access to; a facility that is not theirs is reported as not found. Viewing needs health:read. Raising, receiving, recording and
requesting need health:prepare. Approving budgets, orders, payments, adjustments, write-offs and reports needs health:approve (the service refuses the person who raised the item).
Facilities, departments and facility access need health:admin. Claims need health:claims and staffing costs need health:staffing, which administrators do not hold by default."""
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response

from ...health.service import HealthService
from ...identity.domain.permissions import HEALTH_ADMIN, HEALTH_APPROVE, HEALTH_CLAIMS, HEALTH_PREPARE, HEALTH_READ, HEALTH_STAFFING
from ..deps import get_current_actor, get_current_org, get_health, require_permission

router = APIRouter(prefix="/health", tags=["Health Centre Administration"], dependencies=[Depends(require_permission(HEALTH_READ))])
_prepare = [Depends(require_permission(HEALTH_PREPARE))]
_approve = [Depends(require_permission(HEALTH_APPROVE))]
_admin = [Depends(require_permission(HEALTH_ADMIN))]
_claims = [Depends(require_permission(HEALTH_CLAIMS))]
_claims_prepare = _claims + _prepare
_claims_approve = _claims + _approve
_staff = [Depends(require_permission(HEALTH_STAFFING))]
_staff_approve = _staff + _approve
B = Dict[str, Any]
O, A, S = Depends(get_current_org), Depends(get_current_actor), Depends(get_health)


def _d(v: Optional[str], name: str) -> Optional[date]:
    if not v: return None
    try: return date.fromisoformat(v)
    except ValueError: raise HTTPException(status_code=400, detail=f"{name} must be a date written YYYY-MM-DD.")


def _csv(out: dict) -> Response:
    return Response(content=out["content"], media_type=out["content_type"], headers={"Content-Disposition": f'attachment; filename="{out["filename"]}"', "Cache-Control": "no-store"})


@router.get("/options")
def options(org: str = O, a: str = A, s: HealthService = S): return s.options(org, a)


@router.get("/access", dependencies=_admin)
def get_access(org: str = O, a: str = A, s: HealthService = S): return s.get_access(org, a)

@router.put("/access/{user_id}", dependencies=_admin)
def set_access(user_id: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.set_access(org, user_id, body.get('facility_ids') or [], a)

@router.get("/facilities")
def facilities(org: str = O, a: str = A, s: HealthService = S): return s.list_facilities(org, a)

@router.post("/facilities", status_code=201, dependencies=_admin)
def create_facility(body: B, org: str = O, a: str = A, s: HealthService = S): return s.create_facility(org, body, a)

@router.get("/facilities/{fid}")
def get_facility(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.get_facility(org, fid, a)

@router.put("/facilities/{fid}", dependencies=_admin)
def update_facility(fid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.update_facility(org, fid, body, a)

@router.post("/facilities/{fid}/status", dependencies=_admin)
def facility_status(fid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.set_facility_status(org, fid, bool(body.get('active')), body.get('note'), a)

@router.post("/facilities/{fid}/departments", status_code=201, dependencies=_admin)
def add_department(fid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.add_department(org, fid, body, a)

@router.post("/facilities/{fid}/departments/{did}/active", dependencies=_admin)
def department_active(fid: str, did: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.set_department_active(org, fid, did, bool(body.get('active')), a)

@router.get("/facilities/{fid}/dashboard")
def dashboard(fid: str, start: Optional[str] = None, end: Optional[str] = None, org: str = O, a: str = A, s: HealthService = S): return s.dashboard(org, fid, a, _d(start, 'Start'), _d(end, 'End'))

@router.get("/facilities/{fid}/budgets")
def budgets(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.list_budgets(org, fid, a)

@router.post("/facilities/{fid}/budgets", status_code=201, dependencies=_prepare)
def create_budget(fid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.create_budget(org, fid, body, a)

@router.get("/facilities/{fid}/budgets/{bid}/execution")
def execution(fid: str, bid: str, org: str = O, a: str = A, s: HealthService = S): return s.execution(org, fid, bid, a)

@router.get("/budgets/{bid}")
def get_budget(bid: str, org: str = O, a: str = A, s: HealthService = S): return s.get_budget(org, bid, a)

@router.put("/budgets/{bid}", dependencies=_prepare)
def update_budget(bid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.update_budget(org, bid, body, a)

@router.post("/budgets/{bid}/submit", dependencies=_prepare)
def submit_budget(bid: str, org: str = O, a: str = A, s: HealthService = S): return s.submit_budget(org, bid, a)

@router.post("/budgets/{bid}/approve", dependencies=_approve)
def approve_budget(bid: str, org: str = O, a: str = A, s: HealthService = S): return s.approve_budget(org, bid, a)

@router.post("/budgets/{bid}/reject", dependencies=_approve)
def reject_budget(bid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.reject_budget(org, bid, body.get('note'), a)

@router.post("/budgets/{bid}/revise", status_code=201, dependencies=_prepare)
def revise_budget(bid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.revise_budget(org, bid, body.get('note'), a)

@router.post("/budgets/{bid}/transfers", status_code=201, dependencies=_prepare)
def request_transfer(bid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.request_transfer(org, bid, body.get('from_line'), body.get('to_line'), body.get('amount'), body.get('reason'), a)

@router.post("/budgets/{bid}/transfers/{tid}/decide", dependencies=_approve)
def decide_transfer(bid: str, tid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.decide_transfer(org, bid, tid, bool(body.get('ok')), body.get('note'), a)

@router.get("/facilities/{fid}/suppliers")
def suppliers(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.list_suppliers(org, fid, a)

@router.post("/facilities/{fid}/suppliers", status_code=201, dependencies=_prepare)
def create_supplier(fid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.create_supplier(org, fid, body, a)

@router.post("/suppliers/{sid}/status", dependencies=_prepare)
def supplier_status(sid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.set_supplier_status(org, sid, bool(body.get('authorised')), body.get('note'), a)

@router.get("/facilities/{fid}/requisitions")
def requisitions(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.list_requisitions(org, fid, a)

@router.post("/facilities/{fid}/requisitions", status_code=201, dependencies=_prepare)
def create_requisition(fid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.create_requisition(org, fid, body, a)

@router.put("/requisitions/{rid}", dependencies=_prepare)
def update_requisition(rid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.update_requisition(org, rid, body, a)

@router.post("/requisitions/{rid}/submit", dependencies=_prepare)
def submit_requisition(rid: str, org: str = O, a: str = A, s: HealthService = S): return s.submit_requisition(org, rid, a)

@router.post("/requisitions/{rid}/decide", dependencies=_approve)
def decide_requisition(rid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.decide_requisition(org, rid, bool(body.get('ok')), body.get('note'), a)

@router.post("/requisitions/{rid}/quotes", status_code=201, dependencies=_prepare)
def add_quote(rid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.add_quote(org, rid, body, a)

@router.post("/requisitions/{rid}/po", status_code=201, dependencies=_prepare)
def create_po(rid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.create_po(org, rid, body.get('supplier_id'), a)

@router.get("/facilities/{fid}/pos")
def pos(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.list_pos(org, fid, a)

@router.post("/pos/{pid}/approve", dependencies=_approve)
def approve_po(pid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.approve_po(org, pid, body.get('exception_note'), a)

@router.post("/pos/{pid}/cancel", dependencies=_prepare)
def cancel_po(pid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.cancel_po(org, pid, body.get('note'), a)

@router.post("/pos/{pid}/receive", status_code=201, dependencies=_prepare)
def receive_goods(pid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.receive_goods(org, pid, body, a)

@router.post("/pos/{pid}/invoices", status_code=201, dependencies=_prepare)
def record_invoice(pid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.record_invoice(org, pid, body, a)

@router.get("/facilities/{fid}/goods-receipts")
def goods_receipts(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.list_receipts(org, fid, a)

@router.get("/facilities/{fid}/invoices")
def invoices(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.list_invoices(org, fid, a)

@router.post("/invoices/{iid}/verify", dependencies=_approve)
def verify_invoice(iid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.verify_invoice(org, iid, body.get('exception_note'), a)

@router.post("/invoices/{iid}/approve-payment", dependencies=_approve)
def approve_payment(iid: str, org: str = O, a: str = A, s: HealthService = S): return s.approve_payment(org, iid, a)

@router.post("/invoices/{iid}/pay", dependencies=_prepare)
def pay_invoice(iid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.pay_invoice(org, iid, body.get('payment_ref'), a)

@router.post("/invoices/{iid}/credit", dependencies=_approve)
def credit_note(iid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.credit_note(org, iid, body.get('amount'), body.get('reason'), a)

@router.post("/invoices/{iid}/cancel", dependencies=_prepare)
def cancel_invoice(iid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.cancel_invoice(org, iid, body.get('note'), a)

@router.get("/facilities/{fid}/payables-ageing")
def payables_ageing(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.payables_ageing(org, fid, a)

@router.get("/facilities/{fid}/procurement-exceptions")
def procurement_exceptions(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.procurement_exceptions(org, fid, a)

@router.get("/facilities/{fid}/items")
def items(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.list_items(org, fid, a)

@router.post("/facilities/{fid}/items", status_code=201, dependencies=_prepare)
def create_item(fid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.create_item(org, fid, body, a)

@router.put("/items/{iid}", dependencies=_prepare)
def update_item(iid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.update_item(org, iid, body, a)

@router.get("/facilities/{fid}/stock")
def stock(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.stock_levels(org, fid, a)

@router.get("/items/{iid}/movements")
def movements(iid: str, org: str = O, a: str = A, s: HealthService = S): return s.movements(org, iid, a)

@router.post("/items/{iid}/issue", status_code=201, dependencies=_prepare)
def issue_stock(iid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.issue_stock(org, iid, body, a)

@router.post("/items/{iid}/transfer", status_code=201, dependencies=_prepare)
def transfer_stock(iid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.transfer_stock(org, iid, body, a)

@router.post("/items/{iid}/adjustments", status_code=201, dependencies=_prepare)
def request_adjustment(iid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.request_adjustment(org, iid, body, a)

@router.post("/items/{iid}/count", status_code=201, dependencies=_prepare)
def record_count(iid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.record_count(org, iid, body, a)

@router.get("/facilities/{fid}/adjustments")
def adjustments(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.list_adjustments(org, fid, a)

@router.post("/adjustments/{aid}/decide", dependencies=_approve)
def decide_adjustment(aid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.decide_adjustment(org, aid, bool(body.get('ok')), body.get('note'), a)

@router.get("/facilities/{fid}/fees")
def fees(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.list_fees(org, fid, a)

@router.post("/facilities/{fid}/fees", status_code=201, dependencies=_prepare)
def create_fee(fid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.create_fee(org, fid, body, a)

@router.post("/fees/{feeid}/retire", dependencies=_prepare)
def retire_fee(feeid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.retire_fee(org, feeid, body.get('note'), a)

@router.get("/facilities/{fid}/receipts")
def receipts(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.list_receipts_revenue(org, fid, a)

@router.post("/facilities/{fid}/receipts", status_code=201, dependencies=_prepare)
def record_receipt(fid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.record_receipt(org, fid, body, a)

@router.post("/receipts/{rid}/refunds", status_code=201, dependencies=_prepare)
def request_refund(rid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.request_refund(org, rid, body.get('amount'), body.get('reason'), a)

@router.post("/receipts/{rid}/refunds/{xid}/decide", dependencies=_approve)
def decide_refund(rid: str, xid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.decide_refund(org, rid, xid, bool(body.get('ok')), body.get('note'), a)

@router.get("/facilities/{fid}/revenue-summary")
def revenue_summary(fid: str, start: Optional[str] = None, end: Optional[str] = None, org: str = O, a: str = A, s: HealthService = S): return s.revenue_summary(org, fid, a, _d(start, 'Start'), _d(end, 'End'))

@router.get("/facilities/{fid}/payers")
def payers(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.list_payers(org, fid, a)

@router.post("/facilities/{fid}/payers", status_code=201, dependencies=_prepare)
def create_payer(fid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.create_payer(org, fid, body, a)

@router.get("/facilities/{fid}/claims", dependencies=_claims)
def claims(fid: str, status: Optional[str] = None, org: str = O, a: str = A, s: HealthService = S): return s.list_claims(org, fid, a, status or None)

@router.post("/facilities/{fid}/claims", status_code=201, dependencies=_claims_prepare)
def create_claim(fid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.create_claim(org, fid, body, a)

@router.get("/claims/{cid}", dependencies=_claims)
def get_claim(cid: str, org: str = O, a: str = A, s: HealthService = S): return s.get_claim(org, cid, a)

@router.post("/claims/{cid}/submit", dependencies=_claims_prepare)
def submit_claim(cid: str, org: str = O, a: str = A, s: HealthService = S): return s.submit_claim(org, cid, a)

@router.post("/claims/{cid}/reject", dependencies=_claims_prepare)
def reject_claim(cid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.reject_claim(org, cid, body.get('code'), body.get('note'), a)

@router.post("/claims/{cid}/resubmit", dependencies=_claims_prepare)
def resubmit_claim(cid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.resubmit_claim(org, cid, body.get('amount'), body.get('note'), a)

@router.post("/claims/{cid}/payments", status_code=201, dependencies=_claims_prepare)
def pay_claim(cid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.pay_claim(org, cid, body, a)

@router.post("/claims/{cid}/writeoff", dependencies=_claims_prepare)
def request_writeoff(cid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.request_writeoff(org, cid, body.get('reason'), a)

@router.post("/claims/{cid}/writeoff/decide", dependencies=_claims_approve)
def decide_writeoff(cid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.decide_writeoff(org, cid, bool(body.get('ok')), body.get('note'), a)

@router.get("/facilities/{fid}/receivables-ageing", dependencies=_claims)
def receivables_ageing(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.receivables_ageing(org, fid, a)

@router.post("/facilities/{fid}/payers/{pid}/reconcile", status_code=201, dependencies=_claims_prepare)
def reconcile_payer(fid: str, pid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.payer_reconciliation(org, fid, pid, body, a)

@router.get("/facilities/{fid}/reconciliations", dependencies=_claims)
def reconciliations(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.list_reconciliations(org, fid, a)

@router.post("/reconciliations/{rid}/resolve", dependencies=_claims_prepare)
def resolve_reconciliation(rid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.resolve_reconciliation(org, rid, body.get('note'), a)

@router.get("/facilities/{fid}/assets")
def assets(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.list_assets(org, fid, a)

@router.post("/facilities/{fid}/assets", status_code=201, dependencies=_prepare)
def create_asset(fid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.create_asset(org, fid, body, a)

@router.post("/assets/{aid}/condition", dependencies=_prepare)
def asset_condition(aid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.set_condition(org, aid, body.get('condition'), body.get('note'), a)

@router.post("/assets/{aid}/evidence", dependencies=_prepare)
def asset_evidence(aid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.link_asset_evidence(org, aid, body.get('evidence_ids') or [], a)

@router.post("/assets/{aid}/retirement", dependencies=_prepare)
def request_retirement(aid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.request_retirement(org, aid, body.get('reason'), a)

@router.post("/assets/{aid}/retirement/decide", dependencies=_approve)
def decide_retirement(aid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.decide_retirement(org, aid, bool(body.get('ok')), body.get('note'), a)

@router.post("/assets/{aid}/maintenance", status_code=201, dependencies=_prepare)
def request_maintenance(aid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.request_maintenance(org, aid, body, a)

@router.get("/facilities/{fid}/maintenance")
def maintenance(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.list_maintenance(org, fid, a)

@router.post("/maintenance/{mid}/complete", dependencies=_prepare)
def complete_maintenance(mid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.complete_maintenance(org, mid, body, a)

@router.post("/maintenance/{mid}/cancel", dependencies=_prepare)
def cancel_maintenance(mid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.cancel_maintenance(org, mid, body.get('note'), a)

@router.get("/facilities/{fid}/maintenance-due")
def maintenance_due(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.maintenance_due(org, fid, a)

@router.get("/facilities/{fid}/downtime")
def downtime(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.downtime_summary(org, fid, a)

@router.get("/facilities/{fid}/staffing", dependencies=_staff)
def staffing(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.list_staffing(org, fid, a)

@router.post("/facilities/{fid}/staffing", status_code=201, dependencies=_staff)
def record_staffing(fid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.record_staffing(org, fid, body, a)

@router.post("/staffing/{sid}/decide", dependencies=_staff_approve)
def decide_staffing(sid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.decide_staffing(org, sid, bool(body.get('ok')), body.get('note'), a)

@router.get("/facilities/{fid}/reports")
def reports(fid: str, org: str = O, a: str = A, s: HealthService = S): return s.list_reports(org, fid, a)

@router.post("/facilities/{fid}/reports", status_code=201, dependencies=_prepare)
def create_report(fid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.create_report(org, fid, body, a)

@router.get("/reports/{rid}")
def get_report(rid: str, org: str = O, a: str = A, s: HealthService = S): return s.get_report(org, rid, a)

@router.post("/reports/{rid}/submit", dependencies=_prepare)
def submit_report(rid: str, org: str = O, a: str = A, s: HealthService = S): return s.submit_report(org, rid, a)

@router.post("/reports/{rid}/decide", dependencies=_approve)
def decide_report(rid: str, body: B, org: str = O, a: str = A, s: HealthService = S): return s.decide_report(org, rid, bool(body.get('ok')), body.get('note'), a)

@router.get("/reports/{rid}/export")
def export_report(rid: str, org: str = O, a: str = A, s: HealthService = S): return _csv(s.export_csv(org, rid, a))
