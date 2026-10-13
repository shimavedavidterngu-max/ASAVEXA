"""Start-up schema check. The application no longer creates tables itself: every table comes from schema.sql plus the
tracked Alembic revisions. This check only LOOKS. If a table is missing it says so loudly, naming the fix.

Modes (env ASAVEXA_SCHEMA_CHECK): "strict" (default) refuses to start when a table is missing; "warn" logs and starts.
A database that cannot be reached is not a schema failure: /ready already reports that, so start-up carries on."""
import logging
import os

logger = logging.getLogger("asavexa.schema")

BASE_TABLES = (
    "organisations", "users", "memberships", "sessions", "accounts", "accounting_periods", "journals", "journal_lines",
    "audit_events", "evidence_records", "reconciliations", "bank_transactions", "period_close_processes",
    "control_definitions", "control_executions", "findings", "remediations",
)
LATE_TABLES = (
    "organisation_profiles", "organisation_standards", "organisation_structures",
    "passport_shares", "passport_share_sessions", "security_docs",
)
REQUIRED_TABLES = BASE_TABLES + LATE_TABLES
FIX = "Run `alembic upgrade head` (see docs/stage1-migrations.md)."


class SchemaError(RuntimeError):
    pass


def find_missing(existing, required=REQUIRED_TABLES):
    have = set(existing)
    return [t for t in required if t not in have]


def mode(environ=None):
    value = (environ if environ is not None else os.environ).get("ASAVEXA_SCHEMA_CHECK", "strict").strip().lower()
    return value if value in ("strict", "warn") else "strict"


def check(existing, environ=None):
    """Returns the missing table names. Raises SchemaError in strict mode when any are missing."""
    missing = find_missing(existing)
    if not missing:
        return []
    message = f"database schema is incomplete, missing tables: {', '.join(missing)}. {FIX}"
    logger.critical(message)
    if mode(environ) == "strict":
        raise SchemaError(message)
    return missing


def verify_database(engine=None, environ=None):
    """Reads the table list from the configured database and applies check(). Never writes."""
    from sqlalchemy import inspect
    if engine is None:
        from .db.base import get_engine
        engine = get_engine()
    try:
        existing = inspect(engine).get_table_names()
    except SchemaError:
        raise
    except Exception as exc:
        logger.error("schema_check_skipped_database_unreachable", extra={"error_type": type(exc).__name__})
        return None
    return check(existing, environ)
