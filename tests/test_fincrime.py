"""Financial-crime casework: alerts, cases, conflict declarations, timeline, screening records, two-person decisions, loss and recovery, policy, isolation, audit, confidentiality."""
import ast
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from analysis_fixture import ORG, OTHER, World
from asavexa.fincrime.errors import FincrimeError, FincrimeForbiddenError, FincrimeNotFoundError, FincrimeStateError
from asavexa.fincrime.service import FincrimeService, refnum
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import FINCRIME_APPROVE, FINCRIME_PREPARE, FINCRIME_READ, REPORTING_READ, ROLE_PERMISSIONS

U1, U2, U3, U4, U5 = "user-1", "user-2", "user-3", "user-4", "user-5"
MEMBERS = {U1, U2, U3, U4, U5}
WORKERS = {U1, U3}                      # may prepare; U2 and U4 are decision-makers only; U5 is a member with no role in this


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
        self.svc = FincrimeService(self.w.store, Vault(), is_member=lambda o, u: u in MEMBERS, can_work=lambda o, u: u in WORKERS, log=lambda *a: self.events.append(a), now=self.clock)

    def alert(self, actor=U1, **kw):
        d = dict(source="STAFF_REPORT", summary="A supplier asked for payment to a personal account", observed_on="2026-02-10"); d.update(kw)
        return self.svc.fc_raise_alert(ORG, d, actor)

    def case(self, actor=U1, alerts=(), **kw):
        d = dict(title="Payments to a personal account", summary="A supplier asked for payment into an account in a person's name", severity="MEDIUM", alert_ids=list(alerts)); d.update(kw)
        return self.svc.fc_open_case(ORG, d, actor)

    def clear(self, c, *users):
        for u in users: c = self.svc.fc_declare_interest(ORG, c["id"], {"status": "NONE"}, u)
        return c

    def screen(self, c, result="NO_MATCH", actor=U1, **kw):
        d = dict(subject="Acme Trading Ltd", subject_kind="ORGANISATION", check="SANCTIONS", list_name="Internal sanctions list v3", screened_on="2026-02-12", result=result, note="Checked against the list"); d.update(kw)
        return self.svc.fc_record_screening(ORG, c["id"], d, actor)

    def loss(self, c, amount="1000.00", cur="NGN", actor=U1, **kw):
        d = dict(amount=amount, currency=cur, occurred_on="2026-02-01", description="Payment made to the wrong account"); d.update(kw)
        return self.svc.fc_record_loss(ORG, c["id"], d, actor)

    def recover(self, c, amount="400.00", cur="NGN", actor=U1, **kw):
        d = dict(amount=amount, currency=cur, received_on="2026-02-12", kind="REPAID", note="Part repaid by the supplier"); d.update(kw)
        return self.svc.fc_record_recovery(ORG, c["id"], d, actor)

    def propose(self, c, outcome="CONCERN_RESOLVED", actor=U1, **kw):
        d = dict(outcome=outcome, rationale="The payment was recovered and the control was changed so it cannot happen again"); d.update(kw)
        return self.svc.fc_propose_decision(ORG, c["id"], d, actor)


class Helpers(unittest.TestCase):
    def test_references_sort_numerically(self):
        self.assertEqual(sorted([{"ref": "CS-1000"}, {"ref": "CS-999"}, {"ref": "CS-002"}], key=refnum), [{"ref": "CS-002"}, {"ref": "CS-999"}, {"ref": "CS-1000"}]); self.assertEqual(refnum({}), 0)

    def test_amounts(self):
        from asavexa.fincrime.service import _amount
        for bad in ("0", "-5", "abc", "", None, "1.005", float("nan"), True, "inf", "1e30"):
            with self.assertRaises(FincrimeError, msg=bad): _amount(bad, "x")
        self.assertEqual(str(_amount("1,234.50", "x")), "1234.50")


