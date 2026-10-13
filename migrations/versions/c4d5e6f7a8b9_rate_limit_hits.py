"""Rate limit counters for the shared limiter (Stage 9).

Revision ID: c4d5e6f7a8b9
Revises: b7c1d2e3f4a5
Create Date: 2026-10-13

Adds ONE table, rate_limit_hits, with CREATE ... IF NOT EXISTS. It changes no existing table or row, and holds only throttle counters.
The shared limiter is off unless RATE_LIMIT_BACKEND=postgres, so applying this revision changes no behaviour by itself.
The DDL lives in migrations/sql/ so it can be reviewed and tested directly with psql.
"""
import os
from typing import Sequence, Union

from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b7c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SQL_DIR = os.path.join(os.path.dirname(__file__), "..", "sql")
_NAME = "c4d5e6f7a8b9_rate_limit_hits"


def _read(kind: str) -> str:
    with open(os.path.join(_SQL_DIR, f"{_NAME}.{kind}.sql")) as f:
        return f.read()


def _statements(sql: str):
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def upgrade() -> None:
    for stmt in _statements(_read("up")):
        op.execute(stmt)


def downgrade() -> None:
    for stmt in _statements(_read("down")):
        op.execute(stmt)
