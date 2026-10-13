-- Revision c4d5e6f7a8b9: counters for the shared (multi-instance) rate limiter. Purely additive and IDEMPOTENT:
-- one new table, CREATE ... IF NOT EXISTS, never touches an existing table or row. Holds only a throttle key
-- (for example "login:203.0.113.5"), a window start and a hit count. No customer data. Rows are short-lived and
-- are deleted by the limiter itself once their window has passed.

CREATE TABLE IF NOT EXISTS rate_limit_hits (
    key           VARCHAR(200) NOT NULL,
    window_start  BIGINT NOT NULL,
    hits          INTEGER NOT NULL,
    PRIMARY KEY (key, window_start)
);

CREATE INDEX IF NOT EXISTS ix_rate_limit_hits_window ON rate_limit_hits (window_start);
