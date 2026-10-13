"""Stage 12: the shared status vocabulary. The coverage tests are the point: if a module adds a status and nobody maps it, these fail."""
import enum
import json
import re
import unittest

from test_passport import World
from asavexa.assurance import vocabulary as V
from asavexa.assurance.service import AssuranceService
from asavexa.evidence.domain.enums import EvidenceType
from asavexa.security.store import MemoryDocStore


def _enum_values(e):
    return {m.value if isinstance(m.value, str) else m.name for m in e}


def native_statuses():
    from asavexa.accounting.domain.enums import JournalStatus
    from asavexa.agents.service import DECISION_STATES
    from asavexa.analysis.service import STATUSES as ANALYSIS
    from asavexa.compliance.domain.enums import FindingStatus, RemediationStatus
    from asavexa.evidence.domain.enums import EvidenceStatus
    from asavexa.evidencereview.service import STATUSES as CASES
    from asavexa.period_close.domain.enums import PeriodCloseStatus
    from asavexa.reconciliation.domain.enums import BankTransactionStatus, ReconciliationStatus
    from asavexa.standards.registry import STATUSES as SOURCES
    return {
        "journal": _enum_values(JournalStatus), "evidence": _enum_values(EvidenceStatus), "bank_transaction": _enum_values(BankTransactionStatus),
        "reconciliation": _enum_values(ReconciliationStatus), "period_close": _enum_values(PeriodCloseStatus), "finding": _enum_values(FindingStatus),
        "remediation": _enum_values(RemediationStatus), "evidence_review_case": set(CASES), "standards_source": set(SOURCES),
        "analysis_report": set(ANALYSIS), "agent_decision": set(DECISION_STATES),
    }


class CoverageTests(unittest.TestCase):
    def test_every_native_status_is_mapped_and_nothing_extra_is(self):
        native = native_statuses()
        self.assertEqual(set(native), set(V.TABLE), "a record type is missing from, or extra in, the vocabulary")
        for rtype, statuses in native.items():
            self.assertEqual(set(V.TABLE[rtype]), statuses, f"{rtype}: the vocabulary and the module disagree")

    def test_agent_decision_states_in_the_source_are_all_declared(self):
        import inspect
        from asavexa.agents import service
        from asavexa.agents.service import DECISION_STATES
        src = inspect.getsource(service)
        assigned = set(re.findall(r'\["state"\]\s*=\s*"([A-Z_]+)"', src)) | set(re.findall(r'"state":\s*"([A-Z_]+)"', src))
        assigned |= set(re.findall(r'\(\s*"(APPROVED)"\s+if', src)) | {"REJECTED"}
        self.assertTrue(assigned <= set(DECISION_STATES), assigned - set(DECISION_STATES))

    def test_the_table_only_uses_known_facets_and_flags(self):
        for rtype, rows in V.TABLE.items():
            for status, row in rows.items():
                self.assertTrue(set(row["facets"]) <= set(V.FACETS), (rtype, status))
                self.assertIn(row["flag"], (None,) + V.FLAGS, (rtype, status))
                self.assertTrue(row["headline"], (rtype, status))
        self.assertEqual(set(V.FACET_TEXT), set(V.FACETS)); self.assertEqual(set(V.FLAG_TEXT), set(V.FLAGS))

    def test_independent_verification_is_only_claimed_where_the_system_enforces_it(self):
        allowed = {("finding", "VERIFIED"), ("finding", "CLOSED"), ("remediation", "VERIFIED"), ("evidence_review_case", "VERIFIED"),
                   ("standards_source", "APPROVED"), ("standards_source", "SUPERSEDED"), ("agent_decision", "APPROVED"), ("agent_decision", "USED")}
        found = {(t, s) for t, rows in V.TABLE.items() for s, r in rows.items() if "independently_verified" in r["facets"]}
        self.assertEqual(found, allowed)

    def test_drafts_claim_nothing_and_flagged_rows_are_never_relied_on(self):
        for rtype, rows in V.TABLE.items():
            for status, row in rows.items():
                c = V.classify(rtype, status)
                if status == "DRAFT":
                    self.assertEqual(c["facets"], [], rtype)
                if row["flag"]:
                    self.assertFalse(c["can_rely_on"], (rtype, status))
                self.assertFalse(c["can_rely_on"] and c["facets"] == ["recorded"], (rtype, status))

    def test_a_bare_record_is_never_relied_on(self):
        self.assertFalse(V.classify("journal", "POSTED")["can_rely_on"])
        self.assertTrue(V.classify("bank_transaction", "RECONCILED")["can_rely_on"])


