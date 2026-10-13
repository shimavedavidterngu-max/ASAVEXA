-- Revision b7c1d2e3f4a5: the six tables that used to be created at application start-up.
-- IDEMPOTENT by design: production already holds these tables (created by the old start-up hook), so every statement
-- is CREATE ... IF NOT EXISTS and never touches rows. Running it twice, or on a database that already has the tables,
-- changes nothing. Column types match what SQLAlchemy emitted for the ORM models in api/db/*_models.py.

CREATE TABLE IF NOT EXISTS organisation_profiles (
    org_id      UUID NOT NULL,
    data        JSONB NOT NULL,
    updated_at  TIMESTAMP WITH TIME ZONE,
    updated_by  VARCHAR NOT NULL,
    PRIMARY KEY (org_id),
    FOREIGN KEY (org_id) REFERENCES organisations (id)
);

CREATE TABLE IF NOT EXISTS organisation_standards (
    org_id      UUID NOT NULL,
    data        JSONB NOT NULL,
    updated_at  TIMESTAMP WITH TIME ZONE,
    updated_by  VARCHAR NOT NULL,
    PRIMARY KEY (org_id),
    FOREIGN KEY (org_id) REFERENCES organisations (id)
);

CREATE TABLE IF NOT EXISTS organisation_structures (
    org_id      UUID NOT NULL,
    data        JSONB NOT NULL,
    updated_at  TIMESTAMP WITH TIME ZONE,
    updated_by  VARCHAR NOT NULL,
    PRIMARY KEY (org_id),
    FOREIGN KEY (org_id) REFERENCES organisations (id)
);

CREATE TABLE IF NOT EXISTS passport_shares (
    id                    UUID NOT NULL,
    org_id                UUID NOT NULL,
    recipient_name        VARCHAR NOT NULL,
    recipient_type        VARCHAR NOT NULL,
    recipient_email       VARCHAR,
    purpose               VARCHAR,
    scopes                JSONB NOT NULL,
    include_detail        BOOLEAN NOT NULL,
    allow_download        BOOLEAN NOT NULL,
    closed_periods_only   BOOLEAN NOT NULL,
    date_from             DATE NOT NULL,
    date_to               DATE NOT NULL,
    status                VARCHAR NOT NULL,
    created_at            TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by            VARCHAR NOT NULL,
    expires_at            TIMESTAMP WITH TIME ZONE NOT NULL,
    secret_hash           VARCHAR NOT NULL,
    code_salt             VARCHAR NOT NULL,
    code_hash             VARCHAR NOT NULL,
    snapshot              JSONB NOT NULL,
    meta                  JSONB NOT NULL,
    fingerprint           VARCHAR NOT NULL,
    failed_attempts       INTEGER NOT NULL,
    access_count          INTEGER NOT NULL,
    last_accessed_at      TIMESTAMP WITH TIME ZONE,
    revoked_at            TIMESTAMP WITH TIME ZONE,
    revoked_by            VARCHAR,
    revoke_reason         VARCHAR,
    PRIMARY KEY (id),
    FOREIGN KEY (org_id) REFERENCES organisations (id)
);
CREATE INDEX IF NOT EXISTS ix_passport_shares_org_id ON passport_shares (org_id);

CREATE TABLE IF NOT EXISTS passport_share_sessions (
    id          UUID NOT NULL,
    share_id    UUID NOT NULL,
    token_hash  VARCHAR NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (token_hash),
    FOREIGN KEY (share_id) REFERENCES passport_shares (id)
);
CREATE INDEX IF NOT EXISTS ix_passport_share_sessions_share_id ON passport_share_sessions (share_id);

CREATE TABLE IF NOT EXISTS security_docs (
    kind        VARCHAR NOT NULL,
    key         VARCHAR NOT NULL,
    org_id      VARCHAR,
    data        JSONB NOT NULL,
    updated_at  TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (kind, key)
);
CREATE INDEX IF NOT EXISTS ix_security_docs_kind_org ON security_docs (kind, org_id);
