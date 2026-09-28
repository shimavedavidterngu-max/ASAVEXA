"""
Pure invariant checks for the Evidence Vault. No side effects, no
storage dependency — same discipline as accounting/domain/rules.py.
"""
from __future__ import annotations

import hashlib

from .enums import EvidenceStatus
from .errors import EmptyFileError, InvalidEvidenceStateError

# Terminal states have no outgoing transitions — a REJECTED or EXPIRED
# record is closed; correcting it means uploading new evidence, not
# reopening the old record (mirrors the Accounting Engine's "never
# silently edit, only supersede" philosophy).
ALLOWED_TRANSITIONS: dict[EvidenceStatus, frozenset[EvidenceStatus]] = {
    EvidenceStatus.UPLOADED: frozenset({
        EvidenceStatus.VERIFIED, EvidenceStatus.INCOMPLETE,
        EvidenceStatus.DUPLICATE, EvidenceStatus.CONFLICTING, EvidenceStatus.REJECTED,
    }),
    EvidenceStatus.INCOMPLETE: frozenset({
        EvidenceStatus.VERIFIED, EvidenceStatus.CONFLICTING, EvidenceStatus.REJECTED,
    }),
    EvidenceStatus.CONFLICTING: frozenset({
        EvidenceStatus.VERIFIED, EvidenceStatus.INCOMPLETE, EvidenceStatus.REJECTED,
    }),
    EvidenceStatus.VERIFIED: frozenset({EvidenceStatus.EXPIRED, EvidenceStatus.REJECTED}),
    EvidenceStatus.DUPLICATE: frozenset({EvidenceStatus.REJECTED}),
    EvidenceStatus.REJECTED: frozenset(),
    EvidenceStatus.EXPIRED: frozenset(),
}


def compute_file_hash(content: bytes) -> str:
    if not content:
        raise EmptyFileError("Cannot upload empty evidence content.")
    return hashlib.sha256(content).hexdigest()


def assert_transition_allowed(current: EvidenceStatus, new: EvidenceStatus) -> None:
    if new not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise InvalidEvidenceStateError(
            f"Cannot move evidence from {current.value} to {new.value}."
        )
