"""Cybersecurity: assets, vulnerabilities (deadlines, verification, risk acceptance), incidents, access reviews, posture reports, isolation."""
import csv
import io
import unittest
from datetime import date, datetime, timezone

from analysis_fixture import ORG, OTHER, World
from asavexa.cyber.errors import CyberError, CyberForbiddenError, CyberNotFoundError, CyberStateError
from asavexa.cyber.service import CyberService
from asavexa.evidence.domain.enums import EvidenceType
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, CYBER_APPROVE, CYBER_PREPARE, ROLE_PERMISSIONS

U1, U2, U3 = "user-1", "user-2", "user-3"


class Clock:
    def __init__(self): self.d = date(2026, 2, 15)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = CyberService(self.w.store, self.w.vault, log=lambda *a: self.events.append(a), now=self.clock)

    def asset(self, name="Core banking server", **kw):
        d = dict(name=name, type="SERVER", owner="IT lead", criticality="HIGH", data_class="CONFIDENTIAL"); d.update(kw)
        return self.svc.create_asset(ORG, d, U1)

    def vuln(self, a=None, sev="HIGH", found="2026-02-10", **kw):
        a = a or self.asset()
        d = dict(asset_id=a["id"], title="Outdated TLS library", severity=sev, source="Quarterly scan", found_date=found); d.update(kw)
        return self.svc.create_vulnerability(ORG, d, U1)

    def incident(self, **kw):
        d = dict(title="Phishing email opened", description="A finance user clicked a link", category="PHISHING", severity="HIGH", detected_date="2026-02-12", personal_data_involved=False); d.update(kw)
        return self.svc.create_incident(ORG, d, U1)

    def resolved(self, **kw):
        n = self.incident(**kw)
        self.svc.investigate_incident(ORG, n["id"], "", U1); self.svc.contain_incident(ORG, n["id"], "Account disabled", U1); return self.svc.resolve_incident(ORG, n["id"], "Link led to a credential harvesting page", U1)

    def evidence(self):
        return self.w.vault.upload_evidence(ORG, list(EvidenceType)[0], b"patch confirmation" * 4, "patch.pdf", "application/pdf", uploaded_by=U1)


class Assets(Base):
    def test_create_validate_duplicate_retire(self):
        a = self.asset(); self.assertEqual((a["ref"], a["status"], a["criticality"], a["open_vulnerabilities"]), ("AS-001", "ACTIVE", "HIGH", 0))
        for bad in (dict(name="x"), dict(name="Fine", type="TOASTER"), dict(name="Fine", criticality="EXTREME"), dict(name="Fine", data_class="SECRET"), dict(name="Fine", owner="")):
            with self.assertRaises(CyberError, msg=str(bad)): self.svc.create_asset(ORG, {**dict(name="Fine", owner="IT"), **bad}, U1)
        with self.assertRaises(CyberError): self.asset(name=" core BANKING server ")
        v = self.vuln(a)
        with self.assertRaises(CyberStateError): self.svc.retire_asset(ORG, a["id"], "decommissioned", U1)
        self.svc.mark_fixed(ORG, v["id"], "Library upgraded", [], U1); self.svc.verify_fix(ORG, v["id"], U2)
        self.assertEqual(self.svc.retire_asset(ORG, a["id"], "decommissioned", U1)["status"], "RETIRED")
        with self.assertRaises(CyberStateError): self.svc.update_asset(ORG, a["id"], {"owner": "Someone"}, U1)
        with self.assertRaises(CyberStateError): self.vuln(a)
        self.asset()  # name free again

    def test_update_keeps_fields_and_counts(self):
        a = self.asset(location="Lagos"); b = self.svc.update_asset(ORG, a["id"], {"owner": "Head of IT"}, U2)
        self.assertEqual((b["location"], b["owner"], b["name"]), ("Lagos", "Head of IT", "Core banking server"))
        self.vuln(a); self.assertEqual(self.svc.list_assets(ORG)[0]["open_vulnerabilities"], 1); self.assertEqual(len(self.svc.get_asset(ORG, a["id"])["vulnerabilities"]), 1)