class ClassifyTests(unittest.TestCase):
    def test_evidence_verified_by_another_person_is_independent(self):
        c = V.classify("evidence", "VERIFIED", {"uploaded_by": "a", "verified_by": "b"})
        self.assertIn("independently_verified", c["facets"]); self.assertTrue(c["can_rely_on"])

    def test_evidence_verified_by_its_uploader_is_not(self):
        c = V.classify("evidence", "VERIFIED", {"uploaded_by": "a", "verified_by": "a"})
        self.assertNotIn("independently_verified", c["facets"]); self.assertEqual(c["headline"], "Verified by its own uploader")

    def test_evidence_without_facts_claims_no_independence(self):
        self.assertNotIn("independently_verified", V.classify("evidence", "VERIFIED")["facets"])
        self.assertNotIn("independently_verified", V.classify("evidence", "VERIFIED", {"verified_by": "b"})["facets"])

    def test_a_table_row_is_not_changed_by_classifying(self):
        before = json.dumps(V.TABLE, sort_keys=True)
        V.classify("evidence", "VERIFIED", {"uploaded_by": "a", "verified_by": "b"})
        self.assertEqual(before, json.dumps(V.TABLE, sort_keys=True))

    def test_unknown_things_raise_or_say_not_mapped(self):
        for args in (("nope", "X"), ("finding", "WEIRD"), ("finding", None)):
            with self.assertRaises(V.UnknownStatus):
                V.classify(*args)
            u = V.safe_classify(*args)
            self.assertEqual((u["headline"], u["facets"], u["can_rely_on"]), ("Not mapped", [], False))

    def test_the_vocabulary_is_plain_data(self):
        v = V.vocabulary()
        json.dumps(v)
        self.assertEqual([f["code"] for f in v["facets"]], list(V.FACETS))
        self.assertEqual({r["type"] for r in v["records"]}, set(V.TABLE))
        self.assertIn("not a score", v["note"])


class SummaryTests(unittest.TestCase):
    def test_counts_by_record_type(self):
        svc = AssuranceService({"finding": lambda org: [("f1", "OPEN", {}), ("f2", "VERIFIED", {}), ("f3", "CLOSED", {})],
                                "evidence": lambda org: [("e1", "UPLOADED", {}), ("e2", "VERIFIED", {"uploaded_by": "a", "verified_by": "b"}), ("e3", "REJECTED", {}), ("e4", "CONFLICTING", {})]})
        s = svc.summary("o")
        by = {r["type"]: r for r in s["records"]}
        self.assertEqual(s["covered"], ["evidence", "finding"])
        f = by["finding"]
        self.assertEqual((f["total"], f["facets"]["recorded"], f["facets"]["independently_verified"], f["can_rely_on"]), (3, 3, 2, 2))
        e = by["evidence"]
        self.assertEqual((e["total"], e["facets"]["independently_verified"], e["flags"]["REJECTED"], e["flags"]["CONTESTED"], e["can_rely_on"]), (4, 1, 1, 1, 1))
        self.assertEqual({a["id"] for a in e["attention"]}, {"e3", "e4"})

    def test_a_broken_provider_is_reported_not_hidden(self):
        def boom(org): raise RuntimeError("db down")
        s = AssuranceService({"finding": boom, "evidence": lambda org: []}).summary("o")
        by = {r["type"]: r for r in s["records"]}
        self.assertFalse(by["finding"]["available"]); self.assertTrue(by["evidence"]["available"])

    def test_an_unmapped_status_is_counted_as_such_and_never_as_assured(self):
        s = AssuranceService({"finding": lambda org: [("f1", "SOMETHING_NEW", {})]}).summary("o")
        r = s["records"][0]
        self.assertEqual((r["total"], r["unmapped"], r["can_rely_on"], sum(r["facets"].values())), (1, 1, 0, 0))

    def test_providers_are_called_with_the_organisation_only(self):
        seen = []
        AssuranceService({"finding": lambda org: seen.append(org) or []}).summary("org-1")
        self.assertEqual(seen, ["org-1"])

    def test_examples_are_capped(self):
        s = AssuranceService({"evidence": lambda org: [(f"e{i}", "REJECTED", {}) for i in range(20)]}).summary("o")
        self.assertEqual(len(s["records"][0]["attention"]), 5)
        self.assertEqual(s["records"][0]["flags"]["REJECTED"], 20)


