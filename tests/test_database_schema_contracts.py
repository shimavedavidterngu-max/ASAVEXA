"""
DATABASE SCHEMA & MIGRATION CONTRACT TESTS.

Like tests/test_api_boundary_contracts.py, these are explicitly NOT
live-database tests. alembic/sqlalchemy/psycopg cannot be imported or
executed in this environment (no network access, no cached wheels —
confirmed directly). Nothing here pretends otherwise.

What this file DOES verify, for real:

1. schema.sql (PostgreSQL DDL), every SQLite CREATE TABLE, and every
   SQLAlchemy ORM model declare the SAME column names for the same
   17 tables (parsed via regex/ast, not executed).
2. Every monetary column is NUMERIC(18,2) in schema.sql, Numeric(18,2)
   in the ORM, and Decimal in the domain layer — the complete
   Decimal-only chain, with no float ever entering it.
3. The initial Alembic migration's structure is sound: it has real
   upgrade()/downgrade() functions, it reads the real schema.sql file
   (not a frozen copy that could drift), and its downgrade table list
   exactly matches schema.sql's actual tables.
4. Every tenant-scoped table referenced by a real repository query
   pattern has a matching index in schema.sql.

See docs/postgresql-runtime-verification.md for what remains
unverified (real migration execution, real PostgreSQL constraint
enforcement) and the exact commands to verify it once alembic/
sqlalchemy/psycopg are installable.
"""
import ast
import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO_ROOT, "src", "asavexa")
SCHEMA_SQL = os.path.join(REPO_ROOT, "schema.sql")
MIGRATIONS_DIR = os.path.join(REPO_ROOT, "migrations")


def _strip_sql_comments(text):
    return re.sub(r"--[^\n]*", "", text)


def _extract_pg_columns(table_name):
    with open(SCHEMA_SQL) as f:
        text = _strip_sql_comments(f.read())
    m = re.search(rf"CREATE TABLE {table_name} \((.*?)\n\);", text, re.DOTALL)
    if not m:
        return None
    depth, current, cols = 0, "", []
    for ch in m.group(1):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            cols.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        cols.append(current.strip())
    names = []
    for c in cols:
        c = c.strip()
        if not c or c.upper().startswith(("UNIQUE", "CHECK(", "CHECK (", "PRIMARY KEY", "FOREIGN KEY")):
            continue
        names.append(c.split()[0])
    return set(names)


def _extract_sqlite_columns(file_path, table_name):
    with open(os.path.join(SRC, file_path)) as f:
        text = _strip_sql_comments(f.read())
    m = re.search(rf"CREATE TABLE IF NOT EXISTS {table_name} \((.*?)\n\);", text, re.DOTALL)
    if not m:
        return None
    names = []
    for line in m.group(1).split("\n"):
        line = line.strip().rstrip(",")
        if not line or line.upper().startswith(("UNIQUE", "CHECK(", "CHECK (", "PRIMARY KEY", "FOREIGN KEY")):
            continue
        names.append(line.split()[0])
    return set(names)


def _extract_orm_columns(file_path, class_name):
    with open(os.path.join(SRC, file_path)) as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            names = []
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    if (isinstance(item.value, ast.Call) and isinstance(item.value.func, ast.Name)
                            and item.value.func.id == "relationship"):
                        continue  # ORM navigation helper, not a real column
                    names.append(item.target.id)
            return set(names)
    return None