class Vulnerabilities(Base):
    def test_deadlines_from_policy_at_recording_time(self):
        v = self.vuln(sev="CRITICAL", found="2026-02-10"); self.assertEqual((v["ref"], v["status"], v["sla_days"], v["due"], v["flags"]), ("V-001", "OPEN", 7, "2026-02-17", []))
        self.svc.set_policy(ORG, {"sla_days": {"CRITICAL": 3}}, U2)
        self.assertEqual(self.svc.get_vulnerability(ORG, v["id"])["due"], "2026-02-17")  # not retroactive
        a = self.svc.list_assets(ORG)[0]; self.assertEqual(self.vuln(a, sev="CRITICAL", found="2026-02-10")["due"], "2026-02-13")
        self.assertEqual(self.vuln(a, sev="LOW", found="2026-02-10")["due"], "2026-08-09")

    def test_validation(self):
        a = self.asset(); base = dict(asset_id=a["id"], title="Weak cipher", severity="LOW", source="Pen test report")
        for k, v in (("title", "ab"), ("severity", "SEVERE"), ("source", ""), ("cve", "CVE-24-1"), ("cve", "nonsense"), ("found_date", "2026-03-01"), ("found_date", "2026-02-30"), ("asset_id", "nope")):
            with self.assertRaises(CyberError, msg=k): self.svc.create_vulnerability(ORG, {**base, k: v}, U1)
        self.assertEqual(self.svc.create_vulnerability(ORG, {**base, "cve": "cve-2024-12345"}, U1)["cve"], "CVE-2024-12345")

    def test_overdue_flag_and_days(self):
        v = self.vuln(sev="HIGH", found="2026-02-10"); self.assertEqual(v["due"], "2026-03-12")
        self.clock.d = date(2026, 3, 20); x = self.svc.get_vulnerability(ORG, v["id"]); self.assertEqual((x["flags"], x["days_overdue"]), (["OVERDUE"], 8))
        self.svc.mark_fixed(ORG, v["id"], "Patched the library", [], U1); self.assertEqual(self.svc.get_vulnerability(ORG, v["id"])["flags"], [])

    def test_fix_and_verify_two_people(self):
        e = self.evidence(); v = self.vuln()
        with self.assertRaises(CyberStateError): self.svc.verify_fix(ORG, v["id"], U2)
        with self.assertRaises(CyberError): self.svc.mark_fixed(ORG, v["id"], "no", [], U1)
        with self.assertRaises(CyberError): self.svc.mark_fixed(ORG, v["id"], "Upgraded the library", ["missing"], U1)
        self.assertEqual(self.svc.start_vulnerability(ORG, v["id"], "", U1)["status"], "IN_PROGRESS")
        f = self.svc.mark_fixed(ORG, v["id"], "Upgraded the library to 3.2", [e.id], U1); self.assertEqual((f["status"], f["fix_evidence"][0]["filename"], f["fixed_by"]), ("FIXED", "patch.pdf", U1))
        with self.assertRaises(CyberForbiddenError): self.svc.verify_fix(ORG, v["id"], U1)
        with self.assertRaises(CyberForbiddenError): self.svc.reject_fix(ORG, v["id"], U1, "Not really fixed")
        with self.assertRaises(CyberError): self.svc.reject_fix(ORG, v["id"], U2, "no")
        r = self.svc.reject_fix(ORG, v["id"], U2, "Scan still shows the old version"); self.assertEqual((r["status"], r["fixed_by"]), ("OPEN", None))
        self.svc.mark_fixed(ORG, v["id"], "Redeployed the patched build", [], U3); x = self.svc.verify_fix(ORG, v["id"], U2, "Rescan clean")
        self.assertEqual((x["status"], x["verified_by"]), ("VERIFIED", U2))
        for f2 in (lambda: self.svc.start_vulnerability(ORG, v["id"], "", U1), lambda: self.svc.mark_fixed(ORG, v["id"], "Again and again", [], U1), lambda: self.svc.request_acceptance(ORG, v["id"], "x" * 25, "2026-03-01", U1)):
            with self.assertRaises(CyberStateError): f2()

    def test_risk_acceptance_flow(self):
        v = self.vuln()
        for reason, until, exc in (("too short", "2026-03-01", CyberError), ("The vendor patch breaks the payments interface until March.", "2026-02-10", CyberError), ("The vendor patch breaks the payments interface until March.", "2026-06-01", CyberError),
                                   ("The vendor patch breaks the payments interface until March.", "soon", CyberError)):
            with self.assertRaises(exc, msg=until): self.svc.request_acceptance(ORG, v["id"], reason, until, U1)
        r = self.svc.request_acceptance(ORG, v["id"], "The vendor patch breaks the payments interface until March.", "2026-03-31", U1); self.assertEqual(r["status"], "ACCEPTANCE_PENDING")
        with self.assertRaises(CyberForbiddenError): self.svc.approve_acceptance(ORG, v["id"], U1)
        with self.assertRaises(CyberForbiddenError): self.svc.reject_acceptance(ORG, v["id"], U1, "Rejecting my own request")
        with self.assertRaises(CyberError): self.svc.reject_acceptance(ORG, v["id"], U2, "")
        self.assertEqual(self.svc.reject_acceptance(ORG, v["id"], U2, "Compensating control missing")["status"], "OPEN")
        self.svc.request_acceptance(ORG, v["id"], "The vendor patch breaks the payments interface until March.", "2026-03-31", U1)
        a = self.svc.approve_acceptance(ORG, v["id"], U2, "Firewall rule added"); self.assertEqual((a["status"], a["accepted_until"], a["flags"]), ("ACCEPTED", "2026-03-31", []))
        self.clock.d = date(2026, 4, 2); x = self.svc.get_vulnerability(ORG, v["id"]); self.assertIn("ACCEPTANCE_EXPIRED", x["flags"])
        ov = self.svc.overview(ORG); self.assertEqual((ov["vulnerabilities"]["acceptance_expired"], len(ov["attention"]["acceptance_expired"])), (1, 1))
        with self.assertRaises(CyberError): self.svc.reopen_vulnerability(ORG, v["id"], "", U1)
        self.assertEqual(self.svc.reopen_vulnerability(ORG, v["id"], "Acceptance has expired", U1)["status"], "OPEN")

    def test_accepted_can_still_be_fixed_and_pending_acceptance_period_lapses(self):
        v = self.vuln(); self.svc.request_acceptance(ORG, v["id"], "Waiting for the supplier to ship a patch version.", "2026-02-20", U1)
        self.clock.d = date(2026, 2, 25)
        with self.assertRaises(CyberStateError): self.svc.approve_acceptance(ORG, v["id"], U2)
        w = self.vuln(a=self.svc.list_assets(ORG)[0], title="Second finding here"); self.svc.request_acceptance(ORG, w["id"], "Waiting for the supplier to ship a patch version.", "2026-03-20", U1); self.svc.approve_acceptance(ORG, w["id"], U2)
        self.assertEqual(self.svc.mark_fixed(ORG, w["id"], "Supplier patch applied", [], U1)["status"], "FIXED")

    def test_policy_validation(self):
        for bad in (dict(sla_days={"URGENT": 1}), dict(sla_days={"HIGH": 0}), dict(sla_days={"HIGH": 731}), dict(sla_days={"HIGH": "x"}), dict(sla_days={"CRITICAL": 40}), dict(sla_days=[1]), dict(acceptance_max_days=0), dict(acceptance_max_days=400), dict(sla_days={"LOW": True})):
            with self.assertRaises(CyberError, msg=str(bad)): self.svc.set_policy(ORG, bad, U2)
        p = self.svc.set_policy(ORG, dict(sla_days={"CRITICAL": 2, "HIGH": 10}, acceptance_max_days=30), U2); self.assertEqual((p["sla_days"], p["acceptance_max_days"], p["updated_by"]), ({"CRITICAL": 2, "HIGH": 10, "MEDIUM": 90, "LOW": 180}, 30, U2))
        v = self.vuln()
        with self.assertRaises(CyberError): self.svc.request_acceptance(ORG, v["id"], "Waiting for the supplier to ship a patch version.", "2026-03-31", U1)  # 44 days > 30

    def test_filters(self):
        a = self.asset(); self.vuln(a, sev="LOW"); v2 = self.vuln(a, sev="HIGH", title="Another finding"); self.svc.start_vulnerability(ORG, v2["id"], "", U1)
        self.assertEqual(len(self.svc.list_vulnerabilities(ORG, severity="high")), 1); self.assertEqual(len(self.svc.list_vulnerabilities(ORG, status="in_progress")), 1); self.assertEqual(len(self.svc.list_vulnerabilities(ORG, asset_id=a["id"])), 2)
        self.assertEqual(self.svc.list_vulnerabilities(ORG)[0]["asset_name"], "Core banking server")


