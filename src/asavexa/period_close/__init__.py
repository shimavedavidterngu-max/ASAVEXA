"""
The Period Close & Financial Controls module.

Public entry point: `asavexa.period_close.services.service.PeriodCloseService`.

Signature principle: "Don't just close the period. Prove that it was
properly closed."

Coordinates existing controls — the Accounting Engine's own period lock
(`lock_period`, unchanged), Financial Reporting's trial balance,
Reconciliation's transaction statuses, and Evidence Vault's
verification status — rather than reimplementing any of them. See
README.md for the full architecture and exactly why there is no second
period system here.
"""
from .services.service import PeriodCloseService  # noqa: F401