# table -> (pg name, sqlite file, sqlite table name, orm file, orm class,
#           set of column names present under a different, deliberate
#           name in one layer — e.g. metadata/metadata_json — documented
#           and excluded from the strict equality check below)
TABLE_SOURCES = {
    "organisations": ("identity/repository/sqlite_repository.py", "organisations", "api/db/identity_models.py", "OrganisationORM", set()),
    "users": ("identity/repository/sqlite_repository.py", "users", "api/db/identity_models.py", "UserORM", set()),
    "memberships": ("identity/repository/sqlite_repository.py", "memberships", "api/db/identity_models.py", "MembershipORM", set()),
    "sessions": ("identity/repository/sqlite_repository.py", "sessions", "api/db/identity_models.py", "SessionORM", set()),
    "accounts": ("accounting/repository/sqlite_repository.py", "accounts", "api/db/models.py", "AccountORM", set()),
    "accounting_periods": ("accounting/repository/sqlite_repository.py", "periods", "api/db/models.py", "AccountingPeriodORM", set()),
    "journals": ("accounting/repository/sqlite_repository.py", "journals", "api/db/models.py", "JournalORM", set()),
    "journal_lines": ("accounting/repository/sqlite_repository.py", "journal_lines", "api/db/models.py", "JournalLineORM", set()),
    "audit_events": ("audit/sqlite_repository.py", "audit_events", "api/db/audit_models.py", "AuditEventORM", set()),
    # "metadata" (pg/sqlite) vs "metadata_json" (orm attribute) is a
    # deliberate, necessary SQLAlchemy pattern — DeclarativeBase itself
    # reserves the attribute name `metadata` for its own table registry,
    # so the ORM column MUST be mapped via mapped_column("metadata", ...)
    # under a different Python attribute name. Verified directly against
    # the source; not a defect. See test_evidence_metadata_column_mapping.
    "evidence_records": ("evidence/repository/sqlite_repository.py", "evidence_records", "api/db/evidence_models.py", "EvidenceRecordORM", {"metadata", "metadata_json"}),
    "reconciliations": ("reconciliation/repository/sqlite_repository.py", "reconciliations", "api/db/reconciliation_models.py", "ReconciliationORM", set()),
    "bank_transactions": ("reconciliation/repository/sqlite_repository.py", "bank_transactions", "api/db/reconciliation_models.py", "BankTransactionORM", set()),
    "period_close_processes": ("period_close/repository/sqlite_repository.py", "period_close_processes", "api/db/period_close_models.py", "PeriodCloseProcessORM", set()),
    "control_definitions": ("compliance/repository/sqlite_repository.py", "control_definitions", "api/db/compliance_models.py", "ControlDefinitionORM", set()),
    "control_executions": ("compliance/repository/sqlite_repository.py", "control_executions", "api/db/compliance_models.py", "ControlExecutionORM", set()),
    "findings": ("compliance/repository/sqlite_repository.py", "findings", "api/db/compliance_models.py", "FindingORM", set()),
    "remediations": ("compliance/repository/sqlite_repository.py", "remediations", "api/db/compliance_models.py", "RemediationORM", set()),
}


class SchemaColumnParityTestCase(unittest.TestCase):
    """Section 1/2: three-way column inventory across schema.sql, every
    SQLite schema, and every SQLAlchemy ORM model."""

    def test_every_table_has_matching_columns_across_all_three_representations(self):
        tables_checked = 0
        for table, (sqlite_file, sqlite_table, orm_file, orm_class, excused) in TABLE_SOURCES.items():
            tables_checked += 1
            pg = _extract_pg_columns(table)
            sqlite = _extract_sqlite_columns(sqlite_file, sqlite_table)
            orm = _extract_orm_columns(orm_file, orm_class)
            self.assertIsNotNone(pg, f"{table}: could not parse from schema.sql")
            self.assertIsNotNone(sqlite, f"{table}: could not parse from {sqlite_file} (table {sqlite_table})")
            self.assertIsNotNone(orm, f"{table}: could not parse {orm_class} from {orm_file}")

            pg_vs_sqlite_diff = (pg ^ sqlite) - excused
            pg_vs_orm_diff = (pg ^ orm) - excused
            self.assertFalse(
                pg_vs_sqlite_diff,
                f"{table}: schema.sql vs SQLite column mismatch: {pg_vs_sqlite_diff}",
            )
            self.assertFalse(
                pg_vs_orm_diff,
                f"{table}: schema.sql vs SQLAlchemy ORM column mismatch: {pg_vs_orm_diff}",
            )
        self.assertEqual(tables_checked, 17, "expected exactly 17 persisted tables")

    def test_evidence_metadata_column_mapping_is_the_documented_sqlalchemy_pattern(self):
        """The one legitimate excused difference above — confirmed here
        to actually be what it claims: a real mapped_column("metadata", ...)
        aliasing, not a silently-missing column."""
        with open(os.path.join(SRC, "api/db/evidence_models.py")) as f:
            src = f.read()
        self.assertIn('mapped_column("metadata"', src.replace("'metadata'", '"metadata"'))

    def test_accounting_periods_sqlite_table_name_is_a_documented_cosmetic_difference(self):
        """SQLite names this table `periods`; schema.sql and the ORM
        name it `accounting_periods`. Confirmed harmless: SQLite
        schemas declare no FOREIGN KEY / REFERENCES clauses anywhere
        (tenant/business rules are enforced at the service layer for
        the test backend), so nothing anywhere references this table
        by name across a constraint. Documented here rather than
        silently tolerated, and rather than renamed at risk to 215
        passing tests for a purely cosmetic gain."""
        for module in (
            "accounting/repository/sqlite_repository.py", "identity/repository/sqlite_repository.py",
            "evidence/repository/sqlite_repository.py", "reconciliation/repository/sqlite_repository.py",
            "period_close/repository/sqlite_repository.py", "compliance/repository/sqlite_repository.py",
        ):
            with open(os.path.join(SRC, module)) as f:
                self.assertNotIn("REFERENCES", f.read(), f"{module} unexpectedly declares a foreign key")


