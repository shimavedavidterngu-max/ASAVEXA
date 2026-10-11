"""Forensic: analytics (pure functions on constructed data with known answers), case lifecycle, chain of custody, separation of duties, isolation."""
import math
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from analysis_fixture import ORG, OTHER, PREP, PREP2, REVIEWER, World
from asavexa.evidence.domain.enums import EvidenceType
from asavexa.forensic import analytics as A
from asavexa.forensic.errors import ForensicError, ForensicForbiddenError, ForensicNotFoundError, ForensicStateError
from asavexa.forensic.service import GENESIS, ForensicService
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import FORENSIC_APPROVE, FORENSIC_PREPARE, FORENSIC_READ, ROLE_PERMISSIONS

P = A.clean_params(None)


def J(n, d, total, created="u1", posted="u2", ev="e", lines=None, **kw):
    t = Decimal(str(total))
    base = dict(id=f"id{n}", number=f"JE-{n}", date=d, description=f"entry {n}", created_by=created, posted_by=posted, posted_at=datetime(d.year, d.month, d.day, tzinfo=timezone.utc), total=t,
                lines=lines or [("A", t, Decimal(0)), ("B", Decimal(0), t)], evidence_ref=ev, reversal_of=None, reversed_by=None)
    base.update(kw); return base