class Policy(Base):
    def test_defaults_set_and_bounds(self):
        self.assertEqual(self.svc.fc_get_policy(ORG)["alert_sla_days"], 5)
        p = self.svc.fc_set_policy(ORG, {"alert_sla_days": 2}, U2); self.assertEqual((p["alert_sla_days"], p["case_sla_days"]), (2, 90))
        for bad in ({"alert_sla_days": 61}, {"case_sla_days": 0}, {"case_sla_days": 366}, {"alert_sla_days": "x"}, {"alert_sla_days": True}):
            with self.assertRaises(FincrimeError, msg=bad): self.svc.fc_set_policy(ORG, bad, U2)
        self.assertIn(("FINCRIME_POLICY_SET", U2, "settings", ORG, "alert target 2, case target 90"), self.events)


class Alerts(Base):
    def test_raise_and_validate(self):
        a = self.alert(amount="2,500.00", currency="ngn", evidence_ids=["ev1"]); self.assertEqual((a["ref"], a["status"], a["amount"], a["currency"]), ("AL-001", "NEW", "2500.00", "NGN"))
        self.assertEqual(a["evidence"][0]["file_hash"], "h" * 64)
        for bad in (dict(source="NOPE"), dict(summary="short"), dict(observed_on="2026-02-30"), dict(observed_on="2026-03-30"), dict(amount="5"), dict(currency="NGN"), dict(amount="0", currency="NGN"), dict(evidence_ids=["zzz"])):
            with self.assertRaises(FincrimeError, msg=bad): self.alert(**bad)

    def test_refused_requests_do_not_burn_reference_numbers(self):
        with self.assertRaises(FincrimeError): self.alert(summary="short")
        self.assertEqual(self.alert()["ref"], "AL-001")

    def test_dismiss_needs_another_person_and_a_reason(self):
        a = self.alert()
        with self.assertRaises(FincrimeForbiddenError): self.svc.fc_dismiss_alert(ORG, a["id"], "Nothing in it after checking the invoice", U1)
        with self.assertRaises(FincrimeError): self.svc.fc_dismiss_alert(ORG, a["id"], "no", U2)
        d = self.svc.fc_dismiss_alert(ORG, a["id"], "Nothing in it after checking the invoice", U2); self.assertEqual((d["status"], d["dismissed_by"]), ("DISMISSED", U2))
        with self.assertRaises(FincrimeStateError): self.svc.fc_dismiss_alert(ORG, a["id"], "Nothing in it after checking the invoice", U2)

    def test_list_filter_and_order(self):
        for _ in range(3): self.alert()
        self.assertEqual([a["ref"] for a in self.svc.fc_list_alerts(ORG)], ["AL-001", "AL-002", "AL-003"])
        self.svc.fc_dismiss_alert(ORG, self.svc.fc_list_alerts(ORG)[0]["id"], "Nothing in it after checking", U2)
        self.assertEqual(len(self.svc.fc_list_alerts(ORG, "NEW")), 2)


