"""A rate limiter whose counters live in the shared database, so every server instance counts together (Stage 9).

Same interface as security.monitoring.RateLimiter (`allow(key) -> (allowed, seconds_until_retry)`), so the sign-in routes do not change.
Fixed windows: a counter per (key, window). One atomic upsert increments it, so concurrent instances cannot undercount. A burst can straddle a window
edge and briefly allow up to twice the limit; the in-memory limiter it replaces is a sliding window. That trade-off is the price of one atomic statement.

Safety: the limiter must never lock people out because of its own failure. If the database cannot be reached or the table is missing, it falls back to the
per-instance in-memory limiter, logs a warning (once a minute), and keeps throttling locally. It uses its own short connection that commits at once, so a
failed request cannot roll a hit back. Off by default: RATE_LIMIT_BACKEND=postgres turns it on.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional, Tuple

from .monitoring import RateLimiter

logger = logging.getLogger("asavexa.ratelimit")
KEY_MAX = 200

UPSERT = ("INSERT INTO rate_limit_hits (key, window_start, hits) VALUES ({p}, {p}, 1) "
          "ON CONFLICT (key, window_start) DO UPDATE SET hits = rate_limit_hits.hits + 1 RETURNING hits")
CLEANUP = "DELETE FROM rate_limit_hits WHERE window_start < {p}"


class SqlHitStore:
    """Counts hits through a DB-API connection factory (psycopg: placeholder %s; sqlite3: ?)."""

    def __init__(self, connect: Callable[[], object], placeholder: str = "%s"):
        self.connect, self.p = connect, placeholder

    def hit(self, key: str, window_start: int, cleanup_before: Optional[int] = None) -> int:
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute(UPSERT.format(p=self.p), (key, window_start))
            hits = cur.fetchone()[0]
            if hits == 1 and cleanup_before is not None:      # first hit of a new window: tidy old ones
                cur.execute(CLEANUP.format(p=self.p), (cleanup_before,))
            conn.commit()
            return int(hits)
        except Exception:
            try:
                conn.rollback()
            finally:
                raise
        finally:
            try:
                conn.close()
            except Exception:
                pass


class SharedRateLimiter:
    def __init__(self, name: str, limit: int, window_seconds: int, store, fallback: Optional[RateLimiter] = None, wall_clock: Callable[[], float] = time.time):
        self.name, self.limit, self.window, self.store, self.wall = name, limit, window_seconds, store, wall_clock
        self.fallback = fallback or RateLimiter(limit, window_seconds)
        self._warned_at = 0.0
        self.shared_calls = self.fallback_calls = 0

    def allow(self, key: str) -> Tuple[bool, int]:
        now = self.wall()
        start = int(now // self.window) * self.window
        full_key = f"{self.name}:{key}"[:KEY_MAX]
        try:
            hits = self.store.hit(full_key, start, cleanup_before=start - 2 * self.window)
        except Exception as exc:
            self.fallback_calls += 1
            if now - self._warned_at > 60:
                self._warned_at = now
                logger.warning("shared rate limiter unavailable for %s (%s); counting per instance for now", self.name, type(exc).__name__)
            return self.fallback.allow(key)
        self.shared_calls += 1
        if hits > self.limit:
            return False, max(1, int(start + self.window - now))
        return True, 0


def make_limiter(name: str, limit: int, window_seconds: int, backend: str = "memory", store=None):
    """The limiter for one endpoint. Anything other than backend 'postgres' with a store keeps the original in-memory limiter."""
    if backend == "postgres" and store is not None:
        return SharedRateLimiter(name, limit, window_seconds, store)
    return RateLimiter(limit, window_seconds)
