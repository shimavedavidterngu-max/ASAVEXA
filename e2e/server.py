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
# a second person who can prepare IT-audit work, so one person records and a different person tests (an Administrator holds itaudit:prepare but no approval or case powers)
from asavexa.identity.domain.enums import Role as _Role  # noqa: E402
_tunde = w.identity.register_user("tunde@meridian.test", "tester-password-two1")
w.identity.add_membership(w.org.id, _tunde.id, _Role.ADMINISTRATOR, actor_user_id=w.owner.id)

from asavexa.agents.service import AgentRegistry  # noqa: E402
from asavexa.evidence.domain.enums import EvidenceType  # noqa: E402
from asavexa.evidencereview.service import EvidenceReviewService  # noqa: E402
from asavexa.identity.domain.errors import AsavexaIdentityError, PermissionDeniedError  # noqa: E402
from asavexa.identity.domain.permissions import (AUDIT_READ, FINDING_MANAGE, FINDING_REMEDIATE, FINDING_VERIFY, GRC_APPROVE, GRC_PREPARE,  # noqa: E402
                                                 ORG_MANAGE_SETTINGS, REPORTING_READ, PROCURE_APPROVE, PROCURE_PREPARE, FPA_APPROVE, FPA_PREPARE, FINCRIME_APPROVE, FINCRIME_PREPARE, FINCRIME_READ, ITAUDIT_APPROVE, ITAUDIT_PREPARE, RESIL_APPROVE, RESIL_PREPARE, AIG_APPROVE, AIG_PREPARE, QUAL_APPROVE, QUAL_PREPARE, SEC_APPROVE, SEC_PREPARE, FIX_APPROVE, FIX_PREPARE, INV_APPROVE, INV_PREPARE, INVEST_APPROVE, INVEST_PREPARE, VAL_APPROVE, VAL_PREPARE, INS_APPROVE, INS_PREPARE, ESG_APPROVE, ESG_PREPARE, PAY_APPROVE, PAY_PREPARE, PROJ_APPROVE, PROJ_PREPARE, DG_APPROVE, DG_PREPARE, OPR_APPROVE, OPR_PREPARE, IMP_APPROVE, IMP_PREPARE, ISV_APPROVE, ISV_PREPARE, PEN_APPROVE, PEN_PREPARE, FCH_APPROVE, FCH_PREPARE, MNA_APPROVE, MNA_PREPARE, APW_APPROVE, APW_PREPARE, ROLE_PERMISSIONS, TREASURY_APPROVE, TREASURY_PREPARE,
                                                 HEALTH_READ, HEALTH_PREPARE, HEALTH_APPROVE, HEALTH_ADMIN, HEALTH_CLAIMS, HEALTH_STAFFING, PUBFIN_PREPARE, PUBFIN_APPROVE)
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
iar = importlib.import_module("asavexa.api.routers.itaudit")
rsr = importlib.import_module("asavexa.api.routers.resilience")
gvr = importlib.import_module("asavexa.api.routers.aigov")
qlr = importlib.import_module("asavexa.api.routers.quality")
scr = importlib.import_module("asavexa.api.routers.secretarial")
fxr = importlib.import_module("asavexa.api.routers.fixedassets")
ivr = importlib.import_module("asavexa.api.routers.inventory")
imr = importlib.import_module("asavexa.api.routers.investments")
vlr = importlib.import_module("asavexa.api.routers.valuation")
icr = importlib.import_module("asavexa.api.routers.insurance")
esr = importlib.import_module("asavexa.api.routers.esg")
pwr = importlib.import_module("asavexa.api.routers.payroll")
pjr = importlib.import_module("asavexa.api.routers.projects")
dgr = importlib.import_module("asavexa.api.routers.datagov")
opr = importlib.import_module("asavexa.api.routers.oprs")
impr = importlib.import_module("asavexa.api.routers.impact")
isvr = importlib.import_module("asavexa.api.routers.insolvency")
penr = importlib.import_module("asavexa.api.routers.pension")
fchr = importlib.import_module("asavexa.api.routers.franchise")
mar = importlib.import_module("asavexa.api.routers.mergers")
apwr = importlib.import_module("asavexa.api.routers.approvals")
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
from asavexa.itaudit.service import ItAuditService  # noqa: E402
ias = ItAuditService(store, w.vault, log=log_for("ItAudit"))
from asavexa.resilience.service import ResilienceService  # noqa: E402
rss = ResilienceService(store, w.vault, log=log_for("Resilience"))
from asavexa.aigov.service import AigovService  # noqa: E402
gvs = AigovService(store, w.vault, log=log_for("AiGovernance"))
from asavexa.quality.service import QualityService  # noqa: E402
qls = QualityService(store, w.vault, log=log_for("Quality"))
from asavexa.secretarial.service import SecretarialService  # noqa: E402
scs = SecretarialService(store, w.vault, log=log_for("Secretarial"))
from asavexa.fixedassets.service import FixedAssetService  # noqa: E402
fxs = FixedAssetService(store, w.vault, log=log_for("FixedAssets"))
from asavexa.inventory.service import InventoryService  # noqa: E402
ivs = InventoryService(store, w.vault, log=log_for("Inventory"))
from asavexa.investments.service import InvestmentsService  # noqa: E402
ims = InvestmentsService(store, w.vault, log=log_for("Investments"))
from asavexa.valuation.service import ValuationService  # noqa: E402
vls = ValuationService(store, w.vault, log=log_for("Valuation"))
from asavexa.insurance.service import InsuranceService  # noqa: E402
ics = InsuranceService(store, w.vault, log=log_for("Insurance"))
from asavexa.esg.service import EsgService  # noqa: E402
ess = EsgService(store, w.vault, log=log_for("Esg"))
from asavexa.payroll.service import PayrollService  # noqa: E402
pws = PayrollService(store, w.vault, log=log_for("Payroll"))
from asavexa.projects.service import ProjectsService  # noqa: E402
pjs = ProjectsService(store, w.vault, log=log_for("Projects"))
from asavexa.datagov.service import DatagovService  # noqa: E402
dgs = DatagovService(store, w.vault, log=log_for("Datagov"))
DG_ROUTES = [
    ('GET', '^/options$', '', 'options', '', False, False),
    ('GET', '^/overview$', '', 'overview', '', False, False),
    ('GET', '^/setting$', '', 'setting', '', False, False),
    ('PUT', '^/setting$', 'A', 'set_setting', 'SettingBody', False, False),
    ('GET', '^/assets$', '', 'assets', '', True, False),
    ('POST', '^/assets$', 'P', 'add_asset', 'AssetBody', False, True),
    ('GET', '^/assets/([^/]+)$', '', 'get_asset', '', False, False),
    ('POST', '^/assets/([^/]+)/approve$', 'A', 'approve_asset', 'NoteBody', False, False),
    ('POST', '^/assets/([^/]+)/reject$', 'A', 'reject_asset', 'ReasonBody', False, False),
    ('POST', '^/assets/([^/]+)/retire$', 'A', 'retire_asset', 'ReasonBody', False, False),
    ('POST', '^/assets/([^/]+)/reviews$', 'P', 'add_review', 'ReviewBody', False, False),
    ('POST', '^/assets/([^/]+)/reviews/(?P<n_no>\\d+)/confirm$', 'A', 'confirm_review', 'NoteBody', False, False),
    ('POST', '^/assets/([^/]+)/reviews/(?P<n_no>\\d+)/reject$', 'A', 'reject_review', 'ReasonBody', False, False),
    ('POST', '^/assets/([^/]+)/grants$', 'P', 'add_grant', 'GrantBody', False, False),
    ('POST', '^/assets/([^/]+)/grants/(?P<n_no>\\d+)/approve$', 'A', 'approve_grant', 'NoteBody', False, False),
    ('POST', '^/assets/([^/]+)/grants/(?P<n_no>\\d+)/reject$', 'A', 'reject_grant', 'ReasonBody', False, False),
    ('POST', '^/assets/([^/]+)/grants/(?P<n_no>\\d+)/revoke$', 'A', 'revoke_grant', 'ReasonBody', False, False),
]
from asavexa.oprs.service import OprsService  # noqa: E402
ops = OprsService(store, w.vault, log=log_for("Oprs"))
OPR_ROUTES = [
    ('GET', '^/options$', '', 'options', '', False, False),
    ('GET', '^/overview$', '', 'overview', '', False, False),
    ('GET', '^/analyses$', '', 'analyses', '', True, False),
    ('POST', '^/analyses$', 'P', 'add_analysis', 'AnalysisBody', False, True),
    ('GET', '^/analyses/([^/]+)$', '', 'get_analysis', '', False, False),
    ('POST', '^/analyses/([^/]+)/options$', 'P', 'add_option', 'OptionBody', False, False),
    ('POST', '^/analyses/([^/]+)/options/(?P<n_no>\\d+)/remove$', 'P', 'remove_option', 'ReasonBody', False, False),
    ('POST', '^/analyses/([^/]+)/submit$', 'P', 'submit_analysis', 'NoteBody', False, False),
    ('POST', '^/analyses/([^/]+)/withdraw$', 'P', 'withdraw_analysis', 'ReasonBody', False, False),
    ('POST', '^/analyses/([^/]+)/approve$', 'A', 'approve_analysis', 'NoteBody', False, False),
    ('POST', '^/analyses/([^/]+)/return$', 'A', 'return_analysis', 'ReasonBody', False, False),
    ('POST', '^/analyses/([^/]+)/decision$', 'A', 'record_decision', 'DecisionBody', False, False),
]
from asavexa.impact.service import ImpactService  # noqa: E402
imps = ImpactService(store, w.vault, log=log_for("Impact"))
IMP_ROUTES = [
    ('GET', '^/options$', '', 'options', '', False, False),
    ('GET', '^/overview$', '', 'overview', '', False, False),
    ('GET', '^/setting$', '', 'setting', '', False, False),
    ('PUT', '^/setting$', 'A', 'set_setting', 'SettingBody', False, False),
    ('GET', '^/indicators$', '', 'indicators', '', True, False),
    ('POST', '^/indicators$', 'P', 'add_indicator', 'IndicatorBody', False, True),
    ('GET', '^/indicators/([^/]+)$', '', 'get_indicator', '', False, False),
    ('POST', '^/indicators/([^/]+)/approve$', 'A', 'approve_indicator', 'NoteBody', False, False),
    ('POST', '^/indicators/([^/]+)/reject$', 'A', 'reject_indicator', 'ReasonBody', False, False),
    ('POST', '^/indicators/([^/]+)/close$', 'A', 'close_indicator', 'ReasonBody', False, False),
    ('POST', '^/indicators/([^/]+)/readings$', 'P', 'add_reading', 'ReadingBody', False, False),
    ('POST', '^/indicators/([^/]+)/readings/(?P<n_no>\\d+)/confirm$', 'A', 'confirm_reading', 'NoteBody', False, False),
    ('POST', '^/indicators/([^/]+)/readings/(?P<n_no>\\d+)/reject$', 'A', 'reject_reading', 'ReasonBody', False, False),
]
from asavexa.insolvency.service import InsolvencyService  # noqa: E402
isvs = InsolvencyService(store, w.vault, log=log_for("Insolvency"))
ISV_ROUTES = [
    ('GET', '^/options$', '', 'options', '', False, False),
    ('GET', '^/overview$', '', 'overview', '', False, False),
    ('GET', '^/cases$', '', 'cases', '', True, False),
    ('POST', '^/cases$', 'P', 'add_case', 'CaseBody', False, True),
    ('GET', '^/cases/([^/]+)$', '', 'get_case', '', False, False),
    ('POST', '^/cases/([^/]+)/approve$', 'A', 'approve_case', 'NoteBody', False, False),
    ('POST', '^/cases/([^/]+)/reject$', 'A', 'reject_case', 'ReasonBody', False, False),
    ('POST', '^/cases/([^/]+)/close$', 'A', 'close_case', 'ReasonBody', False, False),
    ('POST', '^/cases/([^/]+)/claims$', 'P', 'add_claim', 'ClaimBody', False, False),
    ('POST', '^/cases/([^/]+)/claims/(?P<n_no>\\d+)/admit$', 'A', 'admit_claim', 'AdmitBody', False, False),
    ('POST', '^/cases/([^/]+)/claims/(?P<n_no>\\d+)/reject$', 'A', 'reject_claim', 'ReasonBody', False, False),
    ('POST', '^/cases/([^/]+)/entries$', 'P', 'add_entry', 'EntryBody', False, False),
    ('POST', '^/cases/([^/]+)/entries/(?P<n_no>\\d+)/confirm$', 'A', 'confirm_entry', 'NoteBody', False, False),
    ('POST', '^/cases/([^/]+)/entries/(?P<n_no>\\d+)/reject$', 'A', 'reject_entry', 'ReasonBody', False, False),
    ('POST', '^/cases/([^/]+)/distribution$', 'A', 'record_distribution', 'NoteBody', False, False),
]
from asavexa.pension.service import PensionService  # noqa: E402
pens = PensionService(store, w.vault, log=log_for("Pension"))
PEN_ROUTES = [
    ('GET', '^/options$', '', 'options', '', False, False),
    ('GET', '^/overview$', '', 'overview', '', False, False),
    ('GET', '^/setting$', '', 'setting', '', False, False),
    ('PUT', '^/setting$', 'A', 'set_setting', 'SettingBody', False, False),
    ('GET', '^/schemes$', '', 'schemes', '', True, False),
    ('POST', '^/schemes$', 'P', 'add_scheme', 'SchemeBody', False, True),
    ('GET', '^/schemes/([^/]+)$', '', 'get_scheme', '', False, False),
    ('POST', '^/schemes/([^/]+)/approve$', 'A', 'approve_scheme', 'NoteBody', False, False),
    ('POST', '^/schemes/([^/]+)/reject$', 'A', 'reject_scheme', 'ReasonBody', False, False),
    ('POST', '^/schemes/([^/]+)/close$', 'A', 'close_scheme', 'ReasonBody', False, False),
    ('POST', '^/schemes/([^/]+)/contributions$', 'P', 'add_contribution', 'ContributionBody', False, False),
    ('POST', '^/schemes/([^/]+)/contributions/(?P<n_no>\\d+)/confirm$', 'A', 'confirm_contribution', 'NoteBody', False, False),
    ('POST', '^/schemes/([^/]+)/contributions/(?P<n_no>\\d+)/reject$', 'A', 'reject_contribution', 'ReasonBody', False, False),
    ('POST', '^/schemes/([^/]+)/valuations$', 'P', 'add_valuation', 'ValuationBody', False, False),
    ('POST', '^/schemes/([^/]+)/valuations/(?P<n_no>\\d+)/confirm$', 'A', 'confirm_valuation', 'NoteBody', False, False),
    ('POST', '^/schemes/([^/]+)/valuations/(?P<n_no>\\d+)/reject$', 'A', 'reject_valuation', 'ReasonBody', False, False),
    ('POST', '^/schemes/([^/]+)/obligations$', 'P', 'add_obligation', 'ObligationBody', False, False),
    ('POST', '^/schemes/([^/]+)/obligations/(?P<n_no>\\d+)/complete$', 'P', 'complete_obligation', 'CompleteBody', False, False),
    ('POST', '^/schemes/([^/]+)/obligations/(?P<n_no>\\d+)/confirm$', 'A', 'confirm_obligation', 'NoteBody', False, False),
    ('POST', '^/schemes/([^/]+)/obligations/(?P<n_no>\\d+)/reject$', 'A', 'reject_obligation', 'ReasonBody', False, False),
    ('POST', '^/schemes/([^/]+)/conflicts$', 'P', 'add_conflict', 'ConflictBody', False, False),
    ('POST', '^/schemes/([^/]+)/conflicts/(?P<n_no>\\d+)/confirm$', 'A', 'confirm_conflict', 'NoteBody', False, False),
    ('POST', '^/schemes/([^/]+)/conflicts/(?P<n_no>\\d+)/reject$', 'A', 'reject_conflict', 'ReasonBody', False, False),
]
from asavexa.franchise.service import FranchiseService  # noqa: E402
fchs = FranchiseService(store, w.vault, log=log_for("Franchise"))
FCH_ROUTES = [
    ('GET', '^/options$', '', 'options', '', False, False),
    ('GET', '^/overview$', '', 'overview', '', False, False),
    ('GET', '^/setting$', '', 'setting', '', False, False),
    ('PUT', '^/setting$', 'A', 'set_setting', 'SettingBody', False, False),
    ('GET', '^/locations$', '', 'locations', '', True, False),
    ('POST', '^/locations$', 'P', 'add_location', 'LocationBody', False, True),
    ('GET', '^/locations/([^/]+)$', '', 'get_location', '', False, False),
    ('POST', '^/locations/([^/]+)/approve$', 'A', 'approve_location', 'NoteBody', False, False),
    ('POST', '^/locations/([^/]+)/reject$', 'A', 'reject_location', 'ReasonBody', False, False),
    ('POST', '^/locations/([^/]+)/close$', 'A', 'close_location', 'ReasonBody', False, False),
    ('POST', '^/locations/([^/]+)/reports$', 'P', 'add_report', 'ReportBody', False, False),
    ('POST', '^/locations/([^/]+)/reports/(?P<n_no>\\d+)/confirm$', 'A', 'confirm_report', 'NoteBody', False, False),
    ('POST', '^/locations/([^/]+)/reports/(?P<n_no>\\d+)/reject$', 'A', 'reject_report', 'ReasonBody', False, False),
    ('POST', '^/locations/([^/]+)/payments$', 'P', 'add_payment', 'PaymentBody', False, False),
    ('POST', '^/locations/([^/]+)/payments/(?P<n_no>\\d+)/confirm$', 'A', 'confirm_payment', 'NoteBody', False, False),
    ('POST', '^/locations/([^/]+)/payments/(?P<n_no>\\d+)/reject$', 'A', 'reject_payment', 'ReasonBody', False, False),
]
from asavexa.mergers.service import MergersService  # noqa: E402
mas = MergersService(store, w.vault, log=log_for("Mergers"))
MNA_ROUTES = [
    ('GET', '^/options$', '', 'options', '', False, False),
    ('GET', '^/overview$', '', 'overview', '', False, False),
    ('GET', '^/setting$', '', 'setting', '', False, False),
    ('PUT', '^/setting$', 'A', 'set_setting', 'SettingBody', False, False),
    ('GET', '^/deals$', '', 'deals', '', True, False),
    ('POST', '^/deals$', 'P', 'add_deal', 'DealBody', False, True),
    ('GET', '^/deals/([^/]+)$', '', 'get_deal', '', False, False),
    ('POST', '^/deals/([^/]+)/approve$', 'A', 'approve_deal', 'NoteBody', False, False),
    ('POST', '^/deals/([^/]+)/reject$', 'A', 'reject_deal', 'ReasonBody', False, False),
    ('POST', '^/deals/([^/]+)/close$', 'A', 'close_deal', 'CloseBody', False, False),
    ('POST', '^/deals/([^/]+)/checklist$', 'P', 'add_checklist', 'ChecklistBody', False, False),
    ('POST', '^/deals/([^/]+)/checklist/(?P<n_no>\\d+)/provide$', 'P', 'provide_checklist', 'DoneBody', False, False),
    ('POST', '^/deals/([^/]+)/checklist/(?P<n_no>\\d+)/confirm$', 'A', 'confirm_checklist', 'NoteBody', False, False),
    ('POST', '^/deals/([^/]+)/checklist/(?P<n_no>\\d+)/reject$', 'A', 'reject_checklist', 'ReasonBody', False, False),
    ('POST', '^/deals/([^/]+)/conditions$', 'P', 'add_condition', 'ConditionBody', False, False),
    ('POST', '^/deals/([^/]+)/conditions/(?P<n_no>\\d+)/meet$', 'P', 'meet_condition', 'DoneBody', False, False),
    ('POST', '^/deals/([^/]+)/conditions/(?P<n_no>\\d+)/confirm$', 'A', 'confirm_condition', 'NoteBody', False, False),
    ('POST', '^/deals/([^/]+)/conditions/(?P<n_no>\\d+)/reject$', 'A', 'reject_condition', 'ReasonBody', False, False),
    ('POST', '^/deals/([^/]+)/adjustments$', 'P', 'add_adjustment', 'AdjustmentBody', False, False),
    ('POST', '^/deals/([^/]+)/adjustments/(?P<n_no>\\d+)/confirm$', 'A', 'confirm_adjustment', 'NoteBody', False, False),
    ('POST', '^/deals/([^/]+)/adjustments/(?P<n_no>\\d+)/reject$', 'A', 'reject_adjustment', 'ReasonBody', False, False),
]
from asavexa.approvals.service import ApprovalsService  # noqa: E402
apws = ApprovalsService(store, w.vault, log=log_for("Approvals"))
APW_ROUTES = [
    ('GET', '^/options$', '', 'options', '', False, False),
    ('GET', '^/overview$', '', 'overview', '', False, False),
    ('GET', '^/setting$', '', 'setting', '', False, False),
    ('PUT', '^/setting$', 'A', 'set_setting', 'SettingBody', False, False),
    ('GET', '^/policies$', '', 'policies', '', True, False),
    ('POST', '^/policies$', 'P', 'add_policy', 'PolicyBody', False, True),
    ('GET', '^/policies/([^/]+)$', '', 'get_policy', '', False, False),
    ('POST', '^/policies/([^/]+)/activate$', 'A', 'activate_policy', 'NoteBody', False, False),
    ('POST', '^/policies/([^/]+)/reject$', 'A', 'reject_policy', 'ReasonBody', False, False),
    ('POST', '^/policies/([^/]+)/retire$', 'A', 'retire_policy', 'ReasonBody', False, False),
    ('GET', '^/requests$', '', 'requests', '', True, False),
    ('POST', '^/requests$', 'P', 'submit_request', 'RequestBody', False, True),
    ('GET', '^/requests/([^/]+)$', '', 'get_request', '', False, False),
    ('POST', '^/requests/([^/]+)/approve$', 'A', 'approve_request', 'NoteBody', False, False),
    ('POST', '^/requests/([^/]+)/reject$', 'A', 'reject_request', 'ReasonBody', False, False),
    ('POST', '^/requests/([^/]+)/withdraw$', 'P', 'withdraw_request', 'ReasonBody', False, False),
]
_fpa_shift = {"days": 0}      # test-only: lets a journey move the Planning and KPIs clock forward so a forecast period can end
fps = FpaService(store, w.vault, is_member=_fpa_member, can_record=_fpa_can_record, log=log_for("Fpa"),
                 now=lambda: datetime.now(timezone.utc) + timedelta(days=_fpa_shift["days"]))