class Cases(Base):
    def test_open_moves_alerts_and_records_the_openers_declaration(self):
        a, b = self.alert(), self.alert(); c = self.case(alerts=[a["id"], b["id"], a["id"]])
        self.assertEqual((c["ref"], c["status"], c["lead"], c["alert_refs"]), ("CS-001", "OPEN", U1, ["AL-001", "AL-002"])); self.assertEqual(c["declarations"][U1]["status"], "NONE")
        self.assertEqual({x["status"] for x in self.svc.fc_list_alerts(ORG)}, {"IN_CASE"}); self.assertEqual(self.svc.fc_list_alerts(ORG)[0]["case_ref"], "CS-001")
        with self.assertRaises(FincrimeStateError): self.case(alerts=[a["id"]])

    def test_a_case_may_be_opened_without_an_alert(self):
        self.assertEqual(self.case()["alert_ids"], [])

    def test_opener_with_a_conflict_is_refused_and_nothing_is_created(self):
        a = self.alert()
        with self.assertRaises(FincrimeForbiddenError): self.case(alerts=[a["id"]], conflict="CONFLICT", conflict_note="The supplier is my brother-in-law")
        self.assertEqual(self.svc.fc_list_cases(ORG), []); self.assertEqual(self.svc.fc_list_alerts(ORG)[0]["status"], "NEW"); self.assertEqual(self.case()["ref"], "CS-001")

    def test_case_validation(self):
        for bad in (dict(title="abc"), dict(summary="too short"), dict(severity="X"), dict(alert_ids=["nope"]), dict(conflict="MAYBE")):
            with self.assertRaises(FincrimeError, msg=bad): self.case(**bad)

    def test_declarations(self):
        c = self.case(); cid = c["id"]
        with self.assertRaises(FincrimeError): self.svc.fc_declare_interest(ORG, cid, {"status": "CONFLICT", "note": "short"}, U2)
        with self.assertRaises(FincrimeStateError): self.svc.fc_declare_interest(ORG, cid, {"status": "NONE"}, U1)          # already declared
        c = self.svc.fc_declare_interest(ORG, cid, {"status": "NONE"}, U2); self.assertEqual(c["declarations"][U2]["status"], "NONE")
        c = self.svc.fc_declare_interest(ORG, cid, {"status": "CONFLICT", "note": "I used to work for this supplier"}, U2); self.assertEqual(c["declarations"][U2]["status"], "CONFLICT")
        with self.assertRaises(FincrimeStateError): self.svc.fc_declare_interest(ORG, cid, {"status": "NONE"}, U2)             # a conflict is never withdrawn

    def test_a_lead_who_declares_a_conflict_loses_the_case_and_it_is_flagged(self):
        c = self.case(); c = self.svc.fc_declare_interest(ORG, c["id"], {"status": "CONFLICT", "note": "My cousin owns the supplier"}, U1)
        self.assertIsNone(c["lead"])
        with self.assertRaises(FincrimeForbiddenError): self.svc.fc_add_event(ORG, c["id"], dict(occurred_on="2026-02-10", kind="OTHER", text="Something happened"), U1)
        self.assertIn("CASES_NO_LEAD", [x["kind"] for x in self.svc.fc_overview(ORG)["attention"]])

    def test_change_lead_rules(self):
        c = self.case(); cid = c["id"]
        with self.assertRaises(FincrimeError): self.svc.fc_change_lead(ORG, cid, U2, "Handing over", U4)                    # not a worker
        with self.assertRaises(FincrimeError): self.svc.fc_change_lead(ORG, cid, "stranger", "Handing over", U4)
        with self.assertRaises(FincrimeStateError): self.svc.fc_change_lead(ORG, cid, U3, "Handing over the file", U4)      # U3 has not declared
        self.clear(c, U3)
        with self.assertRaises(FincrimeError): self.svc.fc_change_lead(ORG, cid, U3, "no", U4)
        with self.assertRaises(FincrimeStateError): self.svc.fc_change_lead(ORG, cid, U1, "Handing over the file", U4)      # already the lead
        c = self.svc.fc_change_lead(ORG, cid, U3, "Handing over the file", U4); self.assertEqual(c["lead"], U3)
        with self.assertRaises(FincrimeForbiddenError): self.svc.fc_add_event(ORG, cid, dict(occurred_on="2026-02-10", kind="OTHER", text="Something happened"), U1)

    def test_a_declared_conflict_cannot_be_given_the_case(self):
        c = self.case(); self.svc.fc_declare_interest(ORG, c["id"], {"status": "CONFLICT", "note": "I know the supplier personally"}, U3)
        with self.assertRaises(FincrimeForbiddenError): self.svc.fc_change_lead(ORG, c["id"], U3, "Handing over the file", U4)

    def test_decision_maker_cannot_take_the_lead_while_reassigning(self):
        w = WORKERS.copy(); WORKERS.add(U4)
        try:
            c = self.case(); self.clear(c, U4)
            with self.assertRaises(FincrimeForbiddenError): self.svc.fc_change_lead(ORG, c["id"], U4, "Taking it myself", U4)
        finally: WORKERS.clear(); WORKERS.update(w)


