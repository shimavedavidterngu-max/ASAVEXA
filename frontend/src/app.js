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
import { Login, OrganisationPicker } from "./pages/Login.js";
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
import { reviewForm, reviewBody, declarationBody, engagementBody, reviewerBody, emptyObservation, actingMode } from "./lib/validation.js";
import { makeBinding, parseOidcReturn, interpretLogin, parseRegions } from "./lib/signin.js";

const API_BASE_URL = "https://asavexa.onrender.com";
const authStore = new AuthStore();
const api = new ApiClient({
  baseUrl: API_BASE_URL,
  getToken: () => authStore.getToken(),
  onUnauthenticated: () => {
    authStore.clear();
    resetSecurityState();
    render();
  },
});

const root = document.getElementById("app-root");

const NAV_ITEMS = [
  { path: "/", label: "Dashboard", permission: null },
  { path: "/audit", label: "Audit Workspace", permission: PERMISSIONS.AUDIT_READ },
  { path: "/accounting", label: "Accounting", permission: PERMISSIONS.LEDGER_READ },
  { path: "/evidence", label: "Evidence", permission: PERMISSIONS.EVIDENCE_READ },
  { path: "/reconciliation", label: "Reconciliation", permission: PERMISSIONS.RECONCILIATION_READ },
  { path: "/reporting", label: "Reporting", permission: PERMISSIONS.REPORTING_READ },
  { path: "/period-close", label: "Period Close", permission: PERMISSIONS.PERIOD_CLOSE_READ },
  { path: "/compliance", label: "Controls & Compliance", permission: PERMISSIONS.CONTROL_READ },
  { path: "/admin", label: "Administration", permission: PERMISSIONS.ORG_MANAGE_USERS },
  { path: "/import", label: "Data Import", permission: null, anyOf: [PERMISSIONS.RECONCILIATION_IMPORT, PERMISSIONS.EVIDENCE_UPLOAD, PERMISSIONS.ACCOUNT_MANAGE, PERMISSIONS.JOURNAL_CREATE] },
  { path: "/ai", label: "ASAVEXA AI", permission: PERMISSIONS.LEDGER_READ },
  { path: "/passport", label: "Financial Passport", permission: PERMISSIONS.PASSPORT_MANAGE },
  { path: "/passport/sharing", label: "Passport Sharing", permission: PERMISSIONS.PASSPORT_MANAGE },
  { path: "/standards", label: "Standards & Policies", permission: null },
  { path: "/validation", label: "Professional Validation", permission: PERMISSIONS.AUDIT_READ },
  { path: "/security", label: "Security", permission: null },
  { path: "/diagnostics", label: "Connection & Self-Test", permission: null },
];

// Order matters for matchRoute (first match wins): a literal segment
// like "/new" must be listed before the ":id" param route it would
// otherwise also match.
const routes = [
  { path: "/", name: "dashboard" },
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
  { path: "/standards", name: "standards" },
  { path: "/validation", name: "validation" },
  { path: "/security", name: "security" },
  { path: "/diagnostics", name: "diagnostics" },
];

let uiState = {
  loginMode: "login", loginError: null, loginPending: false,
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

function render() {
  const authState = authStore.getState();

  // A recipient's link is public: it never needs (or touches) an organisation login.
  const publicMatch = matchRoute(routes, router.currentPath());
  if (publicMatch && publicMatch.route.name === "shared") {
    renderSharedPassport(publicMatch.params.token);
    return;
  }

  if (!authState.token) {
    mount(
      h("div", { id: "screen" },
        Login({
          mode: uiState.loginMode, pending: uiState.loginPending, error: uiState.loginError,
          onSubmit: handleAuthSubmit, onSwitchMode: (m) => { uiState.loginMode = m; uiState.loginError = null; render(); },
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

  if (!authState.organisationId) {
    api.myOrganisations().then((orgs) => {
      mount(
        OrganisationPicker({
          organisations: orgs,
          onSelect: async (orgId) => {
            try {
              const { role } = await api.selectOrganisation(orgId);
              authStore.setOrganisation(orgId, role);
            } catch (err) {
              // e.g. this organisation requires two-step sign-in and this session has not used it
              window.alert(err.message || "Could not open this organisation.");
            }
            render();
          },
          onSecurity: () => { uiState.secNoOrg = true; render(); },
          onCreateNew: async () => {
            const name = window.prompt("Organisation name:");
            if (!name) return;
            const org = await api.createOrganisation(name);
            const { role } = await api.selectOrganisation(org.id);
            authStore.setOrganisation(org.id, role);
            render();
          },
        }),
        root
      );
    });
    return;
  }

  renderShell(authState);
}

function renderShell(authState) {
  const path = router.currentPath();
  const matched = matchRoute(routes, path);

  mount(
    h(
      "div",
      { className: "app-shell" },
      h(
        "nav",
        { className: "app-sidebar" },
        h("div", { className: "brand" }, "ASAVEXA", h("small", {}, "Don't just report it. Prove it.")),
        visibleNav(authState, path).map(({ item, active }) =>
          h(
            "a",
            {
              className: `nav-link${active ? " active" : ""}`,
              href: `#${item.path}`,
            },
            item.label
          )
        )
      ),
      h(
        "main",
        { className: "app-main" },
        h(
          "div",
          { className: "app-topbar" },
          h("div", { className: "org-switcher" }, `Organisation: ${authState.organisationId}  ·  Role: ${authState.role}`),
          h("button", { className: "btn btn-secondary", onClick: handleLogout }, "Sign out")
        ),
        renderPage(matched, authState)
      ),
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

/** The sidebar entries this role may see, with only the most specific match marked active
 * (so "/passport/sharing" lights up Passport Sharing, not Financial Passport as well). */
function visibleNav(authState, path) {
  const items = NAV_ITEMS.filter((item) => (item.anyOf ? item.anyOf.some((p) => allowed(authState.role, p)) : !item.permission || allowed(authState.role, item.permission)));
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
    return Dashboard({ role: authState.role, data: uiState.dashboardData || {}, onNavigate: nav });
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
  if (name.startsWith("evidence")) return renderEvidence(name, params, authState, nav);
  if (name.startsWith("reconciliation")) return renderReconciliation(name, params, authState, nav);
  if (name === "reporting") return renderReporting(authState, nav);
  if (name === "period-close") return renderPeriodClose(authState, nav);
  if (name.startsWith("compliance")) return renderCompliance(name, params, authState, nav);
  if (name === "admin") return renderAdmin(authState, nav);
  if (name === "import") return renderImport(authState, nav);
  if (name === "ai") return renderAi(authState);
  if (name === "passport-sharing") return renderPassportSharing(authState, nav);
  if (name === "passport") return renderPassport(authState, nav);
  if (name === "standards") return renderStandards(authState);
  if (name === "diagnostics") return renderDiagnostics(authState);
  if (name === "security") return renderSecurityPage(authState);
  if (name === "validation") return renderValidationPage(authState);

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

async function handleAuthSubmit({ email, password }) {
  uiState.loginPending = true;
  uiState.loginError = null;
  render();
  try {
    if (uiState.loginMode === "register") {
      await api.register(email, password);
    }
    const result = interpretLogin(await api.login(email, password));
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
  uiState.sec = null; uiState.secNoOrg = false; uiState.mfaChallenge = null;
  loadedOnce.delete("secLoading");
}

function handleLogout() {
  api.logout().finally(() => {
    authStore.clear();
    resetSecurityState();
    render();
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