_NO = object()


def _ws(mod, svc, sub, m, b, org, a, qs, table, P, A_, need):
    """Generic dispatch for the Stage 33+ workspaces: the table is generated from the router itself (method, regex, guard, function, body class, takes a status filter, answers 201)."""
    for (meth, rx, guard, fname, body, wants_status, created) in table:
        if meth != m: continue
        mm = re.match(rx, sub)
        if not mm: continue
        if guard == "P": need(P)
        if guard == "A": need(A_)
        names = {i_: n_ for n_, i_ in mm.re.groupindex.items()}
        args = [int(v) if names.get(i_, "").startswith("n_") else v for i_, v in enumerate(mm.groups(), start=1)]
        if body: args.append(getattr(mod, body)(**b))
        if wants_status: args.append(qs.get("status"))
        args += [org] + ([a] if m != "GET" else []) + [svc]
        out = getattr(mod, fname)(*args)
        return (201, out) if created else out
    return _NO


# ---- Health Centre Administration: the REAL router functions and the REAL service. The route table is read from the router's own decorators, so a route added there is served here.
import inspect  # noqa: E402
from asavexa.health.service import HealthService  # noqa: E402
hcr = importlib.import_module("asavexa.api.routers.health")


def _hc_can(org, actor, perm):
    r_ = w.identity.get_role(actor, org)
    return r_ is not None and perm in ROLE_PERMISSIONS[r_]


