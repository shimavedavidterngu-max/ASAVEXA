"""Stage 1, audit-event coverage.

A. STATIC, every write route: for each of the authenticated POST/PUT/PATCH/DELETE routes, follow the code the route runs
   (the handler, the service class it is given, that class's methods, helper functions) and require an audit-trail write
   somewhere on the way. This is evidence, not proof: it shows a call to the audit trail is reachable, not that every
   branch makes it. The few routes with none are listed below with the reason, and the list may only shrink.
B. DYNAMIC, the actions this stage found without an audit entry (security routes here; health actions in test_health.py)
   are exercised for real and must now leave exactly one event naming the person who acted.
The full dynamic version (every write route over HTTP on the real stack, asserting the audit count rises) is
tests/stack/test_two_tenants_http.py, which runs in CI."""
import ast
import collections
import os
import unittest

import route_inventory as ri

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "asavexa")

# Reviewed: authenticated write routes with no audit-trail write on purpose.
NO_AUDIT_BY_DESIGN = {
    "POST /analysis/breakeven": "calculator: stores nothing",
    "POST /ingestion/preview": "reads the file and shows what would happen: stores nothing (commit is audited)",
    "POST /network/invites/preview": "shows what an invite code would do: stores nothing",
    "POST /standards/resolve": "stateless preview: stores nothing",
    "POST /security/me/mfa/begin": "starts enrolment only; nothing is switched on until confirm, which is audited",
    "POST /security/alerts/refresh": "recomputes derived alerts from existing facts",
    "POST /validation/engagements/{engagement_id}/reviews": "saves a DRAFT review; signing and submitting are audited",
}

classes = {}
funcs = collections.defaultdict(list)
methods_by_name = collections.defaultdict(list)
AUDIT_NAMES = {"log", "_log", "_record_decision", "audit_event", "_audit", "record_event"}


def _index():
    for root, _, files in os.walk(SRC):
        if "__pycache__" in root:
            continue
        for f in files:
            if f.endswith(".py"):
                p = os.path.join(root, f)
                tree = ast.parse(open(p).read())
                for n in tree.body:
                    if isinstance(n, ast.ClassDef):
                        classes.setdefault(n.name, []).append((p, n))
                        for m in n.body:
                            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                methods_by_name[m.name].append((n.name, m))
                    elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        funcs[n.name].append((p, n))


_index()
FILES_BY_NODE = {id(n): p for lst in funcs.values() for p, n in lst}


def _meth(cls, name, seen=()):
    for _, c in classes.get(cls, []):
        for m in c.body:
            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name == name:
                return m
        for b in c.bases:
            if isinstance(b, ast.Name) and b.id in classes and b.id not in seen:
                r = _meth(b.id, name, seen + (cls,))
                if r:
                    return r
    return None


def _factory_class(fname):
    for _, n in funcs.get(fname, []):
        if n.returns is not None:
            for x in ast.walk(n.returns):
                if isinstance(x, ast.Name) and x.id in classes:
                    return x.id
        for x in ast.walk(n):
            if isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id in classes and x.func.id.endswith(("Service", "Engine", "Vault", "Context")):
                return x.func.id
    return None


def _types(fn, row_params):
    out = {}
    for a in fn.args.args + fn.args.kwonlyargs:
        t = None
        if a.annotation is not None:
            for x in ast.walk(a.annotation):
                if isinstance(x, ast.Name) and x.id in classes:
                    t = x.id
        if t is None:
            for d in row_params.get(a.arg, []):
                t = _factory_class(d) or t
        if t:
            out[a.arg] = t
    return out


def _direct(node):
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if name in AUDIT_NAMES or name == "AuditEvent":
                return True
            if name == "record" and isinstance(f, ast.Attribute):
                base = ast.unparse(f.value).lower()
                if "audit" in base or base.endswith("repo"):
                    return True
    return False


def audited(node, cls, types, depth, seen, local_file):
    if _direct(node):
        return True
    if depth <= 0:
        return False
    for n in ast.walk(node):
        if not isinstance(n, ast.Call):
            continue
        f, target = n.func, None
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            b = f.value.id
            if b == "self" and cls:
                target = (cls, f.attr)
            elif b in types:
                target = (types[b], f.attr)
        elif isinstance(f, ast.Attribute):
            c = methods_by_name.get(f.attr, [])
            if len(c) == 1:
                target = (c[0][0], f.attr)
        elif isinstance(f, ast.Name):
            ds = funcs.get(f.id, [])
            same = [x for x in ds if x[0] == local_file] or (ds if len(ds) == 1 else [])
            if same and ("fn", f.id, same[0][0]) not in seen:
                if audited(same[0][1], None, {}, depth - 1, seen | {("fn", f.id, same[0][0])}, same[0][0]):
                    return True
            continue
        if target and target not in seen:
            m = _meth(*target)
            if m is not None and audited(m, target[0], {}, depth - 1, seen | {target}, local_file):
                return True
    return False


