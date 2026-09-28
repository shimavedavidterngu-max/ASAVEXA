"""
Automated tests for the Evidence Vault.

Run with:  PYTHONPATH=src python3 -m unittest discover -s tests -v

Stdlib-only — no external dependencies required.
"""
import unittest

from asavexa.audit.sqlite_repository import SqliteAuditRepository, ensure_schema as ensure_audit_schema
from asavexa.evidence.domain.enums import EvidenceStatus, EvidenceType
from asavexa.evidence.domain.errors import DuplicateEvidenceError, EmptyFileError, InvalidEvidenceStateError
from asavexa.evidence.repository.sqlite_repository import SqliteEvidenceRepository, connect
from asavexa.evidence.services.vault import MISSING, EvidenceVault

ORG_A = "org-meridian"
ORG_B = "org-other-tenant"


def build_vault() -> EvidenceVault:
    conn = connect(":memory:")
    ensure_audit_schema(conn)
    return EvidenceVault(
        evidence=SqliteEvidenceRepository(conn),
        audit=SqliteAuditRepository(conn),
    )


class EvidenceVaultTestCase(unittest.TestCase):
    def setUp(self):
        self.vault = build_vault()

    def test_upload_creates_uploaded_record_with_correct_hash(self):
        content = b"this is a fake invoice PDF"
        record = self.vault.upload_evidence(
            ORG_A, EvidenceType.INVOICE, content, "invoice-101.pdf", "application/pdf",
            uploaded_by="dara", linked_journal_id="journal-1",
        )
        self.assertEqual(record.status, EvidenceStatus.UPLOADED)
        self.assertEqual(record.size_bytes, len(content))
        import hashlib
        self.assertEqual(record.file_hash, hashlib.sha256(content).hexdigest())

    def test_empty_content_is_rejected(self):
        with self.assertRaises(EmptyFileError):
            self.vault.upload_evidence(
                ORG_A, EvidenceType.INVOICE, b"", "empty.pdf", "application/pdf", uploaded_by="dara",
            )

    def test_duplicate_upload_is_rejected_by_default(self):
        content = b"identical content"
        self.vault.upload_evidence(ORG_A, EvidenceType.RECEIPT, content, "r1.pdf", "application/pdf", "dara")
        with self.assertRaises(DuplicateEvidenceError):
            self.vault.upload_evidence(ORG_A, EvidenceType.RECEIPT, content, "r2.pdf", "application/pdf", "dara")

    def test_duplicate_upload_allowed_when_explicitly_flagged(self):
        content = b"identical content again"
        first = self.vault.upload_evidence(ORG_A, EvidenceType.RECEIPT, content, "r1.pdf", "application/pdf", "dara")
        second = self.vault.upload_evidence(
            ORG_A, EvidenceType.RECEIPT, content, "r2.pdf", "application/pdf", "dara", allow_duplicate=True,
        )
        self.assertNotEqual(first.id, second.id)

    def test_same_hash_in_different_orgs_is_not_a_duplicate(self):
        content = b"shared template content"
        self.vault.upload_evidence(ORG_A, EvidenceType.CONTRACT, content, "c.pdf", "application/pdf", "dara")
        # Different tenant — must not collide with org A's duplicate check.
        record = self.vault.upload_evidence(ORG_B, EvidenceType.CONTRACT, content, "c.pdf", "application/pdf", "amara")
        self.assertEqual(record.org_id, ORG_B)

    # ------------------------------------------------------------------
    def test_verify_transitions_to_verified_with_verifier_recorded(self):
        record = self.vault.upload_evidence(
            ORG_A, EvidenceType.INVOICE, b"content-1", "i.pdf", "application/pdf", "dara"
        )
        verified = self.vault.verify_evidence(ORG_A, record.id, actor="controller", note="matches PO #4471")
        self.assertEqual(verified.status, EvidenceStatus.VERIFIED)
        self.assertEqual(verified.verified_by, "controller")
        self.assertIsNotNone(verified.verified_at)
        self.assertEqual(verified.verification_note, "matches PO #4471")

    def test_reject_records_reason(self):
        record = self.vault.upload_evidence(
            ORG_A, EvidenceType.INVOICE, b"content-2", "i2.pdf", "application/pdf", "dara"
        )
        rejected = self.vault.reject_evidence(ORG_A, record.id, actor="controller", reason="illegible scan")
        self.assertEqual(rejected.status, EvidenceStatus.REJECTED)
        self.assertEqual(rejected.rejection_reason, "illegible scan")

    def test_cannot_verify_an_already_rejected_record(self):
        record = self.vault.upload_evidence(
            ORG_A, EvidenceType.INVOICE, b"content-3", "i3.pdf", "application/pdf", "dara"
        )
        self.vault.reject_evidence(ORG_A, record.id, actor="controller", reason="fraudulent")
        with self.assertRaises(InvalidEvidenceStateError):
            self.vault.verify_evidence(ORG_A, record.id, actor="controller")

    def test_verified_evidence_can_later_be_marked_expired(self):
        record = self.vault.upload_evidence(
            ORG_A, EvidenceType.CONTRACT, b"content-4", "c4.pdf", "application/pdf", "dara"
        )
        self.vault.verify_evidence(ORG_A, record.id, actor="controller")
        expired = self.vault.set_status(ORG_A, record.id, EvidenceStatus.EXPIRED, actor="controller", note="contract lapsed")
        self.assertEqual(expired.status, EvidenceStatus.EXPIRED)

    # ------------------------------------------------------------------
    def test_status_for_reference_is_missing_when_nothing_linked(self):
        self.assertEqual(self.vault.get_status_for_reference(ORG_A, journal_id="journal-999"), MISSING)

    def test_status_for_reference_reflects_linked_record(self):
        record = self.vault.upload_evidence(
            ORG_A, EvidenceType.INVOICE, b"content-5", "i5.pdf", "application/pdf", "dara",
            linked_journal_id="journal-42",
        )
        self.assertEqual(
            self.vault.get_status_for_reference(ORG_A, journal_id="journal-42"),
            EvidenceStatus.UPLOADED.value,
        )
        self.vault.verify_evidence(ORG_A, record.id, actor="controller")
        self.assertEqual(
            self.vault.get_status_for_reference(ORG_A, journal_id="journal-42"),
            EvidenceStatus.VERIFIED.value,
        )

    def test_status_for_reference_falls_back_to_transaction_ref(self):
        self.vault.upload_evidence(
            ORG_A, EvidenceType.RECEIPT, b"content-6", "r6.pdf", "application/pdf", "dara",
            linked_transaction_ref="txn-777",
        )
        self.assertEqual(
            self.vault.get_status_for_reference(ORG_A, transaction_ref="txn-777"),
            EvidenceStatus.UPLOADED.value,
        )

    # ------------------------------------------------------------------
    def test_evidence_is_tenant_isolated(self):
        record = self.vault.upload_evidence(
            ORG_A, EvidenceType.INVOICE, b"tenant-isolated-content", "i.pdf", "application/pdf", "dara"
        )
        from asavexa.evidence.domain.errors import EvidenceNotFoundError
        with self.assertRaises(EvidenceNotFoundError):
            self.vault.get_evidence(ORG_B, record.id)

    def test_every_action_is_audit_logged(self):
        record = self.vault.upload_evidence(
            ORG_A, EvidenceType.INVOICE, b"content-7", "i7.pdf", "application/pdf", "dara"
        )
        self.vault.verify_evidence(ORG_A, record.id, actor="controller")
        events = self.vault.audit.list_for_entity("EvidenceRecord", record.id, org_id=ORG_A)
        actions = [e.action for e in events]
        self.assertIn("EVIDENCE_UPLOADED", actions)
        self.assertIn("EVIDENCE_VERIFIED", actions)
        self.assertTrue(all(e.actor for e in events))


if __name__ == "__main__":
    unittest.main()