class Timeline(Base):
    def test_events_are_ordered_and_only_the_lead_adds(self):
        c = self.case(); cid = c["id"]
        self.svc.fc_add_event(ORG, cid, dict(occurred_on="2026-02-10", kind="CONTACT", text="Supplier phoned", evidence_ids=["ev1"]), U1)
        self.svc.fc_add_event(ORG, cid, dict(occurred_on="2026-02-05", kind="TRANSACTION", text="Payment of 1,000 made"), U1)
        c = self.svc.fc_add_event(ORG, cid, dict(occurred_on="2026-02-10", kind="OBSERVATION", text="Account name checked"), U1)
        self.assertEqual([e["text"] for e in c["events"]], ["Payment of 1,000 made", "Supplier phoned", "Account name checked"])
        with self.assertRaises(FincrimeForbiddenError): self.svc.fc_add_event(ORG, cid, dict(occurred_on="2026-02-10", kind="OTHER", text="Not the lead"), U3)
        for bad in (dict(occurred_on="2026-03-30"), dict(kind="X"), dict(text="abc"), dict(evidence_ids=["zzz"]), dict(occurred_on="nope")):
            d = dict(occurred_on="2026-02-10", kind="OTHER", text="Something happened"); d.update(bad)
            with self.assertRaises(FincrimeError, msg=bad): self.svc.fc_add_event(ORG, cid, d, U1)
        self.assertEqual(len(self.svc.fc_get_case(ORG, cid)["events"]), 3)


class Screening(Base):
    def test_record_and_resolve(self):
        c = self.case(); self.clear(c, U2); c = self.screen(c, "POSSIBLE_MATCH"); sid = c["screenings"][0]["id"]
        self.assertEqual(c["unresolved_screenings"], 1)
        with self.assertRaises(FincrimeStateError): self.propose(c)
        with self.assertRaises(FincrimeForbiddenError): self.svc.fc_resolve_screening(ORG, c["id"], sid, {"outcome": "FALSE_POSITIVE", "reason": "Different date of birth and country"}, U1)
        with self.assertRaises(FincrimeStateError): self.svc.fc_resolve_screening(ORG, c["id"], sid, {"outcome": "FALSE_POSITIVE", "reason": "Different date of birth and country"}, U4)   # no declaration
        self.clear(c, U4)
        with self.assertRaises(FincrimeError): self.svc.fc_resolve_screening(ORG, c["id"], sid, {"outcome": "FALSE_POSITIVE", "reason": "short"}, U4)
        c = self.svc.fc_resolve_screening(ORG, c["id"], sid, {"outcome": "FALSE_POSITIVE", "reason": "Different date of birth and country"}, U4)
        self.assertEqual((c["unresolved_screenings"], c["confirmed_matches"]), (0, 0))
        with self.assertRaises(FincrimeStateError): self.svc.fc_resolve_screening(ORG, c["id"], sid, {"outcome": "CONFIRMED", "reason": "Changed my mind about it"}, U4)
        self.assertEqual(self.propose(c)["status"], "DECISION_PROPOSED")

    def test_no_concern_is_blocked_by_a_confirmed_match_or_a_loss(self):
        c = self.case(); self.screen(c, "CONFIRMED_MATCH")
        with self.assertRaises(FincrimeStateError): self.propose(c, "NO_CONCERN")
        self.assertEqual(self.propose(c, "CONCERN_RESOLVED")["status"], "DECISION_PROPOSED")
        d = self.case(); self.loss(d)
        with self.assertRaises(FincrimeStateError): self.propose(d, "NO_CONCERN")

    def test_a_no_match_result_needs_no_resolution_and_validation(self):
        c = self.case(); c = self.screen(c); self.assertEqual(c["unresolved_screenings"], 0)
        with self.assertRaises(FincrimeStateError): self.svc.fc_resolve_screening(ORG, c["id"], c["screenings"][0]["id"], {"outcome": "CONFIRMED", "reason": "Not needed for a no match"}, U2)
        with self.assertRaises(FincrimeNotFoundError): self.svc.fc_resolve_screening(ORG, c["id"], "nope", {"outcome": "CONFIRMED", "reason": "Not needed for a no match"}, U2)
        for bad in (dict(subject="ab"), dict(subject_kind="X"), dict(check="X"), dict(list_name="ab"), dict(screened_on="2026-03-30"), dict(result="X"), dict(note="ab")):
            with self.assertRaises(FincrimeError, msg=bad): self.screen(c, **bad)
        with self.assertRaises(FincrimeForbiddenError): self.screen(c, actor=U3)


