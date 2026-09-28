"""
SQLAlchemy engine/session setup.

Requires `sqlalchemy` and a DB driver (`psycopg[binary]` for PostgreSQL —
see requirements.txt). Not executed in the sandbox that produced this
starter codebase (no network access to install packages there); install
requirements.txt in your own environment before running the API.

Engine construction is lazy (deferred to first use), not performed at
import time. Found during the Phase 2 API-boundary audit: the previous
version called `create_engine(DATABASE_URL)` at module import time,
which means merely *importing* this module — and therefore
`api.main`, and therefore anything that imports `api.main` for reasons
that have nothing to do with serving requests (generating OpenAPI
docs, running a linter, building a test harness against a different
DB) — required a resolvable `DATABASE_URL` and an importable driver
immediately, with no way to defer that. `create_engine()` itself
doesn't open a real connection (SQLAlchemy pools lazily by default),
so the practical risk was narrower than a real eager-connect would be
— but resolving the driver plugin for the URL scheme still happens at
that call, and there was no way to import this module for a purpose
that doesn't need a database at all. Lazy construction below removes
that requirement: `engine`/`SessionLocal` are created on first access
via `get_engine()`/`get_session_factory()`, not at import time.
`get_session()`'s own generator contract — yield a session, always
close it after the request — is completely unchanged.
"""
import os
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_engine: Optional[Engine] = None
_SessionFactory: Optional[sessionmaker] = None


def _database_url() -> str:
    # Read at call time, not import time — a test harness or a
    # differently-configured process can set DATABASE_URL any time
    # before the first real request, not just before this module is
    # first imported.
    return os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://asavexa:asavexa@localhost:5432/asavexa"
    )


def get_engine() -> Engine:
    """Lazily constructs (once) and returns the SQLAlchemy engine.
    Safe to call repeatedly — subsequent calls return the same instance."""
    global _engine
    if _engine is None:
        _engine = create_engine(_database_url(), pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _SessionFactory


class Base(DeclarativeBase):
    pass


def get_session():
    """FastAPI dependency: yields a session scoped to exactly one
    request, and commits it exactly once, here, only if the request
    completed without raising — never per repository call. Rolls back
    on any exception.

    Found during the Phase 3 persistence audit: every repository's
    create()/update() previously called session.commit() itself (29
    call sites across 7 files), making every individual write its own
    auto-committed transaction. That meant a service method performing
    several repository writes in sequence (e.g. AccountingEngine.
    post_journal(): update the journal's status, then record an audit
    event) had no atomicity across them — if the second write failed
    after the first had already committed, the first was left
    permanently persisted with no way to undo it. A journal could end
    up POSTED with no matching audit event, or any of this
    codebase's many other multi-write service operations (evidence
    verification, reconciliation approval, period close, finding/
    remediation transitions) could end up partially applied.

    The fix: repositories no longer call commit() themselves (see each
    repository file); the whole request is now one transaction,
    committed only on clean completion, rolled back otherwise. This is
    a PostgreSQL/SQLAlchemy-layer-only change — the SQLite repositories
    (used only for tests, never production) keep their existing
    per-operation commit behavior unchanged, since altering it would
    touch every test file's assumptions for a backend that never serves
    real traffic. See docs/postgresql-runtime-verification.md."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