class RealRecordsTests(unittest.TestCase):
    """The same providers deps.py builds, over the real services."""

    def setUp(self):
        from test_evidence_review import make
        self.w = World(); self.er = make(self.w); self.o = self.w.org.id
        w = self.w
        self.svc = AssuranceService({
            "evidence": lambda org: [(r.id, r.status.value, {"uploaded_by": r.uploaded_by, "verified_by": r.verified_by}) for r in w.vault.list_for_org(org)],
            "finding": lambda org: [(f.id, f.status.value, {}) for f in w.compliance.list_findings(org)],
            "evidence_review_case": lambda org: [(c["id"], c["status"], {}) for c in self.er.list_cases(org)],
        })

    def by(self, org=None):
        return {r["type"]: r for r in self.svc.summary(org or self.o)["records"]}

    def test_follows_a_case_from_open_to_verified(self):
        w, o = self.w, self.o
        before = self.by()
        findings_before = before["finding"]["total"]; ev_before = before["evidence"]["facets"]["independently_verified"]
        c = self.er.open_case(o, w.period.id, "income_statement", w.accountant.id)
        s = self.by()
        self.assertEqual((s["finding"]["total"] - findings_before, s["finding"]["facets"]["independently_verified"], s["evidence_review_case"]["facets"]["independently_verified"]), (1, 0, 0))
        self.er.plan_action(o, c["id"], "fix", w.accountant.id, w.owner.id)
        ev = w.vault.upload_evidence(o, EvidenceType.CONTRACT, b"x", "x.pdf", "application/pdf", uploaded_by=w.accountant.id, linked_journal_id=w.rent_journal.id)
        self.assertEqual(self.by()["evidence"]["facets"]["independently_verified"], ev_before)      # uploaded, not yet verified
        w.vault.verify_evidence(o, ev.id, actor=w.approver.id)
        self.assertEqual(self.by()["evidence"]["facets"]["independently_verified"], ev_before + 1)  # verified by a different person
        self.er.complete_action(o, c["id"], w.accountant.id, "done")
        self.er.verify_outcome(o, c["id"], w.approver.id, "r", "c")
        s = self.by()
        self.assertEqual((s["finding"]["facets"]["independently_verified"] - before["finding"]["facets"]["independently_verified"], s["evidence_review_case"]["facets"]["independently_verified"]), (1, 1))

    def test_another_organisation_sees_nothing_of_ours(self):
        w = self.w
        self.er.open_case(self.o, w.period.id, "income_statement", w.accountant.id)
        other = self.by("some-other-org")
        self.assertEqual([r["total"] for r in other.values()], [0, 0, 0])


class RouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib
        import harness_security_routers  # noqa: F401  (stands in for fastapi)
        cls.r = importlib.import_module("asavexa.api.routers.assurance")

    def test_vocabulary_and_summary(self):
        self.assertEqual(len(self.r.vocabulary()["facets"]), 6)
        svc = AssuranceService({"finding": lambda org: [("f", "OPEN", {})]})
        self.assertEqual(self.r.summary("o", svc)["records"][0]["total"], 1)

    def test_it_is_read_only_and_needs_audit_read(self):
        import inspect
        src = inspect.getsource(self.r)
        self.assertIn("AUDIT_READ", src)
        self.assertNotIn("@router.post", src); self.assertNotIn("@router.put", src); self.assertNotIn("@router.delete", src); self.assertNotIn("@router.patch", src)


if __name__ == "__main__":
    unittest.main()