class Incidents(Base):
    def test_lifecycle_two_person_closure(self):
        n = self.incident(); self.assertEqual((n["ref"], n["status"], n["timeline"][0]["event"], n["days_open"]), ("I-001", "REPORTED", "REPORTED", 3))
        for f in (lambda: self.svc.contain_incident(ORG, n["id"], "Account disabled", U1), lambda: self.svc.resolve_incident(ORG, n["id"], "Root cause text here", U1), lambda: self.svc.close_incident(ORG, n["id"], "x" * 30, "", U2)):
            with self.assertRaises(CyberStateError): f()
        self.svc.investigate_incident(ORG, n["id"], "Pulled mail logs", U1)
        with self.assertRaises(CyberError): self.svc.contain_incident(ORG, n["id"], "no", U1)
        self.clock.d = date(2026, 2, 16); c = self.svc.contain_incident(ORG, n["id"], "Disabled the account and reset the password", U1); self.assertEqual((c["status"], c["days_to_contain"]), ("CONTAINED", 4))
        with self.assertRaises(CyberError): self.svc.resolve_incident(ORG, n["id"], "short", U1)
        r = self.svc.resolve_incident(ORG, n["id"], "Link led to a credential harvesting page", U1); self.assertEqual((r["status"], r["days_to_resolve"], r["days_open"]), ("RESOLVED", 4, None))
        with self.assertRaises(CyberForbiddenError): self.svc.close_incident(ORG, n["id"], "Train staff to report suspicious mail quickly.", "", U1)
        with self.assertRaises(CyberForbiddenError): self.svc.reopen_incident(ORG, n["id"], U1, "Needs more investigation")
        with self.assertRaises(CyberError): self.svc.close_incident(ORG, n["id"], "too short", "", U2)
        x = self.svc.close_incident(ORG, n["id"], "Train staff to report suspicious mail quickly.", "", U2); self.assertEqual((x["status"], x["closed_by"]), ("CLOSED", U2))
        with self.assertRaises(CyberStateError): self.svc.add_timeline(ORG, n["id"], "Late note here", None, U1)
        self.assertEqual([t["event"] for t in x["timeline"]], ["REPORTED", "INVESTIGATING", "CONTAINED", "RESOLVED", "CLOSED"])

    def test_personal_data_needs_notification_decision(self):
        n = self.resolved(personal_data_involved=True)
        with self.assertRaises(CyberError): self.svc.close_incident(ORG, n["id"], "Review mailbox rules after any phishing event.", "", U2)
        with self.assertRaises(CyberError): self.svc.close_incident(ORG, n["id"], "Review mailbox rules after any phishing event.", "no", U2)
        x = self.svc.close_incident(ORG, n["id"], "Review mailbox rules after any phishing event.", "Counsel advised notifying the regulator; done on 20 Feb.", U2); self.assertIn("regulator", x["notification_decision"])

    def test_reopen_and_timeline(self):
        n = self.resolved()
        with self.assertRaises(CyberError): self.svc.reopen_incident(ORG, n["id"], U2, "no")
        r = self.svc.reopen_incident(ORG, n["id"], U2, "Another mailbox was also affected"); self.assertEqual((r["status"], r["resolved_by"]), ("INVESTIGATING", None))
        t = self.svc.add_timeline(ORG, n["id"], "Second mailbox found", "2026-02-14", U1); self.assertEqual(t["timeline"][-1]["date"], "2026-02-14")
        for bad in (("ab", None), ("Valid note text", "2026-03-01"), ("Valid note text", "2026-02-30")):
            with self.assertRaises(CyberError): self.svc.add_timeline(ORG, n["id"], bad[0], bad[1], U1)

    def test_validation(self):
        a = self.asset(); base = dict(title="Lost laptop", description="Left on a train", category="LOSS_OR_THEFT", severity="MEDIUM", personal_data_involved=True)
        for k, v in (("title", "ab"), ("description", "no"), ("category", "ALIENS"), ("severity", "BAD"), ("detected_date", "2026-03-01"), ("personal_data_involved", "yes"), ("personal_data_involved", None), ("asset_ids", ["nope"])):
            with self.assertRaises(CyberError, msg=k): self.svc.create_incident(ORG, {**base, k: v}, U1)
        n = self.svc.create_incident(ORG, {**base, "asset_ids": [a["id"], a["id"]]}, U1); self.assertEqual((n["asset_ids"], n["asset_names"]), ([a["id"]], ["Core banking server"]))

    def test_filter_by_status(self):
        self.incident(); n = self.incident(title="Second incident here"); self.svc.investigate_incident(ORG, n["id"], "", U1)
        self.assertEqual(len(self.svc.list_incidents(ORG, "investigating")), 1); self.assertEqual(len(self.svc.list_incidents(ORG)), 2)


