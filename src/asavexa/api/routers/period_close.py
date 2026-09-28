from typing import Optional

from fastapi import APIRouter, Depends

from ...identity.domain.permissions import (
    PERIOD_CLOSE_APPROVE,
    PERIOD_CLOSE_READ,
    PERIOD_CLOSE_REQUEST,
    PERIOD_CLOSE_REVIEW,
)
from ...period_close.services.service import PeriodCloseService
from ..deps import get_current_actor, get_current_org, get_period_close_service, require_permission
from ..schemas.period_close import (
    ApproveCloseRequest,
    CloseReadinessReportOut,
    PeriodCloseProcessOut,
    RejectCloseRequest,
    RequestCloseRequest,
)

router = APIRouter(prefix="/period-close", tags=["Period Close & Financial Controls"])


@router.post(
    "/periods/{period_id}/readiness", response_model=CloseReadinessReportOut,
    dependencies=[Depends(require_permission(PERIOD_CLOSE_READ))],
)
def check_close_readiness(
    period_id: str,
    body: RequestCloseRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: PeriodCloseService = Depends(get_period_close_service),
):
    """A pure, repeatable preview — never persists a PeriodCloseProcess.
    Anyone with period_close:read can ask "would this period be allowed
    to close right now?" without committing to a formal request."""
    return service.check_close_readiness(org_id, period_id, actor=actor, required_evidence_refs=body.required_evidence_refs)


@router.post(
    "/periods/{period_id}/request", response_model=PeriodCloseProcessOut, status_code=201,
    dependencies=[Depends(require_permission(PERIOD_CLOSE_REQUEST))],
)
def request_close(
    period_id: str,
    body: RequestCloseRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: PeriodCloseService = Depends(get_period_close_service),
):
    return service.request_close(org_id, period_id, actor=actor, required_evidence_refs=body.required_evidence_refs)


@router.get(
    "/periods/{period_id}/active", response_model=Optional[PeriodCloseProcessOut],
    dependencies=[Depends(require_permission(PERIOD_CLOSE_READ))],
)
def get_active_process(
    period_id: str,
    org_id: str = Depends(get_current_org),
    service: PeriodCloseService = Depends(get_period_close_service),
):
    return service.get_active_process(org_id, period_id)


@router.get(
    "/periods/{period_id}/processes", response_model=list[PeriodCloseProcessOut],
    dependencies=[Depends(require_permission(PERIOD_CLOSE_READ))],
)
def list_processes(
    period_id: str,
    org_id: str = Depends(get_current_org),
    service: PeriodCloseService = Depends(get_period_close_service),
):
    return service.list_processes(org_id, period_id)


@router.get(
    "/processes/{process_id}", response_model=PeriodCloseProcessOut,
    dependencies=[Depends(require_permission(PERIOD_CLOSE_READ))],
)
def get_process(
    process_id: str,
    org_id: str = Depends(get_current_org),
    service: PeriodCloseService = Depends(get_period_close_service),
):
    return service.get_process(org_id, process_id)


@router.post(
    "/processes/{process_id}/recheck", response_model=PeriodCloseProcessOut,
    dependencies=[Depends(require_permission(PERIOD_CLOSE_REQUEST))],
)
def recheck_controls(
    process_id: str,
    body: RequestCloseRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: PeriodCloseService = Depends(get_period_close_service),
):
    """A maker-side action: re-run controls after remediating a
    CONTROLS_FAILED process (e.g. posting the drafts it flagged)."""
    return service.recheck_controls(org_id, process_id, actor=actor, required_evidence_refs=body.required_evidence_refs)


@router.post(
    "/processes/{process_id}/review", response_model=PeriodCloseProcessOut,
    dependencies=[Depends(require_permission(PERIOD_CLOSE_REVIEW))],
)
def review_close(
    process_id: str,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: PeriodCloseService = Depends(get_period_close_service),
):
    return service.review_close(org_id, process_id, actor=actor)


@router.post(
    "/processes/{process_id}/approve", response_model=PeriodCloseProcessOut,
    dependencies=[Depends(require_permission(PERIOD_CLOSE_APPROVE))],
)
def approve_close(
    process_id: str,
    body: ApproveCloseRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: PeriodCloseService = Depends(get_period_close_service),
):
    """The only endpoint that actually locks the accounting period —
    and even this only by calling AccountingEngine.lock_period()
    unchanged. Never accepts a client-supplied status."""
    return service.approve_close(org_id, process_id, actor=actor, reason=body.reason)


@router.post(
    "/processes/{process_id}/reject", response_model=PeriodCloseProcessOut,
    dependencies=[Depends(require_permission(PERIOD_CLOSE_APPROVE))],
)
def reject_close(
    process_id: str,
    body: RejectCloseRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: PeriodCloseService = Depends(get_period_close_service),
):
    return service.reject_close(org_id, process_id, actor=actor, reason=body.reason)
