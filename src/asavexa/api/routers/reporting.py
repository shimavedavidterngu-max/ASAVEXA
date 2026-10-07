from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from ...identity.domain.permissions import REPORTING_READ
from ...reporting.services.service import ReportingService
from ..deps import get_current_actor, get_current_org, get_reporting_service, require_permission
from ..schemas.reporting import (
    BalanceSheetOut,
    GeneralLedgerOut,
    IncomeStatementOut,
    ReconciliationSummaryOut,
    TrialBalanceOut,
)

router = APIRouter(
    prefix="/reports", tags=["Financial Reporting"],
    dependencies=[Depends(require_permission(REPORTING_READ))],
)


@router.get("/trial-balance", response_model=TrialBalanceOut)
def get_trial_balance(
    period_id: str,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ReportingService = Depends(get_reporting_service),
):
    return service.get_trial_balance(org_id, period_id, actor=actor)


@router.get("/income-statement", response_model=IncomeStatementOut)
def get_income_statement(
    period_id: str,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ReportingService = Depends(get_reporting_service),
):
    return service.get_income_statement(org_id, period_id, actor=actor)


@router.get("/balance-sheet", response_model=BalanceSheetOut)
def get_balance_sheet(
    period_id: str,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ReportingService = Depends(get_reporting_service),
):
    return service.get_balance_sheet(org_id, period_id, actor=actor)


@router.get("/general-ledger", response_model=GeneralLedgerOut)
def get_general_ledger(
    period_id: Optional[str] = None,
    account_ids: Optional[List[str]] = Query(default=None),
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ReportingService = Depends(get_reporting_service),
):
    return service.get_general_ledger(org_id, actor=actor, period_id=period_id, account_ids=account_ids)


@router.get("/trace")
def trace_line(
    account_id: str,
    period_id: Optional[str] = None,
    org_id: str = Depends(get_current_org),
    service: ReportingService = Depends(get_reporting_service),
):
    """The 'Show Me the Number' endpoint: the exact posted ledger
    entries — with each entry's journal_id, evidence_ref, and
    transaction_ref — behind one account's balance."""
    return service.trace_line(org_id, account_id, period_id=period_id)


@router.get("/reconciliation-summary", response_model=ReconciliationSummaryOut)
def get_reconciliation_summary(
    bank_account_id: str,
    org_id: str = Depends(get_current_org),
    service: ReportingService = Depends(get_reporting_service),
):
    """Read-only control context — never affects any report figure."""
    return service.get_reconciliation_summary(org_id, bank_account_id)


@router.get("/evidence-completeness")
def get_evidence_completeness(
    account_id: str,
    period_id: Optional[str] = None,
    org_id: str = Depends(get_current_org),
    service: ReportingService = Depends(get_reporting_service),
):
    """Phase 1 'evidence completeness score': of the ledger entries
    behind this account's balance, what fraction have evidence
    attached (and verified)? Read-only control context — never
    affects any report figure."""
    return service.get_evidence_completeness(org_id, account_id, period_id=period_id)
