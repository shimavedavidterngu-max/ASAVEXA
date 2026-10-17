"""Proves the migrated database matches what the application used to create for itself at start-up.

CI-only (needs SQLAlchemy and PostgreSQL). It builds a second, throwaway database the OLD way (schema.sql, then the ORM models'
own table definitions via SQLAlchemy) and compares columns, indexes and constraints of the six late tables with the database
that `alembic upgrade head` produced. Any difference fails the build.

Usage:  DATABASE_URL=<migrated test db>  ADMIN_DATABASE_URL=<same server, database 'postgres'>  python scripts/schema_parity.py
Safety: refuses any URL that is not localhost / 127.0.0.1 / postgres (a CI service container)."""
import os
import re
import subprocess
import sys
import uuid

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
LATE = ("organisation_profiles", "organisation_standards", "organisation_structures", "passport_shares", "passport_share_sessions", "security_docs")


def check_safe(url):
    m = re.search(r"@([^:/?]+)", url or "")
    if not m or m.group(1) not in ("localhost", "127.0.0.1", "postgres") or "onrender.com" in url:
        sys.exit("refusing to run: not a local/CI test database")


def signature(engine):
    from sqlalchemy import text
    names = ",".join(f"'{t}'" for t in LATE)
    with engine.connect() as c:
        cols = c.execute(text(f"select table_name, column_name, data_type, is_nullable, coalesce(column_default,'') from information_schema.columns "
                              f"where table_schema='public' and table_name in ({names}) order by 1,2")).all()
        idx = c.execute(text(f"select tablename, indexname, indexdef from pg_indexes where schemaname='public' and tablename in ({names}) order by 1,2")).all()
        con = c.execute(text(f"select conrelid::regclass::text, conname, pg_get_constraintdef(oid) from pg_constraint where connamespace='public'::regnamespace "
                             f"and conrelid::regclass::text in ({names}) order by 1,2")).all()
    return {"columns": [tuple(r) for r in cols], "indexes": [tuple(r) for r in idx], "constraints": [tuple(r) for r in con]}


def main():
    from sqlalchemy import create_engine, text
    migrated_url, admin_url = os.environ["DATABASE_URL"], os.environ["ADMIN_DATABASE_URL"]
    check_safe(migrated_url); check_safe(admin_url)
    scratch = f"parity_{uuid.uuid4().hex[:8]}"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"CREATE DATABASE {scratch}"))
    try:
        scratch_url = re.sub(r"/[^/?]+(\?|$)", f"/{scratch}\\1", admin_url, count=1)
        plain = re.sub(r"^postgresql\+\w+", "postgresql", scratch_url)
        subprocess.run(["psql", plain, "-v", "ON_ERROR_STOP=1", "-q", "-f", os.path.join(ROOT, "schema.sql")], check=True)
        from asavexa.api.db.base import Base
        from asavexa.api.db import identity_models, passport_models, profile_models, security_models, standards_models  # noqa: F401
        old_way = create_engine(scratch_url)
        Base.metadata.create_all(old_way, tables=[Base.metadata.tables[t] for t in LATE], checkfirst=True)
        a, b = signature(create_engine(migrated_url)), signature(old_way)
    finally:
        with admin.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {scratch} WITH (FORCE)"))
    ok = True
    for part in ("columns", "indexes", "constraints"):
        only_migrated, only_orm = sorted(set(a[part]) - set(b[part])), sorted(set(b[part]) - set(a[part]))
        if only_migrated or only_orm:
            ok = False
            print(f"MISMATCH in {part}:\n  only in migration: {only_migrated}\n  only in ORM-created: {only_orm}")
    print("schema parity:", "OK" if ok else "FAILED", {k: len(v) for k, v in a.items()})
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
