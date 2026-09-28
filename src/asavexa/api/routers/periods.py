from fastapi import APIRouter, Depends

from ...accounting.services.engine import AccountingEngine
from ...identity.domain.permissions import LEDGER_READ, PERIOD_MANAGE
from ..deps import get_accounting_engine, get_current_actor, get_current_org, require_permission
from ..schemas.periods import PeriodCreate, PeriodLockRequest, PeriodOut

router = APIRouter(prefix="/periods", tags=["Accounting Periods"])


@router.post(
    "", response_model=PeriodOut, status_code=201,
    dependencies=[Depends(require_permission(PERIOD_MANAGE))],
)
def open_period(
    body: PeriodCreate,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    engine: AccountingEngine = Depends(get_accounting_engine),
):
    return engine.open_period(org_id, body.name, body.start_date, body.end_date, actor)


@router.get("", response_model=list[PeriodOut], dependencies=[Depends(require_permission(LEDGER_READ))])
def list_periods(
    org_id: str = Depends(get_current_org),
    engine: AccountingEngine = Depends(get_accounting_engine),
):
    return engine.periods.list_for_org(org_id)


@router.post(
    "/{period_id}/lock", response_model=PeriodOut,
    dependencies=[Depends(require_permission(PERIOD_MANAGE))],
)
def lock_period(
    period_id: str,
    body: PeriodLockRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    engine: AccountingEngine = Depends(get_accounting_engine),
):
    return engine.lock_period(org_id, period_id, actor, body.reason)


@router.get("/{period_id}/trial-balance", dependencies=[Depends(require_permission(LEDGER_READ))])
def get_trial_balance(
    period_id: str,
    org_id: str = Depends(get_current_org),
    engine: AccountingEngine = Depends(get_accounting_engine),
):
    return engine.get_trial_balance(org_id, period_id)
