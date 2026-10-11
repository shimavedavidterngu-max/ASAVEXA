"""GRC: scoring, risk lifecycle, acceptance (two-person above appetite), actions (verifier != completer), obligations (recurrence), dashboard, export, isolation."""
import unittest
from datetime import date, datetime, timezone

from analysis_fixture import ORG, OTHER, World
from asavexa.evidence.domain.enums import EvidenceType
from asavexa.grc import service as S
from asavexa.grc.errors import GrcError, GrcForbiddenError, GrcNotFoundError, GrcStateError
from asavexa.grc.service import GrcService, add_months, band
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, GRC_APPROVE, GRC_PREPARE, ROLE_PERMISSIONS

U1, U2, U3 = "user-1", "user-2", "user-3"
CONTROLS = {ORG: [{"id": "c1", "code": "ACC-001", "name": "Balanced journals"}, {"id": "c2", "code": "ACC-002", "name": "Bank reconciled"}], OTHER: [{"id": "c9", "code": "X-1", "name": "Other org control"}]}


class Clock:
    def __init__(self): self.d = date(2026, 6, 15)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = GrcService(self.w.store, lambda org: CONTROLS.get(org, []), self.w.vault, log=lambda *a: self.events.append(a), now=self.clock)

    def risk(self, **kw):
        d = dict(title="Cash theft at till", description="x", category="FRAUD", owner="Finance lead", inherent_l=4, inherent_i=4, treatment="MITIGATE", next_review="2026-09-01")
        d.update(kw); return self.svc.create_risk(ORG, d, U1)

    def evidence(self, name="proof.pdf"):
        return self.w.vault.upload_evidence(ORG, list(EvidenceType)[0], name.encode() * 5, name, "application/pdf", uploaded_by=U1)


class Scoring(Base):
    def test_bands_at_every_boundary(self):
        self.assertEqual([band(n) for n in (1, 4, 5, 9, 10, 16, 17, 25)], ["LOW", "LOW", "MEDIUM", "MEDIUM", "HIGH", "HIGH", "CRITICAL", "CRITICAL"])

    def test_score_is_likelihood_times_impact(self):
        r = self.risk(inherent_l=3, inherent_i=5)
        self.assertEqual((r["inherent_score"], r["residual_score"], r["residual_band"]), (15, 15, "HIGH"))

    def test_scale_must_be_whole_1_to_5(self):
        for bad in (0, 6, "x", None, True, 2.5):
            with self.assertRaises(GrcError, msg=repr(bad)): self.risk(inherent_l=bad)

    def test_lower_residual_needs_a_written_reason(self):
        with self.assertRaises(GrcError): self.risk(residual_l=2, residual_i=2)
        r = self.risk(residual_l=2, residual_i=2, residual_justification="Dual signatures and daily banking now in place")
        self.assertEqual((r["inherent_score"], r["residual_score"]), (16, 4))

    def test_residual_cannot_exceed_inherent(self):
        with self.assertRaises(GrcError): self.risk(residual_l=5, residual_i=4)

    def test_changing_inherent_without_residual_keeps_them_equal(self):
        r = self.risk(); r2 = self.svc.update_risk(ORG, r["id"], {"inherent_l": 2}, U1)
        self.assertEqual((r2["inherent_score"], r2["residual_score"]), (8, 8))

    def test_appetite_flag_and_setting(self):
        r = self.risk(); self.assertTrue(r["above_appetite"])
        self.svc.set_appetite(ORG, 20, U2)
        self.assertFalse(self.svc.get_risk(ORG, r["id"])["above_appetite"])
        for bad in (0, 26, "x", True): 
            with self.assertRaises(GrcError): self.svc.set_appetite(ORG, bad, U2)

    def test_required_fields_and_lists(self):
        for k in ("title", "owner", "next_review"):
            with self.assertRaises(GrcError, msg=k): self.risk(**{k: ""})
        with self.assertRaises(GrcError): self.risk(category="NOPE")
        with self.assertRaises(GrcError): self.risk(treatment="NOPE")
        with self.assertRaises(GrcError): self.risk(next_review="2026-02-30")

    def test_references_are_sequential_per_org(self):
        self.assertEqual([self.risk()["ref"], self.risk()["ref"]], ["R-001", "R-002"])
        self.assertEqual(self.svc.create_risk(OTHER, dict(title="Other risk", owner="Someone", inherent_l=1, inherent_i=1, next_review="2026-09-01"), U1)["ref"], "R-001")


