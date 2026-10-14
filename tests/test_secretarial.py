"""Company secretarial: meetings and minutes, resolutions, filings register, two-person rules, policy, isolation, audit, permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from analysis_fixture import ORG, OTHER, World
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, ROLE_PERMISSIONS, SEC_APPROVE, SEC_PREPARE
from asavexa.secretarial.errors import SecretarialError, SecretarialForbiddenError, SecretarialNotFoundError, SecretarialStateError
from asavexa.secretarial.service import SecretarialService, refnum

U1, U2, U3, U4 = "user-1", "user-2", "user-3", "user-4"   # U1 and U2 prepare, U3 and U4 approve


class Clock:
    def __init__(self): self.d = date(2026, 3, 10)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


class Vault:
    def get_evidence(self, org, i):
        if org == ORG and i in ("ev1", "ev2"): return SimpleNamespace(id=i, original_filename=f"{i}.pdf", file_hash="h" * 64)
        raise LookupError(i)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = SecretarialService(self.w.store, Vault(), log=lambda *a: self.events.append(a), now=self.clock)

    def meeting(self, actor=U1, **kw):
        d = dict(kind="BOARD", title="Quarterly board meeting", held_on="2026-03-12", location="Head office boardroom", agenda="Accounts, budget and the new bank mandate"); d.update(kw)
        return self.svc.cs_schedule_meeting(ORG, d, actor)

    def held(self, m=None, actor=U2, **kw):
        m = m or self.meeting(); self.clock.d = date(2026, 3, 12)
        d = dict(attendees="Ada Obi, Ben Eze, Chidi Nwosu", minutes="The board reviewed the accounts and agreed the budget for the year."); d.update(kw)
        return self.svc.cs_record_minutes(ORG, m["id"], d, actor)

    def resolution(self, m=None, actor=U1, **kw):
        d = dict(kind="ORDINARY", text="That the budget for the year is approved as presented", meeting_id=(m or self.meeting())["id"]); d.update(kw)
        return self.svc.cs_propose_resolution(ORG, d, actor)

    def decide(self, r, actor=U3, **kw):
        d = dict(votes_for=4, votes_against=1, abstentions=0, outcome="PASSED", note="Counted by the chair and the secretary"); d.update(kw)
        return self.svc.cs_decide_resolution(ORG, r["id"], d, actor)

    def filing(self, actor=U1, **kw):
        d = dict(kind="ANNUAL_RETURN", title="Annual return for the year", authority="Companies registry", due_on="2026-04-30", owner_name="Ada Obi"); d.update(kw)
        return self.svc.cs_add_filing(ORG, d, actor)

    def filed(self, f, actor=U2, **kw):
        d = dict(filed_on="2026-03-10", receipt_ref="REG-2026-0042"); d.update(kw)
        return self.svc.cs_file_filing(ORG, f["id"], d, actor)


class Helpers(unittest.TestCase):
    def test_refnum(self):
        self.assertEqual((refnum({"ref": "MT-012"}), refnum({"ref": "x"}), refnum({})), (12, 0, 0))


class Policy(Base):
    def test_default_and_set(self):
        self.assertEqual(self.svc.cs_get_policy(ORG)["due_soon_days"], 14)
        self.assertEqual(self.svc.cs_set_policy(ORG, {"due_soon_days": "30"}, U3)["due_soon_days"], 30)
        self.assertEqual(self.svc.cs_get_policy(OTHER)["due_soon_days"], 14)

    def test_bounds(self):
        for v in (0, 91, "x", True, -1, 4.5, ""):
            with self.assertRaises(SecretarialError, msg=str(v)): self.svc.cs_set_policy(ORG, {"due_soon_days": v}, U3)


class Meetings(Base):
    def test_schedule_and_validation(self):
        m = self.meeting(); self.assertEqual((m["ref"], m["status"]), ("MT-001", "SCHEDULED")); self.assertEqual(self.meeting()["ref"], "MT-002")
        for bad in (dict(kind="PARTY"), dict(title="abc"), dict(held_on="2026-02-30"), dict(held_on="2029-01-01"), dict(location="x"), dict(agenda="short")):
            with self.assertRaises(SecretarialError, msg=str(bad)): self.meeting(**bad)
        self.assertEqual(self.meeting()["ref"], "MT-003")   # failures did not use numbers

    def test_minutes_not_before_the_meeting(self):
        m = self.meeting(held_on="2026-03-20")
        with self.assertRaises(SecretarialError): self.svc.cs_record_minutes(ORG, m["id"], dict(attendees="Ada Obi", minutes="The board met and discussed matters."), U2)
        self.clock.d = date(2026, 3, 20)
        self.assertEqual(self.svc.cs_record_minutes(ORG, m["id"], dict(attendees="Ada Obi", minutes="The board met and discussed matters."), U2)["status"], "HELD")

    def test_minutes_validation_and_once(self):
        m = self.meeting(); self.clock.d = date(2026, 3, 12)
        for bad in (dict(attendees="", minutes="The board met and discussed matters."), dict(attendees="Ada Obi", minutes="short"), dict(attendees="Ada Obi", minutes="The board met and discussed matters.", evidence_ids=["nope"])):
            with self.assertRaises(SecretarialError): self.svc.cs_record_minutes(ORG, m["id"], bad, U2)
        self.held(m)
        with self.assertRaises(SecretarialStateError): self.held(m)

    def test_minutes_evidence_and_overdue_flag(self):
        m = self.meeting(held_on="2026-03-01"); self.assertTrue(self.svc.cs_get_meeting(ORG, m["id"])["record_due"])
        self.clock.d = date(2026, 3, 12); h = self.svc.cs_record_minutes(ORG, m["id"], dict(attendees="Ada Obi", minutes="The board met and discussed matters.", evidence_ids=["ev1", "ev1"]), U2)
        self.assertEqual([e["evidence_id"] for e in h["evidence"]], ["ev1"]); self.assertFalse(h["record_due"])

    def test_approval_needs_a_different_person(self):
        h = self.held()
        with self.assertRaises(SecretarialForbiddenError): self.svc.cs_approve_minutes(ORG, h["id"], {}, U2)
        a = self.svc.cs_approve_minutes(ORG, h["id"], {}, U3); self.assertEqual((a["status"], a["approved_by"]), ("MINUTES_APPROVED", U3))
        with self.assertRaises(SecretarialStateError): self.svc.cs_approve_minutes(ORG, h["id"], {}, U4)
        m2 = self.meeting(); self.held(m2)
        with self.assertRaises(SecretarialError): self.svc.cs_approve_minutes(ORG, m2["id"], {"note": "ok"}, U3)   # a note, when given, obeys its minimum

    def test_cancel(self):
        m = self.meeting()
        with self.assertRaises(SecretarialError): self.svc.cs_cancel_meeting(ORG, m["id"], "short", U3)
        self.assertEqual(self.svc.cs_cancel_meeting(ORG, m["id"], "Postponed to next quarter", U3)["status"], "CANCELLED")
        with self.assertRaises(SecretarialStateError): self.svc.cs_cancel_meeting(ORG, m["id"], "Postponed to next quarter", U3)
        with self.assertRaises(SecretarialStateError): self.resolution(m)

    def test_cancel_blocked_by_open_resolution_then_allowed(self):
        m = self.meeting(); r = self.resolution(m)
        with self.assertRaises(SecretarialStateError): self.svc.cs_cancel_meeting(ORG, m["id"], "Postponed to next quarter", U3)
        self.svc.cs_withdraw_resolution(ORG, r["id"], "Meeting is being postponed", U3)
        self.assertEqual(self.svc.cs_cancel_meeting(ORG, m["id"], "Postponed to next quarter", U3)["status"], "CANCELLED")

    def test_held_meeting_cannot_be_cancelled(self):
        h = self.held()
        with self.assertRaises(SecretarialStateError): self.svc.cs_cancel_meeting(ORG, h["id"], "Changed our minds on this", U3)

    def test_lists(self):
        a = self.meeting(); b = self.meeting(); self.svc.cs_cancel_meeting(ORG, b["id"], "Postponed to next quarter", U3)
        self.assertEqual([m["ref"] for m in self.svc.cs_list_meetings(ORG)], ["MT-001", "MT-002"]); self.assertEqual([m["ref"] for m in self.svc.cs_list_meetings(ORG, "CANCELLED")], ["MT-002"])


class Resolutions(Base):
    def test_propose_and_validation(self):
        m = self.meeting(); r = self.resolution(m); self.assertEqual((r["ref"], r["status"], r["meeting_ref"], r["can_decide"]), ("RS-001", "PROPOSED", "MT-001", False))
        for bad in (dict(kind="LOUD"), dict(text="short"), dict(meeting_id="nope"), dict(meeting_id=None), dict(kind="WRITTEN")):
            with self.assertRaises((SecretarialError,), msg=str(bad)): self.resolution(m, **bad)
        self.assertEqual(self.resolution(m)["ref"], "RS-002")

    def test_written_resolution_needs_no_meeting(self):
        r = self.svc.cs_propose_resolution(ORG, dict(kind="WRITTEN", text="That the registered address is changed to the new office"), U1)
        self.assertTrue(r["can_decide"]); self.assertEqual(self.decide(r)["status"], "PASSED")

    def test_decide_needs_minutes_first(self):
        m = self.meeting(); r = self.resolution(m)
        with self.assertRaises(SecretarialStateError): self.decide(r)
        self.held(m); self.assertTrue(self.svc.cs_get_resolution(ORG, r["id"])["can_decide"]); self.assertEqual(self.decide(r)["status"], "PASSED")

    def test_proposer_cannot_decide_and_only_once(self):
        m = self.meeting(); r = self.resolution(m); self.held(m)
        with self.assertRaises(SecretarialForbiddenError): self.decide(r, actor=U1)
        d = self.decide(r); self.assertEqual((d["votes_for"], d["votes_against"], d["decided_by"]), (4, 1, U3))
        with self.assertRaises(SecretarialStateError): self.decide(r, actor=U4)

    def test_vote_rules(self):
        m = self.meeting(); r = self.resolution(m); self.held(m)
        for bad in (dict(votes_for=1, votes_against=1), dict(votes_for=0, votes_against=3), dict(votes_for=0, votes_against=0, abstentions=0), dict(votes_for="x"), dict(votes_for=-1), dict(outcome="MAYBE"), dict(note="short"), dict(abstentions=None)):
            with self.assertRaises(SecretarialError, msg=str(bad)): self.decide(r, **bad)
        self.assertEqual(self.decide(r, votes_for=1, votes_against=3, outcome="FAILED")["status"], "FAILED")

    def test_a_tie_cannot_pass_but_can_fail(self):
        m = self.meeting(); r = self.resolution(m); self.held(m)
        with self.assertRaises(SecretarialError): self.decide(r, votes_for=2, votes_against=2)
        self.assertEqual(self.decide(r, votes_for=2, votes_against=2, outcome="FAILED")["status"], "FAILED")

    def test_withdraw(self):
        r = self.resolution()
        with self.assertRaises(SecretarialError): self.svc.cs_withdraw_resolution(ORG, r["id"], "short", U3)
        self.assertEqual(self.svc.cs_withdraw_resolution(ORG, r["id"], "Not needed at this meeting", U3)["status"], "WITHDRAWN")
        with self.assertRaises(SecretarialStateError): self.svc.cs_withdraw_resolution(ORG, r["id"], "Not needed at this meeting", U3)

    def test_no_new_resolution_once_minutes_are_approved(self):
        m = self.meeting(); h = self.held(m); self.svc.cs_approve_minutes(ORG, h["id"], {}, U3)
        with self.assertRaises(SecretarialStateError): self.resolution(m)
        self.resolution(self.meeting())   # a held, unapproved meeting would still take one

    def test_meeting_view_lists_its_resolutions(self):
        m = self.meeting(); self.resolution(m); self.resolution(m); self.resolution()
        self.assertEqual([r["ref"] for r in self.svc.cs_get_meeting(ORG, m["id"])["resolutions"]], ["RS-001", "RS-002"])
        self.assertEqual(len(self.svc.cs_list_resolutions(ORG, meeting_id=m["id"])), 2)


class Filings(Base):
    def test_add_and_validation(self):
        f = self.filing(); self.assertEqual((f["ref"], f["status"], f["overdue"], f["due_soon"]), ("FL-001", "OPEN", False, False))
        for bad in (dict(kind="NOPE"), dict(title="abc"), dict(authority="x"), dict(due_on="soon"), dict(due_on="2035-01-01"), dict(owner_name="")):
            with self.assertRaises(SecretarialError, msg=str(bad)): self.filing(**bad)
        self.assertEqual(self.filing()["ref"], "FL-002")

    def test_overdue_and_due_soon(self):
        self.assertTrue(self.filing(due_on="2026-03-09")["overdue"]); soon = self.filing(due_on="2026-03-20"); self.assertTrue(soon["due_soon"]); self.assertFalse(soon["overdue"])
        self.assertTrue(self.filing(due_on="2026-03-10")["due_soon"])
        self.svc.cs_set_policy(ORG, {"due_soon_days": 1}, U3); self.assertFalse(self.svc.cs_get_filing(ORG, soon["id"])["due_soon"])

    def test_file_and_confirm(self):
        f = self.filing()
        for bad in (dict(filed_on="2026-03-30"), dict(filed_on="nope"), dict(receipt_ref="x"), dict(filed_on="2024-01-01"), dict(evidence_ids=["nope"])):
            with self.assertRaises(SecretarialError, msg=str(bad)): self.filed(f, **bad)
        d = self.filed(f, evidence_ids=["ev2"]); self.assertEqual((d["status"], d["filed_by"], d["overdue"]), ("FILED", U2, False))
        with self.assertRaises(SecretarialStateError): self.filed(f)
        with self.assertRaises(SecretarialForbiddenError): self.svc.cs_confirm_filing(ORG, f["id"], {"note": "Checked the receipt"}, U2)
        with self.assertRaises(SecretarialError): self.svc.cs_confirm_filing(ORG, f["id"], {"note": "ok"}, U3)
        c = self.svc.cs_confirm_filing(ORG, f["id"], {"note": "Checked the receipt against the registry"}, U3); self.assertEqual(c["status"], "CONFIRMED")
        with self.assertRaises(SecretarialStateError): self.svc.cs_confirm_filing(ORG, f["id"], {"note": "Checked the receipt again"}, U4)

    def test_confirm_needs_filed_first(self):
        f = self.filing()
        with self.assertRaises(SecretarialStateError): self.svc.cs_confirm_filing(ORG, f["id"], {"note": "Checked the receipt"}, U3)

    def test_withdraw(self):
        f = self.filing()
        with self.assertRaises(SecretarialError): self.svc.cs_withdraw_filing(ORG, f["id"], "short", U3)
        self.assertEqual(self.svc.cs_withdraw_filing(ORG, f["id"], "No longer required of us", U3)["status"], "WITHDRAWN")
        g = self.filing(); self.filed(g)
        with self.assertRaises(SecretarialStateError): self.svc.cs_withdraw_filing(ORG, g["id"], "No longer required of us", U3)
        self.assertEqual([x["ref"] for x in self.svc.cs_list_filings(ORG, "OPEN")], [])

    def test_a_late_filing_stops_being_overdue_once_filed(self):
        f = self.filing(due_on="2026-03-01"); self.assertTrue(f["overdue"]); self.assertFalse(self.filed(f, filed_on="2026-03-09")["overdue"])


class Overview(Base):
    def test_attention(self):
        self.filing(due_on="2026-03-01"); self.filing(due_on="2026-03-15"); f = self.filing(); self.filed(f)
        m = self.meeting(held_on="2026-03-01"); m2 = self.meeting(held_on="2026-03-12"); self.held(m2); r = self.resolution(m2)
        kinds = {x["kind"]: x["count"] for x in self.svc.cs_overview(ORG)["attention"]}
        self.assertEqual(kinds, {"FILINGS_OVERDUE": 1, "FILINGS_DUE_SOON": 1, "FILINGS_TO_CONFIRM": 1, "MEETINGS_TO_RECORD": 1, "MINUTES_TO_APPROVE": 1, "RESOLUTIONS_TO_DECIDE": 1})

    def test_counts(self):
        m = self.meeting(); self.held(m); a = self.resolution(m); b = self.resolution(m, text="That the auditors are reappointed for a year"); self.resolution(m, text="That the dividend is not declared this year")
        self.decide(a); self.decide(b, votes_for=0, votes_against=4, outcome="FAILED"); c = self.svc.cs_overview(ORG)["counts"]
        self.assertEqual((c["resolutions_passed"], c["resolutions_failed"], c["resolutions_open"], c["meetings_held"], c["meetings_scheduled"]), (1, 1, 1, 1, 0))

    def test_empty_and_options(self):
        o = self.svc.cs_overview(ORG); self.assertEqual(o["attention"], []); self.assertIn("ORDINARY", self.svc.cs_options(ORG)["resolution_kinds"]); self.assertTrue(o["limitations"])


class Isolation(Base):
    def test_other_company_sees_nothing_and_cannot_touch(self):
        m = self.meeting(); r = self.resolution(m); self.held(m); f = self.filing(); self.filed(f)
        for lst in (self.svc.cs_list_meetings, self.svc.cs_list_resolutions, self.svc.cs_list_filings): self.assertEqual(lst(OTHER), [])
        for fn in (lambda: self.svc.cs_get_meeting(OTHER, m["id"]), lambda: self.svc.cs_get_resolution(OTHER, r["id"]), lambda: self.svc.cs_get_filing(OTHER, f["id"]),
                   lambda: self.svc.cs_approve_minutes(OTHER, m["id"], {}, U3), lambda: self.svc.cs_decide_resolution(OTHER, r["id"], dict(votes_for=3, votes_against=0, abstentions=0, outcome="PASSED", note="Decided from outside"), U3),
                   lambda: self.svc.cs_confirm_filing(OTHER, f["id"], {"note": "Confirming from outside"}, U3), lambda: self.svc.cs_propose_resolution(OTHER, dict(kind="ORDINARY", text="Proposing against another company", meeting_id=m["id"]), U1)):
            with self.assertRaises(SecretarialNotFoundError): fn()
        self.assertEqual(self.svc.cs_overview(OTHER)["counts"]["filings_open"], 0)


class Audit(Base):
    def test_every_write_logged_without_content(self):
        m = self.meeting(); self.svc.cs_set_policy(ORG, {"due_soon_days": 20}, U3); h = self.held(m); r = self.resolution(m); self.decide(r); self.svc.cs_approve_minutes(ORG, h["id"], {}, U3)
        r2 = self.resolution(self.meeting(), text="That the second proposal is later withdrawn"); self.svc.cs_withdraw_resolution(ORG, r2["id"], "Not needed at this meeting", U3)
        m3 = self.meeting(); self.svc.cs_cancel_meeting(ORG, m3["id"], "Postponed to next quarter", U3)
        f = self.filing(); self.filed(f); self.svc.cs_confirm_filing(ORG, f["id"], {"note": "Checked the receipt against the registry"}, U3); g = self.filing(); self.svc.cs_withdraw_filing(ORG, g["id"], "No longer required of us", U3)
        acts = [x[0] for x in self.events]
        for x in ("SECRETARIAL_MEETING_SCHEDULED", "SECRETARIAL_MINUTES_RECORDED", "SECRETARIAL_MINUTES_APPROVED", "SECRETARIAL_MEETING_CANCELLED", "SECRETARIAL_RESOLUTION_PROPOSED", "SECRETARIAL_RESOLUTION_DECIDED",
                  "SECRETARIAL_RESOLUTION_WITHDRAWN", "SECRETARIAL_FILING_ADDED", "SECRETARIAL_FILING_FILED", "SECRETARIAL_FILING_CONFIRMED", "SECRETARIAL_FILING_WITHDRAWN", "SECRETARIAL_POLICY_SET"): self.assertIn(x, acts)
        blob = " ".join(str(x) for x in self.events)
        for secret in ("bank mandate", "boardroom", "budget", "Counted by the chair", "REG-2026", "Companies registry", "Checked the receipt"): self.assertNotIn(secret, blob)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(SecretarialError): self.meeting(title="abc")
        self.assertEqual(self.events, [])


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, SEC_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, SEC_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, SEC_PREPARE) or has(r, SEC_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if SEC_PREPARE in perms or SEC_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "secretarial.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "SEC_PREPARE", "_approve": "SEC_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_policy", "approve_minutes", "cancel_meeting", "decide_resolution", "withdraw_resolution", "confirm_filing", "withdraw_filing"}
        prepare = {"schedule_meeting", "record_minutes", "propose_resolution", "add_filing", "file_filing"}
        for n in approve: self.assertEqual(g[n][1], {"SEC_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"SEC_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no secretarial guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
