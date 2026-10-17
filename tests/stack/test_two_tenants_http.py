"""Stage 1, REAL-STACK tests: the real FastAPI app, over HTTP (TestClient), on a real PostgreSQL database.

Needs: pip install -r requirements.txt, a THROWAWAY PostgreSQL in DATABASE_URL with `alembic upgrade head` already applied,
and ASAVEXA_STACK_TEST=1. Without those every test here is SKIPPED, loudly, with the reason (it is BLOCKED in the
development sandbox, which cannot install FastAPI/SQLAlchemy). GitHub Actions runs it on every push and pull request.
Safety: refuses to run if DATABASE_URL does not look like a local/CI test database.

What it checks over EVERY route in the running app:
  1. No-token and garbage-token requests never succeed and never crash (apart from the reviewed public routes).
  2. Organisation B's signed-in owner, using organisation A's real identifiers in every path parameter, never receives any of
     A's identifiers or marker text in a successful response, and A's data is unchanged afterwards."""
import os
import re
import sys
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

ENABLED = os.environ.get("ASAVEXA_STACK_TEST") == "1"
URL = os.environ.get("DATABASE_URL", "")
SKIP = "BLOCKED: needs ASAVEXA_STACK_TEST=1, real FastAPI/SQLAlchemy and a throwaway PostgreSQL (runs in GitHub Actions)"


def looks_like_test_db(url):
    host = re.search(r"@([^:/?]+)", url or "")
    return bool(host) and host.group(1) in ("localhost", "127.0.0.1", "postgres") and "onrender.com" not in url


if ENABLED:
    assert looks_like_test_db(URL), "refusing to run: DATABASE_URL is not a local/CI test database"
    from fastapi.testclient import TestClient
    from fastapi.routing import APIRoute
    from asavexa.api.main import app
    import test_stage1_route_security as static

PW = "Stack-Test-Passw0rd"
SKIP_ATTACK = ("/auth/logout", "/security/me/erasure-request", "/security/me/sessions", "/auth/recovery", "/auth/register", "/webhooks/")


def fill(path, value):
    return re.sub(r"\{[^}]+\}", value, path)


