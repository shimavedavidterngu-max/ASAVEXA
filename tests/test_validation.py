"""Professional validation: the rules that make a review count, and the outcome computed only from signed reviews."""
import copy
import unittest

from asavexa.security import crypto
from asavexa.security.store import SqliteDocStore
from asavexa.validation.catalog import STAGE_IDS, STAGES
from asavexa.validation.errors import ProfessionalValidationError as VE, ReviewForbiddenError, ReviewNotFoundError, ReviewStateError
from asavexa.validation.service import ValidationService, sha
import test_passport as T

ORG, MGR = "org1", "mgr-user"
ALL_CONF = {k: True for k in ["no_financial_interest", "not_involved_in_preparing_records", "no_close_personal_relationship", "no_other_threat_to_objectivity"]}
SPEC_FOR = {"ACCOUNTING_TREATMENT": "IFRS", "CONTROLS": "INTERNAL_AUDIT", "EVIDENCE": "AUDIT", "REPORTING": "IFRS", "AUDIT_WORKFLOW": "AUDIT",
            "SECURITY": "CYBERSECURITY", "PROFESSIONAL_JUDGEMENT": "ACADEMIC"}


def good(concl="CONCURS", obs=None, **kw):
    c = {"conclusion": concl, "scope_reviewed": "Trial balance and journals", "basis": "IFRS as issued", "competence_confirmed": True, "observations": obs or []}
    c.update(kw); return c


class Base(unittest.TestCase):
    def setUp(self):
        self.w = T.World()
        self.logs = []
        self.kr = crypto.LocalKeyring({"k1": crypto.LocalKeyring.generate_key()}, "k1")
        self.s = ValidationService(SqliteDocStore(self.w.conn), log=lambda *a, **k: self.logs.append(a), keys=self.kr)

    def reviewer(self, spec="IFRS", name="Ada Okafor", email=None, user_id=None, body="ICAN"):
        return self.s.add_reviewer(ORG, MGR, name, email or f"{name.split()[0].lower()}@firm.test", [{"body": body, "membership_no": "12345", "jurisdiction": "Nigeria", "year_admitted": 2010}],
                                   [spec], "Firm LLP", user_id)

    def eng(self, stages=None, **kw):
        return self.s.create_engagement(ORG, MGR, "Q3 2026 validation", "desc", "2026-09-30", {"counts": {"journals": 3}}, stages, **kw)

    def ready(self, stage="ACCOUNTING_TREATMENT", user=None, open_=True):
        r = self.reviewer(SPEC_FOR[stage], user_id=user, name=f"Rev {stage[:4]}", email=f"{stage.lower()}@x.test")
        e = self.eng([stage])
        if open_: self.s.open(ORG, MGR, e["id"])
        self.s.assign(ORG, MGR, e["id"], stage, r["id"])
        return r, e["id"]

    def declare(self, eid, r, actor=None, **kw):
        manage = not r.get("user_id")
        return self.s.declare_independence(ORG, actor or r.get("user_id") or MGR, eid, r["id"], True, "", ALL_CONF, can_manage=manage,
                                           source_reference=kw.get("ref", "signed pdf ref 1" if manage else None))

    def sign(self, eid, r, stage, content=None, actor=None):
        manage = not r.get("user_id")
        who = actor or r.get("user_id") or MGR
        c = dict(content or good()); 
        if manage: c.setdefault("source_reference", "signed pdf ref 2")
        d = self.s.save_review(ORG, who, eid, stage, r["id"], c, can_manage=manage)
        rid = [x for x in d["reviews"] if x["status"] == "DRAFT" and x["reviewer_id"] == r["id"] and x["stage"] == stage][0]["id"]
        return self.s.sign_review(ORG, who, eid, rid, can_manage=manage), rid


