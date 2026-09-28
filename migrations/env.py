"""
Alembic environment script — standard structure, not executed in this
sandbox (alembic itself is unavailable here; see
docs/postgresql-runtime-verification.md). Written to work unmodified
once the package is installable.

DATABASE_URL is read from the environment (same variable the
application itself uses — see api/db/base.py and .env.example), never
hardcoded, so migrations always run against whatever database the
application is currently configured for.
"""
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `asavexa` importable the same way the application and test suite
# already do (PYTHONPATH=src), so `target_metadata` below can reference
# the real ORM Base without duplicating its definition.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from asavexa.api.db.base import Base  # noqa: E402

# Import every ORM module so their tables register on Base.metadata —
# importing api.db.base alone is not enough, since each module's ORM
# classes only get registered when their own file is imported.
from asavexa.api.db import (  # noqa: E402,F401
    audit_models,
    compliance_models,
    evidence_models,
    identity_models,
    models,
    period_close_models,
    reconciliation_models,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://asavexa:asavexa@localhost:5432/asavexa"
    )


def run_migrations_offline() -> None:
    """Generate SQL scripts without a live DB connection (`alembic
    upgrade head --sql`)."""
    context.configure(
        url=get_url(), target_metadata=target_metadata,
        literal_binds=True, dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """The normal case: connect to the real database and apply
    migrations directly."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
