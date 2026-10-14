"""End-to-end test server. NOT the production server.

It runs the REAL router functions and REAL services (identity, accounting, evidence, reporting, compliance, Evidence Review, Standards Registry,
Agents, audit chain) behind a small HTTP front, with SQLite in memory and FastAPI stood in for (tests/harness_security_routers.py), so the browser
journeys can drive the real frontend without PostgreSQL. It proves the screens and the services work together. It does NOT prove FastAPI, SQLAlchemy,
PostgreSQL or deployment behaviour: tests/stack/ and CI cover those.

    PYTHONPATH=src:tests python3 e2e/server.py [port]      # default 8790
"""
import dataclasses
import importlib
import json
import os
import re
import sys
import types
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src"), os.path.join(ROOT, "tests")]
import harness_security_routers as H0  # noqa: E402
from harness_security_routers import HTTPException, Request, auth  # noqa: E402
import test_passport as T  # noqa: E402

d = sys.modules["asavexa.api.deps"]
for n in ("get_reporting_service", "get_session", "get_security", "get_identity_service", "get_current_actor", "get_current_org"):
    setattr(d, n, lambda: None)
w = T.World()
w.compliance.evidence = w.vault          # api/deps.py does this in production

from asavexa.agents.service import AgentRegistry  # noqa: E402
from asavexa.evidence.domain.enums import EvidenceType  # noqa: E402
from asavexa.evidencereview.service import EvidenceReviewService  # noqa: E402
from asavexa.identity.domain.errors import AsavexaIdentityError, PermissionDeniedError  # noqa: E402
from asavexa.identity.domain.permissions import (AUDIT_READ, FINDING_MANAGE, FINDING_REMEDIATE, FINDING_VERIFY, GRC_APPROVE, GRC_PREPARE,  # noqa: E402
                                                 ORG_MANAGE_SETTINGS, REPORTING_READ, PROCURE_APPROVE, PROCURE_PREPARE, FPA_APPROVE, FPA_PREPARE, FINCRIME_APPROVE, FINCRIME_PREPARE, FINCRIME_READ, ROLE_PERMISSIONS, TREASURY_APPROVE, TREASURY_PREPARE)
from asavexa.reporting.services.service import ReportingService  # noqa: E402
from asavexa.security import crypto  # noqa: E402
from asavexa.security.auditchain import ChainedAuditRepository  # noqa: E402
from asavexa.security.context import SecurityContext  # noqa: E402
from asavexa.security.errors import SecurityError  # noqa: E402
from asavexa.security.objectstore import MemoryObjectStore  # noqa: E402
from asavexa.security.sessions import SessionPolicy  # noqa: E402
from asavexa.security.store import SqliteDocStore  # noqa: E402
from asavexa.standards import catalog as CAT  # noqa: E402
from asavexa.standards.registry import StandardsRegistry  # noqa: E402
from asavexa.api import ratelimit  # noqa: E402

for name in ("get_evidence_review", "get_standards_registry", "get_agent_registry"):
    setattr(d, name, lambda: None)
er = importlib.import_module("asavexa.api.routers.evidence_review")
srt = importlib.import_module("asavexa.api.routers.standards_registry")
agr = importlib.import_module("asavexa.api.routers.agents")
asr = importlib.import_module("asavexa.api.routers.assurance")
plr = importlib.import_module("asavexa.api.routers.proof_links")
ecr = importlib.import_module("asavexa.api.routers.entity_config")
trr = importlib.import_module("asavexa.api.routers.treasury")
prr = importlib.import_module("asavexa.api.routers.procurement")
fpr = importlib.import_module("asavexa.api.routers.fpa")
fcr = importlib.import_module("asavexa.api.routers.fincrime")
ratelimit.LOGIN.limit = ratelimit.MFA.limit = 10000

store = SqliteDocStore(w.conn)
keys = crypto.LocalKeyring({"k1": crypto.LocalKeyring.generate_key()}, "k1")
CH = ChainedAuditRepository(T.SqliteAuditRepository(w.conn), store, keys)
w.identity.audit = CH
ctx = SecurityContext(w.identity, CH, store, keys=keys, objects=MemoryObjectStore("NG"), now=lambda: datetime.now(timezone.utc), commit=w.conn.commit,
                      policy=SessionPolicy(idle_minutes=30, max_sessions=5), database_region="NG")