class Reviews(Base):
    def review(self):
        r = self.svc.create_review(ORG, dict(name="Q1 finance system access", scope="Accounting system users", due_date="2026-03-15"), U1)
        for s, acc in (("Ada N", "Admin"), ("Bola K", "Read-only"), ("Temp contractor", "Posting")): r = self.svc.add_entry(ORG, r["id"], dict(subject=s, system="Accounting", access=acc), U1)
        return r

    def test_full_flow_and_removal_confirmation(self):
        r = self.review(); self.assertEqual((r["ref"], r["counts"]["entries"], r["counts"]["pending"]), ("AR-001", 3, 3))
        with self.assertRaises(CyberError): self.svc.submit_review(ORG, r["id"], U1)
        e = r["entries"]; self.svc.decide_entry(ORG, r["id"], e[0]["id"], "keep", "", U1); self.svc.decide_entry(ORG, r["id"], e[1]["id"], "KEEP", "Still needed", U1)
        with self.assertRaises(CyberError): self.svc.decide_entry(ORG, r["id"], e[2]["id"], "REMOVE", "", U1)
        with self.assertRaises(CyberError): self.svc.decide_entry(ORG, r["id"], e[2]["id"], "MAYBE", "x", U1)
        self.svc.decide_entry(ORG, r["id"], e[2]["id"], "REMOVE", "Contract ended in January", U1)
        with self.assertRaises(CyberStateError): self.svc.confirm_removed(ORG, r["id"], e[0]["id"], U1)
        s = self.svc.submit_review(ORG, r["id"], U1); self.assertEqual(s["status"], "SUBMITTED")
        with self.assertRaises(CyberStateError): self.svc.add_entry(ORG, r["id"], dict(subject="Late addition", system="Accounting", access="Admin"), U1)
        with self.assertRaises(CyberForbiddenError): self.svc.approve_review(ORG, r["id"], U1)
        with self.assertRaises(CyberStateError): self.svc.approve_review(ORG, r["id"], U2)  # removal not yet confirmed
        self.svc.confirm_removed(ORG, r["id"], e[2]["id"], U3)
        with self.assertRaises(CyberStateError): self.svc.confirm_removed(ORG, r["id"], e[2]["id"], U3)
        c = self.svc.approve_review(ORG, r["id"], U2, "Looks complete"); self.assertEqual((c["status"], c["counts"]["removed_confirmed"], c["decided_by"]), ("COMPLETED", 1, U2))
        with self.assertRaises(CyberStateError): self.svc.decide_entry(ORG, r["id"], e[0]["id"], "REMOVE", "Changed my mind", U1)

    def test_reject_reopens_for_changes(self):
        r = self.review()
        for x in r["entries"]: self.svc.decide_entry(ORG, r["id"], x["id"], "KEEP", "", U1)
        self.svc.submit_review(ORG, r["id"], U1)
        with self.assertRaises(CyberForbiddenError): self.svc.reject_review(ORG, r["id"], U1, "Sending myself back")
        with self.assertRaises(CyberError): self.svc.reject_review(ORG, r["id"], U2, "")
        x = self.svc.reject_review(ORG, r["id"], U2, "Ada's admin access needs a reason"); self.assertEqual(x["status"], "REJECTED")
        y = self.svc.decide_entry(ORG, r["id"], r["entries"][0]["id"], "REMOVE", "Admin access no longer justified", U1); self.assertEqual(y["counts"]["remove"], 1)
        self.svc.confirm_removed(ORG, r["id"], r["entries"][0]["id"], U1); self.assertEqual(self.svc.submit_review(ORG, r["id"], U3)["submitted_by"], U3)

    def test_validation_overdue_listing(self):
        for bad in (dict(name="ab", scope="Accounting", due_date="2026-03-15"), dict(name="Valid name", scope="x", due_date="2026-03-15"), dict(name="Valid name", scope="Accounting", due_date="2026-01-01"), dict(name="Valid name", scope="Accounting", due_date="soon")):
            with self.assertRaises(CyberError): self.svc.create_review(ORG, bad, U1)
        r = self.review()
        for bad in (dict(subject="A", system="Accounting", access="Admin"), dict(subject="Valid", system="", access="Admin"), dict(subject="Valid", system="Accounting", access="")):
            with self.assertRaises(CyberError): self.svc.add_entry(ORG, r["id"], bad, U1)
        self.clock.d = date(2026, 3, 20); self.assertTrue(self.svc.get_review(ORG, r["id"])["overdue"]); self.assertNotIn("entries", self.svc.list_reviews(ORG)[0]); self.assertEqual(self.svc.overview(ORG)["reviews"]["overdue"], 1)
        with self.assertRaises(CyberNotFoundError): self.svc.decide_entry(ORG, r["id"], "nope", "KEEP", "", U1)


