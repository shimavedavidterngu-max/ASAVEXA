"""
Enumerations for the Evidence Vault.

Reference: ASAVEXA Master Blueprint, "Evidence Management Skill" and
"Evidence Verification Skill".
"""
from enum import Enum


class EvidenceType(str, Enum):
    INVOICE = "INVOICE"
    RECEIPT = "RECEIPT"
    CONTRACT = "CONTRACT"
    BANK_STATEMENT = "BANK_STATEMENT"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    DELIVERY_NOTE = "DELIVERY_NOTE"
    PAYROLL_EVIDENCE = "PAYROLL_EVIDENCE"
    TAX_DOCUMENT = "TAX_DOCUMENT"
    APPROVAL_RECORD = "APPROVAL_RECORD"
    OTHER = "OTHER"


class EvidenceStatus(str, Enum):
    """
    Blueprint's Evidence Verification Skill lists: present / missing /
    incomplete / duplicate / conflicting / expired / unverified /
    verified / rejected. "Missing" and "present" aren't states of a
    stored record — "missing" is the absence of a record (see
    EvidenceVault.get_status_for_reference), and "present" is simply
    that a record exists, in whichever of the states below it's in.
    """
    UPLOADED = "UPLOADED"        # present, not yet reviewed ("unverified")
    VERIFIED = "VERIFIED"
    INCOMPLETE = "INCOMPLETE"
    DUPLICATE = "DUPLICATE"
    CONFLICTING = "CONFLICTING"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class AuditAction(str, Enum):
    EVIDENCE_UPLOADED = "EVIDENCE_UPLOADED"
    EVIDENCE_VERIFIED = "EVIDENCE_VERIFIED"
    EVIDENCE_REJECTED = "EVIDENCE_REJECTED"
    EVIDENCE_STATUS_CHANGED = "EVIDENCE_STATUS_CHANGED"