class LossRecovery(Base):
    def test_position_is_exact_and_per_currency(self):
        c = self.case(); self.loss(c, "1000.10"); self.loss(c, "0.20"); self.loss(c, "50.00", "USD")
        c = self.recover(c, "400.05"); pos = {p["currency"]: p for p in c["position"]}
        self.assertEqual((pos["NGN"]["lost"], pos["NGN"]["recovered_unconfirmed"], pos["NGN"]["recovered_confirmed"], pos["NGN"]["outstanding"]), ("1000.30", "400.05", "0.00", "1000.30")); self.assertEqual(pos["USD"]["lost"], "50.00")
        self.clear(c, U2); c = self.svc.fc_confirm_recovery(ORG, c["id"], c["recoveries"][0]["id"], U2); pos = {p["currency"]: p for p in c["position"]}
        self.assertEqual((pos["NGN"]["recovered_confirmed"], pos["NGN"]["recovered_unconfirmed"], pos["NGN"]["outstanding"]), ("400.05", "0.00", "600.25"))

    def test_recovery_rules(self):
        c = self.case()
        with self.assertRaises(FincrimeStateError): self.recover(c)                         # no loss yet
        self.loss(c, "100.00")
        with self.assertRaises(FincrimeStateError): self.recover(c, cur="USD")             # no loss in USD
        self.recover(c, "60.00")
        with self.assertRaises(FincrimeError): self.recover(c, "40.01")                    # would exceed
        c = self.recover(c, "40.00"); self.assertEqual(len(c["recoveries"]), 2)
        for bad in (dict(kind="X"), dict(note="ab"), dict(received_on="2026-03-30"), dict(amount="0")):
            with self.assertRaises(FincrimeError, msg=bad): self.recover(c, **{"amount": "1.00", **bad})

    def test_rejected_recovery_frees_the_room(self):
        c = self.case(); self.loss(c, "100.00"); c = self.recover(c, "100.00"); self.clear(c, U2)
        c = self.svc.fc_reject_recovery(ORG, c["id"], c["recoveries"][0]["id"], "The money never arrived in the account", U2)
        self.assertEqual(c["recoveries"][0]["status"], "REJECTED"); self.assertEqual(self.recover(c, "100.00")["position"][0]["recovered_unconfirmed"], "100.00")
        with self.assertRaises(FincrimeStateError): self.svc.fc_confirm_recovery(ORG, c["id"], c["recoveries"][0]["id"], U2)

    def test_confirm_needs_a_different_cleared_person(self):
        c = self.case(); self.loss(c); c = self.recover(c); rid = c["recoveries"][0]["id"]
        with self.assertRaises(FincrimeForbiddenError): self.svc.fc_confirm_recovery(ORG, c["id"], rid, U1)
        with self.assertRaises(FincrimeStateError): self.svc.fc_confirm_recovery(ORG, c["id"], rid, U2)         # no declaration
        self.svc.fc_declare_interest(ORG, c["id"], {"status": "CONFLICT", "note": "I used to manage this supplier"}, U2)
        with self.assertRaises(FincrimeForbiddenError): self.svc.fc_confirm_recovery(ORG, c["id"], rid, U2)
        with self.assertRaises(FincrimeNotFoundError): self.svc.fc_confirm_recovery(ORG, c["id"], "nope", U4)