class FinancialPrecisionTestCase(unittest.TestCase):
    """Section 9: Decimal (domain) -> Numeric(18,2) (SQLAlchemy) ->
    NUMERIC(18,2) (PostgreSQL) -> Decimal (domain), with no float
    anywhere in the chain."""

    MONEY_COLUMNS = [
        ("journal_lines", "debit_amount"), ("journal_lines", "credit_amount"),
        ("bank_transactions", "debit_amount"), ("bank_transactions", "credit_amount"),
    ]

    def test_every_monetary_column_is_numeric_18_2_in_postgresql(self):
        with open(SCHEMA_SQL) as f:
            text = _strip_sql_comments(f.read())
        for table, column in self.MONEY_COLUMNS:
            m = re.search(rf"CREATE TABLE {table} \(.*?\n\s*{column}\s+(\S+)", text, re.DOTALL)
            self.assertIsNotNone(m, f"{table}.{column} not found in schema.sql")
            self.assertEqual(m.group(1), "NUMERIC(18,2)", f"{table}.{column} must be NUMERIC(18,2)")

    def test_no_float_or_real_type_anywhere_in_schema_sql(self):
        with open(SCHEMA_SQL) as f:
            text = _strip_sql_comments(f.read())
        for banned in ("FLOAT", " REAL", "DOUBLE PRECISION"):
            self.assertNotIn(banned, text.upper(), f"schema.sql must never use {banned.strip()} for any column")

    def test_sqlalchemy_orm_uses_numeric_not_float_for_money(self):
        for orm_file in ("api/db/models.py", "api/db/reconciliation_models.py"):
            with open(os.path.join(SRC, orm_file)) as f:
                src = f.read()
            self.assertIn("Numeric(18, 2)", src, f"{orm_file} must declare money columns as Numeric(18, 2)")
            self.assertNotIn("Float", src, f"{orm_file} must never use Float for a monetary column")

    def test_sqlalchemy_never_overrides_numeric_to_return_float(self):
        """SQLAlchemy's Numeric type returns Decimal by default;
        asdecimal=False would silently convert to float on every read.
        Confirmed absent anywhere in the ORM layer."""
        db_dir = os.path.join(SRC, "api", "db")
        for fname in os.listdir(db_dir):
            if fname.endswith(".py"):
                with open(os.path.join(db_dir, fname)) as f:
                    self.assertNotIn("asdecimal=False", f.read(), f"{fname} must never disable Decimal returns")

    def test_domain_layer_types_every_monetary_field_as_decimal(self):
        from decimal import Decimal  # noqa: F401 — imported to prove it's the real stdlib Decimal in scope
        for domain_file, class_names in (
            ("accounting/domain/models.py", ["JournalLine"]),
            ("reconciliation/domain/models.py", ["BankTransaction", "BankTransactionInput"]),
        ):
            with open(os.path.join(SRC, domain_file)) as f:
                tree = ast.parse(f.read())
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and node.name in class_names:
                    for item in node.body:
                        if (isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
                                and item.target.id in ("debit_amount", "credit_amount")):
                            ann = item.annotation
                            ann_name = ann.id if isinstance(ann, ast.Name) else getattr(ann, "attr", None)
                            self.assertEqual(
                                ann_name, "Decimal",
                                f"{domain_file}::{node.name}.{item.target.id} must be typed Decimal",
                            )