class PanelTests(Base):
    def test_add_and_credentials_start_declared(self):
        r = self.reviewer()
        self.assertEqual(r["credentials"][0]["status"], "DECLARED"); self.assertEqual(r["credential_state"], "DECLARED_ONLY")

    def test_validation_of_inputs(self):
        for kw in ({"credentials": []}, {"credentials": [{"body": "NOPE", "membership_no": "1"}]}, {"credentials": [{"body": "ACCA", "membership_no": ""}]},
                   {"credentials": [{"body": "ACCA", "membership_no": "1", "year_admitted": 1800}]}, {"specialisms": []}, {"specialisms": ["ASTROLOGY"]}, {"email": "nope"}, {"name": " "}):
            a = dict(name="X Y", email="x@y.test", credentials=[{"body": "ACCA", "membership_no": "1"}], specialisms=["IFRS"]); a.update(kw)
            with self.assertRaises(VE, msg=str(kw)):
                self.s.add_reviewer(ORG, MGR, a["name"], a["email"], a["credentials"], a["specialisms"])

    def test_duplicate_email_and_user(self):
        self.reviewer(email="a@x.test", user_id="u1")
        with self.assertRaises(ReviewStateError): self.reviewer(email="A@x.test")
        with self.assertRaises(ReviewStateError): self.reviewer(email="b@x.test", user_id="u1")

    def test_verification_and_self_verification(self):
        r = self.reviewer(user_id="u1")
        with self.assertRaises(ReviewForbiddenError): self.s.verify_credential(ORG, "u1", r["id"], 0, True, "register")
        with self.assertRaises(VE): self.s.verify_credential(ORG, MGR, r["id"], 0, True, "")
        with self.assertRaises(VE): self.s.verify_credential(ORG, MGR, r["id"], 0, False, "register", "")   # a rejection needs a reason
        with self.assertRaises(ReviewNotFoundError): self.s.verify_credential(ORG, MGR, r["id"], 5, True, "register")
        out = self.s.verify_credential(ORG, MGR, r["id"], 0, True, "Looked up on ICAN public register 2026-10-01")
        self.assertEqual(out["credentials"][0]["status"], "VERIFIED"); self.assertEqual(out["credential_state"], "VERIFIED")
        out = self.s.verify_credential(ORG, MGR, r["id"], 0, False, "register", "Not found")
        self.assertEqual(out["credentials"][0]["status"], "REJECTED"); self.assertEqual(out["credential_state"], "DECLARED_ONLY")

    def test_update_and_add_credential(self):
        r = self.reviewer()
        out = self.s.update_reviewer(ORG, MGR, r["id"], specialisms=["TAX", "ifrs"], add_credential={"body": "ACCA", "membership_no": "9"})
        self.assertEqual(out["specialisms"], ["IFRS", "TAX"]); self.assertEqual(len(out["credentials"]), 2)
        self.assertEqual(out["credential_state"], "DECLARED_ONLY")

    def test_org_isolation(self):
        r = self.reviewer()
        with self.assertRaises(ReviewNotFoundError): self.s.set_active("other", MGR, r["id"], False)
        self.assertEqual(self.s.panel("other"), [])


