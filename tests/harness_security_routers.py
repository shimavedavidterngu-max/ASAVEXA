"""Runs the REAL auth + security + evidence routers' functions with stand-ins for fastapi only (not installable here).
Real pydantic schemas, real SecurityContext, real SQLite repositories."""
import sys, types, json
sys.path.insert(0, "/home/claude/asavexa/src"); sys.path.insert(0, "/home/claude/asavexa/tests")
def mod(name, **attrs):
    m = types.ModuleType(name); m.__dict__.update(attrs); sys.modules[name] = m; return m
class APIRouter:
    def __init__(self, **k): self.k = k
    def _d(self, *a, **k): return lambda f: f
    get = post = put = patch = delete = _d
class HTTPException(Exception):
    def __init__(self, status_code, detail=None, headers=None): self.status_code, self.detail, self.headers = status_code, detail, headers
class Request:
    def __init__(self, headers=None, host="9.9.9.9"):
        self.headers = headers or {}; self.client = types.SimpleNamespace(host=host)
class Response:
    def __init__(self, content=None, media_type=None, headers=None, status_code=200): self.content, self.media_type, self.headers, self.status_code = content, media_type, headers or {}, status_code
class JSONResponse(Response):
    def __init__(self, status_code=200, content=None, **k): super().__init__(content=content, status_code=status_code)
mod("fastapi", APIRouter=APIRouter, Depends=lambda x=None: ("dep", x), HTTPException=HTTPException, Request=Request, Response=Response,
    File=lambda *a, **k: None, Form=lambda *a, **k: None, UploadFile=object)
mod("fastapi.responses", JSONResponse=JSONResponse)
import asavexa, pydantic
pydantic.EmailStr = str   # email-validator is not installable here; only affects this harness
for pkg, path in [("asavexa.api","api"),("asavexa.api.routers","api/routers"),("asavexa.api.schemas","api/schemas")]:
    m = types.ModuleType(pkg); m.__path__ = ["/home/claude/asavexa/src/asavexa/"+path]; sys.modules[pkg] = m
mod("asavexa.api.deps", **{n: (lambda: None) for n in ["get_bearer_token","get_current_actor","get_identity_service","get_security","get_current_org","get_current_session","get_evidence_vault"]},
    require_permission=lambda p: ("perm", p))
import importlib
auth = importlib.import_module("asavexa.api.routers.auth")
sec = importlib.import_module("asavexa.api.routers.security")
ev = importlib.import_module("asavexa.api.routers.evidence")
from asavexa.api import ratelimit

import unittest
from datetime import datetime, timezone
import test_passport as T
from test_security_context import Ctx, PW
from asavexa.security import totp
from asavexa.security.errors import MfaRequiredError, ValidationError, NotFoundError, LegalHoldError, RetentionError
from asavexa.identity.domain.errors import PermissionDeniedError
from asavexa.evidence.services.vault import EvidenceVault


