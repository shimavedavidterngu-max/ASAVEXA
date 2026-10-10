"""Runs the REAL validation router functions (fastapi stubbed: it is not installable here) over a real SecurityContext, real identity,
real evidence/ledger/compliance services and the real validation service on one SQLite connection."""
import sys, types
sys.path.insert(0, "/home/claude/asavexa/src"); sys.path.insert(0, "/home/claude/asavexa/tests")
def mod(name, **attrs):
    m = types.ModuleType(name); m.__dict__.update(attrs); sys.modules[name] = m; return m
class APIRouter:
    def __init__(self, **k): self.k = k
    def _d(self, *a, **k): return lambda f: f
    get = post = put = patch = delete = _d
mod("fastapi", APIRouter=APIRouter, Depends=lambda x=None: ("dep", x))
import asavexa
for pkg, path in [("asavexa.api","api"),("asavexa.api.routers","api/routers"),("asavexa.api.schemas","api/schemas")]:
    m = types.ModuleType(pkg); m.__path__ = ["/home/claude/asavexa/src/asavexa/"+path]; sys.modules[pkg] = m
mod("asavexa.api.deps", **{n: (lambda: None) for n in ["get_accounting_engine","get_compliance_service","get_current_actor","get_current_org","get_evidence_vault","get_identity_service","get_security","get_validation"]},
    require_permission=lambda p: ("perm", p))
import importlib
vr = importlib.import_module("asavexa.api.routers.validation")

import unittest
from datetime import date
from decimal import Decimal
from test_security_context import Ctx
from asavexa.security.store import SqliteDocStore
from asavexa.validation.service import ValidationService, sha
from asavexa.validation.wiring import make_log
from asavexa.validation.errors import ReviewForbiddenError, ProfessionalValidationError
from asavexa.evidence.domain.enums import EvidenceType
from asavexa.identity.domain.permissions import VALIDATION_MANAGE, AUDIT_READ, ROLE_PERMISSIONS
from asavexa.identity.domain.enums import Role

CONF = {k: True for k in ["no_financial_interest", "not_involved_in_preparing_records", "no_close_personal_relationship", "no_other_threat_to_objectivity"]}
SPECS = {"ACCOUNTING_TREATMENT": "IFRS", "CONTROLS": "INTERNAL_AUDIT", "EVIDENCE": "AUDIT", "REPORTING": "IFRS", "AUDIT_WORKFLOW": "AUDIT", "SECURITY": "CYBERSECURITY", "PROFESSIONAL_JUDGEMENT": "ACADEMIC"}


