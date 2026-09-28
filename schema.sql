-- ASAVEXA — Platform schema (PostgreSQL)
--
-- Covers Identity/Organisation (organisations, users, memberships,
-- sessions), the Accounting Engine (accounts, accounting_periods,
-- journals, journal_lines), the Evidence Vault (evidence_records),
-- Reconciliation (reconciliations, bank_transactions), Period
-- Close (period_close_processes), and Controls & Compliance
-- (control_definitions, control_executions, findings, remediations)
-- — plus the shared audit_events table every module writes to.
-- Financial Reporting owns no tables of its own; every report it
-- produces is derived fresh, never stored (see reporting/README.md).
-- Mirrors the domain dataclasses under src/asavexa/*/domain/models.py
-- and the SQLite schemas used in tests. This is the production
-- target — apply via a migration tool (Alembic recommended, not
-- included in this starter) rather than running this file directly
-- against a live database.
--
-- Design notes:
--   * Money is NUMERIC(18,2), never FLOAT/REAL.
--   * journals.status transitions DRAFT -> POSTED -> REVERSED are
--     enforced in the application layer (services/engine.py), not by a
--     database trigger, so the same rule logic and error messages are
--     used whether the caller is the API or a future batch job. A
--     trigger-level backstop can be added later without changing the
--     application contract.
--   * Nothing is ever DELETEd from journals/journal_lines/audit_events in
--     normal operation — corrections are reversals (Rule 6).
--   * evidence_records has no foreign key to journals — the integration
--     contract between Accounting and Evidence is the opaque string
--     linked_journal_id / Journal.evidence_ref, not a DB-enforced FK
--     (see src/asavexa/evidence/README.md). Keeping the two modules
--     decoupled at the schema level, not just in application code, is
--     deliberate.

CREATE TABLE organisations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------
-- Identity / Organisation / Multi-Tenant
-- ----------------------------------------------------------------------
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    mfa_enabled     BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE memberships (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organisations(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    role            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','SUSPENDED','REVOKED')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      TEXT NOT NULL,
    UNIQUE (org_id, user_id)
);
CREATE INDEX idx_memberships_org ON memberships(org_id);
CREATE INDEX idx_memberships_user ON memberships(user_id);

CREATE TABLE sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    -- The session's *currently selected* organisation context — null
    -- immediately after login, set by POST /auth/select-organisation.
    org_id          UUID REFERENCES organisations(id),
    token_hash      TEXT NOT NULL UNIQUE,   -- sha256 of the bearer token; raw token is never stored
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ
);
CREATE INDEX idx_sessions_user ON sessions(user_id);

-- ----------------------------------------------------------------------
-- Accounting Engine
-- ----------------------------------------------------------------------
CREATE TABLE accounts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organisations(id),
    code            TEXT NOT NULL,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL CHECK (type IN ('ASSET','LIABILITY','EQUITY','REVENUE','EXPENSE')),
    currency        CHAR(3) NOT NULL DEFAULT 'USD',
    parent_id       UUID REFERENCES accounts(id),
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, code)
);
CREATE INDEX idx_accounts_org ON accounts(org_id);

CREATE TABLE accounting_periods (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organisations(id),
    name            TEXT NOT NULL,
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL CHECK (end_date >= start_date),
    status          TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','LOCKED','CLOSED')),
    locked_at       TIMESTAMPTZ,
    locked_by       TEXT
);
CREATE INDEX idx_periods_org_dates ON accounting_periods(org_id, start_date, end_date);

CREATE TABLE journals (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  UUID NOT NULL REFERENCES organisations(id),
    period_id               UUID NOT NULL REFERENCES accounting_periods(id),
    journal_number          TEXT NOT NULL,
    date                    DATE NOT NULL,
    description             TEXT NOT NULL,
    currency                CHAR(3) NOT NULL,
    status                  TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','POSTED','REVERSED')),
    created_by              TEXT NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    posted_by               TEXT,
    posted_at               TIMESTAMPTZ,
    reversal_of_journal_id  UUID REFERENCES journals(id),
    reversed_by_journal_id  UUID REFERENCES journals(id),
    -- Evidence & source linkage — populated once the Evidence Vault and
    -- Transaction modules exist (see src/asavexa/evidence/README.md).
    transaction_ref         TEXT,
    evidence_ref            TEXT,
    UNIQUE (org_id, journal_number)
);
CREATE INDEX idx_journals_org_period ON journals(org_id, period_id);
CREATE INDEX idx_journals_org_status ON journals(org_id, status);
CREATE INDEX idx_journals_org_date ON journals(org_id, date);

CREATE TABLE journal_lines (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    journal_id      UUID NOT NULL REFERENCES journals(id),
    line_no         INTEGER NOT NULL,
    account_id      UUID NOT NULL REFERENCES accounts(id),
    debit_amount    NUMERIC(18,2) NOT NULL DEFAULT 0 CHECK (debit_amount >= 0),
    credit_amount   NUMERIC(18,2) NOT NULL DEFAULT 0 CHECK (credit_amount >= 0),
    description     TEXT NOT NULL DEFAULT '',
    CHECK ( (debit_amount = 0) OR (credit_amount = 0) ),   -- exactly one side per line
    CHECK ( (debit_amount > 0) OR (credit_amount > 0) ),   -- never a no-op line
    UNIQUE (journal_id, line_no)
);
CREATE INDEX idx_lines_journal ON journal_lines(journal_id);
CREATE INDEX idx_lines_account ON journal_lines(account_id);

CREATE TABLE audit_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Nullable: login/logout and other pre-org-selection actions are not
    -- yet scoped to an organisation. Every org-scoped action (journal
    -- postings, evidence uploads, membership changes, ...) still passes
    -- a real org_id — this is not an invitation to omit it.
    org_id              UUID REFERENCES organisations(id),
    entity_type         TEXT NOT NULL,
    entity_id           UUID NOT NULL,
    action              TEXT NOT NULL,
    actor               TEXT NOT NULL,
    timestamp           TIMESTAMPTZ NOT NULL DEFAULT now(),
    previous_value      JSONB,
    new_value           JSONB,
    reason              TEXT,
    related_record_id   UUID
);
CREATE INDEX idx_audit_org_entity ON audit_events(org_id, entity_type, entity_id);
CREATE INDEX idx_audit_org_time ON audit_events(org_id, timestamp);
CREATE INDEX idx_audit_actor ON audit_events(actor);

-- ----------------------------------------------------------------------
-- Evidence Vault
-- ----------------------------------------------------------------------
CREATE TABLE evidence_records (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  UUID NOT NULL REFERENCES organisations(id),
    type                    TEXT NOT NULL,
    status                  TEXT NOT NULL DEFAULT 'UPLOADED',
    file_hash               TEXT NOT NULL,     -- sha256 hex of the uploaded content
    original_filename       TEXT NOT NULL,
    content_type            TEXT NOT NULL,
    size_bytes              INTEGER NOT NULL,
    uploaded_by             TEXT NOT NULL,
    uploaded_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    verified_by             TEXT,
    verified_at             TIMESTAMPTZ,
    verification_note       TEXT,
    rejection_reason        TEXT,
    -- No FK to journals — see the module docstring at the top of this file.
    linked_journal_id       UUID,
    linked_transaction_ref  TEXT,
    metadata                JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX idx_evidence_org ON evidence_records(org_id);
CREATE INDEX idx_evidence_org_hash ON evidence_records(org_id, file_hash);
CREATE INDEX idx_evidence_journal ON evidence_records(linked_journal_id);
CREATE INDEX idx_evidence_txn_ref ON evidence_records(linked_transaction_ref);

-- ----------------------------------------------------------------------
-- Reconciliation
-- ----------------------------------------------------------------------
-- Reads accounts/journals through the Accounting Engine's existing
-- interfaces (see src/asavexa/reconciliation/services/service.py) and
-- never writes to them. bank_transactions.matched_journal_id has no FK
-- to journals for the same decoupling reason evidence_records has none
-- — the relationship is proven by application logic and recorded in
-- match_reason/match_rule/match_history, not enforced by the database.
CREATE TABLE reconciliations (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                          UUID NOT NULL REFERENCES organisations(id),
    bank_account_id                 UUID NOT NULL REFERENCES accounts(id),
    name                            TEXT NOT NULL,
    period_start                    DATE NOT NULL,
    period_end                      DATE NOT NULL CHECK (period_end >= period_start),
    currency                        CHAR(3) NOT NULL DEFAULT 'USD',
    status                          TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','SUBMITTED','RECONCILED','REJECTED')),
    created_by                      TEXT NOT NULL,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    submitted_by                    TEXT,
    submitted_at                    TIMESTAMPTZ,
    approved_by                     TEXT,
    approved_at                     TIMESTAMPTZ,
    rejected_by                     TEXT,
    rejected_at                     TIMESTAMPTZ,
    rejection_reason                TEXT,
    supersedes_reconciliation_id    UUID REFERENCES reconciliations(id),
    -- Opaque pointer into the Evidence Vault, exactly like journals.evidence_ref.
    evidence_ref                    TEXT
);
CREATE INDEX idx_reconciliations_org ON reconciliations(org_id);
CREATE INDEX idx_reconciliations_org_account ON reconciliations(org_id, bank_account_id);

CREATE TABLE bank_transactions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  UUID NOT NULL REFERENCES organisations(id),
    reconciliation_id       UUID NOT NULL REFERENCES reconciliations(id),
    bank_account_id         UUID NOT NULL REFERENCES accounts(id),
    import_batch_id         UUID NOT NULL,
    -- Deterministic duplicate-import guard: sha256(org_id, bank_account_id,
    -- external_ref, date, debit, credit, normalized description). See
    -- reconciliation/domain/matching.py::compute_dedup_hash.
    dedup_hash              TEXT NOT NULL,
    transaction_date        DATE NOT NULL,
    value_date              DATE,
    description             TEXT NOT NULL,
    debit_amount            NUMERIC(18,2) NOT NULL DEFAULT 0 CHECK (debit_amount >= 0),
    credit_amount           NUMERIC(18,2) NOT NULL DEFAULT 0 CHECK (credit_amount >= 0),
    CHECK ( (debit_amount = 0) OR (credit_amount = 0) ),
    CHECK ( (debit_amount > 0) OR (credit_amount > 0) ),
    currency                CHAR(3) NOT NULL DEFAULT 'USD',
    external_ref            TEXT,
    status                  TEXT NOT NULL DEFAULT 'IMPORTED'
                              CHECK (status IN ('IMPORTED','MATCHED','REVIEW_REQUIRED','UNMATCHED','APPROVED','RECONCILED','REJECTED')),
    -- No FK to journals — see the module note above.
    matched_journal_id      UUID,
    match_reason            TEXT,
    match_rule              TEXT,
    match_history           JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_by              TEXT NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, bank_account_id, dedup_hash)
);
CREATE INDEX idx_banktxn_org_recon ON bank_transactions(org_id, reconciliation_id);
CREATE INDEX idx_banktxn_org_account ON bank_transactions(org_id, bank_account_id);
CREATE INDEX idx_banktxn_matched_journal ON bank_transactions(matched_journal_id);

-- ----------------------------------------------------------------------
-- Period Close & Financial Controls
-- ----------------------------------------------------------------------
-- The only thing this module persists: the maker-checker workflow
-- record. It has no other tables — CloseReadinessReport and every
-- ControlFinding are always computed fresh, never stored (see
-- period_close/README.md "Architecture"). Locking the accounting
-- period itself uses accounting_periods.status (already present,
-- unchanged) via the Accounting Engine's own lock_period() — this
-- table has no status column that could ever disagree with it.
CREATE TABLE period_close_processes (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                          UUID NOT NULL REFERENCES organisations(id),
    period_id                       UUID NOT NULL REFERENCES accounting_periods(id),
    status                          TEXT NOT NULL DEFAULT 'REQUESTED'
                                      CHECK (status IN ('REQUESTED','READY_FOR_CLOSE','CONTROLS_FAILED','CLOSED','REJECTED')),
    requested_by                    TEXT NOT NULL,
    requested_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_findings                   JSONB NOT NULL DEFAULT '[]'::jsonb,
    reviewed_by                     TEXT,
    reviewed_at                     TIMESTAMPTZ,
    approved_by                     TEXT,
    approved_at                     TIMESTAMPTZ,
    rejected_by                     TEXT,
    rejected_at                     TIMESTAMPTZ,
    rejection_reason                TEXT,
    supersedes_close_process_id     UUID REFERENCES period_close_processes(id)
);
CREATE INDEX idx_close_org_period ON period_close_processes(org_id, period_id);

-- ----------------------------------------------------------------------
-- Controls & Compliance / Audit Workspace
-- ----------------------------------------------------------------------
-- Four distinct entities, deliberately kept separate — see
-- compliance/README.md "Architecture": a ControlDefinition is not a
-- ControlExecution is not a Finding is not a Remediation. Every
-- control's check_key selects one of a fixed set of built-in Python
-- functions (see compliance/services/service.py) — there is no rule
-- language stored in the database. Tenant isolation for writes follows
-- this project's established pattern (see the same module's README,
-- "Tenant isolation"): every read is org_id-scoped in its WHERE
-- clause; UPDATE statements are not, because the service layer only
-- ever calls update() with a record already fetched (and therefore
-- already org-verified) via get(org_id, id) in the same operation —
-- identical to accounting.journals, evidence.evidence_records, and
-- reconciliation.bank_transactions before it.
CREATE TABLE control_definitions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organisations(id),
    code            TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    objective       TEXT NOT NULL,
    severity        TEXT NOT NULL CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    domain          TEXT NOT NULL CHECK (domain IN ('ACCOUNTING','RECONCILIATION','EVIDENCE','REPORTING','PERIOD_CLOSE')),
    check_key       TEXT NOT NULL,
    frequency       TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_by      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, code)
);
CREATE INDEX idx_control_defs_org ON control_definitions(org_id);

CREATE TABLE control_executions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organisations(id),
    control_id      UUID NOT NULL REFERENCES control_definitions(id),
    period_id       UUID REFERENCES accounting_periods(id),
    executed_by     TEXT NOT NULL,
    executed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    result          TEXT NOT NULL CHECK (result IN ('PASS','FAIL','WARNING','NOT_APPLICABLE','REQUIRES_REVIEW')),
    explanation     TEXT NOT NULL,
    reference       JSONB NOT NULL DEFAULT '{}'::jsonb,
    reviewed_by     TEXT,
    reviewed_at     TIMESTAMPTZ,
    -- No FK to findings — a finding references its originating
    -- execution, not the other way around at the DB level, avoiding a
    -- circular FK between the two tables.
    finding_id      UUID
);
CREATE INDEX idx_control_exec_org_control ON control_executions(org_id, control_id);
CREATE INDEX idx_control_exec_org_period ON control_executions(org_id, period_id);

CREATE TABLE findings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organisations(id),
    control_id      UUID NOT NULL REFERENCES control_definitions(id),
    execution_id    UUID NOT NULL REFERENCES control_executions(id),
    description     TEXT NOT NULL,
    severity        TEXT NOT NULL CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    status          TEXT NOT NULL DEFAULT 'OPEN'
                      CHECK (status IN ('OPEN','UNDER_REVIEW','REMEDIATION_REQUIRED','RESOLVED','VERIFIED','CLOSED')),
    created_by      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    evidence_ref    TEXT,
    -- No FK to remediations — same circular-reference reasoning as
    -- control_executions.finding_id above.
    remediation_id  UUID,
    closed_by       TEXT,
    closed_at       TIMESTAMPTZ,
    history         JSONB NOT NULL DEFAULT '[]'::jsonb
);
CREATE INDEX idx_findings_org_status ON findings(org_id, status);
CREATE INDEX idx_findings_org_control ON findings(org_id, control_id);

CREATE TABLE remediations (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                      UUID NOT NULL REFERENCES organisations(id),
    finding_id                  UUID NOT NULL REFERENCES findings(id),
    action                      TEXT NOT NULL,
    owner                       TEXT NOT NULL,
    status                      TEXT NOT NULL DEFAULT 'PLANNED'
                                  CHECK (status IN ('PLANNED','IN_PROGRESS','COMPLETED','VERIFIED')),
    created_by                  TEXT NOT NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    due_date                    DATE,
    completion_evidence_ref     TEXT,
    completed_by                TEXT,
    completed_at                TIMESTAMPTZ,
    verified_by                 TEXT,
    verified_at                 TIMESTAMPTZ,
    verification_note           TEXT
);
CREATE INDEX idx_remediations_org_finding ON remediations(org_id, finding_id);

-- Defense-in-depth: a database-level guard against editing a posted
-- journal's lines, in addition to the application-layer check in
-- services/engine.py (assert_journal_editable). Uncomment once the
-- application is stable and this has been tested against real migrations.
--
-- CREATE OR REPLACE FUNCTION forbid_edit_of_posted_journal_lines()
-- RETURNS TRIGGER AS $$
-- BEGIN
--   IF EXISTS (
--     SELECT 1 FROM journals
--     WHERE id = OLD.journal_id AND status <> 'DRAFT'
--   ) THEN
--     RAISE EXCEPTION 'Cannot modify lines of a non-DRAFT journal (immutability rule)';
--   END IF;
--   RETURN NEW;
-- END;
-- $$ LANGUAGE plpgsql;
--
-- CREATE TRIGGER trg_forbid_edit_posted_lines
-- BEFORE UPDATE OR DELETE ON journal_lines
-- FOR EACH ROW EXECUTE FUNCTION forbid_edit_of_posted_journal_lines();
