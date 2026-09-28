"""
The Financial Reporting module.

Public entry point: `asavexa.reporting.services.service.ReportingService`.

Signature principle: "Don't just report the number. Prove it."

A pure READ/DERIVATION layer over the Accounting Engine — see
README.md for why there is no reporting/repository/ package at all:
every report is computed fresh, on every call, from
AccountingEngine.get_trial_balance()/get_ledger(), never cached or
snapshotted. Trial Balance, Income Statement, Balance Sheet, and
General Ledger are all supported; `trace_line()` is the named
provenance drill-down back to individual posted ledger entries.
"""
from .services.service import ReportingService  # noqa: F401
