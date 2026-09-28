"""
Repository interfaces for the Accounting Engine.

The service layer (services/engine.py) depends only on these Protocols,
never on a concrete database technology. Two implementations exist in
this starter codebase:

  - sqlite_repository.py   — stdlib-only, used for local development and
                              the automated test suite in this sandbox.
  - ../../api/db/*.py       — SQLAlchemy/PostgreSQL adapter for production
                              (see src/asavexa/api/README in that folder).

Swapping storage technology should never require changing engine.py or
the domain rules — that separation is Blueprint Rule 19.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional, Protocol

from ..domain.models import Account, AccountingPeriod, Journal
from ...audit.repository import AuditRepository  # noqa: F401  (re-exported for callers)


class AccountRepository(Protocol):
    def create(self, account: Account) -> Account: ...
    def get(self, org_id: str, account_id: str) -> Optional[Account]: ...
    def get_by_code(self, org_id: str, code: str) -> Optional[Account]: ...
    def list_for_org(self, org_id: str) -> List[Account]: ...


class PeriodRepository(Protocol):
    def create(self, period: AccountingPeriod) -> AccountingPeriod: ...
    def get(self, org_id: str, period_id: str) -> Optional[AccountingPeriod]: ...
    def get_for_date(self, org_id: str, on_date: date) -> Optional[AccountingPeriod]: ...
    def update(self, period: AccountingPeriod) -> AccountingPeriod: ...
    def list_for_org(self, org_id: str) -> List[AccountingPeriod]: ...


class JournalRepository(Protocol):
    def create(self, journal: Journal) -> Journal: ...
    def get(self, org_id: str, journal_id: str) -> Optional[Journal]: ...
    def update(self, journal: Journal) -> Journal: ...
    def list_for_org(
        self,
        org_id: str,
        period_id: Optional[str] = None,
        account_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Journal]: ...
    def next_journal_number(self, org_id: str) -> str: ...