hcs = HealthService(store, w.vault, w.accounting, log=log_for("HealthCentre"), can=_hc_can)
_HC_GUARDS = {"_prepare": [HEALTH_PREPARE], "_approve": [HEALTH_APPROVE], "_admin": [HEALTH_ADMIN], "_claims": [HEALTH_CLAIMS], "_staff": [HEALTH_STAFFING],
              "_claims_prepare": [HEALTH_CLAIMS, HEALTH_PREPARE], "_claims_approve": [HEALTH_CLAIMS, HEALTH_APPROVE], "_staff_approve": [HEALTH_STAFFING, HEALTH_APPROVE]}
HC_TABLE = []
_src = open(hcr.__file__).read()
for _m in re.finditer(r'@router\.(get|post|put)\("([^"]+)"(?:, status_code=(\d+))?(?:, dependencies=(\w+))?\)\s*\ndef (\w+)\(', _src):
    _meth, _path, _code, _dep, _fn = _m.groups()
    HC_TABLE.append((_meth.upper(), re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", _path) + "$"), _HC_GUARDS.get(_dep, []), _fn, int(_code) if _code else 200))


def _hc(sub, m, b, org, a, qs, need):
    for (meth, rx, guards, fname, code) in HC_TABLE:
        if meth != m: continue
        mm = rx.match(sub)
        if not mm: continue
        need(HEALTH_READ)
        for g_ in guards: need(g_)
        fn = getattr(hcr, fname); kw = {}
        for pn in inspect.signature(fn).parameters:
            if pn in mm.groupdict(): kw[pn] = mm.group(pn)
            elif pn == "body": kw[pn] = b
            elif pn == "org": kw[pn] = org
            elif pn == "a": kw[pn] = a
            elif pn == "s": kw[pn] = hcs
            else: kw[pn] = qs.get(pn)
        out = fn(**kw)
        if hasattr(out, "content") and hasattr(out, "media_type"): return (200, out.content if isinstance(out.content, bytes) else str(out.content).encode())
        return (code, out) if code != 200 else out
    return _NO


# ---- Public Finance: the REAL router functions and the REAL service. The route table is read from the router's own decorators.
from asavexa.pubfin.service import PubFinService  # noqa: E402
pfr = importlib.import_module("asavexa.api.routers.pubfin")
pfs = PubFinService(store, w.accounting, w.vault, log=log_for("PublicFinance"))
PF_TABLE = []
_pfsrc = open(pfr.__file__).read()
for _m in re.finditer(r'@router\.(get|post|put|delete)\("([^"]+)"(?:, status_code=(\d+))?(?:, dependencies=\[(\w+)\])?\)\s*\ndef (\w+)\(', _pfsrc):
    _meth, _path, _code, _dep, _fn = _m.groups()
    PF_TABLE.append((_meth.upper(), re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", _path) + "$"), {"_prepare": PUBFIN_PREPARE, "_approve": PUBFIN_APPROVE}.get(_dep), _fn, int(_code) if _code else 200))


def _pf(sub, m, b, org, a, qs, need):
    for (meth, rx, guard, fname, code) in PF_TABLE:
        if meth != m: continue
        mm = rx.match(sub)
        if not mm: continue
        need(REPORTING_READ)
        if guard: need(guard)
        fn = getattr(pfr, fname); kw = {}
        for pn, par in inspect.signature(fn).parameters.items():
            if pn in mm.groupdict(): kw[pn] = mm.group(pn)
            elif pn == "body": kw[pn] = par.annotation(**b)
            elif pn == "org": kw[pn] = org
            elif pn == "actor": kw[pn] = a
            elif pn == "svc": kw[pn] = pfs
            else: kw[pn] = qs.get(pn)
        out = fn(**kw)
        if hasattr(out, "content") and hasattr(out, "media_type"): return (200, out.content if isinstance(out.content, bytes) else str(out.content).encode())
        return (code, out) if code != 200 else out
    return _NO


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
        if path == "/accounts" and m == "GET": need(REPORTING_READ); return w.accounting.accounts.list_for_org(org)
        if path.startswith("/reports/") and m == "GET":
            # The REAL reporting router functions and service (test-only wiring; the reconciliation summary needs a service built with reconciliation).
            need(REPORTING_READ)
            rr = importlib.import_module("asavexa.api.routers.reporting")
            RSV = ReportingService(accounting=w.accounting, audit=w.audit, reconciliation=w.recon, evidence=w.vault)
            if path == "/reports/trial-balance": return rr.get_trial_balance(qs["period_id"], org, a, w.reporting)
            if path == "/reports/income-statement": return rr.get_income_statement(qs["period_id"], org, a, w.reporting)
            if path == "/reports/balance-sheet": return rr.get_balance_sheet(qs["period_id"], org, a, w.reporting)
            if path == "/reports/trace": return rr.trace_line(qs["account_id"], qs.get("period_id"), org, w.reporting)
            if path == "/reports/evidence-completeness": return rr.get_evidence_completeness(qs["account_id"], qs.get("period_id"), org, RSV)
            if path == "/reports/reconciliation-summary": return rr.get_reconciliation_summary(qs["bank_account_id"], org, RSV)
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
        if path.startswith("/itaudit"):
            need(AUDIT_READ); sub = path[len("/itaudit"):]; P, A_ = ITAUDIT_PREPARE, ITAUDIT_APPROVE
            if sub == "/options": return iar.options(org, ias)
            if sub == "/overview": return iar.overview(org, ias)
            if sub == "/policy" and m == "GET": return iar.policy(org, ias)
            if sub == "/policy" and m == "PUT": need(A_); return iar.set_policy(iar.PolicyBody(**b), org, a, ias)
            if sub == "/changes" and m == "GET": return iar.changes(qs.get("system"), None if qs.get("flagged") is None else qs.get("flagged") == "true", qs.get("status"), org, ias)
            if sub == "/changes" and m == "POST": need(P); return (201, iar.record_change(iar.ChangeBody(**b), org, a, ias))
            mm = re.match(r"/changes/([^/]+)$", sub)
            if mm: return iar.get_change(mm.group(1), org, ias)
            mm = re.match(r"/changes/([^/]+)/void$", sub)
            if mm: need(A_); return iar.void_change(mm.group(1), iar.ReasonBody(**b), org, a, ias)
            if sub == "/controls" and m == "GET": return iar.controls(qs.get("system"), org, ias)
            if sub == "/controls" and m == "POST": need(P); return (201, iar.define_control(iar.ControlBody(**b), org, a, ias))
            mm = re.match(r"/controls/([^/]+)$", sub)
            if mm: return iar.get_control(mm.group(1), org, ias)
            mm = re.match(r"/controls/([^/]+)/retire$", sub)
            if mm: need(A_); return iar.retire_control(mm.group(1), iar.ReasonBody(**b), org, a, ias)
            if sub == "/tests" and m == "GET": return iar.tests(qs.get("kind"), qs.get("status"), org, ias)
            if sub == "/tests/change" and m == "POST": need(P); return (201, iar.plan_change_test(iar.ChangeTestBody(**b), org, a, ias))
            if sub == "/tests/control" and m == "POST": need(P); return (201, iar.plan_control_test(iar.ControlTestBody(**b), org, a, ias))
            mm = re.match(r"/tests/([^/]+)$", sub)
            if mm: return iar.get_test(mm.group(1), org, ias)
            mm = re.match(r"/tests/([^/]+)/items/([^/]+)$", sub)
            if mm: need(P); return iar.conclude_item(mm.group(1), mm.group(2), iar.ItemBody(**b), org, a, ias)
            mm = re.match(r"/tests/([^/]+)/cases$", sub)
            if mm: need(P); return (201, iar.add_case(mm.group(1), iar.CaseBody(**b), org, a, ias))
            mm = re.match(r"/tests/([^/]+)/submit$", sub)
            if mm: need(P); return iar.submit_test(mm.group(1), org, a, ias)
            mm = re.match(r"/tests/([^/]+)/withdraw$", sub)
            if mm: need(P); return iar.withdraw_test(mm.group(1), iar.ReasonBody(**b), org, a, ias)
            mm = re.match(r"/tests/([^/]+)/approve$", sub)
            if mm: need(A_); return iar.approve_test(mm.group(1), iar.NoteBody(**b), org, a, ias)
            mm = re.match(r"/tests/([^/]+)/reject$", sub)
            if mm: need(A_); return iar.reject_test(mm.group(1), iar.ReasonBody(**b), org, a, ias)
        if path.startswith("/resilience"):
            need(AUDIT_READ); sub = path[len("/resilience"):]; P, A_ = RESIL_PREPARE, RESIL_APPROVE
            if sub == "/options": return rsr.options(org, rss)
            if sub == "/overview": return rsr.overview(org, rss)
            if sub == "/policy" and m == "GET": return rsr.policy(org, rss)
            if sub == "/policy" and m == "PUT": need(A_); return rsr.set_policy(rsr.PolicyBody(**b), org, a, rss)
            if sub == "/kris" and m == "GET": return rsr.kris(qs.get("status"), org, rss)
            if sub == "/kris" and m == "POST": need(P); return (201, rsr.propose_kri(rsr.KriBody(**b), org, a, rss))
            mm = re.match(r"/kris/([^/]+)$", sub)
            if mm: return rsr.get_kri(mm.group(1), org, rss)
            mm = re.match(r"/kris/([^/]+)/approve$", sub)
            if mm: need(A_); return rsr.approve_kri(mm.group(1), rsr.NoteBody(**b), org, a, rss)
            mm = re.match(r"/kris/([^/]+)/(reject|retire)$", sub)
            if mm: need(A_); kid, act = mm.groups(); return (rsr.reject_kri if act == "reject" else rsr.retire_kri)(kid, rsr.ReasonBody(**b), org, a, rss)
            mm = re.match(r"/kris/([^/]+)/readings$", sub)
            if mm: need(P); return (201, rsr.record_reading(mm.group(1), rsr.ReadingBody(**b), org, a, rss))
            mm = re.match(r"/kris/([^/]+)/readings/([^/]+)/confirm$", sub)
            if mm: need(A_); return rsr.confirm_reading(mm.group(1), mm.group(2), org, a, rss)
            mm = re.match(r"/kris/([^/]+)/readings/([^/]+)/reject$", sub)
            if mm: need(A_); return rsr.reject_reading(mm.group(1), mm.group(2), rsr.ReasonBody(**b), org, a, rss)
            if sub == "/losses" and m == "GET": return rsr.losses(qs.get("status"), qs.get("kind"), org, rss)
            if sub == "/losses" and m == "POST": need(P); return (201, rsr.record_loss(rsr.LossBody(**b), org, a, rss))
            mm = re.match(r"/losses/([^/]+)$", sub)
            if mm: return rsr.get_loss(mm.group(1), org, rss)
            mm = re.match(r"/losses/([^/]+)/review$", sub)
            if mm: need(A_); return rsr.review_loss(mm.group(1), rsr.ReviewBody(**b), org, a, rss)
            mm = re.match(r"/losses/([^/]+)/void$", sub)
            if mm: need(A_); return rsr.void_loss(mm.group(1), rsr.ReasonBody(**b), org, a, rss)
            if sub == "/processes" and m == "GET": return rsr.processes(qs.get("status"), org, rss)
            if sub == "/processes" and m == "POST": need(P); return (201, rsr.propose_process(rsr.ProcessBody(**b), org, a, rss))
            mm = re.match(r"/processes/([^/]+)$", sub)
            if mm: return rsr.get_process(mm.group(1), org, rss)
            mm = re.match(r"/processes/([^/]+)/approve$", sub)
            if mm: need(A_); return rsr.approve_process(mm.group(1), rsr.NoteBody(**b), org, a, rss)
            mm = re.match(r"/processes/([^/]+)/(reject|retire)$", sub)
            if mm: need(A_); pid, act = mm.groups(); return (rsr.reject_process if act == "reject" else rsr.retire_process)(pid, rsr.ReasonBody(**b), org, a, rss)
            if sub == "/drills" and m == "GET": return rsr.drills(qs.get("process_id"), qs.get("status"), org, rss)
            if sub == "/drills" and m == "POST": need(P); return (201, rsr.record_drill(rsr.DrillBody(**b), org, a, rss))
            mm = re.match(r"/drills/([^/]+)$", sub)
            if mm: return rsr.get_drill(mm.group(1), org, rss)
            mm = re.match(r"/drills/([^/]+)/approve$", sub)
            if mm: need(A_); return rsr.approve_drill(mm.group(1), rsr.NoteBody(**b), org, a, rss)
            mm = re.match(r"/drills/([^/]+)/reject$", sub)
            if mm: need(A_); return rsr.reject_drill(mm.group(1), rsr.ReasonBody(**b), org, a, rss)
        if path.startswith("/aigov"):
            need(AUDIT_READ); sub = path[len("/aigov"):]; P, A_ = AIG_PREPARE, AIG_APPROVE
            if sub == "/options": return gvr.options(org, gvs)
            if sub == "/overview": return gvr.overview(org, gvs)
            if sub == "/policy" and m == "GET": return gvr.policy(org, gvs)
            if sub == "/policy" and m == "PUT": need(A_); return gvr.set_policy(gvr.PolicyBody(**b), org, a, gvs)
            if sub == "/systems" and m == "GET": return gvr.systems(qs.get("status"), qs.get("tier"), org, gvs)
            if sub == "/systems" and m == "POST": need(P); return (201, gvr.propose_system(gvr.SystemBody(**b), org, a, gvs))
            mm = re.match(r"/systems/([^/]+)$", sub)
            if mm and m == "GET": return gvr.get_system(mm.group(1), org, gvs)
            mm = re.match(r"/systems/([^/]+)/approve$", sub)
            if mm: need(A_); return gvr.approve_system(mm.group(1), gvr.NoteBody(**b), org, a, gvs)
            mm = re.match(r"/systems/([^/]+)/review$", sub)
            if mm: need(A_); return gvr.review_system(mm.group(1), gvr.NoteBody(**b), org, a, gvs)
            mm = re.match(r"/systems/([^/]+)/(reject|retire)$", sub)
            if mm: need(A_); sid, act = mm.groups(); return (gvr.reject_system if act == "reject" else gvr.retire_system)(sid, gvr.ReasonBody(**b), org, a, gvs)
            if sub == "/changes" and m == "GET": return gvr.changes(qs.get("system_id"), qs.get("status"), org, gvs)
            if sub == "/changes" and m == "POST": need(P); return (201, gvr.record_change(gvr.ChangeBody(**b), org, a, gvs))
            mm = re.match(r"/changes/([^/]+)$", sub)
            if mm and m == "GET": return gvr.get_change(mm.group(1), org, gvs)
            mm = re.match(r"/changes/([^/]+)/approve$", sub)
            if mm: need(A_); return gvr.approve_change(mm.group(1), gvr.NoteBody(**b), org, a, gvs)
            mm = re.match(r"/changes/([^/]+)/reject$", sub)
            if mm: need(A_); return gvr.reject_change(mm.group(1), gvr.ReasonBody(**b), org, a, gvs)
            if sub == "/incidents" and m == "GET": return gvr.incidents(qs.get("system_id"), qs.get("status"), org, gvs)
            if sub == "/incidents" and m == "POST": need(P); return (201, gvr.record_incident(gvr.IncidentBody(**b), org, a, gvs))
            mm = re.match(r"/incidents/([^/]+)$", sub)
            if mm and m == "GET": return gvr.get_incident(mm.group(1), org, gvs)
            mm = re.match(r"/incidents/([^/]+)/review$", sub)
            if mm: need(A_); return gvr.review_incident(mm.group(1), gvr.ReviewBody(**b), org, a, gvs)
            mm = re.match(r"/incidents/([^/]+)/void$", sub)
            if mm: need(A_); return gvr.void_incident(mm.group(1), gvr.ReasonBody(**b), org, a, gvs)
        if path.startswith("/quality"):
            need(AUDIT_READ); sub = path[len("/quality"):]; P, A_ = QUAL_PREPARE, QUAL_APPROVE
            if sub == "/options": return qlr.options(org, qls)
            if sub == "/overview": return qlr.overview(org, qls)
            if sub == "/policy" and m == "GET": return qlr.policy(org, qls)
            if sub == "/policy" and m == "PUT": need(A_); return qlr.set_policy(qlr.PolicyBody(**b), org, a, qls)
            if sub == "/ncs" and m == "GET": return qlr.ncs(qs.get("status"), qs.get("severity"), org, qls)
            if sub == "/ncs" and m == "POST": need(P); return (201, qlr.raise_nc(qlr.NcBody(**b), org, a, qls))
            mm = re.match(r"/ncs/([^/]+)$", sub)
            if mm and m == "GET": return qlr.get_nc(mm.group(1), org, qls)
            mm = re.match(r"/ncs/([^/]+)/analyse$", sub)
            if mm: need(P); return qlr.analyse_nc(mm.group(1), qlr.AnalyseBody(**b), org, a, qls)
            mm = re.match(r"/ncs/([^/]+)/close$", sub)
            if mm: need(A_); return qlr.close_nc(mm.group(1), qlr.CloseBody(**b), org, a, qls)
            mm = re.match(r"/ncs/([^/]+)/void$", sub)
            if mm: need(A_); return qlr.void_nc(mm.group(1), qlr.ReasonBody(**b), org, a, qls)
            if sub == "/actions" and m == "GET": return qlr.actions(qs.get("nc_id"), qs.get("status"), org, qls)
            if sub == "/actions" and m == "POST": need(P); return (201, qlr.add_action(qlr.ActionBody(**b), org, a, qls))
            mm = re.match(r"/actions/([^/]+)$", sub)
            if mm and m == "GET": return qlr.get_action(mm.group(1), org, qls)
            mm = re.match(r"/actions/([^/]+)/complete$", sub)
            if mm: need(P); return qlr.complete_action(mm.group(1), qlr.CompleteBody(**b), org, a, qls)
            mm = re.match(r"/actions/([^/]+)/verify$", sub)
            if mm: need(A_); return qlr.verify_action(mm.group(1), qlr.VerifyBody(**b), org, a, qls)
            mm = re.match(r"/actions/([^/]+)/cancel$", sub)
            if mm: need(A_); return qlr.cancel_action(mm.group(1), qlr.ReasonBody(**b), org, a, qls)
        if path.startswith("/secretarial"):
            need(AUDIT_READ); sub = path[len("/secretarial"):]; P, A_ = SEC_PREPARE, SEC_APPROVE
            if sub == "/options": return scr.options(org, scs)
            if sub == "/overview": return scr.overview(org, scs)
            if sub == "/policy" and m == "GET": return scr.policy(org, scs)
            if sub == "/policy" and m == "PUT": need(A_); return scr.set_policy(scr.PolicyBody(**b), org, a, scs)
            if sub == "/meetings" and m == "GET": return scr.meetings(qs.get("status"), org, scs)
            if sub == "/meetings" and m == "POST": need(P); return (201, scr.schedule_meeting(scr.MeetingBody(**b), org, a, scs))
            mm = re.match(r"/meetings/([^/]+)$", sub)
            if mm and m == "GET": return scr.get_meeting(mm.group(1), org, scs)
            mm = re.match(r"/meetings/([^/]+)/minutes$", sub)
            if mm: need(P); return scr.record_minutes(mm.group(1), scr.MinutesBody(**b), org, a, scs)
            mm = re.match(r"/meetings/([^/]+)/approve$", sub)
            if mm: need(A_); return scr.approve_minutes(mm.group(1), scr.NoteBody(**b), org, a, scs)
            mm = re.match(r"/meetings/([^/]+)/cancel$", sub)
            if mm: need(A_); return scr.cancel_meeting(mm.group(1), scr.ReasonBody(**b), org, a, scs)
            if sub == "/resolutions" and m == "GET": return scr.resolutions(qs.get("meeting_id"), qs.get("status"), org, scs)
            if sub == "/resolutions" and m == "POST": need(P); return (201, scr.propose_resolution(scr.ResolutionBody(**b), org, a, scs))
            mm = re.match(r"/resolutions/([^/]+)$", sub)
            if mm and m == "GET": return scr.get_resolution(mm.group(1), org, scs)
            mm = re.match(r"/resolutions/([^/]+)/decide$", sub)
            if mm: need(A_); return scr.decide_resolution(mm.group(1), scr.DecideBody(**b), org, a, scs)
            mm = re.match(r"/resolutions/([^/]+)/withdraw$", sub)
            if mm: need(A_); return scr.withdraw_resolution(mm.group(1), scr.ReasonBody(**b), org, a, scs)
            if sub == "/filings" and m == "GET": return scr.filings(qs.get("status"), org, scs)
            if sub == "/filings" and m == "POST": need(P); return (201, scr.add_filing(scr.FilingBody(**b), org, a, scs))
            mm = re.match(r"/filings/([^/]+)$", sub)
            if mm and m == "GET": return scr.get_filing(mm.group(1), org, scs)
            mm = re.match(r"/filings/([^/]+)/file$", sub)
            if mm: need(P); return scr.file_filing(mm.group(1), scr.FiledBody(**b), org, a, scs)
            mm = re.match(r"/filings/([^/]+)/confirm$", sub)
            if mm: need(A_); return scr.confirm_filing(mm.group(1), scr.NoteBody(**b), org, a, scs)
            mm = re.match(r"/filings/([^/]+)/withdraw$", sub)
            if mm: need(A_); return scr.withdraw_filing(mm.group(1), scr.ReasonBody(**b), org, a, scs)
        if path.startswith("/fixedassets"):
            need(AUDIT_READ); sub = path[len("/fixedassets"):]; P, A_ = FIX_PREPARE, FIX_APPROVE
            if sub == "/options": return fxr.options(org, fxs)
            if sub == "/overview": return fxr.overview(org, fxs)
            if sub == "/policy" and m == "GET": return fxr.policy(org, fxs)
            if sub == "/policy" and m == "PUT": need(A_); return fxr.set_policy(fxr.PolicyBody(**b), org, a, fxs)
            if sub == "/assets" and m == "GET": return fxr.assets(qs.get("status"), qs.get("category"), org, fxs)
            if sub == "/assets" and m == "POST": need(P); return (201, fxr.propose_asset(fxr.AssetBody(**b), org, a, fxs))
            mm = re.match(r"/assets/([^/]+)$", sub)
            if mm and m == "GET": return fxr.get_asset(mm.group(1), org, fxs)
            mm = re.match(r"/assets/([^/]+)/schedule$", sub)
            if mm: return fxr.schedule(mm.group(1), int(qs.get("months") or 12), org, fxs)
            mm = re.match(r"/assets/([^/]+)/approve$", sub)
            if mm: need(A_); return fxr.approve_asset(mm.group(1), fxr.NoteBody(**b), org, a, fxs)
            mm = re.match(r"/assets/([^/]+)/reject$", sub)
            if mm: need(A_); return fxr.reject_asset(mm.group(1), fxr.ReasonBody(**b), org, a, fxs)
            mm = re.match(r"/assets/([^/]+)/disposal$", sub)
            if mm: need(P); return fxr.propose_disposal(mm.group(1), fxr.DisposalBody(**b), org, a, fxs)
            mm = re.match(r"/assets/([^/]+)/disposal/approve$", sub)
            if mm: need(A_); return fxr.approve_disposal(mm.group(1), fxr.NoteBody(**b), org, a, fxs)
            mm = re.match(r"/assets/([^/]+)/disposal/reject$", sub)
            if mm: need(A_); return fxr.reject_disposal(mm.group(1), fxr.ReasonBody(**b), org, a, fxs)
            mm = re.match(r"/assets/([^/]+)/counts$", sub)
            if mm: need(P); return fxr.record_count(mm.group(1), fxr.CountBody(**b), org, a, fxs)
            mm = re.match(r"/assets/([^/]+)/counts/(\d+)/review$", sub)
            if mm: need(A_); return fxr.review_count(mm.group(1), int(mm.group(2)), fxr.NoteBody(**b), org, a, fxs)
        if path.startswith("/inventory"):
            need(AUDIT_READ); sub = path[len("/inventory"):]; P, A_ = INV_PREPARE, INV_APPROVE
            if sub == "/options": return ivr.options(org, ivs)
            if sub == "/overview": return ivr.overview(org, ivs)
            if sub == "/policy" and m == "GET": return ivr.policy(org, ivs)
            if sub == "/policy" and m == "PUT": need(A_); return ivr.set_policy(ivr.PolicyBody(**b), org, a, ivs)
            if sub == "/items" and m == "GET": return ivr.items(qs.get("status"), org, ivs)
            if sub == "/items" and m == "POST": need(P); return (201, ivr.add_item(ivr.ItemBody(**b), org, a, ivs))
            mm = re.match(r"/items/([^/]+)$", sub)
            if mm and m == "GET": return ivr.get_item(mm.group(1), org, ivs)
            mm = re.match(r"/items/([^/]+)/discontinue$", sub)
            if mm: need(A_); return ivr.discontinue_item(mm.group(1), ivr.ReasonBody(**b), org, a, ivs)
            mm = re.match(r"/items/([^/]+)/receive$", sub)
            if mm: need(P); return ivr.receive(mm.group(1), ivr.MoveBody(**b), org, a, ivs)
            mm = re.match(r"/items/([^/]+)/issue$", sub)
            if mm: need(P); return ivr.issue(mm.group(1), ivr.MoveBody(**b), org, a, ivs)
            mm = re.match(r"/items/([^/]+)/adjustments$", sub)
            if mm: need(P); return ivr.propose_adjustment(mm.group(1), ivr.AdjustBody(**b), org, a, ivs)
            mm = re.match(r"/items/([^/]+)/adjustments/(\d+)/approve$", sub)
            if mm: need(A_); return ivr.approve_adjustment(mm.group(1), int(mm.group(2)), ivr.NoteBody(**b), org, a, ivs)
            mm = re.match(r"/items/([^/]+)/adjustments/(\d+)/reject$", sub)
            if mm: need(A_); return ivr.reject_adjustment(mm.group(1), int(mm.group(2)), ivr.ReasonBody(**b), org, a, ivs)
        if path.startswith("/investments"):
            need(AUDIT_READ); sub = path[len("/investments"):]; P, A_ = INVEST_PREPARE, INVEST_APPROVE
            if sub == "/options": return imr.options(org, ims)
            if sub == "/overview": return imr.overview(org, ims)
            if sub == "/policy" and m == "GET": return imr.policy(org, ims)
            if sub == "/policy" and m == "PUT": need(A_); return imr.set_policy(imr.PolicyBody(**b), org, a, ims)
            if sub == "/holdings" and m == "GET": return imr.holdings(qs.get("status"), org, ims)
            if sub == "/holdings" and m == "POST": need(P); return (201, imr.add_holding(imr.HoldingBody(**b), org, a, ims))
            mm = re.match(r"/holdings/([^/]+)$", sub)
            if mm and m == "GET": return imr.get_holding(mm.group(1), org, ims)
            mm = re.match(r"/holdings/([^/]+)/close$", sub)
            if mm: need(A_); return imr.close_holding(mm.group(1), imr.ReasonBody(**b), org, a, ims)
            mm = re.match(r"/holdings/([^/]+)/buy$", sub)
            if mm: need(P); return imr.buy(mm.group(1), imr.TradeBody(**b), org, a, ims)
            mm = re.match(r"/holdings/([^/]+)/sells$", sub)
            if mm: need(P); return imr.propose_sell(mm.group(1), imr.TradeBody(**b), org, a, ims)
            mm = re.match(r"/holdings/([^/]+)/sells/(\d+)/approve$", sub)
            if mm: need(A_); return imr.approve_sell(mm.group(1), int(mm.group(2)), imr.NoteBody(**b), org, a, ims)
            mm = re.match(r"/holdings/([^/]+)/sells/(\d+)/reject$", sub)
            if mm: need(A_); return imr.reject_sell(mm.group(1), int(mm.group(2)), imr.ReasonBody(**b), org, a, ims)
            mm = re.match(r"/holdings/([^/]+)/marks$", sub)
            if mm: need(P); return imr.record_mark(mm.group(1), imr.MarkBody(**b), org, a, ims)
        if path.startswith("/valuation"):
            need(AUDIT_READ); sub = path[len("/valuation"):]; P, A_ = VAL_PREPARE, VAL_APPROVE
            if sub == "/options": return vlr.options(org, vls)
            if sub == "/overview": return vlr.overview(org, vls)
            if sub == "/policy" and m == "GET": return vlr.policy(org, vls)
            if sub == "/policy" and m == "PUT": need(A_); return vlr.set_policy(vlr.PolicyBody(**b), org, a, vls)
            if sub == "/cases" and m == "GET": return vlr.cases(qs.get("status"), org, vls)
            if sub == "/cases" and m == "POST": need(P); return (201, vlr.create_case(vlr.CaseBody(**b), org, a, vls))
            mm = re.match(r"/cases/([^/]+)$", sub)
            if mm and m == "GET": return vlr.get_case(mm.group(1), org, vls)
            mm = re.match(r"/cases/([^/]+)/methods/(\d+)/sensitivity$", sub)
            if mm and m == "GET": return vlr.sensitivity(mm.group(1), int(mm.group(2)), org, vls)
            mm = re.match(r"/cases/([^/]+)/methods$", sub)
            if mm and m == "POST": need(P); return vlr.add_method(mm.group(1), vlr.MethodBody(**b), org, a, vls)
            mm = re.match(r"/cases/([^/]+)/methods/(\d+)/remove$", sub)
            if mm: need(P); return vlr.remove_method(mm.group(1), int(mm.group(2)), vlr.ReasonBody(**b), org, a, vls)
            mm = re.match(r"/cases/([^/]+)/submit$", sub)
            if mm: need(P); return vlr.submit(mm.group(1), vlr.SubmitBody(**b), org, a, vls)
            mm = re.match(r"/cases/([^/]+)/withdraw$", sub)
            if mm: need(P); return vlr.withdraw(mm.group(1), vlr.ReasonBody(**b), org, a, vls)
            mm = re.match(r"/cases/([^/]+)/approve$", sub)
            if mm: need(A_); return vlr.approve(mm.group(1), vlr.NoteBody(**b), org, a, vls)
            mm = re.match(r"/cases/([^/]+)/return$", sub)
            if mm: need(A_); return vlr.return_case(mm.group(1), vlr.ReasonBody(**b), org, a, vls)
        if path.startswith("/insurance"):
            need(AUDIT_READ); sub = path[len("/insurance"):]; P, A_ = INS_PREPARE, INS_APPROVE
            if sub == "/options": return icr.options(org, ics)
            if sub == "/overview": return icr.overview(org, ics)
            if sub == "/setting" and m == "GET": return icr.setting(org, ics)
            if sub == "/setting" and m == "PUT": need(A_); return icr.set_setting(icr.SettingBody(**b), org, a, ics)
            if sub == "/policies" and m == "GET": return icr.policies(qs.get("status"), org, ics)
            if sub == "/policies" and m == "POST": need(P); return (201, icr.add_policy(icr.PolicyBody(**b), org, a, ics))
            if sub == "/claims" and m == "GET": return icr.claims(qs.get("status"), org, ics)
            mm = re.match(r"/policies/([^/]+)$", sub)
            if mm and m == "GET": return icr.get_policy(mm.group(1), org, ics)
            mm = re.match(r"/policies/([^/]+)/cancel$", sub)
            if mm: need(A_); return icr.cancel_policy(mm.group(1), icr.ReasonBody(**b), org, a, ics)
            mm = re.match(r"/policies/([^/]+)/claims$", sub)
            if mm: need(P); return (201, icr.add_claim(mm.group(1), icr.ClaimBody(**b), org, a, ics))
            mm = re.match(r"/claims/([^/]+)$", sub)
            if mm and m == "GET": return icr.get_claim(mm.group(1), org, ics)
            mm = re.match(r"/claims/([^/]+)/proposals$", sub)
            if mm: need(P); return icr.propose_outcome(mm.group(1), icr.OutcomeBody(**b), org, a, ics)
            mm = re.match(r"/claims/([^/]+)/proposals/(\d+)/approve$", sub)
            if mm: need(A_); return icr.approve_outcome(mm.group(1), int(mm.group(2)), icr.NoteBody(**b), org, a, ics)
            mm = re.match(r"/claims/([^/]+)/proposals/(\d+)/reject$", sub)
            if mm: need(A_); return icr.reject_outcome(mm.group(1), int(mm.group(2)), icr.ReasonBody(**b), org, a, ics)
            mm = re.match(r"/claims/([^/]+)/receipts$", sub)
            if mm: need(P); return icr.record_receipt(mm.group(1), icr.ReceiptBody(**b), org, a, ics)
        if path.startswith("/esg"):
            need(AUDIT_READ); sub = path[len("/esg"):]; P, A_ = ESG_PREPARE, ESG_APPROVE
            if sub == "/options": return esr.options(org, ess)
            if sub == "/overview": return esr.overview(org, ess)
            if sub == "/setting" and m == "GET": return esr.setting(org, ess)
            if sub == "/setting" and m == "PUT": need(A_); return esr.set_setting(esr.SettingBody(**b), org, a, ess)
            if sub == "/entries" and m == "GET": return esr.entries(qs.get("status"), org, ess)
            if sub == "/entries" and m == "POST": need(P); return (201, esr.add_entry(esr.EntryBody(**b), org, a, ess))
            if sub == "/targets" and m == "GET": return esr.targets(qs.get("status"), org, ess)
            if sub == "/targets" and m == "POST": need(P); return (201, esr.add_target(esr.TargetBody(**b), org, a, ess))
            mm = re.match(r"/entries/([^/]+)$", sub)
            if mm and m == "GET": return esr.get_entry(mm.group(1), org, ess)
            mm = re.match(r"/entries/([^/]+)/verify$", sub)
            if mm: need(A_); return esr.verify_entry(mm.group(1), esr.NoteBody(**b), org, a, ess)
            mm = re.match(r"/entries/([^/]+)/reject$", sub)
            if mm: need(A_); return esr.reject_entry(mm.group(1), esr.ReasonBody(**b), org, a, ess)
            mm = re.match(r"/targets/([^/]+)/approve$", sub)
            if mm: need(A_); return esr.approve_target(mm.group(1), esr.NoteBody(**b), org, a, ess)
            mm = re.match(r"/targets/([^/]+)/reject$", sub)
            if mm: need(A_); return esr.reject_target(mm.group(1), esr.ReasonBody(**b), org, a, ess)
        if path.startswith("/payroll"):
            need(AUDIT_READ); sub = path[len("/payroll"):]; P, A_ = PAY_PREPARE, PAY_APPROVE
            if sub == "/options": return pwr.options(org, pws)
            if sub == "/overview": return pwr.overview(org, pws)
            if sub == "/setting" and m == "GET": return pwr.setting(org, pws)
            if sub == "/setting" and m == "PUT": need(A_); return pwr.set_setting(pwr.SettingBody(**b), org, a, pws)
            if sub == "/runs" and m == "GET": return pwr.runs(qs.get("status"), org, pws)
            if sub == "/runs" and m == "POST": need(P); return (201, pwr.create_run(pwr.RunBody(**b), org, a, pws))
            mm = re.match(r"/runs/([^/]+)$", sub)
            if mm and m == "GET": return pwr.get_run(mm.group(1), org, pws)
            mm = re.match(r"/runs/([^/]+)/lines$", sub)
            if mm and m == "POST": need(P); return pwr.add_line(mm.group(1), pwr.LineBody(**b), org, a, pws)
            mm = re.match(r"/runs/([^/]+)/lines/(\d+)/remove$", sub)
            if mm: need(P); return pwr.remove_line(mm.group(1), int(mm.group(2)), pwr.ReasonBody(**b), org, a, pws)
            mm = re.match(r"/runs/([^/]+)/submit$", sub)
            if mm: need(P); return pwr.submit(mm.group(1), pwr.NoteBody(**b), org, a, pws)
            mm = re.match(r"/runs/([^/]+)/withdraw$", sub)
            if mm: need(P); return pwr.withdraw(mm.group(1), pwr.ReasonBody(**b), org, a, pws)
            mm = re.match(r"/runs/([^/]+)/approve$", sub)
            if mm: need(A_); return pwr.approve(mm.group(1), pwr.NoteBody(**b), org, a, pws)
            mm = re.match(r"/runs/([^/]+)/return$", sub)
            if mm: need(A_); return pwr.return_run(mm.group(1), pwr.ReasonBody(**b), org, a, pws)
        if path.startswith("/projects"):
            need(AUDIT_READ); sub = path[len("/projects"):]; P, A_ = PROJ_PREPARE, PROJ_APPROVE
            if sub == "/options": return pjr.options(org, pjs)
            if sub == "/overview": return pjr.overview(org, pjs)
            if sub == "/setting" and m == "GET": return pjr.setting(org, pjs)
            if sub == "/setting" and m == "PUT": need(A_); return pjr.set_setting(pjr.SettingBody(**b), org, a, pjs)
            if sub == "/projects" and m == "GET": return pjr.projects(qs.get("status"), org, pjs)
            if sub == "/projects" and m == "POST": need(P); return (201, pjr.create_project(pjr.ProjectBody(**b), org, a, pjs))
            mm = re.match(r"/projects/([^/]+)$", sub)
            if mm and m == "GET": return pjr.get_project(mm.group(1), org, pjs)
            mm = re.match(r"/projects/([^/]+)/budget$", sub)
            if mm and m == "POST": need(P); return pjr.add_budget(mm.group(1), pjr.BudgetBody(**b), org, a, pjs)
            mm = re.match(r"/projects/([^/]+)/budget/(\d+)/remove$", sub)
            if mm: need(P); return pjr.remove_budget(mm.group(1), int(mm.group(2)), pjr.ReasonBody(**b), org, a, pjs)
            mm = re.match(r"/projects/([^/]+)/submit$", sub)
            if mm: need(P); return pjr.submit(mm.group(1), pjr.NoteBody(**b), org, a, pjs)
            mm = re.match(r"/projects/([^/]+)/withdraw$", sub)
            if mm: need(P); return pjr.withdraw(mm.group(1), pjr.ReasonBody(**b), org, a, pjs)
            mm = re.match(r"/projects/([^/]+)/approve$", sub)
            if mm: need(A_); return pjr.approve(mm.group(1), pjr.NoteBody(**b), org, a, pjs)
            mm = re.match(r"/projects/([^/]+)/return$", sub)
            if mm: need(A_); return pjr.return_project(mm.group(1), pjr.ReasonBody(**b), org, a, pjs)
            mm = re.match(r"/projects/([^/]+)/close$", sub)
            if mm: need(A_); return pjr.close_project(mm.group(1), pjr.ReasonBody(**b), org, a, pjs)
            mm = re.match(r"/projects/([^/]+)/entries$", sub)
            if mm and m == "POST": need(P); return pjr.add_entry(mm.group(1), pjr.EntryBody(**b), org, a, pjs)
            mm = re.match(r"/projects/([^/]+)/entries/(\d+)/approve$", sub)
            if mm: need(A_); return pjr.approve_entry(mm.group(1), int(mm.group(2)), pjr.NoteBody(**b), org, a, pjs)
            mm = re.match(r"/projects/([^/]+)/entries/(\d+)/reject$", sub)
            if mm: need(A_); return pjr.reject_entry(mm.group(1), int(mm.group(2)), pjr.ReasonBody(**b), org, a, pjs)
        if path.startswith("/datagov"):
            need(AUDIT_READ); r_ = _ws(dgr, dgs, path[len("/datagov"):], m, b, org, a, qs, DG_ROUTES, DG_PREPARE, DG_APPROVE, need)
            if r_ is not _NO: return r_
        if path.startswith("/oprs"):
            need(AUDIT_READ); r_ = _ws(opr, ops, path[len("/oprs"):], m, b, org, a, qs, OPR_ROUTES, OPR_PREPARE, OPR_APPROVE, need)
            if r_ is not _NO: return r_
        if path.startswith("/impact"):
            need(AUDIT_READ); r_ = _ws(impr, imps, path[len("/impact"):], m, b, org, a, qs, IMP_ROUTES, IMP_PREPARE, IMP_APPROVE, need)
            if r_ is not _NO: return r_
        if path.startswith("/insolvency"):
            need(AUDIT_READ); r_ = _ws(isvr, isvs, path[len("/insolvency"):], m, b, org, a, qs, ISV_ROUTES, ISV_PREPARE, ISV_APPROVE, need)
            if r_ is not _NO: return r_
        if path.startswith("/pension"):
            need(AUDIT_READ); r_ = _ws(penr, pens, path[len("/pension"):], m, b, org, a, qs, PEN_ROUTES, PEN_PREPARE, PEN_APPROVE, need)
            if r_ is not _NO: return r_
        if path.startswith("/franchise"):
            need(AUDIT_READ); r_ = _ws(fchr, fchs, path[len("/franchise"):], m, b, org, a, qs, FCH_ROUTES, FCH_PREPARE, FCH_APPROVE, need)
            if r_ is not _NO: return r_
        if path.startswith("/mergers"):
            need(AUDIT_READ); r_ = _ws(mar, mas, path[len("/mergers"):], m, b, org, a, qs, MNA_ROUTES, MNA_PREPARE, MNA_APPROVE, need)
            if r_ is not _NO: return r_
        if path.startswith("/pubfin"):
            r_ = _pf(path[len("/pubfin"):], m, b, org, a, qs, need)
            if r_ is not _NO: return r_
        if path.startswith("/health"):
            r_ = _hc(path[len("/health"):], m, b, org, a, qs, need)
            if r_ is not _NO: return r_
        if path.startswith("/approvals"):
            need(AUDIT_READ); r_ = _ws(apwr, apws, path[len("/approvals"):], m, b, org, a, qs, APW_ROUTES, APW_PREPARE, APW_APPROVE, need)
            if r_ is not _NO: return r_
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
            mm = re.match(r"/proof-links/([^/]+)/supersede$", path)
            if mm: need(GRC_PREPARE); return plr.supersede(mm.group(1), plr.SupersedeBody(**b), org, a, pls)
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
