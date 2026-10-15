/**
 * Application entry point. Browser-only — nothing in this file is
 * unit-tested in this environment (it's pure orchestration: DOM
 * mounting, real fetch calls, real window/location access), matching
 * exactly the same boundary lib/vdom.js's mount() draws. Every page
 * render function it wires together IS unit-tested — see
 * frontend/tests/. See docs/frontend-runtime-verification.md for what
 * "verified" means here vs. what's pending real-browser execution.
 *
 * Phase 8 extends this file with the seven functional areas Phase 5
 * left unbuilt (Accounting, Evidence, Reconciliation, Reporting,
 * Period Close, Controls & Compliance, Administration). Every one of
 * them follows the exact same shape Dashboard/AuditWorkspace already
 * established: this file owns ALL real API calls and mutable state;
 * every page module is a pure `Component(props) -> vnode` function
 * that only ever renders what it's given.
 */
import { ApiClient } from "./api/client.js";
import { AuthStore } from "./state/auth-store.js";
import { Router, matchRoute } from "./lib/router.js";
import { h, mount } from "./lib/vdom.js";
import { allowed } from "./components/PermissionGate.js";
import { PERMISSIONS } from "./lib/permissions.js";
import { Login } from "./pages/Login.js";
import { VerifyEmail } from "./pages/VerifyEmail.js";
import { Recovery } from "./pages/Recovery.js";
import { validateSignup, validateLogin, validateNewPassword, emailProblem, codeProblem, normaliseCode, secondsLeft } from "./lib/passwords.js";
import { Dashboard } from "./pages/Dashboard.js";
import { AuditWorkspace, buildChainLinks } from "./pages/AuditWorkspace.js";
import { DrilldownPanel } from "./components/DrilldownPanel.js";
import { Accounting } from "./pages/Accounting.js";
import { Evidence } from "./pages/Evidence.js";
import { Reconciliation } from "./pages/Reconciliation.js";
import { Reporting } from "./pages/Reporting.js";
import { PeriodClose } from "./pages/PeriodClose.js";
import { Compliance } from "./pages/Compliance.js";
import { Administration } from "./pages/Administration.js";
import { Standards } from "./pages/Standards.js";
import { Passport } from "./pages/Passport.js";
import { DataImport, newImportForm, validateImportForm, buildImportArgs, allowedPurposes } from "./pages/DataImport.js";
import { AiAssistant, newAiForm, validateAiForm, buildAiRequest } from "./pages/AiAssistant.js";
import { PassportSharing, newWizard, presetRange, validateStep, buildSharePayload, RECIPIENT_DEFAULTS, STEPS } from "./pages/PassportSharing.js";
import { SharedPassport } from "./pages/SharedPassport.js";
import { Diagnostics, formatReport } from "./pages/Diagnostics.js";
import { runSelfTest } from "./lib/selftest.js";
import { Security, visibleTabs } from "./pages/Security.js";
import { Validation } from "./pages/Validation.js";
import { Pilot } from "./pages/Pilot.js";
import { Network } from "./pages/Network.js";
import { Proof } from "./pages/Proof.js";
import { EvidenceReview } from "./pages/EvidenceReview.js";
import { verifyPayload } from "./lib/evidenceReview.js";
import { draftFromRules, newRule, toggleValue, rulesPayload } from "./lib/evidenceRules.js";
import { StandardsRegistry } from "./pages/StandardsRegistry.js";
import { Agents } from "./pages/Agents.js";
import { EMPTY_AGENT, agentFormProblem } from "./lib/agents.js";
import { Assurance } from "./pages/Assurance.js";
import { ProofLinks } from "./pages/ProofLinks.js";
import { EntityConfig } from "./pages/EntityConfig.js";
import { filterNavByWorkspaces, shownFor, formFromConfig, configPayload, toggleWorkspace, suggestedFor } from "./lib/entityConfig.js";
import { EMPTY_LINK, EMPTY_GAP, linkPayload, gapPayload, needsReason, ACTION_NOTICE, relationsFor } from "./lib/proofLinks.js";
import { EMPTY_FORM, formProblem } from "./lib/standardsRegistry.js";
import { Analysis } from "./pages/Analysis.js";
import { Workspaces } from "./pages/Workspaces.js";
import { Tax } from "./pages/Tax.js";
import { Forensic } from "./pages/Forensic.js";
import { Grc } from "./pages/Grc.js";
import { Pubfin } from "./pages/Pubfin.js";
import * as PF from "./lib/pubfin.js";
import { Bizdev } from "./pages/Bizdev.js";
import * as BD from "./lib/bizdev.js";
import { Cyber } from "./pages/Cyber.js";
import { Treasury } from "./pages/Treasury.js";
import * as TR from "./lib/treasury.js";
import { Procurement } from "./pages/Procurement.js";
import * as PC from "./lib/procurement.js";
import { Fpa } from "./pages/Fpa.js";
import * as FP from "./lib/fpa.js";
import { Fincrime } from "./pages/Fincrime.js";
import { ItAudit } from "./pages/ItAudit.js";
import { Resilience } from "./pages/Resilience.js";
import * as RS from "./lib/resilience.js";
import { AiGovernance } from "./pages/AiGovernance.js";
import * as GV from "./lib/aigov.js";
import { Quality } from "./pages/Quality.js";
import * as QL from "./lib/quality.js";
import { Secretarial } from "./pages/Secretarial.js";
import * as CS from "./lib/secretarial.js";
import { FixedAssets } from "./pages/FixedAssets.js";
import * as FA from "./lib/fixedassets.js";
import { Inventory } from "./pages/Inventory.js";
import * as IV from "./lib/inventory.js";
import { Investments } from "./pages/Investments.js";
import * as IM from "./lib/investments.js";
import { Valuation } from "./pages/Valuation.js";
import * as VL from "./lib/valuation.js";
import { Insurance } from "./pages/Insurance.js";
import * as IC from "./lib/insurance.js";
import { Esg } from "./pages/Esg.js";
import * as ES from "./lib/esg.js";
import { Payroll } from "./pages/Payroll.js";
import * as PW from "./lib/payroll.js";
import * as IA from "./lib/itaudit.js";
import * as FX from "./lib/fincrime.js";
import * as CY from "./lib/cyber.js";
import { Health } from "./pages/Health.js";
import * as HC from "./lib/health.js";
import { AiDock } from "./components/AiDock.js";
import * as DK from "./lib/aidock.js";
import { emptyRisk, riskProblem, riskBody, riskForm, emptyAction, actionProblem, actionBody, actionForm, doneProblem, emptyObligation, obligationProblem, obligationBody, obligationForm, emptyMet, metProblem, noteProblem, acceptProblem } from "./lib/grc.js";
import { emptyCase, caseProblem, emptyRun, runProblem, runBody, emptyFinding, findingProblem, findingBody, findingForm } from "./lib/forensic.js";
import { emptyRule, ruleProblem, ruleBody, ruleForm, calcProblem, todayIso } from "./lib/tax.js";
import { scenarioProblem, scenarioBody, scenarioForm, emptyScenario, budgetBody, budgetProblem, emptyReportForm, reportProblem, reportBody } from "./lib/analysis.js";
import { inviteBody, inviteProblem, acceptGrant, emptyInviteForm } from "./lib/network.js";
import { pilotBody, clientBody, clientFormProblem, timeBody, issueBody, passportUseBody, surveyBody, surveyProblem, emptyPilotForm, emptyClientForm, today, download } from "./lib/pilot.js";
import { reviewForm, reviewBody, declarationBody, engagementBody, reviewerBody, emptyObservation, actingMode } from "./lib/validation.js";
import { makeBinding, parseOidcReturn, interpretLogin, parseRegions } from "./lib/signin.js";
import { Landing } from "./pages/Landing.js";
import { Home } from "./pages/Home.js";
import { Onboarding } from "./components/Onboarding.js";
import { Setup } from "./pages/Setup.js";
import { validateCreate, validateSettings, validatePeriod, mergeProfile, fiscalYear, currencyForCountry, resumeStep, canSetUp } from "./lib/onboarding.js";
import { SideNav, TopBar } from "./components/Shell.js";
import { groupNav, activeGroupId, breadcrumbs, searchPages, orgName, loadHome } from "./lib/home.js";
import { signedOutScreen } from "./lib/landing.js";

const API_BASE_URL = "https://asavexa.onrender.com";
const authStore = new AuthStore();
const api = new ApiClient({
  baseUrl: API_BASE_URL,
  getToken: () => authStore.getToken(),
  onUnauthenticated: () => {
    const hadSession = !!authStore.getToken();
    authStore.clear();
    resetSecurityState();
    // An expired session goes to sign-in. A 401 with no session at all (a public lookup) must not skip the front page.
    if (hadSession) uiState.enteredAuth = true;
    render();
  },
});

const root = document.getElementById("app-root");

// Escape closes any open menu, the search list and the phone menu; a click anywhere else closes the menus.
if (typeof document !== "undefined" && document.addEventListener) {
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (uiState.menu || uiState.search.open || uiState.mobileNav) { uiState.menu = null; uiState.mobileNav = false; uiState.search = { q: "", open: false, idx: 0 }; render(); }
  });
  document.addEventListener("click", (e) => {
    const t = e.target;
    const inside = t && t.closest ? t.closest(".menu-wrap, .gsearch") : null;
    if (!inside && (uiState.menu || uiState.search.open)) { uiState.menu = null; uiState.search.open = false; render(); }
  });
}

const NAV_ITEMS = [
  { path: "/", label: "Dashboard", permission: null },
  { path: "/audit", label: "Audit Workspace", permission: PERMISSIONS.AUDIT_READ },
  { path: "/accounting", label: "Accounting", permission: PERMISSIONS.LEDGER_READ },
  { path: "/evidence", label: "Evidence", permission: PERMISSIONS.EVIDENCE_READ },
  { path: "/reconciliation", label: "Reconciliation", permission: PERMISSIONS.RECONCILIATION_READ },
  { path: "/reporting", label: "Reporting", permission: PERMISSIONS.REPORTING_READ },
  { path: "/proof", label: "Proof Graph", permission: PERMISSIONS.REPORTING_READ },
  { path: "/evidence-review", label: "Evidence Review", permission: PERMISSIONS.REPORTING_READ },
  { path: "/workspaces", label: "Professional Workspaces", permission: PERMISSIONS.REPORTING_READ },
  { path: "/analysis", label: "Financial Analysis", permission: PERMISSIONS.REPORTING_READ },
  { path: "/tax", label: "Tax Compliance", permission: PERMISSIONS.REPORTING_READ },
  { path: "/forensic", label: "Forensic Investigation", permission: PERMISSIONS.FORENSIC_READ },
  { path: "/grc", label: "Governance, Risk and Compliance", permission: PERMISSIONS.AUDIT_READ },
  { path: "/pubfin", label: "Public Finance", permission: PERMISSIONS.REPORTING_READ },
  { path: "/bizdev", label: "Business Development", permission: PERMISSIONS.REPORTING_READ },
  { path: "/cyber", label: "Cybersecurity", permission: PERMISSIONS.AUDIT_READ },
  { path: "/treasury", label: "Treasury and Cash", permission: PERMISSIONS.REPORTING_READ },
  { path: "/procurement", label: "Procurement", permission: PERMISSIONS.REPORTING_READ },
  { path: "/fpa", label: "Planning and KPIs", permission: PERMISSIONS.REPORTING_READ },
  { path: "/fincrime", label: "Financial-crime casework", permission: PERMISSIONS.FINCRIME_READ },
  { path: "/itaudit", label: "IT audit", permission: PERMISSIONS.AUDIT_READ },
  { path: "/resilience", label: "Risk indicators and resilience", permission: PERMISSIONS.AUDIT_READ },
  { path: "/aigov", label: "AI governance", permission: PERMISSIONS.AUDIT_READ },
  { path: "/quality", label: "Quality management", permission: PERMISSIONS.AUDIT_READ },
  { path: "/secretarial", label: "Company secretarial", permission: PERMISSIONS.AUDIT_READ },
  { path: "/fixedassets", label: "Fixed assets", permission: PERMISSIONS.AUDIT_READ },
  { path: "/inventory", label: "Inventory", permission: PERMISSIONS.AUDIT_READ },
  { path: "/investments", label: "Investments", permission: PERMISSIONS.AUDIT_READ },
  { path: "/valuation", label: "Valuation", permission: PERMISSIONS.AUDIT_READ },
  { path: "/insurance", label: "Insurance and claims", permission: PERMISSIONS.AUDIT_READ },
  { path: "/esg", label: "ESG and carbon", permission: PERMISSIONS.AUDIT_READ },
  { path: "/payroll", label: "Payroll and workforce cost", permission: PERMISSIONS.AUDIT_READ },
  { path: "/health", label: "Health Centre", permission: PERMISSIONS.HEALTH_READ },
  { path: "/period-close", label: "Period Close", permission: PERMISSIONS.PERIOD_CLOSE_READ },
  { path: "/compliance", label: "Controls & Compliance", permission: PERMISSIONS.CONTROL_READ },
  { path: "/admin", label: "Administration", permission: PERMISSIONS.ORG_MANAGE_USERS },
  { path: "/setup", label: "Organisation setup", permission: PERMISSIONS.ORG_MANAGE_SETTINGS },
  { path: "/entity-config", label: "Organisation type and workspaces", permission: PERMISSIONS.ORG_MANAGE_SETTINGS },
  { path: "/import", label: "Data Import", permission: null, anyOf: [PERMISSIONS.RECONCILIATION_IMPORT, PERMISSIONS.EVIDENCE_UPLOAD, PERMISSIONS.ACCOUNT_MANAGE, PERMISSIONS.JOURNAL_CREATE] },
  { path: "/ai", label: "ASAVEXA AI", permission: PERMISSIONS.LEDGER_READ },
  { path: "/passport", label: "Financial Passport", permission: PERMISSIONS.PASSPORT_MANAGE },
  { path: "/passport/sharing", label: "Passport Sharing", permission: PERMISSIONS.PASSPORT_MANAGE },
  { path: "/standards", label: "Standards & Policies", permission: null },
  { path: "/standards-registry", label: "Standards Registry", permission: PERMISSIONS.AUDIT_READ },
  { path: "/agents", label: "Agents", permission: PERMISSIONS.AUDIT_READ },
  { path: "/assurance", label: "Assurance", permission: PERMISSIONS.AUDIT_READ },
  { path: "/proof-links", label: "Proof Links", permission: PERMISSIONS.AUDIT_READ },
  { path: "/validation", label: "Professional Validation", permission: PERMISSIONS.AUDIT_READ },
  { path: "/network", label: "ASAVEXA Network", permission: null },
  { path: "/pilot", label: "Real Pilot", permission: null },
  { path: "/security", label: "Security", permission: null },
  { path: "/diagnostics", label: "Connection & Self-Test", permission: null },
];

// Order matters for matchRoute (first match wins): a literal segment
// like "/new" must be listed before the ":id" param route it would
// otherwise also match.
const routes = [
  { path: "/", name: "dashboard" },
  { path: "/setup", name: "setup" },
  { path: "/entity-config", name: "entity-config" },
  { path: "/audit", name: "audit" },
  { path: "/accounting/journals/new", name: "accounting-journal-new" },
  { path: "/accounting/journals/:id", name: "accounting-journal-detail" },
  { path: "/accounting", name: "accounting" },
  { path: "/evidence/:id", name: "evidence-detail" },
  { path: "/evidence", name: "evidence" },
  { path: "/reconciliation/new", name: "reconciliation-new" },
  { path: "/reconciliation/:id", name: "reconciliation-detail" },
  { path: "/reconciliation", name: "reconciliation" },
  { path: "/reporting", name: "reporting" },
  { path: "/proof", name: "proof" },
  { path: "/evidence-review", name: "evidence-review" },
  { path: "/workspaces", name: "workspaces" },
  { path: "/analysis", name: "analysis" },
  { path: "/tax", name: "tax" },
  { path: "/forensic", name: "forensic" },
  { path: "/grc", name: "grc" },
  { path: "/pubfin", name: "pubfin" },
  { path: "/bizdev", name: "bizdev" },
  { path: "/cyber", name: "cyber" },
  { path: "/treasury", name: "treasury" },
  { path: "/procurement", name: "procurement" },
  { path: "/fpa", name: "fpa" },
  { path: "/fincrime", name: "fincrime" },
  { path: "/itaudit", name: "itaudit" },
  { path: "/resilience", name: "resilience" },
  { path: "/aigov", name: "aigov" },
  { path: "/quality", name: "quality" },
  { path: "/secretarial", name: "secretarial" },
  { path: "/fixedassets", name: "fixedassets" },
  { path: "/inventory", name: "inventory" },
  { path: "/investments", name: "investments" },
  { path: "/valuation", name: "valuation" },
  { path: "/insurance", name: "insurance" },
  { path: "/esg", name: "esg" },
  { path: "/payroll", name: "payroll" },
  { path: "/health", name: "health" },
  { path: "/period-close", name: "period-close" },
  { path: "/compliance/findings/:id", name: "compliance-finding-detail" },
  { path: "/compliance/findings", name: "compliance-findings" },
  { path: "/compliance", name: "compliance" },
  { path: "/admin", name: "admin" },
  { path: "/import", name: "import" },
  { path: "/ai", name: "ai" },
  { path: "/passport/sharing", name: "passport-sharing" },
  { path: "/passport", name: "passport" },
  { path: "/shared/:token", name: "shared" },
  { path: "/welcome", name: "welcome" },
  { path: "/standards", name: "standards" },
  { path: "/standards-registry", name: "standards-registry" },
  { path: "/agents", name: "agents" },
  { path: "/assurance", name: "assurance" },
  { path: "/proof-links", name: "proof-links" },
  { path: "/validation", name: "validation" },
  { path: "/network", name: "network" },
  { path: "/pilot", name: "pilot" },
  { path: "/security", name: "security" },
  { path: "/diagnostics", name: "diagnostics" },
];

let uiState = {
  loginMode: "login", loginError: null, loginPending: false, vf: null,
  auth: { draft: { email: "", password: "", confirm: "" }, fieldErrors: {}, notice: null }, rc: null,
  enteredAuth: false, landingMenu: false, landingSeen: false,
  navOpen: {}, mobileNav: false, search: { q: "", open: false, idx: 0 }, menu: null, lastPath: null,
  home: { key: "", data: null, loading: false, error: null }, showLocked: false, orgLoading: false,
  onb: { mode: "auto", form: { name: "", category: "" }, errors: {}, pending: false, error: null, copied: false, checking: false, checkMessage: null, orgs: null, loading: false }, setup: null, orgList: null, switching: false, switchError: null,
  mfaChallenge: null, ssoConfig: null, secNoOrg: false, sec: null,
  auditQuery: "", auditJournal: null, auditChain: null, auditError: null,

  // Accounting
  accounts: null, periods: null, journals: null, accountingError: null,
  accountForm: { code: "", name: "", type: "ASSET", currency: "USD" }, accountFormError: null, accountFormPending: false,
  periodForm: { name: "", start_date: "", end_date: "" }, periodFormError: null, periodFormPending: false,
  journalForm: { date: "", description: "", currency: "USD", lines: [{}, {}] }, journalFormError: null, journalFormPending: false,
  journal: null, journalError: null, journalAuditEvents: null,

  // Evidence
  evidenceItems: null, evidenceError: null, evidenceFilterStatus: "", evidenceFilterType: "",
  evidenceUploadForm: { type: "INVOICE" }, evidenceUploadFile: null, evidenceUploadError: null, evidenceUploadPending: false,
  evidenceDetail: null, evidenceDetailError: null, evidenceRejectReason: "",

  // Reconciliation
  reconciliations: null, reconciliationError: null,
  reconciliationForm: {}, reconciliationFormError: null, reconciliationFormPending: false,
  reconciliationDetail: null, reconciliationDetailError: null, reconciliationTransactions: null,
  reconciliationRejectReason: "", matchJournalIds: {}, matchRejectReasons: {},

  // Reporting
  reportType: "trial-balance", reportingError: null, reportResult: null, traceResult: null,
  selectedPeriodId: "", selectedAccountId: "",
  traceCompleteness: null, traceReconciliation: null,

  // Drilldown panel ("Why is this number here?" / "Show me the
  // evidence" — Phase 1). Deliberately global (not nested under
  // Reporting/Accounting/etc. state) since it can be opened from any
  // page that shows a journal-backed number.
  drilldownOpen: false, drilldownLoading: false, drilldownError: null, drilldownNote: null,
  drilldownJournal: null, drilldownChain: null, drilldownAuditEvents: null, drilldownEvidence: null,
  drilldownCompleteness: null, drilldownReconciliation: null,

  // Period Close
  selectedClosePeriodId: "", periodCloseError: null, closeReadiness: null, activeCloseProcess: null,
  closeProcesses: null, approveReason: "", periodCloseRejectReason: "",

  // Compliance
  controls: null, executions: null, complianceError: null, selectedControlId: null, executeParams: "",
  executePeriodId: "", executeError: null, executePending: false,
  defineForm: { domain: "ACCOUNTING", severity: "MEDIUM" }, defineError: null, definePending: false,
  findings: null, findingFilter: "", finding: null, findingError: null, remediation: null,
  reasonInputs: {}, remediationForm: {},

  // Data Import
  impForm: newImportForm(), impFile: null, impFormError: null, impPreviewing: false, impPreviewError: null, impBatch: null,
  impOnlyProblems: false, impAck: false, impCommitting: false, impCommitError: null, impResult: null,
  impReconciliations: null, impLevels: null, impLoadError: null,

  // ASAVEXA AI
  aiMode: "EXPLAIN", aiForm: newAiForm(), aiRunning: false, aiFormError: null, aiQuestion: "",
  aiResult: null, aiResultError: null, aiExpanded: null, aiJournals: null, aiPeriods: null, aiLoadError: null,

  // Financial Passport
  passport: null, passportError: null, passportRefreshing: false,
  passportStructure: { owners: [], subsidiaries: [] }, passportStructureSaving: false,
  passportStructureError: null, passportStructureSaved: false,

  // Permissioned sharing (organisation side)
  shares: null, sharesError: null, shareWizard: null, shareWizardError: null, shareCreating: false,
  shareResult: null, shareLink: "", shareCopied: null, shareRevokeTarget: null, shareRevokeReason: "",
  shareRevoking: false, shareRevokeError: null, shareLogTarget: null, shareLog: null, shareLogLoading: false, shareLogError: null,

  // Shared passport (recipient side). The session token lives only here, in memory.
  shared: { token: null, code: "", email: "", phase: "verify", pending: false, error: null, expired: false,
    data: null, sessionToken: null, downloading: false, downloadError: null },

  // Standards & Policies
  standardsCatalog: null, standardsForm: {}, standardsPreview: null, standardsError: null,
  standardsPreviewError: null, standardsPreviewing: false, standardsSaving: false, standardsSaveError: null, standardsSaved: false,

  // Diagnostics
  diagConnection: null, diagConnectionRunning: false, diagResults: [], diagRunning: false, diagCopied: false,

  // Administration
  organisation: null, members: null, adminError: null,
  profileForm: {}, profileError: null, profilePending: false, profileSaved: false,
  addMemberForm: { role: "READ_ONLY" }, addMemberError: null, addMemberPending: false, roleDrafts: {},
};

// Page loaders (see once()) run once per visit to a page. Navigating
// clears this so each visit refreshes its data.
const loadedOnce = new Set();
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const router = new Router(routes, {
  onChange: () => {
    loadedOnce.clear();
    uiState.dashboardData = null;
    uiState.journalRequestedId = null;
    uiState.evidenceDetailRequestedId = null;
    uiState.reconciliationDetailRequestedId = null;
    uiState.impFile = null; uiState.impFormError = null; uiState.impPreviewing = false; uiState.impPreviewError = null; uiState.impBatch = null;
    uiState.impOnlyProblems = false; uiState.impAck = false; uiState.impCommitting = false; uiState.impCommitError = null; uiState.impResult = null;
    uiState.impReconciliations = null; uiState.impLoadError = null; uiState.impForm = newImportForm();
    uiState.aiResult = null; uiState.aiResultError = null; uiState.aiFormError = null; uiState.aiExpanded = null;
    uiState.aiRunning = false; uiState.aiQuestion = ""; uiState.aiJournals = null; uiState.aiPeriods = null; uiState.aiLoadError = null;
    uiState.shareWizard = null; uiState.shareResult = null; uiState.shareLink = "";
    uiState.shareRevokeTarget = null; uiState.shareLogTarget = null;
    render();
  },
});

/** From the landing page into the sign-in screen, either on Sign in or on Create account. */
function openAuth(mode) {
  uiState.enteredAuth = true; uiState.loginMode = mode; uiState.loginError = null; uiState.landingMenu = false; uiState.auth.fieldErrors = {};
  render();
  window.scrollTo(0, 0);
}

/** Scroll to a section of the landing page. The menu is closed without a re-render so the scroll is not interrupted. */
function landingJump(id) {
  const calm = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const behavior = calm ? "auto" : "smooth";
  if (id === "top") window.scrollTo({ top: 0, behavior });
  else { const el = document.getElementById(`ld-${id}`); if (el) el.scrollIntoView({ behavior, block: "start" }); }
  if (uiState.landingMenu) {
    uiState.landingMenu = false;
    const nav = document.getElementById("ld-nav"), burger = document.getElementById("ld-burger");
    if (nav) nav.classList.remove("is-open");
    if (burger) { burger.setAttribute("aria-expanded", "false"); burger.setAttribute("aria-label", "Open the menu"); }
  }
}

function render() {
  const authState = authStore.getState();

  // A recipient's link is public: it never needs (or touches) an organisation login.
  const publicMatch = matchRoute(routes, router.currentPath());
  if (publicMatch && publicMatch.route.name === "shared") {
    renderSharedPassport(publicMatch.params.token);
    return;
  }

  // Someone who is already signed in has no use for the front page.
  if (authState.token && router.currentPath() === "/welcome") { router.navigate("/"); return; }

  if (!authState.token && signedOutScreen({ path: router.currentPath(), enteredAuth: uiState.enteredAuth }) === "landing") {
    const animate = !uiState.landingSeen; uiState.landingSeen = true;
    mount(Landing({
      animate, menuOpen: uiState.landingMenu,
      onSignIn: () => openAuth("login"), onGetStarted: () => openAuth("register"),
      onJump: landingJump, onToggleMenu: () => { uiState.landingMenu = !uiState.landingMenu; render(); },
    }), root);
    return;
  }

  if (!authState.token && uiState.loginMode === "verify" && uiState.vf) {
    const v = uiState.vf;
    mount(h("div", { id: "screen" }, VerifyEmail({
      email: v.email, sent: v.sent, resent: v.resent, code: v.code, pending: v.pending, error: v.error, notice: v.notice, fieldErrors: v.fieldErrors, verified: v.verified,
      available: v.available, cooldown: secondsLeft(v.cooldownUntil || 0), expiresMinutes: v.expiresMinutes,
      onDraft: (k, val) => { v[k] = val; }, onVerify: handleVerifyConfirm, onResend: handleVerifyResend, onContinue: handleVerifyContinue,
    })), root);
    return;
  }

  if (!authState.token && uiState.loginMode === "recover" && uiState.rc) {
    const r = uiState.rc;
    mount(h("div", { id: "screen" }, Recovery({
      step: r.step, email: r.email, code: r.code, pending: r.pending, error: r.error, notice: r.notice, fieldErrors: r.fieldErrors, available: r.available,
      cooldown: secondsLeft(r.cooldownUntil || 0), expiresMinutes: r.expiresMinutes, draft: r.draft,
      onDraft: (k, v) => { if (k === "email" || k === "code") r[k] = v; else r.draft[k] = v; },
      onRequest: handleRecoveryRequest, onResend: () => handleRecoveryRequest(r.email, true), onVerify: handleRecoveryVerify, onReset: handleRecoveryReset,
      onChangeEmail: () => { stopRecoveryTimer(); Object.assign(r, { step: "request", code: "", error: null, notice: null, fieldErrors: {} }); render(); focusHeading("#rc-title"); },
      onBack: leaveRecovery,
    })), root);
    return;
  }

  if (!authState.token) {
    mount(
      h("div", { id: "screen" },
        Login({
          draft: uiState.auth.draft, fieldErrors: uiState.auth.fieldErrors, notice: uiState.auth.notice,
          onDraft: (k, v) => { uiState.auth.draft[k] = v; }, onForgot: openRecovery,
          onHome: () => { uiState.enteredAuth = false; uiState.loginError = null; uiState.mfaChallenge = null; clearAuthDraft(); if (router.currentPath() !== "/") router.navigate("/"); else render(); window.scrollTo(0, 0); },
          mode: uiState.loginMode, pending: uiState.loginPending, error: uiState.loginError,
          onSubmit: handleAuthSubmit, onSwitchMode: (m) => { uiState.loginMode = m; uiState.loginError = null; uiState.auth.fieldErrors = {}; uiState.auth.notice = null; uiState.auth.draft.password = ""; uiState.auth.draft.confirm = ""; render(); },
          mfaStep: !!uiState.mfaChallenge, onMfaSubmit: handleMfaSubmit,
          onMfaCancel: () => { uiState.mfaChallenge = null; uiState.loginError = null; render(); },
          sso: uiState.ssoConfig, onSso: handleSsoStart,
        })
      ),
      root
    );
    return;
  }

  if (!authState.organisationId && uiState.secNoOrg) {
    // Setting up two-step sign-in must be possible BEFORE an organisation is open (an organisation can require it).
    once("secLoading", () => loadSecurity(authState));
    mount(h("div", { style: "max-width:960px; margin:24px auto; padding:0 16px;" },
      h("button", { className: "btn btn-secondary", style: "margin-bottom:12px;", onClick: () => { uiState.secNoOrg = false; render(); } }, "← Back to organisations"),
      renderSecurityPage({ ...authState, role: null })), root);
    return;
  }

  if (!authState.organisationId) { renderOnboarding(authState); return; }

  renderShell(authState);
}

function renderShell(authState) {
  const path = router.currentPath();
  const matched = matchRoute(routes, path);
  // Moving to another page closes every open menu, the search list and the phone menu.
  if (uiState.lastPath !== path) { uiState.lastPath = path; uiState.menu = null; uiState.mobileNav = false; uiState.search = { q: "", open: false, idx: 0 }; }
  const visible = visibleNav(authState, path);
  const groups = groupNav(visible);
  const results = searchPages(uiState.search.q, visible);
  const orgs = uiState.orgList || (uiState.home.data && uiState.home.data.orgs) || null;
  const closeMenus = () => { uiState.menu = null; uiState.search.open = false; };
  // The top bar shows the organisation's name, so make sure the list is known on every page, not only the home page.
  if (uiState.orgList === null && !(uiState.home.data && uiState.home.data.orgs)) ensureOrgs();

  mount(
    h(
      "div",
      { className: "app-shell" },
      SideNav({
        groups, navOpen: uiState.navOpen, activeId: activeGroupId(groups), mobileOpen: uiState.mobileNav,
        onToggleGroup: (id, wasOpen) => { uiState.navOpen = { ...uiState.navOpen, [id]: !wasOpen }; render(); },
        onGo: () => { uiState.mobileNav = false; render(); },
      }),
      uiState.mobileNav ? h("div", { className: "nav-scrim", id: "nav-scrim", onClick: () => { uiState.mobileNav = false; render(); } }) : null,
      h(
        "main",
        { className: "app-main", id: "app-main" },
        TopBar({
          crumbs: breadcrumbs(path, visibleNav(authState, path, true)), user: authState.user, role: authState.role,
          orgs: uiState.orgList === false ? false : (uiState.orgList || (uiState.home.data && uiState.home.data.orgs) || null),
          orgId: authState.organisationId, orgLabel: orgName(orgs, authState.organisationId),
          menu: uiState.menu, switching: uiState.switching, switchError: uiState.switchError, mobileOpen: uiState.mobileNav,
          search: uiState.search, results,
          onToggleNav: () => { uiState.mobileNav = !uiState.mobileNav; render(); },
          onToggle: (m) => { uiState.menu = uiState.menu === m || !m ? null : m; uiState.search.open = false; uiState.switchError = null; if (uiState.menu === "org") ensureOrgs(); render(); },
          onSwitch: (id) => switchOrganisation(id),
          onAll: () => { authStore.setOrganisation(null, null); window.location.hash = "#/"; window.location.reload(); },
          onGo: (p) => { closeMenus(); router.navigate(p); render(); },
          onSignOut: () => { closeMenus(); handleLogout(); },
          onInput: (value, focusOnly) => {
            // Focusing the box re-opens the list, but only once: a render restores focus, which must not trigger another render.
            if (focusOnly && (uiState.search.open || !uiState.search.q.trim())) return;
            uiState.menu = null; uiState.search = { q: value, open: true, idx: focusOnly ? uiState.search.idx : 0 }; render(); },
          onKey: (e, list) => {
            const st = uiState.search;
            if (e.key === "ArrowDown") { e.preventDefault(); st.idx = list.length ? (st.idx + 1) % list.length : 0; st.open = true; render(); }
            else if (e.key === "ArrowUp") { e.preventDefault(); st.idx = list.length ? (st.idx - 1 + list.length) % list.length : 0; render(); }
            else if (e.key === "Enter") { e.preventDefault(); const r = list[st.idx]; if (r) { uiState.search = { q: "", open: false, idx: 0 }; router.navigate(r.path); render(); } }
            else if (e.key === "Escape") { uiState.search = { q: "", open: false, idx: 0 }; render(); }
          },
          onPick: () => { uiState.search = { q: "", open: false, idx: 0 }; },
        }),
        renderPage(matched, authState)
      ),
      renderDock(authState, path),
      DrilldownPanel({
        open: uiState.drilldownOpen, loading: uiState.drilldownLoading, error: uiState.drilldownError,
        note: uiState.drilldownNote, journal: uiState.drilldownJournal, chainLinks: uiState.drilldownChain,
        completeness: uiState.drilldownCompleteness, reconciliationStatus: uiState.drilldownReconciliation,
        auditEvents: uiState.drilldownAuditEvents,
        onClose: closeDrilldown, onNavigate: (p) => { closeDrilldown(); router.navigate(p); },
        onShowEvidence: handleShowEvidence,
      })
    ),
    root
  );
}

// ----------------------------------------------------------------------
// Sign-up journey. Before an organisation is open: choose, create or join. After: guided set-up at #/setup.
// The server decides every role; nothing chosen here can raise anyone's permissions.
// ----------------------------------------------------------------------
function focusHeading(sel) {
  setTimeout(() => { const el = document.querySelector(sel); if (el) { el.setAttribute("tabindex", "-1"); el.focus(); window.scrollTo(0, 0); } }, 0);
}

function renderOnboarding(authState) {
  const o = uiState.onb;
  if (o.orgs === null && !o.loading) {
    o.loading = true;
    api.myOrganisations().then((list) => { o.orgs = Array.isArray(list) ? list : false; }).catch(() => { o.orgs = false; }).finally(() => { o.loading = false; render(); });
  }
  mount(Onboarding({
    user: authState.user, orgs: o.orgs, mode: o.mode, form: o.form, errors: o.errors, pending: o.pending, error: o.error,
    copied: o.copied, checking: o.checking, checkMessage: o.checkMessage,
    onMode: (m) => { o.mode = m; o.errors = {}; o.error = null; o.checkMessage = null; render(); focusHeading(".ob-card h2, .ob-choose h2"); },
    onField: (k, v) => { o.form[k] = v; },
    onCreate: handleCreateOrganisation,
    onSelect: async (orgId) => {
      if (o.pending) return;
      o.pending = true; o.error = null; render();
      try { const { role } = await api.selectOrganisation(orgId); authStore.setOrganisation(orgId, role); o.orgs = null; o.mode = "auto"; }
      catch (err) { o.error = (err && err.message) || "Could not open this organisation."; }
      o.pending = false; render();
    },
    onCopy: async () => {
      const id = (authState.user && authState.user.id) || "";
      try { await navigator.clipboard.writeText(id); o.copied = true; } catch { o.copied = false; o.checkMessage = "Copying is not available in this browser. Select the ID and copy it by hand."; }
      render();
    },
    onRecheck: () => {
      o.checking = true; o.checkMessage = null; render();
      api.myOrganisations().then((list) => {
        const l = Array.isArray(list) ? list : [];
        o.orgs = l; o.checkMessage = l.length ? null : "You are not a member of any organisation yet. Once an administrator has added you, check again.";
        if (l.length) o.mode = "auto";
      }).catch((err) => { o.checkMessage = (err && err.message) || "Could not check right now."; }).finally(() => { o.checking = false; render(); });
    },
    onRetry: () => { o.orgs = null; render(); },
    onSecurity: () => { uiState.secNoOrg = true; render(); },
    onSignOut: () => handleLogout(),
  }), root);
}

async function handleCreateOrganisation() {
  const o = uiState.onb;
  if (o.pending) return;
  const v = validateCreate(o.form);
  o.errors = v.errors; o.error = null;
  if (!v.ok) { render(); focusHeading(".ob-err"); return; }
  o.pending = true; render();
  let created = null;
  try {
    created = await api.createOrganisation(v.name);
    const { role } = await api.selectOrganisation(created.id);
    authStore.setOrganisation(created.id, role);
    // Save what is already known. If this fails the organisation still exists and the set-up page asks again.
    try { await api.updateOrganisationProfile({ legal_name: v.name, organisation_type: o.form.category }); } catch { /* shown as an empty field in set-up */ }
    uiState.setup = null; uiState.home = { key: "", data: null, loading: false, error: null }; uiState.dashboardData = null;
    o.form = { name: "", category: "" }; o.orgs = null; o.mode = "auto"; o.pending = false;
    router.navigate("/setup"); render();
  } catch (err) {
    o.pending = false; o.orgs = null;
    o.error = created
      ? `The organisation “${v.name}” was created, but it could not be opened: ${(err && err.message) || "unknown problem"}. It is in your list now.`
      : (err && err.message) || "The organisation could not be created.";
    if (created) o.mode = "auto";
    render();
  }
}

function newSetup() {
  return { loading: false, loadError: null, loadedFor: "", profile: null, periods: [], countries: null, workspaces: null, step: "settings",
    form: { legal_name: "", organisation_type: "", country: "", base_currency: "", fiscal_year_start_month: "" }, currencyTouched: false,
    period: { name: "", start: "", end: "" }, periodTouched: false, errors: {}, saving: false, error: null, notice: null };
}

function renderSetupPage(authState) {
  const key = `${authState.organisationId}|${authState.role}`;
  if (!uiState.setup || uiState.setup.loadedFor !== key) { uiState.setup = newSetup(); uiState.setup.loadedFor = key; loadSetup(authState, uiState.setup, key); }
  const st = uiState.setup;
  const touchPeriod = () => { if (!st.periodTouched) { const m = (st.profile && st.profile.fiscal_year_start_month) || st.form.fiscal_year_start_month; const fy = fiscalYear(m); st.period = { name: fy.name, start: fy.start, end: fy.end }; } };
  const fail = (err, fallback) => { st.saving = false; st.error = (err && err.message) || fallback; render(); focusHeading("#su-error"); };
  return Setup({
    st, role: authState.role,
    onField: (k, v, currency) => { st.form[k] = v; if (currency) st.currencyTouched = true; },
    onCountry: (v) => {
      st.form.country = v;
      if (st.countries && st.countries.length) {
        if (!st.currencyTouched) { const cur = currencyForCountry(st.countries, v); if (cur) st.form.base_currency = cur; }
        render();
      }
    },
    onSaveSettings: async () => {
      if (st.saving) return;
      const v = validateSettings(st.form);
      st.errors = v.errors; st.error = null; st.notice = null;
      if (!v.ok) { render(); focusHeading(".ob-err"); return; }
      st.saving = true; render();
      try {
        const hit = (st.countries || []).find((c) => c.code === st.form.country);
        const saved = await api.updateOrganisationProfile(mergeProfile(st.profile, { ...st.form, country: hit ? hit.name : st.form.country }));
        st.profile = saved; st.saving = false; st.notice = "Organisation details saved."; st.step = "period"; touchPeriod();
        render(); focusHeading("#setup h2");
      } catch (err) { fail(err, "The details could not be saved."); }
    },
    onPeriodField: (k, v) => { st.period[k] = v; st.periodTouched = true; },
    onSavePeriod: async () => {
      if (st.saving) return;
      const v = validatePeriod(st.period);
      st.errors = v.errors; st.error = null; st.notice = null;
      if (!v.ok) { render(); focusHeading(".ob-err"); return; }
      st.saving = true; render();
      try {
        await api.openPeriod({ name: st.period.name.trim(), start_date: st.period.start, end_date: st.period.end });
        st.periods = await api.listPeriods().catch(() => [{ name: st.period.name }]);
        uiState.dashboardData = null; uiState.periods = null;
        st.saving = false; st.notice = "Accounting period opened."; st.step = "workspaces"; render(); focusHeading("#setup h2");
      } catch (err) { fail(err, "The period could not be opened."); }
    },
    onStep: (id) => { st.step = id; st.errors = {}; st.error = null; st.notice = null; if (id === "period") touchPeriod(); render(); focusHeading("#setup h2"); },
    onGo: (p) => router.navigate(p),
    onFinish: () => { uiState.home = { key: "", data: null, loading: false, error: null }; uiState.dashboardData = null; router.navigate("/"); render(); },
    onRetry: () => { uiState.setup = null; render(); },
  });
}

async function loadSetup(authState, st, key) {
  if (!canSetUp(authState.role)) return;
  st.loading = true;
  try {
    const [profile, periods] = await Promise.all([api.getOrganisationProfile(), api.listPeriods()]);
    const [countries, workspaces] = await Promise.all([
      api.taxCountries().then((r) => (r && r.countries) || null).catch(() => null),
      api.workspaces().then((r) => (r && r.workspaces) || null).catch(() => null),
    ]);
    if (uiState.setup !== st || st.loadedFor !== key) return;
    st.profile = profile || {}; st.periods = Array.isArray(periods) ? periods : []; st.countries = countries; st.workspaces = workspaces;
    const hit = countries && countries.find((c) => c.name === st.profile.country || c.code === st.profile.country);
    st.form = {
      legal_name: st.profile.legal_name || "", organisation_type: st.profile.organisation_type || "",
      country: hit ? hit.code : (st.profile.country || ""), base_currency: st.profile.base_currency || "",
      fiscal_year_start_month: st.profile.fiscal_year_start_month ? String(st.profile.fiscal_year_start_month) : "",
    };
    st.currencyTouched = !!st.profile.base_currency;
    st.step = resumeStep({ profile: st.profile, periods: st.periods });
    if (st.step === "period") { const fy = fiscalYear(st.profile.fiscal_year_start_month); st.period = { name: fy.name, start: fy.start, end: fy.end }; }
  } catch (err) { if (uiState.setup === st) st.loadError = (err && err.message) || "The set-up details could not be loaded."; }
  finally { if (uiState.setup === st) { st.loading = false; render(); } }
}

/** Load the organisation list the first time the switcher opens. `false` means it failed (the menu says so). */
function ensureOrgs() {
  if (uiState.orgList || uiState.orgLoading) return;
  uiState.orgLoading = true;
  api.myOrganisations().then((o) => { uiState.orgList = Array.isArray(o) ? o : false; }).catch(() => { uiState.orgList = false; }).finally(() => { uiState.orgLoading = false; render(); });
}

/**
 * Switch organisation. The server decides (it may demand two-step sign-in). On success the page is reloaded so that nothing from
 * the previous organisation can remain in memory: the session keeps its sign-in and now points at the new organisation.
 */
async function switchOrganisation(orgId) {
  uiState.switching = true; uiState.switchError = null; render();
  try {
    const { role } = await api.selectOrganisation(orgId);
    authStore.setOrganisation(orgId, role);
    window.location.hash = "#/";
    window.location.reload();
  } catch (err) {
    uiState.switching = false; uiState.switchError = (err && err.message) || "Could not open this organisation."; render();
  }
}

/** Read everything the home page shows, once per organisation and role. */
function loadHomeData(authState) {
  const key = `${authState.organisationId}|${authState.role}`;
  const home = uiState.home;
  if (home.key === key) return;
  home.key = key; home.loading = true; home.error = null; home.data = null;
  loadHome(api, authState.role, authState.organisationId)
    .then((data) => { if (uiState.home.key === key) uiState.home.data = data; })
    .catch((err) => { if (uiState.home.key === key) uiState.home.error = (err && err.message) || "The home page could not be loaded."; })
    .finally(() => { if (uiState.home.key === key) { uiState.home.loading = false; render(); } });
}

/** The sidebar entries this role may see, with only the most specific match marked active
 * (so "/passport/sharing" lights up Passport Sharing, not Financial Passport as well). */
function visibleNav(authState, path, ignoreWorkspaceChoice = false) {
  ensureEntityConfig(authState);
  const permitted = NAV_ITEMS.filter((item) => (item.anyOf ? item.anyOf.some((p) => allowed(authState.role, p)) : !item.permission || allowed(authState.role, item.permission)));
  // Menu only: hiding a workspace never grants or removes access, and an organisation that has not been set up sees everything.
  const items = ignoreWorkspaceChoice ? permitted : filterNavByWorkspaces(permitted, shownFor(uiState.entity, authState.organisationId));
  const matches = items.filter((i) => path === i.path || (i.path !== "/" && path.startsWith(i.path + "/")));
  const best = matches.reduce((a, b) => (!a || b.path.length > a.path.length ? b : a), null);
  return items.map((item) => ({ item, active: item === best }));
}

function renderPage(matched, authState) {
  const nav = (p) => router.navigate(p);

  // Section 12's explicit "not-found state" — an unmatched hash route
  // (including a bookmarked/typed URL for a path this app never
  // defined) gets its own clearly-labeled screen, never a silent
  // redirect to the Dashboard, which would misrepresent broken
  // navigation as if it had gone somewhere intentional.
  if (!matched) {
    return h(
      "div", { className: "empty-state card" },
      h("h3", {}, "Page not found"),
      h("p", {}, "There's no page at this address."),
      h("button", { className: "btn btn-primary", onClick: () => nav("/") }, "Go to Dashboard")
    );
  }

  const { route, params } = matched;
  const name = route.name;

  if (name === "dashboard") {
    loadDashboardData(authState);
    loadHomeData(authState);
    const aiOn = DK.dockAvailable(authState.role);
    return Home({
      user: authState.user, role: authState.role, orgLabel: orgName(uiState.orgList || (uiState.home.data && uiState.home.data.orgs), authState.organisationId),
      data: uiState.home.data, loading: uiState.home.loading, error: uiState.home.error, dashboardData: uiState.dashboardData,
      showLocked: uiState.showLocked, aiAvailable: DK.canAsk(authState.role) && aiOn, onNavigate: nav,
      onToggleLocked: () => { uiState.showLocked = !uiState.showLocked; render(); },
      onOpenAi: () => { dockState().open = true; render(); },
      onRetry: () => { uiState.home.key = ""; render(); },
    });
  }
  if (name === "audit") {
    once("auditRecentLoading", loadRecentJournals);
    return AuditWorkspace({
      recentJournals: uiState.journals, onOpenJournal: (id) => handleAuditSearch(id),
      searchQuery: uiState.auditQuery, journal: uiState.auditJournal, chainLinks: uiState.auditChain,
      error: uiState.auditError, onNavigate: nav, onSearch: handleAuditSearch,
    });
  }

  if (name.startsWith("accounting")) return renderAccounting(name, params, authState, nav);
  if (name.startsWith("evidence") && name !== "evidence-review") return renderEvidence(name, params, authState, nav);
  if (name.startsWith("reconciliation")) return renderReconciliation(name, params, authState, nav);
  if (name === "reporting") return renderReporting(authState, nav);
  if (name === "period-close") return renderPeriodClose(authState, nav);
  if (name.startsWith("compliance")) return renderCompliance(name, params, authState, nav);
  if (name === "admin") return renderAdmin(authState, nav);
  if (name === "setup") return renderSetupPage(authState);
  if (name === "entity-config") return renderEntityConfigPage(authState);
  if (name === "import") return renderImport(authState, nav);
  if (name === "ai") return renderAi(authState);
  if (name === "passport-sharing") return renderPassportSharing(authState, nav);
  if (name === "passport") return renderPassport(authState, nav);
  if (name === "standards") return renderStandards(authState);
  if (name === "standards-registry") return renderStandardsRegistryPage(authState);
  if (name === "agents") return renderAgentsPage(authState);
  if (name === "assurance") return renderAssurancePage(authState);
  if (name === "proof-links") return renderProofLinksPage(authState);
  if (name === "diagnostics") return renderDiagnostics(authState);
  if (name === "security") return renderSecurityPage(authState);
  if (name === "validation") return renderValidationPage(authState);
  if (name === "pilot") return renderPilotPage(authState);
  if (name === "network") return renderNetworkPage(authState);
  if (name === "proof") return renderProofPage(authState);
  if (name === "evidence-review") return renderEvidenceReviewPage(authState);
  if (name === "workspaces") return renderWorkspacesPage(authState, nav);
  if (name === "analysis") return renderAnalysisPage(authState);
  if (name === "tax") return renderTaxPage(authState);
  if (name === "forensic") return renderForensicPage(authState);
  if (name === "grc") return renderGrcPage(authState);
  if (name === "pubfin") return renderPubfinPage(authState);
  if (name === "bizdev") return renderBizdevPage(authState);
  if (name === "cyber") return renderCyberPage(authState);
  if (name === "treasury") return renderTreasuryPage(authState);
  if (name === "procurement") return renderProcurementPage(authState);
  if (name === "fpa") return renderFpaPage(authState);
  if (name === "fincrime") return renderFincrimePage(authState);
  if (name === "itaudit") return renderItAuditPage(authState);
  if (name === "resilience") return renderResiliencePage(authState);
  if (name === "aigov") return renderAigovPage(authState);
  if (name === "quality") return renderQualityPage(authState);
  if (name === "secretarial") return renderSecretarialPage(authState);
  if (name === "fixedassets") return renderFixedAssetsPage(authState);
  if (name === "inventory") return renderInventoryPage(authState);
  if (name === "investments") return renderInvestmentsPage(authState);
  if (name === "valuation") return renderValuationPage(authState);
  if (name === "insurance") return renderInsurancePage(authState);
  if (name === "esg") return renderEsgPage(authState);
  if (name === "payroll") return renderPayrollPage(authState);
  if (name === "health") return renderHealthPage(authState);

  return h("div", { className: "empty-state card" }, h("h3", {}, "Page not found"));
}

// ------------------------------------------------------------------
// Shared loading helper: fetch-once-per-render-cycle guard, matching
// loadDashboardData's own pattern below.
// ------------------------------------------------------------------
function once(flagKey, loader) {
  // The flag doubles as the page's `loading` prop, so it stays true until
  // the loader has fully finished. `loadedOnce` stops the re-render that
  // follows from starting the loader again (an endless reload loop that
  // used to keep pages on "Loading..." and collapse open dropdowns).
  if (uiState[flagKey] || loadedOnce.has(flagKey)) return;
  uiState[flagKey] = true;
  Promise.resolve()
    .then(() => loader())
    .catch(() => {})
    .finally(() => {
      uiState[flagKey] = false;
      loadedOnce.add(flagKey);
      render();
    });
}

function reload(flagKey) {
  loadedOnce.delete(flagKey);
  render();
}

async function loadDashboardData(authState) {
  if (uiState.dashboardData || uiState.dashboardLoading) return;
  uiState.dashboardLoading = true;
  try {
    const periods = await api.listPeriods();
    const currentPeriod = periods[periods.length - 1] || null;
    const trialBalance = currentPeriod ? await api.trialBalance(currentPeriod.id).catch(() => null) : null;
    let findingCounts = null;
    if (allowed(authState.role, PERMISSIONS.CONTROL_READ)) {
      const findings = await api.listFindings().catch(() => []);
      findingCounts = findings.reduce((acc, f) => ({ ...acc, [f.status]: (acc[f.status] || 0) + 1 }), {});
    }
    uiState.dashboardData = { trialBalance, currentPeriod, findingCounts };
  } catch {
    uiState.dashboardData = {};
  } finally {
    uiState.dashboardLoading = false;
    render();
  }
}

function clearAuthDraft() {
  uiState.auth = { draft: { email: "", password: "", confirm: "" }, fieldErrors: {}, notice: null };
}

function focusFirstError() {
  setTimeout(() => { const el = document.querySelector('#auth-screen [aria-invalid="true"], #recovery-screen [aria-invalid="true"]'); if (el) el.focus(); }, 0);
}

async function handleAuthSubmit({ email, password, confirm }) {
  if (uiState.loginPending) return;                       // a double click must not submit twice
  const registering = uiState.loginMode === "register";
  const cleanEmail = String(email || "").trim();
  Object.assign(uiState.auth.draft, { email: cleanEmail, password, confirm: confirm || "" });
  // Checked here first so the person gets field-level help at once; the server checks the same rules again.
  const v = registering ? validateSignup({ email: cleanEmail, password, confirm }) : validateLogin({ email: cleanEmail, password });
  uiState.auth.fieldErrors = v.errors;
  if (!v.ok) { uiState.loginError = null; render(); focusFirstError(); return; }
  uiState.auth.notice = null;
  uiState.loginPending = true;
  uiState.loginError = null;
  render();
  try {
    if (registering) {
      const created = await api.register(cleanEmail, password, confirm);
      // The account exists now. The server says truthfully whether the provider accepted the welcome email and the code.
      uiState.vf = newVerify(cleanEmail, (created && created.email_delivery) || {});
      uiState.loginMode = "verify"; uiState.auth.fieldErrors = {};
      if (uiState.vf.cooldownUntil > Date.now()) startVerifyTimer();
      setTimeout(() => { const el = document.getElementById("vf-code"); if (el) el.focus(); }, 0);
      return;
    }
    const result = interpretLogin(await api.login(cleanEmail, password));
    if (result.kind === "mfa") uiState.mfaChallenge = result.challenge;
    else if (result.kind === "done") { authStore.setSession(result.token, result.user); clearAuthDraft(); }
    else uiState.loginError = result.message;
  } catch (err) {
    uiState.loginError = err.message;
    if (!registering) uiState.auth.draft.password = "";   // a wrong password is not worth keeping; the email stays
  } finally {
    uiState.loginPending = false;
    render();
    if (uiState.loginError) setTimeout(() => { const el = document.getElementById(registering ? "email" : "password"); if (el && !registering) el.focus(); }, 0);
  }
}

// ---- email verification right after sign-up: confirm the address with the 6-digit code (real backend) ----
let vfTimer = null;
const newVerify = (email, d) => ({
  email, sent: !!d.sent, resent: false, code: "", pending: false, error: null, notice: null, fieldErrors: {}, verified: false, available: d.reason === "not_configured" ? false : null,
  cooldownUntil: Date.now() + (Number(d.cooldown_seconds) || 0) * 1000, expiresMinutes: Number(d.expires_in_minutes) || 10,
});

function stopVerifyTimer() { if (vfTimer) { clearInterval(vfTimer); vfTimer = null; } }
function startVerifyTimer() {
  stopVerifyTimer();
  vfTimer = setInterval(() => {
    const v = uiState.vf, btn = document.getElementById("vf-resend");
    if (!v || v.verified || !btn) { stopVerifyTimer(); return; }
    const left = secondsLeft(v.cooldownUntil);
    btn.textContent = left > 0 ? `Resend verification code (${left}s)` : "Resend verification code";
    btn.disabled = left > 0 || v.pending || v.available === false;
    if (left <= 0) stopVerifyTimer();
  }, 1000);
}

async function handleVerifyConfirm(code) {
  const v = uiState.vf;
  if (!v || v.pending) return;
  v.code = normaliseCode(code);
  const problem = codeProblem(v.code);
  if (problem) { v.fieldErrors = { code: problem }; v.error = null; render(); focusFirstError(); return; }
  v.fieldErrors = {}; v.error = null; v.notice = null; v.pending = true; render();
  try {
    await api.verificationConfirm(v.email, v.code);
    v.verified = true; v.code = ""; stopVerifyTimer();
  } catch (err) {
    v.error = rcMessage(err); v.code = "";
  } finally {
    v.pending = false; render();
    if (v.verified) focusHeading("#rc-title"); else setTimeout(() => { const el = document.getElementById("vf-code"); if (el) el.focus(); }, 0);
  }
}

async function handleVerifyResend() {
  const v = uiState.vf;
  if (!v || v.pending) return;
  v.error = null; v.notice = null; v.fieldErrors = {}; v.pending = true; render();
  try {
    const res = await api.verificationRequest(v.email);
    v.cooldownUntil = Date.now() + (Number(res && res.cooldown_seconds) || 60) * 1000;
    v.expiresMinutes = Number(res && res.expires_in_minutes) || v.expiresMinutes;
    v.notice = (res && res.message) || "If this email address can be verified, a new code is on its way.";
    v.code = ""; v.resent = true; startVerifyTimer();     // the server's own words (below) replace the first banner
  } catch (err) {
    v.error = rcMessage(err);
    if (err && err.status === 503) { v.available = false; v.error = null; v.sent = false; }
    if (err && err.status === 429 && /wait (\d+) seconds/i.test(err.message || "")) { v.cooldownUntil = Date.now() + Number(/wait (\d+) seconds/i.exec(err.message)[1]) * 1000; startVerifyTimer(); }
  } finally {
    v.pending = false; render();
  }
}

/** Signs the new person in with the password they just chose (held in memory only), whether or not they verified yet. */
async function handleVerifyContinue() {
  const v = uiState.vf;
  if (!v || v.pending) return;
  v.error = null; v.pending = true; render();
  try {
    const result = interpretLogin(await api.login(v.email, uiState.auth.draft.password));
    if (result.kind === "mfa") { uiState.mfaChallenge = result.challenge; uiState.loginMode = "login"; stopVerifyTimer(); uiState.vf = null; }
    else if (result.kind === "done") { stopVerifyTimer(); uiState.vf = null; uiState.loginMode = "login"; authStore.setSession(result.token, result.user); clearAuthDraft(); }
    else v.error = result.message;
  } catch (err) {
    v.error = err.message;
  } finally {
    if (uiState.vf) uiState.vf.pending = false;
    render();
  }
}

// ---- password recovery: request a code, verify it, choose a new password (real backend, one step at a time) ----
let rcTimer = null;
const newRecovery = (email) => ({ step: "request", email: email || "", code: "", resetToken: null, error: null, notice: null, fieldErrors: {}, pending: false, available: null, cooldownUntil: 0, expiresMinutes: 10, draft: { password: "", confirm: "" } });

function stopRecoveryTimer() { if (rcTimer) { clearInterval(rcTimer); rcTimer = null; } }
function startRecoveryTimer() {
  stopRecoveryTimer();
  rcTimer = setInterval(() => {
    const r = uiState.rc, btn = document.getElementById("rc-resend");
    if (!r || r.step !== "verify" || !btn) { stopRecoveryTimer(); return; }
    const left = secondsLeft(r.cooldownUntil);
    btn.textContent = left > 0 ? `Resend code (${left}s)` : "Resend code";
    btn.disabled = left > 0 || r.pending;
    if (left <= 0) stopRecoveryTimer();
  }, 1000);
}

function openRecovery() {
  uiState.loginMode = "recover"; uiState.loginError = null;
  uiState.rc = newRecovery(uiState.auth.draft.email);
  const r = uiState.rc;
  render(); focusHeading("#rc-title");
  api.recoveryStatus().then((s) => { r.available = !!(s && s.available); }).catch(() => { r.available = null; }).finally(() => { if (uiState.rc === r) render(); });
}

function leaveRecovery() {
  stopRecoveryTimer();
  const r = uiState.rc;
  const done = r && r.step === "done";
  uiState.loginMode = "login"; uiState.loginError = null; uiState.rc = null;
  uiState.auth.draft.password = ""; uiState.auth.draft.confirm = ""; uiState.auth.fieldErrors = {};
  uiState.auth.notice = done ? "Your password was reset. Sign in with your new password." : null;
  if (r && r.email) uiState.auth.draft.email = r.email;
  render();
  setTimeout(() => { const el = document.getElementById(done ? "password" : "email"); if (el) el.focus(); }, 0);
}

/** The server's own words for a refusal, including a 503 (which the generic client message would hide). */
const rcMessage = (err) => (err && err.status === 503 && err.body && (err.body.detail || err.body.message) ? (err.body.detail || err.body.message) : (err && err.message) || "Something went wrong. Please try again.");

async function handleRecoveryRequest(email, isResend = false) {
  const r = uiState.rc;
  if (!r || r.pending) return;
  const e = String(email || "").trim();
  r.email = e;
  const problem = emailProblem(e);
  if (problem) { r.fieldErrors = { email: problem }; r.error = null; render(); focusFirstError(); return; }
  r.fieldErrors = {}; r.error = null; r.notice = null; r.pending = true; render();
  try {
    const res = await api.recoveryRequest(e);
    r.cooldownUntil = Date.now() + (Number(res && res.cooldown_seconds) || 60) * 1000;
    r.expiresMinutes = Number(res && res.expires_in_minutes) || 10;
    r.step = "verify"; r.code = "";
    if (isResend) r.notice = "If this email can be recovered, a new code is on its way. Any earlier code no longer works.";
    startRecoveryTimer();
  } catch (err) {
    if (err && err.status === 503) { r.available = false; r.error = null; } // the "not set up" box already says it; never show it twice
    else r.error = rcMessage(err);
    if (err && err.status === 429 && /wait (\d+) seconds/i.test(err.message || "")) { r.cooldownUntil = Date.now() + Number(/wait (\d+) seconds/i.exec(err.message)[1]) * 1000; if (r.step === "verify") startRecoveryTimer(); }
  } finally {
    r.pending = false; render(); focusHeading("#rc-title");
  }
}

async function handleRecoveryVerify(code) {
  const r = uiState.rc;
  if (!r || r.pending) return;
  r.code = normaliseCode(code);
  const problem = codeProblem(r.code);
  if (problem) { r.fieldErrors = { code: problem }; r.error = null; render(); focusFirstError(); return; }
  r.fieldErrors = {}; r.error = null; r.notice = null; r.pending = true; render();
  try {
    const res = await api.recoveryVerify(r.email, r.code);
    r.resetToken = res.reset_token; r.step = "reset"; r.code = "";   // the token stays in memory only: never in the URL, storage or logs
    stopRecoveryTimer();
  } catch (err) {
    r.error = rcMessage(err); r.code = "";
  } finally {
    r.pending = false; render();
    if (r.step === "reset") focusHeading("#rc-title"); else setTimeout(() => { const el = document.getElementById("rc-code"); if (el) el.focus(); }, 0);
  }
}

async function handleRecoveryReset({ password, confirm }) {
  const r = uiState.rc;
  if (!r || r.pending) return;
  Object.assign(r.draft, { password, confirm });
  const v = validateNewPassword({ password, confirm });
  r.fieldErrors = v.errors; r.error = null;
  if (!v.ok) { render(); focusFirstError(); return; }
  r.pending = true; render();
  try {
    await api.recoveryReset(r.email, r.resetToken, password, confirm);
    r.step = "done"; r.resetToken = null; r.draft = { password: "", confirm: "" };   // nothing of the new password is kept
  } catch (err) {
    r.error = rcMessage(err);
    if (/expired|already used|start again/i.test(err.message || "")) { r.step = "request"; r.resetToken = null; r.draft = { password: "", confirm: "" }; }
  } finally {
    r.pending = false; render();
    if (r.step !== "reset") focusHeading("#rc-title");
  }
}

async function handleMfaSubmit({ code }) {
  uiState.loginPending = true;
  uiState.loginError = null;
  render();
  try {
    const result = interpretLogin(await api.verifyMfa(uiState.mfaChallenge, code));
    if (result.kind === "done") {
      uiState.mfaChallenge = null;
      authStore.setSession(result.token, result.user);
    } else {
      uiState.loginError = result.message || "That code was not accepted.";
    }
  } catch (err) {
    uiState.loginError = err.message;
    // an expired sign-in cannot be retried with the same challenge: go back to the password step
    if (/expired|start again/i.test(err.message || "")) uiState.mfaChallenge = null;
  } finally {
    uiState.loginPending = false;
    render();
  }
}

// ---- single sign-on: leave for the identity provider, and come back with ?code&state ----
const SSO_BINDING_KEY = "asavexa.sso.binding";

async function loadSsoConfig() {
  try {
    uiState.ssoConfig = await api.oidcConfig();
  } catch {
    uiState.ssoConfig = { enabled: false };
  }
  render();
}

async function handleSsoStart() {
  uiState.loginPending = true; uiState.loginError = null; render();
  try {
    const binding = makeBinding();
    sessionStorage.setItem(SSO_BINDING_KEY, binding);
    const { url } = await api.oidcStart(binding);
    window.location.assign(url);
    return;
  } catch (err) {
    uiState.loginError = err.message;
  }
  uiState.loginPending = false;
  render();
}

async function handleSsoReturn() {
  const ret = parseOidcReturn(window.location.search);
  if (!ret) return;
  uiState.enteredAuth = true;   // coming back from single sign-on: show the sign-in screen (with any error), not the front page
  const binding = sessionStorage.getItem(SSO_BINDING_KEY);
  sessionStorage.removeItem(SSO_BINDING_KEY);
  window.history.replaceState({}, "", window.location.pathname + window.location.hash);   // never leave the one-time code in the address bar
  if (ret.error) { uiState.loginError = `Single sign-on was not completed: ${ret.error}`; return; }
  uiState.loginPending = true; render();
  try {
    const result = interpretLogin(await api.oidcCallback(ret.code, ret.state, binding || ""));
    if (result.kind === "mfa") uiState.mfaChallenge = result.challenge;
    else if (result.kind === "done") authStore.setSession(result.token, result.user);
    else uiState.loginError = result.message;
  } catch (err) {
    uiState.loginError = err.message;
  } finally {
    uiState.loginPending = false;
    render();
  }
}

function resetSecurityState() {
  uiState.val = null; loadedOnce.delete("valLoading");
  uiState.pilot = null; loadedOnce.delete("pilotLoading");
  uiState.net = null; loadedOnce.delete("netLoading");
  uiState.proof = null; loadedOnce.delete("proofLoading"); uiState.er = null; loadedOnce.delete("erLoading"); uiState.sr = null; loadedOnce.delete("srLoading"); uiState.ag = null; loadedOnce.delete("agLoading"); uiState.as = null; loadedOnce.delete("asLoading"); uiState.pl = null; loadedOnce.delete("plLoading"); uiState.entity = null; uiState.ec = null; loadedOnce.delete("ecLoading"); uiState.tr = null; loadedOnce.delete("trLoading"); uiState.pc = null; loadedOnce.delete("pcLoading"); uiState.fp = null; loadedOnce.delete("fpLoading"); uiState.fx = null; loadedOnce.delete("fxLoading"); uiState.ia = null; loadedOnce.delete("iaLoading"); uiState.rs = null; loadedOnce.delete("rsLoading"); uiState.gv = null; loadedOnce.delete("gvLoading"); uiState.ql = null; loadedOnce.delete("qlLoading"); uiState.cs = null; loadedOnce.delete("csLoading"); uiState.fa = null; loadedOnce.delete("faLoading"); uiState.iv = null; loadedOnce.delete("ivLoading"); uiState.im = null; loadedOnce.delete("imLoading"); uiState.vl = null; loadedOnce.delete("vlLoading"); uiState.ic = null; loadedOnce.delete("icLoading"); uiState.es = null; loadedOnce.delete("esLoading"); uiState.pw = null; loadedOnce.delete("pwLoading");
  uiState.ws = null; loadedOnce.delete("wsLoading");
  uiState.an = null; loadedOnce.delete("anLoading");
  uiState.tx = null; loadedOnce.delete("txLoading");
  uiState.fm = null; loadedOnce.delete("fmLoading");
  uiState.gc = null; loadedOnce.delete("gcLoading");
  uiState.pf = null; loadedOnce.delete("pfLoading");
  uiState.bd = null; loadedOnce.delete("bdLoading");
  uiState.cy = null; loadedOnce.delete("cyLoading");
  uiState.hc = null; loadedOnce.delete("hcLoading");
  uiState.dock = null;
  uiState.sec = null; uiState.secNoOrg = false; uiState.mfaChallenge = null;
  loadedOnce.delete("secLoading");
}

function handleLogout() {
  api.logout().finally(() => {
    authStore.clear();
    resetSecurityState();
    clearAuthDraft(); uiState.rc = null; uiState.vf = null; stopVerifyTimer(); uiState.loginMode = "login";
    uiState.enteredAuth = false; uiState.landingMenu = false;
    render();
    // Nothing from this session may stay in memory for the next person on this tab.
    if (typeof window !== "undefined" && window.location && typeof window.location.reload === "function") { window.location.hash = "#/"; window.location.reload(); }
  });
}

/**
 * Shared chain-loading logic — the exact same 1-2-3-4 sequence
 * AuditWorkspace's own docstring describes (GET journal -> evidence
 * status -> evidence detail -> journal audit-trail), now used by both
 * the Audit Workspace search box (handleAuditSearch) and the new
 * Phase 1 "Show me the evidence" / "Why is this number here?" entry
 * points (openDrilldown) below, instead of being duplicated.
 */
async function loadChainForJournal(journalId) {
  const journal = await api.getJournal(journalId);
  const auditEvents = await api.journalAuditTrail(journalId).catch(() => []);
  let evidence = null;
  const status = await api.evidenceStatus(journalId).catch(() => null);
  if (status && status.evidence_id) {
    evidence = await api.getEvidence(status.evidence_id).catch(() => null);
  }
  const chain = buildChainLinks({ journal, evidence, auditEvents });
  return { journal, chain, auditEvents, evidence };
}

async function loadRecentJournals() {
  uiState.journals = await api.listJournals().catch(() => uiState.journals || []);
}

async function handleAuditSearch(rawQuery) {
  const query = (rawQuery || "").trim();
  uiState.auditQuery = query;
  if (!UUID_RE.test(query)) {
    uiState.auditError = "Enter a journal's ID — a long code like 3f2c9a1e-…, shown on the journal's page. Or pick an entry from the list below.";
    uiState.auditJournal = null;
    uiState.auditChain = null;
    render();
    return;
  }
  uiState.auditError = null;
  uiState.auditJournal = null;
  uiState.auditChain = null;
  render();
  try {
    const { journal, chain } = await loadChainForJournal(query);
    uiState.auditJournal = journal;
    uiState.auditChain = chain;
  } catch (err) {
    uiState.auditError = err.message || "Could not find that journal.";
  } finally {
    render();
  }
}

// ==================================================================
// Drilldown panel — Phase 1's "Why is this number here?" /
// "Show me the evidence" (global: can be opened from any page that
// shows a journal-backed number, not just Audit Workspace).
// ==================================================================
async function openDrilldown(journalId, { accountId, periodId } = {}) {
  uiState.drilldownOpen = true;
  uiState.drilldownLoading = true;
  uiState.drilldownError = null;
  uiState.drilldownNote = null;
  uiState.drilldownJournal = null;
  uiState.drilldownChain = null;
  uiState.drilldownAuditEvents = null;
  uiState.drilldownEvidence = null;
  uiState.drilldownCompleteness = null;
  uiState.drilldownReconciliation = null;
  render();
  try {
    const { journal, chain, auditEvents, evidence } = await loadChainForJournal(journalId);
    uiState.drilldownJournal = journal;
    uiState.drilldownChain = chain;
    uiState.drilldownAuditEvents = auditEvents;
    uiState.drilldownEvidence = evidence;
    // Best-effort context enrichment — only possible when the caller
    // knows which account this number belongs to (the Trace tab
    // always does; General Ledger does only when one specific account
    // is selected). Never blocks showing the chain itself if it fails
    // or isn't applicable.
    if (accountId) {
      uiState.drilldownCompleteness = await api.evidenceCompleteness(accountId, periodId || undefined).catch(() => null);
      const recon = await api.reconciliationSummary(accountId).catch(() => null);
      // An account that isn't actually a reconciled bank account still
      // returns a summary with every count at zero — showing that
      // would falsely imply "this account is reconciled and clean"
      // rather than "reconciliation doesn't apply here". Only surface
      // it when there is real reconciliation activity for this id.
      uiState.drilldownReconciliation =
        recon && (recon.reconciled_count || recon.outstanding_count || recon.exception_count) ? recon : null;
    }
  } catch (err) {
    uiState.drilldownError = err.message || "Could not load this entry.";
  } finally {
    uiState.drilldownLoading = false;
    render();
  }
}

function closeDrilldown() {
  uiState.drilldownOpen = false;
  render();
}

function handleShowEvidence() {
  if (uiState.drilldownEvidence) {
    const evidenceId = uiState.drilldownEvidence.id;
    closeDrilldown();
    router.navigate(`/evidence/${evidenceId}`);
  } else {
    uiState.drilldownNote = "No evidence is linked to this entry yet — upload one from the Evidence page.";
    render();
  }
}

// ==================================================================
// Accounting
// ==================================================================
function renderAccounting(name, params, authState, nav) {
  if (name === "accounting-journal-new") {
    once("accountingLoading", loadAccountsAndPeriods);
    return Accounting({
      role: authState.role, view: "journal-new", accounts: uiState.accounts,
      form: uiState.journalForm, formError: uiState.journalFormError, formPending: uiState.journalFormPending,
      onNavigate: nav,
      onJournalFieldChange: handleJournalFieldChange, onAddJournalLine: handleAddJournalLine,
      onRemoveJournalLine: handleRemoveJournalLine, onSubmitJournal: () => handleSubmitJournal(nav),
    });
  }
  if (name === "accounting-journal-detail") {
    if (uiState.journalRequestedId !== params.id) {
      uiState.journalRequestedId = params.id;
      loadJournalDetail(params.id);
    }
    return Accounting({
      role: authState.role, view: "journal-detail", loading: uiState.journalLoading, journalError: uiState.journalError,
      journal: uiState.journal, onNavigate: nav, onRetry: () => loadJournalDetail(params.id),
      onPostJournal: (id) => handlePostJournal(id), onReverseJournal: (id) => handleReverseJournal(id),
      onLoadJournalAuditTrail: (id) => handleLoadJournalAuditTrail(id), journalAuditEvents: uiState.journalAuditEvents,
    });
  }
  once("accountingLoading", loadAccountsAndPeriods);
  return Accounting({
    role: authState.role, view: "overview", loading: uiState.accountingLoading, error: uiState.accountingError,
    accounts: uiState.accounts, periods: uiState.periods, journals: uiState.journals, onNavigate: nav, onRetry: () => reload("accountingLoading"),
    accountForm: uiState.accountForm, accountFormError: uiState.accountFormError, accountFormPending: uiState.accountFormPending,
    onAccountFieldChange: (f, v) => { uiState.accountForm = { ...uiState.accountForm, [f]: v }; render(); },
    onSubmitAccount: handleSubmitAccount,
    periodForm: uiState.periodForm, periodFormError: uiState.periodFormError, periodFormPending: uiState.periodFormPending,
    onPeriodFieldChange: (f, v) => { uiState.periodForm = { ...uiState.periodForm, [f]: v }; render(); },
    onSubmitPeriod: handleSubmitPeriod, onLockPeriod: handleLockPeriod,
  });
}

async function loadAccountsAndPeriods() {
  uiState.accountingError = null;
  try {
    uiState.accounts = await api.listAccounts();
    uiState.periods = await api.listPeriods();
    uiState.journals = await api.listJournals().catch(() => []);
  } catch (err) {
    uiState.accountingError = err.message || "Could not load accounting data.";
  } finally {
    render();
  }
}

async function handleSubmitAccount() {
  uiState.accountFormPending = true;
  uiState.accountFormError = null;
  render();
  try {
    await api.createAccount(uiState.accountForm);
    uiState.accountForm = { code: "", name: "", type: "ASSET", currency: "USD" };
    uiState.accounts = await api.listAccounts();
  } catch (err) {
    uiState.accountFormError = err.message;
  } finally {
    uiState.accountFormPending = false;
    render();
  }
}

async function handleSubmitPeriod() {
  uiState.periodFormPending = true;
  uiState.periodFormError = null;
  render();
  try {
    await api.openPeriod(uiState.periodForm);
    uiState.periodForm = { name: "", start_date: "", end_date: "" };
    uiState.periods = await api.listPeriods();
  } catch (err) {
    uiState.periodFormError = err.message;
  } finally {
    uiState.periodFormPending = false;
    render();
  }
}

async function handleLockPeriod(periodId) {
  const reason = window.prompt("Reason for locking this period:");
  if (!reason) return;
  try {
    await api.lockPeriod(periodId, reason);
    uiState.periods = await api.listPeriods();
  } catch (err) {
    uiState.accountingError = err.message;
  } finally {
    render();
  }
}

function handleJournalFieldChange(path, value) {
  if (path.startsWith("lines.")) {
    const [, idxStr, field] = path.split(".");
    const idx = Number(idxStr);
    const lines = uiState.journalForm.lines.slice();
    lines[idx] = { ...lines[idx], [field]: value };
    uiState.journalForm = { ...uiState.journalForm, lines };
  } else {
    uiState.journalForm = { ...uiState.journalForm, [path]: value };
  }
  render();
}

function handleAddJournalLine() {
  uiState.journalForm = { ...uiState.journalForm, lines: [...uiState.journalForm.lines, {}] };
  render();
}

function handleRemoveJournalLine(i) {
  const lines = uiState.journalForm.lines.slice();
  lines.splice(i, 1);
  uiState.journalForm = { ...uiState.journalForm, lines };
  render();
}

async function handleSubmitJournal(nav) {
  uiState.journalFormPending = true;
  uiState.journalFormError = null;
  render();
  try {
    const body = {
      date: uiState.journalForm.date,
      description: uiState.journalForm.description,
      currency: uiState.journalForm.currency || "USD",
      transaction_ref: uiState.journalForm.transaction_ref || null,
      evidence_ref: uiState.journalForm.evidence_ref || null,
      lines: uiState.journalForm.lines.map((l) => ({
        account_id: l.account_id,
        debit_amount: l.debit_amount || "0.00",
        credit_amount: l.credit_amount || "0.00",
        description: l.description || "",
      })),
    };
    const journal = await api.createDraftJournal(body);
    uiState.journalForm = { date: "", description: "", currency: "USD", lines: [{}, {}] };
    nav(`/accounting/journals/${journal.id}`);
  } catch (err) {
    uiState.journalFormError = err.message;
  } finally {
    uiState.journalFormPending = false;
    render();
  }
}

async function loadJournalDetail(id) {
  uiState.journalLoading = true;
  uiState.journalError = null;
  uiState.journal = null;
  uiState.journalAuditEvents = null;
  render();
  try {
    uiState.journal = await api.getJournal(id);
  } catch (err) {
    uiState.journalError = err.message || "Journal not found.";
  } finally {
    uiState.journalLoading = false;
    render();
  }
}

async function handlePostJournal(id) {
  try {
    uiState.journal = await api.postJournal(id);
  } catch (err) {
    uiState.journalError = err.message;
  } finally {
    render();
  }
}

async function handleReverseJournal(id) {
  const reason = window.prompt("Reason for reversing this journal:");
  if (!reason) return;
  try {
    await api.reverseJournal(id, reason);
    uiState.journal = await api.getJournal(id);
  } catch (err) {
    uiState.journalError = err.message;
  } finally {
    render();
  }
}

async function handleLoadJournalAuditTrail(id) {
  try {
    uiState.journalAuditEvents = await api.journalAuditTrail(id);
  } catch {
    uiState.journalAuditEvents = [];
  } finally {
    render();
  }
}

// ==================================================================
// Evidence
// ==================================================================
function renderEvidence(name, params, authState, nav) {
  if (name === "evidence-detail") {
    if (uiState.evidenceDetailRequestedId !== params.id) {
      uiState.evidenceDetailRequestedId = params.id;
      loadEvidenceDetail(params.id);
    }
    return Evidence({
      role: authState.role, view: "detail", loading: uiState.evidenceDetailLoading, detailError: uiState.evidenceDetailError,
      detail: uiState.evidenceDetail, onNavigate: nav, onRetry: () => loadEvidenceDetail(params.id),
      onVerify: handleVerifyEvidence, onReject: handleRejectEvidence,
      storage: uiState.evidenceStorage, onDownload: handleDownloadEvidence, downloadError: uiState.evidenceDownloadError, downloading: uiState.evidenceDownloading,
      rejectReason: uiState.evidenceRejectReason, onRejectReasonChange: (v) => { uiState.evidenceRejectReason = v; render(); },
    });
  }
  once("evidenceLoading", loadEvidenceList);
  return Evidence({
    role: authState.role, view: "list", loading: uiState.evidenceLoading, error: uiState.evidenceError,
    items: uiState.evidenceItems, onNavigate: nav, onRetry: () => reload("evidenceLoading"),
    filterStatus: uiState.evidenceFilterStatus, filterType: uiState.evidenceFilterType,
    onFilterChange: (field, value) => {
      if (field === "status") uiState.evidenceFilterStatus = value; else uiState.evidenceFilterType = value;
      render();
    },
    uploadFile: uiState.evidenceUploadFile,
    uploadForm: uiState.evidenceUploadForm, uploadError: uiState.evidenceUploadError, uploadPending: uiState.evidenceUploadPending,
    onUploadFieldChange: (f, v) => { uiState.evidenceUploadForm = { ...uiState.evidenceUploadForm, [f]: v }; render(); },
    onFileSelected: (file) => { uiState.evidenceUploadFile = file; render(); },
    onSubmitUpload: handleSubmitEvidenceUpload,
  });
}

async function loadEvidenceList() {
  uiState.evidenceLoading = true;
  uiState.evidenceError = null;
  render();
  try {
    uiState.evidenceItems = await api.listEvidence();
  } catch (err) {
    uiState.evidenceError = err.message || "Could not load evidence.";
  } finally {
    uiState.evidenceLoading = false;
    render();
  }
}

async function handleSubmitEvidenceUpload() {
  if (!uiState.evidenceUploadFile) {
    uiState.evidenceUploadError = "Select a file first.";
    render();
    return;
  }
  const linked = (uiState.evidenceUploadForm.linkedJournalId || "").trim();
  if (linked && !UUID_RE.test(linked)) {
    uiState.evidenceUploadError = "The linked journal ID must be a journal's ID (a long code like 3f2c9a1e-…). Copy it from the journal's page, or leave it blank.";
    render();
    return;
  }
  uiState.evidenceUploadPending = true;
  uiState.evidenceUploadError = null;
  render();
  try {
    await api.uploadEvidence({
      file: uiState.evidenceUploadFile,
      type: uiState.evidenceUploadForm.type || "OTHER",
      linkedJournalId: linked || undefined,
      linkedTransactionRef: uiState.evidenceUploadForm.linkedTransactionRef,
    });
    uiState.evidenceUploadForm = { type: "INVOICE" };
    uiState.evidenceUploadFile = null;
    await loadEvidenceList();
  } catch (err) {
    uiState.evidenceUploadError = err.message;
  } finally {
    uiState.evidenceUploadPending = false;
    render();
  }
}

async function handleDownloadEvidence(id) {
  uiState.evidenceDownloading = true; uiState.evidenceDownloadError = null; render();
  try {
    const { blob, filename } = await api.downloadEvidence(id);
    saveBlob(blob, filename);
  } catch (err) {
    uiState.evidenceDownloadError = err.message || "Could not download the file.";
  } finally {
    uiState.evidenceDownloading = false;
    render();
  }
}

async function loadEvidenceDetail(id) {
  uiState.evidenceDetailLoading = true;
  uiState.evidenceDetailError = null;
  uiState.evidenceDetail = null;
  render();
  try {
    uiState.evidenceDetail = await api.getEvidence(id);
    uiState.evidenceStorage = await api.evidenceStorage(id).catch(() => null);
    uiState.evidenceDownloadError = null;
  } catch (err) {
    uiState.evidenceDetailError = err.message || "Evidence not found.";
  } finally {
    uiState.evidenceDetailLoading = false;
    render();
  }
}

async function handleVerifyEvidence(id) {
  try {
    uiState.evidenceDetail = await api.verifyEvidence(id);
  } catch (err) {
    uiState.evidenceDetailError = err.message;
  } finally {
    render();
  }
}

async function handleRejectEvidence(id) {
  try {
    uiState.evidenceDetail = await api.rejectEvidence(id, uiState.evidenceRejectReason);
    uiState.evidenceRejectReason = "";
  } catch (err) {
    uiState.evidenceDetailError = err.message;
  } finally {
    render();
  }
}

// ==================================================================
// Reconciliation
// ==================================================================
function renderReconciliation(name, params, authState, nav) {
  if (name === "reconciliation-new") {
    once("accountingLoading", loadAccountsAndPeriods);
    return Reconciliation({
      role: authState.role, view: "new", form: uiState.reconciliationForm,
      accounts: uiState.accounts, accountsLoading: uiState.accountingLoading,
      formError: uiState.reconciliationFormError, formPending: uiState.reconciliationFormPending,
      onFieldChange: (f, v) => { uiState.reconciliationForm = { ...uiState.reconciliationForm, [f]: v }; render(); },
      onSubmitCreate: () => handleSubmitReconciliation(nav), onNavigate: nav,
    });
  }
  if (name === "reconciliation-detail") {
    if (uiState.reconciliationDetailRequestedId !== params.id) {
      uiState.reconciliationDetailRequestedId = params.id;
      loadReconciliationDetail(params.id);
    }
    return Reconciliation({
      role: authState.role, view: "detail", loading: uiState.reconciliationDetailLoading, detailError: uiState.reconciliationDetailError,
      detail: uiState.reconciliationDetail, transactions: uiState.reconciliationTransactions,
      onNavigate: nav, onRetry: () => loadReconciliationDetail(params.id),
      onSubmitReconciliation: (id) => runAndReloadReconciliation(id, () => api.submitReconciliation(id)),
      onApproveReconciliation: (id) => runAndReloadReconciliation(id, () => api.approveReconciliation(id)),
      onRejectReconciliation: (id) => runAndReloadReconciliation(id, () => api.rejectReconciliation(id, uiState.reconciliationRejectReason)),
      rejectReason: uiState.reconciliationRejectReason, onRejectReasonChange: (v) => { uiState.reconciliationRejectReason = v; render(); },
      onManualMatch: (txnId) => runAndReloadReconciliation(params.id, () => api.manualMatch(txnId, uiState.matchJournalIds[txnId])),
      matchJournalId: uiState.matchJournalIds, onMatchJournalIdChange: (txnId, v) => { uiState.matchJournalIds = { ...uiState.matchJournalIds, [txnId]: v }; render(); },
      onApproveTransaction: (txnId) => runAndReloadReconciliation(params.id, () => api.approveTransaction(txnId)),
      onRejectMatch: (txnId) => runAndReloadReconciliation(params.id, () => api.rejectMatch(txnId, uiState.matchRejectReasons[txnId])),
      matchRejectReason: uiState.matchRejectReasons, onMatchRejectReasonChange: (txnId, v) => { uiState.matchRejectReasons = { ...uiState.matchRejectReasons, [txnId]: v }; render(); },
    });
  }
  once("reconciliationLoading", loadReconciliations);
  return Reconciliation({
    role: authState.role, view: "list", loading: uiState.reconciliationLoading, error: uiState.reconciliationError,
    reconciliations: uiState.reconciliations, onNavigate: nav, onRetry: () => reload("reconciliationLoading"),
  });
}

async function loadReconciliations() {
  uiState.reconciliationError = null;
  try {
    uiState.reconciliations = await api.listReconciliations();
  } catch (err) {
    uiState.reconciliationError = err.message || "Could not load reconciliations.";
  } finally {
    render();
  }
}

async function handleSubmitReconciliation(nav) {
  uiState.reconciliationFormPending = true;
  uiState.reconciliationFormError = null;
  render();
  try {
    const bankAccount = (uiState.accounts || []).find((a) => a.id === uiState.reconciliationForm.bank_account_id);
    const r = await api.createReconciliation({
      ...uiState.reconciliationForm,
      currency: (bankAccount && bankAccount.currency) || "USD",
    });
    uiState.reconciliationForm = {};
    nav(`/reconciliation/${r.id}`);
  } catch (err) {
    uiState.reconciliationFormError = err.message;
  } finally {
    uiState.reconciliationFormPending = false;
    render();
  }
}

async function loadReconciliationDetail(id) {
  uiState.reconciliationDetailLoading = true;
  uiState.reconciliationDetailError = null;
  uiState.reconciliationDetail = null;
  uiState.reconciliationTransactions = null;
  render();
  try {
    uiState.reconciliationDetail = await api.getReconciliation(id);
    uiState.reconciliationTransactions = await api.listReconciliationTransactions(id);
  } catch (err) {
    uiState.reconciliationDetailError = err.message || "Reconciliation not found.";
  } finally {
    uiState.reconciliationDetailLoading = false;
    render();
  }
}

async function runAndReloadReconciliation(id, action) {
  try {
    await action();
    uiState.reconciliationDetail = await api.getReconciliation(id);
    uiState.reconciliationTransactions = await api.listReconciliationTransactions(id);
    uiState.reconciliationRejectReason = "";
  } catch (err) {
    uiState.reconciliationDetailError = err.message;
  } finally {
    render();
  }
}

// ==================================================================
// Reporting
// ==================================================================
function renderReporting(authState, nav) {
  once("reportingPrereqLoading", loadReportingPrereqs);
  return Reporting({
    role: authState.role, reportType: uiState.reportType, periods: uiState.periods, accounts: uiState.accounts,
    selectedPeriodId: uiState.selectedPeriodId, selectedAccountId: uiState.selectedAccountId,
    loading: uiState.reportingLoading, error: uiState.reportingError, result: uiState.reportResult, traceResult: uiState.traceResult,
    completeness: uiState.traceCompleteness, reconciliationStatus: uiState.traceReconciliation,
    onSelectReportType: (t) => {
      uiState.reportType = t; uiState.reportResult = null; uiState.traceResult = null;
      uiState.traceCompleteness = null; uiState.traceReconciliation = null; render();
    },
    onSelectPeriod: (id) => { uiState.selectedPeriodId = id; render(); },
    onSelectAccount: (id) => { uiState.selectedAccountId = id; render(); },
    onGenerate: () => handleGenerateReport(),
    onRetry: () => handleGenerateReport(),
    onDrillAccount: (accountId) => handleDrillAccount(accountId),
    onOpenDrilldown: (journalId) => openDrilldown(journalId, {
      accountId: uiState.selectedAccountId, periodId: uiState.selectedPeriodId,
    }),
  });
}

/** A statement line's "account" row has no journal to open directly
 * (a trial balance line is a SUM across many journals) — so clicking
 * it switches to the Trace tab for that exact account + the period
 * already selected, which is where the individual journals/evidence
 * live. This IS the "statement line drill-down" / "account
 * drill-down" from Phase 1: trace_line's own docstring calls itself
 * "the exact posted ledger entries... behind one account's balance". */
function handleDrillAccount(accountId) {
  uiState.reportType = "trace";
  uiState.selectedAccountId = accountId;
  uiState.traceResult = null;
  uiState.traceCompleteness = null;
  uiState.traceReconciliation = null;
  render();
  handleGenerateReport();
}

async function loadReportingPrereqs() {
  try {
    uiState.periods = await api.listPeriods();
    uiState.accounts = await api.listAccounts();
  } catch (err) {
    uiState.reportingError = err.message;
  } finally {
    render();
  }
}

async function handleGenerateReport() {
  uiState.reportingLoading = true;
  uiState.reportingError = null;
  render();
  try {
    if (uiState.reportType === "trial-balance") uiState.reportResult = await api.trialBalance(uiState.selectedPeriodId);
    else if (uiState.reportType === "income-statement") uiState.reportResult = await api.incomeStatement(uiState.selectedPeriodId);
    else if (uiState.reportType === "balance-sheet") uiState.reportResult = await api.balanceSheet(uiState.selectedPeriodId);
    else if (uiState.reportType === "general-ledger") uiState.reportResult = await api.generalLedger(uiState.selectedPeriodId, uiState.selectedAccountId || undefined);
    else if (uiState.reportType === "trace") {
      uiState.traceResult = await api.traceLine(uiState.selectedAccountId, uiState.selectedPeriodId);
      uiState.traceCompleteness = await api
        .evidenceCompleteness(uiState.selectedAccountId, uiState.selectedPeriodId || undefined)
        .catch(() => null);
      const recon = await api.reconciliationSummary(uiState.selectedAccountId).catch(() => null);
      // See openDrilldown's identical comment above on why an
      // all-zero summary is treated as "not applicable" rather than
      // "clean" — this account may simply not be a reconciled bank
      // account at all.
      uiState.traceReconciliation =
        recon && (recon.reconciled_count || recon.outstanding_count || recon.exception_count) ? recon : null;
    }
  } catch (err) {
    uiState.reportingError = err.message || "Could not generate report.";
  } finally {
    uiState.reportingLoading = false;
    render();
  }
}

// ==================================================================
// Period Close
// ==================================================================
function renderPeriodClose(authState, nav) {
  once("periodCloseLoading", loadPeriodClosePeriods);
  return PeriodClose({
    role: authState.role, periods: uiState.periods, selectedPeriodId: uiState.selectedClosePeriodId,
    onSelectPeriod: (id) => { uiState.selectedClosePeriodId = id; uiState.periodCloseError = null; uiState.closeReadiness = null; uiState.activeCloseProcess = null; uiState.closeProcesses = null; loadPeriodCloseState(id); },
    loading: uiState.periodCloseWorking, error: uiState.periodCloseError,
    readiness: uiState.closeReadiness, activeProcess: uiState.activeCloseProcess, processes: uiState.closeProcesses,
    onCheckReadiness: () => handleCheckReadiness(),
    onRequestClose: () => handleRequestClose(),
    onRecheck: (id) => handlePeriodCloseAction(() => api.recheckCloseControls(id)),
    onReview: (id) => handlePeriodCloseAction(() => api.reviewClose(id)),
    onApprove: (id) => handlePeriodCloseAction(() => api.approveClose(id, uiState.approveReason || undefined)),
    onReject: (id) => handlePeriodCloseAction(() => api.rejectClose(id, uiState.periodCloseRejectReason)),
    approveReason: uiState.approveReason, onApproveReasonChange: (v) => { uiState.approveReason = v; render(); },
    rejectReason: uiState.periodCloseRejectReason, onRejectReasonChange: (v) => { uiState.periodCloseRejectReason = v; render(); },
    onRetry: () => loadPeriodCloseState(uiState.selectedClosePeriodId),
  });
}

async function loadPeriodClosePeriods() {
  try {
    uiState.periods = await api.listPeriods();
  } catch (err) {
    uiState.periodCloseError = err.message;
  } finally {
    render();
  }
}

async function loadPeriodCloseState(periodId) {
  if (!periodId) return;
  uiState.periodCloseWorking = true;
  uiState.periodCloseError = null;
  render();
  try {
    uiState.activeCloseProcess = await api.activeCloseProcess(periodId).catch(() => null);
    uiState.closeProcesses = await api.listCloseProcesses(periodId).catch(() => []);
  } catch (err) {
    uiState.periodCloseError = err.message;
  } finally {
    uiState.periodCloseWorking = false;
    render();
  }
}

async function handleCheckReadiness() {
  if (!uiState.selectedClosePeriodId) return;
  uiState.periodCloseError = null;
  uiState.periodCloseWorking = true;
  render();
  try {
    uiState.closeReadiness = await api.checkCloseReadiness(uiState.selectedClosePeriodId);
  } catch (err) {
    uiState.periodCloseError = err.message;
  } finally {
    uiState.periodCloseWorking = false;
    render();
  }
}

async function handleRequestClose() {
  if (!uiState.selectedClosePeriodId) return;
  uiState.periodCloseError = null;
  uiState.periodCloseWorking = true;
  render();
  try {
    uiState.activeCloseProcess = await api.requestClose(uiState.selectedClosePeriodId);
    uiState.closeProcesses = await api.listCloseProcesses(uiState.selectedClosePeriodId).catch(() => []);
  } catch (err) {
    uiState.periodCloseError = err.message;
  } finally {
    uiState.periodCloseWorking = false;
    render();
  }
}

async function handlePeriodCloseAction(action) {
  uiState.periodCloseError = null;
  uiState.periodCloseWorking = true;
  render();
  try {
    uiState.activeCloseProcess = await action();
    uiState.closeProcesses = await api.listCloseProcesses(uiState.selectedClosePeriodId).catch(() => []);
    uiState.approveReason = "";
    uiState.periodCloseRejectReason = "";
  } catch (err) {
    uiState.periodCloseError = err.message;
  } finally {
    uiState.periodCloseWorking = false;
    render();
  }
}

// ==================================================================
// Controls & Compliance
// ==================================================================
function renderCompliance(name, params, authState, nav) {
  if (name === "compliance-finding-detail") {
    if (uiState.findingRequestedId !== params.id) {
      uiState.findingRequestedId = params.id;
      loadFindingDetail(params.id);
    }
    return Compliance({
      role: authState.role, view: "finding-detail", loading: uiState.findingLoading, findingError: uiState.findingError,
      finding: uiState.finding, remediation: uiState.remediation, onNavigate: nav, onRetry: () => loadFindingDetail(params.id),
      reasonInputs: uiState.reasonInputs, onReasonChange: (field, value) => { uiState.reasonInputs = { ...uiState.reasonInputs, [field]: value }; render(); },
      onStartReview: (id) => handleFindingAction(id, () => api.startFindingReview(id)),
      onSendBackToOpen: (id) => handleFindingAction(id, () => api.sendFindingBackToOpen(id, uiState.reasonInputs.sendBack)),
      onMarkRemediationRequired: (id) => handleFindingAction(id, () => api.markRemediationRequired(id)),
      onMarkResolvedWithoutRemediation: (id) => handleFindingAction(id, () => api.markResolvedWithoutRemediation(id, uiState.reasonInputs.resolveNoRemediation)),
      onReopenFinding: (id) => handleFindingAction(id, () => api.reopenFinding(id, uiState.reasonInputs.reopen)),
      onCloseFinding: (id) => handleFindingAction(id, () => api.closeFinding(id)),
      remediationForm: uiState.remediationForm,
      onRemediationFieldChange: (f, v) => { uiState.remediationForm = { ...uiState.remediationForm, [f]: v }; render(); },
      onCreateRemediation: (findingId) => handleCreateRemediation(findingId),
      onStartRemediation: (id) => handleRemediationAction(() => api.startRemediation(id)),
      onCompleteRemediation: (id) => handleRemediationAction(() => api.completeRemediation(id)),
      onVerifyRemediation: (id) => handleRemediationActionAndFinding(() => api.verifyRemediation(id), params.id),
      onRejectRemediation: (id) => handleRemediationActionAndFinding(() => api.rejectRemediation(id, uiState.reasonInputs.rejectRemediation), params.id),
    });
  }

  once("complianceLoading", loadControlsAndExecutions);
  if (name === "compliance-findings") {
    once("findingsLoading", loadFindings);
    return Compliance({
      role: authState.role, view: "findings", loading: uiState.findingsLoading, error: uiState.complianceError,
      onNavigate: nav, onRetry: loadFindings, findings: uiState.findings, findingFilter: uiState.findingFilter,
      onFindingFilterChange: (v) => { uiState.findingFilter = v; loadFindings(); },
    });
  }
  return Compliance({
    role: authState.role, view: "controls", loading: uiState.complianceLoading, error: uiState.complianceError,
    onNavigate: nav, onRetry: loadControlsAndExecutions,
    controls: uiState.controls, onSeedStandard: handleSeedStandard,
    defineForm: uiState.defineForm, defineError: uiState.defineError, definePending: uiState.definePending,
    onDefineFieldChange: (f, v) => { uiState.defineForm = { ...uiState.defineForm, [f]: v }; render(); },
    onSubmitDefine: handleSubmitDefine, onDeactivateControl: handleDeactivateControl,
    executions: uiState.executions, onExecuteControl: handleExecuteControl,
    executeParams: uiState.executeParams, onExecuteParamsChange: (v) => { uiState.executeParams = v; render(); },
    onReviewExecution: handleReviewExecution,
    selectedControlId: uiState.selectedControlId, onSelectControl: (id) => { uiState.selectedControlId = id; uiState.executeError = null; render(); },
    periods: uiState.periods, executePeriodId: uiState.executePeriodId,
    onExecutePeriodChange: (v) => { uiState.executePeriodId = v; render(); },
    executeError: uiState.executeError, executePending: uiState.executePending, onCreateFinding: handleCreateFindingFromExecution,
  });
}

async function loadControlsAndExecutions() {
  uiState.complianceError = null;
  try {
    uiState.controls = await api.listControls();
    uiState.executions = await api.listExecutions();
    uiState.periods = await api.listPeriods().catch(() => uiState.periods || []);
  } catch (err) {
    uiState.complianceError = err.message || "Could not load controls.";
  } finally {
    render();
  }
}

async function handleSeedStandard() {
  try {
    await api.seedStandardControls();
    uiState.controls = await api.listControls();
  } catch (err) {
    uiState.complianceError = err.message;
  } finally {
    render();
  }
}

async function handleSubmitDefine() {
  uiState.definePending = true;
  uiState.defineError = null;
  render();
  try {
    await api.defineControl(uiState.defineForm);
    uiState.defineForm = { domain: "ACCOUNTING", severity: "MEDIUM" };
    uiState.controls = await api.listControls();
  } catch (err) {
    uiState.defineError = err.message;
  } finally {
    uiState.definePending = false;
    render();
  }
}

async function handleDeactivateControl(id) {
  try {
    await api.deactivateControl(id);
    uiState.controls = await api.listControls();
  } catch (err) {
    uiState.complianceError = err.message;
  } finally {
    render();
  }
}

async function handleExecuteControl(controlId) {
  const journalId = (uiState.executeParams || "").trim();
  if (journalId && !UUID_RE.test(journalId)) {
    uiState.executeError = "The journal ID must be a journal's ID (a long code like 3f2c9a1e-…). Copy it from the journal's page, or leave it blank.";
    render();
    return;
  }
  uiState.executePending = true;
  uiState.executeError = null;
  render();
  try {
    await api.executeControl(controlId, uiState.executePeriodId || undefined, journalId ? { journal_id: journalId } : {});
    uiState.executions = await api.listExecutions();
    uiState.selectedControlId = null;
    uiState.executeParams = "";
  } catch (err) {
    uiState.executeError = err.message;
  } finally {
    uiState.executePending = false;
    render();
  }
}

async function handleCreateFindingFromExecution(executionId) {
  const description = window.prompt("Describe the issue to track as a finding:");
  if (!description) return;
  try {
    const finding = await api.createFindingFromExecution(executionId, description);
    router.navigate(`/compliance/findings/${finding.id}`);
  } catch (err) {
    uiState.complianceError = err.message;
    render();
  }
}

async function handleReviewExecution(executionId) {
  try {
    await api.reviewExecution(executionId);
    uiState.executions = await api.listExecutions();
  } catch (err) {
    uiState.complianceError = err.message;
  } finally {
    render();
  }
}

async function loadFindings() {
  uiState.findingsLoading = true;
  uiState.complianceError = null;
  render();
  try {
    uiState.findings = await api.listFindings(uiState.findingFilter || undefined);
  } catch (err) {
    uiState.complianceError = err.message || "Could not load findings.";
  } finally {
    uiState.findingsLoading = false;
    render();
  }
}

async function loadFindingDetail(id) {
  uiState.findingLoading = true;
  uiState.findingError = null;
  uiState.finding = null;
  uiState.remediation = null;
  render();
  try {
    uiState.finding = await api.getFinding(id);
    if (uiState.finding.remediation_id) {
      uiState.remediation = await api.getRemediation(uiState.finding.remediation_id).catch(() => null);
    }
  } catch (err) {
    uiState.findingError = err.message || "Finding not found.";
  } finally {
    uiState.findingLoading = false;
    render();
  }
}

async function handleFindingAction(id, action) {
  try {
    uiState.finding = await action();
    uiState.reasonInputs = {};
  } catch (err) {
    uiState.findingError = err.message;
  } finally {
    render();
  }
}

async function handleCreateRemediation(findingId) {
  try {
    uiState.remediation = await api.createRemediation(findingId, uiState.remediationForm.action, uiState.remediationForm.owner, uiState.remediationForm.due_date || undefined);
    uiState.remediationForm = {};
  } catch (err) {
    uiState.findingError = err.message;
  } finally {
    render();
  }
}

async function handleRemediationAction(action) {
  try {
    uiState.remediation = await action();
  } catch (err) {
    uiState.findingError = err.message;
  } finally {
    render();
  }
}

async function handleRemediationActionAndFinding(action, findingId) {
  try {
    uiState.remediation = await action();
    uiState.finding = await api.getFinding(findingId);
    uiState.reasonInputs = {};
  } catch (err) {
    uiState.findingError = err.message;
  } finally {
    render();
  }
}

// ==================================================================
// Administration
// ==================================================================
function renderAdmin(authState, nav) {
  once("adminLoading", () => loadAdminData(authState));
  return Administration({
    role: authState.role, organisation: uiState.organisation, members: uiState.members,
    loading: uiState.adminLoading, error: uiState.adminError, onRetry: () => loadAdminData(authState),
    addForm: uiState.addMemberForm, addError: uiState.addMemberError, addPending: uiState.addMemberPending,
    onAddFieldChange: (f, v) => { uiState.addMemberForm = { ...uiState.addMemberForm, [f]: v }; render(); },
    onSubmitAdd: () => handleSubmitAddMember(authState),
    profileForm: uiState.profileForm, profileError: uiState.profileError, profilePending: uiState.profilePending,
    profileSaved: uiState.profileSaved,
    onProfileFieldChange: (f, v) => { uiState.profileForm = { ...uiState.profileForm, [f]: v }; uiState.profileSaved = false; render(); },
    onSubmitProfile: handleSubmitProfile,
    onChangeRole: (userId, role) => handleChangeRole(authState, userId, role),
    roleDrafts: uiState.roleDrafts, onRoleDraftChange: (userId, role) => { uiState.roleDrafts = { ...uiState.roleDrafts, [userId]: role }; render(); },
    onRevokeMember: (userId) => handleRevokeMember(authState, userId),
    currentUserId: authState.user && authState.user.id,
  });
}

async function loadAdminData(authState) {
  uiState.adminError = null;
  uiState.profileError = null;
  try {
    const orgs = await api.myOrganisations();
    uiState.organisation = orgs.find((o) => o.id === authState.organisationId) || null;
    uiState.members = await api.listMembers(authState.organisationId);
    try {
      const profile = await api.getOrganisationProfile();
      uiState.profileForm = profileToForm(profile);
    } catch (err) {
      uiState.profileError = err.message;
    }
  } catch (err) {
    uiState.adminError = err.message || "Could not load organisation data.";
  } finally {
    render();
  }
}

function profileToForm(profile) {
  const { org_id, updated_at, updated_by, ...fields } = profile || {};
  return fields;
}

async function handleSubmitProfile() {
  uiState.profilePending = true;
  uiState.profileError = null;
  uiState.profileSaved = false;
  render();
  try {
    const saved = await api.updateOrganisationProfile(uiState.profileForm);
    uiState.profileForm = profileToForm(saved);
    uiState.profileSaved = true;
  } catch (err) {
    uiState.profileError = err.message;
  } finally {
    uiState.profilePending = false;
    render();
  }
}

async function handleSubmitAddMember(authState) {
  uiState.addMemberPending = true;
  uiState.addMemberError = null;
  render();
  try {
    await api.addMember(authState.organisationId, uiState.addMemberForm.user_id, uiState.addMemberForm.role);
    uiState.addMemberForm = { role: "READ_ONLY" };
    uiState.members = await api.listMembers(authState.organisationId);
  } catch (err) {
    uiState.addMemberError = err.message;
  } finally {
    uiState.addMemberPending = false;
    render();
  }
}

async function handleChangeRole(authState, userId, role) {
  try {
    await api.changeMemberRole(authState.organisationId, userId, role);
    uiState.members = await api.listMembers(authState.organisationId);
  } catch (err) {
    uiState.adminError = err.message;
  } finally {
    render();
  }
}

async function handleRevokeMember(authState, userId) {
  try {
    await api.revokeMember(authState.organisationId, userId);
    uiState.members = await api.listMembers(authState.organisationId);
  } catch (err) {
    uiState.adminError = err.message;
  } finally {
    render();
  }
}

authStore.subscribe(() => {});
router.start();
render();
loadSsoConfig();
handleSsoReturn();


// ==================================================================
// Connection & Self-Test
// ==================================================================
function renderDiagnostics(authState) {
  return Diagnostics({
    baseUrl: API_BASE_URL, origin: window.location.origin,
    connection: uiState.diagConnection, connectionRunning: uiState.diagConnectionRunning, onRunConnection: handleConnectionCheck,
    running: uiState.diagRunning, results: uiState.diagResults, onRunSelfTest: () => handleRunSelfTest(authState),
    copied: uiState.diagCopied, onCopyReport: handleCopyReport,
  });
}

async function handleConnectionCheck() {
  uiState.diagConnectionRunning = true;
  render();
  const lines = [];
  let verdict = "";
  let ok = false;
  const health = await api.rawGet("/health");
  if (health.error) {
    // Distinguish "API is down" from "API is up but refusing this website" (CORS).
    lines.push(`Health check failed: ${health.error.message}`);
    verdict = health.error.diagnosis === "cors"
      ? "The API is running, but it is refusing requests from this website (CORS). Add this website's address to CORS_ALLOWED_ORIGINS on the Render service, then redeploy."
      : health.error.diagnosis === "offline"
        ? "Your device appears to be offline."
        : "The API did not answer. On the free Render plan the service sleeps when idle and can take up to a minute to wake — wait 60 seconds and try again. If it still fails, open the Render dashboard and check the service's Logs for a crash.";
  } else {
    lines.push(`/health → HTTP ${health.status} in ${health.ms} ms`);
    const ready = await api.rawGet("/ready");
    if (ready.error) {
      lines.push(`/ready failed: ${ready.error.message}`);
    } else {
      lines.push(`/ready → HTTP ${ready.status} ${typeof ready.body === "object" ? JSON.stringify(ready.body) : ""}`);
    }
    if (!health.ok) {
      verdict = `The API answered with an error (HTTP ${health.status}). Check the Render service logs.`;
    } else if (ready.error || !ready.ok) {
      verdict = "The API is running but cannot reach the database. Check DATABASE_URL on Render and that the database is running.";
    } else {
      const token = authStore.getToken();
      try {
        await api.myOrganisations();
        lines.push("Signed-in request (/organisations/mine) → OK, so this website is allowed by CORS and your session works.");
        ok = true;
        verdict = "Everything is connected: website → API → database, and your sign-in works.";
      } catch (err) {
        lines.push(`Signed-in request failed: ${err.message}`);
        verdict = token ? "The API and database are up, but a signed-in request failed — see the line above." : "The API and database are up. Sign in to test the authenticated path.";
      }
    }
  }
  uiState.diagConnection = { verdict, verdictOk: ok, lines };
  uiState.diagConnectionRunning = false;
  render();
}

async function handleRunSelfTest(authState) {
  if (uiState.diagRunning) return;
  uiState.diagRunning = true;
  uiState.diagResults = [];
  uiState.diagCopied = false;
  render();
  try {
    await runSelfTest(api, {
      orgId: authState.organisationId,
      onResult: (r) => { uiState.diagResults = [...uiState.diagResults, r]; render(); },
    });
  } catch (err) {
    uiState.diagResults = [...uiState.diagResults, { group: "Self-test", name: "Unexpected error", status: "fail", detail: String((err && err.message) || err), ms: 0 }];
  } finally {
    uiState.diagRunning = false;
    render();
  }
}

async function handleCopyReport() {
  const text = formatReport(uiState.diagResults, { origin: window.location.origin, baseUrl: API_BASE_URL });
  try {
    await navigator.clipboard.writeText(text);
    uiState.diagCopied = true;
  } catch {
    window.prompt("Copy this report:", text);
  }
  render();
}


// ==================================================================
// Standards & Policies
// ==================================================================
let standardsPreviewSeq = 0;

function renderStandards(authState) {
  once("standardsLoading", loadStandards);
  return Standards({
    role: authState.role, organisationName: uiState.organisation && uiState.organisation.name,
    loading: uiState.standardsLoading, error: uiState.standardsError, onRetry: () => reload("standardsLoading"),
    catalog: uiState.standardsCatalog, form: uiState.standardsForm, preview: uiState.standardsPreview,
    previewError: uiState.standardsPreviewError, previewing: uiState.standardsPreviewing,
    saving: uiState.standardsSaving, saveError: uiState.standardsSaveError, saved: uiState.standardsSaved,
    onFieldChange: handleStandardsFieldChange,
    onPolicyChange: (code, value) => {
      uiState.standardsForm = { ...uiState.standardsForm, policy_overrides: { ...(uiState.standardsForm.policy_overrides || {}), [code]: value } };
      refreshStandardsPreview();
    },
    onUseRecommended: () => {
      uiState.standardsForm = { ...uiState.standardsForm, framework: null, policy_overrides: {} };
      refreshStandardsPreview();
    },
    onSave: handleSaveStandards,
  });
}

async function loadStandards() {
  uiState.standardsError = null;
  try {
    uiState.standardsCatalog = await api.standardsCatalog();
    if (!uiState.organisation) {
      const orgs = await api.myOrganisations().catch(() => []);
      uiState.organisation = orgs.find((o) => o.id === authStore.getState().organisationId) || null;
    }
    const saved = await api.getStandardsConfiguration();
    if (saved && saved.configured) {
      uiState.standardsForm = {
        jurisdiction: saved.jurisdiction, entity_type: saved.entity_type, framework: saved.framework,
        policy_overrides: Object.fromEntries(saved.policies.filter((p) => p.overridden).map((p) => [p.code, p.effective])),
      };
      uiState.standardsPreview = saved;
    } else {
      uiState.standardsForm = {};
      uiState.standardsPreview = null;
    }
    uiState.standardsPreviewError = null;
    uiState.standardsSaved = false;
  } catch (err) {
    uiState.standardsError = err.message || "Could not load standards configuration.";
  }
}

function handleStandardsFieldChange(field, value) {
  const next = { ...uiState.standardsForm, [field]: value || null };
  if (field === "jurisdiction" || field === "entity_type") {
    // A new place or entity type means a new recommendation: start from its defaults.
    next.framework = null;
    next.policy_overrides = {};
  } else if (field === "framework") {
    next.policy_overrides = {};
  }
  uiState.standardsForm = next;
  uiState.standardsSaved = false;
  refreshStandardsPreview();
}

async function refreshStandardsPreview() {
  const f = uiState.standardsForm;
  uiState.standardsSaved = false;
  if (!f.jurisdiction || !f.entity_type) {
    uiState.standardsPreview = null;
    uiState.standardsPreviewError = null;
    render();
    return;
  }
  const seq = ++standardsPreviewSeq;
  uiState.standardsPreviewing = true;
  uiState.standardsPreviewError = null;
  render();
  try {
    const result = await api.resolveStandards({
      jurisdiction: f.jurisdiction, entity_type: f.entity_type,
      framework: f.framework || undefined, policy_overrides: f.policy_overrides || {},
    });
    if (seq !== standardsPreviewSeq) return; // a newer choice superseded this one
    uiState.standardsPreview = result;
  } catch (err) {
    if (seq !== standardsPreviewSeq) return;
    uiState.standardsPreviewError = err.message;
  } finally {
    if (seq === standardsPreviewSeq) {
      uiState.standardsPreviewing = false;
      render();
    }
  }
}

async function handleSaveStandards() {
  const f = uiState.standardsForm;
  uiState.standardsSaving = true;
  uiState.standardsSaveError = null;
  uiState.standardsSaved = false;
  render();
  try {
    const saved = await api.saveStandardsConfiguration({
      jurisdiction: f.jurisdiction, entity_type: f.entity_type,
      framework: (uiState.standardsPreview && uiState.standardsPreview.framework) || f.framework || undefined,
      policy_overrides: f.policy_overrides || {},
    });
    uiState.standardsPreview = saved;
    uiState.standardsSaved = true;
  } catch (err) {
    uiState.standardsSaveError = err.message;
  } finally {
    uiState.standardsSaving = false;
    render();
  }
}

// ==================================================================
// Data Import: preview (writes nothing), then confirm
function renderImport(authState, nav) {
  once("impLoading", loadImportContext);
  const offered = allowedPurposes(authState.role);
  if (offered.length && !offered.some((p) => p.value === uiState.impForm.purpose)) uiState.impForm = newImportForm(offered[0].value);
  return DataImport({
    role: authState.role, loading: uiState.impLoading, error: uiState.impLoadError, onRetry: () => reload("impLoading"),
    reconciliations: uiState.impReconciliations, levels: uiState.impLevels,
    form: uiState.impForm, file: uiState.impFile, formError: uiState.impFormError,
    previewing: uiState.impPreviewing, previewError: uiState.impPreviewError, batch: uiState.impBatch,
    onlyProblems: uiState.impOnlyProblems, ack: uiState.impAck, committing: uiState.impCommitting, commitError: uiState.impCommitError, result: uiState.impResult,
    onPurpose: (v) => { uiState.impForm = newImportForm(v); clearImportPreview(); render(); },
    onFormChange: (k, v) => { uiState.impForm = { ...uiState.impForm, [k]: v }; uiState.impFormError = null; if (["flip", "dateFormat", "headerRow", "sheet", "docType", "reconciliationId"].includes(k)) clearImportPreview(true); render(); },
    onFile: (file) => { holdImportFile(file); },
    onPreview: () => handleImportPreview(),
    onMappingChange: (role, col) => { uiState.impForm = { ...uiState.impForm, mapping: { ...uiState.impForm.mapping, [role]: col } }; handleImportPreview(); },
    onToggleProblems: (e) => { uiState.impOnlyProblems = !!e.target.checked; render(); },
    onAck: (v) => { uiState.impAck = v; render(); },
    onCommit: () => handleImportCommit(),
    onReset: () => { uiState.impFile = null; uiState.impForm = newImportForm(uiState.impForm.purpose); clearImportPreview(); uiState.impResult = null; render(); },
    onNavigate: nav,
  });
}

// Reads the chosen file into memory once. The preview and the import then send exactly the same bytes, even if the file on disk
// is changed or the page redraws its file box in between (the server also refuses an import whose file differs from the preview).
async function holdImportFile(file) {
  uiState.impForm = { ...uiState.impForm, mapping: {} }; clearImportPreview(); uiState.impFormError = null;
  if (!file) { uiState.impFile = null; render(); return; }
  try {
    const bytes = await file.arrayBuffer();
    uiState.impFile = new File([bytes], file.name, { type: file.type || "application/octet-stream" });
  } catch (err) {
    uiState.impFile = null;
    uiState.impFormError = "That file could not be read. Please choose it again.";
  }
  render();
}

function clearImportPreview(keepError) {
  uiState.impBatch = null; uiState.impAck = false; uiState.impCommitError = null; uiState.impOnlyProblems = false;
  if (!keepError) uiState.impPreviewError = null;
}

async function loadImportContext() {
  uiState.impLoadError = null;
  try {
    const [levels, recs] = await Promise.all([
      api.ingestionLevels().catch(() => null),
      allowed(authStore.getState().role, PERMISSIONS.RECONCILIATION_READ) ? api.listReconciliations() : Promise.resolve([]),
    ]);
    uiState.impLevels = levels && levels.levels;
    uiState.impReconciliations = recs || [];
  } catch (err) {
    uiState.impLoadError = err.message || "Could not load reconciliations.";
  }
}

async function handleImportPreview() {
  const problem = validateImportForm(uiState.impForm, uiState.impFile);
  if (problem) { uiState.impFormError = problem; render(); return; }
  uiState.impFormError = null; uiState.impPreviewError = null; uiState.impPreviewing = true; uiState.impBatch = null; uiState.impAck = false;
  render();
  try {
    uiState.impBatch = await api.ingestionPreview(buildImportArgs(uiState.impForm, uiState.impFile));
  } catch (err) {
    uiState.impPreviewError = err.message || "The file could not be read.";
  } finally {
    uiState.impPreviewing = false;
    render();
  }
}

async function handleImportCommit() {
  const b = uiState.impBatch;
  if (!b || uiState.impCommitting) return;
  uiState.impCommitting = true; uiState.impCommitError = null; render();
  try {
    uiState.impResult = await api.ingestionCommit({ ...buildImportArgs(uiState.impForm, uiState.impFile), fingerprint: b.fingerprint, acknowledge: uiState.impAck,
      evidenceType: uiState.impForm.evidenceType || undefined });
  } catch (err) {
    uiState.impCommitError = err.message || "The import failed. Nothing was imported.";
  } finally {
    uiState.impCommitting = false;
    render();
  }
}

// ------------------------------------------------------------------
// ASAVEXA AI (read-only; every answer is grounded server-side)
function renderAi(authState) {
  once("aiLoading", loadAiContext);
  return AiAssistant({
    role: authState.role, loading: uiState.aiLoading, error: uiState.aiLoadError, onRetry: () => reload("aiLoading"),
    journals: uiState.aiJournals, periods: uiState.aiPeriods,
    mode: uiState.aiMode, form: uiState.aiForm, running: uiState.aiRunning, formError: uiState.aiFormError,
    question: uiState.aiQuestion, result: uiState.aiResult, resultError: uiState.aiResultError, expanded: uiState.aiExpanded,
    onModeChange: (m) => { uiState.aiMode = m; uiState.aiFormError = null; uiState.aiResult = null; uiState.aiResultError = null; uiState.aiExpanded = null; render(); },
    onFormChange: (k, v) => { uiState.aiForm = { ...uiState.aiForm, [k]: v }; uiState.aiFormError = null; render(); },
    onQuestionChange: (v) => { uiState.aiQuestion = v; },
    onRun: handleAiRun, onAsk: () => handleAiAsk(uiState.aiQuestion),
    onSample: (q) => { uiState.aiQuestion = q; handleAiAsk(q); },
    onToggle: (i) => {
      const cur = uiState.aiExpanded || { 0: true };
      uiState.aiExpanded = { ...cur, [i]: !cur[i] }; render();
    },
    onDrill: (mode, subj) => handleAiDrill(mode, subj),
  });
}

async function loadAiContext() {
  uiState.aiLoadError = null;
  try {
    const [journals, periods] = await Promise.all([api.listJournals(), api.listPeriods().catch(() => [])]);
    uiState.aiJournals = journals || [];
    uiState.aiPeriods = periods || [];
  } catch (err) {
    uiState.aiLoadError = err.message || "Could not load your journals.";
  }
}

async function runAi(fn) {
  uiState.aiRunning = true; uiState.aiResultError = null; uiState.aiResult = null; uiState.aiExpanded = null;
  render();
  try {
    uiState.aiResult = await fn();
  } catch (err) {
    uiState.aiResultError = err.message || "ASAVEXA AI could not answer.";
  } finally {
    uiState.aiRunning = false;
    render();
  }
}

function handleAiRun() {
  const problem = validateAiForm(uiState.aiMode, uiState.aiForm);
  if (problem) { uiState.aiFormError = problem; render(); return; }
  const { call, args } = buildAiRequest(uiState.aiMode, uiState.aiForm);
  return runAi(() => api[call](args));
}

function handleAiAsk(question) {
  const q = String(question || "").trim();
  if (!q) { uiState.aiFormError = "Type a question first."; render(); return; }
  uiState.aiFormError = null;
  return runAi(() => api.aiAsk(q));
}

function handleAiDrill(mode, subj) {
  uiState.aiMode = mode;
  if (mode === "EXPLAIN") return runAi(() => api.aiExplain(subj));
  return runAi(() => api.aiProve(subj));
}

// ------------------------------------------------------------------
// VERA Financial Passport
// ==================================================================
function structureFromPassport(passport) {
  const o = (passport && passport.identity && passport.identity.ownership) || {};
  const sb = (passport && passport.identity && passport.identity.subsidiaries) || {};
  const text = (v) => (v === null || v === undefined ? "" : String(v));
  return {
    owners: (o.owners || []).map((x) => ({ name: text(x.name), kind: x.kind || "INDIVIDUAL", ownership_percent: text(x.ownership_percent), notes: text(x.notes) })),
    subsidiaries: (sb.items || []).map((x) => ({
      name: text(x.name), relationship: x.relationship || "SUBSIDIARY", jurisdiction: text(x.jurisdiction),
      registration_number: text(x.registration_number), ownership_percent: text(x.ownership_percent),
    })),
  };
}

function renderPassport(authState, nav) {
  once("passportLoading", loadPassport);
  return Passport({
    role: authState.role,
    loading: uiState.passportLoading, error: uiState.passportError, onRetry: () => reload("passportLoading"),
    passport: uiState.passport, refreshing: uiState.passportRefreshing,
    onRefresh: handleRefreshPassport, onDownload: handleDownloadPassport, onPrint: () => window.print(),
    onOpenSharing: allowed(authState.role, PERMISSIONS.ORG_MANAGE_SETTINGS) ? () => nav("/passport/sharing") : null,
    structureForm: uiState.passportStructure, structureSaving: uiState.passportStructureSaving,
    structureError: uiState.passportStructureError, structureSaved: uiState.passportStructureSaved,
    onStructureChange: (kind, i, field, value) => {
      const rows = uiState.passportStructure[kind].map((r, idx) => (idx === i ? { ...r, [field]: value } : r));
      uiState.passportStructure = { ...uiState.passportStructure, [kind]: rows };
      uiState.passportStructureSaved = false;
      render();
    },
    onAddRow: (kind) => {
      const blank = kind === "owners"
        ? { name: "", kind: "INDIVIDUAL", ownership_percent: "", notes: "" }
        : { name: "", relationship: "SUBSIDIARY", jurisdiction: "", registration_number: "", ownership_percent: "" };
      uiState.passportStructure = { ...uiState.passportStructure, [kind]: [...uiState.passportStructure[kind], blank] };
      uiState.passportStructureSaved = false;
      render();
    },
    onRemoveRow: (kind, i) => {
      uiState.passportStructure = { ...uiState.passportStructure, [kind]: uiState.passportStructure[kind].filter((_, idx) => idx !== i) };
      uiState.passportStructureSaved = false;
      render();
    },
    onSaveStructure: handleSavePassportStructure,
  });
}

async function loadPassport() {
  uiState.passportError = null;
  try {
    uiState.passport = await api.getPassport();
    uiState.passportStructure = structureFromPassport(uiState.passport);
  } catch (err) {
    uiState.passportError = err.message || "Could not build the Financial Passport.";
  }
}

async function handleRefreshPassport() {
  uiState.passportRefreshing = true;
  uiState.passportError = null;
  render();
  try {
    uiState.passport = await api.getPassport();
    uiState.passportStructure = structureFromPassport(uiState.passport);
  } catch (err) {
    uiState.passportError = err.message || "Could not refresh the Financial Passport.";
  } finally {
    uiState.passportRefreshing = false;
    render();
  }
}

function handleDownloadPassport() {
  const p = uiState.passport;
  if (!p) return;
  const blob = new Blob([JSON.stringify(p, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `vera-financial-passport-${String(p.generated_at || "").slice(0, 10)}-${String(p.fingerprint || "").slice(0, 8)}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Percent fields are free text in the form; turn them into numbers (or
// nothing) before they go to the API. Anything unparseable is sent as-is
// so the server's validation message reaches the user instead of being
// silently dropped.
function structureToPayload(form) {
  const pct = (v) => {
    const t = String(v === undefined || v === null ? "" : v).trim().replace(/%$/, "");
    if (t === "") return undefined;
    const n = Number(t);
    return Number.isFinite(n) ? n : t;
  };
  const clean = (row, keys) => {
    const out = {};
    for (const k of keys) {
      if (k === "ownership_percent") {
        const v = pct(row[k]);
        if (v !== undefined) out[k] = v;
      } else {
        const t = String(row[k] === undefined || row[k] === null ? "" : row[k]).trim();
        if (t !== "" || k === "name") out[k] = t;
      }
    }
    return out;
  };
  return {
    owners: form.owners.map((r) => clean(r, ["name", "kind", "ownership_percent", "notes"])),
    subsidiaries: form.subsidiaries.map((r) => clean(r, ["name", "relationship", "jurisdiction", "registration_number", "ownership_percent"])),
  };
}

async function handleSavePassportStructure() {
  uiState.passportStructureSaving = true;
  uiState.passportStructureError = null;
  uiState.passportStructureSaved = false;
  render();
  try {
    await api.savePassportStructure(structureToPayload(uiState.passportStructure));
    uiState.passport = await api.getPassport();
    uiState.passportStructure = structureFromPassport(uiState.passport);
    uiState.passportStructureSaved = true;
  } catch (err) {
    uiState.passportStructureError = err.message;
  } finally {
    uiState.passportStructureSaving = false;
    render();
  }
}


// ------------------------------------------------------------------
// Permissioned sharing: organisation side
// ------------------------------------------------------------------
function renderPassportSharing(authState, nav) {
  once("sharesLoading", loadShares);
  const w = uiState.shareWizard;
  return PassportSharing({
    role: authState.role, loading: uiState.sharesLoading, error: uiState.sharesError, onRetry: () => reload("sharesLoading"),
    shares: uiState.shares, wizard: w, wizardError: uiState.shareWizardError, creating: uiState.shareCreating,
    result: uiState.shareResult, link: uiState.shareLink, copied: uiState.shareCopied,
    onStart: () => { uiState.shareWizard = newWizard(); uiState.shareWizardError = null; render(); },
    onBackToPassport: () => nav("/passport"),
    onWizardChange: handleWizardChange,
    onNext: () => {
      const problem = validateStep(w.step, w);
      uiState.shareWizardError = problem;
      if (!problem) w.step = Math.min(w.step + 1, STEPS.length - 1);
      render();
    },
    onBack: () => { w.step = Math.max(0, w.step - 1); uiState.shareWizardError = null; render(); },
    onCancel: () => { uiState.shareWizard = null; uiState.shareWizardError = null; render(); },
    onCreate: handleCreateShare,
    onCopy: handleCopyShare,
    onDone: () => { uiState.shareResult = null; uiState.shareLink = ""; uiState.shareCopied = null; uiState.shareWizard = null; reload("sharesLoading"); },
    revokeTarget: uiState.shareRevokeTarget, revokeReason: uiState.shareRevokeReason,
    revoking: uiState.shareRevoking, revokeError: uiState.shareRevokeError,
    onRevokeStart: (id) => { uiState.shareRevokeTarget = id; uiState.shareRevokeReason = ""; uiState.shareRevokeError = null; render(); },
    onRevokeReasonChange: (v) => { uiState.shareRevokeReason = v; },
    onRevokeCancel: () => { uiState.shareRevokeTarget = null; render(); },
    onRevokeConfirm: handleRevokeShare,
    logTarget: uiState.shareLogTarget, log: uiState.shareLog, logLoading: uiState.shareLogLoading, logError: uiState.shareLogError,
    onShowLog: handleShowShareLog,
    onCloseLog: () => { uiState.shareLogTarget = null; render(); },
  });
}

async function loadShares() {
  uiState.sharesError = null;
  try {
    uiState.shares = await api.listPassportShares();
  } catch (err) {
    uiState.sharesError = err.message || "Could not load the shares.";
  }
}

function handleWizardChange(key, value) {
  const w = uiState.shareWizard;
  if (!w) return;
  if (key.startsWith("scope:")) {
    const scope = key.slice(6);
    w.scopes = value ? [...new Set([...w.scopes, scope])] : w.scopes.filter((x) => x !== scope);
  } else if (key === "recipient_type") {
    w.recipient_type = value;
    const d = RECIPIENT_DEFAULTS[value];
    if (d) {
      w.scopes = [...d.scopes]; w.closed_periods_only = d.closed_periods_only; w.preset = d.preset;
      Object.assign(w, presetRange(d.preset, new Date()));
    }
  } else if (key === "preset") {
    w.preset = value;
    const r = presetRange(value, new Date());
    if (r) Object.assign(w, r);
  } else {
    w[key] = value;
  }
  uiState.shareWizardError = null;
  // typing in a text box must not re-render the whole page under the cursor
  if (["recipient_name", "recipient_email", "purpose", "expires_in_days", "date_from", "date_to"].includes(key)) {
    if (key === "date_from" || key === "date_to") render();
    return;
  }
  render();
}

async function handleCreateShare() {
  const w = uiState.shareWizard;
  for (let i = 0; i < STEPS.length - 1; i++) {
    const problem = validateStep(i, w);
    if (problem) { w.step = i; uiState.shareWizardError = problem; render(); return; }
  }
  uiState.shareCreating = true;
  uiState.shareWizardError = null;
  render();
  try {
    const res = await api.createPassportShare(buildSharePayload(w));
    uiState.shareResult = res;
    uiState.shareLink = `${window.location.origin}${window.location.pathname}#/shared/${encodeURIComponent(res.access_token)}`;
    uiState.shareCopied = null;
  } catch (err) {
    uiState.shareWizardError = err.message || "Could not create the share.";
  } finally {
    uiState.shareCreating = false;
    render();
  }
}

async function handleCopyShare(which, text) {
  try {
    await navigator.clipboard.writeText(text);
    uiState.shareCopied = which;
  } catch (_) {
    const el = document.getElementById(which === "link" ? "share-link" : "share-code");
    if (el) { el.focus(); el.select(); }
    uiState.shareCopied = null;
  }
  render();
}

async function handleRevokeShare() {
  const id = uiState.shareRevokeTarget;
  uiState.shareRevoking = true;
  uiState.shareRevokeError = null;
  render();
  try {
    await api.revokePassportShare(id, uiState.shareRevokeReason);
    uiState.shareRevokeTarget = null;
    uiState.shares = await api.listPassportShares();
  } catch (err) {
    uiState.shareRevokeError = err.message || "Could not revoke the share.";
  } finally {
    uiState.shareRevoking = false;
    render();
  }
}

async function handleShowShareLog(id) {
  uiState.shareLogTarget = id;
  uiState.shareLog = null;
  uiState.shareLogError = null;
  uiState.shareLogLoading = true;
  render();
  try {
    const log = await api.passportShareAccessLog(id);
    if (uiState.shareLogTarget === id) uiState.shareLog = log;
  } catch (err) {
    uiState.shareLogError = err.message || "Could not load the activity.";
  } finally {
    uiState.shareLogLoading = false;
    render();
  }
}

// ------------------------------------------------------------------
// Permissioned sharing: recipient side (public; no organisation login)
// ------------------------------------------------------------------
function renderSharedPassport(token) {
  const sh = uiState.shared;
  if (sh.token !== token) {
    uiState.shared = { token, code: "", email: "", phase: "verify", pending: false, error: null, expired: false,
      data: null, sessionToken: null, downloading: false, downloadError: null };
  }
  const s = uiState.shared;
  mount(
    SharedPassport({
      phase: token && token.includes(".") ? s.phase : "bad-link",
      pending: s.pending, error: s.error, expired: s.expired, code: s.code, email: s.email, data: s.data,
      downloading: s.downloading, downloadError: s.downloadError,
      onCodeChange: (v) => { s.code = v; },
      onEmailChange: (v) => { s.email = v; },
      onVerify: handleSharedVerify,
      onPrint: () => window.print(),
      onDownload: handleSharedDownload,
      onClose: () => { s.sessionToken = null; s.data = null; s.phase = "verify"; s.code = ""; s.error = null; render(); },
    }),
    root
  );
}

const SESSION_ENDED = "Your verified session has ended";

function sharedSessionEnded(s) {
  s.sessionToken = null; s.data = null; s.phase = "verify"; s.code = ""; s.expired = true; s.error = null;
}

async function handleSharedVerify() {
  const s = uiState.shared;
  if (!s.code.trim()) { s.error = "Enter the access code you were sent."; render(); return; }
  s.pending = true; s.error = null; s.expired = false;
  render();
  try {
    const v = await api.verifyShare({ accessToken: s.token, accessCode: s.code, email: s.email || null });
    s.sessionToken = v.session_token;
    s.data = await api.viewSharedPassport(s.sessionToken);
    s.phase = "view";
    s.code = "";
  } catch (err) {
    s.sessionToken = null; s.data = null; s.phase = "verify";
    s.error = err.message || "Could not open this passport.";
  } finally {
    s.pending = false;
    render();
  }
}

async function handleSharedDownload() {
  const s = uiState.shared;
  s.downloading = true; s.downloadError = null;
  render();
  try {
    const doc = await api.downloadSharedPassport(s.sessionToken);
    const blob = new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `financial-passport-${String((doc.fingerprint || "")).slice(0, 8)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (err) {
    if ((err.message || "").startsWith(SESSION_ENDED)) sharedSessionEnded(s);
    else s.downloadError = err.message || "Could not download.";
  } finally {
    s.downloading = false;
    render();
  }
}


// ----------------------------------------------------------------------
// Security page
// ----------------------------------------------------------------------
function newSec() {
  return { tab: "me", me: null, overview: null, alerts: null, retention: null, vendors: null, residency: null, requests: null, health: null,
    auditResult: null, rotateResult: null, mfa: {}, notice: null, error: null, confirmErase: false, ackTarget: null, disposeTarget: null, d: {} };
}

function renderSecurityPage(authState) {
  if (!uiState.sec) uiState.sec = newSec();
  const sec = uiState.sec;
  if (authState.organisationId || !uiState.secNoOrg) once("secLoading", () => loadSecurity(authState));
  return Security({ role: authState.role, sec, loading: uiState.secLoading, onRetry: () => { loadedOnce.delete("secLoading"); render(); }, actions: securityActions(authState) });
}

async function loadSecurity(authState) {
  const sec = uiState.sec || (uiState.sec = newSec());
  sec.error = null;
  try {
    sec.me = await api.mySecurity();
  } catch (err) {
    sec.error = err.message;
    return;
  }
  if (!authState.organisationId || !allowed(authState.role, PERMISSIONS.SECURITY_MANAGE)) return;
  const [overview, alerts, retention, vendors, residency, requests] = await Promise.allSettled([
    api.securityOverview(), api.listSecurityAlerts(), api.getRetention(), api.listVendors(), api.residencyReport(), api.privacyRequests(),
  ]);
  const val = (r) => (r.status === "fulfilled" ? r.value : null);
  Object.assign(sec, { overview: val(overview), alerts: val(alerts), retention: val(retention), vendors: val(vendors), residency: val(residency), requests: val(requests) });
  const failed = [overview, alerts, retention, vendors, residency, requests].find((r) => r.status === "rejected");
  if (failed) sec.error = failed.reason && failed.reason.message ? failed.reason.message : "Part of this page could not be loaded.";
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function securityActions(authState) {
  const sec = uiState.sec;
  const refresh = async () => { loadedOnce.delete("secLoading"); await loadSecurity(authState); render(); };
  /** Runs one action; any failure is shown on the page, never swallowed. */
  const run = async (fn, okNotice) => {
    sec.error = null; sec.notice = null;
    try { await fn(); if (okNotice) sec.notice = okNotice; } catch (err) { sec.error = err.message || "That did not work."; }
    render();
  };
  const mfaRun = async (fn) => {
    sec.mfa.error = null; sec.mfa.pending = true; render();
    try { await fn(); } catch (err) { sec.mfa.error = err.message; }
    sec.mfa.pending = false; render();
  };
  return {
    // Switching tab re-reads everything quietly, so a figure changed elsewhere (e.g. someone just turned two-step sign-in on) is never stale.
    setTab: (t) => { sec.tab = t; sec.error = null; sec.notice = null; render(); loadSecurity(authState).then(render, render); },
    // two-step sign-in
    mfaCodeChange: (v) => { sec.d.mfaCode = v; },
    mfaBegin: () => mfaRun(async () => { sec.mfa.setup = await api.mfaBegin(); }),
    mfaCancelSetup: () => { sec.mfa.setup = null; sec.mfa.error = null; render(); },
    mfaConfirm: () => mfaRun(async () => {
      const r = await api.mfaConfirm((sec.d.mfaCode || "").trim());
      sec.mfa.setup = null; sec.mfa.recovery = r.recovery_codes; sec.d.mfaCode = "";
      sec.me = await api.mySecurity();
    }),
    mfaNewRecovery: () => mfaRun(async () => {
      sec.mfa.recovery = (await api.mfaRecoveryCodes((sec.d.mfaCode || "").trim())).recovery_codes; sec.d.mfaCode = "";
      sec.me = await api.mySecurity();
    }),
    mfaDisable: () => mfaRun(async () => { await api.mfaDisable((sec.d.mfaCode || "").trim()); sec.d.mfaCode = ""; sec.me = await api.mySecurity(); }),
    mfaDismissRecovery: () => { sec.mfa.recovery = null; render(); },
    // devices
    revokeSession: (id) => run(async () => { await api.revokeSession(id); sec.me = await api.mySecurity(); }, "That device was signed out."),
    revokeOthers: () => run(async () => { const r = await api.revokeOtherSessions(); sec.me = await api.mySecurity(); sec.notice = `${r.revoked} other device(s) signed out.`; }),
    // own data
    exportData: () => run(async () => {
      const doc = await api.exportMyData();
      saveBlob(new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" }), "my-asavexa-data.json");
    }, "Your data was downloaded."),
    startErase: () => { sec.confirmErase = true; render(); },
    cancelErase: () => { sec.confirmErase = false; render(); },
    requestErasure: () => run(async () => { await api.requestErasure(); sec.confirmErase = false; sec.me = await api.mySecurity(); }, "Your erasure request was sent to the organisation's owners."),
    // organisation rules
    setRequireMfa: (on) => run(async () => { await api.updateSecuritySettings({ require_mfa: !!on }); sec.overview = await api.securityOverview(); }, on ? "Two-step sign-in is now required." : "Two-step sign-in is no longer required."),
    regionsChange: (v) => { sec.d.regions = v; },
    saveRegions: () => run(async () => {
      await api.updateSecuritySettings({ allowed_regions: parseRegions(sec.d.regions ?? ((sec.overview.residency || {}).allowed_regions || []).join(",")) });
      sec.overview = await api.securityOverview(); sec.residency = await api.residencyReport();
    }, "Regions saved."),
    rotateKeys: () => run(async () => { sec.rotateResult = await api.rotateKeys(); sec.overview = await api.securityOverview(); }),
    checkHealth: () => run(async () => { sec.health = await api.securityHealth(); }),
    // alerts
    refreshAlerts: () => run(async () => { const r = await api.refreshSecurityAlerts(); sec.alerts = r.alerts; sec.notice = r.new ? `${r.new} new alert(s) found.` : "No new alerts."; }),
    ackStart: (id) => { sec.ackTarget = id; sec.d.ackNote = ""; render(); },
    ackNoteChange: (v) => { sec.d.ackNote = v; },
    ackConfirm: (id) => run(async () => { await api.acknowledgeAlert(id, sec.d.ackNote || ""); sec.ackTarget = null; sec.alerts = await api.listSecurityAlerts(); }),
    // audit trail
    verifyAudit: () => run(async () => { sec.auditResult = await api.verifyAuditChain(); }),
    // retention
    retDaysChange: (v) => { sec.d.retDays = v; },
    saveRetention: () => run(async () => { await api.setRetention(parseInt(sec.d.retDays, 10)); sec.retention = await api.getRetention(); }, "Retention saved."),
    holdReasonChange: (v) => { sec.d.holdReason = v; },
    holdEvidenceChange: (v) => { sec.d.holdEvidence = v; },
    placeHold: () => run(async () => { await api.placeHold(sec.d.holdReason || "", (sec.d.holdEvidence || "").trim() || null); sec.retention = await api.getRetention(); }, "Legal hold placed."),
    releaseHold: (id) => run(async () => { await api.releaseHold(id); sec.retention = await api.getRetention(); }, "Hold released."),
    disposeStart: (id) => { sec.disposeTarget = id; sec.d.disposeReason = ""; render(); },
    disposeReasonChange: (v) => { sec.d.disposeReason = v; },
    disposeConfirm: (id) => run(async () => { await api.disposeEvidence(id, sec.d.disposeReason || ""); sec.disposeTarget = null; sec.retention = await api.getRetention(); }, "The file was disposed of. The record and fingerprint are kept."),
    // privacy requests
    decideNoteChange: (v) => { sec.d.decideNote = v; },
    decide: (id, approve) => run(async () => { await api.decidePrivacyRequest(id, approve, sec.d.decideNote || ""); sec.requests = await api.privacyRequests(); }, approve ? "Erasure completed." : "Request declined."),
    // vendors
    vendorChange: (k, v) => { sec.d.vendor = { ...(sec.d.vendor || {}), [k]: v }; },
    addVendor: () => run(async () => { await api.addVendor({ name: "", ...(sec.d.vendor || {}) }); sec.vendors = await api.listVendors(); sec.residency = await api.residencyReport(); sec.d.vendor = {}; }, "Vendor added."),
    seedVendors: () => run(async () => { await api.seedVendors(); sec.vendors = await api.listVendors(); }, "Added. Their risk shows as unconfirmed until you record the facts."),
  };
}


// ----------------------------------------------------------------------
// Professional Validation page
// ----------------------------------------------------------------------
function newVal() {
  return { tab: "engagements", guide: null, me: null, list: null, panel: null, members: null, detailId: null, detail: null, statement: null,
    form: null, busy: false, notice: null, error: null };
}

function renderValidationPage(authState) {
  if (!uiState.val) uiState.val = newVal();
  once("valLoading", () => loadValidation(authState));
  return Validation({ role: authState.role, val: uiState.val, loading: uiState.valLoading, onRetry: () => { loadedOnce.delete("valLoading"); render(); }, actions: validationActions(authState) });
}

async function loadValidation() {
  const val = uiState.val || (uiState.val = newVal());
  val.error = null;
  try {
    [val.guide, val.me] = await Promise.all([api.validationGuide(), api.validationMe()]);
    const jobs = [api.listEngagements(), api.validationPanel()];
    if (val.me.can_manage) jobs.push(api.securityMembers());
    const [list, panel, members] = await Promise.all(jobs);
    val.list = list; val.panel = panel; val.members = members ? members.filter((m) => m.status === "ACTIVE") : [];
    if (val.detailId) val.detail = await api.getEngagement(val.detailId);
  } catch (err) {
    val.error = err.message || "Professional validation could not be loaded.";
  }
}

function validationActions(authState) {
  const val = uiState.val;
  const reload = async () => { await loadValidation(authState); };
  /** Runs one action; a failure is shown on the page, never swallowed. */
  const run = async (fn, okNotice) => {
    val.error = null; val.notice = null; val.busy = true; render();
    try { await fn(); if (okNotice) val.notice = okNotice; } catch (err) { val.error = err.message || "That did not work."; }
    val.busy = false; render();
  };
  const refreshDetail = async () => { val.detail = await api.getEngagement(val.detailId); val.list = await api.listEngagements(); };
  /** Server actions return the engagement without the live data comparison; keep the last comparison for the same snapshot so the line does not flicker. */
  const keep = (d) => { const prev = val.detail; if (d && prev && d.snapshot_is_current == null && prev.snapshot_hash === d.snapshot_hash) d.snapshot_is_current = prev.snapshot_is_current; return d; };
  const stageIds = () => ((val.guide && val.guide.stages) || []).map((s) => s.id);
  return {
    setTab: (t) => { val.tab = t; val.detailId = null; val.detail = null; val.statement = null; val.form = null; val.error = null; val.notice = null; render(); reload().then(render, render); },
    openDetail: async (id) => {
      val.detailId = id; val.detail = null; val.statement = null; val.form = null; val.error = null; val.notice = null; render();
      try { val.detail = await api.getEngagement(id); if (val.detail.statement) val.statement = await api.validationStatement(id); } catch (err) { val.error = err.message; }
      render();
    },
    closeDetail: () => { val.detailId = null; val.detail = null; val.statement = null; val.form = null; val.error = null; render(); reload().then(render, render); },
    startForm: (kind, f, extra) => { val.form = { kind, f: { ...f }, ...(extra || {}) }; val.error = null; render(); },
    cancelForm: () => { val.form = null; render(); },
    formChange: (k, v) => { if (val.form) val.form.f[k] = v; },
    toggleStage: (id, on) => {
      const cur = new Set(val.form.f.stages || stageIds());
      if (on) cur.add(id); else cur.delete(id);
      val.form.f.stages = stageIds().filter((x) => cur.has(x));
    },
    toggleSpecialism: (sp, on) => {
      const cur = new Set(val.form.f.specialisms || []); if (on) cur.add(sp); else cur.delete(sp);
      val.form.f.specialisms = [...cur];
    },
    confirmChange: (k, on) => { val.form.f.confirmations = { ...(val.form.f.confirmations || {}), [k]: on }; },
    // panel
    addReviewer: () => run(async () => { await api.addReviewer(reviewerBody(val.form.f)); val.form = null; await reload(); }, "Reviewer added. Their credentials are recorded as declared until someone verifies them."),
    submitVerify: (accepted) => run(async () => {
      const { rid, idx, f } = val.form;
      await api.verifyCredential(rid, idx, { accepted, method: (f.method || "").trim(), note: (f.note || "").trim() });
      val.form = null; val.panel = await api.validationPanel();
    }, accepted ? "Recorded as verified." : "Recorded as not confirmed."),
    setActive: (id, on) => run(async () => { await api.setReviewerActive(id, on); val.panel = await api.validationPanel(); }),
    // engagements
    createEngagement: () => run(async () => {
      const e = await api.createEngagement(engagementBody(val.form.f, stageIds()));
      val.form = null; val.list = await api.listEngagements(); val.detailId = e.id; val.detail = await api.getEngagement(e.id);
    }, "Engagement created as a draft. Assign reviewers, then open it for review."),
    openEngagement: () => run(async () => { val.detail = keep(await api.openEngagement(val.detailId)); val.list = await api.listEngagements(); }, "Open for review."),
    refreshSnapshot: () => run(async () => { val.detail = keep(await api.refreshEngagementSnapshot(val.detailId)); }, "Snapshot refreshed to today's data."),
    withdraw: () => run(async () => { val.detail = keep(await api.withdrawEngagement(val.detailId, (val.form.f.reason || "").trim())); val.form = null; val.list = await api.listEngagements(); }, "Engagement withdrawn."),
    completeEngagement: () => run(async () => {
      val.detail = keep(await api.completeEngagement(val.detailId)); val.statement = await api.validationStatement(val.detailId); val.list = await api.listEngagements();
    }, "Completed. The statement below has a fingerprint so any later change is detectable."),
    checkStatement: () => run(async () => { val.statement = await api.validationStatement(val.detailId); }, "Statement checked."),
    assign: (stage) => run(async () => { val.detail = keep(await api.assignReviewer(val.detailId, stage, val.form.f.reviewer_id)); val.form = null; }),
    unassign: (assignmentId) => run(async () => { val.detail = keep(await api.unassignReviewer(val.detailId, assignmentId)); }),
    // reviewer actions
    submitDeclaration: () => run(async () => {
      const { reviewerId, mode, f } = val.form;
      const all = ["no_financial_interest", "not_involved_in_preparing_records", "no_close_personal_relationship", "no_other_threat_to_objectivity"].every((k) => (f.confirmations || {})[k]);
      val.detail = keep(await api.declareIndependence(val.detailId, declarationBody(reviewerId, { ...f, independent: all }, mode))); val.form = null;
    }, "Declaration recorded."),
    startReview: (stage, reviewerId, mode) => {
      const d = val.detail;
      const draft = d.reviews.find((r) => r.stage === stage && r.reviewer_id === reviewerId && r.status === "DRAFT");
      const signed = d.reviews.filter((r) => r.stage === stage && r.reviewer_id === reviewerId && r.status === "SIGNED").sort((a, b) => b.version - a.version)[0];
      val.form = { kind: "review", stage, reviewerId, mode, f: reviewForm(draft || signed || null) }; val.error = null; render();
    },
    addObs: () => { val.form.f.observations.push(emptyObservation()); render(); },
    removeObs: (i) => { val.form.f.observations.splice(i, 1); render(); },
    obsChange: (i, k, v) => { val.form.f.observations[i][k] = v; },
    saveReview: (sign) => run(async () => {
      const { stage, reviewerId, mode, f } = val.form;
      let d = await api.saveReview(val.detailId, reviewBody(stage, reviewerId, f, mode));
      if (sign) {
        const draft = d.reviews.find((r) => r.stage === stage && r.reviewer_id === reviewerId && r.status === "DRAFT");
        d = await api.signReview(val.detailId, draft.id);
      }
      val.detail = keep(d); val.form = null; val.list = await api.listEngagements();
    }, sign ? "Signed. This review can no longer be edited; a new version would replace it." : "Draft saved. It does not count until signed."),
    submitResponse: () => run(async () => {
      const { reviewId, obsId, f } = val.form;
      val.detail = keep(await api.respondToObservation(val.detailId, reviewId, obsId, f.status || "ACCEPTED", (f.note || "").trim())); val.form = null;
    }, "Response recorded."),
  };
}

// ----------------------------------------------------------------------
// Real Pilot page
// ----------------------------------------------------------------------
function newPilot() {
  return { tab: null, guide: null, me: null, pilotId: null, current: null, results: null, logs: null, snapshots: null, eligible: null, mySurvey: null, report: null,
    form: null, busy: false, notice: null, error: null };
}

function renderPilotPage(authState) {
  if (!uiState.pilot) uiState.pilot = newPilot();
  once("pilotLoading", () => loadPilot());
  return Pilot({ pilot: uiState.pilot, loading: uiState.pilotLoading, onRetry: () => { loadedOnce.delete("pilotLoading"); render(); }, actions: pilotActions(authState) });
}

async function loadPilot() {
  const pilot = uiState.pilot || (uiState.pilot = newPilot());
  pilot.error = null;
  try {
    [pilot.guide, pilot.me] = await Promise.all([api.pilotGuide(), api.pilotMe()]);
    const m = pilot.me.membership;
    if (m && m.role === "CLIENT") { pilot.pilotId = m.pilot_id; pilot.current = m.pilot; }
    else {
      const list = pilot.me.can_manage ? await api.listPilots() : ((m && m.pilots) || []);
      const pick = list.find((x) => x.id === pilot.pilotId) || list[0] || null;
      pilot.pilotId = pick ? pick.id : null;
      pilot.current = pick ? (pilot.me.can_manage ? await api.getPilot(pick.id) : pick) : null;
    }
    pilot.results = null; pilot.snapshots = null; pilot.report = null;
    if (pilot.pilotId) {
      const jobs = [api.pilotLogs(pilot.pilotId), api.myPilotSurvey(pilot.pilotId)];
      if (pilot.me.can_manage && !(m && m.role === "CLIENT")) jobs.push(api.pilotSnapshots(pilot.pilotId));
      const [logs, mine, snaps] = await Promise.all(jobs);
      pilot.logs = logs; pilot.mySurvey = mine; pilot.snapshots = snaps || null;
      if (pilot.me.can_manage && pilot.current.clients && pilot.current.clients.some((c) => c.active)) pilot.results = await api.pilotResults(pilot.pilotId);
    }
  } catch (err) {
    pilot.error = err.message || "The pilot could not be loaded.";
  }
}

function pilotActions(authState) {
  const pilot = uiState.pilot;
  const run = async (fn, okNotice) => {
    pilot.error = null; pilot.notice = null; pilot.busy = true; render();
    try { await fn(); if (okNotice) pilot.notice = okNotice; } catch (err) { pilot.error = err.message || "That did not work."; }
    pilot.busy = false; render();
  };
  const reload = async () => { await loadPilot(); };
  const isFirm = () => !(pilot.me && pilot.me.membership && pilot.me.membership.role === "CLIENT");
  return {
    setTab: (t) => { pilot.tab = t; pilot.form = null; pilot.error = null; pilot.notice = null; render(); },
    startForm: (kind, f) => {
      const defaults = { pilot: emptyPilotForm(), time: { performed_on: today() }, issue: { severity: "LOW" }, passport: {}, survey: { round: "GENERAL", scores: {} } };
      pilot.form = { kind, f: { ...(defaults[kind] || {}), ...(f || {}) } }; pilot.error = null; pilot.notice = null; render();
    },
    cancelForm: () => { pilot.form = null; render(); },
    formChange: (k, v) => { if (pilot.form) pilot.form.f[k] = v; },
    createPilot: () => run(async () => {
      const p = await api.createPilot(pilotBody(pilot.form.f)); pilot.form = null; pilot.pilotId = p.id; await reload(); pilot.tab = "clients";
    }, "Pilot created. Add your first client organisation next."),
    setStatus: (s) => run(async () => { pilot.current = await api.setPilotStatus(pilot.pilotId, s); await reload(); }, s === "ACTIVE" ? "The pilot is now active." : "The pilot is completed."),
    saveTargets: () => run(async () => {
      const t = {}; for (const [k, v] of Object.entries(pilot.form.f)) { const n = Number(String(v).trim()); if (!String(v).trim() || Number.isNaN(n)) throw new Error("Every target must be a number."); t[k] = n; }
      pilot.current = await api.updatePilotTargets(pilot.pilotId, t); pilot.form = null; if (pilot.results) pilot.results = await api.pilotResults(pilot.pilotId);
    }, "Targets saved."),
    // clients
    startClientForm: () => run(async () => { pilot.eligible = await api.pilotEligible(); pilot.form = { kind: "client", f: emptyClientForm() }; }),
    addClient: () => run(async () => {
      const bad = clientFormProblem(pilot.form.f); if (bad) throw new Error(bad);
      pilot.current = await api.addPilotClient(pilot.pilotId, clientBody(pilot.form.f)); pilot.form = null; pilot.results = await api.pilotResults(pilot.pilotId);
    }, "Client added. Its consent reference is recorded in both organisations' audit trails."),
    removeClient: () => run(async () => {
      const { org, reason } = pilot.form.f; pilot.current = await api.removePilotClient(pilot.pilotId, org, (reason || "").trim()); pilot.form = null;
      pilot.results = pilot.current.clients.some((c) => c.active) ? await api.pilotResults(pilot.pilotId) : null;
    }, "Client removed. Its data no longer counts in any result."),
    leave: () => run(async () => { await api.leavePilot(pilot.pilotId, (pilot.form.f.reason || "").trim()); pilot.form = null; pilot.tab = null; await reload(); }, "Your organisation has left the pilot."),
    // results
    loadResults: () => run(async () => { pilot.results = await api.pilotResults(pilot.pilotId); }),
    takeSnapshot: () => run(async () => { await api.takePilotSnapshot(pilot.pilotId); pilot.snapshots = await api.pilotSnapshots(pilot.pilotId); }, "Snapshot taken."),
    buildReport: () => run(async () => { pilot.report = await api.pilotReport(pilot.pilotId); pilot.results = pilot.report.results; }),
    downloadReport: () => { if (pilot.report) download(`${(pilot.current.name || "pilot").replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-report.md`, pilot.report.markdown); },
    // recording
    saveLog: (which) => run(async () => {
      const f = pilot.form.f, firm = isFirm(), id = pilot.pilotId;
      if (firm && !f.client_org_id) throw new Error("Choose which client this is about.");
      if (which === "time") await api.logPilotTime(id, timeBody(f, firm));
      else if (which === "issue") await api.logPilotIssue(id, issueBody(f, firm));
      else await api.logPilotPassportUse(id, passportUseBody(f, firm));
      pilot.form = null; pilot.logs = await api.pilotLogs(id);
      if (pilot.results && firm) pilot.results = await api.pilotResults(id);
    }, "Saved."),
    resolveIssue: () => run(async () => { const { id, resolution } = pilot.form.f; await api.resolvePilotIssue(pilot.pilotId, id, (resolution || "").trim()); pilot.form = null; pilot.logs = await api.pilotLogs(pilot.pilotId); }, "Marked resolved."),
    // survey
    startSurvey: () => { pilot.form = { kind: "survey", f: { round: "GENERAL", scores: {}, comment: "" } }; pilot.error = null; pilot.notice = null; render(); },
    surveyScore: (k, v) => { if (pilot.form) pilot.form.f.scores[k] = v; },
    submitSurvey: () => run(async () => {
      const bad = surveyProblem(pilot.form.f); if (bad) throw new Error(bad);
      await api.submitPilotSurvey(pilot.pilotId, surveyBody(pilot.form.f)); pilot.form = null; pilot.mySurvey = await api.myPilotSurvey(pilot.pilotId);
      if (pilot.results && isFirm() && pilot.me.can_manage) pilot.results = await api.pilotResults(pilot.pilotId);
    }, "Thank you. Your answers are recorded."),
  };
}

// ----------------------------------------------------------------------
// ASAVEXA Network page
// ----------------------------------------------------------------------
function newProof() { return { period_id: "", report: "balance_sheet", graph: null, arch: null, open: {}, busy: false, error: null }; }

function renderProofPage(authState) {
  if (!uiState.proof) uiState.proof = newProof();
  once("proofLoading", () => loadProof());
  return Proof({ proof: uiState.proof, periods: uiState.periods, loading: uiState.proofLoading, onRetry: () => { loadedOnce.delete("proofLoading"); render(); }, actions: proofActions() });
}

async function loadProof() {
  const proof = uiState.proof || (uiState.proof = newProof());
  proof.error = null;
  try {
    uiState.periods = await api.listPeriods();
    const last = uiState.periods[uiState.periods.length - 1];
    if (!proof.period_id && last) proof.period_id = last.id;
  } catch (err) {
    proof.error = err.message || "The periods could not be loaded.";
  }
}

function proofActions() {
  const proof = uiState.proof;
  const run = async (fn) => { proof.error = null; proof.busy = true; render(); try { await fn(); } catch (err) { proof.error = err.message || "That did not work."; } proof.busy = false; render(); };
  return {
    setPeriod: (id) => { proof.period_id = id; proof.graph = null; proof.open = {}; render(); },
    setReport: (r) => { proof.report = r; proof.graph = null; proof.open = {}; render(); },
    toggle: (id) => { proof.open[id] = !proof.open[id]; render(); },
    build: () => run(async () => { proof.graph = await api.proofGraph(proof.period_id, proof.report); proof.open = {}; }),
    checkArchitecture: () => run(async () => { proof.arch = await api.proofArchitecture(); }),
  };
}

function newEr() { return { period_id: "", report: "income_statement", review: null, cases: [], members: [], openCase: null, forms: {}, busy: false, error: null, notice: null }; }

function renderEvidenceReviewPage(authState) {
  if (!uiState.er) uiState.er = newEr();
  once("erLoading", () => loadEr(authState));
  return EvidenceReview({ er: uiState.er, periods: uiState.periods, me: authState.user && authState.user.id, role: authState.role, loading: uiState.erLoading,
    onRetry: () => { loadedOnce.delete("erLoading"); render(); }, actions: erActions() });
}

async function loadEr(authState) {
  const er = uiState.er || (uiState.er = newEr());
  er.error = null;
  try {
    uiState.periods = await api.listPeriods();
    const last = uiState.periods[uiState.periods.length - 1];
    if (!er.period_id && last) er.period_id = last.id;
    er.cases = (await api.evidenceReviewCases()).cases;
    try { er.rules = await api.evidenceReviewRules(); } catch (_) { er.rules = null; }
    try { er.members = await api.listMembers(authState.organisationId); } catch (_) { er.members = []; }
  } catch (err) {
    er.error = err.message || "Evidence Review could not be loaded.";
  }
}

function erActions() {
  const er = uiState.er;
  const run = async (fn, notice) => { er.error = null; er.notice = null; er.busy = true; render(); try { await fn(); if (notice) er.notice = notice; } catch (err) { er.error = err.message || "That did not work."; } er.busy = false; render(); };
  const refresh = async () => { er.cases = (await api.evidenceReviewCases()).cases; er.rules = await api.evidenceReviewRules(); };
  const form = (id) => er.forms[id] || {};
  const after = async (c) => { await refresh(); er.openCase = c.id; er.forms[c.id] = {}; };
  return {
    setPeriod: (id) => { er.period_id = id; er.review = null; render(); },
    setReport: (r) => { er.report = r; er.review = null; render(); },
    setForm: (id, k, v) => { er.forms[id] = { ...(er.forms[id] || {}), [k]: v }; },
    toggleCase: (id) => { er.openCase = er.openCase === id ? null : id; render(); },
    startRuleDraft: () => { er.ruleDraft = draftFromRules(er.rules.active.rules); er.ruleReason = ""; er.ruleError = null; render(); },
    cancelRuleDraft: () => { er.ruleDraft = null; er.ruleError = null; render(); },
    setRuleField: (i, k, v, rerender) => { er.ruleDraft[i] = { ...er.ruleDraft[i], [k]: v }; if (rerender) render(); },
    toggleRuleValue: (i, field, v) => { er.ruleDraft[i] = toggleValue(er.ruleDraft[i], field, v); render(); },
    addRule: () => { er.ruleDraft = [...er.ruleDraft, newRule(er.ruleDraft)]; render(); },
    removeRule: (i) => { er.ruleDraft = er.ruleDraft.filter((_, j) => j !== i); render(); },
    setRuleReason: (v) => { er.ruleReason = v; },
    setRuleNote: (v) => { er.ruleNote = v; },
    proposeRules: () => { const p = rulesPayload(er.ruleDraft, er.ruleReason); if (p.problem) { er.ruleError = p.problem; render(); return; }
      return run(async () => { await api.proposeEvidenceReviewRules(p.body); er.ruleDraft = null; er.ruleError = null; await refresh(); }, "Sent for approval. A different person must approve it before it applies."); },
    approveRules: (v) => run(async () => { await api.approveEvidenceReviewRules(v, { note: er.ruleNote || "" }); er.ruleNote = ""; await refresh(); }, "Approved. These rules now apply to new reviews."),
    rejectRules: (v) => { if (!(er.ruleNote || "").trim()) { er.error = "Say why you are rejecting it (use the note box)."; render(); return; }
      return run(async () => { await api.rejectEvidenceReviewRules(v, { reason: er.ruleNote }); er.ruleNote = ""; await refresh(); }, "Rejected. The rules in use did not change."); },
    run: () => run(async () => { er.review = await api.evidenceReview(er.period_id, er.report); }),
    openCase: () => run(async () => { const c = await api.openEvidenceReviewCase({ period_id: er.period_id, report: er.report }); await after(c); }, "Case raised."),
    plan: (id) => run(async () => { const f = form(id); await after(await api.planEvidenceReviewAction(id, { action: f.action || "", owner: f.owner || "", due_date: f.due_date || null })); }, "Action planned."),
    complete: (id) => run(async () => { const f = form(id); await after(await api.completeEvidenceReviewAction(id, { note: f.note || "", evidence_ref: f.evidence_ref || null })); }, "Recorded as done. Someone independent must now verify it."),
    verify: (id) => { const v = verifyPayload(form(id)); if (v.problem) { er.error = v.problem; er.notice = null; render(); return; }
      return run(async () => { const c = await api.verifyEvidenceReviewOutcome(id, v.body); await after(c); er.notice = c.status === "VERIFIED" ? "Verified: the figure was re-measured and no gaps remain." : "Not verified: gaps remain, so the action goes back to its owner."; }); },
    recheck: (id) => run(async () => { const c = await api.recheckEvidenceReviewCase(id); await after(c); er.notice = c.status === "REOPENED" ? "Gaps have returned, so the case was reopened." : "Re-checked: still fully supported."; }),
  };
}

function newSr() { return { coverage: null, sources: [], frameworks: [], jurisdictions: [], form: { ...EMPTY_FORM }, formError: null, reasons: {}, busy: false, error: null, notice: null }; }

function renderStandardsRegistryPage(authState) {
  if (!uiState.sr) uiState.sr = newSr();
  once("srLoading", () => loadSr());
  return StandardsRegistry({ sr: uiState.sr, me: authState.user && authState.user.id, role: authState.role, loading: uiState.srLoading,
    onRetry: () => { loadedOnce.delete("srLoading"); render(); }, actions: srActions() });
}

async function loadSr() {
  const sr = uiState.sr || (uiState.sr = newSr());
  sr.error = null;
  try {
    const [cov, src, cat] = await Promise.all([api.standardsRegistryCoverage(), api.standardsRegistrySources(), api.standardsCatalog()]);
    sr.coverage = cov; sr.sources = src.sources; sr.frameworks = cat.frameworks; sr.jurisdictions = cat.jurisdictions;
  } catch (err) {
    sr.error = err.message || "The Standards Registry could not be loaded.";
  }
}

function srActions() {
  const sr = uiState.sr;
  const run = async (fn, notice) => { sr.error = null; sr.notice = null; sr.busy = true; render(); try { await fn(); if (notice) sr.notice = notice; } catch (err) { sr.error = err.message || "That did not work."; } sr.busy = false; render(); };
  const reload = async () => { const [cov, src] = await Promise.all([api.standardsRegistryCoverage(), api.standardsRegistrySources()]); sr.coverage = cov; sr.sources = src.sources; };
  return {
    setForm: (k, v) => { sr.form = { ...sr.form, [k]: v }; sr.formError = null; },
    setReason: (id, v) => { sr.reasons[id] = v; },
    add: () => {
      const problem = formProblem(sr.form);
      if (problem) { sr.formError = problem; render(); return; }
      return run(async () => { const body = { ...sr.form, jurisdiction: sr.form.jurisdiction || null }; await api.addStandardsSource(body); sr.form = { ...EMPTY_FORM }; await reload(); }, "Source added as a draft. Submit it so someone else can review it.");
    },
    act: (id, action) => run(async () => {
      const reason = (sr.reasons[id] || "").trim();
      const body = action === "send-back" || action === "withdraw" ? { reason } : action === "approve" ? { note: reason } : {};
      await api.standardsSourceAction(id, action, body); sr.reasons[id] = ""; await reload();
    }, action === "approve" ? "Approved." : action === "submit" ? "Submitted for review." : action === "send-back" ? "Sent back to draft." : "Withdrawn."),
  };
}

function renderAssurancePage(authState) {
  if (!uiState.as) uiState.as = { vocabulary: null, summary: null, error: null };
  once("asLoading", () => loadAs());
  return Assurance({ as: uiState.as, loading: uiState.asLoading, onRetry: () => { loadedOnce.delete("asLoading"); render(); },
    onRefresh: () => { uiState.asLoading = false; loadedOnce.delete("asLoading"); render(); } });
}

async function loadAs() {
  const as = uiState.as || (uiState.as = { vocabulary: null, summary: null, error: null });
  as.error = null;
  try {
    const [v, s] = await Promise.all([api.assuranceVocabulary(), api.assuranceSummary()]);
    as.vocabulary = v; as.summary = s;
  } catch (err) {
    as.error = err.message || "Assurance could not be loaded.";
  }
}

// ----------------------------------------------------------------------
// Organisation type and workspaces (Stage 15)
// ----------------------------------------------------------------------
/** Loads this organisation's set-up once per organisation, for the menu. A failure leaves the full menu in place and is not retried in a loop. */
function ensureEntityConfig(authState) {
  const org = authState && authState.organisationId;
  if (!org || (uiState.entity && uiState.entity.org === org)) return;
  const rec = { org, cfg: null };
  uiState.entity = rec;
  Promise.resolve().then(() => api.entityConfig()).then((c) => { rec.cfg = c; }).catch(() => {}).finally(() => { if (uiState.entity === rec) render(); });
}

function newEc() { return { catalog: null, config: null, workspaces: [], form: null, formError: null, busy: false, error: null, notice: null }; }

function renderEntityConfigPage(authState) {
  if (!uiState.ec) uiState.ec = newEc();
  once("ecLoading", () => loadEc(authState));
  return EntityConfig({ ec: uiState.ec, role: authState.role, loading: uiState.ecLoading, onRetry: () => { uiState.ecLoading = false; loadedOnce.delete("ecLoading"); render(); }, actions: ecActions(authState) });
}

async function loadEc(authState) {
  const ec = uiState.ec || (uiState.ec = newEc());
  ec.error = null;
  try {
    const [catalog, config, ws, prof] = await Promise.all([api.entityCatalog(), api.entityConfig(), api.workspaces(), api.getOrganisationProfile().catch(() => null)]);
    ec.catalog = catalog; ec.config = config; ec.workspaces = ws.workspaces;
    ec.form = formFromConfig(config, catalog, ws.workspaces, prof && prof.organisation_type);
    if (uiState.entity && uiState.entity.org === authState.organisationId) uiState.entity.cfg = config;
  } catch (err) {
    ec.error = err.message || "The organisation set-up could not be loaded.";
  }
}

function ecActions(authState) {
  const ec = uiState.ec;
  return {
    setField: (k, v) => { ec.form = { ...ec.form, [k]: v }; ec.formError = null; if (k === "entity_type") { ec.form.subtype = ""; if (v) ec.form.enabled = suggestedFor(ec.catalog, v, ec.workspaces); } if (k === "entity_type" || k === "subtype") render(); },
    toggle: (id) => { ec.form = { ...ec.form, enabled: toggleWorkspace(ec.form.enabled, id) }; render(); },
    useSuggested: () => { ec.form = { ...ec.form, enabled: suggestedFor(ec.catalog, ec.form.entity_type, ec.workspaces) }; render(); },
    save: async () => {
      const r = configPayload(ec.form, ec.config.configured);
      if (r.problem) { ec.formError = r.problem; render(); return; }
      ec.busy = true; ec.error = null; ec.notice = null; render();
      try {
        const cfg = await api.saveEntityConfig(r.body);
        ec.config = cfg; ec.form = formFromConfig(cfg, ec.catalog, ec.workspaces, null); ec.notice = "Saved. The menu now shows the chosen workspaces. Nobody's access has changed.";
        uiState.entity = { org: authState.organisationId, cfg };
      } catch (err) { ec.error = err.message || "That did not work."; }
      ec.busy = false; render();
    },
  };
}


// ----------------------------------------------------------------------
// Proof Links (Stage 13): stored links between records
// ----------------------------------------------------------------------
function newPl() {
  return { vocabulary: null, choices: {}, find: { type: "", id: "", depth: 1 }, graph: null, form: { ...EMPTY_LINK }, gap: { ...EMPTY_GAP }, reasons: {}, formError: null, gapError: null, busy: false, error: null, notice: null };
}

function renderProofLinksPage(authState) {
  if (!uiState.pl) uiState.pl = newPl();
  once("plLoading", () => loadPl());
  return ProofLinks({ pl: uiState.pl, me: authState.user && authState.user.id, role: authState.role, loading: uiState.plLoading || !uiState.pl.vocabulary && !uiState.pl.error,
    onRetry: () => { uiState.plLoading = false; loadedOnce.delete("plLoading"); render(); }, actions: plActions() });
}

async function loadPl() {
  const pl = uiState.pl || (uiState.pl = newPl());
  pl.error = null;
  try { pl.vocabulary = await api.proofLinkVocabulary(); } catch (err) { pl.error = err.message || "Proof Links could not be loaded."; }
}

function plActions() {
  const pl = uiState.pl;
  const run = async (fn, notice) => { pl.error = null; pl.notice = null; pl.busy = true; render(); try { await fn(); if (notice) pl.notice = notice; } catch (err) { pl.error = err.message || "That did not work."; } pl.busy = false; render(); };
  const choose = async (type) => { if (type && !pl.choices[type]) { try { pl.choices[type] = (await api.proofLinkChoices(type)).choices; } catch (_) { pl.choices[type] = []; } } };
  const reload = async () => { if (pl.graph) pl.graph = await api.proofLinkGraph(pl.graph.focus.type, pl.graph.focus.id, pl.graph.depth || 1); };
  return {
    setFind: (k, v) => { pl.find = { ...pl.find, [k]: v }; if (k === "type") { pl.find.id = ""; choose(v).then(() => render()); } render(); },
    look: () => run(async () => { pl.graph = await api.proofLinkGraph(pl.find.type, pl.find.id, pl.find.depth); pl.gap = { ...EMPTY_GAP }; pl.gapError = null; }),
    setForm: (k, v) => {
      pl.form = { ...pl.form, [k]: v }; pl.formError = null;
      if (k === "from_type") { pl.form.from_id = ""; pl.form.to_type = ""; pl.form.to_id = ""; pl.form.relation = ""; }
      if (k === "to_type") { pl.form.to_id = ""; if (v && !relationsFor(pl.vocabulary, pl.form.from_type, v).some((r) => r.code === pl.form.relation)) pl.form.relation = ""; }
      if (k === "relation" && v) { const r = relationsFor(pl.vocabulary, pl.form.from_type, "").find((x) => x.code === v); if (r && pl.form.to_type && !r.to.includes(pl.form.to_type)) { pl.form.to_type = ""; pl.form.to_id = ""; } }
      if (k === "from_type" || k === "to_type") choose(v).then(() => render());
      if (k !== "note") render();
    },
    addLink: () => {
      const r = linkPayload(pl.form);
      if (r.problem) { pl.formError = r.problem; render(); return; }
      return run(async () => { await api.addProofLink(r.body); pl.form = { ...EMPTY_LINK }; pl.formError = null; await reload(); }, "Link recorded. A different person can now confirm it.");
    },
    setReason: (id, v) => { pl.reasons[id] = v; },
    act: (id, kind) => {
      const reason = (pl.reasons[id] || "").trim();
      if (needsReason(kind) && !reason) { pl.error = "Give a reason first."; render(); return; }
      return run(async () => { await api.proofLinkAction(id, kind, kind === "confirm" ? { note: reason } : { reason }); pl.reasons[id] = ""; await reload(); }, ACTION_NOTICE[kind]);
    },
    setGap: (k, v) => { pl.gap = { ...pl.gap, [k]: v }; pl.gapError = null; if (k === "relation") pl.gap.expected_type = ""; if (k !== "note") render(); },
    addGap: () => {
      const r = gapPayload(pl.graph && pl.graph.focus, pl.gap);
      if (r.problem) { pl.gapError = r.problem; render(); return; }
      return run(async () => { await api.addProofLinkGap(r.body); pl.gap = { ...EMPTY_GAP }; await reload(); }, "Noted as missing. A different person can waive it.");
    },
    waive: (id) => {
      const reason = (pl.reasons[id] || "").trim();
      if (!reason) { pl.error = "Give a reason first."; render(); return; }
      return run(async () => { await api.waiveProofLinkGap(id, { reason }); pl.reasons[id] = ""; await reload(); }, "Waived.");
    },
  };
}


function newAg() { return { agents: [], decisions: [], policy: [], catalog: [], members: [], form: { ...EMPTY_AGENT }, formError: null, request: { agent_id: "", action: "", subject: "" }, reasons: {}, busy: false, error: null, notice: null }; }

function renderAgentsPage(authState) {
  if (!uiState.ag) uiState.ag = newAg();
  once("agLoading", () => loadAg(authState));
  return Agents({ ag: uiState.ag, me: authState.user && authState.user.id, role: authState.role, loading: uiState.agLoading, onRetry: () => { loadedOnce.delete("agLoading"); render(); }, actions: agActions(authState) });
}

async function loadAg(authState) {
  const ag = uiState.ag || (uiState.ag = newAg());
  ag.error = null;
  try {
    const [cat, list, dec] = await Promise.all([api.agentCatalog(), api.agents(), api.agentDecisions()]);
    ag.catalog = cat.actions; ag.policy = cat.policy; ag.agents = list.agents; ag.decisions = dec.decisions;
    try { ag.members = await api.listMembers(authState.organisationId); } catch (_) { ag.members = []; }
  } catch (err) {
    ag.error = err.message || "Agents could not be loaded.";
  }
}

function agActions() {
  const ag = uiState.ag;
  const run = async (fn, notice) => { ag.error = null; ag.notice = null; ag.busy = true; render(); try { await fn(); if (notice) ag.notice = notice; } catch (err) { ag.error = err.message || "That did not work."; } ag.busy = false; render(); };
  const reload = async () => { const [cat, list, dec] = await Promise.all([api.agentCatalog(), api.agents(), api.agentDecisions()]); ag.catalog = cat.actions; ag.policy = cat.policy; ag.agents = list.agents; ag.decisions = dec.decisions; };
  return {
    setForm: (k, v) => { ag.form = { ...ag.form, [k]: v }; ag.formError = null; },
    toggleAction: (a) => { const s = new Set(ag.form.actions); s.has(a) ? s.delete(a) : s.add(a); ag.form = { ...ag.form, actions: [...s] }; },
    setReason: (id, v) => { ag.reasons[id] = v; },
    setRequest: (k, v) => { ag.request = { ...ag.request, [k]: v }; if (k !== "subject") render(); },
    propose: () => {
      const problem = agentFormProblem(ag.form);
      if (problem) { ag.formError = problem; render(); return; }
      return run(async () => { await api.proposeAgent(ag.form); ag.form = { ...EMPTY_AGENT, actions: [] }; await reload(); }, "Agent proposed. A different person must activate it.");
    },
    agentAct: (id, k) => run(async () => { const reason = (ag.reasons[id] || "").trim(); await api.agentAction(id, k, k === "activate" ? { note: reason } : { reason }); ag.reasons[id] = ""; await reload(); }, k === "activate" ? "Agent activated." : k === "suspend" ? "Agent suspended." : "Agent retired."),
    tighten: (action, decision) => run(async () => { await api.tightenAgentPolicy({ action, decision }); await reload(); }, "Rule made stricter."),
    ask: () => run(async () => { const d = await api.requestAgentDecision(ag.request); ag.request = { agent_id: "", action: "", subject: "" }; await reload(); ag.notice = d.decision === "ALLOW" ? "Allowed: no approval needed." : d.decision === "REQUIRE_APPROVAL" ? "Needs approval: someone else must approve it." : "Refused: " + d.reason; }),
    resolve: (id, approve) => run(async () => { await api.resolveAgentDecision(id, { approve, note: (ag.reasons[id] || "").trim() }); ag.reasons[id] = ""; await reload(); }, approve ? "Approved. It can be used once." : "Rejected."),
  };
}





// ----------------------------------------------------------------------
// Professional Workspaces + Financial Analysis
// ----------------------------------------------------------------------
function renderWorkspacesPage(authState, nav) {
  if (!uiState.ws) uiState.ws = { data: null, error: null };
  once("wsLoading", () => loadWorkspaces());
  return Workspaces({ data: uiState.ws.data, loading: uiState.wsLoading, error: uiState.ws.error, role: authState.role, onOpen: (path) => nav(path), onRetry: () => { loadedOnce.delete("wsLoading"); render(); } });
}

async function loadWorkspaces() {
  const ws = uiState.ws || (uiState.ws = { data: null, error: null });
  ws.error = null;
  try { ws.data = await api.workspaces(); } catch (err) { ws.error = err.message || "The workspaces could not be loaded."; }
}

function newAnalysis() {
  return { tab: "overview", period_id: "", loaded: {}, busy: false, error: null, notice: null, open: {}, periodNames: {},
    overview: null, ratios: null, variance: null, budget: null, budgetVar: null, config: null, scenarios: [], reports: [], report: null,
    noteFor: null, noteText: "", budgetForm: {}, budgetNote: "", scenarioForm: emptyScenario(), suggestNote: null, run: null, be: { fixed_costs: "", price: "", variable_cost: "" }, beResult: null,
    reportForm: emptyReportForm(), decisionNote: "", verify: null, tagDraft: {}, thresholdForm: { percent: "", amount: "" } };
}

function renderAnalysisPage(authState) {
  if (!uiState.an) uiState.an = newAnalysis();
  once("anLoading", () => loadAnalysisBase());
  return Analysis({ an: uiState.an, periods: uiState.periods, loading: uiState.anLoading, role: authState.role, userId: authState.user && authState.user.id, onRetry: () => { loadedOnce.delete("anLoading"); render(); }, actions: analysisActions() });
}

async function loadAnalysisBase() {
  const an = uiState.an || (uiState.an = newAnalysis());
  an.error = null;
  try {
    uiState.periods = await api.listPeriods();
    an.periodNames = Object.fromEntries(uiState.periods.map((p) => [p.id, p.name]));
    if (!an.period_id && uiState.periods.length) an.period_id = uiState.periods[uiState.periods.length - 1].id;
    await loadAnalysisTab();
  } catch (err) {
    an.error = err.message || "Financial Analysis could not be loaded.";
  }
}

/** Loads whatever the current tab needs. Called when the tab or period changes. */
async function loadAnalysisTab() {
  const an = uiState.an, id = an.period_id, tab = an.tab;
  if (!id && tab !== "reports" && tab !== "setup") return;
  an.busy = true; an.error = null; render();
  try {
    if (tab === "overview") an.overview = await api.analysisOverview(id);
    else if (tab === "ratios") an.ratios = await api.analysisRatios(id);
    else if (tab === "variance") { an.variance = await api.analysisVariance(id); an.config = an.config || await api.analysisConfig(); }
    else if (tab === "budget") {
      [an.budget, an.budgetVar, an.config] = await Promise.all([api.analysisBudget(id), api.analysisBudgetVariance(id), an.config ? Promise.resolve(an.config) : api.analysisConfig()]);
      an.budgetForm = { ...an.budget.lines }; an.budgetNote = "";
    } else if (tab === "forecast") an.scenarios = await api.analysisScenarios(id);
    else if (tab === "reports") { an.reports = await api.analysisReports(); if (id) an.scenarios = await api.analysisScenarios(id); }
    else if (tab === "setup") { an.config = await api.analysisConfig(); an.tagDraft = {}; an.thresholdForm = { percent: an.config.thresholds.percent, amount: an.config.thresholds.amount }; }
    an.loaded[tab] = true;
  } catch (err) {
    an.error = err.message || "That could not be loaded.";
  }
  an.busy = false; render();
}

function analysisActions() {
  const an = uiState.an;
  const run = async (fn, ok) => { an.error = null; an.notice = null; an.busy = true; render(); try { await fn(); if (ok) an.notice = ok; } catch (err) { an.error = err.message || "That did not work."; } an.busy = false; render(); };
  const reload = async (tab) => { an.loaded[tab] = false; await loadAnalysisTab(); };
  const fail = (m) => { an.error = m; render(); };
  return {
    setPeriod: (id) => { an.period_id = id; an.loaded = {}; an.overview = an.ratios = an.variance = an.budget = an.budgetVar = null; an.run = null; an.report = null; loadAnalysisTab(); },
    setTab: (t) => { an.tab = t; an.error = null; an.notice = null; an.report = null; if (!an.loaded[t]) loadAnalysisTab(); else render(); },
    toggle: (id) => { an.open[id] = !an.open[id]; render(); },
    // variance notes
    noteFor: (accountId) => { an.noteFor = accountId; an.noteText = ""; render(); },
    noteChange: (v) => { an.noteText = v; },
    saveNote: () => run(async () => { await api.addAnalysisComment({ period_id: an.period_id, account_id: an.noteFor, text: an.noteText }); an.noteFor = null; an.noteText = ""; an.variance = await api.analysisVariance(an.period_id); }, "Note saved."),
    // budget
    budgetChange: (id, v) => { an.budgetForm = { ...an.budgetForm, [id]: v }; },
    budgetNoteChange: (v) => { an.budgetNote = v; },
    saveBudget: () => {
      const problem = budgetProblem(an.budgetForm); if (problem) return fail(problem);
      return run(async () => { await api.saveAnalysisBudget(budgetBody(an.budgetForm, an.period_id, an.budgetNote)); await reload("budget"); }, "Budget saved.");
    },
    // forecast
    scenarioChange: (k, v) => { an.scenarioForm = { ...an.scenarioForm, [k]: v }; },
    fillFromActuals: () => run(async () => {
      const s = await api.analysisSuggest(an.period_id);
      const a = s.assumptions || s;
      an.scenarioForm = { ...an.scenarioForm, base_monthly_revenue: String(a.base_monthly_revenue ?? ""), base_monthly_expenses: String(a.base_monthly_expenses ?? ""), opening_cash: String(a.opening_cash ?? "") };
      an.suggestNote = [s.basis, s.opening_cash_note].filter(Boolean).join(" ") || null;
    }),
    editScenario: (id) => { const s = an.scenarios.find((x) => x.id === id); if (s) { an.scenarioForm = scenarioForm(s); render(); } },
    saveScenario: () => {
      const problem = scenarioProblem(an.scenarioForm); if (problem) return fail(problem);
      return run(async () => { const id = an.scenarioForm.id; await api.saveAnalysisScenario(scenarioBody(an.scenarioForm, an.period_id), id || null); an.scenarioForm = emptyScenario(); an.scenarios = await api.analysisScenarios(an.period_id); }, "Scenario saved.");
    },
    runScenario: (id) => run(async () => { an.run = await api.runAnalysisScenario(id); }),
    beChange: (k, v) => { an.be = { ...an.be, [k]: v }; },
    runBreakeven: () => run(async () => { an.beResult = await api.analysisBreakeven(an.be); }),
    // reports
    reportChange: (k, v) => { an.reportForm = { ...an.reportForm, [k]: v }; },
    reportScenario: (id, on) => { const cur = new Set(an.reportForm.scenario_ids); on ? cur.add(id) : cur.delete(id); an.reportForm = { ...an.reportForm, scenario_ids: [...cur] }; render(); },
    createReport: () => {
      const problem = reportProblem(an.reportForm); if (problem) return fail(problem);
      return run(async () => { an.report = await api.createAnalysisReport(reportBody(an.reportForm, an.period_id)); an.reportForm = emptyReportForm(); an.verify = null; an.reports = await api.analysisReports(); }, "Draft created.");
    },
    openReport: (id) => run(async () => { an.report = await api.analysisReport(id); an.verify = null; an.decisionNote = ""; }),
    closeReport: () => { an.report = null; an.verify = null; reload("reports"); },
    submitReport: () => run(async () => { an.report = await api.submitAnalysisReport(an.report.id); an.verify = null; }, "Submitted for review. The figures are now frozen."),
    verifyReport: () => run(async () => { an.verify = await api.verifyAnalysisReport(an.report.id); }),
    decisionChange: (v) => { an.decisionNote = v; },
    decide: (approve) => {
      if (!approve && an.decisionNote.trim().length < 3) return fail("Say why you are sending it back (at least 3 characters).");
      return run(async () => { an.report = approve ? await api.approveAnalysisReport(an.report.id, an.decisionNote) : await api.rejectAnalysisReport(an.report.id, an.decisionNote); an.decisionNote = ""; }, approve ? "Approved." : "Sent back.");
    },
    exportReport: () => run(async () => { const { blob, filename } = await api.exportAnalysisReport(an.report.id); saveBlob(blob, filename); }, "Downloaded."),
    // setup
    tagChange: (accountId, tag) => { an.tagDraft = { ...an.tagDraft, [accountId]: tag || null }; },
    thresholdChange: (k, v) => { an.thresholdForm = { ...an.thresholdForm, [k]: v }; },
    saveConfig: () => {
      const f = an.thresholdForm;
      if (!/^\d+(\.\d+)?$/.test(String(f.percent).trim()) || !/^\d+(\.\d+)?$/.test(String(f.amount).trim())) return fail("The thresholds must be positive numbers.");
      return run(async () => { await api.saveAnalysisConfig({ tags: an.tagDraft, thresholds: { percent: String(f.percent).trim(), amount: String(f.amount).trim() } }); an.loaded = {}; await loadAnalysisTab(); }, "Setup saved.");
    },
  };
}


// ----------------------------------------------------------------------
// Tax Compliance
// ----------------------------------------------------------------------
function newTax() {
  const t = new Date(), y = t.getFullYear();
  return { tab: "countries", busy: false, error: null, notice: null, loaded: {}, overview: null, countries: null, q: "", region: "", regDraft: {}, countryList: [], options: null,
    rules: [], ruleFilter: "", rule: null, form: null, decisionNote: "", liveRules: [], periods: [], calcForm: { rule_id: "", amount: "", date: todayIso(t), inclusive: false, period_id: "", kind: "revenue" }, calc: null, ledgerNote: null, ledgerBasis: null, history: [],
    cal: { start: `${y}-01-01`, end: `${y}-12-31`, data: null }, refDraft: {} };
}

function renderTaxPage(authState) {
  if (!uiState.tx) uiState.tx = newTax();
  once("txLoading", () => loadTaxBase());
  return Tax({ tx: uiState.tx, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.txLoading, onRetry: () => { loadedOnce.delete("txLoading"); render(); }, actions: taxActions() });
}

async function loadTaxBase() {
  const tx = uiState.tx || (uiState.tx = newTax());
  tx.error = null;
  try {
    [tx.overview, tx.options] = await Promise.all([api.taxOverview(), api.taxOptions()]);
    const all = await api.taxCountries("", "");
    tx.countryList = all.countries.map((c) => ({ code: c.code, name: c.name }));
    await loadTaxTab();
  } catch (err) { tx.error = err.message || "Tax Compliance could not be loaded."; }
}

async function loadTaxTab() {
  const tx = uiState.tx, tab = tx.tab;
  tx.busy = true; tx.error = null; render();
  try {
    tx.overview = await api.taxOverview();
    if (tab === "countries") tx.countries = await api.taxCountries(tx.q, tx.region);
    else if (tab === "rules") tx.rules = await api.taxRules(tx.ruleFilter, "");
    else if (tab === "calculator") {
      const [rules, periods, history] = await Promise.all([api.taxRules("", "APPROVED"), api.listPeriods().catch(() => []), api.taxCalculations()]);
      tx.liveRules = rules; tx.periods = periods; tx.history = history;
    } else if (tab === "calendar") tx.cal.data = await api.taxCalendar(tx.cal.start, tx.cal.end);
    tx.loaded[tab] = true;
  } catch (err) { tx.error = err.message || "That could not be loaded."; }
  tx.busy = false; render();
}

function taxActions() {
  const tx = uiState.tx;
  const run = async (fn, ok) => { tx.error = null; tx.notice = null; tx.busy = true; render(); try { await fn(); if (ok) tx.notice = ok; } catch (err) { tx.error = err.message || "That did not work."; } tx.busy = false; render(); };
  const fail = (m) => { tx.error = m; render(); };
  const refreshRules = async () => { tx.rules = await api.taxRules(tx.ruleFilter, ""); tx.overview = await api.taxOverview(); };
  let timer = null;
  return {
    setTab: (t) => { tx.tab = t; tx.error = null; tx.notice = null; tx.rule = null; tx.form = null; loadTaxTab(); },
    // countries
    search: (v) => { tx.q = v; clearTimeout(timer); timer = setTimeout(async () => { try { tx.countries = await api.taxCountries(tx.q, tx.region); } catch (err) { tx.error = err.message; } render(); const el = document.getElementById("tx-q"); if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); } }, 250); },
    setRegion: (v) => { tx.region = v; loadTaxTab(); },
    toggleCountry: (code, on) => run(async () => { await api.setTaxCountry(code, { selected: on, registration: tx.regDraft[code] || "" }); tx.countries = await api.taxCountries(tx.q, tx.region); tx.overview = await api.taxOverview(); }),
    regChange: (code, v) => { tx.regDraft = { ...tx.regDraft, [code]: v }; },
    saveReg: (code) => { if (tx.regDraft[code] === undefined) return; run(async () => { await api.setTaxCountry(code, { selected: true, registration: tx.regDraft[code] }); delete tx.regDraft[code]; tx.countries = await api.taxCountries(tx.q, tx.region); }, "Registration number saved."); },
    viewRules: (code) => { tx.ruleFilter = code; tx.tab = "rules"; loadTaxTab(); },
    // rules
    filterRules: (code) => { tx.ruleFilter = code; loadTaxTab(); },
    newRule: () => { tx.form = emptyRule(tx.ruleFilter); render(); },
    formChange: (k, v) => { tx.form = { ...tx.form, [k]: v }; if (["method", "filing_on", "country"].includes(k)) render(); },
    bandChange: (i, k, v) => { tx.form.brackets = tx.form.brackets.map((b, j) => (j === i ? { ...b, [k]: v } : b)); },
    addBand: () => { const last = tx.form.brackets[tx.form.brackets.length - 1]; tx.form.brackets = [...tx.form.brackets, { from: last && last.up_to ? last.up_to : "", up_to: "", rate: "" }]; render(); },
    removeBand: (i) => { tx.form.brackets = tx.form.brackets.filter((_, j) => j !== i); render(); },
    cancelForm: () => { tx.form = null; render(); },
    saveRule: () => {
      const problem = ruleProblem(tx.form); if (problem) return fail(problem);
      return run(async () => {
        const f = tx.form, body = ruleBody(f);
        tx.rule = f.id ? await api.updateTaxRule(f.id, body) : await api.createTaxRule(body);
        tx.form = null; tx.decisionNote = ""; await refreshRules();
      }, "Saved as a draft. Submit it for review when it is ready.");
    },
    openRule: (id) => run(async () => { tx.rule = await api.taxRule(id); tx.decisionNote = ""; }),
    closeRule: () => { tx.rule = null; loadTaxTab(); },
    editRule: () => { tx.form = ruleForm(tx.rule); render(); },
    replaceRule: () => { tx.form = { ...ruleForm(tx.rule), id: "", replaces: tx.rule.id, effective_from: "", effective_to: "" }; render(); },
    submitRule: () => run(async () => { tx.rule = await api.submitTaxRule(tx.rule.id); await refreshRules(); }, "Submitted. A different person must now review it."),
    discardRule: () => run(async () => { await api.discardTaxRule(tx.rule.id); tx.rule = null; await refreshRules(); }, "Draft discarded."),
    decisionChange: (v) => { tx.decisionNote = v; },
    decide: (approve) => {
      if (!approve && tx.decisionNote.trim().length < 3) return fail("Say why you are sending it back (at least 3 characters).");
      return run(async () => { tx.rule = approve ? await api.approveTaxRule(tx.rule.id, tx.decisionNote) : await api.rejectTaxRule(tx.rule.id, tx.decisionNote); tx.decisionNote = ""; await refreshRules(); }, approve ? "Approved. The rule can now be used." : "Sent back.");
    },
    // calculator
    calcChange: (k, v) => { if (k === "amount") tx.ledgerBasis = null; tx.calcForm = { ...tx.calcForm, [k]: v }; if (k === "rule_id" || k === "period_id") render(); },
    useLedger: () => run(async () => {
      const b = await api.taxLedgerBase(tx.calcForm.period_id, tx.calcForm.kind);
      tx.calcForm = { ...tx.calcForm, amount: b.amount };
      tx.ledgerBasis = { label: `${b.kind.replace("_", " ")} for ${b.period.name}` };
      tx.ledgerNote = [b.warning, b.note].filter(Boolean).join(" ");
    }),
    runCalc: () => {
      const problem = calcProblem(tx.calcForm); if (problem) return fail(problem);
      return run(async () => {
        const f = tx.calcForm;
        tx.calc = await api.taxCalculate({ rule_id: f.rule_id, amount: String(f.amount).trim(), date: f.date, inclusive: !!f.inclusive, basis: tx.ledgerBasis });
        tx.history = await api.taxCalculations();
      });
    },
    // calendar
    calRange: (k, v) => { tx.cal[k] = v; },
    loadCalendar: () => run(async () => { tx.cal.data = await api.taxCalendar(tx.cal.start, tx.cal.end); }),
    refChange: (key, v) => { tx.refDraft = { ...tx.refDraft, [key]: v }; },
    markFiled: (item) => {
      const ref = (tx.refDraft[item.key] || "").trim(); if (ref.length < 2) return fail("Enter the reference the tax authority gave you when you filed.");
      return run(async () => { await api.markTaxFiled({ rule_id: item.rule_id, period_end: item.period_end, reference: ref }); delete tx.refDraft[item.key]; tx.cal.data = await api.taxCalendar(tx.cal.start, tx.cal.end); }, "Recorded. ASAVEXA did not submit anything to the authority; this is your record that you did.");
    },
  };
}


// ----------------------------------------------------------------------
// Forensic Accounting and Investigation
// ----------------------------------------------------------------------
function newForensic() {
  return { cases: [], case: null, tab: "overview", caseForm: null, options: null, busy: false, error: null, notice: null, periods: [], vault: [], ev: { id: "", note: "" }, runForm: emptyRun(), run: null,
    findingForm: null, decisionNotes: {}, report: null, reportTitle: "", reportNote: "", closeNote: "", custodyCheck: null };
}

function renderForensicPage(authState) {
  if (!uiState.fm) uiState.fm = newForensic();
  once("fmLoading", () => loadForensic());
  return Forensic({ fm: uiState.fm, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.fmLoading, onRetry: () => { loadedOnce.delete("fmLoading"); render(); }, actions: forensicActions() });
}

async function loadForensic() {
  const fm = uiState.fm || (uiState.fm = newForensic());
  fm.error = null;
  try {
    [fm.options, fm.cases] = await Promise.all([api.forensicOptions(), api.forensicCases()]);
    fm.runForm = emptyRun(fm.options.defaults);
  } catch (err) { fm.error = err.message || "Investigations could not be loaded."; }
}

function forensicActions() {
  const fm = uiState.fm;
  const run = async (fn, ok) => { fm.error = null; fm.notice = null; fm.busy = true; render(); try { await fn(); if (ok) fm.notice = ok; } catch (err) { fm.error = err.message || "That did not work."; } fm.busy = false; render(); };
  const fail = (m) => { fm.error = m; render(); };
  const reloadCase = async () => { fm.case = await api.forensicCase(fm.case.id); };
  return {
    // list
    newCase: () => { fm.caseForm = emptyCase(); render(); },
    caseChange: (k, v) => { fm.caseForm = { ...fm.caseForm, [k]: v }; },
    cancelCase: () => { fm.caseForm = null; render(); },
    saveCase: () => { const p = caseProblem(fm.caseForm); if (p) return fail(p); return run(async () => { const c = await api.createForensicCase({ title: fm.caseForm.title.trim(), description: fm.caseForm.description.trim(), case_type: fm.caseForm.case_type }); fm.caseForm = null; fm.cases = await api.forensicCases(); fm.case = await api.forensicCase(c.id); fm.tab = "overview"; fm.custodyCheck = null; fm.run = null; }, "Case opened."); },
    openCase: (id) => run(async () => { fm.case = await api.forensicCase(id); fm.tab = "overview"; fm.custodyCheck = null; fm.run = null; fm.report = null; fm.findingForm = null; fm.closeNote = ""; }),
    closeCaseView: async () => { fm.case = null; fm.report = null; fm.findingForm = null; try { fm.cases = await api.forensicCases(); } catch (err) { fm.error = err.message; } render(); },
    setTab: async (t) => {
      fm.tab = t; fm.error = null; fm.notice = null; fm.report = null; render();
      try {
        if (t === "evidence") fm.vault = await api.listEvidence();
        if (t === "analytics" && !fm.periods.length) fm.periods = await api.listPeriods();
        if (t === "findings" || t === "reports" || t === "overview") await reloadCase();
        if (t === "findings" && !fm.vault.length) fm.vault = await api.listEvidence().catch(() => []);
      } catch (err) { fm.error = err.message || "That could not be loaded."; }
      render();
    },
    // overview
    verifyCustody: () => run(async () => { fm.custodyCheck = await api.forensicCustody(fm.case.id); }),
    closeNoteChange: (v) => { fm.closeNote = v; },
    closeCase: () => { if (fm.closeNote.trim().length < 3) return fail("Add a closing note (at least 3 characters)."); return run(async () => { await api.closeForensicCase(fm.case.id, fm.closeNote); await reloadCase(); }, "Case closed."); },
    // evidence
    evChange: (k, v) => { fm.ev = { ...fm.ev, [k]: v }; },
    addEvidence: () => { if (!fm.ev.id) return fail("Choose an evidence file."); return run(async () => { await api.addForensicEvidence(fm.case.id, { evidence_id: fm.ev.id, note: fm.ev.note }); fm.ev = { id: "", note: "" }; await reloadCase(); }, "Evidence added and its fingerprint recorded."); },
    // analytics
    runChange: (k, v) => { fm.runForm = { ...fm.runForm, [k]: v }; if (k === "scope_kind") render(); },
    runTest: (k, on) => { const s = new Set(fm.runForm.tests); on ? s.add(k) : s.delete(k); fm.runForm = { ...fm.runForm, tests: [...s] }; },
    runAnalytics: () => { const p = runProblem(fm.runForm); if (p) return fail(p); return run(async () => { fm.run = await api.runForensicAnalytics(fm.case.id, runBody(fm.runForm)); await reloadCase(); }, "Tests finished. These are indicators, not conclusions."); },
    openRun: (id) => run(async () => { fm.run = await api.forensicRun(id); }),
    citeJournal: (hit, runId) => {
      const f = fm.findingForm || emptyFinding();
      if (!f.journals.some((j) => j.id === hit.journal_id)) f.journals = [...f.journals, { id: hit.journal_id, number: hit.number, date: hit.date, amount: hit.amount }];
      f.run_id = f.run_id || runId; fm.findingForm = f; fm.tab = "findings"; fm.notice = `${hit.number} added to a draft finding.`; render();
    },
    // findings
    newFinding: () => { fm.findingForm = emptyFinding(); render(); },
    findingChange: (k, v) => { fm.findingForm = { ...fm.findingForm, [k]: v }; },
    uncite: (id) => { fm.findingForm = { ...fm.findingForm, journals: fm.findingForm.journals.filter((j) => j.id !== id) }; render(); },
    findingEvidence: (id, on) => { const s = new Set(fm.findingForm.evidence_ids); on ? s.add(id) : s.delete(id); fm.findingForm = { ...fm.findingForm, evidence_ids: [...s] }; },
    cancelFinding: () => { fm.findingForm = null; render(); },
    editFinding: (id) => { fm.findingForm = findingForm(fm.case.findings.find((x) => x.id === id)); render(); },
    saveFinding: () => { const p = findingProblem(fm.findingForm); if (p) return fail(p); return run(async () => { const f = fm.findingForm, b = findingBody(f); if (f.id) await api.updateForensicFinding(f.id, b); else await api.createForensicFinding(fm.case.id, b); fm.findingForm = null; await reloadCase(); }, "Saved as a draft. Submit it for review when it is ready."); },
    submitFinding: (id) => run(async () => { await api.submitForensicFinding(id); await reloadCase(); }, "Submitted. A different person must now review it."),
    discardFinding: (id) => run(async () => { await api.discardForensicFinding(id); await reloadCase(); }, "Draft discarded."),
    decisionChange: (id, v) => { fm.decisionNotes = { ...fm.decisionNotes, [id]: v }; },
    decideFinding: (id, approve) => { const n = fm.decisionNotes[id] || ""; if (!approve && n.trim().length < 3) return fail("Say why you are sending it back (at least 3 characters)."); return run(async () => { approve ? await api.approveForensicFinding(id, n) : await api.rejectForensicFinding(id, n); fm.decisionNotes = { ...fm.decisionNotes, [id]: "" }; await reloadCase(); }, approve ? "Approved." : "Sent back."); },
    // reports
    reportTitleChange: (v) => { fm.reportTitle = v; },
    createReport: () => { if (fm.reportTitle.trim().length < 3) return fail("Give the report a title."); return run(async () => { fm.report = await api.createForensicReport(fm.case.id, fm.reportTitle.trim()); fm.reportTitle = ""; fm.reportNote = ""; await reloadCase(); }, "Report frozen as a draft."); },
    openReport: (id) => run(async () => { fm.report = await api.forensicReport(id); fm.reportNote = ""; }),
    closeReport: () => { fm.report = null; reloadCase().then(render); },
    submitReport: () => run(async () => { fm.report = await api.submitForensicReport(fm.report.id); }, "Submitted for review."),
    reportNoteChange: (v) => { fm.reportNote = v; },
    decideReport: (approve) => { if (!approve && fm.reportNote.trim().length < 3) return fail("Say why you are sending it back (at least 3 characters)."); return run(async () => { fm.report = approve ? await api.approveForensicReport(fm.report.id, fm.reportNote) : await api.rejectForensicReport(fm.report.id, fm.reportNote); fm.reportNote = ""; }, approve ? "Approved." : "Sent back."); },
    exportReport: () => run(async () => { const { blob, filename } = await api.exportForensicReport(fm.report.id); saveBlob(blob, filename); }, "Downloaded."),
  };
}

// ----------------------------------------------------------------------
// Governance, Risk and Compliance
// ----------------------------------------------------------------------
function newGrc() {
  return { options: null, dash: null, risks: [], actions: [], obligations: [], vault: [], tab: "overview", filter: "", risk: null, riskForm: null, acceptForm: null, actionForm: null, doneForm: null, cancelId: null,
    obForm: null, metForm: null, retireId: null, notes: {}, appetiteInput: "", busy: false, error: null, notice: null };
}

function renderGrcPage(authState) {
  if (!uiState.gc) uiState.gc = newGrc();
  once("gcLoading", () => loadGrc());
  return Grc({ gc: uiState.gc, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.gcLoading, onRetry: () => { loadedOnce.delete("gcLoading"); render(); }, actions: grcActions() });
}

async function grcRefresh(gc) {
  [gc.dash, gc.risks, gc.actions, gc.obligations] = await Promise.all([api.grcDashboard(), api.grcRisks(gc.filter), api.grcActions(), api.grcObligations()]);
  gc.appetiteInput = String(gc.dash.appetite);
  if (gc.risk) gc.risk = await api.grcRisk(gc.risk.id);
}

async function loadGrc() {
  const gc = uiState.gc || (uiState.gc = newGrc());
  gc.error = null;
  try {
    gc.options = await api.grcOptions();
    await grcRefresh(gc);
    gc.vault = await api.listEvidence().catch(() => []);
  } catch (err) { gc.error = err.message || "Governance, risk and compliance could not be loaded."; }
}

function grcActions() {
  const gc = uiState.gc;
  const run = async (fn, ok) => { gc.error = null; gc.notice = null; gc.busy = true; render(); try { await fn(); if (ok) gc.notice = ok; } catch (err) { gc.error = err.message || "That did not work."; } gc.busy = false; render(); };
  const fail = (m) => { gc.error = m; render(); };
  const today = () => (gc.dash && gc.dash.as_of) || new Date().toISOString().slice(0, 10);
  const clearForms = () => { gc.riskForm = gc.acceptForm = gc.actionForm = gc.doneForm = gc.obForm = gc.metForm = null; gc.cancelId = gc.retireId = null; gc.notes = {}; };
  const refresh = () => grcRefresh(gc);
  const toggle = (list, id) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  const note = (k) => gc.notes[k] || "";
  return {
    setTab: (t) => run(async () => { gc.tab = t; gc.risk = null; clearForms(); await refresh(); }),
    setFilter: (v) => run(async () => { gc.filter = v; gc.risks = await api.grcRisks(v); }),
    exportRegister: () => run(async () => { const { blob, filename } = await api.exportGrcRegister(); saveBlob(blob, filename); }, "Downloaded."),
    appetiteChange: (v) => { gc.appetiteInput = v; },
    saveAppetite: () => { const v = String(gc.appetiteInput).trim(); if (!/^\d+$/.test(v) || +v < 1 || +v > 25) return fail("The risk appetite is a whole number from 1 to 25."); return run(async () => { await api.setGrcAppetite(+v); await refresh(); }, "Risk appetite saved."); },
    noteChange: (k, v) => { gc.notes[k] = v; },
    // risks
    newRisk: () => { clearForms(); gc.riskForm = emptyRisk(); render(); },
    riskChange: (k, v) => {
      const f = gc.riskForm, n = { ...f, [k]: v };
      if (k === "inherent_l" && f.residual_l === f.inherent_l) n.residual_l = v;
      if (k === "inherent_i" && f.residual_i === f.inherent_i) n.residual_i = v;
      gc.riskForm = n;
      if (/^(inherent|residual)_[li]$/.test(k)) render();
    },
    riskControl: (id) => { gc.riskForm = { ...gc.riskForm, control_ids: toggle(gc.riskForm.control_ids, id) }; },
    cancelRisk: () => { gc.riskForm = null; render(); },
    saveRisk: () => { const p = riskProblem(gc.riskForm); if (p) return fail(p); return run(async () => {
      const f = gc.riskForm, b = riskBody(f), r = f.id ? await api.updateGrcRisk(f.id, b) : await api.createGrcRisk(b);
      gc.riskForm = null; gc.risk = r; await refresh(); gc.notice = f.id ? "Risk updated." : `Risk ${r.ref} added.`; }); },
    openRisk: (id) => run(async () => { clearForms(); gc.risk = await api.grcRisk(id); }),
    closeRiskView: () => run(async () => { gc.risk = null; clearForms(); await refresh(); }),
    editRisk: () => { gc.riskForm = riskForm(gc.risk); render(); },
    treatRisk: () => run(async () => { await api.treatGrcRisk(gc.risk.id); await refresh(); }, "Treatment started."),
    openAccept: () => { gc.acceptForm = { justification: "", review_by: "" }; render(); },
    acceptChange: (k, v) => { gc.acceptForm = { ...gc.acceptForm, [k]: v }; },
    cancelAccept: () => { gc.acceptForm = null; render(); },
    submitAccept: () => { const p = acceptProblem(gc.acceptForm, today()); if (p) return fail(p); return run(async () => {
      const r = await api.acceptGrcRisk(gc.risk.id, { justification: gc.acceptForm.justification.trim(), review_by: gc.acceptForm.review_by.trim() });
      gc.acceptForm = null; await refresh(); gc.notice = r.status === "ACCEPTED" ? "Accepted and recorded." : "Sent for approval. A different person must decide it."; }); },
    decideAcceptance: (approve) => { if (!approve) { const p = noteProblem(note("decide"), "a note saying why you are sending it back"); if (p) return fail(p); }
      return run(async () => { await (approve ? api.approveGrcAcceptance(gc.risk.id, note("decide")) : api.rejectGrcAcceptance(gc.risk.id, note("decide"))); gc.notes.decide = ""; await refresh(); }, approve ? "Acceptance approved." : "Sent back."); },
    reopenRisk: () => { const p = noteProblem(note("reopen"), "a reason for reopening"); if (p) return fail(p); return run(async () => { await api.reopenGrcRisk(gc.risk.id, note("reopen")); gc.notes.reopen = ""; await refresh(); }, "Risk reopened."); },
    closeRisk: () => { const p = noteProblem(note("close"), "a reason for closing", 10); if (p) return fail(p); return run(async () => { await api.closeGrcRisk(gc.risk.id, note("close")); gc.notes.close = ""; await refresh(); }, "Risk closed."); },
    // actions
    newAction: (riskId) => { gc.actionForm = { ...emptyAction(riskId), fixedRisk: !!riskId }; render(); },
    actionChange: (k, v) => { gc.actionForm = { ...gc.actionForm, [k]: v }; },
    cancelAction: () => { gc.actionForm = null; render(); },
    editAction: (x) => { gc.actionForm = { ...actionForm(x), fixedRisk: true }; render(); },
    saveAction: () => { const p = actionProblem(gc.actionForm); if (p) return fail(p); return run(async () => {
      const f = gc.actionForm; if (f.id) await api.updateGrcAction(f.id, actionBody(f)); else await api.createGrcAction(actionBody(f));
      gc.actionForm = null; await refresh(); gc.notice = f.id ? "Action updated." : "Action added."; }); },
    openDone: (x) => { gc.doneForm = { id: x.id, note: "", evidence_ids: [] }; render(); },
    doneChange: (k, v) => { gc.doneForm = { ...gc.doneForm, [k]: v }; },
    doneEvidence: (id) => { gc.doneForm = { ...gc.doneForm, evidence_ids: toggle(gc.doneForm.evidence_ids, id) }; },
    cancelDone: () => { gc.doneForm = null; render(); },
    submitDone: () => { const p = doneProblem(gc.doneForm); if (p) return fail(p); return run(async () => { const f = gc.doneForm; await api.completeGrcAction(f.id, { note: f.note.trim(), evidence_ids: f.evidence_ids }); gc.doneForm = null; await refresh(); },
      "Marked done. A different person must now verify it."); },
    verifyAction: (id, ok) => { if (!ok) { const p = noteProblem(note("verify"), "a note saying what is missing"); if (p) return fail(p); }
      return run(async () => { await (ok ? api.verifyGrcAction(id, note("verify")) : api.sendBackGrcAction(id, note("verify"))); gc.notes.verify = ""; await refresh(); }, ok ? "Verified." : "Sent back to the owner."); },
    cancelActionRec: (id) => { gc.cancelId = id; render(); },
    keepAction: () => { gc.cancelId = null; render(); },
    confirmCancelAction: () => { const p = noteProblem(note("cancel"), "a reason for cancelling"); if (p) return fail(p); return run(async () => { await api.cancelGrcAction(gc.cancelId, note("cancel")); gc.cancelId = null; gc.notes.cancel = ""; await refresh(); }, "Action cancelled."); },
    // obligations
    newObligation: () => { clearForms(); gc.obForm = emptyObligation(); render(); },
    obChange: (k, v) => { gc.obForm = { ...gc.obForm, [k]: v }; },
    obControl: (id) => { gc.obForm = { ...gc.obForm, control_ids: toggle(gc.obForm.control_ids, id) }; },
    cancelObligation: () => { gc.obForm = null; render(); },
    editObligation: (x) => { clearForms(); gc.obForm = obligationForm(x); render(); },
    saveObligation: () => { const p = obligationProblem(gc.obForm); if (p) return fail(p); return run(async () => {
      const f = gc.obForm, b = obligationBody(f); if (f.id) await api.updateGrcObligation(f.id, b); else await api.createGrcObligation(b);
      gc.obForm = null; await refresh(); gc.notice = f.id ? "Obligation updated." : "Obligation added."; }); },
    openMet: (x) => { clearForms(); gc.metForm = { id: x.id, ...emptyMet(today()) }; render(); },
    metChange: (k, v) => { gc.metForm = { ...gc.metForm, [k]: v }; },
    metEvidence: (id) => { gc.metForm = { ...gc.metForm, evidence_ids: toggle(gc.metForm.evidence_ids, id) }; },
    cancelMet: () => { gc.metForm = null; render(); },
    submitMet: () => { const p = metProblem(gc.metForm, today()); if (p) return fail(p); return run(async () => { const f = gc.metForm; await api.markGrcObligationMet(f.id, { met_on: f.met_on.trim(), note: f.note.trim(), evidence_ids: f.evidence_ids }); gc.metForm = null; await refresh(); },
      "Recorded. The next due date has moved on."); },
    retireObligation: (id) => { clearForms(); gc.retireId = id; render(); },
    keepObligation: () => { gc.retireId = null; render(); },
    confirmRetire: () => { const p = noteProblem(note("retire"), "a reason for retiring it"); if (p) return fail(p); return run(async () => { await api.retireGrcObligation(gc.retireId, note("retire")); gc.retireId = null; gc.notes.retire = ""; await refresh(); }, "Obligation retired."); },
  };
}

// ----------------------------------------------------------------------
// Financial Management and Public Finance
// ----------------------------------------------------------------------
function newPubfin() {
  return { options: null, ov: null, budgets: [], commitments: [], procs: [], grants: [], reports: [], vault: [], tab: "overview", budget: null, budgetForm: null, virementForm: null, commitForm: null, settleForm: null, cancelCommitId: null,
    procForm: null, proc: null, quoteForm: null, awardForm: null, grant: null, grantForm: null, receiptForm: null, spendForm: null, reportForm: null, report: null, notes: {}, policyForm: null, busy: false, error: null, notice: null };
}

function renderPubfinPage(authState) {
  if (!uiState.pf) uiState.pf = newPubfin();
  once("pfLoading", () => loadPubfin());
  return Pubfin({ pf: uiState.pf, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.pfLoading, onRetry: () => { loadedOnce.delete("pfLoading"); render(); }, actions: pubfinActions() });
}

async function pubfinRefresh(pf) {
  [pf.ov, pf.budgets, pf.commitments, pf.procs, pf.grants, pf.reports] = await Promise.all([api.pubfinOverview(), api.pubfinBudgets(), api.pubfinCommitments(), api.pubfinProcurements(), api.pubfinGrants(), api.pubfinReports()]);
  pf.policyForm = { min_quotes: String(pf.ov.policy.min_quotes), quote_threshold: pf.ov.policy.quote_threshold };
  if (pf.budget) pf.budget = await api.pubfinBudget(pf.budget.id);
  if (pf.proc) pf.proc = await api.pubfinProcurement(pf.proc.id);
  if (pf.grant) pf.grant = await api.pubfinGrant(pf.grant.id);
  if (pf.report) pf.report = await api.pubfinReport(pf.report.id);
}

async function loadPubfin() {
  const pf = uiState.pf || (uiState.pf = newPubfin());
  pf.error = null;
  try {
    pf.options = await api.pubfinOptions();
    await pubfinRefresh(pf);
    pf.vault = await api.listEvidence().catch(() => []);
  } catch (err) { pf.error = err.message || "Public finance could not be loaded."; }
}

function pubfinActions() {
  const pf = uiState.pf;
  const run = async (fn, ok) => { pf.error = null; pf.notice = null; pf.busy = true; render(); try { await fn(); if (ok) pf.notice = ok; } catch (err) { pf.error = err.message || "That did not work."; } pf.busy = false; render(); };
  const fail = (m) => { pf.error = m; render(); };
  const refresh = () => pubfinRefresh(pf);
  const note = (k) => pf.notes[k] || "";
  const toggle = (list, id) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  const clearForms = () => { pf.budgetForm = pf.virementForm = pf.commitForm = pf.settleForm = pf.procForm = pf.quoteForm = pf.awardForm = pf.grantForm = pf.receiptForm = pf.spendForm = pf.reportForm = null; pf.cancelCommitId = null; pf.notes = {}; };
  const set = (key) => (k, v) => { pf[key] = { ...pf[key], [k]: v }; };
  const decide = (needNote, label, f) => (ok, id) => { if (!ok) { const p = PF.noteProblem(needNote(), label, 3); if (p) return fail(p); } return f(ok, id); };
  return {
    setTab: (t) => run(async () => { pf.tab = t; pf.budget = pf.proc = pf.grant = pf.report = null; clearForms(); await refresh(); }),
    policyChange: (k, v) => { pf.policyForm = { ...pf.policyForm, [k]: v }; },
    savePolicy: () => { const p = PF.policyProblem(pf.policyForm); if (p) return fail(p); return run(async () => { await api.setPubfinPolicy({ min_quotes: +pf.policyForm.min_quotes, quote_threshold: pf.policyForm.quote_threshold.trim() }); await refresh(); }, "Procurement policy saved."); },
    noteChange: (k, v) => { pf.notes[k] = v; },
    // budgets
    newBudget: () => { clearForms(); pf.budgetForm = PF.emptyBudget(); render(); },
    budgetChange: set("budgetForm"),
    budgetAmount: (id, v) => { pf.budgetForm = { ...pf.budgetForm, amounts: { ...pf.budgetForm.amounts, [id]: v } }; },
    cancelBudget: () => { pf.budgetForm = null; render(); },
    saveBudget: () => { const p = PF.budgetProblem(pf.budgetForm); if (p) return fail(p); return run(async () => { const f = pf.budgetForm, b = PF.budgetBody(f); const r = f.id ? await api.updatePubfinBudget(f.id, b) : await api.createPubfinBudget(b);
      pf.budgetForm = null; pf.budget = r; await refresh(); pf.notice = f.id ? "Budget updated." : `Budget ${r.ref} saved as a draft.`; }); },
    openBudget: (id) => run(async () => { clearForms(); pf.budget = await api.pubfinBudget(id); }),
    closeBudgetView: () => run(async () => { pf.budget = null; clearForms(); await refresh(); }),
    editBudget: () => { pf.budgetForm = PF.budgetForm(pf.budget); render(); },
    submitBudget: () => run(async () => { await api.submitPubfinBudget(pf.budget.id); await refresh(); }, "Submitted. A different person must now approve it."),
    discardBudget: () => run(async () => { await api.discardPubfinBudget(pf.budget.id); pf.budget = null; await refresh(); }, "Draft discarded."),
    decideBudget: decide(() => note("decide"), "a note saying why you are sending it back", (ok) => run(async () => { await (ok ? api.approvePubfinBudget(pf.budget.id, note("decide")) : api.rejectPubfinBudget(pf.budget.id, note("decide"))); pf.notes.decide = ""; await refresh(); }, ok ? "Budget approved." : "Sent back.")),
    closeBudget: () => { const p = PF.noteProblem(note("close"), "a closing note"); if (p) return fail(p); return run(async () => { await api.closePubfinBudget(pf.budget.id, note("close")); pf.notes.close = ""; await refresh(); }, "Budget closed."); },
    newVirement: () => { pf.virementForm = { from_account: "", to_account: "", amount: "", reason: "" }; render(); },
    virementChange: (k, v) => { pf.virementForm = { ...pf.virementForm, [k]: v }; if (k !== "amount" && k !== "reason") render(); },
    cancelVirement: () => { pf.virementForm = null; render(); },
    saveVirement: () => { const p = PF.virementProblem(pf.virementForm, pf.budget); if (p) return fail(p); return run(async () => { const f = pf.virementForm; await api.proposePubfinVirement(pf.budget.id, { from_account: f.from_account, to_account: f.to_account, amount: f.amount.trim(), reason: f.reason.trim() }); pf.virementForm = null; await refresh(); }, "Proposed. A different person must approve it."); },
    decideVirement: (vid, ok) => decide(() => note("virement"), "a note saying why you are sending it back", () => run(async () => { await (ok ? api.approvePubfinVirement(pf.budget.id, vid, note("virement")) : api.rejectPubfinVirement(pf.budget.id, vid, note("virement"))); pf.notes.virement = ""; await refresh(); }, ok ? "Virement approved." : "Sent back."))(ok, vid),
    // commitments
    newCommit: (budgetId) => { const keep = pf.budget; clearForms(); pf.commitForm = { ...PF.emptyCommit(budgetId), fixedBudget: !!budgetId }; if (keep) pf.budget = keep; render(); },
    commitChange: (k, v) => { pf.commitForm = { ...pf.commitForm, [k]: v }; if (k === "budget_id") { pf.commitForm.account_id = ""; render(); } },
    commitEvidence: (id) => { pf.commitForm = { ...pf.commitForm, evidence_ids: toggle(pf.commitForm.evidence_ids, id) }; },
    cancelCommit: () => { pf.commitForm = null; render(); },
    saveCommit: () => { const p = PF.commitProblem(pf.commitForm); if (p) return fail(p); return run(async () => { const c = await api.createPubfinCommitment(PF.commitBody(pf.commitForm)); pf.commitForm = null; await refresh(); pf.notice = `Commitment ${c.ref} recorded.`; }); },
    openSettle: (c) => { pf.settleForm = { id: c.id, settled_amount: c.amount, note: "" }; render(); },
    settleChange: set("settleForm"),
    cancelSettle: () => { pf.settleForm = null; render(); },
    saveSettle: () => { const p = PF.settleProblem(pf.settleForm); if (p) return fail(p); return run(async () => { const f = pf.settleForm; await api.settlePubfinCommitment(f.id, { settled_amount: f.settled_amount.trim(), note: f.note.trim() }); pf.settleForm = null; await refresh(); }, "Settled."); },
    askCancelCommit: (id) => { pf.cancelCommitId = id; render(); },
    keepCommit: () => { pf.cancelCommitId = null; render(); },
    confirmCancelCommit: () => { const p = PF.noteProblem(note("cancelCommit"), "a reason for cancelling"); if (p) return fail(p); return run(async () => { await api.cancelPubfinCommitment(pf.cancelCommitId, note("cancelCommit")); pf.cancelCommitId = null; pf.notes.cancelCommit = ""; await refresh(); }, "Commitment cancelled."); },
    // procurement
    newProc: () => { clearForms(); pf.procForm = PF.emptyProc(); render(); },
    procChange: (k, v) => { pf.procForm = { ...pf.procForm, [k]: v }; if (k === "budget_id") { pf.procForm.account_id = ""; render(); } },
    cancelProc: () => { pf.procForm = null; render(); },
    saveProc: () => { const p = PF.procProblem(pf.procForm); if (p) return fail(p); return run(async () => { const f = pf.procForm; const r = await api.createPubfinProcurement({ budget_id: f.budget_id, account_id: f.account_id, title: f.title.trim(), description: (f.description || "").trim(), estimate: f.estimate.trim() }); pf.procForm = null; pf.proc = r; await refresh(); pf.notice = `Procurement ${r.ref} created.`; }); },
    openProc: (id) => run(async () => { clearForms(); pf.proc = await api.pubfinProcurement(id); }),
    closeProcView: () => run(async () => { pf.proc = null; clearForms(); await refresh(); }),
    newQuote: () => { pf.quoteForm = { vendor: "", amount: "", note: "" }; render(); },
    quoteChange: set("quoteForm"),
    cancelQuote: () => { pf.quoteForm = null; render(); },
    saveQuote: () => { const p = PF.quoteProblem(pf.quoteForm); if (p) return fail(p); return run(async () => { const f = pf.quoteForm; await api.addPubfinQuote(pf.proc.id, { vendor: f.vendor.trim(), amount: f.amount.trim(), note: (f.note || "").trim() }); pf.quoteForm = null; await refresh(); }, "Quote added."); },
    newAward: () => { pf.awardForm = { quote_id: "", justification: "", exception_reason: "" }; render(); },
    awardChange: (k, v) => { pf.awardForm = { ...pf.awardForm, [k]: v }; },
    cancelAward: () => { pf.awardForm = null; render(); },
    saveAward: () => { const p = PF.awardProblem(pf.awardForm, pf.proc, pf.ov.policy); if (p) return fail(p); return run(async () => { const f = pf.awardForm; await api.proposePubfinAward(pf.proc.id, { quote_id: f.quote_id, justification: (f.justification || "").trim(), exception_reason: (f.exception_reason || "").trim() }); pf.awardForm = null; await refresh(); }, "Award proposed. A different person must approve it."); },
    decideAward: decide(() => note("award"), "a note saying why you are sending it back", (ok) => run(async () => { await (ok ? api.approvePubfinAward(pf.proc.id, note("award")) : api.rejectPubfinAward(pf.proc.id, note("award"))); pf.notes.award = ""; await refresh(); }, ok ? "Award approved and the commitment recorded." : "Sent back.")),
    cancelProcurement: () => { const p = PF.noteProblem(note("procCancel"), "a reason for cancelling"); if (p) return fail(p); return run(async () => { await api.cancelPubfinProcurement(pf.proc.id, note("procCancel")); pf.notes.procCancel = ""; await refresh(); }, "Procurement cancelled."); },
    // grants
    newGrant: () => { clearForms(); pf.grantForm = PF.emptyGrant(); render(); },
    grantChange: set("grantForm"),
    cancelGrant: () => { pf.grantForm = null; render(); },
    saveGrant: () => { const p = PF.grantProblem(pf.grantForm); if (p) return fail(p); return run(async () => { const g = await api.createPubfinGrant(PF.grantBody(pf.grantForm)); pf.grantForm = null; pf.grant = g; await refresh(); pf.notice = `Grant ${g.ref} recorded.`; }); },
    openGrant: (id) => run(async () => { clearForms(); pf.grant = await api.pubfinGrant(id); }),
    closeGrantView: () => run(async () => { pf.grant = null; clearForms(); await refresh(); }),
    newReceipt: () => { pf.receiptForm = { amount: "", date: "", reference: "" }; render(); },
    receiptChange: set("receiptForm"),
    cancelReceipt: () => { pf.receiptForm = null; render(); },
    saveReceipt: () => { const p = PF.receiptProblem(pf.receiptForm); if (p) return fail(p); return run(async () => { const f = pf.receiptForm; await api.recordPubfinReceipt(pf.grant.id, { amount: f.amount.trim(), date: f.date.trim(), reference: f.reference.trim() }); pf.receiptForm = null; await refresh(); }, "Receipt recorded."); },
    newSpend: () => { pf.spendForm = { amount: "", date: "", description: "", reference: "", evidence_ids: [] }; render(); },
    spendChange: set("spendForm"),
    spendEvidence: (id) => { pf.spendForm = { ...pf.spendForm, evidence_ids: toggle(pf.spendForm.evidence_ids, id) }; },
    cancelSpend: () => { pf.spendForm = null; render(); },
    saveSpend: () => { const p = PF.spendProblem(pf.spendForm); if (p) return fail(p); return run(async () => { const f = pf.spendForm; await api.addPubfinSpend(pf.grant.id, { amount: f.amount.trim(), date: f.date.trim(), description: f.description.trim(), reference: (f.reference || "").trim(), evidence_ids: f.evidence_ids }); pf.spendForm = null; await refresh(); }, "Recorded. A different person must approve it before it counts."); },
    decideSpend: (sid, ok) => decide(() => note("spend"), "a note saying why you are sending it back", () => run(async () => { await (ok ? api.approvePubfinSpend(pf.grant.id, sid, note("spend")) : api.rejectPubfinSpend(pf.grant.id, sid, note("spend"))); pf.notes.spend = ""; await refresh(); }, ok ? "Spending approved." : "Sent back."))(ok, sid),
    closeGrant: () => { const p = PF.noteProblem(note("grantClose"), "a closing note"); if (p) return fail(p); return run(async () => { await api.closePubfinGrant(pf.grant.id, note("grantClose")); pf.notes.grantClose = ""; await refresh(); }, "Grant closed."); },
    // reports
    newReport: () => { clearForms(); pf.reportForm = { budget_id: "", title: "" }; render(); },
    reportChange: set("reportForm"),
    cancelReport: () => { pf.reportForm = null; render(); },
    saveReport: () => { const p = PF.reportProblem(pf.reportForm); if (p) return fail(p); return run(async () => { const r = await api.createPubfinReport({ budget_id: pf.reportForm.budget_id, title: pf.reportForm.title.trim() }); pf.reportForm = null; pf.report = r; await refresh(); pf.notice = `Report ${r.ref} created.`; }); },
    openReport: (id) => run(async () => { clearForms(); pf.report = await api.pubfinReport(id); }),
    closeReportView: () => run(async () => { pf.report = null; clearForms(); await refresh(); }),
    submitReport: () => run(async () => { await api.submitPubfinReport(pf.report.id); await refresh(); }, "Frozen and submitted. A different person must now approve it."),
    decideReport: decide(() => note("report"), "a note saying why you are sending it back", (ok) => run(async () => { await (ok ? api.approvePubfinReport(pf.report.id, note("report")) : api.rejectPubfinReport(pf.report.id, note("report"))); pf.notes.report = ""; await refresh(); }, ok ? "Report approved." : "Sent back.")),
    exportReport: () => run(async () => { const { blob, filename } = await api.exportPubfinReport(pf.report.id); saveBlob(blob, filename); }, "Downloaded."),
  };
}

// ----------------------------------------------------------------------
// Business Development
// ----------------------------------------------------------------------
function newBizdev() {
  return { options: null, ov: null, accounts: [], opps: [], targets: [], reports: [], vault: [], tab: "overview", stageFilter: "", account: null, accountForm: null, opp: null, oppForm: null, moveTo: "", activityForm: null,
    proposalForm: null, targetForm: null, reportForm: null, report: null, notes: {}, policyForm: null, busy: false, error: null, notice: null };
}

function renderBizdevPage(authState) {
  if (!uiState.bd) uiState.bd = newBizdev();
  once("bdLoading", () => loadBizdev());
  return Bizdev({ bd: uiState.bd, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.bdLoading, onRetry: () => { loadedOnce.delete("bdLoading"); render(); }, actions: bizdevActions() });
}

async function bizdevRefresh(bd) {
  [bd.options, bd.ov, bd.accounts, bd.opps, bd.targets, bd.reports] = await Promise.all([api.bdOptions(), api.bdOverview(), api.bdAccounts(), api.bdOpportunities(), api.bdTargets(), api.bdReports()]);
  bd.policyForm = BD.policyForm(bd.ov.policy);
  if (bd.account) bd.account = await api.bdAccount(bd.account.id);
  if (bd.opp) bd.opp = await api.bdOpportunity(bd.opp.id);
  if (bd.report) bd.report = await api.bdReport(bd.report.id);
}

async function loadBizdev() {
  const bd = uiState.bd || (uiState.bd = newBizdev());
  bd.error = null;
  try {
    await bizdevRefresh(bd);
    bd.vault = await api.listEvidence().catch(() => []);
  } catch (err) { bd.error = err.message || "Business development could not be loaded."; }
}

function bizdevActions() {
  const bd = uiState.bd;
  const run = async (fn, ok) => { bd.error = null; bd.notice = null; bd.busy = true; render(); try { await fn(); if (ok) bd.notice = ok; } catch (err) { bd.error = err.message || "That did not work."; } bd.busy = false; render(); };
  const fail = (m) => { bd.error = m; render(); };
  const refresh = () => bizdevRefresh(bd);
  const note = (k) => bd.notes[k] || "";
  const clearForms = () => { bd.accountForm = bd.oppForm = bd.activityForm = bd.proposalForm = bd.targetForm = bd.reportForm = null; bd.moveTo = ""; bd.notes = {}; };
  const set = (key) => (k, v) => { bd[key] = { ...bd[key], [k]: v }; };
  const need = (k, what, min) => BD.noteProblem(note(k), what, min);
  return {
    setTab: (t) => run(async () => { bd.tab = t; bd.account = bd.opp = bd.report = null; clearForms(); await refresh(); }),
    noteChange: (k, v) => { bd.notes[k] = v; },
    policyChange: (k, v) => { bd.policyForm = { ...bd.policyForm, [k]: v }; },
    savePolicy: () => { const p = BD.policyProblem(bd.policyForm); if (p) return fail(p); return run(async () => { await api.setBdPolicy(BD.policyBody(bd.policyForm)); await refresh(); }, "Policy saved."); },
    // accounts
    newAccount: () => { clearForms(); bd.accountForm = BD.emptyAccount(); render(); },
    accountChange: set("accountForm"),
    cancelAccount: () => { bd.accountForm = null; render(); },
    editAccount: () => { bd.accountForm = BD.accountForm(bd.account); render(); },
    saveAccount: () => { const p = BD.accountProblem(bd.accountForm); if (p) return fail(p); return run(async () => { const f = bd.accountForm, b = BD.accountBody(f); const r = f.id ? await api.updateBdAccount(f.id, b) : await api.createBdAccount(b); bd.accountForm = null; if (f.id) bd.account = r; await refresh(); bd.notice = f.id ? "Account updated." : `Account ${r.ref} saved.`; }); },
    openAccount: (id) => run(async () => { clearForms(); bd.account = await api.bdAccount(id); }),
    closeAccountView: () => run(async () => { bd.account = null; clearForms(); await refresh(); }),
    archiveAccount: () => { const p = need("archive", "a reason", 3); if (p) return fail(p); return run(async () => { await api.archiveBdAccount(bd.account.id, note("archive")); bd.account = null; clearForms(); await refresh(); }, "Account archived."); },
    // opportunities
    filterStage: (v) => { bd.stageFilter = v; render(); },
    newOpp: (accountId) => { const keepAcc = bd.account; clearForms(); bd.tab = "pipeline"; bd.account = null; bd.oppForm = BD.emptyOpp(accountId); if (!accountId && keepAcc) bd.oppForm.account_id = keepAcc.id; render(); },
    oppChange: set("oppForm"),
    cancelOpp: () => { bd.oppForm = null; render(); },
    editOpp: () => { bd.oppForm = BD.oppForm(bd.opp); render(); },
    saveOpp: () => { const f = bd.oppForm, isNew = !f.id, p = BD.oppProblem(f, isNew); if (p) return fail(p); return run(async () => { const b = BD.oppBody(f, isNew); const r = isNew ? await api.createBdOpportunity(b) : await api.updateBdOpportunity(f.id, b); bd.oppForm = null; bd.opp = r; await refresh(); bd.notice = isNew ? `Opportunity ${r.ref} saved.` : "Opportunity updated."; }); },
    openOpp: (id) => run(async () => { clearForms(); bd.tab = "pipeline"; bd.account = null; bd.opp = await api.bdOpportunity(id); }),
    closeOppView: () => run(async () => { bd.opp = null; clearForms(); await refresh(); }),
    moveChange: (v) => { bd.moveTo = v; },
    moveStage: () => { if (!bd.moveTo) return fail("Choose the stage to move to."); return run(async () => { await api.moveBdStage(bd.opp.id, bd.moveTo, note("move")); bd.moveTo = ""; bd.notes.move = ""; await refresh(); }, "Stage changed."); },
    newActivity: () => { bd.activityForm = BD.emptyActivity(); render(); },
    activityChange: set("activityForm"),
    cancelActivity: () => { bd.activityForm = null; render(); },
    saveActivity: () => { const p = BD.activityProblem(bd.activityForm); if (p) return fail(p); return run(async () => { await api.addBdActivity(bd.opp.id, BD.activityBody(bd.activityForm)); bd.activityForm = null; await refresh(); }, "Activity logged."); },
    markLost: () => { const p = need("lost", "the reason it was lost", 10); if (p) return fail(p); return run(async () => { await api.markBdLost(bd.opp.id, note("lost")); bd.notes.lost = ""; await refresh(); }, "Marked as lost."); },
    requestWin: () => run(async () => { await api.requestBdWin(bd.opp.id, note("win")); bd.notes.win = ""; await refresh(); }, "Asked for the win to be confirmed. A different person must decide."),
    decideWin: (ok) => { if (!ok) { const p = need("windecide", "a note saying why you are sending it back", 3); if (p) return fail(p); } return run(async () => { await (ok ? api.approveBdWin(bd.opp.id, note("windecide")) : api.rejectBdWin(bd.opp.id, note("windecide"))); bd.notes.windecide = ""; await refresh(); }, ok ? "Win confirmed." : "Sent back to negotiation."); },
    // proposals
    newProposal: () => { bd.proposalForm = BD.emptyProposal(); render(); },
    editProposal: (p) => { bd.proposalForm = BD.proposalForm(p); render(); },
    proposalChange: set("proposalForm"),
    itemChange: (i, k, v) => { bd.proposalForm = { ...bd.proposalForm, items: bd.proposalForm.items.map((it, j) => (j === i ? { ...it, [k]: v } : it)) }; if (k !== "description") render(); },
    addItem: () => { bd.proposalForm = { ...bd.proposalForm, items: [...bd.proposalForm.items, { description: "", quantity: "1", unit_price: "" }] }; render(); },
    removeItem: (i) => { bd.proposalForm = { ...bd.proposalForm, items: bd.proposalForm.items.filter((_, j) => j !== i) }; render(); },
    proposalEvidence: (id) => { const l = bd.proposalForm.evidence_ids || []; bd.proposalForm = { ...bd.proposalForm, evidence_ids: l.includes(id) ? l.filter((x) => x !== id) : [...l, id] }; },
    cancelProposal: () => { bd.proposalForm = null; render(); },
    saveProposal: () => { const f = bd.proposalForm, p = BD.proposalProblem(f); if (p) return fail(p); return run(async () => { const b = BD.proposalBody(f); await (f.id ? api.updateBdProposal(bd.opp.id, f.id, b) : api.createBdProposal(bd.opp.id, b)); bd.proposalForm = null; await refresh(); }, "Proposal saved as a draft."); },
    submitProposal: (pid) => run(async () => { await api.bdProposalStep(bd.opp.id, pid, "submit"); await refresh(); }, "Submitted. If the discount is above the limit, a different person must approve it."),
    decideProposal: (pid, ok) => { if (!ok) { const p = need("prop", "a note saying why you are sending it back", 3); if (p) return fail(p); } return run(async () => { await api.bdProposalStep(bd.opp.id, pid, ok ? "approve" : "reject", note("prop")); bd.notes.prop = ""; await refresh(); }, ok ? "Discount approved." : "Sent back."); },
    sendProposal: (pid) => run(async () => { await api.bdProposalStep(bd.opp.id, pid, "send"); await refresh(); }, "Marked as sent to the client."),
    acceptProposal: (pid) => { const p = need("prop", "a note about how the client accepted", 3); if (p) return fail(p); return run(async () => { await api.bdProposalStep(bd.opp.id, pid, "accept", note("prop")); bd.notes.prop = ""; await refresh(); }, "Acceptance recorded. Ask for the win to be confirmed."); },
    declineProposal: (pid) => { const p = need("prop", "the reason the client declined", 3); if (p) return fail(p); return run(async () => { await api.bdProposalStep(bd.opp.id, pid, "decline", note("prop")); bd.notes.prop = ""; await refresh(); }, "Decline recorded."); },
    // targets
    newTarget: () => { clearForms(); bd.targetForm = BD.emptyTarget(); render(); },
    targetChange: set("targetForm"),
    cancelTarget: () => { bd.targetForm = null; render(); },
    saveTarget: () => { const p = BD.targetProblem(bd.targetForm); if (p) return fail(p); return run(async () => { const t = await api.createBdTarget(BD.targetBody(bd.targetForm)); bd.targetForm = null; await refresh(); bd.notice = `Target ${t.ref} saved.`; }); },
    retireTarget: (tid) => { const p = need("retire", "a reason", 3); if (p) return fail(p); return run(async () => { await api.retireBdTarget(tid, note("retire")); bd.notes.retire = ""; await refresh(); }, "Target retired."); },
    // reports
    newReport: () => { clearForms(); bd.reportForm = { currency: "", title: "" }; render(); },
    reportChange: set("reportForm"),
    cancelReport: () => { bd.reportForm = null; render(); },
    saveReport: () => { const p = BD.reportProblem(bd.reportForm); if (p) return fail(p); return run(async () => { const r = await api.createBdReport({ currency: bd.reportForm.currency, title: bd.reportForm.title.trim() }); bd.reportForm = null; bd.report = r; await refresh(); bd.notice = `Report ${r.ref} created.`; }); },
    openReport: (id) => run(async () => { clearForms(); bd.report = await api.bdReport(id); }),
    closeReportView: () => run(async () => { bd.report = null; clearForms(); await refresh(); }),
    submitReport: () => run(async () => { await api.submitBdReport(bd.report.id); await refresh(); }, "Frozen and submitted. A different person must now approve it."),
    decideReport: (ok) => { if (!ok) { const p = need("report", "a note saying why you are sending it back", 3); if (p) return fail(p); } return run(async () => { await (ok ? api.approveBdReport(bd.report.id, note("report")) : api.rejectBdReport(bd.report.id, note("report"))); bd.notes.report = ""; await refresh(); }, ok ? "Report approved." : "Sent back."); },
    exportReport: () => run(async () => { const { blob, filename } = await api.exportBdReport(bd.report.id); saveBlob(blob, filename); }, "Downloaded."),
  };
}

// ----------------------------------------------------------------------
// Treasury and Cash (Stage 16): records and checks; never moves money
// ----------------------------------------------------------------------
function newTr() {
  return { tab: "overview", options: null, ov: null, accounts: [], flows: [], payments: [], covenants: [], vault: [], forecast: null, accuracy: null, weeks: 13, possible: false, acct: null, payFilter: "",
    forms: { account: { ...TR.EMPTY.account }, balance: { ...TR.EMPTY.balance }, flow: { ...TR.EMPTY.flow }, payment: { ...TR.EMPTY.payment }, covenant: { ...TR.EMPTY.covenant }, realise: { actual_amount: "", actual_date: "" }, policy: null },
    notes: {}, formError: null, busy: false, error: null, notice: null };
}

function renderTreasuryPage(authState) {
  if (!uiState.tr) uiState.tr = newTr();
  once("trLoading", () => loadTreasury());
  return Treasury({ tr: uiState.tr, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.trLoading, onRetry: () => { loadedOnce.delete("trLoading"); render(); }, actions: treasuryActions() });
}

async function treasuryRefresh(tr) {
  [tr.options, tr.ov, tr.accounts, tr.flows, tr.payments, tr.covenants, tr.accuracy] = await Promise.all([api.trOptions(), api.trOverview(), api.trAccounts(), api.trFlows(), api.trPayments(tr.payFilter), api.trCovenants(), api.trAccuracy()]);
  tr.forms.policy = TR.policyForm(tr.ov.policy);
  if (tr.acct) tr.acct = await api.trAccount(tr.acct.id);
  if (tr.forecast) tr.forecast = await api.trForecast(tr.weeks, tr.possible);
}

async function loadTreasury() {
  const tr = uiState.tr || (uiState.tr = newTr());
  tr.error = null;
  try {
    await treasuryRefresh(tr);
    tr.vault = await api.listEvidence().catch(() => []);
  } catch (err) { tr.error = err.message || "Treasury could not be loaded."; }
}

function treasuryActions() {
  const tr = uiState.tr;
  const run = async (fn, ok) => { tr.error = null; tr.notice = null; tr.formError = null; tr.busy = true; render(); try { await fn(); if (ok) tr.notice = ok; } catch (err) { tr.error = err.message || "That did not work."; } tr.busy = false; render(); };
  const problem = (form, text) => { tr.formError = { form, text }; tr.notice = null; tr.error = null; render(); };
  const fail = (text) => { tr.formError = null; tr.notice = null; tr.error = text; render(); };      // for buttons that sit in rows an approver sees
  const refresh = () => treasuryRefresh(tr);
  const note = (k) => tr.notes[k] || "";
  const reset = (name) => { tr.forms[name] = { ...TR.EMPTY[name] }; };
  return {
    setTab: (t) => run(async () => { tr.tab = t; tr.formError = null; await refresh(); }),
    setForm: (name, k, v, rerender) => { tr.forms[name] = { ...(tr.forms[name] || {}), [k]: v }; if (name === "flow" && k === "account_id") tr.forms.flow.currency = ""; tr.formError = null; if (rerender) render(); },
    setNote: (k, v) => { tr.notes[k] = v; },
    savePolicy: () => { const r = TR.policyPayload(tr.forms.policy); if (r.problem) return problem("policy", r.problem); return run(async () => { await api.setTrPolicy(r.body); await refresh(); }, "Policy saved. It applies from now on."); },
    // accounts
    selectAccount: (id) => run(async () => { tr.acct = id ? await api.trAccount(id) : null; reset("balance"); tr.notes = {}; }),
    openAccount: () => { const r = TR.accountPayload(tr.forms.account); if (r.problem) return problem("account", r.problem); return run(async () => { const c = await api.openTrAccount(r.body); reset("account"); tr.acct = c; await refresh(); }, "Account opened. Record its balance next."); },
    recordBalance: (id) => { const r = TR.balancePayload(tr.forms.balance); if (r.problem) return problem("balance", r.problem); return run(async () => { await api.addTrBalance(id, r.body); reset("balance"); await refresh(); }, "Balance recorded. A different person must confirm it."); },
    confirmBalance: (id, bid) => run(async () => { await api.confirmTrBalance(id, bid); await refresh(); }, "Balance confirmed."),
    closeAccount: (id) => { const p = TR.noteProblem(note("close-account"), "A reason", 5); if (p) return problem("balance", p); return run(async () => { await api.closeTrAccount(id, note("close-account").trim()); tr.acct = null; tr.notes = {}; await refresh(); }, "Account closed."); },
    // forecast and cash flows
    setWeeks: (w) => { tr.weeks = w; },
    setPossible: (v) => { tr.possible = !!v; },
    runForecast: () => run(async () => { tr.forecast = await api.trForecast(tr.weeks, tr.possible); }),
    addFlow: () => { const r = TR.flowPayload(tr.forms.flow); if (r.problem) return problem("flow", r.problem); return run(async () => { await api.addTrFlow(r.body); reset("flow"); await refresh(); }, "Expected cash flow added."); },
    realiseFlow: (id) => { const f = tr.forms.realise, p = TR.amountProblem(f.actual_amount, "The amount that actually moved", { positive: true }) || (TR.isRealDate(f.actual_date) ? "" : "The date it happened must be a real date written YYYY-MM-DD."); if (p) return problem("realise", p);
      return run(async () => { await api.realiseTrFlow(id, { actual_amount: f.actual_amount.replace(/,/g, "").trim(), actual_date: f.actual_date.trim() }); tr.forms.realise = { actual_amount: "", actual_date: "" }; await refresh(); }, "Marked as happened."); },
    cancelFlow: (id) => { const p = TR.noteProblem(note("flow-note"), "A reason", 5); if (p) return problem("realise", p); return run(async () => { await api.cancelTrFlow(id, note("flow-note").trim()); tr.notes["flow-note"] = ""; await refresh(); }, "Cash flow cancelled."); },
    // payments
    filterPayments: (v) => run(async () => { tr.payFilter = v; tr.payments = await api.trPayments(v); }),
    requestPayment: () => { const r = TR.paymentPayload(tr.forms.payment); if (r.problem) return problem("payment", r.problem); return run(async () => { const p = await api.requestTrPayment(r.body); reset("payment"); await refresh(); tr.notice = `Payment ${p.ref} requested${p.flags.length ? ` with ${p.flags.length} warning${p.flags.length > 1 ? "s" : ""}` : ""}. A different person must approve it.`; }); },
    payStep: (id, step) => {
      const n = note(`pay-${id}`).trim();
      if ((step === "reject" || step === "cancel") && TR.noteProblem(n, "A reason", 5)) return fail(TR.noteProblem(n, "A reason", 5));
      const body = step === "release" ? TR.releasePayload({ released_date: note(`reldate-${id}`), bank_reference: note(`relref-${id}`) }) : { body: { note: n } };
      if (body.problem) return fail(body.problem);
      return run(async () => { await api.trPaymentStep(id, step, body.body); tr.notes = {}; await refresh(); }, { approve: "Approval recorded.", reject: "Payment rejected.", cancel: "Request cancelled.", release: "Recorded as released." }[step]);
    },
    // covenants
    addCovenant: () => { const r = TR.covenantPayload(tr.forms.covenant); if (r.problem) return problem("covenant", r.problem); return run(async () => { await api.addTrCovenant(r.body); reset("covenant"); await refresh(); }, "Covenant added."); },
    addResult: (id) => { const name = `result-${id}`, f = tr.forms[name] || { ...TR.EMPTY.result }, r = TR.resultPayload(f); if (r.problem) return problem(name, r.problem);
      return run(async () => { const c = await api.addTrResult(id, r.body); delete tr.forms[name]; await refresh(); tr.notice = c.latest_status === "BREACHED" ? "Result recorded. It is a breach, so a different person must acknowledge it." : `Result recorded: ${TR.label(c.latest_status).toLowerCase()}.`; }); },
    acknowledge: (cid, rid) => { const k = `ack-${rid}`, n = note(k).trim(); if (TR.noteProblem(n, "Your note", 10)) return fail(TR.noteProblem(n, "Your note", 10));
      return run(async () => { await api.ackTrBreach(cid, rid, { waiver_obtained: !!tr.notes[`${k}-waiver`], note: n }); tr.notes = {}; await refresh(); }, "Breach acknowledged. It stays on the record."); },
    retireCovenant: (id) => { const p = TR.noteProblem(note(`retire-${id}`), "A reason", 5); if (p) return problem(`result-${id}`, p); return run(async () => { await api.retireTrCovenant(id, note(`retire-${id}`).trim()); tr.notes = {}; await refresh(); }, "Covenant retired."); },
  };
}

// ----------------------------------------------------------------------
// Procurement (Stage 17): records and checks; never buys or pays
// ----------------------------------------------------------------------
function newPc() {
  const f = () => JSON.parse(JSON.stringify(PC.EMPTY));
  return { tab: "overview", options: null, ov: null, suppliers: [], contracts: [], orders: [], live: [], deliveries: [], invoices: [], reviews: [], released: [], orderFilter: "", sel: { supplier: null, order: null },
    forms: { ...f(), policy: null }, notes: {}, formError: null, busy: false, error: null, notice: null };
}

function renderProcurementPage(authState) {
  if (!uiState.pc) uiState.pc = newPc();
  once("pcLoading", () => loadProcurement());
  return Procurement({ pc: uiState.pc, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.pcLoading, onRetry: () => { loadedOnce.delete("pcLoading"); render(); }, actions: procurementActions() });
}

async function procurementRefresh(pc) {
  [pc.options, pc.ov, pc.suppliers, pc.contracts, pc.orders, pc.live, pc.deliveries, pc.invoices, pc.reviews] = await Promise.all([api.pcOptions(), api.pcOverview(), api.pcSuppliers(), api.pcContracts(), api.pcOrders(pc.orderFilter), api.pcOrders("APPROVED"), api.pcDeliveries(), api.pcInvoices(), api.pcReviews()]);
  pc.forms.policy = PC.policyForm(pc.ov.policy);
  if (pc.sel.supplier) pc.sel.supplier = await api.pcSupplier(pc.sel.supplier.id).catch(() => null);
  if (pc.sel.order) pc.sel.order = await api.pcOrder(pc.sel.order.id).catch(() => null);
  pc.released = await api.trPayments("RELEASED").catch(() => []);
}

async function loadProcurement() {
  const pc = uiState.pc || (uiState.pc = newPc());
  pc.error = null;
  try { await procurementRefresh(pc); } catch (err) { pc.error = err.message || "Procurement could not be loaded."; }
}

function procurementActions() {
  const pc = uiState.pc;
  const run = async (fn, ok) => { pc.error = null; pc.notice = null; pc.formError = null; pc.busy = true; render(); try { await fn(); if (ok) pc.notice = ok; } catch (err) { pc.error = err.message || "That did not work."; } pc.busy = false; render(); };
  const problem = (form, text) => { pc.formError = { form, text }; pc.notice = null; pc.error = null; render(); };
  const fail = (text) => { pc.formError = null; pc.notice = null; pc.error = text; render(); };
  const refresh = () => procurementRefresh(pc);
  const note = (k) => (pc.notes[k] || "").trim();
  const reset = (name) => { pc.forms[name] = JSON.parse(JSON.stringify(PC.EMPTY[name])); };
  const step = (kind, id, m, call, extra) => {
    const n = note(`${kind}-${id}`), min = PC.needsNote[m];
    if (min && PC.noteProblem(n, "A reason", min)) return fail(PC.noteProblem(n, "A reason", min));
    return run(async () => { await call(id, m, n); pc.notes = {}; await refresh(); }, extra[m]);
  };
  return {
    setTab: (t) => run(async () => { pc.tab = t; pc.formError = null; await refresh(); }),
    setForm: (name, k, v, rerender) => { pc.forms[name] = { ...(pc.forms[name] || {}), [k]: v }; pc.formError = null;
      if (name === "delivery" && k === "order_id") pc.forms.delivery = PC.prefillDelivery(pc.live.find((o) => o.id === v));
      if (name === "invoice" && k === "order_id") pc.forms.invoice = PC.prefillInvoice(pc.live.find((o) => o.id === v));
      if (name === "order" && k === "supplier_id") pc.forms.order.contract_id = "";
      if (rerender) render(); },
    setNote: (k, v) => { pc.notes[k] = v; },
    setLine: (i, k, v) => { pc.forms.order.lines[i][k] = v; pc.formError = null; },
    addLine: () => { pc.forms.order.lines.push({ description: "", qty: "", unit_price: "" }); render(); },
    setQty: (form, n, v) => { pc.forms[form].qtys = { ...(pc.forms[form].qtys || {}), [n]: v }; pc.formError = null; },
    setPrice: (n, v) => { pc.forms.invoice.prices = { ...(pc.forms.invoice.prices || {}), [n]: v }; pc.formError = null; },
    savePolicy: () => { const r = PC.policyPayload(pc.forms.policy); if (r.problem) return problem("policy", r.problem); return run(async () => { await api.setPcPolicy(r.body); await refresh(); }, "Policy saved. It applies from now on."); },
    // suppliers
    selectSupplier: (id) => run(async () => { pc.sel.supplier = id ? await api.pcSupplier(id) : null; pc.notes = {}; }),
    registerSupplier: () => { const r = PC.supplierPayload(pc.forms.supplier); if (r.problem) return problem("supplier", r.problem); return run(async () => { const s = await api.registerPcSupplier(r.body); reset("supplier"); await refresh(); pc.notice = `Supplier ${s.ref} registered. A different person must approve it.`; }); },
    supplierStep: (id, m) => step("sup", id, m, (i, mm, n) => api.pcSupplierStep(i, mm, n), { approve: "Supplier approved.", suspend: "Supplier suspended.", reinstate: "Supplier reinstated." }),
    // contracts
    draftContract: () => { const r = PC.contractPayload(pc.forms.contract); if (r.problem) return problem("contract", r.problem); return run(async () => { const c = await api.draftPcContract(r.body); reset("contract"); await refresh(); pc.notice = `Contract ${c.ref} drafted. A different person must approve it.`; }); },
    contractStep: (id, m) => step("con", id, m, (i, mm, n) => api.pcContractStep(i, mm, n), { approve: "Contract approved.", terminate: "Contract terminated." }),
    // orders
    filterOrders: (v) => run(async () => { pc.orderFilter = v; pc.orders = await api.pcOrders(v); }),
    raiseOrder: () => { const r = PC.orderPayload(pc.forms.order); if (r.problem) return problem("order", r.problem); return run(async () => { const o = await api.raisePcOrder(r.body); reset("order"); await refresh(); pc.notice = `Order ${o.ref} raised${o.approvals_needed > 1 ? `. It needs ${o.approvals_needed} different approvers` : ". A different person must approve it"}.`; }); },
    orderStep: (id, m) => step("po", id, m, (i, mm, n) => api.pcOrderStep(i, mm, n), { approve: "Approval recorded.", reject: "Order rejected.", cancel: "Order cancelled.", close: "Order closed." }),
    selectOrder: (id) => run(async () => { pc.sel.order = id ? await api.pcOrder(id) : null; }),
    // deliveries and invoices
    addDelivery: () => { const f = pc.forms.delivery, r = PC.deliveryPayload(f); if (r.problem) return problem("delivery", r.problem); return run(async () => { const d = await api.addPcDelivery(f.order_id, r.body); reset("delivery"); await refresh(); pc.notice = `Delivery ${d.ref} recorded.`; }); },
    addInvoice: () => { const f = pc.forms.invoice, r = PC.invoicePayload(f); if (r.problem) return problem("invoice", r.problem); return run(async () => { const i = await api.addPcInvoice(f.order_id, r.body); reset("invoice"); await refresh();
      pc.notice = i.flags.length ? `Invoice ${i.ref} recorded as an exception: ${i.flags.map(PC.words).join(", ").toLowerCase()}. A different person must decide.` : `Invoice ${i.ref} matched the order and the deliveries. A different person must approve it.`; }); },
    invoiceStep: (id, m) => {
      if (m === "paid") { const r = PC.paidPayload({ treasury_payment_id: pc.notes[`link-${id}`], paid_date: pc.notes[`paiddate-${id}`], bank_reference: pc.notes[`paidref-${id}`] }); if (r.problem) return fail(r.problem); return run(async () => { await api.payPcInvoice(id, r.body); pc.notes = {}; await refresh(); }, "Payment recorded."); }
      const inv = pc.invoices.find((x) => x.id === id), n = note(`iv-${id}`);
      if (m === "approve" && PC.overrideNeeded(inv) && PC.noteProblem(n, "Your reason for accepting the exception", 10)) return fail(PC.noteProblem(n, "Your reason for accepting the exception", 10));
      if (m === "reject" && PC.noteProblem(n, "A reason", 5)) return fail(PC.noteProblem(n, "A reason", 5));
      return run(async () => { await api.pcInvoiceStep(id, m, n); pc.notes = {}; await refresh(); }, m === "approve" ? "Invoice approved." : "Invoice rejected.");
    },
    // reviews
    addReview: () => { const f = pc.forms.review, r = PC.reviewPayload(f); if (r.problem) return problem("review", r.problem); return run(async () => { const x = await api.addPcReview(f.supplier_id, r.body); reset("review"); await refresh(); pc.notice = `Review ${x.ref} saved. Average ${x.average} of 5.`; }); },
  };
}

// ----------------------------------------------------------------------
// Planning and KPIs (Stage 18): records and checks; never calculates or verifies
// ----------------------------------------------------------------------
function newFp() {
  const f = () => JSON.parse(JSON.stringify(FP.EMPTY));
  return { tab: "overview", options: null, ov: null, kpis: [], forecasts: [], accuracy: null, members: [], vault: [], forecastFilter: "", minLead: 0, sel: { kpi: null },
    forms: { ...f(), policy: null }, notes: {}, formError: null, busy: false, error: null, notice: null };
}

function renderFpaPage(authState) {
  if (!uiState.fp) uiState.fp = newFp();
  once("fpLoading", () => loadFpa(authState));
  return Fpa({ fp: uiState.fp, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.fpLoading, onRetry: () => { loadedOnce.delete("fpLoading"); render(); }, actions: fpaActions(authState) });
}

async function fpaRefresh(fp) {
  [fp.options, fp.ov, fp.kpis, fp.forecasts, fp.accuracy] = await Promise.all([api.fpOptions(), api.fpOverview(), api.fpKpis(), api.fpForecasts(fp.forecastFilter), api.fpAccuracy(fp.minLead)]);
  fp.forms.policy = FP.policyForm(fp.ov.policy);
  if (fp.sel.kpi) fp.sel.kpi = await api.fpKpi(fp.sel.kpi.id).catch(() => null);
}

async function loadFpa(authState) {
  const fp = uiState.fp || (uiState.fp = newFp());
  fp.error = null;
  try {
    await fpaRefresh(fp);
    try { fp.members = await api.listMembers(authState.organisationId); } catch (_) { fp.members = []; }
    fp.vault = await api.listEvidence().catch(() => []);
  } catch (err) { fp.error = err.message || "Planning and KPIs could not be loaded."; }
}

function fpaActions(authState) {
  const fp = uiState.fp;
  const run = async (fn, ok) => { fp.error = null; fp.notice = null; fp.formError = null; fp.busy = true; render(); try { await fn(); if (ok) fp.notice = ok; } catch (err) { fp.error = err.message || "That did not work."; } fp.busy = false; render(); };
  const problem = (form, text) => { fp.formError = { form, text }; fp.notice = null; fp.error = null; render(); };
  const fail = (text) => { fp.formError = null; fp.notice = null; fp.error = text; render(); };
  const refresh = () => fpaRefresh(fp);
  const note = (k) => (fp.notes[k] || "").trim();
  const reset = (name) => { fp.forms[name] = JSON.parse(JSON.stringify(FP.EMPTY[name])); };
  const needNote = (n, m) => { const min = FP.minNote[m]; return min ? FP.noteProblem(n, "A reason", min) : ""; };
  return {
    setTab: (t) => run(async () => { fp.tab = t; fp.formError = null; await refresh(); }),
    setForm: (name, k, v, rerender) => { fp.forms[name] = { ...(fp.forms[name] || {}), [k]: v }; fp.formError = null; if (rerender) render(); },
    setNote: (k, v) => { fp.notes[k] = v; },
    savePolicy: () => { const r = FP.policyPayload(fp.forms.policy); if (r.problem) return problem("policy", r.problem); return run(async () => { await api.setFpPolicy(r.body); await refresh(); }, "Settings saved. They apply from now on."); },
    // KPIs
    selectKpi: (id) => run(async () => { fp.sel.kpi = id ? await api.fpKpi(id) : null; fp.notes = {}; fp.forms.reading = { ...FP.EMPTY.reading, period_end: (fp.sel.kpi && fp.sel.kpi.next_period_end) || "" }; }),
    defineKpi: () => { const r = FP.kpiPayload(fp.forms.kpi); if (r.problem) return problem("kpi", r.problem); return run(async () => { const k = await api.defineFpKpi(r.body); reset("kpi"); await refresh(); fp.notice = `KPI ${k.ref} defined. A different person must approve the target, and the owner must accept ownership.`; }); },
    kpiStep: (id, m) => {
      const n = note(`kpi-${id}`), p = needNote(n, m); if (p) return fail(p);
      if (m === "accept") return run(async () => { await api.acceptFpKpi(id); await refresh(); }, "Ownership accepted. You can now record readings.");
      return run(async () => { await api.fpKpiStep(id, m, n); fp.notes = {}; await refresh(); }, m === "approve" ? "KPI approved." : "KPI retired.");
    },
    changeOwner: (id) => { const r = FP.reassignPayload(fp.forms.reassign); if (r.problem) return problem(`owner-${id}`, r.problem); return run(async () => { await api.changeFpOwner(id, r.body); fp.forms.reassign = { ...FP.EMPTY.reassign }; await refresh(); }, "Owner changed. The new owner must accept before recording readings."); },
    recordReading: (id) => { const k = fp.sel.kpi, r = FP.readingPayload(fp.forms.reading, k.unit); if (r.problem) return problem("reading", r.problem); return run(async () => { const x = await api.addFpReading(id, r.body); fp.forms.reading = { ...FP.EMPTY.reading }; await refresh(); fp.notice = `Reading ${x.ref} recorded. A different person must review it.`; }); },
    readingStep: (kid, rid, m) => {
      const n = note(`rd-${kid}`), p = needNote(n, m); if (p) return fail(p);
      return run(async () => { await api.fpReadingStep(kid, rid, m, n); fp.notes = {}; await refresh(); }, m === "review" ? "Reading reviewed." : "Reading rejected. The owner can record it again.");
    },
    // forecasts
    filterForecasts: (v) => run(async () => { fp.forecastFilter = v; fp.forecasts = await api.fpForecasts(v); }),
    registerForecast: () => { const r = FP.forecastPayload(fp.forms.forecast); if (r.problem) return problem("forecast", r.problem); return run(async () => { const f = await api.registerFpForecast(r.body); reset("forecast"); await refresh(); fp.notice = `Forecast ${f.ref} registered on ${f.made_on}. It cannot be changed, only withdrawn.`; }); },
    forecastStep: (id, m) => {
      const x = fp.forecasts.find((f) => f.id === id), n = note(`fc-${id}`);
      if (m === "actual") { const r = FP.actualPayload({ value: fp.notes[`actval-${id}`], source_note: fp.notes[`actsrc-${id}`], evidence_id: fp.notes[`actdoc-${id}`] }, x.unit); if (r.problem) return fail(r.problem); return run(async () => { await api.addFpActual(id, r.body); fp.notes = {}; await refresh(); }, "Actual recorded. A third person must confirm it."); }
      const p = m === "reject" || m === "withdraw" ? FP.noteProblem(n, "A reason", 5) : ""; if (p) return fail(p);
      const step = { withdraw: "withdraw", confirm: "actual/confirm", reject: "actual/reject" }[m];
      return run(async () => { await api.fpForecastStep(id, step, n); fp.notes = {}; await refresh(); }, { withdraw: "Forecast withdrawn.", confirm: "Actual confirmed. It now counts towards accuracy.", reject: "Actual rejected. The forecast is waiting for the right figure." }[m]);
    },
    setMinLead: (n) => run(async () => { fp.minLead = n; fp.accuracy = await api.fpAccuracy(n); }),
  };
}

// ----------------------------------------------------------------------
// Financial-crime casework (Stage 19): records and checks; never screens, monitors or files
// ----------------------------------------------------------------------
function newFx() {
  const f = () => JSON.parse(JSON.stringify(FX.EMPTY));
  return { tab: "overview", options: null, ov: null, alerts: [], cases: [], sel: { case: null }, members: [], vault: [], forms: { ...f(), policy: null }, notes: {}, formError: null, busy: false, error: null, notice: null };
}

function renderFincrimePage(authState) {
  if (!uiState.fx) uiState.fx = newFx();
  once("fxLoading", () => loadFincrime(authState));
  return Fincrime({ fc: uiState.fx, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.fxLoading, onRetry: () => { loadedOnce.delete("fxLoading"); render(); }, actions: fincrimeActions(authState) });
}

async function fincrimeRefresh(fx) {
  [fx.options, fx.ov, fx.alerts, fx.cases] = await Promise.all([api.fcOptions(), api.fcOverview(), api.fcAlerts(), api.fcCases()]);
  fx.forms.policy = FX.policyForm(fx.ov.policy);
  if (fx.sel.case) fx.sel.case = await api.fcCase(fx.sel.case.id).catch(() => null);
}

async function loadFincrime(authState) {
  const fx = uiState.fx || (uiState.fx = newFx());
  fx.error = null;
  try {
    await fincrimeRefresh(fx);
    try { fx.members = await api.listMembers(authState.organisationId); } catch (_) { fx.members = []; }
    fx.vault = await api.listEvidence().catch(() => []);
  } catch (err) { fx.error = err.message || "Financial-crime casework could not be loaded."; }
}

function fincrimeActions(authState) {
  const fx = uiState.fx;
  const run = async (fn, ok) => { fx.error = null; fx.notice = null; fx.formError = null; fx.busy = true; render(); try { await fn(); if (ok) fx.notice = ok; } catch (err) { fx.error = err.message || "That did not work."; } fx.busy = false; render(); };
  const problem = (form, text) => { fx.formError = { form, text }; fx.notice = null; fx.error = null; render(); };
  const fail = (text) => { fx.formError = null; fx.notice = null; fx.error = text; render(); };
  const refresh = () => fincrimeRefresh(fx);
  const reset = (name) => { fx.forms[name] = JSON.parse(JSON.stringify(FX.EMPTY[name])); };
  const note = (k) => (fx.notes[k] || "").trim();
  const act = (form, build, call, ok, after) => { const r = build(fx.forms[form]); if (r.problem) return problem(form, r.problem); return run(async () => { const x = await call(r.body); if (after) after(x); await refresh(); }, ok); };
  return {
    setTab: (t) => run(async () => { fx.tab = t; fx.formError = null; await refresh(); }),
    setForm: (name, k, v, rerender) => { fx.forms[name] = { ...(fx.forms[name] || {}), [k]: v }; fx.formError = null; if (rerender) render(); },
    setNote: (k, v) => { fx.notes[k] = v; },
    toggleAlert: (id, on) => { const cur = fx.forms.casef.alert_ids || []; fx.forms.casef = { ...fx.forms.casef, alert_ids: on ? [...new Set([...cur, id])] : cur.filter((x) => x !== id) }; },
    savePolicy: () => { const r = FX.policyPayload(fx.forms.policy); if (r.problem) return problem("policy", r.problem); return run(async () => { await api.setFcPolicy(r.body); await refresh(); }, "Targets saved. They apply from now on."); },
    raiseAlert: () => act("alert", FX.alertPayload, (b) => api.raiseFcAlert(b), "Alert raised.", () => reset("alert")),
    dismissAlert: (id) => { const n = note(`al-${id}`), p = FX.noteProblem(n, "A reason", FX.minNote.dismiss); if (p) return fail(p); return run(async () => { await api.dismissFcAlert(id, n); fx.notes = {}; await refresh(); }, "Alert dismissed. The reason is kept."); },
    selectCase: (id) => run(async () => { fx.sel.case = id ? await api.fcCase(id) : null; fx.notes = {}; fx.forms.declare = { ...FX.EMPTY.declare }; }),
    openCase: () => act("casef", FX.casePayload, (b) => api.openFcCase(b), null, (c) => { reset("casef"); fx.sel.case = c; fx.notice = `Case ${c.ref} opened. You are the lead investigator.`; }),
    declare: (id) => act("declare", FX.declarePayload, (b) => api.declareFc(id, b), "Declaration recorded.", () => { fx.forms.declare = { ...FX.EMPTY.declare }; }),
    addEvent: (id) => act("event", FX.eventPayload, (b) => api.addFcEvent(id, b), "Added to the timeline.", () => reset("event")),
    recordScreening: (id) => act("screening", FX.screeningPayload, (b) => api.recordFcScreening(id, b), "Screening result recorded. A possible match must be resolved by a different person.", () => reset("screening")),
    resolveScreening: (cid, sid, outcome) => { const n = note(`case-${cid}`), r = FX.resolvePayload(outcome, n); if (r.problem) return fail(r.problem); return run(async () => { await api.resolveFcScreening(cid, sid, r.body); fx.notes = {}; await refresh(); }, "Screening result resolved."); },
    recordLoss: (id) => act("loss", FX.lossPayload, (b) => api.recordFcLoss(id, b), "Loss recorded.", () => reset("loss")),
    recordRecovery: (id) => act("recovery", FX.recoveryPayload, (b) => api.recordFcRecovery(id, b), "Recovery recorded. A different person must confirm it.", () => reset("recovery")),
    recoveryStep: (cid, rid, m) => {
      if (m === "confirm") return run(async () => { await api.confirmFcRecovery(cid, rid); await refresh(); }, "Recovery confirmed.");
      const n = note(`case-${cid}`), p = FX.noteProblem(n, "A reason", FX.minNote.reject_recovery); if (p) return fail(p);
      return run(async () => { await api.rejectFcRecovery(cid, rid, n); fx.notes = {}; await refresh(); }, "Recovery rejected.");
    },
    propose: (id) => act("decision", FX.decisionPayload, (b) => api.proposeFcDecision(id, b), "Outcome proposed. A different person must decide it.", () => reset("decision")),
    decisionStep: (id, m) => {
      const n = note(`case-${id}`);
      if (m === "approve") return run(async () => { await api.approveFcDecision(id, n); fx.notes = {}; await refresh(); }, "Outcome approved. The case is closed.");
      const p = FX.noteProblem(n, "A reason", FX.minNote.reject); if (p) return fail(p);
      return run(async () => { await api.rejectFcDecision(id, n); fx.notes = {}; await refresh(); }, "Outcome sent back to the lead investigator.");
    },
    reopen: (id) => { const n = note(`case-${id}`), p = FX.noteProblem(n, "A reason", FX.minNote.reopen); if (p) return fail(p); return run(async () => { await api.reopenFcCase(id, n); fx.notes = {}; await refresh(); }, "Case reopened. The history is kept."); },
    changeLead: (id) => act("lead", FX.leadPayload, (b) => api.changeFcLead(id, b), "Lead investigator changed.", () => reset("lead")),
  };
}

// ----------------------------------------------------------------------
// IT audit (Stage 20): records and checks; never connects to, scans or tests a system
// ----------------------------------------------------------------------
function newIa() {
  const f = () => JSON.parse(JSON.stringify(IA.EMPTY));
  return { tab: "overview", options: null, ov: null, changes: [], controls: [], tests: [], sel: { test: null }, vault: [], flaggedOnly: false, forms: { ...f(), policy: null }, notes: {}, formError: null, busy: false, error: null, notice: null };
}

function renderItAuditPage(authState) {
  if (!uiState.ia) uiState.ia = newIa();
  once("iaLoading", () => loadItAudit());
  return ItAudit({ ia: uiState.ia, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.iaLoading, onRetry: () => { loadedOnce.delete("iaLoading"); render(); }, actions: itAuditActions() });
}

async function itAuditRefresh(ia) {
  [ia.options, ia.ov, ia.changes, ia.controls, ia.tests] = await Promise.all([api.iaOptions(), api.iaOverview(), api.iaChanges(), api.iaControls(), api.iaTests()]);
  ia.forms.policy = IA.policyForm(ia.ov.policy);
  if (ia.sel.test) ia.sel.test = await api.iaTest(ia.sel.test.id).catch(() => null);
}

async function loadItAudit() {
  const ia = uiState.ia || (uiState.ia = newIa());
  ia.error = null;
  try {
    await itAuditRefresh(ia);
    ia.vault = await api.listEvidence().catch(() => []);
  } catch (err) { ia.error = err.message || "IT audit could not be loaded."; }
}

function itAuditActions() {
  const ia = uiState.ia;
  const run = async (fn, ok) => { ia.error = null; ia.notice = null; ia.formError = null; ia.busy = true; render(); try { await fn(); if (ok) ia.notice = ok; } catch (err) { ia.error = err.message || "That did not work."; } ia.busy = false; render(); };
  const problem = (form, text) => { ia.formError = { form, text }; ia.notice = null; ia.error = null; render(); };
  const fail = (text) => { ia.formError = null; ia.notice = null; ia.error = text; render(); };
  const refresh = () => itAuditRefresh(ia);
  const reset = (name) => { ia.forms[name] = JSON.parse(JSON.stringify(IA.EMPTY[name])); };
  const note = (k) => (ia.notes[k] || "").trim();
  const act = (form, build, call, ok, after) => { const r = build(ia.forms[form]); if (r.problem) return problem(form, r.problem); return run(async () => { const x = await call(r.body); if (after) after(x); await refresh(); }, ok); };
  return {
    setTab: (t) => run(async () => { ia.tab = t; ia.formError = null; await refresh(); }),
    setForm: (name, k, v, rerender) => { ia.forms[name] = { ...(ia.forms[name] || {}), [k]: v }; ia.formError = null; if (rerender) render(); },
    setNote: (k, v) => { ia.notes[k] = v; },
    toggleFlagged: () => { ia.flaggedOnly = !ia.flaggedOnly; render(); },
    savePolicy: () => { const r = IA.policyPayload(ia.forms.policy); if (r.problem) return problem("policy", r.problem); return run(async () => { await api.setIaPolicy(r.body); await refresh(); }, "Settings saved. They apply to changes recorded from now on."); },
    recordChange: () => act("change", IA.changePayload, (b) => api.recordIaChange(b), null, (c) => { reset("change"); ia.notice = `Change ${c.ref} recorded${c.flags.length ? ` with ${c.flags.length} flag(s)` : ""}.`; }),
    voidChange: (id) => { const n = note(`void-${id}`), p = IA.noteProblem(n, "A reason", IA.minNote.void); if (p) return fail(p); return run(async () => { await api.voidIaChange(id, n); ia.notes = {}; await refresh(); }, "Change record voided. The reason is kept."); },
    defineControl: () => act("control", IA.controlPayload, (b) => api.defineIaControl(b), null, (c) => { reset("control"); ia.notice = `Control ${c.ref} defined. A different person must test it.`; }),
    retireControl: (id) => { const n = note(`retire-${id}`), p = IA.noteProblem(n, "A reason", IA.minNote.retire); if (p) return fail(p); return run(async () => { await api.retireIaControl(id, n); ia.notes = {}; await refresh(); }, "Control retired. The reason is kept."); },
    selectTest: (id) => run(async () => { ia.sel.test = id ? await api.iaTest(id) : null; ia.notes = {}; }),
    planChangeTest: () => act("ptest", IA.ptestPayload, (b) => api.planIaChangeTest(b), null, (t) => { reset("ptest"); ia.sel.test = t; ia.notice = `Test ${t.ref} planned with ${t.items.length} sampled change(s).`; }),
    planControlTest: () => act("ctest", IA.ctestPayload, (b) => api.planIaControlTest(b), null, (t) => { reset("ctest"); ia.sel.test = t; ia.notice = `Test ${t.ref} planned.`; }),
    concludeItem: (item, result) => {
      const t = ia.sel.test, r = IA.itemPayload(result, note(`it-${item.id}`), item.flags.length > 0); if (r.problem) return fail(r.problem);
      return run(async () => { await api.concludeIaItem(t.id, item.id, r.body); ia.notes = {}; await refresh(); }, `${item.ref} concluded.`);
    },
    addCase: (id) => act("case", IA.casePayload, (b) => api.addIaCase(id, b), "Test case added.", () => reset("case")),
    withdrawTest: (id) => { const n = note(`wd-${id}`), p = IA.noteProblem(n, "A reason", IA.minNote.withdraw); if (p) return fail(p); return run(async () => { await api.withdrawIaTest(id, n); ia.notes = {}; await refresh(); }, "Test withdrawn. Its sample and reason are kept."); },
    submitTest: (id) => run(async () => { await api.submitIaTest(id); await refresh(); }, "Test submitted. A different person must approve it."),
    decideTest: (id, m, t) => {
      const n = note(`test-${id}`);
      if (m === "approve") { const p = IA.needsApprovalNote(t) ? IA.noteProblem(n, "A note", IA.minNote.approve) : (n ? IA.noteProblem(n, "A note", IA.minNote.approve) : ""); if (p) return fail(p); return run(async () => { await api.approveIaTest(id, n); ia.notes = {}; await refresh(); }, "Test approved."); }
      const p = IA.noteProblem(n, "A reason", IA.minNote.reject); if (p) return fail(p);
      return run(async () => { await api.rejectIaTest(id, n); ia.notes = {}; await refresh(); }, "Test sent back to the person who carried it out.");
    },
  };
}

// ----------------------------------------------------------------------
// Risk indicators and resilience (Stage 21): records and checks; measures nothing, connects to nothing
// ----------------------------------------------------------------------
function newRs() {
  const f = () => JSON.parse(JSON.stringify(RS.EMPTY));
  return { tab: "overview", options: null, ov: null, kris: [], losses: [], processes: [], drills: [], sel: { kri: null, loss: null }, vault: [], forms: { ...f(), review: { cause: "", lesson: "" }, policy: null }, notes: {}, formError: null, busy: false, error: null, notice: null };
}

function renderResiliencePage(authState) {
  if (!uiState.rs) uiState.rs = newRs();
  once("rsLoading", () => loadResilience());
  return Resilience({ rs: uiState.rs, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.rsLoading, onRetry: () => { loadedOnce.delete("rsLoading"); render(); }, actions: resilienceActions() });
}

async function resilienceRefresh(rs) {
  [rs.options, rs.ov, rs.kris, rs.losses, rs.processes, rs.drills] = await Promise.all([api.rsOptions(), api.rsOverview(), api.rsKris(), api.rsLosses(), api.rsProcesses(), api.rsDrills()]);
  rs.forms.policy = RS.policyForm(rs.ov.policy);
  if (rs.sel.kri) rs.sel.kri = await api.rsKri(rs.sel.kri.id).catch(() => null);
  if (rs.sel.loss) rs.sel.loss = await api.rsLoss(rs.sel.loss.id).catch(() => null);
}

async function loadResilience() {
  const rs = uiState.rs || (uiState.rs = newRs());
  rs.error = null;
  try {
    await resilienceRefresh(rs);
    rs.vault = await api.listEvidence().catch(() => []);
  } catch (err) { rs.error = err.message || "Risk indicators and resilience could not be loaded."; }
}

function resilienceActions() {
  const rs = uiState.rs;
  const run = async (fn, ok) => { rs.error = null; rs.notice = null; rs.formError = null; rs.busy = true; render(); try { await fn(); if (ok) rs.notice = ok; } catch (err) { rs.error = err.message || "That did not work."; } rs.busy = false; render(); };
  const problem = (form, text) => { rs.formError = { form, text }; rs.notice = null; rs.error = null; render(); };
  const fail = (text) => { rs.formError = null; rs.notice = null; rs.error = text; render(); };
  const refresh = () => resilienceRefresh(rs);
  const reset = (name) => { rs.forms[name] = JSON.parse(JSON.stringify(RS.EMPTY[name] || { cause: "", lesson: "" })); };
  const note = (k) => (rs.notes[k] || "").trim();
  const act = (form, build, call, ok, after) => { const r = build(rs.forms[form]); if (r.problem) return problem(form, r.problem); return run(async () => { const x = await call(r.body); if (after) after(x); await refresh(); }, ok); };
  const needNote = (k, what, min) => RS.noteProblem(note(k), what, min);
  return {
    setTab: (t) => run(async () => { rs.tab = t; rs.formError = null; await refresh(); }),
    setForm: (name, k, v, rerender) => { rs.forms[name] = { ...(rs.forms[name] || {}), [k]: v }; rs.formError = null; if (rerender) render(); },
    setNote: (k, v) => { rs.notes[k] = v; },
    savePolicy: () => { const r = RS.policyPayload(rs.forms.policy); if (r.problem) return problem("policy", r.problem); return run(async () => { await api.setRsPolicy(r.body); await refresh(); }, "Settings saved. They apply from now on."); },
    selectKri: (id) => run(async () => { rs.sel.kri = id ? await api.rsKri(id) : null; rs.notes = {}; reset("reading"); }),
    proposeKri: () => act("kri", RS.kriPayload, (b) => api.proposeRsKri(b), null, (k) => { reset("kri"); rs.notice = `Indicator ${k.ref} proposed. A different person must approve it.`; }),
    kriStep: (id, m) => {
      const n = note(`kri-${id}`);
      if (m === "approve") return run(async () => { await api.approveRsKri(id, n); rs.notes = {}; await refresh(); }, "Indicator approved. Its thresholds can no longer be changed.");
      const p = needNote(`kri-${id}`, "A reason", RS.minNote[m === "reject" ? "reject" : "retire"]); if (p) return fail(p);
      return run(async () => { await (m === "reject" ? api.rejectRsKri(id, n) : api.retireRsKri(id, n)); rs.notes = {}; await refresh(); }, m === "reject" ? "Indicator rejected. The reason is kept." : "Indicator retired. The reason is kept.");
    },
    recordReading: (id) => act("reading", RS.readingPayload, (b) => api.recordRsReading(id, b), "Reading recorded. It counts once a different person confirms it.", () => reset("reading")),
    readingStep: (kid, rid, m) => {
      if (m === "confirm") return run(async () => { await api.confirmRsReading(kid, rid); await refresh(); }, "Reading confirmed.");
      const p = needNote(`kri-${kid}`, "A reason", RS.minNote.reject); if (p) return fail(p);
      return run(async () => { await api.rejectRsReading(kid, rid, note(`kri-${kid}`)); rs.notes = {}; await refresh(); }, "Reading rejected. The reason is kept.");
    },
    selectLoss: (id) => run(async () => { rs.sel.loss = id ? await api.rsLoss(id) : null; rs.notes = {}; reset("review"); }),
    recordLoss: () => act("loss", RS.lossPayload, (b) => api.recordRsLoss(b), null, (e) => { reset("loss"); rs.notice = `${e.ref} recorded. A different person must review it.`; }),
    reviewLoss: (id) => act("review", RS.reviewPayload, (b) => api.reviewRsLoss(id, b), "Loss event reviewed.", () => { reset("review"); rs.sel.loss = null; }),
    voidLoss: (id) => { const p = needNote(`void-${id}`, "A reason", RS.minNote.void); if (p) return fail(p); return run(async () => { await api.voidRsLoss(id, note(`void-${id}`)); rs.notes = {}; rs.sel.loss = null; await refresh(); }, "Loss event voided. The reason is kept."); },
    proposeProcess: () => act("process", RS.processPayload, (b) => api.proposeRsProcess(b), null, (p) => { reset("process"); rs.notice = `Process ${p.ref} proposed. A different person must approve it.`; }),
    processStep: (id, m) => {
      const n = note(`proc-${id}`);
      if (m === "approve") return run(async () => { await api.approveRsProcess(id, n); rs.notes = {}; await refresh(); }, "Process approved. Its objectives can no longer be changed.");
      const p = needNote(`proc-${id}`, "A reason", RS.minNote[m === "reject" ? "reject" : "retire"]); if (p) return fail(p);
      return run(async () => { await (m === "reject" ? api.rejectRsProcess(id, n) : api.retireRsProcess(id, n)); rs.notes = {}; await refresh(); }, m === "reject" ? "Process rejected. The reason is kept." : "Process retired. The reason is kept.");
    },
    recordDrill: () => act("drill", RS.drillPayload, (b) => api.recordRsDrill(b), null, (t) => { reset("drill"); rs.notice = `Test ${t.ref} recorded: ${RS.statusOf(t.result).label}. A different person must approve it.`; }),
    drillStep: (id, m, t) => {
      const n = note(`drill-${id}`);
      if (m === "approve") { const p = t.result === "NOT_MET" ? needNote(`drill-${id}`, "A note", RS.minNote.approveMiss) : (n ? needNote(`drill-${id}`, "A note", RS.minNote.approveMiss) : ""); if (p) return fail(p); return run(async () => { await api.approveRsDrill(id, n); rs.notes = {}; await refresh(); }, "Test approved."); }
      const p = needNote(`drill-${id}`, "A reason", RS.minNote.reject); if (p) return fail(p);
      return run(async () => { await api.rejectRsDrill(id, n); rs.notes = {}; await refresh(); }, "Test rejected. The reason is kept.");
    },
  };
}

// ----------------------------------------------------------------------
// AI governance (Stage 22): records and checks; connects to no AI system, tests nothing
// ----------------------------------------------------------------------
function newGv() {
  const f = () => JSON.parse(JSON.stringify(GV.EMPTY));
  return { tab: "overview", options: null, ov: null, systems: [], changes: [], incidents: [], sel: { system: null, incident: null }, vault: [], forms: { ...f(), policy: null }, notes: {}, formError: null, busy: false, error: null, notice: null };
}

function renderAigovPage(authState) {
  if (!uiState.gv) uiState.gv = newGv();
  once("gvLoading", () => loadAigov());
  return AiGovernance({ gv: uiState.gv, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.gvLoading, onRetry: () => { loadedOnce.delete("gvLoading"); render(); }, actions: aigovActions() });
}

async function aigovRefresh(gv) {
  [gv.options, gv.ov, gv.systems, gv.changes, gv.incidents] = await Promise.all([api.gvOptions(), api.gvOverview(), api.gvSystems(), api.gvChanges(), api.gvIncidents()]);
  gv.forms.policy = GV.policyForm(gv.ov.policy);
  if (gv.sel.system) gv.sel.system = await api.gvSystem(gv.sel.system.id).catch(() => null);
  if (gv.sel.incident) gv.sel.incident = await api.gvIncident(gv.sel.incident.id).catch(() => null);
}

async function loadAigov() {
  const gv = uiState.gv || (uiState.gv = newGv());
  gv.error = null;
  try {
    await aigovRefresh(gv);
    gv.vault = await api.listEvidence().catch(() => []);
  } catch (err) { gv.error = err.message || "AI governance could not be loaded."; }
}

function aigovActions() {
  const gv = uiState.gv;
  const run = async (fn, ok) => { gv.error = null; gv.notice = null; gv.formError = null; gv.busy = true; render(); try { await fn(); if (ok) gv.notice = ok; } catch (err) { gv.error = err.message || "That did not work."; } gv.busy = false; render(); };
  const problem = (form, text) => { gv.formError = { form, text }; gv.notice = null; gv.error = null; render(); };
  const fail = (text) => { gv.formError = null; gv.notice = null; gv.error = text; render(); };
  const refresh = () => aigovRefresh(gv);
  const reset = (name) => { gv.forms[name] = JSON.parse(JSON.stringify(GV.EMPTY[name])); };
  const note = (k) => (gv.notes[k] || "").trim();
  const act = (form, build, call, ok, after) => { const r = build(gv.forms[form]); if (r.problem) return problem(form, r.problem); return run(async () => { const x = await call(r.body); if (after) after(x); await refresh(); }, ok); };
  const needNote = (k, what, min) => GV.noteProblem(note(k), what, min);
  return {
    setTab: (t) => run(async () => { gv.tab = t; gv.formError = null; await refresh(); }),
    setForm: (name, k, v, rerender) => { gv.forms[name] = { ...(gv.forms[name] || {}), [k]: v }; gv.formError = null; if (rerender) render(); },
    setNote: (k, v) => { gv.notes[k] = v; },
    savePolicy: () => { const r = GV.policyPayload(gv.forms.policy); if (r.problem) return problem("policy", r.problem); return run(async () => { await api.setGvPolicy(r.body); await refresh(); }, "Settings saved. They apply from now on."); },
    selectSystem: (id) => run(async () => { gv.sel.system = id ? await api.gvSystem(id) : null; gv.notes = {}; }),
    proposeSystem: () => act("system", GV.systemPayload, (b) => api.proposeGvSystem(b), null, (s) => { reset("system"); gv.notice = `AI system ${s.ref} proposed. A different person must approve it.`; }),
    systemStep: (id, m) => {
      const n = note(`sys-${id}`);
      if (m === "approve") return run(async () => { await api.approveGvSystem(id, n); gv.notes = {}; await refresh(); }, "AI system approved. Its intended use and tier can no longer be changed.");
      const p = needNote(`sys-${id}`, "A note", GV.minNote[m]); if (p) return fail(p);
      if (m === "review") return run(async () => { await api.reviewGvSystem(id, n); gv.notes = {}; await refresh(); }, "Review recorded.");
      return run(async () => { await (m === "reject" ? api.rejectGvSystem(id, n) : api.retireGvSystem(id, n)); gv.notes = {}; await refresh(); }, m === "reject" ? "AI system rejected. The reason is kept." : "AI system retired. The reason is kept.");
    },
    recordChange: () => act("change", GV.changePayload, (b) => api.recordGvChange(b), null, (c) => { reset("change"); gv.notice = `Change ${c.ref} recorded. A different person must approve it.`; }),
    changeStep: (id, m) => {
      const n = note(`chg-${id}`);
      if (m === "approve") return run(async () => { await api.approveGvChange(id, n); gv.notes = {}; await refresh(); }, "Change approved.");
      const p = needNote(`chg-${id}`, "A reason", GV.minNote.reject); if (p) return fail(p);
      return run(async () => { await api.rejectGvChange(id, n); gv.notes = {}; await refresh(); }, "Change rejected. The reason is kept.");
    },
    selectIncident: (id) => run(async () => { gv.sel.incident = id ? await api.gvIncident(id) : null; gv.notes = {}; reset("review"); }),
    recordIncident: () => act("incident", GV.incidentPayload, (b) => api.recordGvIncident(b), null, (i) => { reset("incident"); gv.notice = `${i.ref} recorded. A different person must review it.`; }),
    reviewIncident: (id) => act("review", GV.reviewPayload, (b) => api.reviewGvIncident(id, b), "Incident reviewed.", () => { reset("review"); gv.sel.incident = null; }),
    voidIncident: (id) => { const p = needNote(`void-${id}`, "A reason", GV.minNote.void); if (p) return fail(p); return run(async () => { await api.voidGvIncident(id, note(`void-${id}`)); gv.notes = {}; gv.sel.incident = null; await refresh(); }, "Incident voided. The reason is kept."); },
  };
}

// ----------------------------------------------------------------------
// Quality management (Stage 23): records and checks; inspects and measures nothing
// ----------------------------------------------------------------------
function newQl() {
  const f = () => JSON.parse(JSON.stringify(QL.EMPTY));
  return { tab: "overview", options: null, ov: null, ncs: [], actions: [], sel: { nc: null }, vault: [], forms: { ...f(), policy: null }, notes: {}, formError: null, busy: false, error: null, notice: null };
}

function renderQualityPage(authState) {
  if (!uiState.ql) uiState.ql = newQl();
  once("qlLoading", () => loadQuality());
  return Quality({ ql: uiState.ql, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.qlLoading, onRetry: () => { loadedOnce.delete("qlLoading"); render(); }, actions: qualityActions() });
}

async function qualityRefresh(ql) {
  [ql.options, ql.ov, ql.ncs, ql.actions] = await Promise.all([api.qlOptions(), api.qlOverview(), api.qlNcs(), api.qlActions()]);
  ql.forms.policy = QL.policyForm(ql.ov.policy);
  if (ql.sel.nc) ql.sel.nc = await api.qlNc(ql.sel.nc.id).catch(() => null);
}

async function loadQuality() {
  const ql = uiState.ql || (uiState.ql = newQl());
  ql.error = null;
  try {
    await qualityRefresh(ql);
    ql.vault = await api.listEvidence().catch(() => []);
  } catch (err) { ql.error = err.message || "Quality management could not be loaded."; }
  render();
}

function qualityActions() {
  const ql = uiState.ql;
  const run = async (fn, ok) => { ql.error = null; ql.notice = null; ql.formError = null; ql.busy = true; render(); try { await fn(); if (ok) ql.notice = ok; } catch (err) { ql.error = err.message || "That did not work."; } ql.busy = false; render(); };
  const problem = (form, text) => { ql.formError = { form, text }; ql.notice = null; ql.error = null; render(); };
  const fail = (text) => { ql.formError = null; ql.notice = null; ql.error = text; render(); };
  const refresh = () => qualityRefresh(ql);
  const reset = (name) => { ql.forms[name] = JSON.parse(JSON.stringify(QL.EMPTY[name])); };
  const note = (k) => (ql.notes[k] || "").trim();
  const needNote = (k, what, min) => QL.noteProblem(note(k), what, min);
  const act = (form, errForm, build, call, ok, after) => { const r = build(ql.forms[form]); if (r.problem) return problem(errForm, r.problem); return run(async () => { const x = await call(r.body); if (after) after(x); await refresh(); }, ok); };
  return {
    setTab: (t) => run(async () => { ql.tab = t; ql.formError = null; await refresh(); }),
    setForm: (name, k, v, rerender) => { ql.forms[name] = { ...(ql.forms[name] || {}), [k]: v }; ql.formError = null; if (rerender) render(); },
    setNote: (k, v) => { ql.notes[k] = v; },
    savePolicy: () => { const r = QL.policyPayload(ql.forms.policy); if (r.problem) return problem("policy", r.problem); return run(async () => { await api.setQlPolicy(r.body); await refresh(); }, "Settings saved. They apply from now on."); },
    selectNc: (id) => run(async () => { ql.sel.nc = id ? await api.qlNc(id) : null; ql.notes = {}; reset("analyse"); reset("close"); }),
    raiseNc: () => act("nc", "nc", QL.ncPayload, (b) => api.raiseQlNc(b), null, (n) => { reset("nc"); ql.notice = `${n.ref} raised. Record its analysis next.`; }),
    analyseNc: (id) => act("analyse", "analyse", QL.analysePayload, (b) => api.analyseQlNc(id, b), "Analysis recorded.", () => { reset("analyse"); }),
    closeNc: (id) => act("close", "close", QL.closePayload, (b) => api.closeQlNc(id, b), "Nonconformance closed.", () => { reset("close"); ql.sel.nc = null; }),
    voidNc: (id) => { const p = needNote(`void-${id}`, "A reason", QL.minNote.void); if (p) return fail(p); return run(async () => { await api.voidQlNc(id, note(`void-${id}`)); ql.notes = {}; ql.sel.nc = null; await refresh(); }, "Record voided. The reason is kept."); },
    addAction: () => act("action", "action", QL.actionPayload, (b) => api.addQlAction(b), null, (x) => { reset("action"); ql.notice = `${x.ref} added.`; }),
    completeAction: (id) => act("complete", `complete-${id}`, QL.completePayload, (b) => api.completeQlAction(id, b), "Action recorded as completed. A different person must check it worked.", () => { reset("complete"); }),
    verifyAction: (id) => act("verify", `verify-${id}`, QL.verifyPayload, (b) => api.verifyQlAction(id, b), "Effectiveness check recorded.", () => { reset("verify"); }),
    cancelAction: (id) => { const p = needNote(`cancel-${id}`, "A reason", QL.minNote.cancel); if (p) return fail(p); return run(async () => { await api.cancelQlAction(id, note(`cancel-${id}`)); ql.notes = {}; await refresh(); }, "Action cancelled. The reason is kept."); },
  };
}

// ----------------------------------------------------------------------
// Company secretarial (Stage 24): records only; checks no law and contacts no registry
// ----------------------------------------------------------------------
function newCs() {
  const f = () => JSON.parse(JSON.stringify(CS.EMPTY));
  return { tab: "overview", options: null, ov: null, meetings: [], resolutions: [], filings: [], vault: [], forms: { ...f(), policy: null }, notes: {}, formError: null, busy: false, error: null, notice: null };
}

function renderSecretarialPage(authState) {
  if (!uiState.cs) uiState.cs = newCs();
  once("csLoading", () => loadSecretarial());
  return Secretarial({ cs: uiState.cs, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.csLoading, onRetry: () => { loadedOnce.delete("csLoading"); render(); }, actions: secretarialActions() });
}

async function secretarialRefresh(cs) {
  [cs.options, cs.ov, cs.meetings, cs.resolutions, cs.filings] = await Promise.all([api.csOptions(), api.csOverview(), api.csMeetings(), api.csResolutions(), api.csFilings()]);
  cs.forms.policy = CS.policyForm(cs.ov.policy);
}

async function loadSecretarial() {
  const cs = uiState.cs || (uiState.cs = newCs());
  cs.error = null;
  try {
    await secretarialRefresh(cs);
    cs.vault = await api.listEvidence().catch(() => []);
  } catch (err) { cs.error = err.message || "Company secretarial could not be loaded."; }
  render();
}

function secretarialActions() {
  const cs = uiState.cs;
  const run = async (fn, ok) => { cs.error = null; cs.notice = null; cs.formError = null; cs.busy = true; render(); try { await fn(); if (ok) cs.notice = ok; } catch (err) { cs.error = err.message || "That did not work."; } cs.busy = false; render(); };
  const problem = (form, text) => { cs.formError = { form, text }; cs.notice = null; cs.error = null; render(); };
  const fail = (text) => { cs.formError = null; cs.notice = null; cs.error = text; render(); };
  const refresh = () => secretarialRefresh(cs);
  const reset = (name) => { cs.forms[name] = JSON.parse(JSON.stringify(CS.EMPTY[name])); };
  const note = (k) => (cs.notes[k] || "").trim();
  const needNote = (k, what, min) => CS.noteProblem(note(k), what, min);
  const act = (form, errForm, build, call, ok, after) => { const r = build(cs.forms[form]); if (r.problem) return problem(errForm, r.problem); return run(async () => { const x = await call(r.body); if (after) after(x); await refresh(); }, ok); };
  return {
    setTab: (t) => run(async () => { cs.tab = t; cs.formError = null; await refresh(); }),
    setForm: (name, k, v, rerender) => { cs.forms[name] = { ...(cs.forms[name] || {}), [k]: v }; cs.formError = null; if (rerender) render(); },
    setNote: (k, v) => { cs.notes[k] = v; },
    savePolicy: () => { const r = CS.policyPayload(cs.forms.policy); if (r.problem) return problem("policy", r.problem); return run(async () => { await api.setCsPolicy(r.body); await refresh(); }, "Settings saved. They apply from now on."); },
    scheduleMeeting: () => act("meeting", "meeting", CS.meetingPayload, (b) => api.scheduleCsMeeting(b), null, (m) => { reset("meeting"); cs.notice = `${m.ref} scheduled.`; }),
    recordMinutes: (id) => act("minutes", `minutes-${id}`, CS.minutesPayload, (b) => api.recordCsMinutes(id, b), "Minutes recorded. A different person must approve them.", () => { reset("minutes"); }),
    approveMinutes: (id) => { const n = note(`approve-${id}`); if (n) { const p = needNote(`approve-${id}`, "An approval note", 10); if (p) return fail(p); } return run(async () => { await api.approveCsMinutes(id, n); cs.notes = {}; await refresh(); }, "Minutes approved."); },
    cancelMeeting: (id) => { const p = needNote(`cancel-${id}`, "A reason", CS.minNote.cancel); if (p) return fail(p); return run(async () => { await api.cancelCsMeeting(id, note(`cancel-${id}`)); cs.notes = {}; await refresh(); }, "Meeting cancelled. The reason is kept."); },
    proposeResolution: () => act("resolution", "resolution", CS.resolutionPayload, (b) => api.proposeCsResolution(b), null, (r) => { reset("resolution"); cs.notice = `${r.ref} proposed. A different person must decide it.`; }),
    decideResolution: (id) => act("decide", `decide-${id}`, CS.decidePayload, (b) => api.decideCsResolution(id, b), "Decision recorded.", () => { reset("decide"); }),
    withdrawResolution: (id) => { const p = needNote(`withdraw-${id}`, "A reason", CS.minNote.withdraw); if (p) return fail(p); return run(async () => { await api.withdrawCsResolution(id, note(`withdraw-${id}`)); cs.notes = {}; await refresh(); }, "Resolution withdrawn. The reason is kept."); },
    addFiling: () => act("filing", "filing", CS.filingPayload, (b) => api.addCsFiling(b), null, (f) => { reset("filing"); cs.notice = `${f.ref} added.`; }),
    fileFiling: (id) => act("filed", `filed-${id}`, CS.filedPayload, (b) => api.fileCsFiling(id, b), "Recorded as filed. A different person must confirm it.", () => { reset("filed"); }),
    confirmFiling: (id) => act("confirm", `confirm-${id}`, CS.confirmPayload, (b) => api.confirmCsFiling(id, b.note), "Filing confirmed.", () => { reset("confirm"); }),
    withdrawFiling: (id) => { const p = needNote(`fwithdraw-${id}`, "A reason", CS.minNote.withdraw); if (p) return fail(p); return run(async () => { await api.withdrawCsFiling(id, note(`fwithdraw-${id}`)); cs.notes = {}; await refresh(); }, "Filing withdrawn. The reason is kept."); },
  };
}

// ----------------------------------------------------------------------
// Fixed assets (Stage 25): records and arithmetic on typed figures; posts nothing to a ledger
// ----------------------------------------------------------------------
function newFa() {
  const f = () => JSON.parse(JSON.stringify(FA.EMPTY));
  return { tab: "overview", options: null, ov: null, assets: [], sel: { asset: null }, schedule: null, vault: [], forms: { ...f(), policy: null }, notes: {}, formError: null, busy: false, error: null, notice: null };
}

function renderFixedAssetsPage(authState) {
  if (!uiState.fa) uiState.fa = newFa();
  once("faLoading", () => loadFixedAssets());
  return FixedAssets({ fa: uiState.fa, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.faLoading, onRetry: () => { loadedOnce.delete("faLoading"); render(); }, actions: fixedAssetsActions() });
}

async function fixedAssetsRefresh(fa) {
  [fa.options, fa.ov, fa.assets] = await Promise.all([api.faOptions(), api.faOverview(), api.faAssets()]);
  fa.forms.policy = FA.policyForm(fa.ov.policy);
  if (fa.sel.asset) {
    fa.sel.asset = await api.faAsset(fa.sel.asset.id).catch(() => null);
    fa.schedule = fa.sel.asset ? await api.faSchedule(fa.sel.asset.id, 12).catch(() => null) : null;
  }
}

async function loadFixedAssets() {
  const fa = uiState.fa || (uiState.fa = newFa());
  fa.error = null;
  try {
    await fixedAssetsRefresh(fa);
    fa.vault = await api.listEvidence().catch(() => []);
  } catch (err) { fa.error = err.message || "Fixed assets could not be loaded."; }
  render();
}

function fixedAssetsActions() {
  const fa = uiState.fa;
  const run = async (fn, ok) => { fa.error = null; fa.notice = null; fa.formError = null; fa.busy = true; render(); try { await fn(); if (ok) fa.notice = ok; } catch (err) { fa.error = err.message || "That did not work."; } fa.busy = false; render(); };
  const problem = (form, text) => { fa.formError = { form, text }; fa.notice = null; fa.error = null; render(); };
  const fail = (text) => { fa.formError = null; fa.notice = null; fa.error = text; render(); };
  const refresh = () => fixedAssetsRefresh(fa);
  const reset = (name) => { fa.forms[name] = JSON.parse(JSON.stringify(FA.EMPTY[name])); };
  const note = (k) => (fa.notes[k] || "").trim();
  const needNote = (k, what, min) => FA.noteProblem(note(k), what, min);
  const optNote = (k, what) => { const n = note(k); return n ? FA.noteProblem(n, what, 10) : ""; };
  const act = (form, errForm, build, call, ok, after) => { const r = build(fa.forms[form]); if (r.problem) return problem(errForm, r.problem); return run(async () => { const x = await call(r.body); if (after) after(x); await refresh(); }, ok); };
  return {
    setTab: (t) => run(async () => { fa.tab = t; fa.formError = null; await refresh(); }),
    setForm: (name, k, v, rerender) => { fa.forms[name] = { ...(fa.forms[name] || {}), [k]: v }; fa.formError = null; if (rerender) render(); },
    setNote: (k, v) => { fa.notes[k] = v; },
    savePolicy: () => { const r = FA.policyPayload(fa.forms.policy); if (r.problem) return problem("policy", r.problem); return run(async () => { await api.setFaPolicy(r.body); await refresh(); }, "Settings saved. They apply from now on."); },
    selectAsset: (id) => run(async () => { fa.sel.asset = id ? await api.faAsset(id) : null; fa.schedule = id ? await api.faSchedule(id, 12).catch(() => null) : null; fa.notes = {}; reset("disposal"); reset("count"); }),
    proposeAsset: () => act("asset", "asset", FA.assetPayload, (b) => api.proposeFaAsset(b), null, (x) => { reset("asset"); fa.notice = `${x.ref} proposed. A different person must approve it.`; }),
    approveAsset: (id) => { const p = optNote(`asset-${id}`, "An approval note"); if (p) return fail(p); return run(async () => { await api.approveFaAsset(id, note(`asset-${id}`)); fa.notes = {}; await refresh(); }, "Asset approved."); },
    rejectAsset: (id) => { const p = needNote(`asset-${id}`, "A reason", FA.minNote.reject); if (p) return fail(p); return run(async () => { await api.rejectFaAsset(id, note(`asset-${id}`)); fa.notes = {}; await refresh(); }, "Asset rejected. The reason is kept."); },
    proposeDisposal: (id) => act("disposal", "disposal", FA.disposalPayload, (b) => api.proposeFaDisposal(id, b), "Disposal proposed. A different person must decide it.", () => { reset("disposal"); }),
    approveDisposal: (id) => { const p = optNote(`disposal-${id}`, "An approval note"); if (p) return fail(p); return run(async () => { await api.approveFaDisposal(id, note(`disposal-${id}`)); fa.notes = {}; await refresh(); }, "Disposal approved."); },
    rejectDisposal: (id) => { const p = needNote(`disposal-${id}`, "A reason", FA.minNote.rejectDisposal); if (p) return fail(p); return run(async () => { await api.rejectFaDisposal(id, note(`disposal-${id}`)); fa.notes = {}; await refresh(); }, "Disposal rejected. The asset stays active."); },
    recordCount: (id) => act("count", "count", FA.countPayload, (b) => api.recordFaCount(id, b), "Count recorded. A different person must review it.", () => { reset("count"); }),
    reviewCount: (id, no) => { const p = needNote(`count-${id}-${no}`, "A review note", 10); if (p) return fail(p); return run(async () => { await api.reviewFaCount(id, no, note(`count-${id}-${no}`)); fa.notes = {}; await refresh(); }, "Count reviewed."); },
  };
}

// ----------------------------------------------------------------------
// Inventory (Stage 26): a stock register from typed receipts and issues; posts nothing to a ledger
// ----------------------------------------------------------------------
function newIv() {
  const f = () => JSON.parse(JSON.stringify(IV.EMPTY));
  return { tab: "overview", options: null, ov: null, items: [], sel: { item: null }, forms: { ...f(), policy: null }, notes: {}, formError: null, busy: false, error: null, notice: null };
}

function renderInventoryPage(authState) {
  if (!uiState.iv) uiState.iv = newIv();
  once("ivLoading", () => loadInventory());
  return Inventory({ iv: uiState.iv, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.ivLoading, onRetry: () => { loadedOnce.delete("ivLoading"); render(); }, actions: inventoryActions() });
}

async function inventoryRefresh(iv) {
  [iv.options, iv.ov, iv.items] = await Promise.all([api.ivOptions(), api.ivOverview(), api.ivItems()]);
  iv.forms.policy = IV.policyForm(iv.ov.policy);
  if (iv.sel.item) iv.sel.item = await api.ivItem(iv.sel.item.id).catch(() => null);
}
async function loadInventory() {
  const iv = uiState.iv || (uiState.iv = newIv());
  iv.error = null;
  try { await inventoryRefresh(iv); } catch (err) { iv.error = err.message || "Inventory could not be loaded."; }
  render();
}

function inventoryActions() {
  const iv = uiState.iv;
  const run = async (fn, ok) => { iv.error = null; iv.notice = null; iv.formError = null; iv.busy = true; render(); try { await fn(); if (ok) iv.notice = ok; } catch (err) { iv.error = err.message || "That did not work."; } iv.busy = false; render(); };
  const problem = (form, text) => { iv.formError = { form, text }; iv.notice = null; iv.error = null; render(); };
  const fail = (text) => { iv.formError = null; iv.notice = null; iv.error = text; render(); };
  const refresh = () => inventoryRefresh(iv);
  const reset = (name) => { iv.forms[name] = JSON.parse(JSON.stringify(IV.EMPTY[name])); };
  const note = (k) => (iv.notes[k] || "").trim();
  const needNote = (k, what, min) => IV.noteProblem(note(k), what, min);
  const optNote = (k, what) => { const n = note(k); return n ? IV.noteProblem(n, what, 10) : ""; };
  const act = (form, errForm, build, call, ok, after) => { const r = build(iv.forms[form]); if (r.problem) return problem(errForm, r.problem); return run(async () => { const x = await call(r.body); if (after) after(x); await refresh(); }, ok); };
  return {
    setTab: (t) => run(async () => { iv.tab = t; iv.formError = null; await refresh(); }),
    setForm: (name, k, v, rerender) => { iv.forms[name] = { ...(iv.forms[name] || {}), [k]: v }; iv.formError = null; if (rerender) render(); },
    setNote: (k, v) => { iv.notes[k] = v; },
    savePolicy: () => { const r = IV.policyPayload(iv.forms.policy); if (r.problem) return problem("policy", r.problem); return run(async () => { await api.setIvPolicy(r.body); await refresh(); }, "Settings saved. They apply from now on."); },
    selectItem: (id) => run(async () => { iv.sel.item = id ? await api.ivItem(id) : null; iv.notes = {}; reset("receive"); reset("issue"); reset("adjust"); }),
    addItem: () => act("item", "item", IV.itemPayload, (b) => api.addIvItem(b), null, (x) => { reset("item"); iv.notice = `${x.ref} added.`; }),
    receive: (id) => act("receive", "receive", IV.receivePayload, (b) => api.receiveIv(id, b), "Receipt recorded.", () => { reset("receive"); }),
    issue: (id) => act("issue", "issue", IV.issuePayload, (b) => api.issueIv(id, b), "Issue recorded.", () => { reset("issue"); }),
    proposeAdjustment: (id, onHand) => act("adjust", "adjust", (f) => IV.adjustPayload(f, onHand), (b) => api.proposeIvAdjustment(id, b), "Adjustment proposed. A different person must decide it.", () => { reset("adjust"); }),
    approveAdjustment: (id, no) => { const p = optNote(`adj-${id}-${no}`, "An approval note"); if (p) return fail(p); return run(async () => { await api.approveIvAdjustment(id, no, note(`adj-${id}-${no}`)); iv.notes = {}; await refresh(); }, "Adjustment approved and applied."); },
    rejectAdjustment: (id, no) => { const p = needNote(`adj-${id}-${no}`, "A reason", IV.minNote.reject); if (p) return fail(p); return run(async () => { await api.rejectIvAdjustment(id, no, note(`adj-${id}-${no}`)); iv.notes = {}; await refresh(); }, "Adjustment rejected. The reason is kept."); },
    discontinue: (id) => { const p = needNote(`disc-${id}`, "A reason", IV.minNote.discontinue); if (p) return fail(p); return run(async () => { await api.discontinueIvItem(id, note(`disc-${id}`)); iv.notes = {}; await refresh(); }, "Item discontinued. The reason is kept."); },
  };
}

// ----------------------------------------------------------------------
// Investments (Stage 27): holdings from typed purchases, sales and prices; reads no market data; posts nothing to a ledger
// ----------------------------------------------------------------------
function newIm() {
  const f = () => JSON.parse(JSON.stringify(IM.EMPTY));
  return { tab: "overview", options: null, ov: null, holdings: [], sel: { holding: null }, forms: { ...f(), policy: null }, notes: {}, formError: null, busy: false, error: null, notice: null };
}

function renderInvestmentsPage(authState) {
  if (!uiState.im) uiState.im = newIm();
  once("imLoading", () => loadInvestments());
  return Investments({ im: uiState.im, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.imLoading, onRetry: () => { loadedOnce.delete("imLoading"); render(); }, actions: investmentsActions() });
}

async function investmentsRefresh(im) {
  [im.options, im.ov, im.holdings] = await Promise.all([api.imOptions(), api.imOverview(), api.imHoldings()]);
  im.forms.policy = IM.policyForm(im.ov.policy);
  if (im.sel.holding) im.sel.holding = await api.imHolding(im.sel.holding.id).catch(() => null);
}
async function loadInvestments() {
  const im = uiState.im || (uiState.im = newIm());
  im.error = null;
  try { await investmentsRefresh(im); } catch (err) { im.error = err.message || "Investments could not be loaded."; }
  render();
}

function investmentsActions() {
  const im = uiState.im;
  const run = async (fn, ok) => { im.error = null; im.notice = null; im.formError = null; im.busy = true; render(); try { await fn(); if (ok) im.notice = ok; } catch (err) { im.error = err.message || "That did not work."; } im.busy = false; render(); };
  const problem = (form, text) => { im.formError = { form, text }; im.notice = null; im.error = null; render(); };
  const fail = (text) => { im.formError = null; im.notice = null; im.error = text; render(); };
  const refresh = () => investmentsRefresh(im);
  const reset = (name) => { im.forms[name] = JSON.parse(JSON.stringify(IM.EMPTY[name])); };
  const note = (k) => (im.notes[k] || "").trim();
  const needNote = (k, what, min) => IM.noteProblem(note(k), what, min);
  const optNote = (k, what) => { const n = note(k); return n ? IM.noteProblem(n, what, 10) : ""; };
  const act = (form, errForm, build, call, ok, after) => { const r = build(im.forms[form]); if (r.problem) return problem(errForm, r.problem); return run(async () => { const x = await call(r.body); if (after) after(x); await refresh(); }, ok); };
  return {
    setTab: (t) => run(async () => { im.tab = t; im.formError = null; await refresh(); }),
    setForm: (name, k, v, rerender) => { im.forms[name] = { ...(im.forms[name] || {}), [k]: v }; im.formError = null; if (rerender) render(); },
    setNote: (k, v) => { im.notes[k] = v; },
    savePolicy: () => { const r = IM.policyPayload(im.forms.policy); if (r.problem) return problem("policy", r.problem); return run(async () => { await api.setImPolicy(r.body); await refresh(); }, "Settings saved. They apply from now on."); },
    selectHolding: (id) => run(async () => { im.sel.holding = id ? await api.imHolding(id) : null; im.notes = {}; reset("buy"); reset("sell"); reset("mark"); }),
    addHolding: () => act("holding", "holding", IM.holdingPayload, (b) => api.addImHolding(b), null, (x) => { reset("holding"); im.notice = `${x.ref} added.`; }),
    buy: (id) => act("buy", "buy", IM.buyPayload, (b) => api.buyIm(id, b), "Purchase recorded.", () => { reset("buy"); }),
    proposeSell: (id, held) => act("sell", "sell", (f) => IM.sellPayload(f, held), (b) => api.proposeImSell(id, b), "Sale proposed. A different person must decide it.", () => { reset("sell"); }),
    recordMark: (id) => act("mark", "mark", IM.markPayload, (b) => api.recordImMark(id, b), "Price recorded.", () => { reset("mark"); }),
    approveSell: (id, no) => { const p = optNote(`sell-${id}-${no}`, "An approval note"); if (p) return fail(p); return run(async () => { await api.approveImSell(id, no, note(`sell-${id}-${no}`)); im.notes = {}; await refresh(); }, "Sale approved and applied."); },
    rejectSell: (id, no) => { const p = needNote(`sell-${id}-${no}`, "A reason", IM.minNote.reject); if (p) return fail(p); return run(async () => { await api.rejectImSell(id, no, note(`sell-${id}-${no}`)); im.notes = {}; await refresh(); }, "Sale rejected. The reason is kept."); },
    close: (id) => { const p = needNote(`close-${id}`, "A reason", IM.minNote.close); if (p) return fail(p); return run(async () => { await api.closeImHolding(id, note(`close-${id}`)); im.notes = {}; await refresh(); }, "Holding closed. The reason is kept."); },
  };
}

// ----------------------------------------------------------------------
// Valuation (Stage 28): workpapers worked out from typed inputs; reads no market data; gives no opinion of value
// ----------------------------------------------------------------------
function newVl() {
  const f = () => JSON.parse(JSON.stringify(VL.EMPTY));
  return { tab: "overview", options: null, ov: null, cases: [], sel: { case: null }, sens: null, forms: { ...f(), policy: null }, notes: {}, formError: null, busy: false, error: null, notice: null };
}

function renderValuationPage(authState) {
  if (!uiState.vl) uiState.vl = newVl();
  once("vlLoading", () => loadValuation());
  return Valuation({ vl: uiState.vl, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.vlLoading, onRetry: () => { loadedOnce.delete("vlLoading"); render(); }, actions: valuationActions() });
}

async function valuationRefresh(vl) {
  [vl.options, vl.ov, vl.cases] = await Promise.all([api.vlOptions(), api.vlOverview(), api.vlCases()]);
  vl.forms.policy = VL.policyForm(vl.ov.policy);
  if (vl.sel.case) vl.sel.case = await api.vlCase(vl.sel.case.id).catch(() => null);
  if (!vl.sel.case) vl.sens = null;
}
async function loadValuation() {
  const vl = uiState.vl || (uiState.vl = newVl());
  vl.error = null;
  try { await valuationRefresh(vl); } catch (err) { vl.error = err.message || "Valuation could not be loaded."; }
  render();
}

function valuationActions() {
  const vl = uiState.vl;
  const run = async (fn, ok) => { vl.error = null; vl.notice = null; vl.formError = null; vl.busy = true; render(); try { await fn(); if (ok) vl.notice = ok; } catch (err) { vl.error = err.message || "That did not work."; } vl.busy = false; render(); };
  const problem = (form, text) => { vl.formError = { form, text }; vl.notice = null; vl.error = null; render(); };
  const fail = (text) => { vl.formError = null; vl.notice = null; vl.error = text; render(); };
  const refresh = () => valuationRefresh(vl);
  const reset = (name) => { vl.forms[name] = JSON.parse(JSON.stringify(VL.EMPTY[name])); };
  const note = (k) => (vl.notes[k] || "").trim();
  const needNote = (k, what, min) => VL.noteProblem(note(k), what, min);
  const optNote = (k, what) => { const n = note(k); return n ? VL.noteProblem(n, what, 10) : ""; };
  const act = (form, errForm, build, call, ok, after) => { const r = build(vl.forms[form]); if (r.problem) return problem(errForm, r.problem); return run(async () => { const x = await call(r.body); if (after) after(x); await refresh(); }, ok); };
  return {
    setTab: (t) => run(async () => { vl.tab = t; vl.formError = null; await refresh(); }),
    setForm: (name, k, v, rerender) => { vl.forms[name] = { ...(vl.forms[name] || {}), [k]: v }; vl.formError = null; if (rerender) render(); },
    setNote: (k, v) => { vl.notes[k] = v; },
    savePolicy: () => { const r = VL.policyPayload(vl.forms.policy); if (r.problem) return problem("policy", r.problem); return run(async () => { await api.setVlPolicy(r.body); await refresh(); }, "Settings saved. They apply from now on."); },
    selectCase: (id) => run(async () => { vl.sel.case = id ? await api.vlCase(id) : null; vl.sens = null; vl.notes = {}; reset("method"); reset("submit"); }),
    createCase: () => act("case", "case", VL.casePayload, (b) => api.createVlCase(b), null, (x) => { reset("case"); vl.notice = `${x.ref} started.`; }),
    addMethod: (id) => act("method", "method", VL.methodPayload, (b) => api.addVlMethod(id, b), "Method added.", () => { const k = vl.forms.method.kind; reset("method"); vl.forms.method.kind = k; }),
    removeMethod: (id, no) => { const p = needNote(`rm-${id}-${no}`, "A reason", VL.minNote.remove); if (p) return fail(p); return run(async () => { await api.removeVlMethod(id, no, note(`rm-${id}-${no}`)); vl.notes = {}; vl.sens = null; await refresh(); }, "Method removed. The reason is kept."); },
    showSensitivity: (id, no) => run(async () => { const s = await api.vlSensitivity(id, no); vl.sens = { caseId: id, method: no, rows: s.rows }; }),
    submit: (id) => act("submit", "submit", VL.submitPayload, (b) => api.submitVl(id, b.rationale), "Submitted. A different person must review it.", () => { reset("submit"); }),
    withdraw: (id) => { const p = needNote(`wd-${id}`, "A reason", VL.minNote.withdraw); if (p) return fail(p); return run(async () => { await api.withdrawVl(id, note(`wd-${id}`)); vl.notes = {}; await refresh(); }, "Valuation withdrawn. The reason is kept."); },
    approve: (id) => { const p = optNote(`dec-${id}`, "An approval note"); if (p) return fail(p); return run(async () => { await api.approveVl(id, note(`dec-${id}`)); vl.notes = {}; await refresh(); }, "Valuation approved."); },
    returnCase: (id) => { const p = needNote(`dec-${id}`, "A reason", VL.minNote.return); if (p) return fail(p); return run(async () => { await api.returnVl(id, note(`dec-${id}`)); vl.notes = {}; await refresh(); }, "Valuation returned. The reason is kept."); },
  };
}

// ----------------------------------------------------------------------
// Insurance and claims (Stage 29): a register of what people type in; contacts no insurer; gives no advice
// ----------------------------------------------------------------------
function newIc() {
  return { tab: "overview", ov: null, policies: [], claims: [], sel: { policy: null, claim: null }, forms: { ...JSON.parse(JSON.stringify(IC.EMPTY)), setting: null }, notes: {}, formError: null, busy: false, error: null, notice: null };
}

function renderInsurancePage(authState) {
  if (!uiState.ic) uiState.ic = newIc();
  once("icLoading", () => loadInsurance());
  return Insurance({ ic: uiState.ic, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.icLoading, onRetry: () => { loadedOnce.delete("icLoading"); render(); }, actions: insuranceActions() });
}

async function insuranceRefresh(ic) {
  [ic.ov, ic.policies, ic.claims] = await Promise.all([api.icOverview(), api.icPolicies(), api.icClaims()]);
  ic.forms.setting = { warning_days: String(ic.ov.policy.warning_days) };
  if (ic.sel.policy) ic.sel.policy = await api.icPolicy(ic.sel.policy.id).catch(() => null);
  if (ic.sel.claim) ic.sel.claim = await api.icClaim(ic.sel.claim.id).catch(() => null);
}
async function loadInsurance() {
  const ic = uiState.ic || (uiState.ic = newIc());
  ic.error = null;
  try { await insuranceRefresh(ic); } catch (err) { ic.error = err.message || "Insurance and claims could not be loaded."; }
  render();
}

function insuranceActions() {
  const ic = uiState.ic;
  const run = async (fn, ok) => { ic.error = null; ic.notice = null; ic.formError = null; ic.busy = true; render(); try { await fn(); if (ok) ic.notice = ok; } catch (err) { ic.error = err.message || "That did not work."; } ic.busy = false; render(); };
  const problem = (form, text) => { ic.formError = { form, text }; ic.notice = null; ic.error = null; render(); };
  const fail = (text) => { ic.formError = null; ic.notice = null; ic.error = text; render(); };
  const refresh = () => insuranceRefresh(ic);
  const reset = (name) => { ic.forms[name] = JSON.parse(JSON.stringify(IC.EMPTY[name])); };
  const note = (k) => (ic.notes[k] || "").trim();
  const act = (form, errForm, build, call, ok, after) => { const r = build(ic.forms[form]); if (r.problem) return problem(errForm, r.problem); return run(async () => { const x = await call(r.body); if (after) after(x); await refresh(); }, ok); };
  return {
    setTab: (t) => run(async () => { ic.tab = t; ic.formError = null; await refresh(); }),
    setForm: (name, k, v, rerender) => { ic.forms[name] = { ...(ic.forms[name] || {}), [k]: v }; ic.formError = null; if (rerender) render(); },
    setNote: (k, v) => { ic.notes[k] = v; },
    saveSetting: () => { const r = IC.settingPayload(ic.forms.setting.warning_days); if (r.problem) return problem("setting", r.problem); return run(async () => { await api.setIcSetting(r.body); await refresh(); }, "Settings saved. They apply from now on."); },
    selectPolicy: (id) => run(async () => { ic.sel.policy = id ? await api.icPolicy(id) : null; ic.notes = {}; reset("claim"); }),
    selectClaim: (id) => run(async () => { ic.sel.claim = id ? await api.icClaim(id) : null; ic.notes = {}; reset("outcome"); reset("receipt"); }),
    addPolicy: () => act("policy", "policy", IC.policyPayload, (b) => api.addIcPolicy(b), null, (x) => { reset("policy"); ic.notice = `${x.ref} recorded.`; }),
    cancelPolicy: (id) => { const n = note(`cancel-${id}`); const p = IC.noteProblem(n, "A reason", IC.minNote.cancel); if (p) return fail(p); return run(async () => { await api.cancelIcPolicy(id, n); ic.notes = {}; await refresh(); }, "Policy cancelled. The reason is kept."); },
    addClaim: (id) => act("claim", "claim", (f) => IC.claimPayload(f, ic.sel.policy && ic.sel.policy.sum_insured), (b) => api.addIcClaim(id, b), null, (x) => { reset("claim"); ic.notice = `${x.ref} recorded.`; }),
    proposeOutcome: (id, claimed) => act("outcome", "outcome", (f) => IC.outcomePayload(f, claimed), (b) => api.proposeIcOutcome(id, b), "Outcome proposed. A different person must decide it.", () => { reset("outcome"); }),
    approveOutcome: (id, no) => { const n = note(`pr-${id}-${no}`); if (n) { const p = IC.noteProblem(n, "An approval note", 10); if (p) return fail(p); } return run(async () => { await api.approveIcOutcome(id, no, n); ic.notes = {}; await refresh(); }, "Outcome approved."); },
    rejectOutcome: (id, no) => { const n = note(`pr-${id}-${no}`); const p = IC.noteProblem(n, "A reason", IC.minNote.reject); if (p) return fail(p); return run(async () => { await api.rejectIcOutcome(id, no, n); ic.notes = {}; await refresh(); }, "Outcome rejected. The reason is kept."); },
    recordReceipt: (id, outstanding) => act("receipt", "receipt", (f) => IC.receiptPayload(f, outstanding), (b) => api.recordIcReceipt(id, b), "Money received recorded.", () => { reset("receipt"); }),
  };
}

// ----------------------------------------------------------------------
// ESG and carbon (Stage 30): emission records from typed data and factors; supplies no factors; measures nothing
// ----------------------------------------------------------------------
function newEs() {
  return { tab: "overview", ov: null, entries: [], targets: [], forms: { ...JSON.parse(JSON.stringify(ES.EMPTY)), setting: null }, notes: {}, formError: null, busy: false, error: null, notice: null };
}

function renderEsgPage(authState) {
  if (!uiState.es) uiState.es = newEs();
  once("esLoading", () => loadEsg());
  return Esg({ es: uiState.es, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.esLoading, onRetry: () => { loadedOnce.delete("esLoading"); render(); }, actions: esgActions() });
}

async function esgRefresh(es) {
  [es.ov, es.entries, es.targets] = await Promise.all([api.esOverview(), api.esEntries(), api.esTargets()]);
  es.forms.setting = { factor_max_age_years: String(es.ov.setting.factor_max_age_years) };
}
async function loadEsg() {
  const es = uiState.es || (uiState.es = newEs());
  es.error = null;
  try { await esgRefresh(es); } catch (err) { es.error = err.message || "ESG and carbon could not be loaded."; }
  render();
}

function esgActions() {
  const es = uiState.es;
  const run = async (fn, ok) => { es.error = null; es.notice = null; es.formError = null; es.busy = true; render(); try { await fn(); if (ok) es.notice = ok; } catch (err) { es.error = err.message || "That did not work."; } es.busy = false; render(); };
  const problem = (form, text) => { es.formError = { form, text }; es.notice = null; es.error = null; render(); };
  const fail = (text) => { es.formError = null; es.notice = null; es.error = text; render(); };
  const refresh = () => esgRefresh(es);
  const reset = (name) => { es.forms[name] = JSON.parse(JSON.stringify(ES.EMPTY[name])); };
  const note = (k) => (es.notes[k] || "").trim();
  const act = (form, errForm, build, call, ok, after) => { const r = build(es.forms[form]); if (r.problem) return problem(errForm, r.problem); return run(async () => { const x = await call(r.body); if (after) after(x); await refresh(); }, ok); };
  const approve = (call, key) => { const n = note(key); if (n) { const p = ES.noteProblem(n, "An approval note", 10); if (p) return fail(p); } return run(async () => { await call(n); es.notes = {}; await refresh(); }, "Approved."); };
  const reject = (call, key) => { const n = note(key); const p = ES.noteProblem(n, "A reason", ES.minNote.reject); if (p) return fail(p); return run(async () => { await call(n); es.notes = {}; await refresh(); }, "Rejected. The reason is kept."); };
  return {
    setTab: (t) => run(async () => { es.tab = t; es.formError = null; await refresh(); }),
    setForm: (name, k, v, rerender) => { es.forms[name] = { ...(es.forms[name] || {}), [k]: v }; es.formError = null; if (rerender) render(); },
    setNote: (k, v) => { es.notes[k] = v; },
    saveSetting: () => { const r = ES.settingPayload(es.forms.setting.factor_max_age_years); if (r.problem) return problem("setting", r.problem); return run(async () => { await api.setEsSetting(r.body); await refresh(); }, "Settings saved. They apply from now on."); },
    addEntry: () => act("entry", "entry", ES.entryPayload, (b) => api.addEsEntry(b), null, (x) => { const k = [es.forms.entry.scope, es.forms.entry.category]; reset("entry"); es.forms.entry.scope = k[0]; es.forms.entry.category = k[1]; es.notice = `${x.ref} proposed. A different person must verify it.`; }),
    verifyEntry: (id) => approve((n) => api.verifyEsEntry(id, n), `en-${id}`),
    rejectEntry: (id) => reject((n) => api.rejectEsEntry(id, n), `en-${id}`),
    addTarget: () => act("target", "target", ES.targetPayload, (b) => api.addEsTarget(b), null, (x) => { reset("target"); es.notice = `${x.ref} proposed. A different person must decide it.`; }),
    approveTarget: (id) => approve((n) => api.approveEsTarget(id, n), `tg-${id}`),
    rejectTarget: (id) => reject((n) => api.rejectEsTarget(id, n), `tg-${id}`),
  };
}

// ----------------------------------------------------------------------
// Payroll and workforce cost (Stage 31): typed pay lines added up exactly; calculates no tax; pays nobody
// ----------------------------------------------------------------------
function newPw() {
  return { tab: "overview", ov: null, runs: [], sel: { run: null }, forms: { ...JSON.parse(JSON.stringify(PW.EMPTY)), setting: null }, notes: {}, formError: null, busy: false, error: null, notice: null };
}

function renderPayrollPage(authState) {
  if (!uiState.pw) uiState.pw = newPw();
  once("pwLoading", () => loadPayroll());
  return Payroll({ pw: uiState.pw, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.pwLoading, onRetry: () => { loadedOnce.delete("pwLoading"); render(); }, actions: payrollActions() });
}

async function payrollRefresh(pw) {
  [pw.ov, pw.runs] = await Promise.all([api.pwOverview(), api.pwRuns()]);
  pw.forms.setting = { review_limit: String(pw.ov.setting.review_limit) };
  if (pw.sel.run) pw.sel.run = await api.pwRun(pw.sel.run.id).catch(() => null);
}
async function loadPayroll() {
  const pw = uiState.pw || (uiState.pw = newPw());
  pw.error = null;
  try { await payrollRefresh(pw); } catch (err) { pw.error = err.message || "Payroll could not be loaded."; }
  render();
}

function payrollActions() {
  const pw = uiState.pw;
  const run = async (fn, ok) => { pw.error = null; pw.notice = null; pw.formError = null; pw.busy = true; render(); try { await fn(); if (ok) pw.notice = ok; } catch (err) { pw.error = err.message || "That did not work."; } pw.busy = false; render(); };
  const problem = (form, text) => { pw.formError = { form, text }; pw.notice = null; pw.error = null; render(); };
  const fail = (text) => { pw.formError = null; pw.notice = null; pw.error = text; render(); };
  const refresh = () => payrollRefresh(pw);
  const reset = (name) => { pw.forms[name] = JSON.parse(JSON.stringify(PW.EMPTY[name])); };
  const note = (k) => (pw.notes[k] || "").trim();
  const act = (form, errForm, build, call, ok, after) => { const r = build(pw.forms[form]); if (r.problem) return problem(errForm, r.problem); return run(async () => { const x = await call(r.body); if (after) after(x); await refresh(); }, ok); };
  return {
    setTab: (t) => run(async () => { pw.tab = t; pw.formError = null; await refresh(); }),
    setForm: (name, k, v, rerender) => { pw.forms[name] = { ...(pw.forms[name] || {}), [k]: v }; pw.formError = null; if (rerender) render(); },
    setNote: (k, v) => { pw.notes[k] = v; },
    saveSetting: () => { const r = PW.settingPayload(pw.forms.setting.review_limit); if (r.problem) return problem("setting", r.problem); return run(async () => { await api.setPwSetting(r.body); await refresh(); }, "Settings saved. They apply from now on."); },
    selectRun: (id) => run(async () => { pw.sel.run = id ? await api.pwRun(id) : null; pw.notes = {}; reset("line"); reset("submit"); }),
    createRun: () => act("run", "run", PW.runPayload, (b) => api.createPwRun(b), null, (x) => { reset("run"); pw.notice = `${x.ref} started.`; }),
    addLine: (id) => act("line", "line", PW.linePayload, (b) => api.addPwLine(id, b), "Line added.", () => { reset("line"); }),
    removeLine: (id, no) => { const p = PW.noteProblem(note(`rm-${id}-${no}`), "A reason", PW.minNote.remove); if (p) return fail(p); return run(async () => { await api.removePwLine(id, no, note(`rm-${id}-${no}`)); pw.notes = {}; await refresh(); }, "Line removed. The reason is kept."); },
    submit: (id) => act("submit", "submit", PW.submitPayload, (b) => api.submitPw(id, b.note), "Submitted. A different person must review it.", () => { reset("submit"); }),
    withdraw: (id) => { const p = PW.noteProblem(note(`wd-${id}`), "A reason", PW.minNote.withdraw); if (p) return fail(p); return run(async () => { await api.withdrawPw(id, note(`wd-${id}`)); pw.notes = {}; await refresh(); }, "Run withdrawn. The reason is kept."); },
    approve: (id) => { const n = note(`dec-${id}`); if (n) { const p = PW.noteProblem(n, "An approval note", 10); if (p) return fail(p); } return run(async () => { await api.approvePw(id, n); pw.notes = {}; await refresh(); }, "Run approved."); },
    returnRun: (id) => { const p = PW.noteProblem(note(`dec-${id}`), "A reason", PW.minNote.return); if (p) return fail(p); return run(async () => { await api.returnPw(id, note(`dec-${id}`)); pw.notes = {}; await refresh(); }, "Run returned. The reason is kept."); },
  };
}

// ----------------------------------------------------------------------
// Cybersecurity and Digital Risk
// ----------------------------------------------------------------------
function newCyber() {
  return { options: null, ov: null, assets: [], vulns: [], incidents: [], reviews: [], reports: [], vault: [], tab: "overview", vulnFilter: "", asset: null, assetForm: null, vuln: null, vulnForm: null, fixForm: null, acceptForm: null,
    incident: null, incidentForm: null, closeForm: null, review: null, reviewForm: null, entryForm: null, report: null, reportForm: null, notes: {}, policyForm: null, busy: false, error: null, notice: null };
}

function renderCyberPage(authState) {
  if (!uiState.cy) uiState.cy = newCyber();
  once("cyLoading", () => loadCyber());
  return Cyber({ cy: uiState.cy, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.cyLoading, onRetry: () => { loadedOnce.delete("cyLoading"); render(); }, actions: cyberActions() });
}

async function cyberRefresh(cy) {
  [cy.options, cy.ov, cy.assets, cy.vulns, cy.incidents, cy.reviews, cy.reports] = await Promise.all([api.cyOptions(), api.cyOverview(), api.cyAssets(), api.cyVulns(), api.cyIncidents(), api.cyReviews(), api.cyReports()]);
  cy.policyForm = CY.policyForm(cy.ov.policy);
  if (cy.asset) cy.asset = await api.cyAsset(cy.asset.id);
  if (cy.vuln) cy.vuln = await api.cyVuln(cy.vuln.id);
  if (cy.incident) cy.incident = await api.cyIncident(cy.incident.id);
  if (cy.review) cy.review = await api.cyReview(cy.review.id);
  if (cy.report) cy.report = await api.cyReport(cy.report.id);
}

async function loadCyber() {
  const cy = uiState.cy || (uiState.cy = newCyber());
  cy.error = null;
  try {
    await cyberRefresh(cy);
    cy.vault = await api.listEvidence().catch(() => []);
  } catch (err) { cy.error = err.message || "Cybersecurity could not be loaded."; }
}

function cyberActions() {
  const cy = uiState.cy;
  const run = async (fn, ok) => { cy.error = null; cy.notice = null; cy.busy = true; render(); try { await fn(); if (ok) cy.notice = ok; } catch (err) { cy.error = err.message || "That did not work."; } cy.busy = false; render(); };
  const fail = (m) => { cy.error = m; render(); };
  const refresh = () => cyberRefresh(cy);
  const note = (k) => cy.notes[k] || "";
  const clearForms = () => { cy.assetForm = cy.vulnForm = cy.fixForm = cy.acceptForm = cy.incidentForm = cy.closeForm = cy.reviewForm = cy.entryForm = cy.reportForm = null; cy.notes = {}; };
  const closeViews = () => { cy.asset = cy.vuln = cy.incident = cy.review = cy.report = null; };
  const set = (key) => (k, v) => { cy[key] = { ...cy[key], [k]: v }; };
  const need = (k, what, min) => CY.noteProblem(note(k), what, min);
  const clearNote = (k) => { cy.notes[k] = ""; };
  return {
    setTab: (t) => run(async () => { cy.tab = t; closeViews(); clearForms(); await refresh(); }),
    noteChange: (k, v) => { cy.notes[k] = v; },
    policyChange: (k, v) => { cy.policyForm = { ...cy.policyForm, [k]: v }; },
    savePolicy: () => { const p = CY.policyProblem(cy.policyForm); if (p) return fail(p); return run(async () => { await api.setCyPolicy(CY.policyBody(cy.policyForm)); await refresh(); }, "Policy saved. It applies to vulnerabilities recorded from now on."); },
    // assets
    newAsset: () => { clearForms(); cy.assetForm = CY.emptyAsset(); render(); },
    assetChange: set("assetForm"),
    cancelAsset: () => { cy.assetForm = null; render(); },
    editAsset: () => { cy.assetForm = CY.assetForm(cy.asset); render(); },
    saveAsset: () => { const p = CY.assetProblem(cy.assetForm); if (p) return fail(p); return run(async () => { const f = cy.assetForm, b = CY.assetBody(f); const r = f.id ? await api.updateCyAsset(f.id, b) : await api.createCyAsset(b); cy.assetForm = null; if (f.id) cy.asset = r; await refresh(); cy.notice = f.id ? "Asset updated." : `Asset ${r.ref} saved.`; }); },
    openAsset: (id) => run(async () => { clearForms(); closeViews(); cy.tab = "assets"; cy.asset = await api.cyAsset(id); }),
    closeAssetView: () => run(async () => { cy.asset = null; clearForms(); await refresh(); }),
    retireAsset: () => { const p = need("retire", "a reason", 3); if (p) return fail(p); return run(async () => { await api.retireCyAsset(cy.asset.id, note("retire")); cy.asset = null; clearForms(); await refresh(); }, "Asset retired."); },
    // vulnerabilities
    filterVulns: (v) => { cy.vulnFilter = v; render(); },
    newVuln: (assetId) => { clearForms(); closeViews(); cy.tab = "vulns"; cy.vulnForm = CY.emptyVuln(assetId || ""); render(); },
    vulnChange: set("vulnForm"),
    cancelVuln: () => { cy.vulnForm = null; render(); },
    saveVuln: () => { const p = CY.vulnProblem(cy.vulnForm); if (p) return fail(p); return run(async () => { const r = await api.createCyVuln(CY.vulnBody(cy.vulnForm)); cy.vulnForm = null; cy.vuln = r; await refresh(); cy.notice = `Vulnerability ${r.ref} saved. Fix deadline: ${r.due}.`; }); },
    openVuln: (id) => run(async () => { clearForms(); closeViews(); cy.tab = "vulns"; cy.vuln = await api.cyVuln(id); }),
    closeVulnView: () => run(async () => { cy.vuln = null; clearForms(); await refresh(); }),
    startVuln: () => run(async () => { await api.cyVulnStep(cy.vuln.id, "start"); await refresh(); }, "Work started."),
    newFix: () => { cy.acceptForm = null; cy.fixForm = { note: "", evidence_ids: [] }; render(); },
    fixChange: (k, v) => { cy.fixForm = { ...cy.fixForm, [k]: v }; },
    fixEvidence: (id) => { const l = cy.fixForm.evidence_ids || []; cy.fixForm = { ...cy.fixForm, evidence_ids: l.includes(id) ? l.filter((x) => x !== id) : [...l, id] }; },
    cancelFix: () => { cy.fixForm = null; render(); },
    saveFix: () => { const p = CY.noteProblem(cy.fixForm.note, "what was done", 3); if (p) return fail(p); return run(async () => { await api.cyVulnStep(cy.vuln.id, "fixed", { note: cy.fixForm.note.trim(), evidence_ids: cy.fixForm.evidence_ids || [] }); cy.fixForm = null; await refresh(); }, "Marked as fixed. A different person must verify it."); },
    newAccept: () => { cy.fixForm = null; cy.acceptForm = { reason: "", until: "" }; render(); },
    acceptChange: (k, v) => { cy.acceptForm = { ...cy.acceptForm, [k]: v }; },
    cancelAccept: () => { cy.acceptForm = null; render(); },
    saveAccept: () => { const p = CY.acceptProblem(cy.acceptForm); if (p) return fail(p); return run(async () => { await api.cyVulnStep(cy.vuln.id, "acceptance", { reason: cy.acceptForm.reason.trim(), until: cy.acceptForm.until.trim() }); cy.acceptForm = null; await refresh(); }, "Asked to accept the risk. A different person must decide."); },
    reopenVuln: () => { const p = need("v", "a reason", 3); if (p) return fail(p); return run(async () => { await api.cyVulnStep(cy.vuln.id, "reopen", { note: note("v") }); clearNote("v"); await refresh(); }, "Reopened."); },
    verifyVuln: (ok) => { if (!ok) { const p = need("v", "a note saying what is still wrong", 3); if (p) return fail(p); } return run(async () => { await api.cyVulnStep(cy.vuln.id, ok ? "verify" : "reject-fix", { note: note("v") }); clearNote("v"); await refresh(); }, ok ? "Fix verified." : "Sent back to open."); },
    decideAccept: (ok) => { if (!ok) { const p = need("v", "a note saying why you are refusing", 3); if (p) return fail(p); } return run(async () => { await api.cyVulnStep(cy.vuln.id, ok ? "acceptance/approve" : "acceptance/reject", { note: note("v") }); clearNote("v"); await refresh(); }, ok ? "Risk accepted until the date given." : "Acceptance refused."); },
    // incidents
    newIncident: () => { clearForms(); closeViews(); cy.tab = "incidents"; cy.incidentForm = CY.emptyIncident(); render(); },
    incidentChange: set("incidentForm"),
    incidentAsset: (id) => { const l = cy.incidentForm.asset_ids || []; cy.incidentForm = { ...cy.incidentForm, asset_ids: l.includes(id) ? l.filter((x) => x !== id) : [...l, id] }; },
    cancelIncident: () => { cy.incidentForm = null; render(); },
    saveIncident: () => { const p = CY.incidentProblem(cy.incidentForm); if (p) return fail(p); return run(async () => { const r = await api.createCyIncident(CY.incidentBody(cy.incidentForm)); cy.incidentForm = null; cy.incident = r; cy.closeForm = { lessons_learned: "", notification_decision: "" }; await refresh(); cy.notice = `Incident ${r.ref} recorded.`; }); },
    openIncident: (id) => run(async () => { clearForms(); closeViews(); cy.tab = "incidents"; cy.incident = await api.cyIncident(id); cy.closeForm = { lessons_learned: "", notification_decision: "" }; }),
    closeIncidentView: () => run(async () => { cy.incident = null; clearForms(); await refresh(); }),
    incidentStep: (step) => { if (step === "resolve" || step === "contain") { const p = step === "resolve" ? need("i", "the root cause", 10) : need("i", "how it was contained", 5); if (p) return fail(p); } return run(async () => { await api.cyIncidentStep(cy.incident.id, step, { note: note("i") }); clearNote("i"); await refresh(); }, { investigate: "Investigation started.", contain: "Marked as contained.", resolve: "Marked as resolved. A different person must close it." }[step]); },
    closeChange: (k, v) => { cy.closeForm = { ...cy.closeForm, [k]: v }; },
    closeIncident: () => { const p = CY.closeProblem(cy.closeForm || {}, cy.incident); if (p) return fail(p); return run(async () => { await api.cyIncidentStep(cy.incident.id, "close", { lessons_learned: cy.closeForm.lessons_learned.trim(), notification_decision: (cy.closeForm.notification_decision || "").trim() }); cy.closeForm = { lessons_learned: "", notification_decision: "" }; await refresh(); }, "Incident closed."); },
    reopenIncident: () => { const p = need("iback", "a reason", 3); if (p) return fail(p); return run(async () => { await api.cyIncidentStep(cy.incident.id, "reopen", { note: note("iback") }); clearNote("iback"); await refresh(); }, "Sent back to investigation."); },
    addTimeline: () => { const p = need("tl", "the note", 3); if (p) return fail(p); return run(async () => { await api.cyIncidentStep(cy.incident.id, "timeline", { note: note("tl") }); clearNote("tl"); await refresh(); }, "Added to the timeline."); },
    // access reviews
    newReview: () => { clearForms(); closeViews(); cy.tab = "reviews"; cy.reviewForm = CY.emptyReview(); render(); },
    reviewChange: set("reviewForm"),
    cancelReview: () => { cy.reviewForm = null; render(); },
    saveReview: () => { const p = CY.reviewProblem(cy.reviewForm); if (p) return fail(p); return run(async () => { const f = cy.reviewForm; const r = await api.createCyReview({ name: f.name.trim(), scope: f.scope.trim(), due_date: f.due_date.trim() }); cy.reviewForm = null; cy.review = r; cy.entryForm = CY.emptyEntry(); await refresh(); cy.notice = `Review ${r.ref} created. Add the people and accounts to review.`; }); },
    openReview: (id) => run(async () => { clearForms(); closeViews(); cy.tab = "reviews"; cy.review = await api.cyReview(id); cy.entryForm = CY.emptyEntry(); }),
    closeReviewView: () => run(async () => { cy.review = null; clearForms(); await refresh(); }),
    entryChange: set("entryForm"),
    addEntry: () => { const p = CY.entryProblem(cy.entryForm); if (p) return fail(p); return run(async () => { const f = cy.entryForm; await api.addCyEntry(cy.review.id, { subject: f.subject.trim(), system: f.system.trim(), access: f.access.trim() }); cy.entryForm = CY.emptyEntry(); await refresh(); }, "Entry added."); },
    decideEntry: (id, decision) => { if (decision === "REMOVE") { const p = need("entry", "why the access should be removed", 3); if (p) return fail(p); } return run(async () => { await api.decideCyEntry(cy.review.id, id, decision, note("entry")); clearNote("entry"); await refresh(); }); },
    confirmRemoved: (id) => run(async () => { await api.confirmCyRemoved(cy.review.id, id); await refresh(); }, "Removal confirmed."),
    submitReview: () => run(async () => { await api.cyReviewStep(cy.review.id, "submit"); await refresh(); }, "Submitted. A different person must approve it."),
    decideReview: (ok) => { if (!ok) { const p = need("rv", "a note saying why you are sending it back", 3); if (p) return fail(p); } return run(async () => { await api.cyReviewStep(cy.review.id, ok ? "approve" : "reject", note("rv")); clearNote("rv"); await refresh(); }, ok ? "Review approved." : "Sent back."); },
    // reports
    newReport: () => { clearForms(); closeViews(); cy.tab = "reports"; cy.reportForm = { title: "" }; render(); },
    reportChange: set("reportForm"),
    cancelReport: () => { cy.reportForm = null; render(); },
    saveReport: () => { const p = CY.reportProblem(cy.reportForm); if (p) return fail(p); return run(async () => { const r = await api.createCyReport({ title: cy.reportForm.title.trim() }); cy.reportForm = null; cy.report = r; await refresh(); cy.notice = `Report ${r.ref} created.`; }); },
    openReport: (id) => run(async () => { clearForms(); closeViews(); cy.tab = "reports"; cy.report = await api.cyReport(id); }),
    closeReportView: () => run(async () => { cy.report = null; clearForms(); await refresh(); }),
    submitReport: () => run(async () => { await api.submitCyReport(cy.report.id); await refresh(); }, "Frozen and submitted. A different person must now approve it."),
    decideReport: (ok) => { if (!ok) { const p = need("report", "a note saying why you are sending it back", 3); if (p) return fail(p); } return run(async () => { await (ok ? api.approveCyReport(cy.report.id, note("report")) : api.rejectCyReport(cy.report.id, note("report"))); clearNote("report"); await refresh(); }, ok ? "Report approved." : "Sent back."); },
    exportReport: () => run(async () => { const { blob, filename } = await api.exportCyReport(cy.report.id); saveBlob(blob, filename); }, "Downloaded."),
  };
}

// ----------------------------------------------------------------------
// Health Centre Administration
// ----------------------------------------------------------------------
function newHealth() {
  return { options: null, facilityId: "", tab: "dashboard", data: {}, ref: {}, vault: [], dashboard: null, form: null, detail: null, noteText: "", busy: false, error: null, notice: null };
}

function renderHealthPage(authState) {
  if (!uiState.hc) uiState.hc = newHealth();
  once("hcLoading", () => loadHealth(authState.role));
  return Health({ hc: uiState.hc, role: authState.role, userId: authState.user && authState.user.id, loading: uiState.hcLoading, onRetry: () => { loadedOnce.delete("hcLoading"); render(); }, actions: healthActions(authState) });
}

/** Reload what the current tab shows. Reference lists feed the drop-downs in forms. */
async function healthRefresh(hc, role, withOptions) {
  if (withOptions || !hc.options) hc.options = await api.hcOptions();
  const fs = hc.options.facilities || [];
  if (!fs.some((f) => f.id === hc.facilityId)) hc.facilityId = fs.length ? fs[0].id : "";
  const fid = hc.facilityId, c = HC.caps(role);
  hc.data = {}; hc.dashboard = null;
  if (!fid) { hc.ref = {}; if (c.admin) hc.data.facilities = await api.hcGet("/facilities"); return; }
  const soft = (p) => p.catch(() => []);
  const [depts, suppliers, items, payers, fees] = await Promise.all([
    api.hcGet(`/facilities/${encodeURIComponent(fid)}`).then((f) => f.departments).catch(() => []), soft(api.hcGet(`/facilities/${encodeURIComponent(fid)}/suppliers`)), soft(api.hcGet(`/facilities/${encodeURIComponent(fid)}/items`)),
    soft(api.hcGet(`/facilities/${encodeURIComponent(fid)}/payers`)), soft(api.hcGet(`/facilities/${encodeURIComponent(fid)}/fees`))]);
  hc.ref = { depts, suppliers, items, payers, fees };
  if (hc.tab === "dashboard") { hc.dashboard = await api.hcGet(`/facilities/${encodeURIComponent(fid)}/dashboard`); return; }
  const tabSecs = HC.visibleSections(hc.tab, c);
  await Promise.all(tabSecs.map(async ([id, s]) => { try { hc.data[id] = await s.load(api, fid); } catch (err) { hc.data[id] = null; hc.error = err.message || `${s.title} could not be loaded.`; } }));
}

async function loadHealth(role) {
  const hc = uiState.hc || (uiState.hc = newHealth());
  hc.error = null;
  try {
    await healthRefresh(hc, role, true);
    hc.vault = await api.listEvidence().catch(() => []);
  } catch (err) { hc.error = err.message || "Health Centre could not be loaded."; }
}

function healthActions(authState) {
  const hc = uiState.hc, role = authState.role, userId = authState.user && authState.user.id;
  const run = async (fn, ok, withOptions, refresh) => { hc.error = null; hc.notice = null; hc.busy = true; render(); try { await fn(); if (ok) hc.notice = ok; if (refresh !== false) await healthRefresh(hc, role, withOptions); } catch (err) { hc.error = err.message || "That did not work."; } hc.busy = false; render(); };
  const fail = (m) => { hc.error = m; hc.notice = null; render(); };
  const rowOf = (secId, rowId) => (hc.data[secId] || []).find((r) => r.id === rowId);
  const close = () => { hc.form = null; hc.detail = null; hc.noteText = ""; };
  const setVal = (k, v) => { hc.form.values = { ...hc.form.values, [k]: v }; };
  return {
    setTab: (t) => { hc.tab = t; close(); return run(async () => {}); },
    setFacility: (id) => { hc.facilityId = id; close(); return run(async () => {}); },
    noteChange: (v) => { hc.noteText = v; },
    closeDetail: () => { hc.detail = null; render(); },
    newForm: (secId) => { close(); const name = SECTIONS_CREATE(secId); hc.form = { name, secId, row: null, values: HC.emptyForm(HC.FORMS[name], null) }; hc.error = null; render(); },
    formChange: (k, v) => setVal(k, v),
    lineChange: (k, i, sub, v) => { const rows = (hc.form.values[k] || []).map((r, j) => (j === i ? { ...r, [sub]: v } : r)); setVal(k, rows); },
    addLine: (k) => { const fd = HC.FORMS[hc.form.name].fields.find((f) => f.k === k); setVal(k, [...(hc.form.values[k] || []), HC.blankLine(fd)]); render(); },
    removeLine: (k, i) => { setVal(k, (hc.form.values[k] || []).filter((_, j) => j !== i)); render(); },
    toggleEvidence: (id) => { const l = hc.form.values.evidence_ids || []; setVal("evidence_ids", l.includes(id) ? l.filter((x) => x !== id) : [...l, id]); },
    toggleFacility: (id) => { const l = hc.form.values.facility_ids || []; setVal("facility_ids", l.includes(id) ? l.filter((x) => x !== id) : [...l, id]); },
    cancelForm: () => { hc.form = null; hc.error = null; render(); },
    saveForm: () => {
      const f = hc.form, def = HC.FORMS[f.name], p = HC.formProblem(def, f.values); if (p) return fail(p);
      return run(async () => { await def.submit(api, hc.facilityId, HC.formBody(def, f.values), f.row); hc.form = null; }, def.done, true);
    },
    runAction: async (secId, actId, rowId) => {
      const sec = HC.SECTIONS[secId], act = sec.actions.find((x) => x.id === actId), row = rowOf(secId, rowId);
      if (!act || !row) return;
      hc.error = null; hc.notice = null;
      if (act.form) { close(); hc.form = { name: act.form, secId, row, values: HC.emptyForm(HC.FORMS[act.form], row) }; render(); return; }
      if (act.detail) return run(async () => { hc.detail = { title: `${sec.title}: ${row.ref || row.name || row.sku || ""}`.trim(), lines: await act.detail(api, hc.facilityId, row) }; }, null, false, false);
      if (act.export) return run(async () => { const { blob, filename } = await api.exportHcReport(row.id); saveBlob(blob, filename); }, "Downloaded. The file is marked confidential.");
      const min = HC.needsNote(act, row);
      if (min > 0) { const p = HC.noteProblem(hc.noteText, `${act.note.label || "a reason"}`, min); if (p) return fail(p); }
      return run(async () => { await act.call(api, row, (hc.noteText || "").trim(), hc.facilityId, true, userId); hc.noteText = ""; hc.detail = null; }, act.done);
    },
  };
}
const SECTIONS_CREATE = (secId) => HC.SECTIONS[secId].create.form;

// ----------------------------------------------------------------------
// ASAVEXA AI, docked on every signed-in page (the Proof Lens)
// ----------------------------------------------------------------------
const BRIEF_STALE_MS = 2 * 60 * 1000;

function dockState() { return uiState.dock || (uiState.dock = DK.newDock()); }

function renderDock(authState, path) {
  if (!DK.dockAvailable(authState.role)) return null;
  const dock = dockState(), ws = DK.workspaceForPath(path);
  const key = `${authState.organisationId}|${authState.role}|${ws}`;
  // Another organisation or workspace must never show the previous one's brief or answer, even for a moment.
  if (dock.org !== authState.organisationId) { Object.assign(dock, DK.newDock(), { org: authState.organisationId, ws }); }
  if (dock.ws !== ws) { dock.ws = ws; dock.tab = "brief"; dock.brief = null; dock.answer = null; dock.askError = null; }
  if (dock.briefFor !== key) loadDockBrief(authState, ws, key);
  const urgent = dock.brief && dock.brief.ok ? dock.brief.items.filter((i) => i.tone !== "clear").length : 0;
  return AiDock({ dock, role: authState.role, workspace: ws, urgent, a: dockActions(authState, ws, key) });
}

async function loadDockBrief(authState, ws, key) {
  const dock = dockState();
  dock.briefFor = key; dock.briefLoading = true;
  const hint = { facilityId: uiState.hc && uiState.hc.facilityId };
  let out;
  try { out = await DK.fetchBrief(api, ws, authState.role, hint); } catch (err) { out = { ok: false, reason: "error", message: err.message || "The brief could not be loaded." }; }
  if (dock.briefFor !== key) return;            // the person moved on; never show another page's brief
  dock.brief = out; dock.briefLoading = false; render();
}

function dockActions(authState, ws, key) {
  const dock = dockState();
  const refresh = () => { dock.brief = dock.brief && dock.brief.ok ? dock.brief : null; loadDockBrief(authState, ws, key); render(); };
  const ask = async (q) => {
    const text = String(q == null ? dock.question : q).trim();
    if (!text) { dock.askError = "Type a question first."; render(); return; }
    dock.question = text; dock.askError = null; dock.answer = null; dock.asking = true; render();
    try { dock.answer = DK.summariseAnswer(await api.aiAsk(text)); }
    catch (err) { dock.askError = err.status === 403 ? "Your role cannot ask ASAVEXA AI." : (err.message || "ASAVEXA AI could not answer."); }
    dock.asking = false; render();
  };
  return {
    onToggle: () => {
      dock.open = !dock.open;
      if (dock.open) {
        const fresh = dock.brief && dock.brief.asOf && Date.now() - Date.parse(dock.brief.asOf) < BRIEF_STALE_MS;
        if (!fresh && !dock.briefLoading) loadDockBrief(authState, ws, key);
      }
      render();
      const el = document.getElementById(dock.open ? "lens-close" : "lens-launch"); if (el) el.focus();
    },
    onTab: (t) => { dock.tab = t; render(); if (t === "ask") { const q = document.getElementById("lens-q"); if (q) q.focus(); } },
    onQuestion: (v) => { dock.question = v; },
    onAsk: () => ask(),
    onStarter: (q) => { dock.tab = "ask"; return ask(q); },
    onRefresh: refresh,
    onNavigate: () => { dock.open = false; },
  };
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && uiState.dock && uiState.dock.open) { uiState.dock.open = false; render(); const el = document.getElementById("lens-launch"); if (el) el.focus(); }
});

function newNet() {
  return { tab: "connections", guide: null, me: null, invites: null, form: null, created: null, code: "", preview: null, accept: { scopes: [], detail: false }, view: null, log: null, logFor: null,
    busy: false, notice: null, error: null };
}

function renderNetworkPage(authState) {
  if (!uiState.net) uiState.net = newNet();
  once("netLoading", () => loadNetwork());
  return Network({ net: uiState.net, loading: uiState.netLoading, onRetry: () => { loadedOnce.delete("netLoading"); render(); }, actions: networkActions(authState) });
}

async function loadNetwork() {
  const net = uiState.net || (uiState.net = newNet());
  net.error = null;
  try {
    [net.guide, net.me] = await Promise.all([api.networkGuide(), api.networkMe()]);
    net.invites = net.me.can_manage && net.me.profile ? await api.networkInvites() : [];
  } catch (err) {
    net.error = err.message || "The network could not be loaded.";
  }
}

function networkActions() {
  const net = uiState.net;
  const run = async (fn, okNotice) => {
    net.error = null; net.notice = null; net.busy = true; render();
    try { await fn(); if (okNotice) net.notice = okNotice; } catch (err) { net.error = err.message || "That did not work."; }
    net.busy = false; render();
  };
  const reload = async () => { await loadNetwork(); };
  const profileForm = () => { const p = net.me && net.me.profile; return { kind: "profile", f: { org_type: p ? p.org_type : "", display_name: p ? p.display_name : "", description: p ? p.description : "" } }; };
  return {
    setTab: (t) => { net.tab = t; net.view = null; net.form = t === "profile" ? profileForm() : null; net.preview = null; net.error = null; net.notice = null; net.logFor = null; render(); },
    cancelForm: () => { net.form = null; render(); },
    formChange: (k, v) => { if (!net.form && (net.tab === "profile" || (net.me && !net.me.profile))) net.form = profileForm(); if (net.form) net.form.f[k] = v; },
    toggleScope: (s, on) => { const cur = new Set(net.form.f.scopes || []); if (on) cur.add(s); else cur.delete(s); net.form.f.scopes = Object.keys(SCOPE_ORDER).filter((x) => cur.has(x)); },
    // profile
    saveProfile: () => run(async () => {
      const f = (net.form && net.form.f) || profileForm().f;
      if (!f.org_type) throw new Error("Choose what kind of organisation you are.");
      await api.setNetworkProfile({ org_type: f.org_type, display_name: (f.display_name || "").trim(), description: (f.description || "").trim() }); net.form = null; await reload(); net.tab = "connections";
    }, "Profile saved."),
    // invitations
    startInvite: () => { net.form = { kind: "invite", f: emptyInviteForm() }; net.error = null; render(); },
    createInvite: () => run(async () => {
      const bad = inviteProblem(net.form.f, net.me.can_offer_to); if (bad) throw new Error(bad);
      net.created = await api.createNetworkInvite(inviteBody(net.form.f)); net.form = null; await reload();
    }),
    dismissCreated: () => { net.created = null; render(); },
    cancelInvite: (id) => run(async () => { await api.cancelNetworkInvite(id); await reload(); }, "Invitation cancelled."),
    setCode: (v) => { net.code = v; },
    previewCode: () => run(async () => {
      if (!(net.code || "").trim()) throw new Error("Enter the invitation code first.");
      net.preview = await api.previewNetworkInvite(net.code.trim()); net.accept = { scopes: [...net.preview.grant.scopes], detail: !!net.preview.grant.include_detail };
    }),
    clearPreview: () => { net.preview = null; render(); },
    toggleAcceptScope: (s, on) => { const cur = new Set(net.accept.scopes); if (on) cur.add(s); else cur.delete(s); net.accept.scopes = net.preview.grant.scopes.filter((x) => cur.has(x)); render(); },
    setAcceptDetail: (on) => { net.accept.detail = on; },
    acceptCode: () => run(async () => {
      const pv = net.preview, body = { code: net.code.trim() };
      if (pv.you_decide) { const g = acceptGrant(pv, net.accept.scopes, net.accept.detail, pv.grant.closed_periods_only); if (g) body.grant = g; }
      await api.acceptNetworkInvite(body); net.preview = null; net.code = ""; await reload(); net.tab = "connections";
    }, "Connected. Both organisations' audit trails record it."),
    // connections
    openView: (id) => run(async () => { net.view = await api.networkPassport(id); }),
    closeView: () => { net.view = null; render(); },
    loadLog: (id) => run(async () => { net.log = await api.networkAccessLog(id); net.logFor = id; }),
    startGrant: (c) => { net.form = { kind: "grant", f: { id: c.id, scopes: [...c.grant.scopes], include_detail: c.grant.include_detail, closed_periods_only: c.grant.closed_periods_only, extend_days: "" } }; net.error = null; render(); },
    saveGrant: () => run(async () => {
      const f = net.form.f; if (!f.scopes.length) throw new Error("Leave at least one kind of information, or end the connection instead.");
      const body = { grant: { scopes: f.scopes, include_detail: !!f.include_detail, closed_periods_only: !!f.closed_periods_only } };
      if (String(f.extend_days || "").trim()) { const n = Number(f.extend_days); if (!Number.isInteger(n) || n < 1 || n > 365) throw new Error("Extend by a whole number of days from 1 to 365."); body.extend_days = n; }
      await api.updateNetworkConnection(f.id, body); net.form = null; await reload();
    }, "Saved. The change applies the next time they open it."),
    startEnd: (id) => { net.form = { kind: "end", f: { id, reason: "" } }; net.error = null; render(); },
    endConnection: () => run(async () => { await api.endNetworkConnection(net.form.f.id, (net.form.f.reason || "").trim()); net.form = null; await reload(); }, "Connection ended. They can no longer open anything."),
  };
}
const SCOPE_ORDER = { IDENTITY: 1, FINANCIAL_HISTORY: 1, EVIDENCE_QUALITY: 1, GOVERNANCE: 1, REPORTING: 1, AUDIT_TRAIL: 1 };
