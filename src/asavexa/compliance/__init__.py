"""
The Controls & Compliance / Audit Workspace module.

Public entry point: `asavexa.compliance.services.service.ComplianceService`.

Signature principle: "Don't just report the number. Prove it." —
extended here to: "Don't just claim compliance. Prove the control."

An orchestration/assessment layer over the six other modules. It
defines no accounting rules, stores no evidence, matches no bank
transactions, computes no financial statements, and writes to no
audit trail of its own — see README.md for the full architecture and
exactly which authoritative module each built-in control calls.

Makes no regulatory claims (no "IFRS compliant", no "SOX compliant")
— see README.md "Compliance scope".
"""
from .services.service import ComplianceService  # noqa: F401
