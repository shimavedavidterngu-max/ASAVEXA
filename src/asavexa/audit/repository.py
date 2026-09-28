"""Storage-agnostic audit repository contract, shared by every module."""
from __future__ import annotations

from typing import List, Optional, Protocol

from .models import AuditEvent


class AuditRepository(Protocol):
    def record(self, event: AuditEvent) -> AuditEvent: ...
    def list_for_entity(
        self, entity_type: str, entity_id: str, org_id: Optional[str] = None
    ) -> List[AuditEvent]: ...
    def list_for_org(self, org_id: str) -> List[AuditEvent]: ...
    def list_for_actor(self, actor: str) -> List[AuditEvent]: ...