class RouterRun(Ctx):
    def setUp(self):
        self.build(oidc=False)
        ratelimit.LOGIN.limit = 1000
        self.req = Request({"user-agent": "UA", "x-forwarded-for": "5.5.5.5, 6.6.6.6"})

    def sign_in(self):
        r = auth.login(self.req, auth.LoginRequest(email="dara@meridian.test", password=PW), self.ctx)
        s = self.w.identity.validate_session(r.token); return r, s

    def test_login_shape_and_ip(self):
        r, s = self.sign_in()
        self.assertEqual(r.user.email, "dara@meridian.test"); self.assertFalse(r.mfa_required); self.assertTrue(r.token)
        self.assertEqual(self.ctx.guard.meta(s)["ip"], "5.5.5.5")          # first forwarded hop, not the proxy
        self.assertEqual(ratelimit.client_ip(Request({}, host="1.2.3.4")), "1.2.3.4")

    def test_mfa_flow_through_routers(self):
        r, s = self.sign_in()
        b = sec.mfa_begin(self.req, s, self.ctx)
        self.assertIn("secret", b); self.assertIn("otpauth://", b["otpauth_uri"])
        self.clock.advance(seconds=1)
        done = sec.mfa_confirm(self.req, sec.CodeBody(code=self.code_for(b["secret"])), s, self.ctx)
        self.assertEqual(len(done["recovery_codes"]), 10)
        me = sec.my_security(s, self.ctx)
        self.assertTrue(me["mfa"]["enabled"]); self.assertTrue(me["this_session"]["mfa_verified"])
        self.assertNotIn("secret", json.dumps(me)); self.assertNotIn("token_hash", json.dumps(me, default=str))
        r2 = auth.login(self.req, auth.LoginRequest(email="dara@meridian.test", password=PW), self.ctx)
        self.assertTrue(r2.mfa_required); self.assertIsNone(r2.token); self.assertTrue(r2.challenge)
        self.clock.advance(seconds=30)
        r3 = auth.mfa_verify(self.req, auth.MfaVerifyRequest(challenge=r2.challenge, code=self.code_for(b["secret"])), self.ctx)
        self.assertTrue(r3.token); self.assertTrue(r3.mfa_verified)
        # recovery code works instead of a code
        r4 = auth.login(self.req, auth.LoginRequest(email="dara@meridian.test", password=PW), self.ctx)
        r5 = auth.mfa_verify(self.req, auth.MfaVerifyRequest(challenge=r4.challenge, code=done["recovery_codes"][0]), self.ctx)
        self.assertTrue(r5.token)

    def test_rate_limit_returns_429_with_retry_after(self):
        lim = ratelimit.RateLimiter(2, 60); 
        ratelimit.throttle(lim, self.req); ratelimit.throttle(lim, self.req)
        with self.assertRaises(HTTPException) as c:
            ratelimit.throttle(lim, self.req)
        self.assertEqual(c.exception.status_code, 429); self.assertIn("Retry-After", c.exception.headers)

    def test_oidc_config_off_and_start_errors(self):
        self.assertFalse(auth.oidc_config(self.ctx)["enabled"])
        from asavexa.security.errors import OidcError
        with self.assertRaises(OidcError):
            auth.oidc_start(self.req, auth.OidcStartRequest(binding="x" * 20), self.ctx)

    def test_sessions_and_revocation(self):
        r, s = self.sign_in()
        r2, s2 = self.sign_in()
        me = sec.my_security(s, self.ctx)
        self.assertEqual(len(me["sessions"]), 2); self.assertEqual(sum(1 for x in me["sessions"] if x.get("current")), 1)
        self.assertEqual(sec.revoke_other_sessions(s, self.ctx)["revoked"], 1)
        from asavexa.identity.domain.errors import SessionRevokedError
        with self.assertRaises(SessionRevokedError):
            self.w.identity.validate_session(r2.token)

    def test_org_routes(self):
        r, s = self.sign_in()
        org = self.w.org.id; actor = r.user.id
        ov = sec.overview(org, self.w.identity, self.ctx)
        self.assertTrue(ov["encryption"]["configured"])
        out = sec.update_settings(sec.SettingsBody(require_mfa=True, allowed_regions=["eu", "ng"]), org, actor, self.ctx)
        self.assertEqual(out["allowed_regions"], ["EU", "NG"])
        acts = [e.action for e in T.SqliteAuditRepository(self.w.conn).list_for_org(org)]
        self.assertIn("SECURITY_SETTINGS_CHANGED", acts)
        with self.assertRaises(ValidationError):
            sec.update_settings(sec.SettingsBody(allowed_regions=["Mars"]), org, actor, self.ctx)
        self.assertEqual(sec.retention  and sec.set_retention(sec.RetentionBody(evidence_days=3000), org, actor, self.ctx)["days"]["EVIDENCE"], 3000)
        with self.assertRaises(ValidationError):
            sec.set_retention(sec.RetentionBody(evidence_days=100), org, actor, self.ctx)
        v = sec.add_vendor(sec.VendorBody(name="Acme", data_categories=["FINANCIAL"]), org, actor, self.ctx)
        self.assertIn(v["risk_tier"], ("MEDIUM", "HIGH", "CRITICAL")); 
        self.assertEqual(len(sec.seed_vendors(org, actor, self.ctx)), 3)
        self.assertEqual(len(sec.vendors(org, self.ctx)), 4)
        res = sec.residency(org, self.ctx); self.assertFalse(res["compliant"])
        a = sec.refresh_alerts(org, self.w.identity, self.ctx); self.assertIn("alerts", a)
        h = sec.detailed_health(self.ctx); self.assertEqual(h.status_code, 200)
        ver = sec.verify_audit(org, self.ctx); self.assertTrue(ver["ok"])
        m = sec.member_security(org, self.w.identity, self.ctx); self.assertTrue(all("secret" not in json.dumps(x) for x in m))
        rot = sec.rotate_keys(sec.RotateBody(), org, actor, self.ctx); self.assertEqual(rot["failed"], 0)

    def test_privacy_routes(self):
        r, s = self.sign_in()
        exp = sec.export_my_data(r.user.id, self.ctx)
        self.assertNotIn("password_hash", json.dumps(exp)); self.assertNotIn("token_hash", json.dumps(exp)); self.assertNotIn("pbkdf2", json.dumps(exp).lower())
        req = sec.request_erasure(r.user.id, self.ctx); self.assertIn(req["status"], ("PENDING", "COMPLETED"))

    def test_without_keys_everything_says_so(self):
        self.build(keys=False)
        from asavexa.security.errors import KeysNotConfiguredError
        r = auth.login(self.req, auth.LoginRequest(email="dara@meridian.test", password=PW), self.ctx)
        self.assertTrue(r.token)                                 # plain sign-in still works
        s = self.w.identity.validate_session(r.token)
        with self.assertRaises(KeysNotConfiguredError): sec.mfa_begin(self.req, s, self.ctx)
        me = sec.my_security(s, self.ctx); self.assertFalse(me["mfa_available"])
        self.assertFalse(sec.verify_audit(self.w.org.id, self.ctx)["enabled"])
        self.assertFalse(sec.overview(self.w.org.id, self.w.identity, self.ctx)["encryption"]["configured"])

if __name__ == "__main__":
    unittest.main(argv=["x"], verbosity=1)
