"""Late tables — brings the six start-up-created tables under version control.

Revision ID: b7c1d2e3f4a5
Revises: 9ab0a651f090
Create Date: 2026-10-12

Until this revision the application created organisation_profiles, organisation_standards, organisation_structures,
passport_shares, passport_share_sessions and security_docs itself at start-up. Production already has them, so upgrade()
is IDEMPOTENT (CREATE ... IF NOT EXISTS): it never alters or deletes a row, and running it on a database that already
has the tables is a no-op. The DDL lives in migrations/sql/ so it can be reviewed and tested directly with psql.

downgrade() is deliberately guarded: it would delete real customer data, so it refuses unless
ASAVEXA_ALLOW_DESTRUCTIVE_DOWNGRADE=1 is set on purpose. See docs/stage1-migrations.md.
"""
import os
from typing import Sequence, Union

from alembic import op

revision: str = "b7c1d2e3f4a5"
down_revision: Union[str, None] = "9ab0a651f090"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SQL_DIR = os.path.join(os.path.dirname(__file__), "..", "sql")
_NAME = "b7c1d2e3f4a5_late_tables"


def _read(kind: str) -> str:
    with open(os.path.join(_SQL_DIR, f"{_NAME}.{kind}.sql")) as f:
        return f.read()


def _statements(sql: str):
    """One statement per call, comments removed: works the same on psycopg3 and in offline (--sql) mode."""
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def upgrade() -> None:
    for stmt in _statements(_read("up")):
        op.execute(stmt)


def downgrade() -> None:
    if os.environ.get("ASAVEXA_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "Refusing to drop the six late tables: this deletes real data. Take a verified backup, then set "
            "ASAVEXA_ALLOW_DESTRUCTIVE_DOWNGRADE=1 if you really mean it (docs/stage1-migrations.md)."
        )
    for stmt in _statements(_read("down")):
        op.execute(stmt)