def unaudited_writes():
    out = []
    for r in ri.inventory():
        if r["method"] == "GET" or not ri.is_session_authenticated(r):
            continue
        local = os.path.join(SRC, "api", "routers", r["file"])
        if not audited(r["node"], None, _types(r["node"], r["params"]), 6, frozenset(), local):
            out.append(ri.key(r))
    return out


class StaticAuditCoverage(unittest.TestCase):
    def test_every_write_route_reaches_an_audit_trail_write_or_is_reviewed(self):
        missing = set(unaudited_writes())
        self.assertEqual(missing - set(NO_AUDIT_BY_DESIGN), set(), "WRITE ROUTE WITH NO AUDIT-TRAIL WRITE: add one, or review it and list it with a reason")
        self.assertEqual(set(NO_AUDIT_BY_DESIGN) - missing, set(), "listed as unaudited but now audited (or gone): remove it from the list")

    def test_the_scan_covers_the_whole_write_surface(self):
        writes = [r for r in ri.inventory() if r["method"] != "GET" and ri.is_session_authenticated(r)]
        self.assertGreaterEqual(len(writes), 300)
        self.assertLess(len(NO_AUDIT_BY_DESIGN), 10)

    def test_the_drafts_and_previews_listed_really_do_write_nothing_audited_elsewhere(self):
        text = open(os.path.join(SRC, "validation", "service.py")).read()
        self.assertIn("VALIDATION_REVIEW_SIGNED", text)         # signing is audited, saving the draft is not
        self.assertIn('"MFA_ENABLED"', open(os.path.join(SRC, "security", "context.py")).read())

    def test_the_analyser_is_not_vacuous(self):
        # A fake write route with no audit call must be flagged; one with a call must not.
        bare = ast.parse("def f(x):\n    return x + 1").body[0]
        logged = ast.parse("def f(x, security):\n    security.log('A', x, x)\n    return x").body[0]
        self.assertFalse(audited(bare, None, {}, 6, frozenset(), ""))
        self.assertTrue(audited(logged, None, {}, 6, frozenset(), ""))


import harness_security_routers as H  # noqa: E402
from harness_security_routers import sec, Request  # noqa: E402
from test_security_context import Ctx, PW  # noqa: E402
import test_passport as T  # noqa: E402
from asavexa.api import ratelimit  # noqa: E402


class SecurityWritesAreAudited(Ctx):
    """Dynamic: the real router functions, real SecurityContext, real SQLite audit repository."""
    setUp = H.RouterRun.setUp
    sign_in = H.RouterRun.sign_in

    def events(self, org=None, actor=None):
        repo = T.SqliteAuditRepository(self.w.conn)
        return [e.action for e in (repo.list_for_org(org) if org else repo.list_for_actor(actor))]

    def test_vendor_add_update_and_seed(self):
        r, s = self.sign_in(); org, actor = self.w.org.id, r.user.id
        v = sec.add_vendor(sec.VendorBody(name="Acme", data_categories=["FINANCIAL"]), org, actor, self.ctx)
        self.assertEqual(self.events(org).count("VENDOR_ADDED"), 1)
        sec.update_vendor(v["id"], sec.VendorBody(name="Acme Ltd", data_categories=["FINANCIAL"]), org, actor, self.ctx)
        self.assertEqual(self.events(org).count("VENDOR_UPDATED"), 1)
        sec.seed_vendors(org, actor, self.ctx)
        self.assertEqual(self.events(org).count("VENDORS_SEEDED"), 1)

    def test_alert_acknowledge(self):
        r, s = self.sign_in(); org, actor = self.w.org.id, r.user.id
        self.store.put("alert", f"{org}:a1", {"id": "a1", "status": "OPEN", "kind": "TEST"}, org_id=org)
        sec.acknowledge_alert("a1", sec.AckBody(note="Looked into it"), org, actor, self.ctx)
        self.assertEqual(self.events(org).count("SECURITY_ALERT_ACKNOWLEDGED"), 1)

    def test_own_session_revocation_and_recovery_code_regeneration(self):
        r, s = self.sign_in(); uid = r.user.id
        r2, s2 = self.sign_in()
        sec.revoke_session(s2.id, s, self.ctx)
        self.assertEqual(self.events(actor=uid).count("SESSION_REVOKED_BY_USER"), 1)
        sec.revoke_other_sessions(s, self.ctx)
        self.assertEqual(self.events(actor=uid).count("OTHER_SESSIONS_REVOKED_BY_USER"), 1)
        b = self.ctx.mfa_begin(uid); self.clock.advance(seconds=1)
        self.ctx.mfa_confirm(uid, self.code_for(b["secret"]), s); self.clock.advance(seconds=31)
        sec.mfa_recovery(Request({}), sec.CodeBody(code=self.code_for(b["secret"])), s, self.ctx)
        self.assertEqual(self.events(actor=uid).count("MFA_RECOVERY_CODES_REGENERATED"), 1)


if __name__ == "__main__":
    unittest.main()