class Analytics(unittest.TestCase):
    def test_benford_conforming_data_passes_and_skewed_data_is_flagged(self):
        rows = []
        n = 0
        for d in range(1, 10):
            for _ in range(round(1000 * math.log10(1 + 1 / d))):
                n += 1; rows.append(J(n, date(2026, 1, 5), f"{d}{n % 90 + 10}.00"))
        r = A.benford(rows, P)
        self.assertEqual(r["status"], "NO_INDICATORS"); self.assertLess(r["detail"]["mad"], 0.006)
        skew = [J(i, date(2026, 1, 5), f"9{i % 90 + 10}.00") for i in range(300)]
        r = A.benford(skew, P)
        self.assertEqual(r["status"], "INDICATORS"); self.assertEqual(r["detail"]["band"], "non-conformity"); self.assertIn("9", r["summary"])

    def test_benford_needs_enough_data(self):
        self.assertEqual(A.benford([J(i, date(2026, 1, 5), 500) for i in range(10)], P)["status"], "NOT_ENOUGH_DATA")

    def test_duplicates_window_and_exclusions(self):
        rows = [J(1, date(2026, 1, 5), 500), J(2, date(2026, 1, 7), 500), J(3, date(2026, 1, 20), 500), J(4, date(2026, 1, 5), 501),
                J(5, date(2026, 1, 5), 800, reversed_by="x"), J(6, date(2026, 1, 5), 800, reversal_of="y")]
        r = A.duplicates(rows, P)
        self.assertEqual([h["number"] for h in r["hits"]], ["JE-2"]); self.assertEqual(r["hits"][0]["matches"], "JE-1")
        self.assertEqual(A.duplicates(rows, {**P, "duplicate_window_days": 30})["hit_count"], 3)       # 2 and 3 each match 1, and 3 matches 2

    def test_duplicates_need_the_same_accounts(self):
        a = J(1, date(2026, 1, 5), 500); b = J(2, date(2026, 1, 5), 500, lines=[("A", Decimal(500), Decimal(0)), ("C", Decimal(0), Decimal(500))])
        self.assertEqual(A.duplicates([a, b], P)["status"], "NO_INDICATORS")

    def test_round_numbers(self):
        rows = [J(i, date(2026, 1, 5), 5000) for i in range(6)] + [J(10 + i, date(2026, 1, 5), 1234 + i) for i in range(6)]
        r = A.round_numbers(rows, P); self.assertEqual(r["status"], "INDICATORS"); self.assertEqual(r["hit_count"], 6)
        self.assertEqual(A.round_numbers(rows[:3], P)["status"], "NOT_ENOUGH_DATA")
        calm = [J(i, date(2026, 1, 5), 1100 + i) for i in range(20)]
        self.assertEqual(A.round_numbers(calm, P)["status"], "NO_INDICATORS")

    def test_just_below_limit(self):
        rows = [J(1, date(2026, 1, 5), 9600), J(2, date(2026, 1, 5), 9999.99), J(3, date(2026, 1, 5), 10000), J(4, date(2026, 1, 5), 9400), J(5, date(2026, 1, 5), 9500)]
        self.assertEqual(A.just_below(rows, P)["status"], "NOT_CONFIGURED")
        r = A.just_below(rows, {**P, "approval_limit": "10000"})
        self.assertEqual(sorted(h["number"] for h in r["hits"]), ["JE-1", "JE-2", "JE-5"])      # 9500 included (lower bound), 10000 and 9400 excluded

    def test_weekend_default_and_custom(self):
        rows = [J(1, date(2026, 1, 3), 10), J(2, date(2026, 1, 4), 10), J(3, date(2026, 1, 5), 10), J(4, date(2026, 1, 2), 10)]      # Sat, Sun, Mon, Fri
        self.assertEqual([h["number"] for h in A.weekend(rows, P)["hits"]], ["JE-1", "JE-2"])
        self.assertEqual([h["number"] for h in A.weekend(rows, {**P, "weekend_days": [4, 5]})["hits"]], ["JE-1", "JE-4"])

    def test_same_person_and_unposted(self):
        rows = [J(1, date(2026, 1, 5), 10, created="a", posted="a"), J(2, date(2026, 1, 5), 10, created="a", posted="b"), J(3, date(2026, 1, 5), 10, created="a", posted=None)]
        self.assertEqual([h["number"] for h in A.same_person(rows, P)["hits"]], ["JE-1"])

    def test_no_evidence(self):
        rows = [J(1, date(2026, 1, 5), 5000, ev=None), J(2, date(2026, 1, 5), 5000), J(3, date(2026, 1, 5), 50, ev=None)]
        self.assertEqual(A.no_evidence(rows, P)["status"], "NOT_CONFIGURED")
        self.assertEqual([h["number"] for h in A.no_evidence(rows, {**P, "evidence_threshold": "1000"})["hits"]], ["JE-1"])

    def test_reversals_threshold(self):
        rows = [J(i, date(2026, 1, 5), 10, reversed_by=f"r{i}") for i in range(3)] + [J(10 + i, date(2026, 1, 5), 10) for i in range(7)]
        self.assertEqual(A.reversals(rows, P)["status"], "INDICATORS")
        self.assertEqual(A.reversals(rows[2:], P)["status"], "NO_INDICATORS")

    def test_late_posting(self):
        j = J(1, date(2026, 1, 5), 10, posted_at=datetime(2026, 3, 1, tzinfo=timezone.utc)); k = J(2, date(2026, 1, 5), 10)
        r = A.late_posting([j, k], P); self.assertEqual([h["number"] for h in r["hits"]], ["JE-1"]); self.assertEqual(r["hits"][0]["lag_days"], 55)

    def test_params_are_validated(self):
        for bad in ({"round_to": "0"}, {"just_below_pct": "101"}, {"approval_limit": "abc"}, {"weekend_days": [7]}, {"late_days": "-1"}, {"weekend_days": "x"}, {"approval_limit": "NaN"}):
            with self.assertRaises(ForensicError, msg=str(bad)): A.clean_params(bad)
        with self.assertRaises(ForensicError): A.run_tests([], [], P)
        with self.assertRaises(ForensicError): A.run_tests([], ["nope"], P)

    def test_hits_are_capped_but_counted(self):
        rows = [J(i, date(2026, 1, 3), 10) for i in range(250)]
        r = A.weekend(rows, P); self.assertEqual((r["hit_count"], len(r["hits"]), r["truncated"]), (250, 200, True))

    def test_every_result_says_indicator_not_proof(self):
        rows = [J(i, date(2026, 1, 3), 1000 + i) for i in range(30)]
        for r in A.run_tests(rows, list(A.TESTS), {**P, "approval_limit": "2000", "evidence_threshold": "500"}):
            self.assertIn("status", r); self.assertTrue(r["name"])
            if r["status"] == "INDICATORS": self.assertTrue(r["limits"], r["id"])


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.events = []
        self.now = datetime(2026, 4, 1, tzinfo=timezone.utc)
        self.s = ForensicService(self.w.store, self.w.acc, self.w.vault, log=lambda *a, **k: self.events.append(a), now=lambda: self.now)
        self.case = self.s.create_case(ORG, "Rent payments review", "Looks odd", "IRREGULARITY", PREP)

    def evidence(self, content=b"statement", name="bank.pdf"):
        return self.w.vault.upload_evidence(ORG, list(EvidenceType)[0], content, name, "application/pdf", uploaded_by=PREP)


