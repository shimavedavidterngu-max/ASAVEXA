"""Stage 6: Verified Standards Registry service and router."""
import unittest
from datetime import datetime, timedelta, timezone

from asavexa.security.store import MemoryDocStore
from asavexa.standards.registry import (RegistryError, RegistryForbiddenError, RegistryNotFoundError, RegistryStateError, StandardsRegistry)

ORG, OTHER = "org-1", "org-2"
A, B, C = "alice", "bob", "carol"
T0 = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self): self.t = T0
    def __call__(self): return self.t


def make():
    ck = Clock(); events = []
    return StandardsRegistry(MemoryDocStore(), log=lambda *a, **k: events.append(a), now=ck), ck, events


def src(r, who=A, **kw):
    d = dict(framework="IFRS", title="IFRS Accounting Standards", url="https://www.ifrs.org/issued-standards/", authority="IASB", version="2026-01",
             effective_from="2026-01-01", review_by="2027-01-01", summary="Full IFRS", jurisdiction=None)
    d.update(kw)
    return r.add_source(ORG, who, d["framework"], d["title"], d["url"], d["authority"], d["version"], d["effective_from"], d["review_by"], d["summary"], d["jurisdiction"])


class RegistryTests(unittest.TestCase):
    def test_nothing_is_verified_to_begin_with(self):
        r, _, _ = make()
        cov = r.coverage(ORG)
        self.assertEqual(cov["counts"], {"UNVERIFIED": len(cov["frameworks"])})
        self.assertIn("not legal advice", cov["note"])

    def test_full_lifecycle_and_audit(self):
        r, _, ev = make()
        s = src(r)
        self.assertEqual(s["status"], "DRAFT")
        s = r.submit(ORG, s["id"], A)
        s = r.approve(ORG, s["id"], B, "checked against ifrs.org")
        self.assertEqual((s["status"], s["approved_by"]), ("APPROVED", B))
        v = r.verification(ORG, "IFRS")
        self.assertEqual(v["state"], "VERIFIED"); self.assertEqual(v["source"]["url"], "https://www.ifrs.org/issued-standards/")
        self.assertEqual([e[0] for e in ev], ["STANDARDS_SOURCE_ADDED", "STANDARDS_SOURCE_SUBMITTED", "STANDARDS_SOURCE_APPROVED"])

    def test_adder_and_submitter_cannot_approve(self):
        r, _, _ = make()
        s = src(r, A); r.submit(ORG, s["id"], C)
        for who in (A, C):
            with self.assertRaises(RegistryForbiddenError):
                r.approve(ORG, s["id"], who)
        self.assertEqual(r.get_source(ORG, s["id"])["status"], "UNDER_REVIEW")
        self.assertEqual(r.approve(ORG, s["id"], B)["status"], "APPROVED")

    def test_a_new_approved_version_supersedes_the_old(self):
        r, _, ev = make()
        old = src(r); r.submit(ORG, old["id"], A); r.approve(ORG, old["id"], B)
        new = src(r, version="2027-01", effective_from="2026-06-01", review_by="2028-01-01"); r.submit(ORG, new["id"], A); r.approve(ORG, new["id"], B)
        self.assertEqual(r.get_source(ORG, old["id"])["status"], "SUPERSEDED")
        self.assertEqual(r.get_source(ORG, old["id"])["superseded_by"], new["id"])
        self.assertEqual(r.verification(ORG, "IFRS")["source"]["version"], "2027-01")
        self.assertIn("STANDARDS_SOURCE_SUPERSEDED", [e[0] for e in ev])

    def test_review_overdue_is_flagged_and_stale_sources_cannot_be_approved(self):
        r, ck, _ = make()
        s = src(r, review_by="2026-12-01"); r.submit(ORG, s["id"], A); r.approve(ORG, s["id"], B)
        ck.t = datetime(2026, 12, 2, tzinfo=timezone.utc)
        self.assertEqual(r.verification(ORG, "IFRS")["state"], "REVIEW_OVERDUE")
        old = src(r, version="x", review_by="2026-12-03"); r.submit(ORG, old["id"], A)
        ck.t = datetime(2026, 12, 3, tzinfo=timezone.utc)
        with self.assertRaises(RegistryStateError):
            r.approve(ORG, old["id"], B)

    def test_not_yet_effective(self):
        r, _, _ = make()
        s = src(r, effective_from="2027-01-01", review_by="2028-01-01"); r.submit(ORG, s["id"], A); r.approve(ORG, s["id"], B)
        self.assertEqual(r.verification(ORG, "IFRS")["state"], "NOT_YET_EFFECTIVE")

    def test_jurisdiction_specific_source_wins_and_others_do_not_leak(self):
        r, _, _ = make()
        g = src(r); r.submit(ORG, g["id"], A); r.approve(ORG, g["id"], B)
        ng = src(r, jurisdiction="NG", title="FRC Nigeria", version="ng-1"); r.submit(ORG, ng["id"], A); r.approve(ORG, ng["id"], B)
        self.assertEqual(r.verification(ORG, "IFRS", "NG")["source"]["title"], "FRC Nigeria")
        self.assertEqual(r.verification(ORG, "IFRS", "GH")["source"]["title"], "IFRS Accounting Standards")
        self.assertEqual(r.get_source(ORG, g["id"])["status"], "APPROVED")

    def test_send_back_and_withdraw_need_a_reason(self):
        r, _, _ = make()
        s = src(r); r.submit(ORG, s["id"], A)
        with self.assertRaises(RegistryError):
            r.send_back(ORG, s["id"], B, "")
        self.assertEqual(r.send_back(ORG, s["id"], B, "link is a summary page")["status"], "DRAFT")
        r.submit(ORG, s["id"], A); r.approve(ORG, s["id"], B)
        with self.assertRaises(RegistryError):
            r.withdraw(ORG, s["id"], B, " ")
        self.assertEqual(r.withdraw(ORG, s["id"], B, "standard replaced")["status"], "WITHDRAWN")
        self.assertEqual(r.verification(ORG, "IFRS")["state"], "UNVERIFIED")
        with self.assertRaises(RegistryStateError):
            r.withdraw(ORG, s["id"], B, "again")

    def test_state_machine_rejects_out_of_order_steps(self):
        r, _, _ = make()
        s = src(r)
        with self.assertRaises(RegistryStateError): r.approve(ORG, s["id"], B)
        with self.assertRaises(RegistryStateError): r.send_back(ORG, s["id"], B, "x")
        r.submit(ORG, s["id"], A)
        with self.assertRaises(RegistryStateError): r.submit(ORG, s["id"], A)

    def test_input_validation(self):
        r, _, _ = make()
        for bad in (dict(framework="NOPE"), dict(jurisdiction="ZZ"), dict(url="http://insecure.example.org"), dict(url="https://nodot"), dict(url="javascript:alert(1)"),
                    dict(url="https://a b.example.org"), dict(title=" "), dict(authority=""), dict(version=""), dict(effective_from="soon"), dict(review_by="2025-01-01"),
                    dict(summary="x" * 2001), dict(title="x" * 301)):
            with self.assertRaises(RegistryError, msg=str(bad)):
                src(r, **bad)

    def test_other_organisation_sees_and_touches_nothing(self):
        r, _, _ = make()
        s = src(r); r.submit(ORG, s["id"], A)
        self.assertEqual(r.list_sources(OTHER), [])
        self.assertEqual(r.coverage(OTHER)["counts"], {"UNVERIFIED": len(r.coverage(OTHER)["frameworks"])})
        for call in (lambda: r.get_source(OTHER, s["id"]), lambda: r.approve(OTHER, s["id"], B), lambda: r.submit(OTHER, s["id"], A),
                     lambda: r.send_back(OTHER, s["id"], B, "x"), lambda: r.withdraw(OTHER, s["id"], B, "x")):
            with self.assertRaises(RegistryNotFoundError):
                call()

    def test_filters(self):
        r, _, _ = make()
        a = src(r); src(r, framework="US_GAAP", title="FASB ASC", url="https://asc.fasb.org/")
        self.assertEqual(len(r.list_sources(ORG)), 2)
        self.assertEqual([s["framework"] for s in r.list_sources(ORG, framework="US_GAAP")], ["US_GAAP"])
        self.assertEqual(r.list_sources(ORG, status="APPROVED"), [])


class RouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib
        import harness_security_routers as H
        cls.H = H
        cls.rt = importlib.import_module("asavexa.api.routers.standards_registry")

    def test_endpoints_work_end_to_end_and_errors_are_typed(self):
        rt = self.rt; r, _, _ = make()
        body = rt.SourceBody(framework="IFRS", title="IFRS", url="https://www.ifrs.org/", authority="IASB", version="1", effective_from="2026-01-01", review_by="2027-01-01")
        s = rt.add_source(body, ORG, A, r)
        rt.submit(s["id"], ORG, A, r)
        self.assertEqual(rt.approve(s["id"], rt.NoteBody(note="ok"), ORG, B, r)["status"], "APPROVED")
        self.assertEqual(rt.coverage(None, ORG, r)["counts"]["VERIFIED"], 1)
        self.assertEqual(len(rt.list_sources(None, None, ORG, r)["sources"]), 1)
        with self.assertRaises(RegistryNotFoundError): rt.get_source("nope", ORG, r)
        self.assertEqual(RegistryForbiddenError.status, 403); self.assertEqual(RegistryStateError.status, 409)

    def test_permissions_declared(self):
        import inspect
        src_ = inspect.getsource(self.rt)
        for n in ("AUDIT_READ", "GRC_PREPARE", "GRC_APPROVE"): self.assertIn(n, src_)


if __name__ == "__main__":
    unittest.main()