def log_for(kind):
    return lambda action, actor, eid, org, reason="": ctx.log(action, actor, eid, org_id=org, entity_type=kind, reason=reason)


is_member = lambda o, u: w.identity.memberships.get(o, u) is not None  # noqa: E731
rep = ReportingService(accounting=w.accounting, audit=w.audit, evidence=w.vault)
ers = EvidenceReviewService(store, rep, w.vault, w.compliance, is_member=is_member, log=log_for("EvidenceReview"))
srg = StandardsRegistry(store, log=log_for("StandardsRegistry"))
agrg = AgentRegistry(store, is_member=is_member, log=log_for("Agent"))
from asavexa.assurance.service import AssuranceService  # noqa: E402
asvc = AssuranceService({
    "evidence": lambda org: [(r.id, r.status.value, {"uploaded_by": r.uploaded_by, "verified_by": r.verified_by}) for r in w.vault.list_for_org(org)],
    "finding": lambda org: [(f.id, f.status.value, {}) for f in w.compliance.list_findings(org)],
    "evidence_review_case": lambda org: [(c["id"], c["status"], {}) for c in ers.list_cases(org)],
    "standards_source": lambda org: [(x["id"], x["status"], {}) for x in srg.list_sources(org)],
    "agent_decision": lambda org: [(d["id"], d["state"], {}) for d in agrg.list_decisions(org)],
})


from asavexa.proofgraph.links import ProofLinks  # noqa: E402
from asavexa.proofgraph.wiring import make_sources  # noqa: E402
pls = ProofLinks(store, make_sources(store, w.vault, w.compliance), log=log_for("ProofLink"))
ers.links = pls
from asavexa.entities.service import EntityConfigService  # noqa: E402
from asavexa.workspaces import WORKSPACES, catalog as ws_catalog  # noqa: E402
ecs = EntityConfigService(store, lambda: [x["id"] for x in WORKSPACES], log=log_for("EntityConfig"))
from asavexa.treasury.service import TreasuryService  # noqa: E402
trs = TreasuryService(store, w.vault, log=log_for("Treasury"))
from asavexa.procurement.service import ProcurementService  # noqa: E402
prs = ProcurementService(store, log=log_for("Procurement"))
from asavexa.fpa.service import FpaService  # noqa: E402


def _fpa_member(o, u):
    m = w.identity.memberships.get(o, u)
    return m is not None and m.status.value == "ACTIVE"


def _fpa_can_record(o, u):
    m = w.identity.memberships.get(o, u)
    return m is not None and FPA_PREPARE in ROLE_PERMISSIONS.get(m.role, ())


from asavexa.fincrime.service import FincrimeService  # noqa: E402


def _fc_can_work(o, u):
    m = w.identity.memberships.get(o, u)
    return m is not None and FINCRIME_PREPARE in ROLE_PERMISSIONS.get(m.role, ())


fcs = FincrimeService(store, w.vault, is_member=_fpa_member, can_work=_fc_can_work, log=log_for("Fincrime"))
_fpa_shift = {"days": 0}      # test-only: lets a journey move the Planning and KPIs clock forward so a forecast period can end
fps = FpaService(store, w.vault, is_member=_fpa_member, can_record=_fpa_can_record, log=log_for("Fpa"),
                 now=lambda: datetime.now(timezone.utc) + timedelta(days=_fpa_shift["days"]))