class EngagementTests(Base):
    def test_create_defaults_and_validation(self):
        e = self.eng()
        self.assertEqual(e["stages"], STAGE_IDS); self.assertEqual(e["status"], "DRAFT"); self.assertEqual(e["coverage"]["outcome"], "INCOMPLETE")
        self.assertEqual(e["snapshot_hash"], sha({"counts": {"journals": 3}}))
        for kw in ({"title": ""}, {"as_of": "30/09/2026"}, {"stages": ["NOPE"]}, {"min_reviewers": {"EVIDENCE": 0}}, {"min_reviewers": {"EVIDENCE": 9}}, {"min_reviewers": {"EVIDENCE": True}}):
            a = dict(title="t", as_of="2026-09-30", stages=None, min_reviewers=None); a.update(kw)
            with self.assertRaises(VE, msg=str(kw)):
                self.s.create_engagement(ORG, MGR, a["title"], "", a["as_of"], {}, a["stages"], a["min_reviewers"])

    def test_stage_order_is_normalised(self):
        e = self.eng(["SECURITY", "accounting_treatment"])
        self.assertEqual(e["stages"], ["ACCOUNTING_TREATMENT", "SECURITY"])

    def test_assignment_needs_competence_and_activity(self):
        r = self.reviewer("TAX"); e = self.eng(["CONTROLS"])
        with self.assertRaises(VE): self.s.assign(ORG, MGR, e["id"], "CONTROLS", r["id"])      # tax specialist, controls stage
        with self.assertRaises(VE): self.s.assign(ORG, MGR, e["id"], "SECURITY", r["id"])      # not in scope
        r2 = self.reviewer("INTERNAL_AUDIT", name="Bola Ade")
        self.s.assign(ORG, MGR, e["id"], "CONTROLS", r2["id"])
        with self.assertRaises(ReviewStateError): self.s.assign(ORG, MGR, e["id"], "CONTROLS", r2["id"])
        self.s.set_active(ORG, MGR, r2["id"], False)
        e2 = self.eng(["CONTROLS"])
        with self.assertRaises(ReviewStateError): self.s.assign(ORG, MGR, e2["id"], "CONTROLS", r2["id"])

    def test_every_stage_has_a_competent_specialism(self):
        for st in STAGES: self.assertTrue(set(st["specialisms"]) & {SPEC_FOR[st["id"]]})

    def test_state_machine(self):
        r, eid = self.ready(open_=False)
        with self.assertRaises(ReviewStateError): self.s.save_review(ORG, MGR, eid, "ACCOUNTING_TREATMENT", r["id"], good(), True)   # not open
        self.s.open(ORG, MGR, eid)
        with self.assertRaises(ReviewStateError): self.s.open(ORG, MGR, eid)
        self.s.withdraw(ORG, MGR, eid, "scope changed")
        for fn in (lambda: self.s.assign(ORG, MGR, eid, "ACCOUNTING_TREATMENT", r["id"]), lambda: self.s.withdraw(ORG, MGR, eid, "x"), lambda: self.s.complete(ORG, MGR, eid)):
            with self.assertRaises(ReviewStateError): fn()
        with self.assertRaises(VE): self.s.withdraw(ORG, MGR, self.eng()["id"], " ")

    def test_snapshot_refresh_locks_after_first_signature(self):
        r, eid = self.ready(); self.declare(eid, r)
        out = self.s.refresh_snapshot(ORG, MGR, eid, {"counts": {"journals": 4}})
        self.assertEqual(out["snapshot_hash"], sha({"counts": {"journals": 4}}))
        self.sign(eid, r, "ACCOUNTING_TREATMENT")
        with self.assertRaises(ReviewStateError): self.s.refresh_snapshot(ORG, MGR, eid, {"x": 1})

    def test_unassign_blocked_after_signature_and_drops_drafts(self):
        r, eid = self.ready(); self.declare(eid, r)
        d = self.s.save_review(ORG, MGR, eid, "ACCOUNTING_TREATMENT", r["id"], {**good(), "source_reference": "ref"}, True)
        aid = d["assignments"][0]["id"]
        d = self.s.unassign(ORG, MGR, eid, aid); self.assertEqual(d["reviews"], [])
        self.s.assign(ORG, MGR, eid, "ACCOUNTING_TREATMENT", r["id"]); self.sign(eid, r, "ACCOUNTING_TREATMENT")
        aid = self.s.detail(ORG, eid)["assignments"][0]["id"]
        with self.assertRaises(ReviewStateError): self.s.unassign(ORG, MGR, eid, aid)

    def test_list_engagements(self):
        self.eng(); self.eng()
        ls = self.s.list_engagements(ORG)
        self.assertEqual(len(ls), 2); self.assertEqual(ls[0]["stages_total"], 7); self.assertEqual(ls[0]["outcome"], "INCOMPLETE")


