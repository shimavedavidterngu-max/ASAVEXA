"""
The Evidence Vault module.

Public entry point: `asavexa.evidence.services.vault.EvidenceVault`.

See README.md in this directory for the integration contract with the
Accounting Engine (Journal.evidence_ref / Journal.transaction_ref) —
the two modules connect only through opaque string references, never
by importing each other's domain types.
"""
from .services.vault import EvidenceVault  # noqa: F401