class Controls(Base):
    def test_links_existing_controls_and_shows_codes(self):
        r = self.risk(control_ids=["c1", "c2", "c1"])
        self.assertEqual([c["code"] for c in r["controls"]], ["ACC-001", "ACC-002"])

    def test_cannot_link_another_orgs_or_unknown_control(self):
        for ids in (["c9"], ["nope"]):
            with self.assertRaises(GrcError): self.risk(control_ids=ids)

    def test_control_object_style_lookup(self):
        class C:
            id, code, name = "k1", "K-1", "Obj"
        svc = GrcService(self.w.store, lambda org: [C()], self.w.vault, now=self.clock)
        r = svc.create_risk(ORG, dict(title="Obj risk", owner="Me again", inherent_l=1, inherent_i=1, next_review="2026-09-01", control_ids=["k1"]), U1)
        self.assertEqual(r["controls"][0]["code"], "K-1")


class Lifecycle(Base):
    def test_edit_blocked_once_accepted_or_closed(self):
        r = self.risk(inherent_l=1, inherent_i=1)
        self.svc.request_acceptance(ORG, r["id"], "Low impact and cheap to tolerate for now.", "2026-12-01", U1)
        with self.assertRaises(GrcStateError): self.svc.update_risk(ORG, r["id"], {"title": "Renamed"}, U1)

    def test_treatment_flow(self):
        r = self.risk(); t = self.svc.start_treatment(ORG, r["id"], U1); self.assertEqual(t["status"], "TREATING")
        with self.assertRaises(GrcStateError): self.svc.start_treatment(ORG, r["id"], U1)
        a = self.risk(treatment="ACCEPT")
        with self.assertRaises(GrcStateError): self.svc.start_treatment(ORG, a["id"], U1)

    def test_within_appetite_accepts_directly(self):
        r = self.risk(inherent_l=2, inherent_i=2)
        a = self.svc.request_acceptance(ORG, r["id"], "Small and well understood; we monitor it.", "2026-12-01", U1)
        self.assertEqual((a["status"], a["next_review"]), ("ACCEPTED", "2026-12-01"))

    def test_above_appetite_needs_a_second_person(self):
        r = self.risk()
        p = self.svc.request_acceptance(ORG, r["id"], "Cost of control exceeds the loss we expect.", "2026-12-01", U1)
        self.assertEqual(p["status"], "ACCEPTANCE_REQUESTED")
        with self.assertRaises(GrcForbiddenError): self.svc.approve_acceptance(ORG, r["id"], U1)
        with self.assertRaises(GrcForbiddenError): self.svc.reject_acceptance(ORG, r["id"], U1, "no no no")
        self.assertEqual(self.svc.approve_acceptance(ORG, r["id"], U2, "Agreed by the board.")["status"], "ACCEPTED")
        self.assertEqual(self.svc.get_risk(ORG, r["id"])["acceptance"]["decided_by"], U2)

    def test_rejected_acceptance_returns_to_assessed(self):
        r = self.risk(); self.svc.request_acceptance(ORG, r["id"], "Cost of control exceeds the loss we expect.", "2026-12-01", U1)
        with self.assertRaises(GrcError): self.svc.reject_acceptance(ORG, r["id"], U2, "")
        self.assertEqual(self.svc.reject_acceptance(ORG, r["id"], U2, "Too risky to accept.")["status"], "ASSESSED")

    def test_acceptance_validation(self):
        r = self.risk()
        with self.assertRaises(GrcError): self.svc.request_acceptance(ORG, r["id"], "short", "2026-12-01", U1)
        with self.assertRaises(GrcError): self.svc.request_acceptance(ORG, r["id"], "A perfectly long enough reason.", "2026-06-15", U1)
        with self.assertRaises(GrcError): self.svc.request_acceptance(ORG, r["id"], "A perfectly long enough reason.", "", U1)

    def test_decide_requires_pending_request(self):
        r = self.risk()
        with self.assertRaises(GrcStateError): self.svc.approve_acceptance(ORG, r["id"], U2)

    def test_reopen_and_close(self):
        r = self.risk(inherent_l=1, inherent_i=1)
        self.svc.request_acceptance(ORG, r["id"], "Small and well understood; we monitor it.", "2026-12-01", U1)
        with self.assertRaises(GrcError): self.svc.reopen_risk(ORG, r["id"], "", U1)
        self.assertEqual(self.svc.reopen_risk(ORG, r["id"], "Review came round", U1)["status"], "ASSESSED")
        with self.assertRaises(GrcStateError): self.svc.reopen_risk(ORG, r["id"], "Review came round", U1)
        with self.assertRaises(GrcError): self.svc.close_risk(ORG, r["id"], "short", U1)
        c = self.svc.close_risk(ORG, r["id"], "Activity stopped entirely.", U1)
        self.assertEqual(c["status"], "CLOSED")
        with self.assertRaises(GrcStateError): self.svc.close_risk(ORG, r["id"], "Activity stopped entirely.", U1)

    def test_cannot_close_while_acceptance_pending_or_actions_open(self):
        r = self.risk(); a = self.svc.create_action(ORG, dict(risk_id=r["id"], title="Install safe", owner="Ops", due="2026-07-01"), U1)
        with self.assertRaises(GrcStateError): self.svc.close_risk(ORG, r["id"], "Closing too early now", U1)
        self.svc.cancel_action(ORG, a["id"], "No longer needed", U1)
        self.svc.request_acceptance(ORG, r["id"], "Cost of control exceeds the loss we expect.", "2026-12-01", U1)
        with self.assertRaises(GrcStateError): self.svc.close_risk(ORG, r["id"], "Closing too early now", U1)

    def test_history_records_each_step(self):
        r = self.risk(); self.svc.start_treatment(ORG, r["id"], U1)
        self.assertEqual([h["event"] for h in self.svc.get_risk(ORG, r["id"])["history"]], ["CREATED", "TREATMENT_STARTED"])

    def test_review_overdue_flag(self):
        r = self.risk(next_review="2026-06-10"); self.assertTrue(r["review_overdue"])
        self.assertFalse(self.risk(next_review="2026-06-15")["review_overdue"])


