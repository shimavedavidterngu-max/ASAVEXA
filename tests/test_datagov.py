"""Data governance: assets, reviews, access grants, exact dates, different-person decisions, flags, settings, isolation, audit, permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timedelta, timezone

from analysis_fixture import ORG, OTHER, World
from asavexa.datagov.errors import DatagovError, DatagovForbiddenError, DatagovNotFoundError, DatagovStateError
from asavexa.datagov.service import DatagovService, add_months
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, DG_APPROVE, DG_PREPARE, ROLE_PERMISSIONS

U1, U2, U3, U4 = "user-1", "user-2", "user-3", "user-4"   # U1 and U2 prepare, U3 and U4 approve


class Clock:
    def __init__(self): self.d = date(2026, 3, 31)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = DatagovService(self.w.store, None, log=lambda *a: self.events.append(a), now=self.clock)

    def asset(self, actor=U1, **kw):
        d = dict(name="Customer ledger extracts", owner_ref="FIN-LEAD", classification="CONFIDENTIAL", personal_data="YES", retention_months=84, review_every_months=6, description="Monthly extracts of the customer ledger"); d.update(kw)
        return self.svc.dg_add_asset(ORG, d, actor)

    def approved(self, actor=U1, approver=U3, **kw):
        a = self.asset(actor, **kw); return self.svc.dg_approve_asset(ORG, a["id"], {}, approver)

    def grant(self, a, actor=U1, **kw):
        d = dict(person_ref="STAFF-017", access_level="READ", purpose="Prepare the quarterly reconciliation", starts_on="2026-04-01", expires_on="2026-09-30"); d.update(kw)
        return self.svc.dg_add_grant(ORG, a["id"], d, actor)

    def review(self, a, actor=U1, **kw):
        d = dict(review_date="2026-03-31", outcome="Owner confirmed the data is still needed"); d.update(kw)
        return self.svc.dg_add_review(ORG, a["id"], d, actor)


class Months(unittest.TestCase):
    def test_add_months_against_known_dates(self):
        for d, n, want in (("2026-01-31", 1, "2026-02-28"), ("2024-01-31", 1, "2024-02-29"), ("2026-03-31", 6, "2026-09-30"), ("2026-11-15", 3, "2027-02-15"), ("2026-12-31", 12, "2027-12-31"), ("2026-05-31", 9, "2027-02-28"), ("2026-03-31", 60, "2031-03-31")):
            self.assertEqual(add_months(date.fromisoformat(d), n).isoformat(), want, (d, n))


class Assets(Base):
    def test_validation_and_numbering(self):
        for bad in ({"name": "ab"}, {"owner_ref": "x"}, {"classification": "SECRET"}, {"classification": None}, {"personal_data": "MAYBE"}, {"retention_months": 0}, {"retention_months": 1201}, {"retention_months": 1.5}, {"retention_months": True}, {"retention_months": "x"},
                    {"review_every_months": 0}, {"review_every_months": 61}, {"description": "short"}):
            with self.assertRaises(DatagovError, msg=bad): self.asset(**bad)
        a = self.asset(classification="restricted", personal_data="yes"); self.assertEqual((a["ref"], a["classification"], a["personal_data"], a["status"]), ("DA-001", "RESTRICTED", "YES", "PROPOSED")); self.assertEqual(self.asset()["ref"], "DA-002")

    def test_approve_reject_different_person(self):
        a = self.asset()
        with self.assertRaises(DatagovForbiddenError): self.svc.dg_approve_asset(ORG, a["id"], {}, U1)
        with self.assertRaises(DatagovForbiddenError): self.svc.dg_reject_asset(ORG, a["id"], "Rejecting my own asset", U1)
        with self.assertRaises(DatagovError): self.svc.dg_reject_asset(ORG, a["id"], "short", U3)
        with self.assertRaises(DatagovError): self.svc.dg_approve_asset(ORG, a["id"], {"note": "short"}, U3)
        r = self.svc.dg_approve_asset(ORG, a["id"], {"note": "Checked against the register"}, U3); self.assertEqual((r["status"], r["approved_on"], r["next_review_due"]), ("APPROVED", "2026-03-31", "2026-09-30"))
        for f in (lambda: self.svc.dg_approve_asset(ORG, a["id"], {}, U4), lambda: self.svc.dg_reject_asset(ORG, a["id"], "Trying to reject it later", U4)):
            with self.assertRaises(DatagovStateError): f()
        b = self.asset(); self.assertEqual(self.svc.dg_reject_asset(ORG, b["id"], "Duplicate of an existing asset", U3)["status"], "REJECTED")
        with self.assertRaises(DatagovStateError): self.review(b)

    def test_nothing_can_be_added_to_an_unapproved_asset(self):
        a = self.asset()
        for f in (lambda: self.review(a), lambda: self.grant(a)):
            with self.assertRaises(DatagovStateError): f()

    def test_list_carries_summary_only(self):
        a = self.approved(); self.grant(a); row = self.svc.dg_list_assets(ORG)[0]; self.assertEqual((row["grants"], row["reviews"], row["history"]), ([], [], [])); self.assertEqual(row["pending_grants"], 1)
        self.assertEqual(len(self.svc.dg_list_assets(ORG, "APPROVED")), 1); self.assertEqual(self.svc.dg_list_assets(ORG, "PROPOSED"), [])

    def test_retire(self):
        a = self.approved(); g = self.grant(a)
        with self.assertRaises(DatagovStateError): self.svc.dg_retire_asset(ORG, a["id"], "No longer held by us", U3)       # a grant is waiting
        self.svc.dg_approve_grant(ORG, a["id"], 1, {}, U3)
        with self.assertRaises(DatagovStateError): self.svc.dg_retire_asset(ORG, a["id"], "No longer held by us", U3)       # an active grant
        self.svc.dg_revoke_grant(ORG, a["id"], 1, "Access no longer needed", U3); self.review(a)
        with self.assertRaises(DatagovStateError): self.svc.dg_retire_asset(ORG, a["id"], "No longer held by us", U3)       # a review is waiting
        self.svc.dg_confirm_review(ORG, a["id"], 1, {}, U3)
        with self.assertRaises(DatagovError): self.svc.dg_retire_asset(ORG, a["id"], "short", U3)
        r = self.svc.dg_retire_asset(ORG, a["id"], "No longer held by us", U3); self.assertEqual((r["status"], r["next_review_due"]), ("RETIRED", None))
        for f in (lambda: self.review(a), lambda: self.grant(a, person_ref="STAFF-099")):
            with self.assertRaises(DatagovStateError): f()


class Reviews(Base):
    def test_next_review_moves_with_confirmed_reviews_only(self):
        a = self.approved(); self.assertEqual(a["next_review_due"], "2026-09-30")
        self.clock.d = date(2026, 5, 31); a = self.review(a, review_date="2026-05-31"); self.assertEqual(a["next_review_due"], "2026-09-30")      # proposed does not count yet
        a = self.svc.dg_confirm_review(ORG, a["id"], 1, {}, U3); self.assertEqual(a["next_review_due"], "2026-11-30")
        a = self.review(a, review_date="2026-05-20"); a = self.svc.dg_reject_review(ORG, a["id"], 2, "Wrong asset was reviewed", U3); self.assertEqual(a["next_review_due"], "2026-11-30")     # rejected does not count
        a = self.review(a, review_date="2026-05-20"); a = self.svc.dg_confirm_review(ORG, a["id"], 3, {}, U4); self.assertEqual(a["next_review_due"], "2026-11-30")                        # an earlier review does not move it back

    def test_overdue(self):
        a = self.approved(); self.assertFalse(a["review_overdue"]); self.clock.d = date(2026, 9, 30); self.assertFalse(self.svc.dg_get_asset(ORG, a["id"])["review_overdue"])
        self.clock.d = date(2026, 10, 1); self.assertTrue(self.svc.dg_get_asset(ORG, a["id"])["review_overdue"]); self.assertIn("REVIEWS_OVERDUE", [x["kind"] for x in self.svc.dg_overview(ORG)["attention"]])

    def test_validation(self):
        a = self.approved()
        for bad in ({"review_date": "2026-02-30"}, {"review_date": "2026-04-05"}, {"review_date": "2026-03-30"}, {"review_date": None}, {"outcome": "short"}):
            with self.assertRaises(DatagovError, msg=bad): self.review(a, **bad)
        self.assertEqual(self.review(a, review_date="2026-04-01")["reviews"][0]["review_date"], "2026-04-01")                  # one day of leeway

    def test_different_person_decides(self):
        a = self.approved(); self.review(a)
        with self.assertRaises(DatagovForbiddenError): self.svc.dg_confirm_review(ORG, a["id"], 1, {}, U1)
        with self.assertRaises(DatagovForbiddenError): self.svc.dg_reject_review(ORG, a["id"], 1, "Rejecting my own review", U1)
        with self.assertRaises(DatagovError): self.svc.dg_reject_review(ORG, a["id"], 1, "short", U3)
        for bad in ("x", None, True):
            with self.assertRaises(DatagovError): self.svc.dg_confirm_review(ORG, a["id"], bad, {}, U3)
        with self.assertRaises(DatagovNotFoundError): self.svc.dg_confirm_review(ORG, a["id"], 9, {}, U3)
        self.svc.dg_confirm_review(ORG, a["id"], 1, {}, U3)
        with self.assertRaises(DatagovStateError): self.svc.dg_confirm_review(ORG, a["id"], 1, {}, U4)


class Grants(Base):
    def test_validation_and_limits(self):
        a = self.approved(); r = self.approved(classification="RESTRICTED")
        for bad in ({"person_ref": "x"}, {"access_level": "ADMIN"}, {"purpose": "short"}, {"starts_on": "2026-02-30"}, {"expires_on": None}, {"expires_on": "2026-03-31", "starts_on": "2026-04-01"}, {"expires_on": "2026-03-30", "starts_on": "2026-03-01"}, {"starts_on": "2026-04-01", "expires_on": "2029-04-02"}):
            with self.assertRaises(DatagovError, msg=bad): self.grant(a, **bad)
        self.assertEqual(self.grant(a, starts_on="2026-04-01", expires_on="2029-03-31")["grants"][0]["expires_on"], "2029-03-31")                                  # exactly 1095 days
        with self.assertRaises(DatagovError): self.grant(r, starts_on="2026-04-01", expires_on="2027-04-03")                                                       # 367 days on a restricted asset
        self.assertEqual(self.grant(r, starts_on="2026-04-01", expires_on="2027-04-02")["grants"][0]["no"], 1)                                                     # 366 days is allowed

    def test_duplicate_access_refused_until_revoked(self):
        a = self.approved(); self.grant(a)
        with self.assertRaises(DatagovStateError): self.grant(a, person_ref=" staff-017 ")
        self.grant(a, access_level="WRITE"); self.svc.dg_approve_grant(ORG, a["id"], 1, {}, U3)
        with self.assertRaises(DatagovStateError): self.grant(a)
        self.svc.dg_revoke_grant(ORG, a["id"], 1, "Moved to another team", U3); self.assertEqual(self.grant(a)["grants"][-1]["no"], 3)

    def test_decisions_by_a_different_person(self):
        a = self.approved(); self.grant(a)
        with self.assertRaises(DatagovForbiddenError): self.svc.dg_approve_grant(ORG, a["id"], 1, {}, U1)
        with self.assertRaises(DatagovForbiddenError): self.svc.dg_reject_grant(ORG, a["id"], 1, "Rejecting my own request", U1)
        with self.assertRaises(DatagovError): self.svc.dg_reject_grant(ORG, a["id"], 1, "short", U3)
        with self.assertRaises(DatagovStateError): self.svc.dg_revoke_grant(ORG, a["id"], 1, "Not approved yet at all", U3)
        g = self.svc.dg_approve_grant(ORG, a["id"], 1, {"note": "Purpose is documented"}, U3)["grants"][0]; self.assertEqual((g["status"], g["state"]), ("APPROVED", "NOT_YET_ACTIVE"))
        with self.assertRaises(DatagovStateError): self.svc.dg_approve_grant(ORG, a["id"], 1, {}, U4)
        with self.assertRaises(DatagovError): self.svc.dg_revoke_grant(ORG, a["id"], 1, "short", U3)
        r = self.svc.dg_revoke_grant(ORG, a["id"], 1, "Moved to another team", U4)["grants"][0]; self.assertEqual((r["state"], r["revoke_note"]), ("REVOKED", "Moved to another team"))
        with self.assertRaises(DatagovStateError): self.svc.dg_revoke_grant(ORG, a["id"], 1, "Revoking it a second time", U3)

    def test_states_follow_the_dates(self):
        a = self.approved(); self.grant(a, starts_on="2026-03-31", expires_on="2026-04-20"); self.svc.dg_approve_grant(ORG, a["id"], 1, {}, U3)
        g = lambda: self.svc.dg_get_asset(ORG, a["id"])["grants"][0]
        self.assertEqual((g()["state"], g()["days_to_expiry"]), ("EXPIRING", 20))                       # inside the 30-day window
        self.svc.dg_set_setting(ORG, {"expiry_warning_days": 10}, U3); self.assertEqual(g()["state"], "ACTIVE")
        self.clock.d = date(2026, 4, 10); self.assertEqual(g()["state"], "EXPIRING"); self.clock.d = date(2026, 4, 20); self.assertEqual((g()["state"], g()["days_to_expiry"]), ("EXPIRING", 0))
        self.clock.d = date(2026, 4, 21); self.assertEqual((g()["state"], g()["days_to_expiry"]), ("EXPIRED", -1)); self.assertEqual(self.svc.dg_get_asset(ORG, a["id"])["active_grants"], 0)
        self.svc.dg_revoke_grant(ORG, a["id"], 1, "Tidying an expired grant up", U3)                    # an expired grant can still be revoked on the record

    def test_an_expired_proposal_cannot_be_approved(self):
        a = self.approved(); self.grant(a, starts_on="2026-03-31", expires_on="2026-04-05"); self.clock.d = date(2026, 4, 6)
        with self.assertRaises(DatagovStateError): self.svc.dg_approve_grant(ORG, a["id"], 1, {}, U3)
        self.assertEqual(self.svc.dg_reject_grant(ORG, a["id"], 1, "The dates have already passed", U3)["grants"][0]["status"], "REJECTED")
        with self.assertRaises(DatagovError): self.grant(a, starts_on="2026-03-01", expires_on="2026-04-05")      # already past


class Flags(Base):
    def test_too_many_grants_on_a_restricted_asset(self):
        r = self.approved(classification="RESTRICTED"); self.svc.dg_set_setting(ORG, {"max_restricted_grants": 2}, U3)
        for i in range(3):
            self.grant(r, person_ref=f"STAFF-0{i}", starts_on="2026-03-31", expires_on="2026-12-31"); self.svc.dg_approve_grant(ORG, r["id"], i + 1, {}, U3)
        v = self.svc.dg_get_asset(ORG, r["id"]); self.assertEqual((v["active_grants"], v["too_many_grants"]), (3, True)); self.assertIn("TOO_MANY_GRANTS", [x["kind"] for x in self.svc.dg_overview(ORG)["attention"]])
        n = self.approved(classification="INTERNAL")                                                  # only RESTRICTED assets are flagged
        for i in range(3): self.grant(n, person_ref=f"STAFF-1{i}", starts_on="2026-03-31", expires_on="2026-12-31"); self.svc.dg_approve_grant(ORG, n["id"], i + 1, {}, U3)
        self.assertFalse(self.svc.dg_get_asset(ORG, n["id"])["too_many_grants"])

    def test_settings(self):
        s = self.svc.dg_get_setting(ORG); self.assertEqual((s["expiry_warning_days"], s["max_restricted_grants"]), (30, 5))
        for f, bad in (("expiry_warning_days", 0), ("expiry_warning_days", 366), ("expiry_warning_days", "x"), ("expiry_warning_days", 1.5), ("expiry_warning_days", True), ("max_restricted_grants", 0), ("max_restricted_grants", 1001)):
            with self.assertRaises(DatagovError, msg=(f, bad)): self.svc.dg_set_setting(ORG, {f: bad}, U3)
        s = self.svc.dg_set_setting(ORG, {"expiry_warning_days": "45"}, U3); self.assertEqual((s["expiry_warning_days"], s["max_restricted_grants"]), (45, 5))


class Overview(Base):
    def test_counts_and_percentages(self):
        a = self.approved(); b = self.approved(classification="RESTRICTED", personal_data="NO"); c = self.approved(classification="PUBLIC", personal_data="NO"); self.asset(); d = self.asset(); self.svc.dg_reject_asset(ORG, d["id"], "Duplicate of an existing asset", U3)
        self.clock.d = date(2026, 10, 1)                                                              # all three approved assets are now overdue
        self.review(a, review_date="2026-10-01"); self.svc.dg_confirm_review(ORG, a["id"], 1, {}, U3)    # a is reviewed again
        o = self.svc.dg_overview(ORG)
        self.assertEqual(o["counts"], {"proposed": 1, "approved": 3, "rejected": 1, "retired": 0}); self.assertEqual(o["by_classification"], {"PUBLIC": 1, "INTERNAL": 0, "CONFIDENTIAL": 1, "RESTRICTED": 1}); self.assertEqual(o["personal_data_assets"], 1)
        self.assertEqual(o["reviews_on_time_pct"], "33.33")                                           # 1 of 3 reviewed on time
        kinds = {x["kind"]: x["count"] for x in o["attention"]}; self.assertEqual((kinds["ASSETS_TO_APPROVE"], kinds["REVIEWS_OVERDUE"]), (1, 2))

    def test_empty(self):
        o = self.svc.dg_overview(ORG); self.assertEqual((o["attention"], o["reviews_on_time_pct"], o["active_grants"]), ([], "0.00", 0))


class Isolation(Base):
    def test_other_company(self):
        a = self.approved(); self.grant(a); self.assertEqual(self.svc.dg_list_assets(OTHER), [])
        for f in (lambda: self.svc.dg_get_asset(OTHER, a["id"]), lambda: self.svc.dg_approve_grant(OTHER, a["id"], 1, {}, U3), lambda: self.svc.dg_add_review(OTHER, a["id"], {}, U1), lambda: self.svc.dg_retire_asset(OTHER, a["id"], "Retiring from elsewhere", U3)):
            with self.assertRaises(DatagovNotFoundError): f()
        self.assertEqual(self.svc.dg_add_asset(OTHER, dict(name="Other asset", owner_ref="OPS", classification="PUBLIC", personal_data="NO", retention_months=12, review_every_months=12, description="An asset of another company"), U1)["ref"], "DA-001")


class Audit(Base):
    def test_every_write_logged_without_content(self):
        a = self.approved(); self.review(a, outcome="Owner Chinedu confirmed the data"); self.svc.dg_confirm_review(ORG, a["id"], 1, {"note": "Seen in the register"}, U3); self.grant(a); self.svc.dg_approve_grant(ORG, a["id"], 1, {"note": "Purpose documented"}, U3)
        self.grant(a, person_ref="STAFF-018", purpose="Weekend support cover work"); self.svc.dg_reject_grant(ORG, a["id"], 2, "Not needed for the weekend", U3); self.svc.dg_revoke_grant(ORG, a["id"], 1, "Moved to another team", U3)
        self.review(a, review_date="2026-04-01"); self.svc.dg_reject_review(ORG, a["id"], 2, "Wrong asset was reviewed", U3); self.svc.dg_reject_review(ORG, a["id"], 2, "x" * 12, U3) if False else None
        b = self.asset(); self.svc.dg_reject_asset(ORG, b["id"], "Duplicate of the ledger asset", U3); self.svc.dg_set_setting(ORG, {"expiry_warning_days": 12}, U3)
        c = self.approved(name="Payroll archive"); self.svc.dg_retire_asset(ORG, c["id"], "Archive was destroyed", U3)
        acts = [x[0] for x in self.events]
        for x in ("DATAGOV_ASSET_PROPOSED", "DATAGOV_ASSET_APPROVED", "DATAGOV_ASSET_REJECTED", "DATAGOV_ASSET_RETIRED", "DATAGOV_REVIEW_RECORDED", "DATAGOV_REVIEW_CONFIRMED", "DATAGOV_REVIEW_REJECTED", "DATAGOV_GRANT_PROPOSED", "DATAGOV_GRANT_APPROVED", "DATAGOV_GRANT_REJECTED", "DATAGOV_GRANT_REVOKED", "DATAGOV_SETTING_SET"): self.assertIn(x, acts)
        blob = " ".join(str(x) for x in self.events)
        for secret in ("Customer ledger", "FIN-LEAD", "STAFF-01", "Chinedu", "reconciliation", "Seen in the register", "Purpose documented", "weekend", "Moved to another team", "Wrong asset", "Duplicate of", "Payroll archive", "destroyed"): self.assertNotIn(secret, blob)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(DatagovError): self.asset(name="ab")
        a = self.approved(); n = len(self.events)
        with self.assertRaises(DatagovError): self.grant(a, person_ref="x")
        with self.assertRaises(DatagovForbiddenError): self.svc.dg_approve_asset(ORG, self.asset()["id"], {}, U1)
        n += 1                                                                                          # the one asset proposed above
        self.assertEqual(len(self.events), n)


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, DG_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, DG_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, DG_PREPARE) or has(r, DG_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if DG_PREPARE in perms or DG_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "datagov.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "DG_PREPARE", "_approve": "DG_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_setting", "approve_asset", "reject_asset", "retire_asset", "confirm_review", "reject_review", "approve_grant", "reject_grant", "revoke_grant"}
        prepare = {"add_asset", "add_review", "add_grant"}
        for n in approve: self.assertEqual(g[n][1], {"DG_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"DG_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no data governance guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
