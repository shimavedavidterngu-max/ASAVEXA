"""Projects and grants: award, budget lines, entries, exact totals, different-person review, flags, setting, isolation, audit, permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from fractions import Fraction

from analysis_fixture import ORG, OTHER, World
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, PROJ_APPROVE, PROJ_PREPARE, ROLE_PERMISSIONS
from asavexa.projects.errors import ProjectsError, ProjectsForbiddenError, ProjectsNotFoundError, ProjectsStateError
from asavexa.projects.service import ProjectsService, refnum

U1, U2, U3, U4 = "user-1", "user-2", "user-3", "user-4"   # U1 and U2 prepare, U3 and U4 approve


class Clock:
    def __init__(self): self.d = date(2026, 3, 31)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


F = lambda s: Fraction(Decimal(s))
fr = lambda s: Fraction(Decimal(s))


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = ProjectsService(self.w.store, None, log=lambda *a: self.events.append(a), now=self.clock)

    def proj(self, actor=U1, **kw):
        d = dict(title="Clean water programme", funder_ref="FND-2026-01", currency="NGN", award="1,000,000.00", period_start="2026-01-01", period_end="2026-12-31"); d.update(kw)
        return self.svc.pj_create_project(ORG, d, actor)

    def budget(self, p, actor=U1, **kw):
        d = dict(category="Personnel", amount="600000.00"); d.update(kw)
        return self.svc.pj_add_budget(ORG, p["id"], d, actor)

    def ready(self, actor=U1):
        p = self.proj(actor); self.budget(p, actor); return self.budget(p, actor, category="Equipment", amount="250000.50")

    def submit(self, p, actor=U1, note=""): return self.svc.pj_submit(ORG, p["id"], {"note": note}, actor)

    def active(self, preparer=U1, approver=U3):
        p = self.ready(preparer); self.submit(p, preparer); return self.svc.pj_approve_project(ORG, p["id"], {}, approver)

    def entry(self, p, actor=U1, **kw):
        d = dict(entry_type="EXPENSE", budget_no=1, amount="200000.25", entry_date="2026-02-10", description="Field staff salaries for February"); d.update(kw)
        return self.svc.pj_add_entry(ORG, p["id"], d, actor)

    def decide(self, p, no, actor=U3): return self.svc.pj_approve_entry(ORG, p["id"], no, {}, actor)


class Budget(Base):
    def test_award_and_unallocated_against_an_oracle(self):
        p = self.ready(); a = fr("1000000.00"); b = fr("600000.00") + fr("250000.50")
        self.assertEqual((p["budgeted"], p["unallocated"], p["award"]), ("850000.50", "149999.50", "1000000.00"))
        self.assertEqual((fr(p["budgeted"]), fr(p["unallocated"])), (b, a - b))
        self.assertEqual(p["ref"], "PJ-001"); self.assertEqual(p["status"], "DRAFT")

    def test_budget_cannot_exceed_award(self):
        p = self.ready()
        with self.assertRaises(ProjectsError): self.budget(p, category="Travel", amount="150000.00")        # 850000.50 + 150000 > 1000000
        self.budget(p, category="Travel", amount="149999.50")                                              # exactly the award
        with self.assertRaises(ProjectsError): self.budget(p, category="Other", amount="0.01")

    def test_validation(self):
        p = self.proj()
        for bad in ({"category": "x"}, {"category": ""}, {"amount": "0"}, {"amount": 100.5}, {"amount": "1.234"}, {"amount": "１２３"}, {"amount": "1,00"}, {"amount": "-5"}, {"amount": None}, {"amount": True}):
            with self.assertRaises(ProjectsError, msg=bad): self.budget(p, **bad)
        self.assertEqual(self.budget(p, amount="1,500.50")["budget"][0]["amount"], "1500.50")

    def test_duplicate_category_refused_but_reusable_after_removal(self):
        p = self.proj(); self.budget(p)
        with self.assertRaises(ProjectsStateError): self.budget(p, category="  personnel ")
        self.svc.pj_remove_budget(ORG, p["id"], 1, "Entered the wrong amount", U1)
        p = self.budget(p, amount="500000.00"); self.assertEqual([(l["no"], l["status"]) for l in p["budget"]], [(1, "REMOVED"), (2, "ACTIVE")]); self.assertEqual(p["budgeted"], "500000.00")

    def test_remove(self):
        p = self.ready()
        for bad in ("x", "", None, True):
            with self.assertRaises(ProjectsError): self.svc.pj_remove_budget(ORG, p["id"], bad, "A good reason", U1)
        with self.assertRaises(ProjectsError): self.svc.pj_remove_budget(ORG, p["id"], 1, "abc", U1)
        with self.assertRaises(ProjectsNotFoundError): self.svc.pj_remove_budget(ORG, p["id"], 9, "A good reason", U1)
        p = self.svc.pj_remove_budget(ORG, p["id"], 1, "Wrong category", U1); self.assertEqual((p["budgeted"], p["budget"][0]["removed_note"]), ("250000.50", "Wrong category"))
        with self.assertRaises(ProjectsStateError): self.svc.pj_remove_budget(ORG, p["id"], 1, "Wrong category", U1)

    def test_line_limit(self):
        p = self.proj(award="100000.00")
        for i in range(50): self.budget(p, category=f"Cat {i:02d}", amount="1.00")
        with self.assertRaises(ProjectsStateError): self.budget(p, category="One more", amount="1.00")


class Projects(Base):
    def test_create_validation_and_numbering(self):
        for bad in ({"title": "ab"}, {"funder_ref": "x"}, {"currency": "NG"}, {"currency": "N1G"}, {"award": "0"}, {"award": 5.5}, {"award": "1.234"}, {"period_start": "2026-02-30"}, {"period_end": "2025-12-31"}, {"period_end": "2037-01-02"}, {"period_start": "01/01/2026"}):
            with self.assertRaises(ProjectsError, msg=bad): self.proj(**bad)
        p = self.proj(currency="ngn"); self.assertEqual((p["ref"], p["currency"]), ("PJ-001", "NGN")); self.assertEqual(self.proj()["ref"], "PJ-002")
        self.assertEqual(self.proj(period_end="2036-12-31", period_start="2026-12-31")["ref"], "PJ-003")      # a long future project is fine, only the length is limited

    def test_withdraw(self):
        p = self.proj()
        with self.assertRaises(ProjectsError): self.svc.pj_withdraw_project(ORG, p["id"], "short", U1)
        p = self.svc.pj_withdraw_project(ORG, p["id"], "Started for the wrong funder", U1); self.assertEqual(p["status"], "WITHDRAWN")
        with self.assertRaises(ProjectsStateError): self.budget(p)

    def test_list_carries_totals_not_lines(self):
        self.ready(); row = self.svc.pj_list_projects(ORG)[0]
        self.assertEqual((row["budget"], row["entries"], row["budgeted"]), ([], [], "850000.50"))
        self.assertEqual(len(self.svc.pj_list_projects(ORG, "DRAFT")), 1); self.assertEqual(self.svc.pj_list_projects(ORG, "ACTIVE"), [])


class Review(Base):
    def test_submit_needs_a_budget_line(self):
        p = self.proj()
        with self.assertRaises(ProjectsStateError): self.submit(p)
        self.budget(p); self.svc.pj_remove_budget(ORG, p["id"], 1, "Removed in error", U1)
        with self.assertRaises(ProjectsStateError): self.submit(p)
        self.budget(p, category="Other"); self.assertEqual(self.submit(p, note="Please review the budget")["status"], "SUBMITTED")
        with self.assertRaises(ProjectsError): self.submit(self.proj(), note="short")

    def test_approve_and_return_by_a_different_person(self):
        p = self.ready(); self.submit(p)
        with self.assertRaises(ProjectsForbiddenError): self.svc.pj_approve_project(ORG, p["id"], {}, U1)
        with self.assertRaises(ProjectsForbiddenError): self.svc.pj_return_project(ORG, p["id"], "Returning my own project", U1)
        with self.assertRaises(ProjectsError): self.svc.pj_return_project(ORG, p["id"], "short", U3)
        r = self.svc.pj_return_project(ORG, p["id"], "Personnel looks too high", U3); self.assertEqual((r["status"], r["decision_note"]), ("RETURNED", "Personnel looks too high"))
        with self.assertRaises(ProjectsStateError): self.svc.pj_approve_project(ORG, p["id"], {}, U3)
        self.budget(p, category="Travel", amount="10.00"); self.submit(p)
        with self.assertRaises(ProjectsError): self.svc.pj_approve_project(ORG, p["id"], {"note": "short"}, U3)
        a = self.svc.pj_approve_project(ORG, p["id"], {"note": "Checked against the agreement"}, U4); self.assertEqual((a["status"], a["decided_by"]), ("ACTIVE", U4))
        for f in (lambda: self.svc.pj_approve_project(ORG, p["id"], {}, U3), lambda: self.budget(p), lambda: self.svc.pj_withdraw_project(ORG, p["id"], "Trying to withdraw it", U1)):
            with self.assertRaises(ProjectsStateError): f()

    def test_a_returned_project_can_be_edited_and_resubmitted_by_anyone_who_prepares(self):
        p = self.ready(); self.submit(p); self.svc.pj_return_project(ORG, p["id"], "Please add a travel line", U3)
        self.budget(p, actor=U2, category="Travel", amount="1000.00"); self.assertEqual(self.submit(p, U2)["submitted_by"], U2)

    def test_owner_two_person_rule(self):
        p = self.ready(); self.submit(p, U3)         # an approver-capable person submitted it; they still cannot decide it
        with self.assertRaises(ProjectsForbiddenError): self.svc.pj_approve_project(ORG, p["id"], {}, U3)
        self.assertEqual(self.svc.pj_approve_project(ORG, p["id"], {}, U4)["status"], "ACTIVE")


class Entries(Base):
    def test_entries_need_an_open_approved_project(self):
        p = self.ready()
        with self.assertRaises(ProjectsStateError): self.entry(p)
        self.submit(p)
        with self.assertRaises(ProjectsStateError): self.entry(p)

    def test_exact_totals_against_an_oracle(self):
        p = self.active()
        self.entry(p); self.entry(p, amount="150000.10", entry_date="2026-03-01"); self.entry(p, budget_no=2, amount="250000.51"); self.entry(p, entry_type="RECEIPT", budget_no=None, amount="400000.00", description="First instalment from the funder")
        for n in (1, 2, 3, 4): p = self.decide(p, n)
        spent = fr("200000.25") + fr("150000.10") + fr("250000.51"); award = fr("1000000.00")
        self.assertEqual((p["spent"], p["remaining"], p["received"], p["still_to_receive"]), ("600000.86", "399999.14", "400000.00", "600000.00"))
        self.assertEqual((fr(p["spent"]), fr(p["remaining"])), (spent, award - spent)); self.assertEqual(p["spent_pct"], "60.00")
        l1, l2 = p["budget"]; self.assertEqual((l1["spent"], l1["remaining"], l1["over_budget"]), ("350000.35", "249999.65", False)); self.assertEqual((l2["spent"], l2["remaining"], l2["over_budget"]), ("250000.51", "-0.01", True))
        self.assertEqual(p["over_budget_lines"], 1)

    def test_only_approved_entries_count(self):
        p = self.active(); self.entry(p); self.entry(p, amount="5.00"); self.entry(p, amount="7.00")
        p = self.decide(p, 1); p = self.svc.pj_reject_entry(ORG, p["id"], 2, "Duplicate of the first entry", U3)
        self.assertEqual((p["spent"], p["pending_entries"]), ("200000.25", 1)); self.assertEqual([e["status"] for e in p["entries"]], ["APPROVED", "REJECTED", "PROPOSED"])

    def test_validation(self):
        p = self.active()
        for bad in ({"entry_type": "x"}, {"entry_type": None}, {"amount": "0"}, {"amount": 5.5}, {"amount": "1.234"}, {"entry_date": "2026-02-30"}, {"entry_date": "2025-12-31"}, {"entry_date": "2027-01-01"}, {"entry_date": "2026-04-05"},
                    {"description": "ab"}, {"budget_no": None}, {"budget_no": 9}, {"budget_no": "x"}, {"budget_no": True}, {"budget_no": 0}):
            with self.assertRaises(ProjectsError, msg=bad): self.entry(p, **bad)
        with self.assertRaises(ProjectsError): self.entry(p, entry_type="RECEIPT", budget_no=1)
        self.assertEqual(self.entry(p, entry_type="expense", entry_date="2026-04-01")["entries"][0]["entry_date"], "2026-04-01")    # one day of leeway
        self.assertEqual(self.entry(p, entry_type="RECEIPT", budget_no=None, amount="1,000.00")["entries"][1]["entry_type"], "RECEIPT")

    def test_removed_budget_line_is_refused(self):
        p = self.active()
        # budget lines cannot be removed once active, so check the draft rule through a direct removal first
        q = self.proj(); self.budget(q); self.budget(q, category="Equipment", amount="1.00"); self.svc.pj_remove_budget(ORG, q["id"], 1, "Wrong category entered", U1)
        self.submit(q); q = self.svc.pj_approve_project(ORG, q["id"], {}, U3)
        with self.assertRaises(ProjectsError): self.entry(q, budget_no=1)
        self.assertEqual(self.entry(q, budget_no=2, amount="1.00")["entries"][0]["budget_no"], 2)

    def test_different_person_decides(self):
        p = self.active(); self.entry(p)
        with self.assertRaises(ProjectsForbiddenError): self.svc.pj_approve_entry(ORG, p["id"], 1, {}, U1)
        with self.assertRaises(ProjectsForbiddenError): self.svc.pj_reject_entry(ORG, p["id"], 1, "Rejecting my own entry", U1)
        with self.assertRaises(ProjectsError): self.svc.pj_reject_entry(ORG, p["id"], 1, "short", U3)
        with self.assertRaises(ProjectsError): self.svc.pj_approve_entry(ORG, p["id"], 1, {"note": "short"}, U3)
        for bad in ("x", None, True):
            with self.assertRaises(ProjectsError): self.svc.pj_approve_entry(ORG, p["id"], bad, {}, U3)
        with self.assertRaises(ProjectsNotFoundError): self.svc.pj_approve_entry(ORG, p["id"], 9, {}, U3)
        self.decide(p, 1)
        with self.assertRaises(ProjectsStateError): self.decide(p, 1)
        with self.assertRaises(ProjectsStateError): self.svc.pj_reject_entry(ORG, p["id"], 1, "Trying to reject it later", U4)

    def test_close(self):
        p = self.active(); self.entry(p)
        with self.assertRaises(ProjectsStateError): self.svc.pj_close_project(ORG, p["id"], "Project finished on time", U3)      # a proposed entry is still open
        self.decide(p, 1)
        with self.assertRaises(ProjectsError): self.svc.pj_close_project(ORG, p["id"], "short", U3)
        c = self.svc.pj_close_project(ORG, p["id"], "Project finished on time", U3); self.assertEqual((c["status"], c["closed_by"], c["close_note"]), ("CLOSED", U3, "Project finished on time"))
        for f in (lambda: self.entry(p), lambda: self.svc.pj_close_project(ORG, p["id"], "Closing it again later", U3)):
            with self.assertRaises(ProjectsStateError): f()
        self.assertEqual(c["spent"], "200000.25")

    def test_entry_limit(self):
        p = self.active(); key = f"{ORG}:{p['id']}"; raw = self.w.store.get("pj_project", key, for_update=True)
        raw["entries"] = [{"no": i, "entry_type": "RECEIPT", "budget_no": None, "amount": "1.00", "entry_date": "2026-02-01", "description": "filler", "status": "REJECTED", "proposed_by": U1} for i in range(1, 2001)]
        self.w.store.put("pj_project", key, raw, org_id=ORG)
        with self.assertRaises(ProjectsStateError): self.entry(p)


class Flags(Base):
    def test_ending_soon_and_ended_still_open(self):
        p = self.active(); self.assertFalse(p["ending_soon"])
        q = self.proj(period_start="2026-03-01", period_end="2026-04-15"); self.budget(q); self.submit(q); q = self.svc.pj_approve_project(ORG, q["id"], {}, U3)
        self.assertEqual((q["days_left"], q["ending_soon"], q["ended_still_open"]), (15, True, False))
        self.svc.pj_set_setting(ORG, {"ending_soon_days": 10}, U3); self.assertFalse(self.svc.pj_get_project(ORG, q["id"])["ending_soon"])
        self.clock.d = date(2026, 4, 16); q = self.svc.pj_get_project(ORG, q["id"]); self.assertEqual((q["days_left"], q["ending_soon"], q["ended_still_open"]), (-1, False, True))
        kinds = [a["kind"] for a in self.svc.pj_overview(ORG)["attention"]]; self.assertIn("ENDED_STILL_OPEN", kinds); self.assertNotIn("ENDING_SOON", kinds)
        self.svc.pj_close_project(ORG, q["id"], "Ended and closed on time", U3); self.assertFalse(self.svc.pj_get_project(ORG, q["id"])["ended_still_open"])

    def test_receipts_above_award_are_flagged_not_blocked(self):
        p = self.active(); self.entry(p, entry_type="RECEIPT", budget_no=None, amount="1000000.01"); p = self.decide(p, 1)
        self.assertTrue(p["received_above_award"]); self.assertEqual(p["still_to_receive"], "-0.01")
        self.assertIn("RECEIVED_ABOVE_AWARD", [a["kind"] for a in self.svc.pj_overview(ORG)["attention"]])

    def test_setting(self):
        self.assertEqual(self.svc.pj_get_setting(ORG)["ending_soon_days"], 30)
        for bad in (0, 366, "x", 1.5, True, "-1"):
            with self.assertRaises(ProjectsError, msg=bad): self.svc.pj_set_setting(ORG, {"ending_soon_days": bad}, U3)
        self.assertEqual(self.svc.pj_set_setting(ORG, {"ending_soon_days": "45"}, U3)["ending_soon_days"], 45)


class Overview(Base):
    def test_totals_per_currency_and_attention(self):
        p = self.active(); self.entry(p); self.decide(p, 1); self.entry(p, amount="9.00")
        e = self.proj(currency="USD", award="5000.00"); self.budget(e, category="Supplies", amount="5000.00"); self.submit(e); self.svc.pj_approve_project(ORG, e["id"], {}, U3)
        d = self.proj(); self.budget(d); self.submit(d); self.proj(); o = self.svc.pj_overview(ORG)
        self.assertEqual(o["counts"], {"draft": 1, "submitted": 1, "active": 2, "returned": 0, "closed": 0, "withdrawn": 0})
        ngn = next(t for t in o["totals"] if t["currency"] == "NGN"); usd = next(t for t in o["totals"] if t["currency"] == "USD")
        self.assertEqual((ngn["projects"], ngn["award"], ngn["spent"], ngn["remaining"], ngn["budgeted"]), (1, "1000000.00", "200000.25", "799999.75", "850000.50")); self.assertEqual((usd["award"], usd["spent"]), ("5000.00", "0.00"))
        kinds = {a["kind"]: a["count"] for a in o["attention"]}; self.assertEqual((kinds["PROJECTS_TO_REVIEW"], kinds["ENTRIES_TO_REVIEW"]), (1, 1))

    def test_empty(self):
        o = self.svc.pj_overview(ORG); self.assertEqual((o["totals"], o["attention"]), ([], [])); self.assertEqual(sum(o["counts"].values()), 0)


class Isolation(Base):
    def test_other_company(self):
        p = self.active(); self.entry(p)
        self.assertEqual(self.svc.pj_list_projects(OTHER), [])
        for f in (lambda: self.svc.pj_get_project(OTHER, p["id"]), lambda: self.budget_other(p), lambda: self.svc.pj_approve_entry(OTHER, p["id"], 1, {}, U3), lambda: self.svc.pj_close_project(OTHER, p["id"], "Closing from elsewhere", U3)):
            with self.assertRaises(ProjectsNotFoundError): f()
        self.assertEqual(self.svc.pj_get_project(ORG, p["id"])["pending_entries"], 1)

    def budget_other(self, p): return self.svc.pj_add_budget(OTHER, p["id"], {"category": "Personnel", "amount": "1.00"}, U1)

    def test_numbering_per_company(self):
        self.proj(); self.assertEqual(self.svc.pj_create_project(OTHER, dict(title="Other programme", funder_ref="OTH-1", currency="NGN", award="10.00", period_start="2026-01-01", period_end="2026-12-31"), U1)["ref"], "PJ-001")


class Audit(Base):
    def test_every_write_logged_without_content(self):
        p = self.ready(); self.svc.pj_remove_budget(ORG, p["id"], 2, "Entered with the wrong figures", U1); self.submit(p, note="Note about Chinedu"); self.svc.pj_return_project(ORG, p["id"], "Personnel looks too high", U3)
        self.budget(p, category="Equipment", amount="250000.50"); self.submit(p); self.svc.pj_approve_project(ORG, p["id"], {"note": "Checked against agreement"}, U3)
        self.entry(p); self.entry(p, amount="5.00"); self.svc.pj_approve_entry(ORG, p["id"], 1, {"note": "Receipt seen by me"}, U3); self.svc.pj_reject_entry(ORG, p["id"], 2, "Duplicate of the first one", U3)
        self.svc.pj_close_project(ORG, p["id"], "Closing after the final audit", U3); w = self.proj(); self.svc.pj_withdraw_project(ORG, w["id"], "Started for the wrong funder", U1); self.svc.pj_set_setting(ORG, {"ending_soon_days": 12}, U3)
        acts = [x[0] for x in self.events]
        for x in ("PROJECTS_PROJECT_CREATED", "PROJECTS_BUDGET_ADDED", "PROJECTS_BUDGET_REMOVED", "PROJECTS_PROJECT_SUBMITTED", "PROJECTS_PROJECT_RETURNED", "PROJECTS_PROJECT_APPROVED", "PROJECTS_ENTRY_PROPOSED", "PROJECTS_ENTRY_APPROVED",
                  "PROJECTS_ENTRY_REJECTED", "PROJECTS_PROJECT_CLOSED", "PROJECTS_PROJECT_WITHDRAWN", "PROJECTS_SETTING_SET"): self.assertIn(x, acts)
        blob = " ".join(str(x) for x in self.events)
        for secret in ("Clean water", "FND-2026", "Personnel", "Equipment", "1000000", "600000", "200000", "Field staff", "Chinedu", "wrong figures", "too high", "Checked against", "Receipt seen", "Duplicate of", "final audit", "wrong funder"): self.assertNotIn(secret, blob)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(ProjectsError): self.proj(title="ab")
        p = self.proj(); n = len(self.events)
        with self.assertRaises(ProjectsError): self.budget(p, amount="0")
        with self.assertRaises(ProjectsStateError): self.submit(p)
        with self.assertRaises(ProjectsStateError): self.entry(p)
        self.assertEqual(len(self.events), n)


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, PROJ_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, PROJ_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, PROJ_PREPARE) or has(r, PROJ_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if PROJ_PREPARE in perms or PROJ_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "projects.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "PROJ_PREPARE", "_approve": "PROJ_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_setting", "approve", "return_project", "close_project", "approve_entry", "reject_entry"}
        prepare = {"create_project", "add_budget", "remove_budget", "submit", "withdraw", "add_entry"}
        for n in approve: self.assertEqual(g[n][1], {"PROJ_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"PROJ_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no projects guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
