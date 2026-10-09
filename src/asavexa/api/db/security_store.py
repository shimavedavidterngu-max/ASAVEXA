"""PostgreSQL implementation of the security DocStore (same contract as MemoryDocStore / SqliteDocStore)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import select

from .security_models import SecurityDocORM


class SqlAlchemyDocStore:
    def __init__(self, session):
        self.session = session

    def put(self, kind: str, key: str, data: dict, org_id: Optional[str] = None) -> None:
        clean = json.loads(json.dumps(data, sort_keys=True, default=str))
        row = self.session.get(SecurityDocORM, (kind, key))
        now = datetime.now(timezone.utc)
        if row is None:
            self.session.add(SecurityDocORM(kind=kind, key=key, org_id=org_id, data=clean, updated_at=now))
            self.session.flush()      # so a second put of the same key in this request finds the row instead of inserting a duplicate
        else:
            row.data, row.org_id, row.updated_at = clean, org_id, now

    def get(self, kind: str, key: str, for_update: bool = False) -> Optional[dict]:
        row = self.session.get(SecurityDocORM, (kind, key), with_for_update=for_update)
        return dict(row.data) if row is not None else None

    def delete(self, kind: str, key: str) -> None:
        row = self.session.get(SecurityDocORM, (kind, key))
        if row is not None:
            self.session.delete(row)
            self.session.flush()

    def list(self, kind: str, org_id: Optional[str] = None, prefix: Optional[str] = None) -> List[Tuple[str, dict]]:
        q = select(SecurityDocORM).where(SecurityDocORM.kind == kind)
        if org_id is not None:
            q = q.where(SecurityDocORM.org_id == org_id)
        if prefix:
            q = q.where(SecurityDocORM.key.startswith(prefix, autoescape=True))
        return [(r.key, dict(r.data)) for r in self.session.scalars(q.order_by(SecurityDocORM.key)).all()]