class Actions(Base):
    def setUp(self):
        super().setUp(); self.r = self.risk()

    def act(self, **kw):
        d = dict(risk_id=self.r["id"], title="Install a safe", owner="Ops manager", due="2026-07-01"); d.update(kw); return self.svc.create_action(ORG, d, U1)

    def test_happy_path_with_evidence(self):
        a = self.act(); ev = self.evidence()
        d = self.svc.complete_action(ORG, a["id"], "Safe installed and keys logged.", [ev.id], U2)
        self.assertEqual((d["status"], d["evidence"][0]["filename"]), ("DONE", "proof.pdf"))
        with self.assertRaises(GrcForbiddenError): self.svc.verify_action(ORG, a["id"], U2)
        self.assertEqual(self.svc.verify_action(ORG, a["id"], U3)["status"], "VERIFIED")

    def test_send_back_reopens_and_needs_reason(self):
        a = self.act(); self.svc.complete_action(ORG, a["id"], "Safe installed and keys logged.", [], U2)
        with self.assertRaises(GrcForbiddenError): self.svc.reject_action(ORG, a["id"], U2, "not good")
        with self.assertRaises(GrcError): self.svc.reject_action(ORG, a["id"], U3, "")
        back = self.svc.reject_action(ORG, a["id"], U3, "No photo of the safe.")
        self.assertEqual((back["status"], back["completed_by"]), ("OPEN", None))

    def test_unknown_evidence_and_wrong_org_evidence_refused(self):
        a = self.act()
        with self.assertRaises(GrcError): self.svc.complete_action(ORG, a["id"], "Safe installed and keys logged.", ["nope"], U2)
        self.assertEqual(self.svc.list_actions(ORG)[0]["status"], "OPEN")

    def test_state_guards(self):
        a = self.act()
        with self.assertRaises(GrcStateError): self.svc.verify_action(ORG, a["id"], U3)
        self.svc.complete_action(ORG, a["id"], "Safe installed and keys logged.", [], U2)
        for f in (lambda: self.svc.complete_action(ORG, a["id"], "Again and again once more.", [], U2), lambda: self.svc.cancel_action(ORG, a["id"], "too late", U1),
                  lambda: self.svc.update_action(ORG, a["id"], {"title": "New"}, U1)):
            with self.assertRaises(GrcStateError): f()

    def test_overdue_flag_and_validation(self):
        a = self.act(due="2026-06-01"); self.assertTrue(a["overdue"])
        with self.assertRaises(GrcError): self.act(due="soon")
        with self.assertRaises(GrcError): self.act(owner="")
        with self.assertRaises(GrcNotFoundError): self.act(risk_id="nope")

    def test_no_action_on_closed_risk(self):
        r = self.risk(); self.svc.close_risk(ORG, r["id"], "Activity stopped entirely.", U1)
        with self.assertRaises(GrcStateError): self.act(risk_id=r["id"])

    def test_update_and_cancel(self):
        a = self.act(); u = self.svc.update_action(ORG, a["id"], {"due": "2026-08-01", "owner": "New owner"}, U1)
        self.assertEqual((u["due"], u["owner"]), ("2026-08-01", "New owner"))
        with self.assertRaises(GrcError): self.svc.cancel_action(ORG, a["id"], "no", U1)
        self.assertEqual(self.svc.cancel_action(ORG, a["id"], "Not needed any more", U1)["status"], "CANCELLED")

    def test_action_counts_on_risk(self):
        self.act(); self.assertEqual(self.svc.get_risk(ORG, self.r["id"])["action_counts"]["OPEN"], 1)