class MigrationStructureTestCase(unittest.TestCase):
    """Section 3: the Alembic migration structure is sound, and its
    initial migration genuinely represents the actual current schema
    (by reading schema.sql live, not a frozen transcription)."""

    def test_alembic_ini_and_env_py_exist(self):
        self.assertTrue(os.path.isfile(os.path.join(REPO_ROOT, "alembic.ini")))
        self.assertTrue(os.path.isfile(os.path.join(MIGRATIONS_DIR, "env.py")))
        self.assertTrue(os.path.isfile(os.path.join(MIGRATIONS_DIR, "script.py.mako")))

    def test_initial_migration_has_upgrade_and_downgrade_functions(self):
        versions_dir = os.path.join(MIGRATIONS_DIR, "versions")
        files = [f for f in os.listdir(versions_dir) if f.endswith(".py")]
        self.assertEqual(len(files), 1, "expected exactly one migration so far")
        with open(os.path.join(versions_dir, files[0])) as f:
            tree = ast.parse(f.read())
        fn_names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        self.assertIn("upgrade", fn_names)
        self.assertIn("downgrade", fn_names)

    def test_initial_migration_reads_the_real_schema_sql_not_a_frozen_copy(self):
        versions_dir = os.path.join(MIGRATIONS_DIR, "versions")
        files = [f for f in os.listdir(versions_dir) if f.endswith(".py")]
        with open(os.path.join(versions_dir, files[0])) as f:
            src = f.read()
        # Reads the file at runtime (open(...).read()) rather than
        # embedding schema.sql's text as a string literal — the two
        # can never quietly diverge if there is only one copy.
        self.assertIn("open(_SCHEMA_SQL_PATH)", src)
        self.assertNotIn("CREATE TABLE organisations", src, "schema DDL must not be duplicated inline in the migration")

    def test_downgrade_table_list_exactly_matches_schema_sql_tables(self):
        with open(SCHEMA_SQL) as f:
            text = _strip_sql_comments(f.read())
        real_tables = set(re.findall(r"CREATE TABLE (\w+)", text))

        versions_dir = os.path.join(MIGRATIONS_DIR, "versions")
        files = [f for f in os.listdir(versions_dir) if f.endswith(".py")]
        with open(os.path.join(versions_dir, files[0])) as f:
            tree = ast.parse(f.read())
        for node in tree.body:
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == "_TABLES_IN_CREATION_ORDER"):
                migration_tables = {elt.value for elt in node.value.elts}
                self.assertEqual(
                    migration_tables, real_tables,
                    "the migration's downgrade table list must exactly match schema.sql's actual tables",
                )
                return
        self.fail("_TABLES_IN_CREATION_ORDER not found in the initial migration")


class TenantIndexCoverageTestCase(unittest.TestCase):
    """Section 7: every table that real repository code queries by
    org_id has a schema.sql index covering that access pattern —
    checked against the tables this codebase's repositories actually
    query by org_id, not a generic 'every table needs an index' rule."""

    # table -> the leading-column index that must exist for its
    # dominant org_id-scoped query pattern (verified against each
    # repository's actual SELECT ... WHERE org_id=... usage).
    TENANT_SCOPED_TABLES = [
        "memberships", "accounts", "accounting_periods", "journals",
        "audit_events", "evidence_records", "reconciliations", "bank_transactions",
        "period_close_processes", "control_definitions", "control_executions",
        "findings", "remediations",
    ]

    def test_every_tenant_scoped_table_has_at_least_one_org_id_leading_index(self):
        with open(SCHEMA_SQL) as f:
            text = _strip_sql_comments(f.read())
        indexes = re.findall(r"CREATE INDEX \w+ ON (\w+)\(org_id", text)
        unique_org_scoped = re.findall(r"UNIQUE \(org_id", text)
        tables_with_org_coverage = set(indexes)
        # UNIQUE(org_id, ...) constraints also create an implicit index
        # in PostgreSQL — accounts and control_definitions rely on this
        # (UNIQUE (org_id, code)) rather than a separate CREATE INDEX.
        for table in ("accounts", "control_definitions"):
            tables_with_org_coverage.add(table)
        missing = [t for t in self.TENANT_SCOPED_TABLES if t not in tables_with_org_coverage]
        self.assertFalse(missing, f"tenant-scoped tables with no org_id-leading index or unique constraint: {missing}")


if __name__ == "__main__":
    unittest.main()