class Cases(Base):
    def test_case_numbers_and_opening_custody(self):
        c2 = self.s.create_case(ORG, "Second case", "", "OTHER", PREP)
        self.assertEqual((self.case["reference"], c2["reference"]), ("CASE-0001", "CASE-0002"))
        self.assertEqual(self.s.create_case(OTHER, "Other org case", "", "OTHER", PREP)["reference"], "CASE-0001")
        full = self.s.get_case(ORG, self.case["id"]); self.assertEqual(full["custody"][0]["action"], "CASE_OPENED"); self.assertTrue(full["custody_check"]["ok"])

    def test_validation(self):
        with self.assertRaises(ForensicError): self.s.create_case(ORG, "ab", "", "OTHER", PREP)
        with self.assertRaises(ForensicError): self.s.create_case(ORG, "Good title", "", "BOGUS", PREP)

    def test_isolation_between_organisations(self):
        with self.assertRaises(ForensicNotFoundError): self.s.get_case(OTHER, self.case["id"])
        with self.assertRaises(ForensicNotFoundError): self.s.run_analytics(OTHER, self.case["id"], {"period_id": self.w.jan.id}, ["weekend"], None, PREP)
        self.assertEqual(self.s.list_cases(OTHER), [])
        self.assertEqual(len(self.s.list_cases(ORG)), 1)

    def test_close_needs_a_different_person_and_no_open_findings(self):
        with self.assertRaises(ForensicForbiddenError): self.s.close_case(ORG, self.case["id"], PREP, "done")
        f = self.s.create_finding(ORG, self.case["id"], "Duplicate rent", "Rent for January was paid twice on consecutive days.", "MEDIUM", [], [], None, PREP)
        with self.assertRaises(ForensicStateError): self.s.close_case(ORG, self.case["id"], REVIEWER, "done")
        self.s.discard_finding(ORG, f["id"], PREP)
        c = self.s.close_case(ORG, self.case["id"], REVIEWER, "No further action")
        self.assertEqual(c["status"], "CLOSED")
        with self.assertRaises(ForensicStateError): self.s.add_evidence(ORG, self.case["id"], self.evidence().id, "", PREP)
        with self.assertRaises(ForensicStateError): self.s.update_case(ORG, self.case["id"], "New title", "", PREP)
        with self.assertRaises(ForensicStateError): self.s.run_analytics(ORG, self.case["id"], {"period_id": self.w.jan.id}, ["weekend"], None, PREP)


