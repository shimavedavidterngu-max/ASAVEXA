"""Health checks, counters, a simple rate limiter, and security headers."""
from __future__ import annotations

import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Callable, Dict, List, Optional, Tuple


class Metrics:
    def __init__(self):
        self._c: Dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()
        self.started = time.time()

    def inc(self, name: str, n: int = 1):
        with self._lock:
            self._c[name] += n

    def snapshot(self) -> dict:
        with self._lock:
            return {"uptime_seconds": int(time.time() - self.started), "counters": dict(self._c)}


class RateLimiter:
    """Sliding window per key. In-memory, so each server instance counts separately (state that single instance only)."""
    def __init__(self, limit: int, window_seconds: int, now: Callable[[], float] = time.monotonic):
        self.limit, self.window, self.now = limit, window_seconds, now
        self._hits: Dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> Tuple[bool, int]:
        """Returns (allowed, seconds_until_retry)."""
        t = self.now()
        with self._lock:
            q = self._hits[key]
            while q and t - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False, max(1, int(self.window - (t - q[0])))
            q.append(t)
            if len(self._hits) > 50000:                  # bound memory
                for k in [k for k, v in self._hits.items() if not v or t - v[-1] >= self.window][:10000]:
                    self._hits.pop(k, None)
            return True, 0


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store", "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'", "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}


def new_request_id() -> str:
    return secrets.token_hex(8)


class HealthChecker:
    """checks: list of (name, callable returning detail str; raising means failed, critical?)."""
    def __init__(self):
        self.checks: List[Tuple[str, Callable[[], str], bool]] = []

    def add(self, name: str, fn: Callable[[], str], critical: bool = True):
        self.checks.append((name, fn, critical))
        return self

    def run(self) -> dict:
        results, worst = [], "OK"
        for name, fn, critical in self.checks:
            t0 = time.perf_counter()
            try:
                detail, ok = fn(), True
            except Exception as e:
                detail, ok = f"{type(e).__name__}: {str(e)[:160]}", False
            results.append({"name": name, "ok": ok, "critical": critical, "detail": detail, "ms": int((time.perf_counter() - t0) * 1000)})
            if not ok:
                worst = "DOWN" if critical else ("DEGRADED" if worst == "OK" else worst)
        return {"status": worst, "checks": results}