@unittest.skipUnless(ENABLED, SKIP)
class RealStack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, raise_server_exceptions=False)
        cls.routes = [(m, r.path) for r in app.routes if isinstance(r, APIRoute) for m in sorted(r.methods or []) if m in ("GET", "POST", "PUT", "PATCH", "DELETE")]

    def signup(self, tag):
        email = f"{tag}-{uuid.uuid4().hex[:8]}@stack-check.com"
        r = self.client.post("/auth/register", json={"email": email, "password": PW, "confirm_password": PW})
        self.assertEqual(r.status_code, 201, r.text)
        r = self.client.post("/auth/login", json={"email": email, "password": PW})
        self.assertEqual(r.status_code, 200, r.text)
        token, user = r.json()["token"], r.json()["user"]["id"]
        h = {"Authorization": f"Bearer {token}"}
        org = self.client.post("/organisations", json={"name": f"ZXQ-{tag}-ORG-{uuid.uuid4().hex[:6]}"}, headers=h)
        self.assertEqual(org.status_code, 201, org.text)
        org_id = org.json()["id"]
        r = self.client.post("/auth/select-organisation", json={"org_id": org_id}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        return {"h": h, "user": user, "org": org_id, "email": email, "org_name": org.json()["name"]}

    def seed(self, a):
        marker = f"ZXQ-MARKER-{uuid.uuid4().hex}"
        acc = []
        for code, kind in (("1000", "ASSET"), ("4000", "REVENUE")):
            r = self.client.post("/accounts", json={"code": code, "name": f"{marker}-{code}", "type": kind}, headers=a["h"])
            self.assertEqual(r.status_code, 201, r.text); acc.append(r.json()["id"])
        r = self.client.post("/periods", json={"name": "P1", "start_date": "2026-01-01", "end_date": "2026-01-31"}, headers=a["h"])
        self.assertEqual(r.status_code, 201, r.text); period = r.json()["id"]
        r = self.client.post("/journals", json={"date": "2026-01-05", "description": marker, "currency": "USD",
                                                 "lines": [{"account_id": acc[0], "debit_amount": "10.00"}, {"account_id": acc[1], "credit_amount": "10.00"}]}, headers=a["h"])
        self.assertEqual(r.status_code, 201, r.text); journal = r.json()["id"]
        a.update(marker=marker, ids=[a["org"], a["user"], *acc, period, journal], journal=journal)

    def snapshot(self, a):
        out = {}
        for p in ("/accounts", "/periods", "/journals", f"/organisations/{a['org']}/members", f"/journals/{a['journal']}/audit-trail"):
            r = self.client.get(p, headers=a["h"]); out[p] = (r.status_code, r.json() if r.status_code == 200 else None)
        return out

    # 1 ---------------------------------------------------------------------------------------------------------------
    def test_1_no_route_works_without_a_valid_token(self):
        public = set(static.PUBLIC)
        bad, rejected = [], 0
        for method, path in self.routes:
            if f"{method} {path}" in public:
                continue
            for headers in ({}, {"Authorization": "Bearer not-a-real-token"}):
                r = self.client.request(method, fill(path, "x"), headers=headers, json={} if method != "GET" else None)
                if r.status_code in (401, 403):
                    rejected += 1
                elif r.status_code < 300 or r.status_code >= 500:
                    bad.append(f"{method} {path} -> {r.status_code}")
        self.assertEqual(bad, [], "a protected route answered without a valid token, or crashed")
        self.assertGreater(rejected, 400)

    def test_1b_every_route_the_static_audit_saw_is_really_in_the_app(self):
        live = {f"{m} {p}" for m, p in self.routes}
        static_keys = {static.ri.key(r) for r in static.ROWS if r["file"] != "main.py"}
        self.assertEqual(static_keys - live, set(), "a route the static audit saw is not in the running app")

    # 2 ---------------------------------------------------------------------------------------------------------------
    def test_2_organisation_b_cannot_reach_organisation_a_through_any_route(self):
        a, b = self.signup("A"), self.signup("B")
        self.seed(a)
        before = self.snapshot(a)
        leaks, writes_ok, attempts = [], [], 0
        needles = a["ids"] + [a["marker"], a["org_name"], a["email"]]
        for method, path in self.routes:
            if any(path.startswith(s) for s in SKIP_ATTACK):
                continue
            if not re.search(r"\{[^}]+\}", path) and method == "GET":
                value_sets = [None]                       # list endpoints: B must see only B's data
            else:
                value_sets = a["ids"]
            for v in value_sets:
                url = fill(path, v) if v else path
                r = self.client.request(method, url, headers=b["h"], json={} if method != "GET" else None)
                attempts += 1
                if r.status_code < 300:
                    if any(n in r.text for n in needles):
                        leaks.append(f"{method} {url} -> {r.status_code} contained organisation A's data")
                    elif method != "GET" and v:
                        writes_ok.append(f"{method} {url} -> {r.status_code}")
        self.assertEqual(leaks, [], "CROSS-TENANT LEAK")
        self.assertEqual(self.snapshot(a), before, "organisation A's data changed because of organisation B's requests")
        me = self.client.get("/auth/me", headers=b["h"])
        self.assertEqual(me.status_code, 200, "B's own session died during the run, so later attacks were not really tried")
        self.assertGreater(attempts, 500)
        print(f"\n[two-tenant HTTP] attempts={attempts} leaks=0 successful_B_writes_by_A_id={len(writes_ok)}")
        self.assertEqual(writes_ok, [], "a write by B using A's identifier succeeded (A's data looked unchanged, but this must be refused)")

    def test_3_b_sees_only_its_own_lists(self):
        a, b = self.signup("A2"), self.signup("B2")
        self.seed(a)
        for p in ("/accounts", "/periods", "/journals", "/organisations/mine"):
            r = self.client.get(p, headers=b["h"])
            self.assertEqual(r.status_code, 200, p)
            for n in a["ids"] + [a["marker"]]:
                self.assertNotIn(n, r.text, f"{p} shows organisation A's data to B")


if __name__ == "__main__":
    unittest.main()
