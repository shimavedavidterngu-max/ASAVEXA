from typing import Optional

from fastapi import APIRouter, Depends

from ...identity.domain.permissions import (
    RECONCILIATION_APPROVE,
    RECONCILIATION_CREATE,
    RECONCILIATION_IMPORT,
    RECONCILIATION_MATCH,
    RECONCILIATION_READ,
)
from ...reconciliation.domain.models import BankTransactionInput
from ...reconciliation.services.service import ReconciliationService
from ..deps import get_current_actor, get_current_org, get_reconciliation_service, require_permission
from ..schemas.reconciliation import (
    AttachEvidenceRequest,
    BankTransactionOut,
    ImportTransactionsRequest,
    ManualMatchRequest,
    ReconciliationCreate,
    ReconciliationOut,
    RejectMatchRequest,
    RejectReconciliationRequest,
)

router = APIRouter(prefix="/reconciliations", tags=["Reconciliation"])


@router.post("", response_model=ReconciliationOut, status_code=201,
             dependencies=[Depends(require_permission(RECONCILIATION_CREATE))])
def create_reconciliation(
    body: ReconciliationCreate,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ReconciliationService = Depends(get_reconciliation_service),
):
    return service.create_reconciliation(
        org_id, body.bank_account_id, body.name, body.period_start, body.period_end,
        actor=actor, currency=body.currency,
    )


@router.get("", response_model=list[ReconciliationOut],
            dependencies=[Depends(require_permission(RECONCILIATION_READ))])
def list_reconciliations(
    bank_account_id: Optional[str] = None,
    org_id: str = Depends(get_current_org),
    service: ReconciliationService = Depends(get_reconciliation_service),
):
    return service.list_reconciliations(org_id, bank_account_id=bank_account_id)


@router.get("/{reconciliation_id}", response_model=ReconciliationOut,
            dependencies=[Depends(require_permission(RECONCILIATION_READ))])
def get_reconciliation(
    reconciliation_id: str,
    org_id: str = Depends(get_current_org),
    service: ReconciliationService = Depends(get_reconciliation_service),
):
    return service.get_reconciliation(org_id, reconciliation_id)


@router.post("/{reconciliation_id}/transactions", response_model=list[BankTransactionOut], status_code=201,
             dependencies=[Depends(require_permission(RECONCILIATION_IMPORT))])
def import_transactions(
    reconciliation_id: str,
    body: ImportTransactionsRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ReconciliationService = Depends(get_reconciliation_service),
):
    rows = [
        BankTransactionInput(
            transaction_date=r.transaction_date, description=r.description,
            debit_amount=r.debit_amount, credit_amount=r.credit_amount,
            value_date=r.value_date, external_ref=r.external_ref, currency=r.currency,
        )
        for r in body.rows
    ]
    return service.import_transactions(org_id, reconciliation_id, rows, actor=actor, import_source=body.import_source)


@router.get("/{reconciliation_id}/transactions", response_model=list[BankTransactionOut],
            dependencies=[Depends(require_permission(RECONCILIATION_READ))])
def list_transactions(
    reconciliation_id: str,
    org_id: str = Depends(get_current_org),
    service: ReconciliationService = Depends(get_reconciliation_service),
):
    return service.list_transactions(org_id, reconciliation_id)


@router.post("/{reconciliation_id}/submit", response_model=ReconciliationOut,
             dependencies=[Depends(require_permission(RECONCILIATION_CREATE))])
def submit_reconciliation(
    reconciliation_id: str,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ReconciliationService = Depends(get_reconciliation_service),
):
    return service.submit_reconciliation(org_id, reconciliation_id, actor=actor)


@router.post("/{reconciliation_id}/approve", response_model=ReconciliationOut,
             dependencies=[Depends(require_permission(RECONCILIATION_APPROVE))])
def approve_reconciliation(
    reconciliation_id: str,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ReconciliationService = Depends(get_reconciliation_service),
):
    """Finalizes the reconciliation — requires every transaction in it
    to already be individually APPROVED (see POST .../transactions/{id}/approve).
    Never accepts a client-supplied status; the only way to reach
    RECONCILED is through this call succeeding."""
    return service.approve_reconciliation(org_id, reconciliation_id, actor=actor)


@router.post("/{reconciliation_id}/reject", response_model=ReconciliationOut,
             dependencies=[Depends(require_permission(RECONCILIATION_APPROVE))])
def reject_reconciliation(
    reconciliation_id: str,
    body: RejectReconciliationRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ReconciliationService = Depends(get_reconciliation_service),
):
    return service.reject_reconciliation(org_id, reconciliation_id, actor=actor, reason=body.reason)


@router.post("/{reconciliation_id}/evidence", response_model=ReconciliationOut,
             dependencies=[Depends(require_permission(RECONCILIATION_CREATE))])
def attach_evidence(
    reconciliation_id: str,
    body: AttachEvidenceRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ReconciliationService = Depends(get_reconciliation_service),
):
    """Stores an id already returned by POST /evidence — this endpoint
    does not accept a file itself. Upload to the Evidence Vault first."""
    return service.attach_evidence(org_id, reconciliation_id, evidence_id=body.evidence_id, actor=actor)


# ----------------------------------------------------------------------
# Per-transaction actions
# ----------------------------------------------------------------------
txn_router = APIRouter(prefix="/reconciliations/transactions", tags=["Reconciliation"])


@txn_router.get("/{transaction_id}", response_model=BankTransactionOut,
                 dependencies=[Depends(require_permission(RECONCILIATION_READ))])
def get_transaction(
    transaction_id: str,
    org_id: str = Depends(get_current_org),
    service: ReconciliationService = Depends(get_reconciliation_service),
):
    return service.get_transaction(org_id, transaction_id)


@txn_router.post("/{transaction_id}/manual-match", response_model=BankTransactionOut,
                  dependencies=[Depends(require_permission(RECONCILIATION_MATCH))])
def manual_match(
    transaction_id: str,
    body: ManualMatchRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ReconciliationService = Depends(get_reconciliation_service),
):
    return service.manual_match(org_id, transaction_id, body.journal_id, actor=actor, note=body.note)


@txn_router.post("/{transaction_id}/reject-match", response_model=BankTransactionOut,
                  dependencies=[Depends(require_permission(RECONCILIATION_APPROVE))])
def reject_match(
    transaction_id: str,
    body: RejectMatchRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ReconciliationService = Depends(get_reconciliation_service),
):
    """A checker action — disagreeing with a proposed match requires
    the same RECONCILIATION_APPROVE permission as approving one."""
    return service.reject_match(org_id, transaction_id, actor=actor, reason=body.reason)


@txn_router.post("/{transaction_id}/approve", response_model=BankTransactionOut,
                  dependencies=[Depends(require_permission(RECONCILIATION_APPROVE))])
def approve_transaction(
    transaction_id: str,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ReconciliationService = Depends(get_reconciliation_service),
):
    return service.approve_transaction(org_id, transaction_id, actor=actor)
