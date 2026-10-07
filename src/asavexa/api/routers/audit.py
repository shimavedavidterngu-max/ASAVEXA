from fastapi import APIRouter, Depends

from ...audit.repository import AuditRepository
from ...identity.domain.permissions import AUDIT_READ
from ..deps import get_audit_repository, get_current_org, require_permission

router = APIRouter(
    prefix="/audit", tags=["Audit Trail"],
    dependencies=[Depends(require_permission(AUDIT_READ))],
)


@router.get("/entity/{entity_type}/{entity_id}")
def get_entity_audit_trail(
    entity_type: str,
    entity_id: str,
    org_id: str = Depends(get_current_org),
    audit: AuditRepository = Depends(get_audit_repository),
):
    """
    Generic, read-only audit-event history for ANY entity in the
    system — Journal, Account, AccountingPeriod, Reconciliation,
    BankTransaction, ControlDefinition, ControlExecution, Finding,
    Remediation, Period, PeriodCloseProcess, Organisation, User,
    Membership, Session, EvidenceRecord, Report — exactly the
    `entity_type` strings each module already passes to its own
    `_log()` helper (see each service module's `self._log(...)` calls;
    none invented here).

    This is deliberately the ONE generic read path rather than a
    bespoke "/x/{id}/audit-trail" endpoint per module (journals.py's
    own /journals/{id}/audit-trail predates this and is left as-is —
    it is equivalent to calling this endpoint with entity_type="Journal").

    Phase 1 "approval history" is this same feed, filtered by the
    caller (frontend) for action names that represent an approval/
    review/rejection step (e.g. RECONCILIATION_APPROVED, CLOSE_APPROVED,
    CONTROL_REVIEWED, REMEDIATION_VERIFIED) — there is no separate
    "approvals" table; an approval is simply an audit event like any
    other, and filtering client-side keeps this endpoint honest: it
    never claims to know which actions "count" as an approval for
    every module.

    Scoped to the caller's current organisation: `list_for_entity`
    is always called with org_id, so one org can never read another
    org's audit history for a guessed entity_id.
    """
    return audit.list_for_entity(entity_type, entity_id, org_id=org_id)