class Obligations(Base):
    def ob(self, **kw):
        d = dict(title="File annual return", source_type="LAW", authority="Registrar of Companies", source_ref="s.12", source_url="https://example.org/law", description="File the annual return.",
                 owner="Company secretary", frequency="ANNUAL", next_due="2026-06-30"); d.update(kw); return self.svc.create_obligation(ORG, d, U1)

    def test_state_boundaries(self):
        self.assertEqual(self.ob(next_due="2026-06-14")["state"], "OVERDUE")
        self.assertEqual(self.ob(next_due="2026-06-15")["state"], "DUE_SOON")
        self.assertEqual(self.ob(next_due="2026-07-15")["state"], "DUE_SOON")
        self.assertEqual(self.ob(next_due="2026-07-16")["state"], "ON_TRACK")

    def test_mark_met_advances_from_due_date_not_met_date(self):
        o = self.ob(frequency="QUARTERLY", next_due="2026-06-30")
        m = self.svc.mark_met(ORG, o["id"], "2026-06-15", "Filed online, receipt saved.", [], U2)
        self.assertEqual(m["next_due"], "2026-09-30"); self.assertFalse(m["history"][0]["late"])
        self.clock.d = date(2026, 10, 5)
        late = self.svc.mark_met(ORG, o["id"], "2026-10-05", "Filed late, penalty accepted.", [], U2)
        self.assertTrue(late["history"][1]["late"]); self.assertEqual(late["next_due"], "2026-12-30")

    def test_month_end_clamping(self):
        self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(add_months(date(2026, 11, 30), 3), date(2027, 2, 28))
        self.assertEqual(add_months(date(2024, 2, 29), 12), date(2025, 2, 28))

    def test_one_off_becomes_met(self):
        o = self.ob(frequency="ONE_OFF")
        m = self.svc.mark_met(ORG, o["id"], "2026-06-15", "Licence renewed and filed.", [], U2)
        self.assertEqual((m["state"], m["next_due"]), ("MET", None))
        with self.assertRaises(GrcStateError): self.svc.mark_met(ORG, o["id"], "2026-06-15", "Licence renewed twice?", [], U2)

    def test_met_validation(self):
        o = self.ob()
        with self.assertRaises(GrcError): self.svc.mark_met(ORG, o["id"], "2026-06-16", "Filed ahead of time.", [], U2)
        with self.assertRaises(GrcError): self.svc.mark_met(ORG, o["id"], "2026-06-15", "", [], U2)
        with self.assertRaises(GrcError): self.svc.mark_met(ORG, o["id"], "2026-06-15", "Filed online ok.", ["nope"], U2)

    def test_evidence_is_recorded(self):
        o = self.ob(); ev = self.evidence()
        m = self.svc.mark_met(ORG, o["id"], "2026-06-15", "Filed online, receipt saved.", [ev.id], U2)
        self.assertEqual(m["history"][0]["evidence"][0]["file_hash"], ev.file_hash)

    def test_retire(self):
        o = self.ob(); r = self.svc.retire_obligation(ORG, o["id"], "Law repealed in 2026.", U1)
        self.assertEqual(r["state"], "RETIRED")
        for f in (lambda: self.svc.mark_met(ORG, o["id"], "2026-06-15", "Filed online ok.", [], U2), lambda: self.svc.update_obligation(ORG, o["id"], {"title": "New title"}, U1),
                  lambda: self.svc.retire_obligation(ORG, o["id"], "Law repealed in 2026.", U1)):
            with self.assertRaises(GrcStateError): f()

    def test_validation(self):
        for kw in ({"source_url": "javascript:alert(1)"}, {"source_type": "NOPE"}, {"frequency": "WEEKLY"}, {"next_due": ""}, {"authority": ""}, {"control_ids": ["c9"]}):
            with self.assertRaises(GrcError, msg=str(kw)): self.ob(**kw)

    def test_update_fields(self):
        o = self.ob(); u = self.svc.update_obligation(ORG, o["id"], {"owner": "New owner", "frequency": "monthly", "control_ids": ["c1"]}, U1)
        self.assertEqual((u["owner"], u["frequency"], u["controls"][0]["code"]), ("New owner", "MONTHLY", "ACC-001"))
        with self.assertRaises(GrcError): self.svc.update_obligation(ORG, o["id"], {"source_url": "ftp://x"}, U1)

    def test_no_legal_content_ships(self):
        self.assertEqual(self.svc.list_obligations(ORG), [])