class Custody(Base):
    def test_evidence_added_with_hash_and_chain_is_valid(self):
        e = self.evidence(); it = self.s.add_evidence(ORG, self.case["id"], e.id, "from the bank", PREP)
        self.assertEqual(it["file_hash"], e.file_hash)
        v = self.s.verify_custody(ORG, self.case["id"])
        self.assertTrue(v["ok"]); self.assertEqual(v["entries"], 2); self.assertTrue(v["evidence"][0]["hash_matches"])
        with self.assertRaises(ForensicStateError): self.s.add_evidence(ORG, self.case["id"], e.id, "", PREP)

    def test_evidence_must_exist_in_this_org(self):
        e = self.evidence()
        with self.assertRaises(Exception): self.s.add_evidence(OTHER, self.s.create_case(OTHER, "Other case", "", "OTHER", PREP)["id"], e.id, "", PREP)
        with self.assertRaises(Exception): self.s.add_evidence(ORG, self.case["id"], "no-such-id", "", PREP)

    def test_tampering_with_the_custody_log_is_detected(self):
        self.s.add_evidence(ORG, self.case["id"], self.evidence().id, "", PREP)
        raw = self.w.store.get("forensic_case", f"{ORG}:{self.case['id']}")
        raw["custody"][0]["actor"] = "someone-else"; self.w.store.put("forensic_case", f"{ORG}:{self.case['id']}", raw, org_id=ORG)
        v = self.s.verify_custody(ORG, self.case["id"])
        self.assertFalse(v["ok"]); self.assertEqual(v["custody_chain"]["broken_at"], 1); self.assertIn("altered", v["meaning"])

    def test_removing_a_custody_entry_is_detected(self):
        self.s.add_evidence(ORG, self.case["id"], self.evidence().id, "", PREP); self.s.add_evidence(ORG, self.case["id"], self.evidence(b"two", "two.pdf").id, "", PREP)
        raw = self.w.store.get("forensic_case", f"{ORG}:{self.case['id']}"); del raw["custody"][1]
        self.w.store.put("forensic_case", f"{ORG}:{self.case['id']}", raw, org_id=ORG)
        self.assertFalse(self.s.verify_custody(ORG, self.case["id"])["custody_chain"]["ok"])

    def test_changed_evidence_hash_is_detected(self):
        e = self.evidence(); self.s.add_evidence(ORG, self.case["id"], e.id, "", PREP)
        raw = self.w.store.get("forensic_case", f"{ORG}:{self.case['id']}"); raw["evidence"][0]["file_hash"] = "0" * 64
        self.w.store.put("forensic_case", f"{ORG}:{self.case['id']}", raw, org_id=ORG)
        v = self.s.verify_custody(ORG, self.case["id"]); self.assertFalse(v["ok"]); self.assertFalse(v["evidence"][0]["hash_matches"])