class Run(Ctx):
    def setUp(self):
        self.build()
        self.w_ = self.w; self.o = self.w.org.id; self.owner = self.w.owner.id; self.acct = self.w.accountant.id
        self.svc = ValidationService(SqliteDocStore(self.w.conn), log=make_log(self.ctx), keys=self.kr)
        self.deps = dict(vault=self.w.vault, accounting=self.w.accounting, compliance=self.w.compliance, identity=self.w.identity, security=self.ctx)

    def snap(self): return vr.current_snapshot(self.o, **self.deps)

    def add(self, spec, name, user_id=None):
        return vr.add_reviewer(vr.ReviewerBody(name=name, email=f"{name.split()[0].lower()}@firm.test", credentials=[vr.CredentialBody(body="ACCA", membership_no="1")],
                                               specialisms=[spec], user_id=user_id), self.o, self.owner, self.w.identity, self.svc)

    def test_snapshot_is_deterministic_stable_and_reflects_changes(self):
        a, b = self.snap(), self.snap()
        self.assertEqual(a, b)
        self.assertGreater(a["evidence"]["records"], 0); self.assertGreater(a["ledger"]["journals"], 0); self.assertGreater(a["controls"]["defined"], 0)
        self.assertTrue(a["security"]["encryption_configured"]); self.assertTrue(a["audit_chain"]["checked"])
        text = str(a)
        self.assertNotIn("Kadena", text); self.assertNotIn("meridian", text.lower())     # counts only, no names
        # doing validation work must not itself change the snapshot
        self.add("IFRS", "Ada Okafor")
        self.assertEqual(self.snap(), a)
        # real data changes do
        self.w.vault.upload_evidence(self.o, EvidenceType.INVOICE, b"another", "x.pdf", "application/pdf", uploaded_by=self.acct)
        self.assertNotEqual(sha(self.snap()), sha(a))

    def test_roles(self):
        self.assertIn(VALIDATION_MANAGE, ROLE_PERMISSIONS[Role.OWNER]); self.assertIn(VALIDATION_MANAGE, ROLE_PERMISSIONS[Role.ADMINISTRATOR])
        for r in Role:
            if r not in (Role.OWNER, Role.ADMINISTRATOR): self.assertNotIn(VALIDATION_MANAGE, ROLE_PERMISSIONS[r], r)
        self.assertTrue(vr._can_manage(self.w.identity, self.owner, self.o)); self.assertFalse(vr._can_manage(self.w.identity, self.acct, self.o))
        self.assertFalse(vr._can_manage(self.w.identity, self.owner, self.w.other_org.id))
        g = vr.guide(); self.assertEqual(len(g["stages"]), 7); self.assertIn("not an audit opinion", g["disclaimer"].lower())

    def test_full_flow_through_router_functions(self):
        # reviewers: one linked to a real user, the rest unlinked and recorded on their behalf
        linked = self.add("AUDIT", "Linus Auditor", user_id=self.w.approver.id)
        self.assertEqual(vr.me(self.w.approver.id, self.o, self.w.identity, self.svc)["reviewer"]["id"], linked["id"])
        self.assertIsNone(vr.me(self.acct, self.o, self.w.identity, self.svc)["reviewer"])
        with self.assertRaises(ProfessionalValidationError): self.add("AUDIT", "Ghost", user_id=self.w.other_owner.id)   # not a member of this org
        revs = {st: (linked if st == "EVIDENCE" else self.add(sp, f"Rev{i} Name")) for i, (st, sp) in enumerate(SPECS.items())}
        eng = vr.create_engagement(vr.EngagementBody(title="FY2026 validation", as_of="2026-09-30"), self.o, self.owner, self.w.vault, self.w.accounting,
                                   self.w.compliance, self.w.identity, self.ctx, self.svc)
        eid = eng["id"]; self.assertEqual(eng["snapshot"], self.snap())
        vr.open_engagement(eid, self.o, self.owner, self.svc)
        for st, r in revs.items(): vr.assign(eid, vr.AssignBody(stage=st, reviewer_id=r["id"]), self.o, self.owner, self.svc)
        for st, r in revs.items():
            if r["id"] == linked["id"]:
                with self.assertRaises(ReviewForbiddenError):   # even the owner cannot declare for someone with their own account
                    vr.declare(eid, vr.DeclarationBody(reviewer_id=r["id"], independent=True, confirmations=CONF, source_reference="x"), self.o, self.owner, self.w.identity, self.svc)
                vr.declare(eid, vr.DeclarationBody(reviewer_id=r["id"], independent=True, confirmations=CONF), self.o, self.w.approver.id, self.w.identity, self.svc)
            else:
                with self.assertRaises(ReviewForbiddenError):   # an ordinary accountant cannot declare for an unlinked reviewer
                    vr.declare(eid, vr.DeclarationBody(reviewer_id=r["id"], independent=True, confirmations=CONF, source_reference="x"), self.o, self.acct, self.w.identity, self.svc)
                vr.declare(eid, vr.DeclarationBody(reviewer_id=r["id"], independent=True, confirmations=CONF, source_reference="signed declaration 7"), self.o, self.owner, self.w.identity, self.svc)
        for st, r in revs.items():
            actor = self.w.approver.id if r["id"] == linked["id"] else self.owner
            body = vr.ReviewBody(stage=st, reviewer_id=r["id"], conclusion="CONCURS_WITH_COMMENTS" if st == "CONTROLS" else "CONCURS", scope_reviewed="Sample of FY2026", basis="IFRS",
                                 competence_confirmed=True, source_reference=None if r["id"] == linked["id"] else "signed report 12",
                                 observations=[vr.ObservationBody(severity="MAJOR", text="Segregation of duties thin")] if st == "CONTROLS" else [])
            d = vr.save_review(eid, body, self.o, actor, self.w.identity, self.svc)
            rid = [x for x in d["reviews"] if x["stage"] == st and x["status"] == "DRAFT"][0]["id"]
            d = vr.sign_review(eid, rid, self.o, actor, self.w.identity, self.svc)
        self.assertEqual(d["coverage"]["outcome"], "VALIDATED_WITH_RESERVATIONS")
        with self.assertRaises(Exception): vr.complete(eid, self.o, self.owner, self.svc)    # major observation unanswered
        cr = [x for x in d["reviews"] if x["stage"] == "CONTROLS"][0]
        d = vr.respond(eid, cr["id"], cr["observations"][0]["id"], vr.ResponseBody(status="ACCEPTED", note="Will add a second approver"), self.o, self.owner, self.svc)
        done = vr.complete(eid, self.o, self.owner, self.svc)
        self.assertEqual(done["status"], "COMPLETED")
        st = vr.statement(eid, self.o, self.w.vault, self.w.accounting, self.w.compliance, self.w.identity, self.ctx, self.svc)
        self.assertTrue(st["verification"]["ok"]); self.assertTrue(st["verification"]["signature_ok"]); self.assertTrue(st["data_unchanged_since_review"])
        self.assertEqual(st["credential_verification"], "SOME_UNVERIFIED")
        # data moves after the review: the statement says so
        self.w.vault.upload_evidence(self.o, EvidenceType.INVOICE, b"after-review", "late.pdf", "application/pdf", uploaded_by=self.acct)
        st2 = vr.statement(eid, self.o, self.w.vault, self.w.accounting, self.w.compliance, self.w.identity, self.ctx, self.svc)
        self.assertFalse(st2["data_unchanged_since_review"]); self.assertTrue(st2["verification"]["ok"])
        d = vr.engagement(eid, self.o, self.w.vault, self.w.accounting, self.w.compliance, self.w.identity, self.ctx, self.svc)
        self.assertFalse(d["snapshot_is_current"])
        # audit trail has the actions, attributed correctly, with the right entity types
        evs = [e for e in self.w.audit.list_for_org(self.o) if e.action.startswith("VALIDATION_")]
        acts = {e.action for e in evs}
        for a in ("VALIDATION_REVIEWER_ADDED", "VALIDATION_ENGAGEMENT_CREATED", "VALIDATION_REVIEW_SIGNED", "VALIDATION_ENGAGEMENT_COMPLETED", "VALIDATION_OBSERVATION_RESPONDED"):
            self.assertIn(a, acts)
        self.assertEqual({e.entity_type for e in evs if e.action == "VALIDATION_REVIEWER_ADDED"}, {"ValidationReviewer"})
        self.assertEqual({e.entity_type for e in evs if e.action == "VALIDATION_REVIEW_SIGNED"}, {"ValidationEngagement"})
        self.assertTrue(self.ctx.verify_audit(self.o)["ok"])                                    # chain still intact after all of it
        self.assertEqual(vr.list_engagements(self.o, self.svc)[0]["outcome"], "VALIDATED_WITH_RESERVATIONS")

    def test_verify_own_credentials_blocked_via_router(self):
        r = self.add("AUDIT", "Self Check", user_id=self.w.approver.id)
        with self.assertRaises(ReviewForbiddenError):
            vr.verify_credential(r["id"], 0, vr.VerifyBody(accepted=True, method="looked up"), self.o, self.w.approver.id, self.svc)
        out = vr.verify_credential(r["id"], 0, vr.VerifyBody(accepted=True, method="ACCA register 2026-10-01"), self.o, self.owner, self.svc)
        self.assertEqual(out["credential_state"], "VERIFIED")
        out = vr.update_reviewer(r["id"], vr.ReviewerUpdateBody(add_credential=vr.CredentialBody(body="CPA", membership_no="9")), self.o, self.owner, self.svc)
        self.assertEqual(len(out["credentials"]), 2)
        out = vr.update_reviewer(r["id"], vr.ReviewerUpdateBody(affiliation="New Firm"), self.o, self.owner, self.svc)
        self.assertEqual(out["affiliation"], "New Firm"); self.assertEqual(len(out["credentials"]), 2)       # unset fields left alone
        self.assertEqual(vr.deactivate_reviewer(r["id"], self.o, self.owner, self.svc)["active"], False)
        self.assertEqual(vr.activate_reviewer(r["id"], self.o, self.owner, self.svc)["active"], True)

    def test_refresh_snapshot_and_withdraw(self):
        eng = vr.create_engagement(vr.EngagementBody(title="T", as_of="2026-09-30", stages=["EVIDENCE"]), self.o, self.owner, self.w.vault, self.w.accounting, self.w.compliance, self.w.identity, self.ctx, self.svc)
        self.w.vault.upload_evidence(self.o, EvidenceType.INVOICE, b"zzz", "z.pdf", "application/pdf", uploaded_by=self.acct)
        d = vr.refresh_snapshot(eng["id"], self.o, self.owner, self.w.vault, self.w.accounting, self.w.compliance, self.w.identity, self.ctx, self.svc)
        self.assertEqual(d["snapshot"], self.snap())
        d = vr.withdraw(eng["id"], vr.WithdrawBody(reason="Wrong scope"), self.o, self.owner, self.svc)
        self.assertEqual(d["status"], "WITHDRAWN")

    def test_other_org_cannot_see_anything(self):
        self.add("IFRS", "Ada Okafor")
        self.assertEqual(vr.panel(self.w.other_org.id, self.svc), [])
        self.assertEqual(vr.list_engagements(self.w.other_org.id, self.svc), [])


if __name__ == "__main__":
    unittest.main()
