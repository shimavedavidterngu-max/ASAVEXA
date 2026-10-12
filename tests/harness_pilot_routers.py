"""Runs the REAL pilot router functions (fastapi stubbed: not installable here) over real identity, a real SecurityContext (so the audit chain is
exercised) and the real pilot service on one SQLite connection. The firm is 'Other Ltd'; the client is 'Meridian Textiles' (which has real data)."""
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
for pkg, path in [("asavexa.api","api"),("asavexa.api.routers","api/routers"),("asavexa.api.schemas","api/schemas"),("asavexa.api.db","api/db")]:
    m = types.ModuleType(pkg); m.__path__ = ["/home/claude/asavexa/src/asavexa/"+path]; sys.modules[pkg] = m
mod("asavexa.api.deps", **{n: (lambda: None) for n in ["get_audit_repository","get_current_actor","get_current_org","get_identity_service","get_pilot","get_session"]},
    require_permission=lambda p: ("perm", p))
# the two SQLAlchemy-backed readers the router imports lazily, replaced by the SQLite equivalents the passport tests already use
mod("asavexa.api.db.audit_sqlalchemy_repository", SqlAlchemyAuditRepository=lambda session: session.audit)
mod("asavexa.api.routers.passport", gather_inputs=lambda session, org: session.inputs(org))
import importlib
pr = importlib.import_module("asavexa.api.routers.pilot")

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from test_security_context import Ctx
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import LEDGER_READ, PILOT_MANAGE, ROLE_PERMISSIONS
from asavexa.pilot.errors import PilotError, PilotForbiddenError, PilotNotFoundError, PilotStateError
from asavexa.pilot.service import PilotService
from asavexa.pilot.wiring import make_log
from asavexa.security.store import SqliteDocStore

PW = "correct horse battery staple1"


