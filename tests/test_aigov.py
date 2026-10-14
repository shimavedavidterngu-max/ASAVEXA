"""AI governance: AI systems, model changes, incidents, two-person rules, policy, isolation, audit, permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from analysis_fixture import ORG, OTHER, World
from asavexa.aigov.errors import AigovError, AigovForbiddenError, AigovNotFoundError, AigovStateError
from asavexa.aigov.service import AigovService, refnum
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AIG_APPROVE, AIG_PREPARE, AUDIT_READ, ROLE_PERMISSIONS

U1, U2, U3 = "user-1", "user-2", "user-3"   # U1 prepares, U2 prepares too, U3 approves


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
        self.svc = AigovService(self.w.store, Vault(), log=lambda *a: self.events.append(a), now=self.clock)

    def system(self, actor=U1, active=False, **kw):
        d = dict(name=f"Invoice reader {len(self.events)}{kw.get('n', '')}", description="Reads supplier invoices and suggests the account to post to", origin="VENDOR", vendor_name="Acme AI", intended_use="Suggest accounts for invoices; a person posts every entry",
                 out_of_scope="Must not post entries or approve payments on its own", risk_tier="LIMITED", owner_name="Ada Obi")
        d.update({k: v for k, v in kw.items() if k != "n"}); s = self.svc.aig_propose_system(ORG, d, actor)
        return self.svc.aig_approve_system(ORG, s["id"], U3) if active else s

    def change(self, s, actor=U1, **kw):
        d = dict(system_id=s["id"], change_kind="MODEL_UPDATE", from_version="1.0", to_version="1.1", description="The vendor released a new model version", effective_on="2026-02-10", testing_summary="Ran 50 sample invoices and compared with the old version")
        d.update(kw); return self.svc.aig_record_change(ORG, d, actor)

    def incident(self, s, actor=U1, **kw):
        d = dict(system_id=s["id"], incident_kind="WRONG_OUTPUT", severity="LOW", description="The suggested account was wrong for a batch of invoices", occurred_on="2026-02-08", discovered_on="2026-02-09")
        d.update(kw); return self.svc.aig_record_incident(ORG, d, actor)


class Helpers(unittest.TestCase):
    def test_refnum(self): self.assertEqual(sorted([{"ref": "AI-010"}, {"ref": "AI-002"}], key=refnum)[0]["ref"], "AI-002"); self.assertEqual(refnum({"ref": "x"}), 0)


class Policy(Base):
    def test_defaults_set_and_validation(self):
        self.assertEqual(self.svc.aig_get_policy(ORG)["review_days"], 180)
        self.assertEqual(self.svc.aig_set_policy(ORG, {"review_days": 90, "incident_review_days": 3}, U3)["incident_review_days"], 3)
        for bad in ({"review_days": 10}, {"review_days": 731}, {"incident_review_days": 0}, {"incident_review_days": "x"}, {"review_days": True}):
            with self.assertRaises(AigovError, msg=str(bad)): self.svc.aig_set_policy(ORG, bad, U3)


class Systems(Base):
    def test_propose_approve_and_cannot_change(self):
        s = self.system(); self.assertEqual((s["ref"], s["status"], s["risk_tier"]), ("AI-001", "PROPOSED", "LIMITED"))
        with self.assertRaises(AigovForbiddenError): self.svc.aig_approve_system(ORG, s["id"], U1)
        a = self.svc.aig_approve_system(ORG, s["id"], U3); self.assertEqual((a["status"], a["decided_by"]), ("APPROVED", U3))
        for f in (lambda: self.svc.aig_approve_system(ORG, s["id"], U3), lambda: self.svc.aig_reject_system(ORG, s["id"], "Not wanted after all", U3)):
            with self.assertRaises(AigovStateError): f()
        self.assertFalse(hasattr(self.svc, "aig_update_system"))

    def test_validation(self):
        for kw in (dict(name="abc"), dict(description="short"), dict(origin="MAGIC"), dict(vendor_name=""), dict(intended_use="short"), dict(out_of_scope="short"), dict(risk_tier="SEVERE"),
                   dict(owner_name="A"), dict(data_categories="ab"), dict(risk_tier="HIGH"), dict(risk_tier="HIGH", human_oversight="short")):
            with self.assertRaises(AigovError, msg=str(kw)): self.system(**kw)
        self.assertEqual(self.events, [])
        self.assertEqual(self.system(origin="IN_HOUSE", vendor_name="")["vendor_name"], None)
        self.assertEqual(self.system(n="b", risk_tier="HIGH", human_oversight="A person checks every output before use")["risk_tier"], "HIGH")

    def test_refs_taken_last_so_refused_requests_burn_no_number(self):
        with self.assertRaises(AigovError): self.system(name="abc")
        self.assertEqual(self.system()["ref"], "AI-001")

    def test_duplicate_name(self):
        self.system(name="Invoice reader main")
        with self.assertRaises(AigovStateError): self.system(name="invoice READER main")
        s2 = self.system(name="Another reader")
        self.svc.aig_reject_system(ORG, s2["id"], "Duplicate of another record", U3); self.system(name="Another reader")

    def test_reject_needs_reason(self):
        s = self.system()
        with self.assertRaises(AigovError): self.svc.aig_reject_system(ORG, s["id"], "no", U3)
        self.assertEqual(self.svc.aig_reject_system(ORG, s["id"], "Not an AI system at all", U3)["status"], "REJECTED")

    def test_retire_rules(self):
        s = self.system(active=True)
        with self.assertRaises(AigovError): self.svc.aig_retire_system(ORG, s["id"], "short", U3)
        c = self.change(s)
        with self.assertRaises(AigovStateError): self.svc.aig_retire_system(ORG, s["id"], "Replaced by another tool", U3)
        self.svc.aig_approve_change(ORG, c["id"], U3); i = self.incident(s)
        with self.assertRaises(AigovStateError): self.svc.aig_retire_system(ORG, s["id"], "Replaced by another tool", U3)
        self.svc.aig_void_incident(ORG, i["id"], "Recorded against the wrong system", U3)
        self.assertEqual(self.svc.aig_retire_system(ORG, s["id"], "Replaced by another tool", U3)["status"], "RETIRED")
        with self.assertRaises(AigovStateError): self.change(s)

    def test_review_needs_a_different_person_and_resets_due(self):
        s = self.system(active=True)
        with self.assertRaises(AigovForbiddenError): self.svc.aig_review_system(ORG, s["id"], "Still used as approved", U1)
        with self.assertRaises(AigovError): self.svc.aig_review_system(ORG, s["id"], "short", U3)
        self.assertFalse(self.svc.aig_get_system(ORG, s["id"])["review_due"])
        self.clock.d = date(2026, 9, 1); self.assertTrue(self.svc.aig_get_system(ORG, s["id"])["review_due"])
        r = self.svc.aig_review_system(ORG, s["id"], "Still used as approved and nothing has changed", U3); self.assertFalse(r["review_due"]); self.assertEqual(r["last_reviewed_on"], "2026-09-01")
        p = self.system(n="p")
        with self.assertRaises(AigovStateError): self.svc.aig_review_system(ORG, p["id"], "Not approved yet at all", U3)

    def test_list_filters(self):
        self.system(); self.system(n="x", risk_tier="MINIMAL")
        self.assertEqual(len(self.svc.aig_list_systems(ORG, tier="MINIMAL")), 1); self.assertEqual(len(self.svc.aig_list_systems(ORG, status="APPROVED")), 0)


class Changes(Base):
    def test_record_and_approve(self):
        s = self.system(active=True); c = self.change(s); self.assertEqual((c["ref"], c["status"], c["system_ref"]), ("MC-001", "RECORDED", "AI-001"))
        with self.assertRaises(AigovForbiddenError): self.svc.aig_approve_change(ORG, c["id"], U1)
        self.assertEqual(self.svc.aig_approve_change(ORG, c["id"], U3)["status"], "APPROVED"); self.assertEqual(self.svc.aig_get_system(ORG, s["id"])["changes"], 1)
        with self.assertRaises(AigovStateError): self.svc.aig_approve_change(ORG, c["id"], U3)

    def test_only_for_approved_systems(self):
        s = self.system()
        with self.assertRaises(AigovStateError): self.change(s)
        with self.assertRaises(AigovNotFoundError): self.svc.aig_record_change(ORG, {"system_id": "nope"}, U1)

    def test_validation(self):
        s = self.system(active=True)
        for kw in (dict(change_kind="MAGIC"), dict(from_version=""), dict(to_version="1.0"), dict(to_version=" 1.0 "), dict(description="short"), dict(effective_on="2026-02-31"), dict(effective_on="2026-02-20"), dict(testing_summary="short")):
            with self.assertRaises(AigovError, msg=str(kw)): self.change(s, **kw)
        self.assertEqual(self.svc.aig_list_changes(ORG), [])
        self.assertEqual(self.change(s)["ref"], "MC-001")

    def test_high_risk_needs_a_test_document(self):
        s = self.system(active=True, risk_tier="HIGH", human_oversight="A person checks every output before use")
        with self.assertRaises(AigovError): self.change(s)
        with self.assertRaises(AigovError): self.change(s, evidence_ids=["nope"])
        self.assertEqual(self.change(s, evidence_ids=["ev1"])["evidence"][0]["file_hash"], "h" * 64)

    def test_reject_needs_reason_and_a_different_person(self):
        s = self.system(active=True); c = self.change(s)
        with self.assertRaises(AigovError): self.svc.aig_reject_change(ORG, c["id"], "no", U3)
        with self.assertRaises(AigovForbiddenError): self.svc.aig_reject_change(ORG, c["id"], "Testing was not enough", U1)
        self.assertEqual(self.svc.aig_reject_change(ORG, c["id"], "Testing was not enough", U3)["status"], "REJECTED")

    def test_snapshot_keeps_tier_at_time_of_change(self):
        s = self.system(active=True); c = self.change(s); self.assertEqual(c["risk_tier"], "LIMITED")


class Incidents(Base):
    def test_record_review_and_void(self):
        s = self.system(active=True); i = self.incident(s); self.assertEqual((i["ref"], i["status"]), ("AX-001", "RECORDED"))
        with self.assertRaises(AigovForbiddenError): self.svc.aig_review_incident(ORG, i["id"], dict(cause="The model was not given the chart of accounts", corrective_action="Added the chart of accounts to every request"), U1)
        with self.assertRaises(AigovError): self.svc.aig_review_incident(ORG, i["id"], dict(cause="short", corrective_action="Added the chart of accounts to every request"), U3)
        with self.assertRaises(AigovError): self.svc.aig_review_incident(ORG, i["id"], dict(cause="The model was not given the chart of accounts", corrective_action="too short"), U3)
        r = self.svc.aig_review_incident(ORG, i["id"], dict(cause="The model was not given the chart of accounts", corrective_action="Added the chart of accounts to every request"), U3); self.assertEqual(r["status"], "REVIEWED")
        with self.assertRaises(AigovStateError): self.svc.aig_void_incident(ORG, i["id"], "Recorded against the wrong system", U3)
        j = self.incident(s)
        with self.assertRaises(AigovForbiddenError): self.svc.aig_void_incident(ORG, j["id"], "Recorded against the wrong system", U1)
        with self.assertRaises(AigovError): self.svc.aig_void_incident(ORG, j["id"], "short", U3)
        self.assertEqual(self.svc.aig_void_incident(ORG, j["id"], "Recorded against the wrong system", U3)["status"], "VOIDED")

    def test_validation(self):
        s = self.system(active=True)
        for kw in (dict(incident_kind="MAGIC"), dict(severity="EXTREME"), dict(description="short"), dict(occurred_on="2026-02-31"), dict(occurred_on="2026-02-20", discovered_on="2026-02-20"), dict(discovered_on="2026-02-01"),
                   dict(severity="HIGH"), dict(severity="CRITICAL", harm="short"), dict(people_affected="-3"), dict(people_affected="x"), dict(evidence_ids=["nope"])):
            with self.assertRaises(AigovError, msg=str(kw)): self.incident(s, **kw)
        ok = self.incident(s, severity="HIGH", harm="Forty invoices were posted to the wrong account", people_affected="12"); self.assertEqual((ok["ref"], ok["people_affected"]), ("AX-001", 12))

    def test_only_for_systems_that_were_approved(self):
        p = self.system()
        with self.assertRaises(AigovStateError): self.incident(p)
        s = self.system(n="z", active=True); self.svc.aig_retire_system(ORG, s["id"], "Replaced by another tool", U3)
        self.assertEqual(self.incident(s)["status"], "RECORDED")

    def test_overdue_by_policy(self):
        s = self.system(active=True); i = self.incident(s); self.assertFalse(i["review_overdue"])
        self.clock.d = date(2026, 2, 23); self.assertTrue(self.svc.aig_get_incident(ORG, i["id"])["review_overdue"])
        self.svc.aig_set_policy(ORG, {"incident_review_days": 30}, U3); self.assertFalse(self.svc.aig_get_incident(ORG, i["id"])["review_overdue"])


class Overview(Base):
    def test_attention(self):
        s = self.system(active=True); self.system(n="p"); c = self.change(s); i = self.incident(s, severity="HIGH", harm="Forty invoices were posted to the wrong account")
        o = self.svc.aig_overview(ORG); kinds = {a["kind"]: a["count"] for a in o["attention"]}
        self.assertEqual(kinds, {"SEVERE_INCIDENTS_OPEN": 1, "SYSTEMS_TO_APPROVE": 1, "CHANGES_TO_APPROVE": 1, "INCIDENTS_TO_REVIEW": 1})
        self.assertEqual((o["counts"]["systems_approved"], o["counts"]["systems_limited"], o["counts"]["incidents_open"]), (1, 1, 1))
        self.clock.d = date(2026, 9, 1); kinds = {a["kind"] for a in self.svc.aig_overview(ORG)["attention"]}; self.assertTrue({"SYSTEMS_REVIEW_DUE", "INCIDENTS_REVIEW_OVERDUE"} <= kinds)

    def test_empty_and_options(self):
        o = self.svc.aig_overview(ORG); self.assertEqual((o["attention"], o["counts"]["systems_approved"]), ([], 0)); self.assertIn("HIGH", self.svc.aig_options(ORG)["tiers"]); self.assertTrue(o["limitations"])


class Isolation(Base):
    def test_other_company_sees_nothing_and_cannot_touch(self):
        s = self.system(active=True); c = self.change(s); i = self.incident(s)
        for lst in (self.svc.aig_list_systems, self.svc.aig_list_changes, self.svc.aig_list_incidents): self.assertEqual(lst(OTHER), [])
        for f in (lambda: self.svc.aig_get_system(OTHER, s["id"]), lambda: self.svc.aig_get_change(OTHER, c["id"]), lambda: self.svc.aig_get_incident(OTHER, i["id"]),
                  lambda: self.svc.aig_approve_change(OTHER, c["id"], U3), lambda: self.svc.aig_void_incident(OTHER, i["id"], "Recorded against the wrong system", U3),
                  lambda: self.svc.aig_record_change(OTHER, {"system_id": s["id"]}, U1), lambda: self.svc.aig_review_system(OTHER, s["id"], "Still used as approved", U3)):
            with self.assertRaises(AigovNotFoundError): f()
        self.assertEqual(self.svc.aig_overview(OTHER)["counts"]["systems_approved"], 0)

    def test_same_names_allowed_in_each_company(self):
        self.system(name="Invoice reader main"); d = dict(name="Invoice reader main", description="Reads supplier invoices and suggests accounts", origin="IN_HOUSE", intended_use="Suggest accounts for invoices", out_of_scope="Must not post on its own", risk_tier="MINIMAL", owner_name="Ada")
        self.assertEqual(self.svc.aig_propose_system(OTHER, d, U1)["ref"], "AI-001")


class Audit(Base):
    def test_every_write_logged_without_content(self):
        s = self.system(active=True); c = self.change(s); self.svc.aig_approve_change(ORG, c["id"], U3); i = self.incident(s)
        self.svc.aig_review_incident(ORG, i["id"], dict(cause="The model was not given the chart of accounts", corrective_action="Added the chart of accounts to every request"), U3)
        self.svc.aig_review_system(ORG, s["id"], "Still used as approved and nothing has changed", U3); self.svc.aig_set_policy(ORG, {"review_days": 100}, U3)
        j = self.incident(s); self.svc.aig_void_incident(ORG, j["id"], "Recorded against the wrong system", U3); r = self.change(s, to_version="1.2"); self.svc.aig_reject_change(ORG, r["id"], "Testing was not enough", U3)
        p = self.system(n="p"); self.svc.aig_reject_system(ORG, p["id"], "Not an AI system at all", U3); self.svc.aig_retire_system(ORG, s["id"], "Replaced by another tool", U3)
        acts = [x[0] for x in self.events]
        for a in ("AIGOV_SYSTEM_PROPOSED", "AIGOV_SYSTEM_APPROVED", "AIGOV_SYSTEM_REJECTED", "AIGOV_SYSTEM_RETIRED", "AIGOV_SYSTEM_REVIEWED", "AIGOV_CHANGE_RECORDED", "AIGOV_CHANGE_APPROVED", "AIGOV_CHANGE_REJECTED",
                  "AIGOV_INCIDENT_RECORDED", "AIGOV_INCIDENT_REVIEWED", "AIGOV_INCIDENT_VOIDED", "AIGOV_POLICY_SET"): self.assertIn(a, acts)
        blob = " ".join(str(x) for x in self.events)
        for secret in ("chart of accounts", "supplier invoices", "new model version", "Recorded against", "Acme AI", "Testing was not"): self.assertNotIn(secret, blob)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(AigovError): self.system(name="abc")
        self.assertEqual(self.events, [])


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, AIG_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, AIG_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, AIG_PREPARE) or has(r, AIG_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if AIG_PREPARE in perms or AIG_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "aigov.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "AIG_PREPARE", "_approve": "AIG_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_policy", "approve_system", "reject_system", "retire_system", "review_system", "approve_change", "reject_change", "review_incident", "void_incident"}
        prepare = {"propose_system", "record_change", "record_incident"}
        for n in approve: self.assertEqual(g[n][1], {"AIG_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"AIG_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no aigov guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