def j(o):
    return json.dumps(o, default=lambda x: dataclasses.asdict(x) if dataclasses.is_dataclass(x) else (x.value if hasattr(x, "value") else (x.isoformat() if hasattr(x, "isoformat") else str(x))))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else j(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def do_GET(self): self.go("GET")
    def do_POST(self): self.go("POST")
    def do_PUT(self): self.go("PUT")

    def go(self, m):
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        path, _, q = self.path.partition("?")
        qs = dict(x.split("=", 1) for x in q.split("&") if "=" in x)
        req = Request({"user-agent": self.headers.get("user-agent", ""), "x-forwarded-for": "7.7.7.7"})
        try:
            out = self.dispatch(m, path, qs, body, req)
            return self.send(*out) if isinstance(out, tuple) else self.send(200, out)
        except HTTPException as e: self.send(e.status_code, {"detail": e.detail})
        except SecurityError as e: self.send(e.status, {"error": type(e).__name__, "message": str(e)})
        except PermissionDeniedError as e: self.send(403, {"error": type(e).__name__, "message": str(e)})
        except AsavexaIdentityError as e: self.send(401, {"error": type(e).__name__, "message": str(e)})
        except Exception as e:
            import traceback; traceback.print_exc(); self.send(500, {"error": "InternalServerError", "message": str(e)})

    def dispatch(self, m, path, qs, b, req):
        if path == "/auth/login": return auth.login(req, auth.LoginRequest(**b), ctx).model_dump()
        tok = (self.headers.get("authorization") or "")[7:]
        s = w.identity.validate_session(tok); ctx.check_session(s)
        if path == "/organisations/mine":
            return [w.identity.organisations.get(x.org_id) for x in w.identity.memberships.list_for_user(s.user_id) if x.status.value == "ACTIVE"]
        if path == "/auth/select-organisation":
            s = w.identity.select_organisation(tok, b["org_id"]); return {"org_id": s.org_id, "role": w.identity.get_role(s.user_id, b["org_id"]).value}
        if path == "/auth/logout": w.identity.logout(tok); return (204, b"")
        org, a = s.org_id, s.user_id
        r = w.identity.get_role(a, org)

        def need(p):
            if r is None or p not in ROLE_PERMISSIONS[r]: raise PermissionDeniedError("You do not have " + p + ".")
        if path == "/periods": return w.accounting.periods.list_for_org(org)
        if path.startswith("/organisations/") and path.endswith("/members"): return w.identity.list_members(org)
        if path == "/standards/catalog": return {"frameworks": [{"code": k, **v} for k, v in CAT.FRAMEWORKS.items()], "jurisdictions": [{"code": k, "name": v} for k, v in CAT.JURISDICTIONS.items()]}
        # ---- test-only hooks the journeys use to play "the person who does the work in the Evidence Vault"
        if path == "/_fix":
            ev = w.vault.upload_evidence(org, EvidenceType.CONTRACT, b"lease-browser", "lease.pdf", "application/pdf", uploaded_by=w.accountant.id, linked_journal_id=w.rent_journal.id)
            w.vault.verify_evidence(org, ev.id, actor=w.approver.id); return {"ev": ev.id}
        if path == "/_fpa_clock":
            _fpa_shift["days"] = int(qs.get("days", 0)); return {"days": _fpa_shift["days"]}
        if path == "/_audit":
            evs, _ = w.audit.list_recent_for_org(org, 1000); return {"actions": [e.action for e in evs]}
        if path.startswith("/evidence-review"):
            need(REPORTING_READ)
            if path == "/evidence-review/review": return er.review(qs["period_id"], qs.get("report", "income_statement"), qs.get("account_id"), org, a, ers)
            if path == "/evidence-review/rules" and m == "GET": return er.rules_overview(org, ers)
            if path == "/evidence-review/rules" and m == "POST": need(GRC_PREPARE); return (201, er.propose_rules(er.RulesBody(**b), org, a, ers))
            mm = re.match(r"/evidence-review/rules/(\d+)/(approve|reject)$", path)
            if mm:
                need(GRC_APPROVE)
                return er.approve_rules(int(mm.group(1)), er.DecisionBody(**b), org, a, ers) if mm.group(2) == "approve" else er.reject_rules(int(mm.group(1)), er.RejectBody(**b), org, a, ers)
            if path == "/evidence-review/cases" and m == "GET": return er.list_cases(None, org, ers)
            if path == "/evidence-review/cases" and m == "POST": need(FINDING_MANAGE); return (201, er.open_case(er.OpenBody(**b), org, a, ers))
            mm = re.match(r"/evidence-review/cases/([^/]+)(?:/(\w+))?$", path)
            if mm:
                cid, act = mm.groups()
                if act is None: return er.get_case(cid, org, ers)
                if act == "plan": need(FINDING_MANAGE); return er.plan(cid, er.PlanBody(**b), org, a, ers)
                if act == "complete": need(FINDING_REMEDIATE); return er.complete(cid, er.DoneBody(**b), org, a, ers)
                if act == "verify": need(FINDING_VERIFY); return er.verify(cid, er.VerifyBody(**b), org, a, ers)
                if act == "recheck": need(FINDING_VERIFY); return er.recheck(cid, org, a, ers)
        if path.startswith("/assurance"):
            need(AUDIT_READ)
            if path == "/assurance/vocabulary": return asr.vocabulary()
            if path == "/assurance/summary": return asr.summary(org, asvc)
        if path == "/workspaces": return ws_catalog()
        if path == "/organisation-profile": return {"organisation_type": "Business or SME"}
        if path.startswith("/entity-config"):
            if path == "/entity-config/catalog": return ecr.catalog(org)
            if path == "/entity-config" and m == "GET": return ecr.read(org, ecs)
            if path == "/entity-config" and m == "PUT": need(ORG_MANAGE_SETTINGS); return ecr.save(ecr.EntityConfigBody(**b), org, a, ecs)
        if path.startswith("/procurement"):
            need(REPORTING_READ); sub = path[len("/procurement"):]; P, A_ = PROCURE_PREPARE, PROCURE_APPROVE
            if sub == "/options": return prr.options(org, prs)
            if sub == "/overview": return prr.overview(org, prs)
            if sub == "/policy" and m == "GET": return prr.policy(org, prs)
            if sub == "/policy" and m == "PUT": need(A_); return prr.set_policy(prr.PolicyBody(**b), org, a, prs)
            if sub == "/suppliers" and m == "GET": return prr.suppliers(qs.get("status"), org, prs)
            if sub == "/suppliers" and m == "POST": need(P); return (201, prr.register_supplier(prr.SupplierBody(**b), org, a, prs))
            mm = re.match(r"/suppliers/([^/]+)$", sub)
            if mm: return prr.get_supplier(mm.group(1), org, prs)
            mm = re.match(r"/suppliers/([^/]+)/(approve|suspend|reinstate)$", sub)
            if mm:
                need(A_); sid, act = mm.groups(); fn = {"approve": prr.approve_supplier, "suspend": prr.suspend_supplier, "reinstate": prr.reinstate_supplier}[act]
                return fn(sid, prr.NoteBody(**b), org, a, prs)
            mm = re.match(r"/suppliers/([^/]+)/reviews$", sub)
            if mm: need(P); return (201, prr.add_review(mm.group(1), prr.ReviewBody(**b), org, a, prs))
            if sub == "/contracts" and m == "GET": return prr.contracts(org, prs)
            if sub == "/contracts" and m == "POST": need(P); return (201, prr.draft_contract(prr.ContractBody(**b), org, a, prs))
            mm = re.match(r"/contracts/([^/]+)$", sub)
            if mm: return prr.get_contract(mm.group(1), org, prs)
            mm = re.match(r"/contracts/([^/]+)/(approve|terminate)$", sub)
            if mm:
                need(A_); cid, act = mm.groups(); return (prr.approve_contract if act == "approve" else prr.terminate_contract)(cid, prr.NoteBody(**b), org, a, prs)
            if sub == "/orders" and m == "GET": return prr.orders(qs.get("status"), qs.get("supplier_id"), org, prs)
            if sub == "/orders" and m == "POST": need(P); return (201, prr.raise_order(prr.OrderBody(**b), org, a, prs))
            mm = re.match(r"/orders/([^/]+)$", sub)
            if mm: return prr.get_order(mm.group(1), org, prs)
            mm = re.match(r"/orders/([^/]+)/(approve|reject)$", sub)
            if mm: need(A_); oid, act = mm.groups(); return (prr.approve_order if act == "approve" else prr.reject_order)(oid, prr.NoteBody(**b), org, a, prs)
            mm = re.match(r"/orders/([^/]+)/(cancel|close)$", sub)
            if mm: need(P); oid, act = mm.groups(); return (prr.cancel_order if act == "cancel" else prr.close_order)(oid, prr.NoteBody(**b), org, a, prs)
            mm = re.match(r"/orders/([^/]+)/deliveries$", sub)
            if mm: need(P); return (201, prr.add_delivery(mm.group(1), prr.DeliveryBody(**b), org, a, prs))
            mm = re.match(r"/orders/([^/]+)/invoices$", sub)
            if mm: need(P); return (201, prr.add_invoice(mm.group(1), prr.InvoiceBody(**b), org, a, prs))
            if sub == "/deliveries": return prr.deliveries(qs.get("order_id"), org, prs)
            if sub == "/invoices": return prr.invoices(qs.get("status"), qs.get("order_id"), org, prs)
            if sub == "/reviews": return prr.reviews(qs.get("supplier_id"), org, prs)
            mm = re.match(r"/invoices/([^/]+)$", sub)
            if mm: return prr.get_invoice(mm.group(1), org, prs)
            mm = re.match(r"/invoices/([^/]+)/(approve|reject)$", sub)
            if mm: need(A_); iid, act = mm.groups(); return (prr.approve_invoice if act == "approve" else prr.reject_invoice)(iid, prr.NoteBody(**b), org, a, prs)
            mm = re.match(r"/invoices/([^/]+)/paid$", sub)
            if mm: need(P); return prr.pay_invoice(mm.group(1), prr.PaidBody(**b), org, a, prs)
        if path.startswith("/fpa"):
            need(REPORTING_READ); sub = path[len("/fpa"):]; P, A_ = FPA_PREPARE, FPA_APPROVE
            if sub == "/options": return fpr.options(org, fps)
            if sub == "/overview": return fpr.overview(org, fps)
            if sub == "/policy" and m == "GET": return fpr.policy(org, fps)
            if sub == "/policy" and m == "PUT": need(A_); return fpr.set_policy(fpr.PolicyBody(**b), org, a, fps)
            if sub == "/kpis" and m == "GET": return fpr.kpis(qs.get("status"), qs.get("owner"), org, fps)
            if sub == "/kpis" and m == "POST": need(P); return (201, fpr.define_kpi(fpr.KpiBody(**b), org, a, fps))
            mm = re.match(r"/kpis/([^/]+)$", sub)
            if mm: return fpr.get_kpi(mm.group(1), org, fps)
            mm = re.match(r"/kpis/([^/]+)/(approve|retire)$", sub)
            if mm: need(A_); kid, act = mm.groups(); return (fpr.approve_kpi if act == "approve" else fpr.retire_kpi)(kid, fpr.NoteBody(**b), org, a, fps)
            mm = re.match(r"/kpis/([^/]+)/accept$", sub)
            if mm: need(P); return fpr.accept_ownership(mm.group(1), org, a, fps)
            mm = re.match(r"/kpis/([^/]+)/owner$", sub)
            if mm: need(A_); return fpr.change_owner(mm.group(1), fpr.OwnerBody(**b), org, a, fps)
            mm = re.match(r"/kpis/([^/]+)/readings$", sub)
            if mm: need(P); return (201, fpr.add_reading(mm.group(1), fpr.ReadingBody(**b), org, a, fps))
            mm = re.match(r"/kpis/([^/]+)/readings/([^/]+)/(review|reject)$", sub)
            if mm: need(A_); kid, rid, act = mm.groups(); return (fpr.review_reading if act == "review" else fpr.reject_reading)(kid, rid, fpr.NoteBody(**b), org, a, fps)
            if sub == "/forecasts" and m == "GET": return fpr.forecasts(qs.get("status"), org, fps)
            if sub == "/forecasts" and m == "POST": need(P); return (201, fpr.register_forecast(fpr.ForecastBody(**b), org, a, fps))
            mm = re.match(r"/forecasts/([^/]+)$", sub)
            if mm: return fpr.get_forecast(mm.group(1), org, fps)
            mm = re.match(r"/forecasts/([^/]+)/withdraw$", sub)
            if mm: need(P); return fpr.withdraw_forecast(mm.group(1), fpr.NoteBody(**b), org, a, fps)
            mm = re.match(r"/forecasts/([^/]+)/actual$", sub)
            if mm: need(P); return fpr.add_actual(mm.group(1), fpr.ActualBody(**b), org, a, fps)
            mm = re.match(r"/forecasts/([^/]+)/actual/(confirm|reject)$", sub)
            if mm: need(A_); fid, act = mm.groups(); return (fpr.confirm_actual if act == "confirm" else fpr.reject_actual)(fid, fpr.NoteBody(**b), org, a, fps)
            if sub == "/accuracy": return fpr.accuracy(int(qs.get("min_lead_days", 0)), org, fps)
        if path.startswith("/fincrime"):
            need(FINCRIME_READ); sub = path[len("/fincrime"):]; P, A_ = FINCRIME_PREPARE, FINCRIME_APPROVE
            if sub == "/options": return fcr.options(org, fcs)
            if sub == "/overview": return fcr.overview(org, fcs)
            if sub == "/policy" and m == "GET": return fcr.policy(org, fcs)
            if sub == "/policy" and m == "PUT": need(A_); return fcr.set_policy(fcr.PolicyBody(**b), org, a, fcs)
            if sub == "/alerts" and m == "GET": return fcr.alerts(qs.get("status"), org, fcs)
            if sub == "/alerts" and m == "POST": need(P); return (201, fcr.raise_alert(fcr.AlertBody(**b), org, a, fcs))
            mm = re.match(r"/alerts/([^/]+)/dismiss$", sub)
            if mm: need(A_); return fcr.dismiss_alert(mm.group(1), fcr.ReasonBody(**b), org, a, fcs)
            if sub == "/cases" and m == "GET": return fcr.cases(qs.get("status"), org, fcs)
            if sub == "/cases" and m == "POST": need(P); return (201, fcr.open_case(fcr.CaseBody(**b), org, a, fcs))
            mm = re.match(r"/cases/([^/]+)$", sub)
            if mm: return fcr.get_case(mm.group(1), org, fcs)
            mm = re.match(r"/cases/([^/]+)/declaration$", sub)
            if mm: return fcr.declare_interest(mm.group(1), fcr.DeclareBody(**b), org, a, fcs)
            mm = re.match(r"/cases/([^/]+)/lead$", sub)
            if mm: need(A_); return fcr.change_lead(mm.group(1), fcr.LeadBody(**b), org, a, fcs)
            mm = re.match(r"/cases/([^/]+)/events$", sub)
            if mm: need(P); return (201, fcr.add_event(mm.group(1), fcr.EventBody(**b), org, a, fcs))
            mm = re.match(r"/cases/([^/]+)/screenings$", sub)
            if mm: need(P); return (201, fcr.record_screening(mm.group(1), fcr.ScreeningBody(**b), org, a, fcs))
            mm = re.match(r"/cases/([^/]+)/screenings/([^/]+)/resolve$", sub)
            if mm: need(A_); return fcr.resolve_screening(mm.group(1), mm.group(2), fcr.ResolveBody(**b), org, a, fcs)
            mm = re.match(r"/cases/([^/]+)/losses$", sub)
            if mm: need(P); return (201, fcr.record_loss(mm.group(1), fcr.LossBody(**b), org, a, fcs))
            mm = re.match(r"/cases/([^/]+)/recoveries$", sub)
            if mm: need(P); return (201, fcr.record_recovery(mm.group(1), fcr.RecoveryBody(**b), org, a, fcs))
            mm = re.match(r"/cases/([^/]+)/recoveries/([^/]+)/(confirm|reject)$", sub)
            if mm:
                need(A_); cid, rid, act = mm.groups()
                return fcr.confirm_recovery(cid, rid, org, a, fcs) if act == "confirm" else fcr.reject_recovery(cid, rid, fcr.ReasonBody(**b), org, a, fcs)
            mm = re.match(r"/cases/([^/]+)/decision$", sub)
            if mm: need(P); return fcr.propose_decision(mm.group(1), fcr.DecisionBody(**b), org, a, fcs)
            mm = re.match(r"/cases/([^/]+)/decision/(approve|reject)$", sub)
            if mm:
                need(A_); cid, act = mm.groups()
                return fcr.approve_decision(cid, fcr.NoteBody(**b), org, a, fcs) if act == "approve" else fcr.reject_decision(cid, fcr.ReasonBody(**b), org, a, fcs)
            mm = re.match(r"/cases/([^/]+)/reopen$", sub)
            if mm: need(A_); return fcr.reopen_case(mm.group(1), fcr.ReasonBody(**b), org, a, fcs)
        if path.startswith("/treasury"):
            need(REPORTING_READ); sub = path[len("/treasury"):]; P, A_ = TREASURY_PREPARE, TREASURY_APPROVE
            if sub == "/options": return trr.options(org, trs)
            if sub == "/overview": return trr.overview(org, trs)
            if sub == "/position": return trr.position(org, trs)
            if sub == "/forecast": return trr.forecast(int(qs.get("weeks", 13)), qs.get("include_possible") == "true", org, trs)
            if sub == "/forecast-accuracy": return trr.accuracy(org, trs)
            if sub == "/policy" and m == "GET": return trr.policy(org, trs)
            if sub == "/policy" and m == "PUT": need(A_); return trr.set_policy(trr.PolicyBody(**b), org, a, trs)
            if sub == "/accounts" and m == "GET": return trr.accounts(org, trs)
            if sub == "/accounts" and m == "POST": need(P); return (201, trr.open_account(trr.AccountBody(**b), org, a, trs))
            mm = re.match(r"/accounts/([^/]+)$", sub)
            if mm and m == "GET": return trr.get_account(mm.group(1), org, trs)
            mm = re.match(r"/accounts/([^/]+)/close$", sub)
            if mm: need(P); return trr.close_account(mm.group(1), trr.NoteBody(**b), org, a, trs)
            mm = re.match(r"/accounts/([^/]+)/balances$", sub)
            if mm: need(P); return (201, trr.add_balance(mm.group(1), trr.BalanceBody(**b), org, a, trs))
            mm = re.match(r"/accounts/([^/]+)/balances/([^/]+)/confirm$", sub)
            if mm: need(A_); return trr.confirm_balance(mm.group(1), mm.group(2), org, a, trs)
            if sub == "/flows" and m == "GET": return trr.flows(qs.get("status"), qs.get("currency"), org, trs)
            if sub == "/flows" and m == "POST": need(P); return (201, trr.add_flow(trr.FlowBody(**b), org, a, trs))
            mm = re.match(r"/flows/([^/]+)$", sub)
            if mm and m == "GET": return trr.get_flow(mm.group(1), org, trs)
            if mm and m == "PUT": need(P); return trr.change_flow(mm.group(1), trr.FlowChangeBody(**b), org, a, trs)
            mm = re.match(r"/flows/([^/]+)/(realise|cancel)$", sub)
            if mm:
                need(P); fid, act = mm.groups()
                return trr.realise_flow(fid, trr.RealiseBody(**b), org, a, trs) if act == "realise" else trr.cancel_flow(fid, trr.NoteBody(**b), org, a, trs)
            if sub == "/payments" and m == "GET": return trr.payments(qs.get("status"), org, trs)
            if sub == "/payments" and m == "POST": need(P); return (201, trr.request_payment(trr.PaymentBody(**b), org, a, trs))
            mm = re.match(r"/payments/([^/]+)$", sub)
            if mm and m == "GET": return trr.get_payment(mm.group(1), org, trs)
            mm = re.match(r"/payments/([^/]+)/(approve|reject|cancel|release)$", sub)
            if mm:
                pid, act = mm.groups(); need(A_ if act in ("approve", "reject") else P)
                if act == "release": return trr.release_payment(pid, trr.ReleaseBody(**b), org, a, trs)
                return getattr(trr, act + "_payment")(pid, trr.NoteBody(**b), org, a, trs)
            if sub == "/covenants" and m == "GET": return trr.covenants(org, trs)
            if sub == "/covenants" and m == "POST": need(P); return (201, trr.add_covenant(trr.CovenantBody(**b), org, a, trs))
            mm = re.match(r"/covenants/([^/]+)$", sub)
            if mm and m == "GET": return trr.get_covenant(mm.group(1), org, trs)
            mm = re.match(r"/covenants/([^/]+)/retire$", sub)
            if mm: need(P); return trr.retire_covenant(mm.group(1), trr.NoteBody(**b), org, a, trs)
            mm = re.match(r"/covenants/([^/]+)/results$", sub)
            if mm: need(P); return (201, trr.add_result(mm.group(1), trr.ResultBody(**b), org, a, trs))
            mm = re.match(r"/covenants/([^/]+)/results/([^/]+)/acknowledge$", sub)
            if mm: need(A_); return trr.acknowledge(mm.group(1), mm.group(2), trr.AckBody(**b), org, a, trs)
        if path.startswith("/proof-links"):
            need(AUDIT_READ)
            if path == "/proof-links/vocabulary": return plr.vocabulary()
            if path == "/proof-links/choices": return plr.choices(qs["type"], org, pls)
            if path == "/proof-links/graph": return plr.graph(qs["type"], qs["id"], int(qs.get("depth", 1)), False, org, pls)
            if path == "/proof-links" and m == "GET": return plr.list_all(qs.get("status"), org, pls)
            if path == "/proof-links" and m == "POST": need(GRC_PREPARE); return (201, plr.add(plr.LinkBody(**b), org, a, pls))
            if path == "/proof-links/gaps" and m == "POST": need(GRC_PREPARE); return (201, plr.expect(plr.GapBody(**b), org, a, pls))
            mm = re.match(r"/proof-links/gaps/([^/]+)/waive$", path)
            if mm: need(GRC_APPROVE); return plr.waive(mm.group(1), plr.ReasonBody(**b), org, a, pls)
            mm = re.match(r"/proof-links/([^/]+)$", path)
            if mm and m == "GET": return plr.get_one(mm.group(1), org, pls)
            mm = re.match(r"/proof-links/([^/]+)/(retire|dispute|confirm|reinstate)$", path)
            if mm:
                lid, act = mm.groups()
                if act in ("retire", "dispute"): need(GRC_PREPARE)
                else: need(GRC_APPROVE)
                body = plr.NoteBody(**b) if act == "confirm" else plr.ReasonBody(**b)
                return getattr(plr, act)(lid, body, org, a, pls)
        if path.startswith("/standards-registry"):
            need(AUDIT_READ)
            if path == "/standards-registry/coverage": return srt.coverage(qs.get("jurisdiction"), org, srg)
            if path == "/standards-registry/sources" and m == "GET": return srt.list_sources(None, None, org, srg)
            if path == "/standards-registry/sources" and m == "POST": need(GRC_PREPARE); return (201, srt.add_source(srt.SourceBody(**b), org, a, srg))
            mm = re.match(r"/standards-registry/sources/([^/]+)/([\w-]+)$", path)
            if mm:
                sid, act = mm.groups()
                if act == "submit": need(GRC_PREPARE); return srt.submit(sid, org, a, srg)
                need(GRC_APPROVE)
                if act == "approve": return srt.approve(sid, srt.NoteBody(**b), org, a, srg)
                if act == "send-back": return srt.send_back(sid, srt.ReasonBody(**b), org, a, srg)
                if act == "withdraw": return srt.withdraw(sid, srt.ReasonBody(**b), org, a, srg)
        if path.startswith("/agents"):
            need(AUDIT_READ)
            if path == "/agents/catalog": return agr.catalog(org, agrg)
            if path == "/agents/decisions" and m == "GET": return agr.list_decisions(None, org, agrg)
            if path == "/agents/decisions" and m == "POST": need(GRC_PREPARE); return (201, agr.decide(agr.DecideBody(**b), org, a, agrg))
            if path == "/agents/policy": need(GRC_APPROVE); return agr.tighten(agr.PolicyBody(**b), org, a, agrg)
            if path == "/agents" and m == "GET": return agr.list_agents(org, agrg)
            if path == "/agents" and m == "POST": need(GRC_PREPARE); return (201, agr.propose(agr.AgentBody(**b), org, a, agrg))
            mm = re.match(r"/agents/decisions/([^/]+)/(resolve|confirm)$", path)
            if mm:
                did, act = mm.groups()
                if act == "resolve": need(GRC_APPROVE); return agr.resolve(did, agr.ResolveBody(**b), org, a, agrg)
                need(GRC_PREPARE); return agr.confirm(did, org, a, agrg)
            mm = re.match(r"/agents/([^/]+)/(activate|suspend|retire)$", path)
            if mm:
                aid, act = mm.groups(); need(GRC_APPROVE)
                if act == "activate": return agr.activate(aid, agr.NoteBody(**b), org, a, agrg)
                return getattr(agr, act)(aid, agr.ReasonBody(**b), org, a, agrg)
        return (404, {"detail": "no route " + path})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8790
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
