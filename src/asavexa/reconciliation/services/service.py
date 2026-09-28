"""
ReconciliationService — the public service facade for Reconciliation.

Reads the Accounting Engine's ledger through its existing, documented
public interface (`AccountingEngine.accounts`, `.journals`,
`.get_ledger`) and never writes to it — no journal is ever created,
posted, or reversed from here. The Accounting Engine remains the sole
authoritative accounting record; this module only proves correspondence
with it.

Deliberately has NO dependency on EvidenceVault or IdentityService:
- Evidence linkage is a single opaque id (`Reconciliation.evidence_ref`)
  set by `attach_evidence`, exactly mirroring how `Journal.evidence_ref`
  is set by the *caller* (API layer / test), not by AccountingEngine
  calling into EvidenceVault itself. See evidence/README.md — that
  precedent is followed here on purpose.
- Permission checks are not performed here at all. Every method takes a
  plain `actor: str` and trusts the caller (the API layer's
  `require_permission(...)`) to have already authorized the action —
  exactly like AccountingEngine and EvidenceVault. Reconciliation must
  not become a second place permission logic lives.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from ...accounting.services.engine import AccountingEngine
from ...accounting.domain.errors import JournalNotFoundError as AccountingJournalNotFoundError
from ...audit.models import AuditEvent
from ...audit.repository import AuditRepository
from ..domain import matching, rules
from ..domain.enums import AuditAction, BankTransactionStatus, MatchOutcome, ReconciliationStatus
from ..domain.errors import (
    BankAccountNotFoundError,
    BankTransactionNotFoundError,
    DuplicateExternalTransactionError,
    EmptyReconciliationError,
    InvalidReconciliationStateError,
    JournalAlreadyMatchedError,
    ReconciliationNotFoundError,
    UnresolvedTransactionsError,
)
from ..domain.models import BankTransaction, BankTransactionInput, Reconciliation
from ..repository.interfaces import BankTransactionRepository, ReconciliationRepository

# A journal counts as "already claimed" by another transaction once
# that transaction's match has been accepted at all — including simply
# MATCHED, not only APPROVED/RECONCILED. Two live proposals pointing at
# the same journal would both look "matched" while only one can really
# be true; the second is a data problem to surface, not to allow.
_CLAIMED_STATUSES = frozenset({
    BankTransactionStatus.MATCHED, BankTransactionStatus.APPROVED, BankTransactionStatus.RECONCILED,
})


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ReconciliationService:
    def __init__(
        self,
        reconciliations: ReconciliationRepository,
        transactions: BankTransactionRepository,
        audit: AuditRepository,
        accounting: AccountingEngine,
    ):
        self.reconciliations = reconciliations
        self.transactions = transactions
        self.audit = audit
        self.accounting = accounting

    # ------------------------------------------------------------------
    # Reconciliation (batch) lifecycle
    # ------------------------------------------------------------------
    def create_reconciliation(
        self,
        org_id: str,
        bank_account_id: str,
        name: str,
        period_start: date,
        period_end: date,
        actor: str,
        currency: str = "USD",
        supersedes_reconciliation_id: Optional[str] = None,
    ) -> Reconciliation:
        account = self.accounting.accounts.get(org_id, bank_account_id)
        if account is None:
            raise BankAccountNotFoundError(
                f"Accounting account {bank_account_id} not found in organisation {org_id}."
            )
        reconciliation = Reconciliation(
            id=_new_id(), org_id=org_id, bank_account_id=bank_account_id, name=name,
            period_start=period_start, period_end=period_end, currency=currency,
            created_by=actor, created_at=_now(),
            supersedes_reconciliation_id=supersedes_reconciliation_id,
        )
        self.reconciliations.create(reconciliation)
        self._log(
            org_id, AuditAction.RECONCILIATION_CREATED, actor, "Reconciliation", reconciliation.id,
            new_value={
                "bank_account_id": bank_account_id, "name": name,
                "period_start": str(period_start), "period_end": str(period_end),
            },
        )
        return reconciliation

    def _get_reconciliation(self, org_id: str, reconciliation_id: str) -> Reconciliation:
        reconciliation = self.reconciliations.get(org_id, reconciliation_id)
        if reconciliation is None:
            raise ReconciliationNotFoundError(f"Reconciliation {reconciliation_id} not found.")
        return reconciliation

    def get_reconciliation(self, org_id: str, reconciliation_id: str) -> Reconciliation:
        return self._get_reconciliation(org_id, reconciliation_id)

    def list_reconciliations(self, org_id: str, bank_account_id: Optional[str] = None) -> List[Reconciliation]:
        return self.reconciliations.list_for_org(org_id, bank_account_id=bank_account_id)

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------
    def import_transactions(
        self,
        org_id: str,
        reconciliation_id: str,
        rows: List[BankTransactionInput],
        actor: str,
        import_source: str,
        date_tolerance_days: int = matching.DEFAULT_DATE_TOLERANCE_DAYS,
    ) -> List[BankTransaction]:
        """
        Imports every row into `reconciliation_id` (which must be
        DRAFT), then immediately runs deterministic matching on each new
        transaction. Validates every row's duplicate status *before*
        creating any of them — a partially-applied import would leave
        an unclear audit story, so this either imports the whole batch
        or none of it.
        """
        reconciliation = self._get_reconciliation(org_id, reconciliation_id)
        if reconciliation.status != ReconciliationStatus.DRAFT:
            raise InvalidReconciliationStateError(
                f"Reconciliation {reconciliation_id} is {reconciliation.status.value}; "
                f"transactions can only be imported into a DRAFT reconciliation."
            )

        bank_account_id = reconciliation.bank_account_id
        import_batch_id = _new_id()

        # Pass 1: validate every row is not a duplicate before writing anything.
        dedup_hashes = []
        for row in rows:
            dedup_hash = matching.compute_dedup_hash(
                org_id, bank_account_id, row.external_ref, row.transaction_date,
                row.debit_amount, row.credit_amount, row.description,
            )
            existing = self.transactions.get_by_dedup_hash(org_id, bank_account_id, dedup_hash)
            if existing is not None:
                self._log(
                    org_id, AuditAction.DUPLICATE_IMPORT_REJECTED, actor, "BankTransaction", existing.id,
                    reason=f"Duplicate of existing transaction {existing.id} (hash {dedup_hash[:12]}…).",
                )
                raise DuplicateExternalTransactionError(
                    f"Row dated {row.transaction_date} ({row.description!r}) duplicates "
                    f"existing transaction {existing.id}. No rows from this import were created."
                )
            dedup_hashes.append(dedup_hash)

        # Pass 2: create, then match, each row.
        created: List[BankTransaction] = []
        for row, dedup_hash in zip(rows, dedup_hashes):
            transaction = BankTransaction(
                id=_new_id(), org_id=org_id, reconciliation_id=reconciliation_id,
                bank_account_id=bank_account_id, import_batch_id=import_batch_id,
                dedup_hash=dedup_hash, transaction_date=row.transaction_date,
                value_date=row.value_date, description=row.description,
                debit_amount=row.debit_amount, credit_amount=row.credit_amount,
                currency=row.currency, external_ref=row.external_ref,
                created_by=actor, created_at=_now(),
            )
            self.transactions.create(transaction)
            self._log(
                org_id, AuditAction.TRANSACTION_IMPORTED, actor, "BankTransaction", transaction.id,
                new_value={
                    "bank_account_id": bank_account_id, "date": str(row.transaction_date),
                    "debit": str(row.debit_amount), "credit": str(row.credit_amount),
                    "external_ref": row.external_ref, "import_batch_id": import_batch_id,
                },
            )
            transaction = self._run_matching(org_id, transaction, actor, date_tolerance_days)
            created.append(transaction)
        return created

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------
    def _already_claimed_journal_ids(self, org_id: str, bank_account_id: str) -> set[str]:
        existing = self.transactions.list_for_account(org_id, bank_account_id)
        return {
            t.matched_journal_id for t in existing
            if t.matched_journal_id and t.status in _CLAIMED_STATUSES
        }

    def _record_decision(self, transaction: BankTransaction, actor: str, note: str) -> None:
        transaction.match_history.append({
            "at": _now().isoformat(), "by": actor,
            "status": transaction.status.value,
            "matched_journal_id": transaction.matched_journal_id,
            "note": note,
        })

    def _run_matching(
        self, org_id: str, transaction: BankTransaction, actor: str,
        date_tolerance_days: int = matching.DEFAULT_DATE_TOLERANCE_DAYS,
    ) -> BankTransaction:
        ledger_entries = self.accounting.get_ledger(org_id, transaction.bank_account_id)
        exclude = self._already_claimed_journal_ids(org_id, transaction.bank_account_id)
        candidates = matching.find_candidates(transaction, ledger_entries, exclude, date_tolerance_days)
        decision = matching.decide_match(transaction, candidates)

        previous_status = transaction.status.value
        if decision.outcome == MatchOutcome.UNIQUE_CANDIDATE:
            new_status = BankTransactionStatus.MATCHED
            transaction.matched_journal_id = decision.matched_journal_id
        elif decision.outcome == MatchOutcome.AMBIGUOUS:
            new_status = BankTransactionStatus.REVIEW_REQUIRED
        else:
            new_status = BankTransactionStatus.UNMATCHED

        rules.assert_transaction_transition_allowed(transaction.status, new_status)
        transaction.status = new_status
        transaction.match_reason = decision.reason
        transaction.match_rule = decision.match_rule
        self._record_decision(transaction, actor, decision.reason)
        self.transactions.update(transaction)

        self._log(
            org_id, AuditAction.CANDIDATE_MATCH_GENERATED, actor, "BankTransaction", transaction.id,
            previous_value={"status": previous_status}, new_value={"status": new_status.value},
            reason=decision.reason,
        )
        if decision.outcome == MatchOutcome.UNIQUE_CANDIDATE:
            self._log(org_id, AuditAction.MATCH_ACCEPTED, actor, "BankTransaction", transaction.id,
                       reason=decision.reason, related_record_id=transaction.matched_journal_id)
        else:
            self._log(org_id, AuditAction.EXCEPTION_CREATED, actor, "BankTransaction", transaction.id,
                       reason=decision.reason)
        return transaction

    def _get_transaction(self, org_id: str, transaction_id: str) -> BankTransaction:
        transaction = self.transactions.get(org_id, transaction_id)
        if transaction is None:
            raise BankTransactionNotFoundError(f"Bank transaction {transaction_id} not found.")
        return transaction

    def get_transaction(self, org_id: str, transaction_id: str) -> BankTransaction:
        return self._get_transaction(org_id, transaction_id)

    def list_transactions(self, org_id: str, reconciliation_id: str) -> List[BankTransaction]:
        return self.transactions.list_for_reconciliation(org_id, reconciliation_id)

    def manual_match(
        self, org_id: str, transaction_id: str, journal_id: str, actor: str, note: Optional[str] = None,
    ) -> BankTransaction:
        """
        A human override — used when deterministic matching left a
        transaction REVIEW_REQUIRED or UNMATCHED (or to correct a
        rejected match). Still records exactly why, and still refuses
        to double-claim a journal another live match already points to.
        """
        transaction = self._get_transaction(org_id, transaction_id)
        rules.assert_transaction_transition_allowed(transaction.status, BankTransactionStatus.MATCHED)

        journal = self.accounting.journals.get(org_id, journal_id)
        if journal is None:
            raise AccountingJournalNotFoundError(f"Journal {journal_id} not found.")

        claimed = self._already_claimed_journal_ids(org_id, transaction.bank_account_id)
        if journal_id in claimed and transaction.matched_journal_id != journal_id:
            raise JournalAlreadyMatchedError(
                f"Journal {journal_id} is already matched to another transaction."
            )

        journal_debit = sum((l.debit_amount for l in journal.lines if l.account_id == transaction.bank_account_id), Decimal("0.00"))
        journal_credit = sum((l.credit_amount for l in journal.lines if l.account_id == transaction.bank_account_id), Decimal("0.00"))
        amounts_match = (
            journal_debit == transaction.debit_amount and journal_credit == transaction.credit_amount
        )
        reason = (
            f"Manual match by {actor} to journal {journal.journal_number}"
            + (f": {note}" if note else "")
            + (
                "" if amounts_match else
                f" — AMOUNT MISMATCH: bank shows debit={transaction.debit_amount}/"
                f"credit={transaction.credit_amount}, ledger shows debit={journal_debit}/"
                f"credit={journal_credit}. Recorded as an explicit human override, not "
                f"silently reconciled as equal."
            )
        )

        previous_status = transaction.status.value
        transaction.status = BankTransactionStatus.MATCHED
        transaction.matched_journal_id = journal_id
        transaction.match_reason = reason
        transaction.match_rule = matching.MATCH_RULE_MANUAL_OVERRIDE
        self._record_decision(transaction, actor, reason)
        self.transactions.update(transaction)
        self._log(
            org_id, AuditAction.MANUAL_MATCH_PERFORMED, actor, "BankTransaction", transaction.id,
            previous_value={"status": previous_status}, new_value={"status": "MATCHED"},
            reason=reason, related_record_id=journal_id,
        )
        return transaction

    def reject_match(self, org_id: str, transaction_id: str, actor: str, reason: str) -> BankTransaction:
        """A checker disagreeing with a MATCHED (or already-APPROVED)
        transaction moves it to REJECTED — never silently deleted or
        reset to IMPORTED, so the original proposal remains in
        match_history. REJECTED is not itself a dead end, but moving it
        onward to REVIEW_REQUIRED is a separate, explicit call
        (`request_review`) — one method here causes exactly one
        transition, so the audit trail says precisely what happened."""
        transaction = self._get_transaction(org_id, transaction_id)
        rules.assert_transaction_transition_allowed(transaction.status, BankTransactionStatus.REJECTED)
        previous_status = transaction.status.value
        transaction.status = BankTransactionStatus.REJECTED
        self._record_decision(transaction, actor, f"Rejected: {reason}")
        self.transactions.update(transaction)
        self._log(
            org_id, AuditAction.MATCH_REJECTED, actor, "BankTransaction", transaction.id,
            previous_value={"status": previous_status}, new_value={"status": "REJECTED"}, reason=reason,
        )
        return transaction

    def request_review(self, org_id: str, transaction_id: str, actor: str, reason: str) -> BankTransaction:
        transaction = self._get_transaction(org_id, transaction_id)
        rules.assert_transaction_transition_allowed(transaction.status, BankTransactionStatus.REVIEW_REQUIRED)
        previous_status = transaction.status.value
        transaction.status = BankTransactionStatus.REVIEW_REQUIRED
        transaction.matched_journal_id = None
        self._record_decision(transaction, actor, reason)
        self.transactions.update(transaction)
        self._log(
            org_id, AuditAction.EXCEPTION_CREATED, actor, "BankTransaction", transaction.id,
            previous_value={"status": previous_status}, new_value={"status": "REVIEW_REQUIRED"}, reason=reason,
        )
        return transaction

    def approve_transaction(self, org_id: str, transaction_id: str, actor: str) -> BankTransaction:
        """A checker individually blesses one transaction's match. Does
        NOT finalize anything by itself — see approve_reconciliation."""
        transaction = self._get_transaction(org_id, transaction_id)
        rules.assert_transaction_transition_allowed(transaction.status, BankTransactionStatus.APPROVED)
        previous_status = transaction.status.value
        transaction.status = BankTransactionStatus.APPROVED
        self._record_decision(transaction, actor, "Approved by checker.")
        self.transactions.update(transaction)
        self._log(
            org_id, AuditAction.TRANSACTION_APPROVED, actor, "BankTransaction", transaction.id,
            previous_value={"status": previous_status}, new_value={"status": "APPROVED"},
        )
        return transaction

    # ------------------------------------------------------------------
    # Reconciliation submit / approve / reject
    # ------------------------------------------------------------------
    def submit_reconciliation(self, org_id: str, reconciliation_id: str, actor: str) -> Reconciliation:
        reconciliation = self._get_reconciliation(org_id, reconciliation_id)
        rules.assert_reconciliation_transition_allowed(reconciliation.status, ReconciliationStatus.SUBMITTED)
        lines = self.transactions.list_for_reconciliation(org_id, reconciliation_id)
        if not lines:
            raise EmptyReconciliationError(
                f"Reconciliation {reconciliation_id} has no imported transactions to submit."
            )
        reconciliation.status = ReconciliationStatus.SUBMITTED
        reconciliation.submitted_by = actor
        reconciliation.submitted_at = _now()
        self.reconciliations.update(reconciliation)
        self._log(org_id, AuditAction.RECONCILIATION_SUBMITTED, actor, "Reconciliation", reconciliation.id)
        return reconciliation

    def approve_reconciliation(self, org_id: str, reconciliation_id: str, actor: str) -> Reconciliation:
        """
        Finalizes a SUBMITTED reconciliation: requires every one of its
        transactions to already be APPROVED (never auto-resolves a
        remaining exception to get there) and then bulk-transitions
        every one of them, plus the batch itself, to the terminal
        RECONCILED state.
        """
        reconciliation = self._get_reconciliation(org_id, reconciliation_id)
        rules.assert_reconciliation_transition_allowed(reconciliation.status, ReconciliationStatus.RECONCILED)

        lines = self.transactions.list_for_reconciliation(org_id, reconciliation_id)
        unresolved = [t for t in lines if t.status != BankTransactionStatus.APPROVED]
        if unresolved:
            raise UnresolvedTransactionsError(
                f"{len(unresolved)} transaction(s) in reconciliation {reconciliation_id} are not "
                f"APPROVED yet (statuses: "
                + ", ".join(sorted({t.status.value for t in unresolved}))
                + ") — every transaction must be approved before the reconciliation can be finalized."
            )

        for transaction in lines:
            rules.assert_transaction_transition_allowed(transaction.status, BankTransactionStatus.RECONCILED)
            transaction.status = BankTransactionStatus.RECONCILED
            self._record_decision(transaction, actor, "Finalized with reconciliation approval.")
            self.transactions.update(transaction)

        reconciliation.status = ReconciliationStatus.RECONCILED
        reconciliation.approved_by = actor
        reconciliation.approved_at = _now()
        self.reconciliations.update(reconciliation)
        self._log(org_id, AuditAction.RECONCILIATION_APPROVED, actor, "Reconciliation", reconciliation.id)
        self._log(
            org_id, AuditAction.RECONCILIATION_FINALIZED, actor, "Reconciliation", reconciliation.id,
            new_value={"transactions_finalized": len(lines)},
        )
        return reconciliation

    def reject_reconciliation(self, org_id: str, reconciliation_id: str, actor: str, reason: str) -> Reconciliation:
        """Terminal rejection — the transactions are left exactly as
        they are (not reset), and rework happens via a new
        Reconciliation with `supersedes_reconciliation_id` set, not by
        reopening this one."""
        reconciliation = self._get_reconciliation(org_id, reconciliation_id)
        rules.assert_reconciliation_transition_allowed(reconciliation.status, ReconciliationStatus.REJECTED)
        reconciliation.status = ReconciliationStatus.REJECTED
        reconciliation.rejected_by = actor
        reconciliation.rejected_at = _now()
        reconciliation.rejection_reason = reason
        self.reconciliations.update(reconciliation)
        self._log(
            org_id, AuditAction.RECONCILIATION_REJECTED, actor, "Reconciliation", reconciliation.id,
            reason=reason,
        )
        return reconciliation

    # ------------------------------------------------------------------
    # Evidence linkage (opaque id only — no EvidenceVault dependency)
    # ------------------------------------------------------------------
    def attach_evidence(self, org_id: str, reconciliation_id: str, evidence_id: str, actor: str) -> Reconciliation:
        reconciliation = self._get_reconciliation(org_id, reconciliation_id)
        if reconciliation.status in (ReconciliationStatus.RECONCILED, ReconciliationStatus.REJECTED):
            from ..domain.errors import InvalidReconciliationStateError
            raise InvalidReconciliationStateError(
                f"Reconciliation {reconciliation_id} is {reconciliation.status.value} and finalized — "
                f"evidence cannot be attached to it. Create a new reconciliation instead."
            )
        reconciliation.evidence_ref = evidence_id
        self.reconciliations.update(reconciliation)
        self._log(
            org_id, AuditAction.EVIDENCE_LINKED, actor, "Reconciliation", reconciliation.id,
            new_value={"evidence_ref": evidence_id},
        )
        return reconciliation

    # ------------------------------------------------------------------
    def _log(
        self,
        org_id: str,
        action: AuditAction,
        actor: str,
        entity_type: str,
        entity_id: str,
        previous_value: Optional[dict] = None,
        new_value: Optional[dict] = None,
        reason: Optional[str] = None,
        related_record_id: Optional[str] = None,
    ) -> None:
        self.audit.record(
            AuditEvent(
                id=_new_id(), org_id=org_id, entity_type=entity_type, entity_id=entity_id,
                action=action.value, actor=actor, timestamp=_now(),
                previous_value=previous_value, new_value=new_value, reason=reason,
                related_record_id=related_record_id,
            )
        )