class Decision(Base):
    def ready(self):
        c = self.case(); self.clear(c, U2); return self.propose(c)

    def test_full_flow(self):
        c = self.ready(); self.assertEqual(c["decision"]["proposed_by"], U1)
        c = self.svc.fc_approve_decision(ORG, c["id"], U2, "Agreed"); self.assertEqual((c["status"], c["outcome"], c["closed_on"], c["decision"]["decided_by"]), ("CLOSED", "CONCERN_RESOLVED", "2026-02-15", U2))
        with self.assertRaises(FincrimeStateError): self.svc.fc_add_event(ORG, c["id"], dict(occurred_on="2026-02-10", kind="OTHER", text="Too late for this"), U1)
        with self.assertRaises(FincrimeStateError): self.svc.fc_approve_decision(ORG, c["id"], U2)

    def test_who_may_not_decide(self):
        c = self.ready(); cid = c["id"]
        with self.assertRaises(FincrimeForbiddenError): self.svc.fc_approve_decision(ORG, cid, U1)                       # the lead and proposer
        with self.assertRaises(FincrimeStateError): self.svc.fc_approve_decision(ORG, cid, U4)                           # no declaration
        self.svc.fc_declare_interest(ORG, cid, {"status": "CONFLICT", "note": "I supervised the supplier account"}, U4)
        with self.assertRaises(FincrimeForbiddenError): self.svc.fc_approve_decision(ORG, cid, U4)
        with self.assertRaises(FincrimeForbiddenError): self.svc.fc_reject_decision(ORG, cid, "Not convinced of the reasons", U4)

    def test_the_opener_cannot_decide_after_the_lead_changes(self):
        c = self.case(); self.clear(c, U3, U2); self.svc.fc_change_lead(ORG, c["id"], U3, "Handing over the file", U2)
        c = self.propose(c, actor=U3)
        with self.assertRaises(FincrimeForbiddenError): self.svc.fc_approve_decision(ORG, c["id"], U1)                  # opened it, no longer leads it

    def test_the_person_who_raised_an_alert_cannot_decide_the_case(self):
        a = self.alert(actor=U2); c = self.case(alerts=[a["id"]]); self.clear(c, U2); c = self.propose(c)
        with self.assertRaises(FincrimeForbiddenError): self.svc.fc_approve_decision(ORG, c["id"], U2)
        self.clear(c, U4); self.assertEqual(self.svc.fc_approve_decision(ORG, c["id"], U4)["status"], "CLOSED")

    def test_reject_returns_it_to_the_lead(self):
        c = self.ready()
        with self.assertRaises(FincrimeError): self.svc.fc_reject_decision(ORG, c["id"], "no", U2)
        c = self.svc.fc_reject_decision(ORG, c["id"], "The reasons do not explain the second payment", U2); self.assertEqual(c["status"], "OPEN"); self.assertIn("second payment", c["decision"]["rejected_note"])
        self.assertEqual(self.propose(c, "NO_CONCERN")["decision"]["outcome"], "NO_CONCERN")

    def test_proposal_rules(self):
        c = self.case()
        for bad in (dict(outcome="X"), dict(rationale="too short"), dict(outcome="REFER_ONWARD"), dict(referral_to="The regulator")):
            with self.assertRaises(FincrimeError, msg=bad): self.propose(c, **bad)
        with self.assertRaises(FincrimeForbiddenError): self.propose(c, actor=U3)
        c = self.propose(c, "REFER_ONWARD", referral_to="The financial intelligence unit"); self.assertEqual(c["decision"]["referral_to"], "The financial intelligence unit")
        with self.assertRaises(FincrimeStateError): self.propose(c)                       # one is already waiting
        with self.assertRaises(FincrimeStateError): self.svc.fc_approve_decision(ORG, self.case()["id"], U2)   # nothing proposed

    def test_a_declaration_can_be_made_on_a_closed_case_so_it_can_be_reopened(self):
        c = self.ready(); c = self.svc.fc_approve_decision(ORG, c["id"], U2)
        self.assertEqual(self.svc.fc_declare_interest(ORG, c["id"], {"status": "CONFLICT", "note": "I used to manage this supplier"}, U4)["declarations"][U4]["status"], "CONFLICT")
        with self.assertRaises(FincrimeForbiddenError): self.svc.fc_reopen_case(ORG, c["id"], "New information has come in", U4)

    def test_reopen(self):
        c = self.ready(); c = self.svc.fc_approve_decision(ORG, c["id"], U2)
        with self.assertRaises(FincrimeStateError): self.svc.fc_reopen_case(ORG, c["id"], "New information has come in", U4)    # no declaration
        self.clear(c, U4)
        with self.assertRaises(FincrimeError): self.svc.fc_reopen_case(ORG, c["id"], "no", U4)
        c = self.svc.fc_reopen_case(ORG, c["id"], "New information has come in", U4); self.assertEqual((c["status"], c["outcome"], c["decision"]), ("OPEN", None, None))
        self.assertTrue(any(h["event"] == "DECISION_APPROVED" for h in c["history"]))
        with self.assertRaises(FincrimeStateError): self.svc.fc_reopen_case(ORG, c["id"], "New information has come in", U4)


