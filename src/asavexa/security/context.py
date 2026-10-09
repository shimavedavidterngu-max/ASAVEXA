"""SecurityContext: puts the security pieces together for one request. The API layer stays thin: it builds one of these and calls
its methods. Everything here runs against the same small interfaces the tests use."""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from ..audit.models import AuditEvent
from ..identity.domain.errors import AsavexaIdentityError
from . import auditchain
from .alerts import AlertService
from .blobs import BlobService
from .errors import KeysNotConfiguredError, MfaError, MfaLockedError, MfaRequiredError, NotFoundError, OidcError, SecurityError, SessionPolicyError
from .governance import ResidencyService, SettingsService, VendorRegister
from .mfa import MfaService
from .monitoring import HealthChecker
from .oidc import OidcService
from .privacy import PrivacyService
from .retention import RetentionService
from .sessions import SessionGuard, SessionPolicy
from .store import DocStore


def _utc():
    return datetime.now(timezone.utc)


class SecurityContext:
    def __init__(self, identity, audit, store: DocStore, keys=None, objects=None, oidc_cfg=None, now: Callable[[], datetime] = _utc,
                 commit: Callable[[], None] = lambda: None, policy: Optional[SessionPolicy] = None, database_region: str = "unspecified",
                 notifier=None, oidc_http=None):
        self.identity, self.audit, self.store, self.keys, self.objects, self.oidc_cfg = identity, audit, store, keys, objects, oidc_cfg
        self.now, self.commit, self.database_region, self.notifier, self.oidc_http = now, commit, database_region, notifier, oidc_http or {}
        self.guard = SessionGuard(store, identity.sessions, now=now, policy=policy)
        self.settings = SettingsService(store, now)
        self.vendors = VendorRegister(store, now)
        self.residency = ResidencyService(self.settings, self.vendors)
        self.alerts = AlertService(store, now, notifier=notifier)
        self.blobs = BlobService(store, objects, keys, residency=self.residency, now=now) if (keys is not None and objects is not None) else None
        self.retention = RetentionService(store, self.blobs, now)
        self._mfa = MfaService(store, keys, now=lambda: now()) if keys is not None else None
        self.privacy = PrivacyService(identity, self._mfa, self.guard, audit, store, now)

    # ----------------------------------------------------------------- helpers
    @property
    def mfa(self) -> MfaService:
        if self._mfa is None:
            raise KeysNotConfiguredError("Multi-factor sign-in needs the platform's encryption keys, which are not set up yet "
                                         "(ASAVEXA_KEYS). Ask the person who runs the platform to add them.")
        return self._mfa

    def log(self, action: str, actor: str, entity_id: str, org_id: Optional[str] = None, entity_type: str = "User", **kw) -> None:
        self.audit.record(AuditEvent(id=str(uuid.uuid4()), org_id=org_id, entity_type=entity_type, entity_id=entity_id, action=action, actor=actor,
                                     timestamp=self.now(), **kw))

    def _persist_and_raise(self):
        """A refused attempt must still be recorded: commit what was logged before the error is raised (the request rolls back otherwise)."""
        self.commit()

    # ----------------------------------------------------------------- sign-in
    def login(self, email: str, password: str, ip: Optional[str], user_agent: Optional[str]) -> dict:
        try:
            user = self.identity.verify_credentials(email, password)
        except AsavexaIdentityError:
            self._persist_and_raise()
            raise
        if self._mfa is not None and self._mfa.is_enabled(user.id):
            return {"mfa_required": True, "challenge": self._mfa.issue_challenge(user.id)}
        return self._open_session(user, "PASSWORD", False, ip, user_agent)

    def login_with_mfa(self, challenge: str, code: str, ip: Optional[str], user_agent: Optional[str]) -> dict:
        try:
            uid = self.mfa.redeem_challenge(challenge, code)
        except MfaLockedError:
            self.commit(); raise
        except MfaError:
            uid = self._uid_from_challenge(challenge)
            if uid:
                self.log("MFA_FAILED", uid, uid, reason="wrong sign-in code")
                # lock events are logged once, when the factor locks
                if (self.store.get("mfa", uid) or {}).get("locked_until"):
                    self.log("MFA_LOCKED", uid, uid, reason="too many wrong codes")
            self.commit()
            raise
        user = self.identity.users.get(uid)
        if user is None or not user.is_active:
            raise MfaError("This account is not available.")
        return self._open_session(user, "PASSWORD+MFA", True, ip, user_agent)

    def _uid_from_challenge(self, challenge: str) -> Optional[str]:
        from .crypto import open_text
        import json
        try:
            return json.loads(open_text(self.keys, challenge, "mfa-challenge"))["u"]
        except Exception:
            return None

    def _open_session(self, user, method: str, mfa_verified: bool, ip, ua) -> dict:
        session, raw = self.identity.issue_session(user)
        self.guard.register(session, ip, ua, method, mfa_verified)
        return {"user": user, "token": raw, "mfa_verified": mfa_verified, "mfa_required": False}

    # OIDC
    def oidc(self) -> OidcService:
        if self.oidc_cfg is None:
            raise OidcError("Single sign-on is not set up for this platform.")
        if self.keys is None:
            raise KeysNotConfiguredError("Single sign-on needs the platform's encryption keys (ASAVEXA_KEYS).")
        return OidcService(self.oidc_cfg, self.keys, self.store, self.identity.users, **self.oidc_http)

    def oidc_login(self, code: str, state: str, binding: str, ip, ua) -> dict:
        try:
            r = self.oidc().finish(code, state, binding)
        except OidcError as e:
            self.commit(); raise
        user = r["user"]
        if r["mfa_by_provider"]:
            out = self._open_session(user, "OIDC", True, ip, ua)
        elif self._mfa is not None and self._mfa.is_enabled(user.id):
            return {"mfa_required": True, "challenge": self._mfa.issue_challenge(user.id)}
        else:
            out = self._open_session(user, "OIDC", False, ip, ua)
        self.log("LOGIN_OIDC", user.id, user.id, reason="signed in with single sign-on")
        return out

    # ----------------------------------------------------------------- per-request checks
    def check_session(self, session) -> dict:
        try:
            return self.guard.check(session)
        except SessionPolicyError:
            self.commit()          # the idle sign-out must persist even though this request is refused
            raise

    def gate_org(self, session, org_id: str) -> None:
        """An organisation can require everyone to have passed MFA this session."""
        if self.settings.get(org_id)["require_mfa"] and not self.guard.meta(session).get("mfa_verified_at"):
            enrolled = self._mfa is not None and self._mfa.is_enabled(session.user_id)
            raise MfaRequiredError("This organisation requires multi-factor sign-in. " +
                                   ("Sign out and sign in again with your authenticator code." if enrolled else "Set up multi-factor authentication under Security, then sign in again."))

    # ----------------------------------------------------------------- MFA management
    def mfa_begin(self, user_id: str) -> dict:
        u = self.identity.users.get(user_id)
        return self.mfa.begin_enrolment(user_id, u.email)

    def mfa_confirm(self, user_id: str, code: str, session) -> dict:
        r = self.mfa.confirm_enrolment(user_id, code)
        u = self.identity.users.get(user_id)
        self.identity.users.update(replace(u, mfa_enabled=True))
        self.guard.mark_mfa_verified(session)
        self.log("MFA_ENABLED", user_id, user_id)
        return r

    def mfa_disable(self, user_id: str, code: str, org_ids=()) -> None:
        try:
            for org in org_ids:
                if self.settings.get(org)["require_mfa"]:
                    raise MfaRequiredError("An organisation you belong to requires multi-factor sign-in, so it cannot be turned off.")
            self.mfa.disable(user_id, code)
        except (MfaError, MfaLockedError, MfaRequiredError):
            self.commit(); raise
        u = self.identity.users.get(user_id)
        self.identity.users.update(replace(u, mfa_enabled=False))
        self.log("MFA_DISABLED", user_id, user_id, reason="turned off by the account holder")

    # ----------------------------------------------------------------- evidence files
    def require_blobs(self) -> BlobService:
        if self.blobs is None:
            raise KeysNotConfiguredError("Encrypted file storage is not switched on (it needs ASAVEXA_KEYS).")
        return self.blobs

    # ----------------------------------------------------------------- audit chain
    def verify_audit(self, org_id: str) -> dict:
        if self.keys is None:
            return {"scope": org_id, "ok": None, "enabled": False, "note": "The tamper-evident chain is not running because encryption keys are not configured."}
        r = auditchain.verify_chain(self.audit, self.store, self.keys, org_id)
        r["enabled"] = True
        if not r["ok"]:
            self.log("AUDIT_CHAIN_FAILED", "system", org_id, org_id=org_id, entity_type="Organisation", reason=f"{r['problem_count']} problem(s) found")
            self.commit()
        return r

    # ----------------------------------------------------------------- alerts
    def refresh_alerts(self, org_id: str, member_ids, member_emails) -> dict:
        evs = list(self.audit.list_for_org(org_id))
        for who in list(member_ids) + list(member_emails):
            evs.extend(self.audit.list_for_actor(who))
        seen, uniq = set(), []
        for e in evs:
            if e.id not in seen:
                seen.add(e.id); uniq.append(e)
        return self.alerts.refresh(org_id, uniq)

    # ----------------------------------------------------------------- overview
    def health(self) -> dict:
        h = HealthChecker()
        h.add("database", lambda: ("reachable" if self.identity.organisations.list_all() is not None else "?"))
        h.add("encryption keys", lambda: (f"{len(self.keys.key_ids())} key(s), current {self.keys.current_key_id}" if self.keys else (_ for _ in ()).throw(RuntimeError("not configured"))), critical=False)
        if self.objects is not None:
            def probe():
                k = f"system/probe/{uuid.uuid4().hex}"
                self.objects.put(k, b"ok")
                try:
                    if self.objects.get(k) != b"ok":
                        raise RuntimeError("read-back mismatch")
                finally:
                    self.objects.delete(k)
                return f"{self.objects.name} writable"
            h.add("file storage", probe)
        return h.run()

    def backup_status(self, max_age_hours: int = 26) -> dict:
        """Reads the marker that scripts/backup.py leaves in object storage. If nothing reports in, it says so rather than guessing."""
        if self.objects is None:
            return {"known": False, "detail": "File storage is off, so backup reports cannot be seen here. Check the backup job's own log."}
        try:
            import json as _json
            m = _json.loads(self.objects.get("system/backups/latest.json"))
        except Exception:
            return {"known": False, "detail": "No backup has reported in yet. Run scripts/backup.py (see the disaster-recovery runbook)."}
        hours = (self.now() - datetime.fromisoformat(m["created_at"])).total_seconds() / 3600
        return {"known": True, "ok": hours <= max_age_hours, "latest": m["name"], "age_hours": round(hours, 1), "key_id": m.get("key_id"),
                "detail": f"Latest backup is {hours:.1f} hours old." + ("" if hours <= max_age_hours else " That is older than expected.")}

    def overview(self, org_id: str, member_ids) -> dict:
        s = self.settings.get(org_id)
        mfa_on = sum(1 for m in member_ids if self._mfa is not None and self._mfa.is_enabled(m)) if self._mfa else 0
        return {
            "encryption": {"configured": self.keys is not None, "current_key": self.keys.current_key_id if self.keys else None,
                           "keys": self.keys.key_ids() if self.keys else [], "keys_in_use": self.blobs.keys_in_use(org_id) if self.blobs else {}},
            "storage": {"enabled": self.blobs is not None, "backend": getattr(self.objects, "name", None), "region": getattr(self.objects, "data_region", None)},
            "audit_chain": {"enabled": self.keys is not None, "head": (self.store.get("audit_head", org_id) or {}).get("seq", 0)},
            "mfa": {"members": len(list(member_ids)), "with_mfa": mfa_on, "required": s["require_mfa"], "available": self._mfa is not None},
            "sso": {"configured": self.oidc_cfg is not None, "issuer": self.oidc_cfg.issuer if self.oidc_cfg else None},
            "residency": {"allowed_regions": s["allowed_regions"], "database_region": self.database_region},
            "retention": self.retention.policy(org_id),
            "holds": len(self.retention.holds(org_id, active_only=True)),
            "alerts_open": len(self.alerts.list(org_id, status="OPEN")),
            "vendors_overdue": sum(1 for v in self.vendors.list(org_id) if v["review_overdue"]),
            "backups": self.backup_status(),
            "session_policy": {"idle_minutes": self.guard.policy.idle_minutes, "max_sessions": self.guard.policy.max_sessions},
        }