class DashboardAndExport(Base):
    def test_dashboard(self):
        r1 = self.risk(title="Big one", inherent_l=5, inherent_i=5)            # 25 critical, above appetite, no plan
        r2 = self.risk(title="Small one", inherent_l=1, inherent_i=2, next_review="2026-01-01")  # overdue review
        r3 = self.risk(title="Planned", inherent_l=4, inherent_i=4)
        self.svc.create_action(ORG, dict(risk_id=r3["id"], title="Do it", owner="Ops", due="2026-06-01"), U1)
        r4 = self.risk(title="Pending accept", inherent_l=3, inherent_i=4)
        self.svc.request_acceptance(ORG, r4["id"], "Cost of control exceeds the loss we expect.", "2026-12-01", U1)
        self.svc.create_obligation(ORG, dict(title="Late filing", source_type="LAW", authority="Registrar", description="File the thing", owner="Secretary", next_due="2026-06-01"), U1)
        d = self.svc.dashboard(ORG)
        self.assertEqual(d["counts"]["live_risks"], 4); self.assertEqual(d["counts"]["above_appetite"], 3)
        self.assertEqual(d["heatmap"]["cells"][4][4], 1)
        self.assertEqual(d["top_risks"][0]["title"], "Big one")
        att = d["attention"]
        self.assertEqual([r["title"] for r in att["above_appetite_without_plan"]], ["Big one"])
        self.assertEqual([r["title"] for r in att["reviews_overdue"]], ["Small one"])
        self.assertEqual([r["title"] for r in att["acceptances_waiting"]], ["Pending accept"])
        self.assertEqual(len(att["actions_overdue"]), 1); self.assertEqual(len(att["obligations_overdue"]), 1)
        self.assertTrue(d["limitations"])

    def test_closed_risks_leave_the_live_picture(self):
        r = self.risk(); self.svc.close_risk(ORG, r["id"], "Activity stopped entirely.", U1)
        d = self.svc.dashboard(ORG); self.assertEqual((d["counts"]["risks"], d["counts"]["live_risks"]), (1, 0))

    def test_empty_dashboard(self):
        d = self.svc.dashboard(ORG); self.assertEqual(d["counts"]["risks"], 0); self.assertEqual(sum(map(sum, d["heatmap"]["cells"])), 0)

    def test_export_neutralises_formulas_and_is_labelled(self):
        self.risk(title="=HYPERLINK(\"http://evil\")", owner="+cmd|' /C calc'!A0")
        out = self.svc.export_csv(ORG, U1)
        self.assertIn("CONFIDENTIAL", out["content"].splitlines()[0])
        self.assertNotIn(",=HYPERLINK", out["content"]); self.assertIn("'=HYPERLINK", out["content"]); self.assertIn("'+cmd", out["content"])
        self.assertTrue(out["filename"].endswith("2026-06-15.csv"))


