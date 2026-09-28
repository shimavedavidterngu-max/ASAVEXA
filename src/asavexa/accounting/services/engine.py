"""
AccountingEngine — the public service facade for the Asavexa Accounting
Engine module.

This is the ONE place every other module (Evidence, Reconciliation,
Reporting, AI, Financial Passport) should call into for anything
ledger-related. Nothing outside this file should construct a Journal and
write it directly to storage — that would bypass the invariants
(balance, immutability, period locks, audit logging) this class exists
to guarantee.

Dependency injection: the engine is constructed with repository
implementations satisfying the Protocols in repository/interfaces.py.
It does not know or care whether those are backed by SQLite (tests,
local dev) or PostgreSQL via SQLAlemy (production — see
src/asavexa/api/db/).
"""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from ..domain import rules
from ..domain.enums import AccountType, AuditAction, JournalStatus, PeriodStatus
from ..domain.errors import (
    AccountNotFoundError,
    InactiveAccountError,
    JournalNotFoundError,
    PeriodNotFoundError,
)
from ..domain.models import (
    Account,
    AccountingPeriod,
    Journal,
    JournalLine,
)
from ..repository.interfaces import (
    AccountRepository,
    AuditRepository,
    JournalRepository,
    PeriodRepository,
)
from ...audit.models import AuditEvent


def _new_id() -> str:
    return str(uuid.uuid4())


class LineInput:
    """Plain input shape for a journal line, used when creating a journal.
    Kept separate from the JournalLine domain model because at creation
    time there is no id/journal_id yet."""

    __slots__ = ("account_id", "debit_amount", "credit_amount", "description")

    def __init__(
        self,
        account_id: str,
        debit_amount: Decimal = Decimal("0.00"),
        credit_amount: Decimal = Decimal("0.00"),
        description: str = "",
    ):
        self.account_id = account_id
        self.debit_amount = debit_amount
        self.credit_amount = credit_amount
        self.description = description


