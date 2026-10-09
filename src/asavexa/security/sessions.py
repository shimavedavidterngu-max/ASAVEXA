"""Session hardening on top of the existing bearer-token sessions: idle timeout, a cap on concurrent sessions, a visible
device list that the person can revoke, and a record of whether the session passed MFA. Sessions themselves still live in the
identity tables; this module keeps the security facts about them."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

from .errors import NotFoundError, SessionPolicyError
from .store import DocStore


def _utc():
    return datetime.now(timezone.utc)


@dataclass
class SessionPolicy:
    idle_minutes: int = 30
    max_sessions: int = 5
    touch_every_seconds: int = 60


class SessionGuard:
    def __init__(self, store: DocStore, sessions_repo, now: Callable[[], datetime] = _utc, policy: Optional[SessionPolicy] = None):
        """sessions_repo: the identity SessionRepository (get_by_token_hash / update)."""
        self.store, self.repo, self.now, self.policy = store, sessions_repo, now, policy or SessionPolicy()

    @staticmethod
    def _key(user_id, session_id):
        return f"{user_id}:{session_id}"

    def register(self, session, ip: Optional[str], user_agent: Optional[str], auth_method: str, mfa_verified: bool) -> None:
        now = self.now().isoformat()
        self.store.put("session_meta", self._key(session.user_id, session.id), {
            "session_id": session.id, "user_id": session.user_id, "token_hash": session.token_hash, "created_at": now, "last_seen": now,
            "ip": (ip or "")[:64], "user_agent": (user_agent or "")[:200], "auth_method": auth_method,
            "mfa_verified_at": now if mfa_verified else None, "revoked": False})
        # a cap on concurrent sessions: the oldest beyond the cap are signed out
        live = [m for m in self.list_for_user(session.user_id, include_current=None) if not m["revoked"]]
        live.sort(key=lambda m: m["created_at"])
        for m in live[:-self.policy.max_sessions] if len(live) > self.policy.max_sessions else []:
            self._revoke_meta(m, "session limit reached")

    def meta(self, session) -> dict:
        m = self.store.get("session_meta", self._key(session.user_id, session.id))
        if m is None:   # a session created before this feature existed: treat as password-only, seen when created
            ts = session.created_at.isoformat()
            m = {"session_id": session.id, "user_id": session.user_id, "token_hash": session.token_hash, "created_at": ts, "last_seen": ts,
                 "ip": "", "user_agent": "", "auth_method": "PASSWORD", "mfa_verified_at": None, "revoked": False}
            self.store.put("session_meta", self._key(session.user_id, session.id), m)
        return m

    def check(self, session) -> dict:
        """Called on every request. Signs the session out if it has been idle too long. Returns its security facts."""
        m = self.meta(session)
        now = self.now()
        last = datetime.fromisoformat(m["last_seen"])
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if m.get("revoked"):
            raise SessionPolicyError("This session was signed out. Please log in again.")
        if now - last > timedelta(minutes=self.policy.idle_minutes):
            self._revoke_meta(m, "idle timeout")
            raise SessionPolicyError("You were signed out after being inactive. Please log in again.")
        if (now - last).total_seconds() >= self.policy.touch_every_seconds:
            m["last_seen"] = now.isoformat()
            self.store.put("session_meta", self._key(m["user_id"], m["session_id"]), m)
        return m

    def mark_mfa_verified(self, session) -> None:
        m = self.meta(session)
        m["mfa_verified_at"] = self.now().isoformat()
        self.store.put("session_meta", self._key(m["user_id"], m["session_id"]), m)

    def list_for_user(self, user_id: str, include_current: Optional[str] = None) -> List[dict]:
        out = [m for _, m in self.store.list("session_meta", prefix=user_id + ":")]
        for m in out:
            m["current"] = (include_current == m["session_id"])
        return sorted(out, key=lambda m: m["last_seen"], reverse=True)

    @staticmethod
    def public(m: dict) -> dict:
        """What may be shown to the person (never the stored token fingerprint)."""
        return {k: v for k, v in m.items() if k != "token_hash"}

    def _revoke_meta(self, m: dict, why: str) -> None:
        s = self.repo.get_by_token_hash(m["token_hash"])
        if s is not None and s.revoked_at is None:
            s.revoked_at = self.now()
            self.repo.update(s)
        m["revoked"], m["revoked_reason"] = True, why
        self.store.put("session_meta", self._key(m["user_id"], m["session_id"]), m)

    def revoke(self, user_id: str, session_id: str) -> None:
        m = self.store.get("session_meta", self._key(user_id, session_id))
        if m is None:
            raise NotFoundError("That session was not found.")
        self._revoke_meta(m, "revoked by the user")

    def revoke_others(self, user_id: str, keep_session_id: str) -> int:
        n = 0
        for m in self.list_for_user(user_id):
            if m["session_id"] != keep_session_id and not m["revoked"]:
                self._revoke_meta(m, "revoked by the user"); n += 1
        return n

    def revoke_all(self, user_id: str, reason: str = "revoked by an administrator") -> int:
        n = 0
        for m in self.list_for_user(user_id):
            if not m["revoked"]:
                self._revoke_meta(m, reason); n += 1
        return n
