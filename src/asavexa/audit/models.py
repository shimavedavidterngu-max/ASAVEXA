"""
Shared audit-trail model.

Promoted out of accounting/domain/models.py now that a second module
(Identity) needs to write audit events — see the note that was left in
this package's __init__.py when the Accounting Engine was built.

`org_id` is Optional because some actions are not yet scoped to an
organisation — most notably login/logout, which authenticate a user
before they have selected an organisation context. Every
organisation-scoped action (journal posting, evidence upload, ...) must
still pass a real org_id; this is not an invitation to omit it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class AuditEvent:
    """
    An immutable record of a material action, per the blueprint's Audit
    Trail Rule: who / what / when / previous value / new value / reason /
    related record.
    """
    id: str
    entity_type: str
    entity_id: str
    action: str
    actor: str
    timestamp: datetime
    org_id: Optional[str] = None
    previous_value: Optional[dict] = None
    new_value: Optional[dict] = None
    reason: Optional[str] = None
    related_record_id: Optional[str] = None