class AccountingEngine:
    def __init__(
        self,
        accounts: AccountRepository,
        periods: PeriodRepository,
        journals: JournalRepository,
        audit: AuditRepository,
    ):
        self.accounts = accounts
        self.periods = periods
        self.journals = journals
        self.audit = audit

    # ------------------------------------------------------------------
    # Chart of accounts
    # ------------------------------------------------------------------
    def create_account(
        self,
        org_id: str,
        code: str,
        name: str,
        type: AccountType,
        actor: str,
        currency: str = "USD",
        parent_id: Optional[str] = None,
    ) -> Account:
        account = Account(
            id=_new_id(), org_id=org_id, code=code, name=name, type=type,
            currency=currency, parent_id=parent_id, is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        self.accounts.create(account)
        self._log(org_id, "Account", account.id, AuditAction.ACCOUNT_CREATED,
                   actor, new_value={"code": code, "name": name, "type": type.value})
        return account

    def _get_active_account(self, org_id: str, account_id: str) -> Account:
        account = self.accounts.get(org_id, account_id)
        if account is None:
            raise AccountNotFoundError(f"Account {account_id} not found.")
        if not account.is_active:
            raise InactiveAccountError(f"Account {account.code} is inactive.")
        return account

    # ------------------------------------------------------------------
    # Periods
    # ------------------------------------------------------------------
    def open_period(
        self, org_id: str, name: str, start_date: date, end_date: date, actor: str
    ) -> AccountingPeriod:
        period = AccountingPeriod(
            id=_new_id(), org_id=org_id, name=name,
            start_date=start_date, end_date=end_date, status=PeriodStatus.OPEN,
        )
        self.periods.create(period)
        self._log(org_id, "AccountingPeriod", period.id, AuditAction.PERIOD_OPENED,
                   actor, new_value={"name": name, "start": str(start_date), "end": str(end_date)})
        return period

    def lock_period(self, org_id: str, period_id: str, actor: str, reason: str) -> AccountingPeriod:
        period = self.periods.get(org_id, period_id)
        if period is None:
            raise PeriodNotFoundError(f"Period {period_id} not found.")
        previous_status = period.status.value
        period.status = PeriodStatus.LOCKED
        period.locked_at = datetime.now(timezone.utc)
        period.locked_by = actor
        self.periods.update(period)
        self._log(org_id, "AccountingPeriod", period.id, AuditAction.PERIOD_LOCKED,
                   actor, previous_value={"status": previous_status},
                   new_value={"status": period.status.value}, reason=reason)
        return period

    def _get_period_for_date(self, org_id: str, on_date: date) -> AccountingPeriod:
        period = self.periods.get_for_date(org_id, on_date)
        if period is None:
            raise PeriodNotFoundError(
                f"No accounting period is configured covering {on_date}."
            )
        return period

    # ------------------------------------------------------------------
    # Journals
    # ------------------------------------------------------------------
    def create_draft_journal(
        self,
        org_id: str,
        date_: date,
        description: str,
        currency: str,
        lines: List[LineInput],
        created_by: str,
        transaction_ref: Optional[str] = None,
        evidence_ref: Optional[str] = None,
    ) -> Journal:
        """
        Create a DRAFT journal. Does not post it — posting is a separate,
        explicit step (create_draft_journal -> post_journal) so that
        approval workflows can sit in between (Blueprint: maker-checker /
        segregation of duties).
        """
        period = self._get_period_for_date(org_id, date_)
        rules.assert_period_open_for_posting(period)

        # Verify every referenced account exists and is active before we
        # even construct the journal lines.
        for line in lines:
            self._get_active_account(org_id, line.account_id)

        domain_lines = [
            JournalLine(
                id=_new_id(), journal_id="", line_no=i + 1,
                account_id=l.account_id, debit_amount=l.debit_amount,
                credit_amount=l.credit_amount, description=l.description,
            )
            for i, l in enumerate(lines)
        ]
        rules.validate_new_journal(domain_lines, currency)

        journal = Journal(
            id=_new_id(), org_id=org_id, period_id=period.id,
            journal_number=self.journals.next_journal_number(org_id),
            date=date_, description=description, currency=currency,
            created_by=created_by, created_at=datetime.now(timezone.utc),
            lines=domain_lines, status=JournalStatus.DRAFT,
            transaction_ref=transaction_ref, evidence_ref=evidence_ref,
        )
        for line in domain_lines:
            line.journal_id = journal.id
        self.journals.create(journal)
        self._log(
            org_id, "Journal", journal.id, AuditAction.JOURNAL_DRAFTED, created_by,
            new_value={
                "journal_number": journal.journal_number,
                "description": description,
                "lines": [
                    {"account_id": l.account_id, "debit": str(l.debit_amount),
                     "credit": str(l.credit_amount)}
                    for l in domain_lines
                ],
            },
        )
        return journal

    def _get_journal(self, org_id: str, journal_id: str) -> Journal:
        journal = self.journals.get(org_id, journal_id)
        if journal is None:
            raise JournalNotFoundError(f"Journal {journal_id} not found.")
        return journal

    def post_journal(self, org_id: str, journal_id: str, actor: str) -> Journal:
        """
        Move a DRAFT journal to POSTED. Re-validates balance and period
        status at post time (defense in depth — the world may have
        changed since the draft was created, e.g. the period was locked
        in the interim).
        """
        journal = self._get_journal(org_id, journal_id)
        rules.assert_journal_postable(journal)
        rules.assert_balanced(journal.lines)
        period = self.periods.get(org_id, journal.period_id)
        if period is None:
            raise PeriodNotFoundError(f"Period {journal.period_id} not found.")
        rules.assert_period_open_for_posting(period)

        journal.status = JournalStatus.POSTED
        journal.posted_by = actor
        journal.posted_at = datetime.now(timezone.utc)
        self.journals.update(journal)
        self._log(org_id, "Journal", journal.id, AuditAction.JOURNAL_POSTED, actor,
                   new_value={"status": journal.status.value})
        return journal

    def update_draft_journal_description(
        self, org_id: str, journal_id: str, new_description: str, actor: str
    ) -> Journal:
        """Only a DRAFT journal's metadata may change. Lines on a DRAFT
        journal should be edited by deleting and recreating the draft in
        this starter engine, to keep the audit story simple — a richer
        line-level diff can be added once real usage patterns are known."""
        journal = self._get_journal(org_id, journal_id)
        rules.assert_journal_editable(journal)
        previous = journal.description
        journal.description = new_description
        self.journals.update(journal)
        self._log(org_id, "Journal", journal.id, AuditAction.JOURNAL_DRAFT_UPDATED,
                   actor, previous_value={"description": previous},
                   new_value={"description": new_description})
        return journal

    def reverse_journal(
        self,
        org_id: str,
        journal_id: str,
        actor: str,
        reason: str,
        reversal_date: Optional[date] = None,
    ) -> Journal:
        """
        Rule: "corrections use reversals ... rather than silent edits."
        Creates a new, fully posted journal with every line's debit and
        credit swapped, linked both ways to the original. The original
        journal's status becomes REVERSED — it is never deleted, and its
        lines still count in the ledger/trial balance (see get_ledger),
        so its history remains fully reconstructable.

        `reversal_date` defaults to today, but callers may specify a
        different date (e.g. backdating a correction into the period the
        error was found in) — it must still fall inside an OPEN period,
        just like any other posting.
        """
        original = self._get_journal(org_id, journal_id)
        rules.assert_journal_reversible(original)

        reversal_date = reversal_date or date.today()
        period = self._get_period_for_date(org_id, reversal_date)
        rules.assert_period_open_for_posting(period)

        reversal_lines = [
            LineInput(
                account_id=l.account_id,
                debit_amount=l.credit_amount,   # swapped
                credit_amount=l.debit_amount,   # swapped
                description=f"Reversal of {original.journal_number} line {l.line_no}: {reason}",
            )
            for l in original.lines
        ]

        reversal = self.create_draft_journal(
            org_id=org_id, date_=reversal_date,
            description=f"Reversal of {original.journal_number}: {reason}",
            currency=original.currency, lines=reversal_lines, created_by=actor,
            transaction_ref=original.transaction_ref,
            evidence_ref=original.evidence_ref,
        )
        reversal.reversal_of_journal_id = original.id
        self.journals.update(reversal)
        reversal = self.post_journal(org_id, reversal.id, actor)

        original.status = JournalStatus.REVERSED
        original.reversed_by_journal_id = reversal.id
        self.journals.update(original)
        self._log(
            org_id, "Journal", original.id, AuditAction.JOURNAL_REVERSED, actor,
            previous_value={"status": "POSTED"}, new_value={"status": "REVERSED"},
            reason=reason, related_record_id=reversal.id,
        )
        return reversal

    # ------------------------------------------------------------------
    # Read models — ledger, trial balance, Proof-to-Report entry point
    # ------------------------------------------------------------------
    def get_ledger(
        self, org_id: str, account_id: str, period_id: Optional[str] = None
    ) -> List[dict]:
        """
        Every line ever posted to `account_id`, in date order, with a
        running balance. DRAFT journals never contribute (they are not
        yet part of the ledger). A REVERSED journal's original lines
        **remain included** — immutability (Rule 6) means a posted entry
        is never erased from history, even after it is reversed; the
        offsetting reversal journal is a separate, later POSTED entry
        that nets it out. Excluding reversed entries from the ledger
        would falsify the running balance and break the audit trail.
        """
        journals = [
            j for j in self.journals.list_for_org(
                org_id, period_id=period_id, account_id=account_id
            )
            if j.status != JournalStatus.DRAFT
        ]
        entries: list[dict] = []
        running = Decimal("0.00")
        for journal in journals:
            for line in journal.lines:
                if line.account_id != account_id:
                    continue
                running += line.debit_amount - line.credit_amount
                entries.append({
                    "journal_id": journal.id,
                    "journal_number": journal.journal_number,
                    "date": journal.date,
                    "description": line.description or journal.description,
                    "debit": line.debit_amount,
                    "credit": line.credit_amount,
                    "running_balance": running,
                    "evidence_ref": journal.evidence_ref,
                    "transaction_ref": journal.transaction_ref,
                })
        return entries

    def get_trial_balance(self, org_id: str, period_id: str) -> dict:
        """
        Sum of debits and credits per account for a period, from every
        journal that was ever posted (POSTED and REVERSED — see the note
        in get_ledger on why reversed entries stay in), plus the overall
        balance check the blueprint requires before accepting a completed
        period: Total Debits == Total Credits.
        """
        journals = [
            j for j in self.journals.list_for_org(org_id, period_id=period_id)
            if j.status != JournalStatus.DRAFT
        ]
        by_account: dict[str, dict] = {}
        total_debits = Decimal("0.00")
        total_credits = Decimal("0.00")
        for journal in journals:
            for line in journal.lines:
                bucket = by_account.setdefault(
                    line.account_id, {"debit_total": Decimal("0.00"), "credit_total": Decimal("0.00")}
                )
                bucket["debit_total"] += line.debit_amount
                bucket["credit_total"] += line.credit_amount
                total_debits += line.debit_amount
                total_credits += line.credit_amount
        return {
            "period_id": period_id,
            "accounts": by_account,
            "total_debits": total_debits,
            "total_credits": total_credits,
            "is_balanced": total_debits.quantize(Decimal("0.01"))
            == total_credits.quantize(Decimal("0.01")),
        }

    def get_audit_trail(self, org_id: str, entity_type: str, entity_id: str) -> List[AuditEvent]:
        return self.audit.list_for_entity(entity_type, entity_id, org_id=org_id)

    # ------------------------------------------------------------------
    def _log(
        self,
        org_id: str,
        entity_type: str,
        entity_id: str,
        action: AuditAction,
        actor: str,
        previous_value: Optional[dict] = None,
        new_value: Optional[dict] = None,
        reason: Optional[str] = None,
        related_record_id: Optional[str] = None,
    ) -> None:
        self.audit.record(
            AuditEvent(
                id=_new_id(), org_id=org_id, entity_type=entity_type,
                entity_id=entity_id, action=action.value, actor=actor,
                timestamp=datetime.now(timezone.utc), previous_value=previous_value,
                new_value=new_value, reason=reason, related_record_id=related_record_id,
            )
        )
