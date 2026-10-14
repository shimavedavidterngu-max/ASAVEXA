"""Quality management: nonconformances, corrective actions with effectiveness checks, two-person rules, policy, isolation, audit, permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from analysis_fixture import ORG, OTHER, World
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, QUAL_APPROVE, QUAL_PREPARE, ROLE_PERMISSIONS
from asavexa.quality.errors import QualityError, QualityForbiddenError, QualityNotFoundError, QualityStateError
from asavexa.quality.service import QualityService, refnum

U1, U2, U3, U4 = "user-1", "user-2", "user-3", "user-4"   # U1 raises, U2 prepares too, U3 and U4 approve


class Clock:
    def __init__(self): self.d = date(2026, 2, 15)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


class Vault:
    def get_evidence(self, org, i):
        if org == ORG and i in ("ev1", "ev2"): return SimpleNamespace(id=i, original_filename=f"{i}.pdf", file_hash="h" * 64)
        raise LookupError(i)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = QualityService(self.w.store, Vault(), log=lambda *a: self.events.append(a), now=self.clock)

    def nc(self, actor=U1, analysed=False, **kw):
        d = dict(title="Wrong batch label on shipment", description="A shipment left with the label of a different batch", source="CUSTOMER_COMPLAINT", severity="MAJOR", area="Dispatch", occurred_on="2026-02-01", discovered_on="2026-02-03")
        d.update(kw); n = self.svc.ql_raise_nc(ORG, d, actor)
        return self.svc.ql_analyse_nc(ORG, n["id"], dict(root_cause="Labels were printed from the wrong batch file at the end of a shift", containment="Stopped shipping until every label was checked by hand"), U2) if analysed else n

    def action(self, n, actor=U1, **kw):
        d = dict(nc_id=n["id"], kind="CORRECTIVE", description="Labels are now printed only from the scanned batch number", owner_name="Ben Eze", due_on="2026-03-15"); d.update(kw)
        return self.svc.ql_add_action(ORG, d, actor)

    def done(self, a, actor=U2, **kw):
        d = dict(completed_on="2026-02-10", note="The label printer now reads the batch number from the scanner"); d.update(kw); return self.svc.ql_complete_action(ORG, a["id"], d, actor)

    def verified(self, a, result="EFFECTIVE", actor=U3):
        return self.svc.ql_verify_action(ORG, a["id"], dict(result=result, note="Checked twenty shipments and every label matched its batch"), actor)

    def closed_ready(self, severity="MAJOR"):
        n = self.nc(analysed=True, severity=severity); a = self.verified(self.done(self.action(n))); return n, a


class Helpers(unittest.TestCase):
    def test_refnum(self): self.assertEqual(sorted([{"ref": "NC-010"}, {"ref": "NC-002"}], key=refnum)[0]["ref"], "NC-002"); self.assertEqual(refnum({"ref": "x"}), 0)


class Policy(Base):
    def test_defaults_set_and_validation(self):
        self.assertEqual(self.svc.ql_get_policy(ORG)["verify_days"], 30)
        self.assertEqual(self.svc.ql_set_policy(ORG, {"verify_days": 14}, U3)["verify_days"], 14)
        for bad in ({"verify_days": 6}, {"verify_days": 181}, {"verify_days": "x"}, {"verify_days": True}):
            with self.assertRaises(QualityError, msg=str(bad)): self.svc.ql_set_policy(ORG, bad, U3)


class Ncs(Base):
    def test_raise_and_validation(self):
        n = self.nc(); self.assertEqual((n["ref"], n["status"], n["severity"]), ("NC-001", "RAISED", "MAJOR"))
        for kw in (dict(title="abc"), dict(description="short"), dict(source="MAGIC"), dict(severity="HUGE"), dict(area="x"), dict(occurred_on="2026-02-31"), dict(occurred_on="2026-02-20", discovered_on="2026-02-20"),
                   dict(discovered_on="2026-01-01"), dict(evidence_ids=["nope"])):
            with self.assertRaises(QualityError, msg=str(kw)): self.nc(**kw)
        self.assertEqual(len(self.svc.ql_list_ncs(ORG)), 1); self.assertEqual(self.nc(evidence_ids=["ev1"])["evidence"][0]["file_hash"], "h" * 64)

    def test_refused_requests_burn_no_number(self):
        with self.assertRaises(QualityError): self.nc(title="abc")
        self.assertEqual(self.nc()["ref"], "NC-001")

    def test_analyse_once_with_enough_detail(self):
        n = self.nc()
        for kw in (dict(root_cause="short", containment="Stopped shipping until every label was checked"), dict(root_cause="Labels were printed from the wrong batch file", containment="short")):
            with self.assertRaises(QualityError): self.svc.ql_analyse_nc(ORG, n["id"], kw, U2)
        a = self.svc.ql_analyse_nc(ORG, n["id"], dict(root_cause="Labels were printed from the wrong batch file at shift end", containment="Stopped shipping until every label was checked"), U2); self.assertEqual(a["status"], "ANALYSED")
        with self.assertRaises(QualityStateError): self.svc.ql_analyse_nc(ORG, n["id"], dict(root_cause="Labels were printed from the wrong batch file at shift end", containment="Stopped shipping until every label was checked"), U2)

    def test_void_rules(self):
        n = self.nc()
        with self.assertRaises(QualityForbiddenError): self.svc.ql_void_nc(ORG, n["id"], "Raised against the wrong site", U1)
        with self.assertRaises(QualityError): self.svc.ql_void_nc(ORG, n["id"], "short", U3)
        self.assertEqual(self.svc.ql_void_nc(ORG, n["id"], "Raised against the wrong site", U3)["status"], "VOIDED")
        m = self.nc(analysed=True)
        with self.assertRaises(QualityStateError): self.svc.ql_void_nc(ORG, m["id"], "Raised against the wrong site", U3)

    def test_filters(self):
        self.nc(); self.nc(severity="MINOR"); self.assertEqual(len(self.svc.ql_list_ncs(ORG, severity="MINOR")), 1); self.assertEqual(len(self.svc.ql_list_ncs(ORG, status="CLOSED")), 0)


class Actions(Base):
    def test_only_for_analysed_nonconformances(self):
        n = self.nc()
        with self.assertRaises(QualityStateError): self.action(n)
        with self.assertRaises(QualityNotFoundError): self.svc.ql_add_action(ORG, {"nc_id": "nope"}, U1)

    def test_add_validation(self):
        n = self.nc(analysed=True)
        for kw in (dict(kind="MAGIC"), dict(description="short"), dict(owner_name="A"), dict(due_on="2026-02-31"), dict(due_on="2026-01-01"), dict(due_on="2029-01-01")):
            with self.assertRaises(QualityError, msg=str(kw)): self.action(n, **kw)
        a = self.action(n); self.assertEqual((a["ref"], a["status"], a["nc_ref"]), ("CA-001", "OPEN", "NC-001"))

    def test_complete_rules(self):
        a = self.action(self.nc(analysed=True))
        for kw in (dict(completed_on="2026-02-31"), dict(completed_on="2026-02-20"), dict(completed_on="2026-01-01"), dict(note="short"), dict(evidence_ids=["nope"])):
            with self.assertRaises(QualityError, msg=str(kw)): self.done(a, **kw)
        c = self.done(a, evidence_ids=["ev1"]); self.assertEqual((c["status"], c["completed_by"], c["evidence"][0]["filename"]), ("COMPLETED", U2, "ev1.pdf"))
        with self.assertRaises(QualityStateError): self.done(a)

    def test_effectiveness_check_needs_a_different_person(self):
        a = self.done(self.action(self.nc(analysed=True)))
        with self.assertRaises(QualityForbiddenError): self.verified(a, actor=U2)
        for kw in (dict(result="MAYBE", note="Checked twenty shipments and every label matched"), dict(result="EFFECTIVE", note="short")):
            with self.assertRaises(QualityError): self.svc.ql_verify_action(ORG, a["id"], kw, U3)
        v = self.verified(a); self.assertEqual((v["status"], v["checked_by"], v["result"]), ("VERIFIED", U3, "EFFECTIVE"))
        with self.assertRaises(QualityStateError): self.verified(a)
        b = self.done(self.action(self.nc(analysed=True, title="Another wrong label found")))
        self.assertEqual(self.verified(b, "NOT_EFFECTIVE")["status"], "NOT_EFFECTIVE")

    def test_cannot_check_an_open_action(self):
        a = self.action(self.nc(analysed=True))
        with self.assertRaises(QualityStateError): self.verified(a)

    def test_cancel_rules(self):
        a = self.action(self.nc(analysed=True))
        with self.assertRaises(QualityError): self.svc.ql_cancel_action(ORG, a["id"], "short", U3)
        self.assertEqual(self.svc.ql_cancel_action(ORG, a["id"], "Replaced by a better action", U3)["status"], "CANCELLED")
        b = self.done(self.action(self.nc(analysed=True, title="Another wrong label found")))
        with self.assertRaises(QualityStateError): self.svc.ql_cancel_action(ORG, b["id"], "Replaced by a better action", U3)

    def test_overdue_and_check_overdue_flags(self):
        n = self.nc(analysed=True); a = self.action(n, due_on="2026-02-20"); self.assertFalse(self.svc.ql_get_action(ORG, a["id"])["overdue"])
        self.clock.d = date(2026, 2, 21); self.assertTrue(self.svc.ql_get_action(ORG, a["id"])["overdue"])
        self.done(a, completed_on="2026-02-21"); g = self.svc.ql_get_action(ORG, a["id"]); self.assertFalse(g["overdue"]); self.assertFalse(g["check_overdue"])
        self.clock.d = date(2026, 3, 25); self.assertTrue(self.svc.ql_get_action(ORG, a["id"])["check_overdue"])
        self.svc.ql_set_policy(ORG, {"verify_days": 90}, U3); self.assertFalse(self.svc.ql_get_action(ORG, a["id"])["check_overdue"])

    def test_filters(self):
        n = self.nc(analysed=True); self.action(n); self.assertEqual(len(self.svc.ql_list_actions(ORG, nc_id=n["id"])), 1); self.assertEqual(len(self.svc.ql_list_actions(ORG, status="VERIFIED")), 0)


class Closing(Base):
    def test_close_needs_a_different_person_and_a_verified_action(self):
        n = self.nc(analysed=True)
        with self.assertRaises(QualityStateError): self.svc.ql_close_nc(ORG, n["id"], {"note": "Everything is done now"}, U3)
        a = self.action(n)
        with self.assertRaises(QualityStateError): self.svc.ql_close_nc(ORG, n["id"], {"note": "Everything is done now"}, U3)
        self.done(a)
        with self.assertRaises(QualityStateError): self.svc.ql_close_nc(ORG, n["id"], {"note": "Everything is done now"}, U3)
        self.verified(a)
        with self.assertRaises(QualityForbiddenError): self.svc.ql_close_nc(ORG, n["id"], {"note": "Everything is done now"}, U1)
        with self.assertRaises(QualityError): self.svc.ql_close_nc(ORG, n["id"], {"note": "short"}, U3)
        c = self.svc.ql_close_nc(ORG, n["id"], {"note": "Everything is done now"}, U3); self.assertEqual((c["status"], c["closed_by"], c["closed_on"]), ("CLOSED", U3, "2026-02-15"))
        with self.assertRaises(QualityStateError): self.svc.ql_close_nc(ORG, n["id"], {"note": "Everything is done now"}, U3)
        with self.assertRaises(QualityStateError): self.action(n)

    def test_not_effective_needs_a_later_effective_action(self):
        n = self.nc(analysed=True); a1 = self.verified(self.done(self.action(n)), "NOT_EFFECTIVE")
        self.assertIn("not effective", self.svc.ql_get_nc(ORG, n["id"])["close_problem"])
        with self.assertRaises(QualityStateError): self.svc.ql_close_nc(ORG, n["id"], {"note": "Everything is done now"}, U3)
        a2 = self.action(n, description="Add a second person who checks every label before dispatch"); self.verified(self.done(a2, completed_on="2026-02-12"), actor=U4)
        self.assertIsNone(self.svc.ql_get_nc(ORG, n["id"])["close_problem"]); self.assertEqual(self.svc.ql_close_nc(ORG, n["id"], {"note": "Everything is done now"}, U3)["status"], "CLOSED")

    def test_earlier_effective_action_does_not_hide_a_later_failure(self):
        n = self.nc(analysed=True); self.verified(self.done(self.action(n)))
        self.verified(self.done(self.action(n, description="A second action that turned out not to work")), "NOT_EFFECTIVE")
        with self.assertRaises(QualityStateError): self.svc.ql_close_nc(ORG, n["id"], {"note": "Everything is done now"}, U3)

    def test_minor_may_close_without_action_only_with_a_reason(self):
        n = self.nc(analysed=True, severity="MINOR")
        with self.assertRaises(QualityStateError): self.svc.ql_close_nc(ORG, n["id"], {"note": "Nothing more to do here"}, U3)
        with self.assertRaises(QualityError): self.svc.ql_close_nc(ORG, n["id"], {"note": "Nothing more to do here", "no_action_reason": "short"}, U3)
        c = self.svc.ql_close_nc(ORG, n["id"], {"note": "Nothing more to do here", "no_action_reason": "A one-off typing slip that was corrected the same day"}, U3); self.assertIsNotNone(c["no_action_reason"])
        m = self.nc(analysed=True, severity="MAJOR", title="A major problem found later")
        with self.assertRaises(QualityStateError): self.svc.ql_close_nc(ORG, m["id"], {"note": "Nothing more to do here", "no_action_reason": "A one-off typing slip that was corrected the same day"}, U3)

    def test_cancelled_actions_do_not_count(self):
        n = self.nc(analysed=True, severity="MINOR"); a = self.action(n); self.svc.ql_cancel_action(ORG, a["id"], "Replaced by a better action", U3)
        with self.assertRaises(QualityStateError): self.svc.ql_close_nc(ORG, n["id"], {"note": "Nothing more to do here"}, U3)
        c = self.svc.ql_close_nc(ORG, n["id"], {"note": "Nothing more to do here", "no_action_reason": "A one-off typing slip that was corrected the same day"}, U3); self.assertEqual(c["status"], "CLOSED")

    def test_reason_ignored_when_real_actions_exist(self):
        n = self.nc(analysed=True, severity="MINOR"); self.verified(self.done(self.action(n)))
        c = self.svc.ql_close_nc(ORG, n["id"], {"note": "Everything is done now", "no_action_reason": "A one-off typing slip that was corrected the same day"}, U3); self.assertIsNone(c["no_action_reason"])

    def test_no_deadlock_a_waiting_nonconformance_can_always_move(self):
        n = self.nc(analysed=True); a = self.action(n)
        self.svc.ql_cancel_action(ORG, a["id"], "Replaced by a better action", U3); b = self.action(n, description="A better action than the first one"); self.assertEqual(b["status"], "OPEN")


class Overview(Base):
    def test_attention(self):
        c = self.nc(severity="CRITICAL"); n = self.nc(analysed=True, title="A second wrong label found"); a = self.action(n, due_on="2026-02-10"); m = self.nc(analysed=True, title="A third wrong label found"); self.done(self.action(m))
        o = self.svc.ql_overview(ORG); kinds = {x["kind"]: x["count"] for x in o["attention"]}
        self.assertEqual(kinds["CRITICAL_OPEN"], 1); self.assertEqual(kinds["ACTIONS_OVERDUE"], 1); self.assertEqual(kinds["ACTIONS_TO_CHECK"], 1); self.assertEqual(kinds["NCS_TO_ANALYSE"], 1); self.assertNotIn("NCS_READY_TO_CLOSE", kinds)
        self.assertEqual((o["counts"]["open"], o["counts"]["critical_open"], o["counts"]["major_open"]), (3, 1, 2))
        self.verified(self.svc.ql_get_action(ORG, self.svc.ql_list_actions(ORG, nc_id=m["id"])[0]["id"])); self.assertEqual({x["kind"] for x in self.svc.ql_overview(ORG)["attention"]} & {"NCS_READY_TO_CLOSE"}, {"NCS_READY_TO_CLOSE"})

    def test_not_effective_and_without_actions(self):
        n = self.nc(analysed=True); self.assertEqual({x["kind"]: x["count"] for x in self.svc.ql_overview(ORG)["attention"]}["NCS_WITHOUT_ACTIONS"], 1)
        self.verified(self.done(self.action(n)), "NOT_EFFECTIVE"); kinds = {x["kind"] for x in self.svc.ql_overview(ORG)["attention"]}; self.assertIn("NOT_EFFECTIVE", kinds); self.assertNotIn("NCS_READY_TO_CLOSE", kinds)

    def test_empty_and_options(self):
        o = self.svc.ql_overview(ORG); self.assertEqual((o["attention"], o["counts"]["open"]), ([], 0)); self.assertIn("MAJOR", self.svc.ql_options(ORG)["severities"]); self.assertTrue(o["limitations"])


class Isolation(Base):
    def test_other_company_sees_nothing_and_cannot_touch(self):
        n = self.nc(analysed=True); a = self.done(self.action(n))
        for lst in (self.svc.ql_list_ncs, self.svc.ql_list_actions): self.assertEqual(lst(OTHER), [])
        for f in (lambda: self.svc.ql_get_nc(OTHER, n["id"]), lambda: self.svc.ql_get_action(OTHER, a["id"]), lambda: self.verified_other(a), lambda: self.svc.ql_close_nc(OTHER, n["id"], {"note": "Closing from outside"}, U3),
                  lambda: self.svc.ql_add_action(OTHER, {"nc_id": n["id"]}, U1), lambda: self.svc.ql_analyse_nc(OTHER, n["id"], {}, U2), lambda: self.svc.ql_cancel_action(OTHER, a["id"], "Cancelling from outside", U3)):
            with self.assertRaises(QualityNotFoundError): f()
        self.assertEqual(self.svc.ql_overview(OTHER)["counts"]["open"], 0)

    def verified_other(self, a): return self.svc.ql_verify_action(OTHER, a["id"], dict(result="EFFECTIVE", note="Checked from outside the company"), U3)

    def test_same_titles_allowed_in_each_company(self):
        self.nc(); d = dict(title="Wrong batch label on shipment", description="A shipment left with the label of a different batch", source="OTHER", severity="MINOR", area="Dispatch", occurred_on="2026-02-01", discovered_on="2026-02-03")
        self.assertEqual(self.svc.ql_raise_nc(OTHER, d, U1)["ref"], "NC-001")


class Audit(Base):
    def test_every_write_logged_without_content(self):
        n = self.nc(analysed=True); a = self.action(n); self.svc.ql_set_policy(ORG, {"verify_days": 20}, U3); self.verified(self.done(a)); self.svc.ql_close_nc(ORG, n["id"], {"note": "Everything is done now"}, U3)
        v = self.nc(title="Raised against the wrong site"); self.svc.ql_void_nc(ORG, v["id"], "Raised against the wrong site", U3)
        m = self.nc(analysed=True, title="A fourth wrong label found"); self.svc.ql_cancel_action(ORG, self.action(m)["id"], "Replaced by a better action", U3)
        acts = [x[0] for x in self.events]
        for x in ("QUALITY_NC_RAISED", "QUALITY_NC_ANALYSED", "QUALITY_NC_CLOSED", "QUALITY_NC_VOIDED", "QUALITY_ACTION_ADDED", "QUALITY_ACTION_COMPLETED", "QUALITY_ACTION_VERIFIED", "QUALITY_ACTION_CANCELLED", "QUALITY_POLICY_SET"): self.assertIn(x, acts)
        blob = " ".join(str(x) for x in self.events)
        for secret in ("batch label", "scanned batch", "label printer", "Checked twenty", "Everything is done", "wrong batch file", "Dispatch"): self.assertNotIn(secret, blob)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(QualityError): self.nc(title="abc")
        self.assertEqual(self.events, [])


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, QUAL_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, QUAL_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, QUAL_PREPARE) or has(r, QUAL_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if QUAL_PREPARE in perms or QUAL_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "quality.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "QUAL_PREPARE", "_approve": "QUAL_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_policy", "close_nc", "void_nc", "verify_action", "cancel_action"}
        prepare = {"raise_nc", "analyse_nc", "add_action", "complete_action"}
        for n in approve: self.assertEqual(g[n][1], {"QUAL_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"QUAL_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no quality guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