class IndependenceAndAuthorityTests(Base):
    def test_review_needs_assignment_and_declaration(self):
        r = self.reviewer(SPEC_FOR["EVIDENCE"]); e = self.eng(["EVIDENCE"]); self.s.open(ORG, MGR, e["id"])
        with self.assertRaises(ReviewForbiddenError): self.s.save_review(ORG, MGR, e["id"], "EVIDENCE", r["id"], good(source_reference="x"), True)  # not assigned
        self.s.assign(ORG, MGR, e["id"], "EVIDENCE", r["id"])
        with self.assertRaises(ReviewStateError): self.s.save_review(ORG, MGR, e["id"], "EVIDENCE", r["id"], good(source_reference="x"), True)    # no declaration

    def test_conflict_blocks_review_and_needs_details(self):
        r, eid = self.ready()
        with self.assertRaises(VE):
            self.s.declare_independence(ORG, MGR, eid, r["id"], True, "", {**ALL_CONF, "no_financial_interest": False}, True, "ref")
        with self.assertRaises(VE):   # claims independent but a confirmation is false and no details
            self.s.declare_independence(ORG, MGR, eid, r["id"], True, "", {**ALL_CONF, "no_close_personal_relationship": False}, True, "ref")
        d = self.s.declare_independence(ORG, MGR, eid, r["id"], True, "Holds shares in client", {**ALL_CONF, "no_financial_interest": False}, True, "ref")
        self.assertFalse(d["declarations"][r["id"]]["independent"])
        with self.assertRaises(ReviewForbiddenError): self.s.save_review(ORG, MGR, eid, "ACCOUNTING_TREATMENT", r["id"], good(source_reference="x"), True)
        d = self.s.declare_independence(ORG, MGR, eid, r["id"], False, "Former CFO", ALL_CONF, True, "ref")
        self.assertFalse(d["declarations"][r["id"]]["independent"])           # independent=False overrides all-true confirmations

    def test_later_conflict_removes_the_review_from_the_count(self):
        r, eid = self.ready(); self.declare(eid, r); self.sign(eid, r, "ACCOUNTING_TREATMENT")
        self.assertTrue(self.s.detail(ORG, eid)["coverage"]["complete"])
        self.s.declare_independence(ORG, MGR, eid, r["id"], False, "New conflict discovered", ALL_CONF, True, "ref")
        d = self.s.detail(ORG, eid)
        self.assertFalse(d["coverage"]["complete"]); self.assertEqual(d["coverage"]["outcome"], "INCOMPLETE")

    def test_deactivated_reviewer_no_longer_counts(self):
        r, eid = self.ready(); self.declare(eid, r); self.sign(eid, r, "ACCOUNTING_TREATMENT")
        self.s.set_active(ORG, MGR, r["id"], False)
        self.assertEqual(self.s.detail(ORG, eid)["coverage"]["outcome"], "INCOMPLETE")

    def test_linked_reviewer_acts_only_as_themselves(self):
        r, eid = self.ready(user="u-rev")
        with self.assertRaises(ReviewForbiddenError): self.s.declare_independence(ORG, MGR, eid, r["id"], True, "", ALL_CONF, can_manage=True, source_reference="ref")   # manager cannot override
        self.declare(eid, r)
        with self.assertRaises(ReviewForbiddenError): self.s.save_review(ORG, MGR, eid, "ACCOUNTING_TREATMENT", r["id"], good(source_reference="ref"), True)
        d = self.s.save_review(ORG, "u-rev", eid, "ACCOUNTING_TREATMENT", r["id"], good())
        rid = d["reviews"][0]["id"]
        with self.assertRaises(ReviewForbiddenError): self.s.sign_review(ORG, MGR, eid, rid, can_manage=True)
        out = self.s.sign_review(ORG, "u-rev", eid, rid)
        self.assertFalse(out["reviews"][0]["on_behalf"]); self.assertEqual(out["reviews"][0]["signed_by"], "u-rev")

    def test_unlinked_reviewer_needs_manager_and_source_reference(self):
        r, eid = self.ready()
        with self.assertRaises(ReviewForbiddenError): self.s.declare_independence(ORG, "random", eid, r["id"], True, "", ALL_CONF, can_manage=False, source_reference="ref")
        with self.assertRaises(VE): self.s.declare_independence(ORG, MGR, eid, r["id"], True, "", ALL_CONF, can_manage=True)
        self.declare(eid, r)
        with self.assertRaises(VE): self.s.save_review(ORG, MGR, eid, "ACCOUNTING_TREATMENT", r["id"], good(), True)     # no source reference
        with self.assertRaises(ReviewForbiddenError): self.s.save_review(ORG, "random", eid, "ACCOUNTING_TREATMENT", r["id"], good(source_reference="ref"), False)
        out, _ = self.sign(eid, r, "ACCOUNTING_TREATMENT")
        rv = out["reviews"][0]; self.assertTrue(rv["on_behalf"]); self.assertEqual(rv["source_reference"], "signed pdf ref 2")
        self.assertTrue(out["declarations"][r["id"]]["on_behalf"])