class Overview(Base):
    def test_attention_and_counts(self):
        self.assertEqual(self.svc.fc_overview(ORG)["attention"], [])
        a = self.alert(); self.clear(self.case(), U2)
        self.clock.d += timedelta(days=6)
        kinds = lambda: {x["kind"]: x["count"] for x in self.svc.fc_overview(ORG)["attention"]}
        self.assertEqual(kinds(), {"ALERTS_WAITING": 1})
        c = self.svc.fc_list_cases(ORG)[0]; self.screen(c, "POSSIBLE_MATCH"); self.loss(c); self.recover(c)
        self.assertEqual(kinds(), {"ALERTS_WAITING": 1, "SCREENINGS_UNRESOLVED": 1, "RECOVERIES_TO_CONFIRM": 1})
        self.clock.d += timedelta(days=100); self.assertIn("CASES_AGING", kinds())
        ov = self.svc.fc_overview(ORG); self.assertEqual((ov["counts"]["alerts"], ov["counts"]["cases_open"], ov["counts"]["open_by_severity"]["MEDIUM"]), (1, 1, 1)); self.assertTrue(ov["limitations"])

    def test_decision_pending_and_options(self):
        c = self.case(); self.propose(c)
        self.assertEqual({x["kind"] for x in self.svc.fc_overview(ORG)["attention"]}, {"DECISIONS_PENDING"})
        o = self.svc.fc_options(ORG); self.assertIn("REFER_ONWARD", o["outcomes"]); self.assertIn("SANCTIONS", o["checks"])

    def test_list_summaries_hide_the_detail(self):
        c = self.case(); self.loss(c)
        row = self.svc.fc_list_cases(ORG)[0]; self.assertEqual((row["losses_count"], row["events_count"]), (1, 0)); self.assertNotIn("losses", row)


class Isolation(Base):
    def test_other_company_sees_nothing_and_cannot_act(self):
        a = self.alert(); c = self.case(); cid = c["id"]
        self.assertEqual(self.svc.fc_list_cases(OTHER), []); self.assertEqual(self.svc.fc_list_alerts(OTHER), [])
        for call in (lambda: self.svc.fc_get_case(OTHER, cid), lambda: self.svc.fc_declare_interest(OTHER, cid, {"status": "NONE"}, U2),
                     lambda: self.svc.fc_add_event(OTHER, cid, dict(occurred_on="2026-02-10", kind="OTHER", text="Something happened"), U1), lambda: self.svc.fc_dismiss_alert(OTHER, a["id"], "Nothing in it at all", U2),
                     lambda: self.svc.fc_open_case(OTHER, dict(title="Another firm case", summary="x" * 30, severity="LOW", alert_ids=[a["id"]]), U1)):
            with self.assertRaises(FincrimeNotFoundError): call()
        self.assertEqual(self.svc.fc_overview(OTHER)["counts"]["cases"], 0); self.assertEqual(self.svc.fc_overview(ORG)["counts"]["cases"], 1)

    def test_other_companys_evidence_is_refused(self):
        with self.assertRaises(FincrimeError): self.svc.fc_raise_alert(OTHER, dict(source="OTHER", summary="Something odd was noticed", observed_on="2026-02-10", evidence_ids=["ev1"]), U1)