class Overview(Base):
    def test_posture_figures(self):
        a = self.asset(); b = self.asset(name="Marketing website", criticality="LOW")
        v1 = self.vuln(a, sev="CRITICAL", found="2026-01-01"); self.vuln(b, sev="MEDIUM"); v3 = self.vuln(a, sev="HIGH", title="Fixed finding", found="2026-02-01")
        self.svc.mark_fixed(ORG, v3["id"], "Patched it today", [], U1); self.svc.verify_fix(ORG, v3["id"], U2)
        n = self.incident(); self.svc.investigate_incident(ORG, n["id"], "", U1); self.svc.contain_incident(ORG, n["id"], "Account disabled now", U1)
        ov = self.svc.overview(ORG); vu = ov["vulnerabilities"]
        self.assertEqual((vu["open"], vu["overdue"], vu["fixed_and_verified"], vu["average_days_to_fix"]), (2, 1, 1, 14.0))
        crit = next(x for x in vu["by_severity"] if x["severity"] == "CRITICAL"); self.assertEqual((crit["open"], crit["overdue"]), (1, 1))
        self.assertEqual((ov["assets"]["active"], ov["assets"]["by_criticality"]["HIGH"], ov["assets"]["high_value_with_overdue_serious_vulns"]), (2, 1, ["AS-001"]))
        self.assertEqual((ov["incidents"]["open"], ov["incidents"]["open_critical_or_high"], ov["incidents"]["average_days_to_contain"]), (1, 1, 3.0))
        self.assertEqual([x["ref"] for x in ov["attention"]["overdue"]], [v1["ref"]]); self.assertEqual((ov["counts"]["vulnerabilities_open"], ov["counts"]["incidents_open"]), (2, 1)); self.assertTrue(ov["limitations"])

    def test_empty_and_options(self):
        ov = self.svc.overview(ORG); self.assertEqual((ov["counts"]["assets"], ov["vulnerabilities"]["average_days_to_fix"], ov["incidents"]["average_days_to_contain"]), (0, None, None))
        o = self.svc.options(ORG); self.assertEqual((o["assets"], o["severities"][0], o["policy"]["sla_days"]["CRITICAL"]), ([], "CRITICAL", 7))


