-- Drops the rate-limit counters. Safe: they hold only throttle counts, no customer data. If the shared limiter is
-- switched on (RATE_LIMIT_BACKEND=postgres) it falls back to per-instance counting until the table exists again.
DROP TABLE IF EXISTS rate_limit_hits;