class RunAndFindings(Base):
    def test_run_over_the_real_ledger(self):
        run = self.s.run_analytics(ORG, self.case["id"], {"period_id": self.w.jan.id}, ["same_person", "weekend", "duplicates", "late_posting"], {"late_days": 5}, PREP)
        self.assertEqual(run["journals_examined"], 8)
        sp = [r for r in run["results"] if r["id"] == "same_person"][0]; self.assertEqual(sp["hit_count"], 8)      # fixture creates and posts as the same user
        self.assertIn("INDICATORS ONLY", run["kind"]); self.assertEqual(len(run["fingerprint"]), 64)
        self.assertEqual(self.s.get_run(ORG, run["id"])["fingerprint"], run["fingerprint"])
        self.assertEqual(self.s.list_runs(ORG, self.case["id"])[0]["indicator_count"], sum(1 for r in run["results"] if r["status"] == "INDICATORS"))
        self.assertIn("ANALYTICS_RUN", [e["action"] for e in self.s.get_case(ORG, self.case["id"])["custody"]])

    def test_scope_by_dates_and_drafts_are_excluded(self):
        w = self.w
        j = w.acc.create_draft_journal(ORG, date(2026, 1, 28), "draft only", "USD", [__import__("asavexa.accounting.services.engine", fromlist=["LineInput"]).LineInput(w.a["5100"].id, debit_amount=Decimal("1")), __import__("asavexa.accounting.services.engine", fromlist=["LineInput"]).LineInput(w.a["1000"].id, credit_amount=Decimal("1"))], created_by=PREP)
        run = self.s.run_analytics(ORG, self.case["id"], {"start": "2026-01-01", "end": "2026-01-31"}, ["weekend"], None, PREP)
        self.assertEqual(run["journals_examined"], 8)
        run2 = self.s.run_analytics(ORG, self.case["id"], {"start": "2026-02-01", "end": "2026-02-28"}, ["weekend"], None, PREP); self.assertEqual(run2["journals_examined"], 3)
        for bad in ({"start": "x", "end": "y"}, {"start": "2026-02-01", "end": "2026-01-01"}, {}, {"period_id": "nope"}):
            with self.assertRaises(Exception, msg=str(bad)): self.s.run_analytics(ORG, self.case["id"], bad, ["weekend"], None, PREP)

    def test_finding_lifecycle_and_separation_of_duties(self):
        jid = self.w.acc.journals.list_for_org(ORG)[0].id
        f = self.s.create_finding(ORG, self.case["id"], "Rent paid twice", "Two identical rent payments were posted two days apart without evidence.", "HIGH", [jid], [], None, PREP)
        self.assertEqual((f["status"], len(f["journals"])), ("DRAFT", 1))
        with self.assertRaises(ForensicStateError): self.s.approve_finding(ORG, f["id"], REVIEWER, "")
        self.s.submit_finding(ORG, f["id"], PREP2)
        for who in (PREP, PREP2):
            with self.assertRaises(ForensicForbiddenError): self.s.approve_finding(ORG, f["id"], who, "")
        with self.assertRaises(ForensicError): self.s.reject_finding(ORG, f["id"], REVIEWER, "no")
        self.assertEqual(self.s.reject_finding(ORG, f["id"], REVIEWER, "Needs the bank statement")["status"], "REJECTED")
        e = self.evidence(); self.s.add_evidence(ORG, self.case["id"], e.id, "", PREP)
        f = self.s.update_finding(ORG, f["id"], "Rent paid twice", "Two identical rent payments were posted two days apart; bank statement attached.", "HIGH", [jid], [e.id], PREP)
        self.assertEqual((f["status"], f["version"]), ("DRAFT", 2))
        self.s.submit_finding(ORG, f["id"], PREP)
        self.assertEqual(self.s.approve_finding(ORG, f["id"], REVIEWER, "Agreed")["status"], "APPROVED")
        with self.assertRaises(ForensicStateError): self.s.update_finding(ORG, f["id"], "x" * 5, "y" * 30, "LOW", [], [], PREP)
        with self.assertRaises(ForensicStateError): self.s.discard_finding(ORG, f["id"], PREP)

    def test_finding_validation(self):
        base = (ORG, self.case["id"])
        with self.assertRaises(ForensicError): self.s.create_finding(*base, "Title", "short", "LOW", [], [], None, PREP)
        with self.assertRaises(ForensicError): self.s.create_finding(*base, "Title", "x" * 30, "EXTREME", [], [], None, PREP)
        with self.assertRaises(ForensicNotFoundError): self.s.create_finding(*base, "Title", "x" * 30, "LOW", ["no-journal"], [], None, PREP)
        with self.assertRaises(ForensicError): self.s.create_finding(*base, "Title", "x" * 30, "LOW", [], [self.evidence().id], None, PREP)      # evidence not in the case
        other = self.s.create_case(ORG, "Another case", "", "OTHER", PREP)
        run = self.s.run_analytics(ORG, other["id"], {"period_id": self.w.jan.id}, ["weekend"], None, PREP)
        with self.assertRaises(ForensicNotFoundError): self.s.create_finding(*base, "Title", "x" * 30, "LOW", [], [], run["id"], PREP)

    def test_a_journal_from_another_org_cannot_be_cited(self):
        with self.assertRaises(ForensicNotFoundError): self.s.create_finding(OTHER, self.s.create_case(OTHER, "Other case", "", "OTHER", PREP)["id"], "Title", "x" * 30, "LOW", [self.w.acc.journals.list_for_org(ORG)[0].id], [], None, PREP)