class Reports(Base):
    def make(self, title="Posture at February"):
        self.vuln(self.asset(name="=Evil server"), sev="CRITICAL", title="=cmd|bad"); self.incident()
        return self.svc.create_report(ORG, title, U1)

    def test_lifecycle_two_person_and_freeze(self):
        r = self.make(); self.assertEqual((r["ref"], r["status"], r["has_snapshot"]), ("R-001", "DRAFT", False))
        with self.assertRaises(CyberStateError): self.svc.export_csv(ORG, r["id"], U1)
        r = self.svc.submit_report(ORG, r["id"], U1); fp = r["fingerprint"]; self.assertEqual((r["status"], r["version"], r["snapshot"]["posture"]["vulnerabilities"]["open"]), ("SUBMITTED", 1, 1))
        self.vuln(self.svc.list_assets(ORG)[0], title="Added after freezing"); self.assertEqual(self.svc.get_report(ORG, r["id"])["fingerprint"], fp); self.assertEqual(self.svc.get_report(ORG, r["id"])["snapshot"]["posture"]["vulnerabilities"]["open"], 1)
        with self.assertRaises(CyberForbiddenError): self.svc.approve_report(ORG, r["id"], U1)
        with self.assertRaises(CyberError): self.svc.reject_report(ORG, r["id"], U2, "")
        self.assertEqual(self.svc.reject_report(ORG, r["id"], U2, "Include the new finding")["status"], "REJECTED")
        r = self.svc.submit_report(ORG, r["id"], U3); self.assertEqual((r["version"], r["snapshot"]["posture"]["vulnerabilities"]["open"]), (2, 2))
        self.assertEqual(self.svc.approve_report(ORG, r["id"], U2)["status"], "APPROVED")
        with self.assertRaises(CyberStateError): self.svc.submit_report(ORG, r["id"], U1)

    def test_csv_confidential_and_neutralised(self):
        r = self.make(title="=Posture report"); self.svc.submit_report(ORG, r["id"], U1); self.svc.approve_report(ORG, r["id"], U2)
        out = self.svc.export_csv(ORG, r["id"], U3); self.assertEqual((out["filename"], out["content_type"]), ("R-001-posture-v1.csv", "text/csv; charset=utf-8"))
        rows = list(csv.reader(io.StringIO(out["content"]))); self.assertTrue(rows[0][0].startswith("CONFIDENTIAL"))
        for h in ("VULNERABILITIES BY SEVERITY", "ASSETS BY CRITICALITY", "INCIDENTS", "ACCESS REVIEWS", "POLICY IN FORCE", "LIMITATIONS"): self.assertIn(h, out["content"])
        self.assertIn("'=Posture", out["content"])
        self.assertFalse(any(c.startswith(("=", "+", "@")) for row in rows for c in row)); self.assertTrue(any(e[0] == "CY_REPORT_EXPORTED" for e in self.events))

    def test_tamper_blocks_export(self):
        r = self.make(); self.svc.submit_report(ORG, r["id"], U1); self.svc.approve_report(ORG, r["id"], U2)
        d = self.w.store.get("cy_report", f"{ORG}:{r['id']}", for_update=True); d["snapshot"]["posture"]["vulnerabilities"]["open"] = 0; self.w.store.put("cy_report", f"{ORG}:{r['id']}", d, org_id=ORG)
        with self.assertRaises(CyberStateError): self.svc.export_csv(ORG, r["id"], U3)

    def test_title_validation(self):
        with self.assertRaises(CyberError): self.svc.create_report(ORG, "ab", U1)