class SigningRuleTests(Base):
    def setUp(self):
        super().setUp(); self.r, self.eid = self.ready(); self.declare(self.eid, self.r)

    def attempt(self, content):
        with self.assertRaises(VE):
            self.sign(self.eid, self.r, "ACCOUNTING_TREATMENT", content)

    def test_missing_pieces_block_signing(self):
        self.attempt(good(conclusion=None)); self.attempt(good(scope_reviewed="")); self.attempt(good(basis="")); self.attempt(good(competence_confirmed=False))

    def test_conclusion_rules(self):
        self.attempt(good("CONCURS_WITH_COMMENTS")); self.attempt(good("DISAGREES"))
        self.attempt(good("DISAGREES", [{"severity": "MINOR", "text": "small"}])); self.attempt(good("UNABLE_TO_ASSESS"))
        with self.assertRaises(VE): self.s.save_review(ORG, MGR, self.eid, "ACCOUNTING_TREATMENT", self.r["id"], good("MAYBE", source_reference="x"), True)
        with self.assertRaises(VE): self.s.save_review(ORG, MGR, self.eid, "ACCOUNTING_TREATMENT", self.r["id"], good(obs=[{"severity": "HUGE", "text": "x"}], source_reference="x"), True)
        with self.assertRaises(VE): self.s.save_review(ORG, MGR, self.eid, "ACCOUNTING_TREATMENT", self.r["id"], good(obs=[{"severity": "MINOR", "text": ""}], source_reference="x"), True)

    def test_valid_variants_sign(self):
        for c in (good("CONCURS"), good("CONCURS_WITH_COMMENTS", [{"severity": "MINOR", "text": "t"}]), good("DISAGREES", [{"severity": "MAJOR", "text": "t"}]),
                  good("UNABLE_TO_ASSESS", limitations="No access to ledger")):
            out, _ = self.sign(self.eid, self.r, "ACCOUNTING_TREATMENT", c)
            self.assertEqual([x["status"] for x in out["reviews"]].count("SIGNED"), 1)

    def test_signed_is_immutable_and_new_version_supersedes(self):
        out, rid = self.sign(self.eid, self.r, "ACCOUNTING_TREATMENT")
        signed = out["reviews"][0]; self.assertEqual(signed["version"], 1); self.assertEqual(len(signed["hash"]), 64)
        with self.assertRaises(ReviewStateError): self.s.sign_review(ORG, MGR, self.eid, rid, can_manage=True)       # re-sign
        out, rid2 = self.sign(self.eid, self.r, "ACCOUNTING_TREATMENT", good("CONCURS_WITH_COMMENTS", [{"severity": "MINOR", "text": "t"}]))
        by = {x["id"]: x for x in out["reviews"]}
        self.assertEqual(by[rid]["status"], "SUPERSEDED"); self.assertEqual(by[rid2]["version"], 2); self.assertEqual(by[rid2]["status"], "SIGNED")
        self.assertEqual(out["coverage"]["stages"][0]["status"], "COVERED_WITH_COMMENTS")                      # only the newest counts
        self.assertEqual(by[rid]["conclusion"], "CONCURS")                                                      # the old one stays on record

    def test_signed_content_cannot_be_edited_by_save(self):
        out, rid = self.sign(self.eid, self.r, "ACCOUNTING_TREATMENT")
        d = self.s.save_review(ORG, MGR, self.eid, "ACCOUNTING_TREATMENT", self.r["id"], good("DISAGREES", [{"severity": "CRITICAL", "text": "x"}], source_reference="r"), True)
        old = [x for x in d["reviews"] if x["id"] == rid][0]
        self.assertEqual(old["conclusion"], "CONCURS"); self.assertEqual(old["status"], "SIGNED")
        self.assertEqual(len(d["reviews"]), 2)

    def test_signing_captures_credential_state_at_the_time(self):
        out, _ = self.sign(self.eid, self.r, "ACCOUNTING_TREATMENT")
        self.assertEqual(out["reviews"][0]["reviewer_snapshot"]["credentials"][0]["status"], "DECLARED")
        self.assertEqual(out["coverage"]["credential_verification"], "SOME_UNVERIFIED")

    def test_specialism_removed_before_signing_blocks(self):
        self.s.save_review(ORG, MGR, self.eid, "ACCOUNTING_TREATMENT", self.r["id"], good(source_reference="r"), True)
        self.s.update_reviewer(ORG, MGR, self.r["id"], specialisms=["CYBERSECURITY"])
        rid = self.s.detail(ORG, self.eid)["reviews"][0]["id"]
        with self.assertRaises(VE): self.s.sign_review(ORG, MGR, self.eid, rid, can_manage=True)

    def test_draft_edit_replaces_not_duplicates(self):
        self.s.save_review(ORG, MGR, self.eid, "ACCOUNTING_TREATMENT", self.r["id"], good(source_reference="r"), True)
        d = self.s.save_review(ORG, MGR, self.eid, "ACCOUNTING_TREATMENT", self.r["id"], good("CONCURS_WITH_COMMENTS", [{"severity": "MINOR", "text": "t"}], source_reference="r"), True)
        self.assertEqual(len(d["reviews"]), 1); self.assertEqual(d["reviews"][0]["conclusion"], "CONCURS_WITH_COMMENTS")


