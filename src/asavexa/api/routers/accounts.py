from fastapi import APIRouter, Depends

from ...accounting.services.engine import AccountingEngine
from ...identity.domain.permissions import ACCOUNT_MANAGE, LEDGER_READ
from ..deps import get_accounting_engine, get_current_actor, get_current_org, require_permission
from ..schemas.accounts import AccountCreate, AccountOut

router = APIRouter(prefix="/accounts", tags=["Chart of Accounts"])


@router.post(
    "", response_model=AccountOut, status_code=201,
    dependencies=[Depends(require_permission(ACCOUNT_MANAGE))],
)
def create_account(
    body: AccountCreate,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    engine: AccountingEngine = Depends(get_accounting_engine),
):
    account = engine.create_account(
        org_id=org_id, code=body.code, name=body.name, type=body.type,
        actor=actor, currency=body.currency, parent_id=body.parent_id,
    )
    return account


@router.get("", response_model=list[AccountOut], dependencies=[Depends(require_permission(LEDGER_READ))])
def list_accounts(
    org_id: str = Depends(get_current_org),
    engine: AccountingEngine = Depends(get_accounting_engine),
):
    return engine.accounts.list_for_org(org_id)


@router.get("/{account_id}/ledger", dependencies=[Depends(require_permission(LEDGER_READ))])
def get_account_ledger(
    account_id: str,
    period_id: str | None = None,
    org_id: str = Depends(get_current_org),
    engine: AccountingEngine = Depends(get_accounting_engine),
):
    """
    The "Show Me the Number" endpoint for a single account: every posted
    line affecting it, in order, with a running balance and each line's
    evidence/transaction reference.
    """
    return engine.get_ledger(org_id, account_id, period_id=period_id)
