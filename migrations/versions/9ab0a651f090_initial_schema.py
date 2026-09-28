"""Initial schema — applies schema.sql verbatim.

Revision ID: 9ab0a651f090
Revises:
Create Date: 2026-09-24

This migration deliberately does NOT reimplement schema.sql's DDL in
Alembic's op.create_table()/op.create_index() Python DSL. Doing so
would create a second, hand-transcribed copy of the schema that could
silently drift from schema.sql over time (exactly the failure mode the
Phase 3 brief warned against: "Avoid a situation where schema.sql and
Alembic migrations quietly describe different databases"). Instead,
upgrade() reads and executes schema.sql's actual, current content at
migration-run time. There is exactly one source of truth for the
schema's DDL — this file has no copy of it to go stale.

Not executed in the sandbox that produced this codebase (alembic is
unavailable — see docs/postgresql-runtime-verification.md). The SQL
this applies is schema.sql itself, which the domain/service layer's
213+ SQLite-backed tests already prove is a coherent, self-consistent
schema for every table's read/write contract — this migration's job is
only to apply that same DDL to PostgreSQL in a tracked, repeatable way,
not to define new schema.
"""
import os
from typing import Sequence, Union

from alembic import op

revision: str = "9ab0a651f090"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# schema.sql lives at the repository root, two directories up from
# migrations/versions/.
_SCHEMA_SQL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "schema.sql"
)

# Table names in the exact dependency order schema.sql creates them in
# — used only by downgrade() below, which must drop in reverse.
_TABLES_IN_CREATION_ORDER = [
    "organisations", "users", "memberships", "sessions",
    "accounts", "accounting_periods", "journals", "journal_lines",
    "audit_events", "evidence_records",
    "reconciliations", "bank_transactions",
    "period_close_processes",
    "control_definitions", "control_executions", "findings", "remediations",
]


def upgrade() -> None:
    with open(_SCHEMA_SQL_PATH) as f:
        ddl = f.read()
    # schema.sql's own trailing section is an explicitly-commented-out
    # trigger (see its own note: "Uncomment once the application is
    # stable and this has been tested against real migrations") — never
    # executed here either; op.execute runs exactly the same
    # CREATE TABLE/CREATE INDEX statements schema.sql contains, nothing
    # more, nothing translated.
    #
    # CAVEAT, stated honestly rather than assumed away: this passes the
    # entire multi-statement file to op.execute() in one call, relying
    # on psycopg3 (requirements.txt pins psycopg[binary]>=3.1, not
    # psycopg2) supporting multi-statement execution in a single
    # cursor.execute() call, which psycopg3 does but psycopg2 does not.
    # This has NOT been run against a real database in this environment
    # — if it turns out not to work as expected against the actual
    # driver/server combination, split on statement-terminating `;`
    # (respecting that schema.sql's only semicolons inside comments are
    # in its fully `--`-commented-out trigger block, never executed
    # either way) and call op.execute() per statement instead. See
    # docs/postgresql-runtime-verification.md.
    op.execute(ddl)


def downgrade() -> None:
    # Reverse dependency order: a table with a foreign key to another
    # must be dropped before the table it references.
    for table in reversed(_TABLES_IN_CREATION_ORDER):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