class OutcomeTests(Base):
    def full(self, concl_by_stage=None, extra_min=None):
        e = self.eng(min_reviewers=extra_min); eid = e["id"]; self.s.open(ORG, MGR, eid)
        revs = {}
        for st in STAGE_IDS:
            r = self.reviewer(SPEC_FOR[st], name=f"R {st}", email=f"{st}@x.test"); revs[st] = r
            self.s.assign(ORG, MGR, eid, st, r["id"]); self.declare(eid, r)
        return eid, revs

    def test_all_concur_is_validated(self):
        eid, revs = self.full()
        for st, r in revs.items():
            if st == "PROFESSIONAL_JUDGEMENT":
                self.assertEqual(self.s.detail(ORG, eid)["coverage"]["outcome"], "INCOMPLETE")
            out, _ = self.sign(eid, r, st)
        self.assertEqual(out["coverage"]["outcome"], "VALIDATED")
        done = self.s.complete(ORG, MGR, eid)
        self.assertEqual(done["status"], "COMPLETED"); self.assertEqual(done["statement"]["outcome"], "VALIDATED")
        self.assertEqual(done["statement"]["credential_verification"], "SOME_UNVERIFIED")

    def test_outcome_levels(self):
        eid, revs = self.full()
        for st, r in revs.items(): out, _ = self.sign(eid, r, st, good("CONCURS_WITH_COMMENTS", [{"severity": "MINOR", "text": "n"}]) if st == "CONTROLS" else None)
        self.assertEqual(out["coverage"]["outcome"], "VALIDATED_WITH_RESERVATIONS")
        out, _ = self.sign(eid, revs["SECURITY"], "SECURITY", good("DISAGREES", [{"severity": "CRITICAL", "text": "No MFA"}]))
        self.assertEqual(out["coverage"]["outcome"], "NOT_VALIDATED")
        self.assertEqual([s for s in out["coverage"]["stages"] if s["stage"] == "SECURITY"][0]["status"], "COVERED_ADVERSE")

    def test_unable_to_assess_means_incomplete(self):
        eid, revs = self.full()
        for st, r in revs.items(): out, _ = self.sign(eid, r, st, good("UNABLE_TO_ASSESS", limitations="no access") if st == "EVIDENCE" else None)
        self.assertEqual(out["coverage"]["outcome"], "INCOMPLETE")
        self.assertEqual([s for s in out["coverage"]["stages"] if s["stage"] == "EVIDENCE"][0]["status"], "COVERED_LIMITED")
        with self.assertRaises(ReviewStateError): self.s.complete(ORG, MGR, eid)

    def test_minimum_reviewers_per_stage(self):
        e = self.eng(["EVIDENCE"], min_reviewers={"EVIDENCE": 2}); eid = e["id"]; self.s.open(ORG, MGR, eid)
        a = self.reviewer("AUDIT", name="A One", email="a1@x.test"); b = self.reviewer("AUDIT", name="B Two", email="b2@x.test")
        for r in (a, b): self.s.assign(ORG, MGR, eid, "EVIDENCE", r["id"]); self.declare(eid, r)
        out, _ = self.sign(eid, a, "EVIDENCE")
        self.assertEqual(out["coverage"]["stages"][0]["status"], "IN_PROGRESS"); self.assertFalse(out["coverage"]["complete"])
        out, _ = self.sign(eid, b, "EVIDENCE"); self.assertEqual(out["coverage"]["outcome"], "VALIDATED")

    def test_uncovered_status(self):
        e = self.eng(["EVIDENCE"]); self.assertEqual(e["coverage"]["stages"][0]["status"], "UNCOVERED")

    def test_serious_observations_need_a_response_to_complete(self):
        r, eid = self.ready(); self.declare(eid, r)
        out, rid = self.sign(eid, r, "ACCOUNTING_TREATMENT", good("CONCURS_WITH_COMMENTS", [{"severity": "MAJOR", "text": "Revenue cut-off"}, {"severity": "MINOR", "text": "typo"}]))
        self.assertEqual(out["coverage"]["unresolved_serious_observations"], 1)
        with self.assertRaises(ReviewStateError): self.s.complete(ORG, MGR, eid)
        major = [o for o in out["reviews"][0]["observations"] if o["severity"] == "MAJOR"][0]
        with self.assertRaises(VE): self.s.respond(ORG, MGR, eid, rid, major["id"], "NONSENSE", "x")
        with self.assertRaises(VE): self.s.respond(ORG, MGR, eid, rid, major["id"], "ACCEPTED", "")
        with self.assertRaises(ReviewNotFoundError): self.s.respond(ORG, MGR, eid, rid, "nope", "ACCEPTED", "x")
        out = self.s.respond(ORG, MGR, eid, rid, major["id"], "REMEDIATED", "Cut-off procedure added")
        self.assertEqual(out["coverage"]["unresolved_serious_observations"], 0)
        self.assertEqual(self.s.complete(ORG, MGR, eid)["statement"]["outcome"], "VALIDATED_WITH_RESERVATIONS")

    def test_cannot_respond_to_a_draft(self):
        r, eid = self.ready(); self.declare(eid, r)
        d = self.s.save_review(ORG, MGR, eid, "ACCOUNTING_TREATMENT", r["id"], good("CONCURS_WITH_COMMENTS", [{"severity": "MAJOR", "text": "x"}], source_reference="r"), True)
        with self.assertRaises(ReviewStateError): self.s.respond(ORG, MGR, eid, d["reviews"][0]["id"], d["reviews"][0]["observations"][0]["id"], "ACCEPTED", "ok")


