"""
Shared audit-trail module.

`AuditEvent` (models.py) and `AuditRepository` (repository.py) are the
single source of truth for audit logging across Asavexa — the
Accounting Engine, Identity/Organisation module, and Evidence Vault all
write to the same audit trail through this module rather than each
keeping their own.

This was originally left as a stub with a note in the Accounting
Engine's pass: "promote AuditEvent/AuditRepository out of accounting/
into this package when a second module needs it." The Identity module
is that second module, so the promotion has been done.
"""
from .models import AuditEvent  # noqa: F401
from .repository import AuditRepository  # noqa: F401
