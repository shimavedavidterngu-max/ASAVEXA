"""READ-ONLY database preflight. Run it BEFORE deploying a release that contains a migration.

    python scripts/db_preflight.py

It reads DATABASE_URL from the environment (it is never printed), opens a READ ONLY transaction, and reports:
  * which database kind it reached (postgresql or not), never the host, user, password or name;
  * which Alembic revision the database is at (the alembic_version table);
  * which of the 23 expected tables exist, and how many rows the six start-up-created tables hold;
  * what to do next.
It runs SELECT statements only and changes nothing. Exit code 0 = safe to run `alembic upgrade head`, 1 = read the advice."""
import os
import sys

HEAD = "b7c1d2e3f4a5"
INITIAL = "9ab0a651f090"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))


def advise(version, missing_base, missing_late):
    if missing_base and len(missing_base) == 17 and version is None:
        return 0, "EMPTY DATABASE: `alembic upgrade head` will build everything. Safe."
    if missing_base:
        return 1, f"BASE TABLES MISSING ({', '.join(missing_base)}): do not deploy. Restore from a backup or investigate."
    if version is None:
        return 1, (f"The 17 base tables exist but there is NO alembic_version table, so Alembic would try to create them again and fail. "
                   f"Do NOT deploy yet. After taking a backup and confirming the schema, run `alembic stamp {INITIAL}` once, then `alembic upgrade head`.")
    if version == HEAD:
        return 0, "Already at the latest revision. Nothing to migrate."
    if version == INITIAL:
        return 0, ("At the initial revision. `alembic upgrade head` will add revision " + HEAD + " (CREATE TABLE IF NOT EXISTS only: the "
                   "tables that exist already are left exactly as they are). Take a backup first.")
    return 1, f"Unknown revision {version!r}. Do not deploy until this is understood."


def main():
    from asavexa.api.schema_check import BASE_TABLES, LATE_TABLES
    from sqlalchemy import create_engine, inspect, text
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set in this shell."); return 1
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        kind = engine.dialect.name
        have = set(inspect(conn).get_table_names())
        version = conn.execute(text("select version_num from alembic_version")).scalar() if "alembic_version" in have else None
        counts = {t: conn.execute(text(f'select count(*) from "{t}"')).scalar() for t in LATE_TABLES if t in have}
    missing_base = [t for t in BASE_TABLES if t not in have]
    missing_late = [t for t in LATE_TABLES if t not in have]
    print(f"database kind        : {kind}" + ("" if kind == "postgresql" else "   <- NOT PostgreSQL"))
    print(f"alembic revision     : {version or '(none)'}")
    print(f"base tables present  : {len(BASE_TABLES) - len(missing_base)} of {len(BASE_TABLES)}")
    print(f"late tables present  : {len(LATE_TABLES) - len(missing_late)} of {len(LATE_TABLES)}   rows: {counts}")
    code, msg = advise(version, missing_base, missing_late)
    print("verdict              :", msg)
    return code


if __name__ == "__main__":
    sys.exit(main())