class Reports(Base):
    def approved_report(self):
        jid = self.w.acc.journals.list_for_org(ORG)[0].id
        f = self.s.create_finding(ORG, self.case["id"], "=SUM(1)+1", "x" * 30, "LOW", [jid], [], None, PREP)
        self.s.submit_finding(ORG, f["id"], PREP); self.s.approve_finding(ORG, f["id"], REVIEWER, "")
        r = self.s.create_report(ORG, self.case["id"], "Interim report", PREP); self.s.submit_report(ORG, r["id"], PREP)
        return self.s.approve_report(ORG, r["id"], REVIEWER, "ok")

    def test_report_freezes_only_approved_findings_and_needs_second_person(self):
        d = self.s.create_finding(ORG, self.case["id"], "Draft one", "x" * 30, "LOW", [], [], None, PREP)
        r = self.approved_report()
        self.assertEqual(len(r["snapshot"]["findings"]), 1); self.assertNotIn(d["id"], [f["id"] for f in r["snapshot"]["findings"]])
        self.assertTrue(self.s.get_report(ORG, r["id"])["intact"])
        fresh = self.s.create_report(ORG, self.case["id"], "Another", PREP); self.s.submit_report(ORG, fresh["id"], PREP)
        with self.assertRaises(ForensicForbiddenError): self.s.approve_report(ORG, fresh["id"], PREP, "")
        with self.assertRaises(ForensicStateError): self.s.export_csv(ORG, fresh["id"], PREP)

    def test_export_is_labelled_and_neutralises_formulas(self):
        r = self.approved_report(); out = self.s.export_csv(ORG, r["id"], PREP)
        self.assertTrue(out["filename"].endswith("-report.csv")); self.assertIn("STRICTLY CONFIDENTIAL", out["content"]); self.assertIn("not proof of wrongdoing", out["content"])
        self.assertIn("'=SUM(1)+1", out["content"]); self.assertNotIn(",=SUM", out["content"]); self.assertNotIn("\n=SUM", out["content"])
        self.assertEqual(self.events[-1][0], "FORENSIC_REPORT_EXPORTED")

    def test_tampered_report_cannot_be_approved_or_exported(self):
        jid = self.w.acc.journals.list_for_org(ORG)[0].id
        r = self.s.create_report(ORG, self.case["id"], "Report", PREP); self.s.submit_report(ORG, r["id"], PREP)
        raw = self.w.store.get("forensic_report", f"{ORG}:{r['id']}"); raw["snapshot"]["case"]["title"] = "Changed"; self.w.store.put("forensic_report", f"{ORG}:{r['id']}", raw, org_id=ORG)
        self.assertFalse(self.s.get_report(ORG, r["id"])["intact"])
        with self.assertRaises(ForensicStateError): self.s.approve_report(ORG, r["id"], REVIEWER, "")

    def test_report_records_custody_state_at_freeze(self):
        e = self.evidence(); self.s.add_evidence(ORG, self.case["id"], e.id, "", PREP)
        r = self.s.create_report(ORG, self.case["id"], "Report", PREP)
        self.assertTrue(r["snapshot"]["integrity"]["ok"]); self.assertEqual(len(r["snapshot"]["evidence"]), 1); self.assertTrue(r["snapshot"]["limitations"])

    def test_every_step_lands_in_the_custody_chain(self):
        self.approved_report()
        c = self.s.get_case(ORG, self.case["id"])
        self.assertEqual([e["action"] for e in c["custody"]], ["CASE_OPENED", "FINDING_DRAFTED", "FINDING_SUBMITTED", "FINDING_APPROVED", "REPORT_FROZEN", "REPORT_SUBMITTED", "REPORT_APPROVED"])
        self.assertTrue(c["custody_check"]["ok"])
        self.s.close_case(ORG, self.case["id"], REVIEWER, "done")
        self.assertEqual(self.s.get_case(ORG, self.case["id"])["custody"][-1]["action"], "CASE_CLOSED")

    def test_audit_trail(self):
        self.approved_report()
        names = [e[0] for e in self.events]
        for n in ("FORENSIC_CASE_OPENED", "FORENSIC_FINDING_CREATED", "FORENSIC_FINDING_APPROVED", "FORENSIC_REPORT_CREATED", "FORENSIC_REPORT_APPROVED"): self.assertIn(n, names)


class Permissions(unittest.TestCase):
    def test_operational_roles_cannot_see_investigations(self):
        for r in (Role.ACCOUNTANT, Role.FINANCE_OFFICER, Role.ADMINISTRATOR, Role.READ_ONLY, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER):
            self.assertNotIn(FORENSIC_READ, ROLE_PERMISSIONS[r], r)
        self.assertEqual({p for p in ROLE_PERMISSIONS[Role.AUDITOR] if p.startswith("forensic")}, {FORENSIC_READ, FORENSIC_PREPARE})
        for r in (Role.MANAGER, Role.APPROVER):
            self.assertEqual({p for p in ROLE_PERMISSIONS[r] if p.startswith("forensic")}, {FORENSIC_READ, FORENSIC_APPROVE})
        self.assertTrue({FORENSIC_READ, FORENSIC_PREPARE, FORENSIC_APPROVE} <= ROLE_PERMISSIONS[Role.OWNER])


if __name__ == "__main__":
    unittest.main()