class Run(Ctx):
    def setUp(self):
        self.build(); w = self.w
        self.firm, self.client = w.other_org.id, w.org.id
        self.mgr = w.other_owner.id                                       # firm manager (OWNER of the firm)
        self.svc = PilotService(SqliteDocStore(w.conn), log=make_log(self.ctx))
        w.identity.add_membership(self.client, self.mgr, Role.ADMINISTRATOR, actor_user_id=w.owner.id)   # the SME's owner gives the firm manager admin rights
        w.identity.add_membership(self.firm, w.accountant.id, Role.ACCOUNTANT, actor_user_id=self.mgr)   # firm staff member (also works in the SME's books)
        self.session = types.SimpleNamespace(audit=w.audit, inputs=w.inputs)
        self.kick = (datetime.now(timezone.utc) - timedelta(days=5)).date().isoformat()

    def make(self, start=True):
        p = pr.create_pilot(pr.PilotBody(name="Lagos SME pilot", start_date=self.kick), self.firm, self.mgr, self.svc)
        pr.add_client(p["id"], pr.ClientBody(client_org_id=self.client, label="Meridian Textiles", consent_reference="Letter signed 2026-10-01", kickoff=self.kick,
                                             baseline={"audit_prep_minutes": 1200}), self.firm, self.mgr, self.w.identity, self.svc)
        if start: pr.set_status(p["id"], pr.StatusBody(status="ACTIVE"), self.firm, self.mgr, self.svc)
        return p["id"]

    def res(self, pid, actor=None): return pr.build_results(self.svc, self.session, self.w.identity, actor or self.mgr, self.firm, pid, True)

    # ---------------------------------------------------------------- permission
    def test_pilot_manage_is_owner_and_administrator_only(self):
        for r in Role:
            self.assertEqual(PILOT_MANAGE in ROLE_PERMISSIONS[r], r in (Role.OWNER, Role.ADMINISTRATOR), r)

    def test_me_and_guide(self):
        g = pr.guide()
        self.assertEqual(len(g["default_targets"]), 11); self.assertIn("honesty", g); self.assertEqual(g["max_clients"], 12)
        m = pr.me(self.mgr, self.firm, self.w.identity, self.svc); self.assertTrue(m["can_manage"]); self.assertIsNone(m["membership"])
        self.assertFalse(pr.me(self.w.accountant.id, self.client, self.w.identity, self.svc)["can_manage"])

    # ---------------------------------------------------------------- consent
    def test_adding_a_client_needs_admin_rights_in_that_client(self):
        p = pr.create_pilot(pr.PilotBody(name="P", start_date=self.kick), self.firm, self.mgr, self.svc)
        body = pr.ClientBody(client_org_id=self.client, label="Meridian", consent_reference="Letter 1")
        # aisha is a firm member and an accountant in the client's books, but cannot give the client's consent
        with self.assertRaises(PilotForbiddenError): pr.add_client(p["id"], body, self.firm, self.w.accountant.id, self.w.identity, self.svc)
        # a person with no standing in the client organisation at all
        w = self.w; stranger = w.identity.register_user("nobody@x.test", "stranger-password-1")
        w.identity.add_membership(self.firm, stranger.id, Role.OWNER, actor_user_id=self.mgr)
        with self.assertRaises(PilotForbiddenError): pr.add_client(p["id"], body, self.firm, stranger.id, w.identity, self.svc)
        out = pr.add_client(p["id"], body, self.firm, self.mgr, w.identity, self.svc)
        self.assertEqual(out["clients"][0]["consent_reference"], "Letter 1")

    def test_eligible_lists_only_organisations_the_person_administers_and_not_already_taken(self):
        e = pr.eligible(self.mgr, self.firm, self.w.identity, self.svc)
        self.assertEqual([x["org_id"] for x in e], [self.client])
        self.make(start=False)
        self.assertEqual(pr.eligible(self.mgr, self.firm, self.w.identity, self.svc), [])
        self.assertEqual(pr.eligible(self.w.accountant.id, self.firm, self.w.identity, self.svc), [])      # accountant administers nothing

    # ---------------------------------------------------------------- measured results from the real platform records
    def test_results_are_measured_from_the_clients_real_records(self):
        pid = self.make()
        r = self.res(pid)
        self.assertEqual((r["clients_included"], r["clients_total"], r["skipped"]), (1, 1, []))
        keys = [m["key"] for m in r["evaluation"]["measures"]]
        self.assertEqual(len(keys), 11); self.assertEqual(len(set(keys)), 11)
        c = r["clients"][0]["metrics"]
        self.assertGreater(c["processing"]["journals_posted"], 0); self.assertGreater(c["evidence"]["posted"], 0)
        self.assertEqual(c["evidence"]["posted"], c["processing"]["journals_posted"])                  # same posted-journal definition as the Passport
        by = {m["key"]: m for m in r["evaluation"]["measures"]}
        self.assertEqual(by["satisfaction"]["status"], "INSUFFICIENT_DATA")                              # nobody answered the survey: never invented
        self.assertTrue(all(m["source"] in ("MEASURED", "REPORTED") for m in r["evaluation"]["measures"]))
        self.assertIn("indicative", r["evaluation"]["caution"])

    def test_a_viewer_who_cannot_read_a_client_gets_nothing_from_it(self):
        pid = self.make()
        w = self.w; outsider = w.identity.register_user("fin@firm.test", "outsider-password-1")
        w.identity.add_membership(self.firm, outsider.id, Role.ADMINISTRATOR, actor_user_id=self.mgr)     # firm admin, but not a member of the client's books
        r = self.res(pid, outsider.id)
        self.assertEqual((r["clients_included"], r["clients_total"]), (0, 1)); self.assertEqual(len(r["skipped"]), 1); self.assertEqual(r["clients"], [])
        self.assertIn("not included", r["evaluation"]["caution"])
        self.assertEqual({m["status"] for m in r["evaluation"]["measures"] if m["source"] == "MEASURED"}, {"INSUFFICIENT_DATA"})
        self.assertNotIn("Kadena", str(r))

    def test_withdrawn_clients_leave_the_results(self):
        pid = self.make()
        pr.leave(pid, pr.ReasonBody(reason="Changing accountant"), self.client, self.w.owner.id, self.w.identity, self.svc)
        r = self.res(pid)
        self.assertEqual((r["clients_included"], r["clients_total"]), (0, 0))

    # ---------------------------------------------------------------- recording
    def test_client_side_recording_is_limited_to_itself(self):
        pid = self.make()
        mem = pr.me(self.w.owner.id, self.client, self.w.identity, self.svc)["membership"]
        self.assertEqual(mem["role"], "CLIENT"); self.assertEqual(mem["firm_org_id"], self.firm)
        today = datetime.now(timezone.utc).date().isoformat()
        # client records about itself without naming itself; a client_org_id for someone else is ignored in favour of its own organisation
        t = pr.log_time(pid, pr.TimeBody(kind="REPORT", minutes=30, performed_on=today, client_org_id="someone-else"), self.client, self.w.owner.id, self.svc)
        self.assertEqual(t["client_org_id"], self.client)
        with self.assertRaises(PilotForbiddenError): pr.log_time(pid, pr.TimeBody(kind="REPORT", minutes=30, performed_on=today), self.firm, self.mgr, self.svc)   # firm must name a client
        i = pr.log_issue(pid, pr.IssueBody(kind="USER_ERROR", severity="LOW", text="Picked the wrong month"), self.client, self.w.accountant.id, self.svc)
        mine = pr.logs(pid, self.client, self.svc)
        self.assertEqual(len(mine["issues"]), 1); self.assertNotIn("reported_by", mine["issues"][0])
        with self.assertRaises(PilotNotFoundError): pr.logs(pid, "unrelated-org", self.svc)
        with self.assertRaises(PilotNotFoundError): pr.logs("no-such-pilot", self.client, self.svc)
        # only the firm can resolve
        done = pr.resolve_issue(pid, i["id"], pr.ResolveBody(resolution="Shown how"), self.firm, self.mgr, self.svc)
        self.assertEqual(done["status"], "RESOLVED")

    def test_survey_and_passport_use_flow_into_the_measures(self):
        pid = self.make()
        pr.log_passport_use(pid, pr.PassportUseBody(purpose="LENDER", outcome="HELPFUL", saved_minutes=90), self.client, self.w.owner.id, self.svc)
        for u, org in ((self.mgr, self.firm), (self.w.accountant.id, self.firm), (self.w.owner.id, self.client)):
            pr.submit_survey(pid, pr.SurveyBody(round="WEEK 2", scores={"overall": 5, "ease": 4, "trust": 5, "recommend": 10, "passport_useful": 4}), org, u, self.svc)
        by = {m["key"]: m for m in self.res(pid)["evaluation"]["measures"]}
        self.assertEqual((by["satisfaction"]["value"], by["satisfaction"]["status"], by["satisfaction"]["source"]), (5.0, "MET", "REPORTED"))

    # ---------------------------------------------------------------- snapshots, report, audit
    def test_snapshot_report_and_audit_trail(self):
        pid = self.make()
        s = pr.take_snapshot(pid, self.firm, self.mgr, self.w.identity, self.svc, self.session)
        self.assertEqual(len(pr.snapshots(pid, self.firm, self.svc)), 1); self.assertEqual(len(s["hash"]), 64)
        rep = pr.report(pid, self.firm, self.mgr, self.w.identity, self.svc, self.session)
        self.assertIn("The eleven measures", rep["markdown"]); self.assertIn("Lagos SME pilot", rep["markdown"]); self.assertIn("small pilot", rep["markdown"])
        self.assertEqual(rep["markdown"].count("\n| "), 12)                                               # header row + 11 measures
        evs = self.w.audit.list_for_org(self.firm)
        self.assertTrue({"PILOT_CREATED", "PILOT_CLIENT_ADDED", "PILOT_STATUS_CHANGED", "PILOT_SNAPSHOT_TAKEN"} <= {e.action for e in evs})
        cevs = self.w.audit.list_for_org(self.client)
        self.assertIn("PILOT_CLIENT_ADDED", {e.action for e in cevs})                                         # the SME's own trail records that it joined
        self.assertTrue(self.ctx.verify_audit(self.firm)["ok"]); self.assertTrue(self.ctx.verify_audit(self.client)["ok"])

    def test_pilot_activity_does_not_count_as_accountant_work(self):
        pid = self.make()
        before = self.res(pid)["clients"][0]["metrics"]["errors"]["work_actions"]
        pr.log_issue(pid, pr.IssueBody(kind="BUG", severity="HIGH", text="Something odd happened"), self.client, self.w.owner.id, self.svc)
        self.assertEqual(self.res(pid)["clients"][0]["metrics"]["errors"]["work_actions"], before)

    def test_leave_rules(self):
        pid = self.make()
        with self.assertRaises(PilotForbiddenError): pr.leave(pid, pr.ReasonBody(reason="x y"), self.client, self.w.accountant.id, self.w.identity, self.svc)   # not an administrator
        with self.assertRaises(PilotForbiddenError): pr.leave(pid, pr.ReasonBody(reason="x y"), self.firm, self.mgr, self.w.identity, self.svc)               # the firm itself
        self.assertTrue(pr.leave(pid, pr.ReasonBody(reason="Not for us"), self.client, self.w.owner.id, self.w.identity, self.svc)["left"])
        self.assertIsNone(pr.me(self.w.owner.id, self.client, self.w.identity, self.svc)["membership"])
        with self.assertRaises(PilotNotFoundError): pr.logs(pid, self.client, self.svc)                                                                          # no longer a participant


if __name__ == "__main__":
    unittest.main()