class Isolation(Base):
    def test_other_org_sees_nothing(self):
        a = self.asset(); v = self.vuln(a); n = self.incident(); rv = self.svc.create_review(ORG, dict(name="Review one", scope="Accounting", due_date="2026-03-15"), U1); rp = self.svc.create_report(ORG, "Our report", U1)
        self.assertEqual((self.svc.list_assets(OTHER), self.svc.list_vulnerabilities(OTHER), self.svc.list_incidents(OTHER), self.svc.list_reviews(OTHER), self.svc.list_reports(OTHER)), ([], [], [], [], []))
        self.assertEqual(self.svc.overview(OTHER)["counts"]["assets"], 0)
        for f in (lambda: self.svc.get_asset(OTHER, a["id"]), lambda: self.svc.get_vulnerability(OTHER, v["id"]), lambda: self.svc.get_incident(OTHER, n["id"]), lambda: self.svc.get_review(OTHER, rv["id"]), lambda: self.svc.get_report(OTHER, rp["id"]),
                  lambda: self.svc.mark_fixed(OTHER, v["id"], "Not their finding", [], U1), lambda: self.svc.create_vulnerability(OTHER, dict(asset_id=a["id"], title="Cross org", severity="LOW", source="scan"), U1),
                  lambda: self.svc.create_incident(OTHER, dict(title="Cross org", description="Cross org text", category="OTHER", severity="LOW", personal_data_involved=False, asset_ids=[a["id"]]), U1)):
            with self.assertRaises(CyberNotFoundError): f()


