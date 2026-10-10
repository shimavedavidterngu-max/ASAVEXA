"""A small, fully controlled client organisation ("Bakery") built from the real domain dataclasses, so every pilot figure can be checked by hand."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from asavexa.accounting.domain.enums import AccountType, JournalStatus, PeriodStatus
from asavexa.accounting.domain.models import Account, AccountingPeriod, Journal, JournalLine
from asavexa.audit.models import AuditEvent
from asavexa.compliance.domain.enums import ControlSeverity, FindingStatus
from asavexa.compliance.domain.models import Finding
from asavexa.evidence.domain.enums import EvidenceStatus, EvidenceType
from asavexa.evidence.domain.models import EvidenceRecord
from asavexa.identity.domain.enums import MembershipStatus, Role
from asavexa.identity.domain.models import Membership
from asavexa.passport.builder import PassportInputs
from asavexa.reconciliation.domain.enums import BankTransactionStatus, ReconciliationStatus
from asavexa.reconciliation.domain.models import BankTransaction, Reconciliation

UTC = timezone.utc
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
ORG = "bakery-org"
ACC1, ACC2, READER, OWNER = "acc-1", "acc-2", "reader-1", "owner-1"
FIRM_USERS = {ACC1, ACC2, READER}


def d(day, hour=9):
    return datetime(2026, 10, day, hour, 0, tzinfo=UTC)


def journal(i, status, created, posted_after_h=None):
    jid = f"j{i}"
    j = Journal(id=jid, org_id=ORG, period_id="p-oct", journal_number=f"J-{i:03d}", date=date(2026, 10, 5), description=f"Sale {i}", currency="NGN", created_by=ACC1, created_at=created,
                lines=[JournalLine(f"{jid}-1", jid, 1, "cash", Decimal("1000.00"), Decimal("0.00")), JournalLine(f"{jid}-2", jid, 2, "sales", Decimal("0.00"), Decimal("1000.00"))],
                status=status)
    if posted_after_h is not None:
        j.posted_at, j.posted_by = created + timedelta(hours=posted_after_h), "approver-1"
    return j


def ev(i, status, journal_id=None, uploaded=None):
    return EvidenceRecord(id=f"e{i}", org_id=ORG, type=EvidenceType.INVOICE, status=status, file_hash=f"{i:064x}", original_filename=f"inv{i}.pdf", content_type="application/pdf",
                          size_bytes=10, uploaded_by=ACC1, uploaded_at=uploaded or d(3), linked_journal_id=journal_id)


def bank(i, status):
    return BankTransaction(id=f"b{i}", org_id=ORG, reconciliation_id="r1", bank_account_id="cash", import_batch_id="batch", dedup_hash=f"h{i}", transaction_date=date(2026, 10, 4),
                           description=f"Deposit {i}", debit_amount=Decimal("1000.00"), credit_amount=Decimal("0.00"), currency="NGN", created_by=ACC1, created_at=d(4), status=status)


def event(i, action, actor=ACC1, day=10, entity_type="Journal"):
    return AuditEvent(id=f"ev{i}", entity_type=entity_type, entity_id=f"x{i}", action=action, actor=actor, timestamp=d(day, 10), org_id=ORG)


def bakery_inputs() -> PassportInputs:
    hours = [2, 4, 6, 8, 10, 12, 24, 48, 72, 100]
    journals = [journal(i + 1, JournalStatus.POSTED, d(5), h) for i, h in enumerate(hours)]
    journals.append(journal(11, JournalStatus.REVERSED, d(6), 1))
    journals += [journal(12, JournalStatus.DRAFT, d(20)), journal(13, JournalStatus.DRAFT, d(30))]
    evidence = [ev(i, EvidenceStatus.VERIFIED, f"j{i}") for i in range(1, 7)] + [ev(7, EvidenceStatus.UPLOADED, "j7"), ev(8, EvidenceStatus.REJECTED, "j8")]
    txs = [bank(i, BankTransactionStatus.RECONCILED) for i in range(1, 10)] + [bank(10, BankTransactionStatus.UNMATCHED), bank(11, BankTransactionStatus.UNMATCHED), bank(12, BankTransactionStatus.REVIEW_REQUIRED)]
    rec = Reconciliation(id="r1", org_id=ORG, bank_account_id="cash", name="October", period_start=date(2026, 10, 1), period_end=date(2026, 10, 31), currency="NGN", created_by=ACC1,
                         created_at=d(4), status=ReconciliationStatus.RECONCILED, approved_by="approver-1", approved_at=d(12))
    accounts = [Account(id=a, org_id=ORG, code=a, name=a.title(), type=t, currency="NGN", created_at=d(2)) for a, t in (("cash", AccountType.ASSET), ("sales", AccountType.REVENUE))]
    periods = [AccountingPeriod(id="p-oct", org_id=ORG, name="Oct", start_date=date(2026, 10, 1), end_date=date(2026, 10, 31), status=PeriodStatus.LOCKED)]
    members = [Membership(id=f"m{i}", org_id=ORG, user_id=u, role=r, status=MembershipStatus.ACTIVE, created_at=d(1), created_by=OWNER)
               for i, (u, r) in enumerate([(ACC1, Role.ACCOUNTANT), (ACC2, Role.ACCOUNTANT), (READER, Role.READ_ONLY), (OWNER, Role.OWNER)])]
    findings = [Finding(id="f1", org_id=ORG, control_id="c", execution_id="x", description="d", severity=ControlSeverity.HIGH, status=FindingStatus.OPEN, created_by=ACC1, created_at=d(9)),
                Finding(id="f2", org_id=ORG, control_id="c", execution_id="x", description="d", severity=ControlSeverity.LOW, status=FindingStatus.CLOSED, created_by=ACC1, created_at=d(9))]
    return PassportInputs(org_id=ORG, org_name="Bakery Ltd", accounts=accounts, periods=periods, journals=journals, evidence=evidence, reconciliations=[rec], bank_transactions=txs,
                          findings=findings, memberships=members)


def bakery_events() -> list:
    n = [0]
    def mk(action, count=1, actor=ACC1, day=10, entity_type="Journal"):
        out = []
        for _ in range(count):
            n[0] += 1; out.append(event(n[0], action, actor, day, entity_type))
        return out
    ev_ = []
    ev_ += mk("JOURNAL_DRAFTED", 40, day=12) + mk("EVIDENCE_UPLOADED", 10, day=13)
    ev_ += mk("JOURNAL_REVERSED") + mk("JOURNAL_DRAFT_DELETED") + mk("EVIDENCE_REJECTED")
    ev_ += mk("REPORT_GENERATED", 2, day=15, entity_type="TRIAL_BALANCE") + mk("REPORT_GENERATED", 1, day=16, entity_type="INCOME_STATEMENT") + mk("REPORT_GENERATION_FAILED", day=16)
    ev_ += mk("PASSPORT_GENERATED", 2, day=20) + mk("PASSPORT_SHARE_CREATED", day=21) + mk("PASSPORT_SHARE_VIEWED", 2, actor="lender-token", day=22)
    ev_ += mk("LOGIN_SUCCEEDED", 5) + mk("PILOT_CLIENT_ADDED") + mk("ORG_CONTEXT_SELECTED", 3)
    return ev_