class Isolation(Base):
    def test_other_org_cannot_see_or_touch(self):
        r = self.risk(); a = self.svc.create_action(ORG, dict(risk_id=r["id"], title="Do it", owner="Ops", due="2026-07-01"), U1)
        o = self.svc.create_obligation(ORG, dict(title="File it", source_type="LAW", authority="Registrar", description="File the thing", owner="Secretary", next_due="2026-07-01"), U1)
        for f in (lambda: self.svc.get_risk(OTHER, r["id"]), lambda: self.svc.update_risk(OTHER, r["id"], {"title": "x" * 5}, U2), lambda: self.svc.close_risk(OTHER, r["id"], "Closing from outside", U2),
                  lambda: self.svc.complete_action(OTHER, a["id"], "Done from outside org", [], U2), lambda: self.svc.get_obligation(OTHER, o["id"]),
                  lambda: self.svc.mark_met(OTHER, o["id"], "2026-06-15", "Met from outside org", [], U2), lambda: self.svc.create_action(OTHER, dict(risk_id=r["id"], title="Sneaky", owner="Me", due="2026-07-01"), U2)):
            with self.assertRaises(GrcNotFoundError): f()
        self.assertEqual((self.svc.list_risks(OTHER), self.svc.list_actions(OTHER), self.svc.list_obligations(OTHER)), ([], [], []))
        self.assertEqual(self.svc.dashboard(OTHER)["counts"]["risks"], 0)

    def test_appetite_is_per_org(self):
        self.svc.set_appetite(ORG, 3, U2); self.assertEqual(self.svc.get_settings(OTHER)["appetite"], S.DEFAULT_APPETITE)


class AuditAndRoles(Base):
    def test_every_write_is_audited(self):
        r = self.risk(); self.svc.start_treatment(ORG, r["id"], U1)
        a = self.svc.create_action(ORG, dict(risk_id=r["id"], title="Do it", owner="Ops", due="2026-07-01"), U1)
        self.svc.complete_action(ORG, a["id"], "Done and dusted fully.", [], U2); self.svc.verify_action(ORG, a["id"], U3)
        self.svc.set_appetite(ORG, 12, U3); self.svc.export_csv(ORG, U1)
        acts = [e[0] for e in self.events]
        for x in ("GRC_RISK_CREATED", "GRC_RISK_TREATING", "GRC_ACTION_CREATED", "GRC_ACTION_DONE", "GRC_ACTION_VERIFIED", "GRC_APPETITE_SET", "GRC_REGISTER_EXPORTED"):
            self.assertIn(x, acts)

    def test_role_matrix(self):
        has = lambda role, p: p in ROLE_PERMISSIONS[role]
        for role in (Role.OWNER, Role.ADMINISTRATOR, Role.FINANCE_OFFICER, Role.MANAGER): self.assertTrue(has(role, GRC_PREPARE) and has(role, AUDIT_READ), role)
        for role in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(role, GRC_APPROVE), role)
        for role in (Role.ACCOUNTANT, Role.AUDITOR, Role.REVIEWER, Role.READ_ONLY, Role.EXTERNAL_AUDITOR, Role.FINANCE_OFFICER, Role.ADMINISTRATOR):
            self.assertFalse(has(role, GRC_APPROVE), role)
        for role in (Role.READ_ONLY, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.AUDITOR, Role.APPROVER): self.assertFalse(has(role, GRC_PREPARE), role)


if __name__ == "__main__":
    unittest.main()
