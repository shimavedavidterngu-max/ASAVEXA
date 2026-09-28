"""
The Accounting Engine module — the foundational module of Asavexa.

Public entry point: `asavexa.accounting.services.engine.AccountingEngine`.
Every other module should depend on this engine's public methods
(create_draft_journal, post_journal, reverse_journal, get_ledger,
get_trial_balance, get_audit_trail) rather than reaching into its
domain models or repositories directly.
"""
from .services.engine import AccountingEngine, LineInput  # noqa: F401