class StatementTests(Base):
    def completed(self, keys=True):
        if not keys: self.s.keys = None
        r, eid = self.ready(); self.declare(eid, r); self.sign(eid, r, "ACCOUNTING_TREATMENT")
        self.s.complete(ORG, MGR, eid); return eid

    def test_statement_before_completion(self):
        r, eid = self.ready()
        with self.assertRaises(ReviewStateError): self.s.statement(ORG, eid)

    def test_statement_verifies_and_carries_disclaimer(self):
        eid = self.completed(); st = self.s.statement(ORG, eid, sha({"counts": {"journals": 3}}))
        self.assertTrue(st["verification"]["ok"]); self.assertTrue(st["verification"]["signature_ok"]); self.assertTrue(st["data_unchanged_since_review"])
        self.assertIn("not an audit opinion", st["disclaimer"].lower()); self.assertEqual(st["credential_verification"], "SOME_UNVERIFIED")
        self.assertFalse(self.s.statement(ORG, eid, "different")["data_unchanged_since_review"])

    def test_tampering_is_detected(self):
        eid = self.completed(); st = self.s.statement(ORG, eid)
        for mutate in (lambda s: s.update(outcome="VALIDATED"), lambda s: s["stages"][0]["reviews"][0].update(conclusion="CONCURS"), lambda s: s.update(title="Other"),
                       lambda s: s["snapshot"].update(counts={})):
            t = copy.deepcopy(st); mutate(t) if mutate.__code__.co_consts != () else None
            if t == st: t["title"] = "Changed"
            self.assertFalse(self.s.verify_statement(t)["hash_ok"])
        t = copy.deepcopy(st); t["mac"] = "0" * len(st["mac"])
        self.assertFalse(self.s.verify_statement(t)["signature_ok"]); self.assertFalse(self.s.verify_statement(t)["ok"])
        t = copy.deepcopy(st); t["mac_key_id"] = "nope"; self.assertFalse(self.s.verify_statement(t)["ok"])

    def test_without_keys_statement_is_hash_only(self):
        eid = self.completed(keys=False); st = self.s.statement(ORG, eid)
        self.assertNotIn("mac", st); self.assertTrue(st["verification"]["ok"]); self.assertIsNone(st["verification"]["signature_ok"])

    def test_completed_engagement_is_frozen(self):
        eid = self.completed()
        for fn in (lambda: self.s.open(ORG, MGR, eid), lambda: self.s.complete(ORG, MGR, eid), lambda: self.s.refresh_snapshot(ORG, MGR, eid, {}), lambda: self.s.withdraw(ORG, MGR, eid, "x"),
                   lambda: self.s.respond(ORG, MGR, eid, "a", "b", "ACCEPTED", "x")):
            with self.assertRaises((ReviewStateError, ReviewNotFoundError)): fn()
        self.assertEqual(self.s.list_engagements(ORG)[0]["outcome"], "VALIDATED")

    def test_detail_snapshot_current_flag(self):
        e = self.eng(); self.assertIsNone(e["snapshot_is_current"])
        self.assertTrue(self.s.detail(ORG, e["id"], e["snapshot_hash"])["snapshot_is_current"]); self.assertFalse(self.s.detail(ORG, e["id"], "x")["snapshot_is_current"])

    def test_engagement_org_isolation(self):
        e = self.eng()
        with self.assertRaises(ReviewNotFoundError): self.s.detail("other", e["id"])


class AuditTests(Base):
    def test_actions_are_logged(self):
        r, eid = self.ready(); self.declare(eid, r); self.sign(eid, r, "ACCOUNTING_TREATMENT"); self.s.complete(ORG, MGR, eid)
        acts = [l[0] for l in self.logs]
        for a in ("VALIDATION_REVIEWER_ADDED", "VALIDATION_ENGAGEMENT_CREATED", "VALIDATION_ENGAGEMENT_OPENED", "VALIDATION_REVIEWER_ASSIGNED", "VALIDATION_INDEPENDENCE_DECLARED",
                  "VALIDATION_REVIEW_SIGNED", "VALIDATION_ENGAGEMENT_COMPLETED"):
            self.assertIn(a, acts)


if __name__ == "__main__":
    unittest.main()