class Audit(Base):
    def test_every_write_is_logged(self):
        v = self.vuln(); self.svc.mark_fixed(ORG, v["id"], "Patched it today", [], U1); self.svc.verify_fix(ORG, v["id"], U2); self.resolved(); self.svc.set_policy(ORG, {"acceptance_max_days": 30}, U2)
        acts = {e[0] for e in self.events}
        for a in ("CY_ASSET_CREATED", "CY_VULN_CREATED", "CY_VULN_FIXED", "CY_VULN_VERIFIED", "CY_INCIDENT_CREATED", "CY_INCIDENT_CONTAINED", "CY_INCIDENT_RESOLVED", "CY_POLICY_SET"): self.assertIn(a, acts)


class Roles(unittest.TestCase):
    def test_role_matrix(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.MANAGER): self.assertTrue(has(r, CYBER_PREPARE) and has(r, CYBER_APPROVE), r)
        self.assertTrue(has(Role.ADMINISTRATOR, CYBER_PREPARE) and not has(Role.ADMINISTRATOR, CYBER_APPROVE)); self.assertTrue(has(Role.APPROVER, CYBER_APPROVE) and not has(Role.APPROVER, CYBER_PREPARE))
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.AUDITOR, Role.FINANCE_OFFICER): self.assertFalse(has(r, CYBER_PREPARE) or has(r, CYBER_APPROVE), r)
        for r in (Role.ADMINISTRATOR, Role.AUDITOR, Role.REVIEWER, Role.MANAGER): self.assertTrue(has(r, AUDIT_READ), r)


if __name__ == "__main__":
    unittest.main()