class Audit(Base):
    def test_every_step_is_audited_and_content_stays_out_of_the_trail(self):
        a = self.alert(summary="Secret details about Mr Adebayo"); c = self.case(alerts=[a["id"]], title="Mr Adebayo payments"); self.clear(c, U2)
        self.svc.fc_add_event(ORG, c["id"], dict(occurred_on="2026-02-10", kind="OTHER", text="Adebayo confidential note"), U1); self.screen(c, "POSSIBLE_MATCH", subject="Mr Adebayo")
        c = self.svc.fc_get_case(ORG, c["id"]); self.svc.fc_resolve_screening(ORG, c["id"], c["screenings"][0]["id"], {"outcome": "FALSE_POSITIVE", "reason": "Different person with the same name"}, U2)
        self.loss(c); c = self.recover(c); self.svc.fc_confirm_recovery(ORG, c["id"], c["recoveries"][0]["id"], U2); self.propose(c, "REFER_ONWARD", referral_to="The financial intelligence unit")
        self.svc.fc_reject_decision(ORG, c["id"], "Please add the third payment", U2); self.propose(c); self.svc.fc_approve_decision(ORG, c["id"], U2); self.clear(c, U4)
        self.svc.fc_reopen_case(ORG, c["id"], "New information has come in", U4)
        self.svc.fc_set_policy(ORG, {"case_sla_days": 30}, U2); x = self.alert(); self.svc.fc_dismiss_alert(ORG, x["id"], "Nothing in it at all", U2)
        acts = {e[0] for e in self.events}
        need = {"FINCRIME_ALERT_RAISED", "FINCRIME_CASE_OPENED", "FINCRIME_INTEREST_DECLARED", "FINCRIME_EVENT_ADDED", "FINCRIME_SCREENING_RECORDED", "FINCRIME_SCREENING_RESOLVED", "FINCRIME_LOSS_RECORDED", "FINCRIME_RECOVERY_RECORDED",
                "FINCRIME_RECOVERY_CONFIRMED", "FINCRIME_DECISION_PROPOSED", "FINCRIME_DECISION_REJECTED", "FINCRIME_DECISION_APPROVED", "FINCRIME_CASE_REOPENED", "FINCRIME_POLICY_SET", "FINCRIME_ALERT_DISMISSED"}
        self.assertEqual(need - acts, set())
        blob = " ".join(str(e) for e in self.events); self.assertNotIn("Adebayo", blob); self.assertNotIn("financial intelligence", blob)

    def test_lead_change_is_audited(self):
        c = self.case(); self.clear(c, U3); self.svc.fc_change_lead(ORG, c["id"], U3, "Handing over the file", U4)
        self.assertIn("FINCRIME_LEAD_CHANGED", {e[0] for e in self.events})


class Permissions(unittest.TestCase):
    def test_roles_follow_the_forensic_pattern(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.AUDITOR): self.assertTrue(has(r, FINCRIME_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, FINCRIME_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.FINANCE_OFFICER, Role.ADMINISTRATOR, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER):
            for p in (FINCRIME_READ, FINCRIME_PREPARE, FINCRIME_APPROVE): self.assertFalse(has(r, p), (r, p))

    def test_anyone_who_can_prepare_or_approve_can_also_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if FINCRIME_PREPARE in perms or FINCRIME_APPROVE in perms: self.assertIn(FINCRIME_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "fincrime.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "FINCRIME_PREPARE", "_approve": "FINCRIME_APPROVE", "_read": "FINCRIME_READ"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_policy", "dismiss_alert", "change_lead", "resolve_screening", "confirm_recovery", "reject_recovery", "approve_decision", "reject_decision", "reopen_case"}
        prepare = {"raise_alert", "open_case", "add_event", "record_screening", "record_loss", "record_recovery", "propose_decision"}
        for n in approve: self.assertEqual(g[n][1], {"FINCRIME_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"FINCRIME_PREPARE"}, n)
        self.assertEqual(g["declare_interest"][1], {"FINCRIME_READ"})
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare | {"declare_interest"}, f"{n} writes but has no fincrime guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(FINCRIME_READ))]", src); self.assertNotIn("REPORTING_READ", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
