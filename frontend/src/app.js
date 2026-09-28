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
import { Accounting } from "./pages/Accounting.js";
import { Evidence } from "./pages/Evidence.js";
import { Reconciliation } from "./pages/Reconciliation.js";
import { Reporting } from "./pages/Reporting.js";
import { PeriodClose } from "./pages/PeriodClose.js";
import { Compliance } from "./pages/Compliance.js";
import { Administration } from "./pages/Administration.js";

const authStore = new AuthStore();
const api = new ApiClient({
  getToken: () => authStore.getToken(),
  onUnauthenticated: () => {
    authStore.clear();
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
];

let uiState = {
  loginMode: "login", loginError: null, loginPending: false,
  auditQuery: "", auditJournal: null, auditChain: null, auditError: null,

  // Accounting
  accounts: null, periods: null, accountingError: null,
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

  // Period Close
  selectedClosePeriodId: "", periodCloseError: null, closeReadiness: null, activeCloseProcess: null,
  closeProcesses: null, approveReason: "", periodCloseRejectReason: "",

  // Compliance
  controls: null, executions: null, complianceError: null, selectedControlId: null, executeParams: "",
  defineForm: { domain: "ACCOUNTING", severity: "MEDIUM" }, defineError: null, definePending: false,
  findings: null, findingFilter: "", finding: null, findingError: null, remediation: null,
  reasonInputs: {}, remediationForm: {},

  // Administration
  organisation: null, members: null, adminError: null,
  addMemberForm: { role: "READ_ONLY" }, addMemberError: null, addMemberPending: false, roleDrafts: {},
};

const router = new Router(routes, { onChange: () => render() });

function render() {
  const authState = authStore.getState();

  if (!authState.token) {
    mount(
      h("div", { id: "screen" },
        Login({
          mode: uiState.loginMode, pending: uiState.loginPending, error: uiState.loginError,
          onSubmit: handleAuthSubmit, onSwitchMode: (m) => { uiState.loginMode = m; uiState.loginError = null; render(); },
        })
      ),
      root
    );
    return;
  }

  if (!authState.organisationId) {
    api.myOrganisations().then((orgs) => {
      mount(
        OrganisationPicker({
          organisations: orgs,
          onSelect: async (orgId) => {
            const { role } = await api.selectOrganisation(orgId);
            authStore.setOrganisation(orgId, role);
            render();
          },
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
        NAV_ITEMS.filter((item) => !item.permission || allowed(authState.role, item.permission)).map((item) =>
          h(
            "a",
            {
              className: `nav-link${path === item.path || (item.path !== "/" && path.startsWith(item.path)) ? " active" : ""}`,
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
      )
    ),
    root
  );
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
    return AuditWorkspace({
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

  return h("div", { className: "empty-state card" }, h("h3", {}, "Page not found"));
}

// ------------------------------------------------------------------
// Shared loading helper: fetch-once-per-render-cycle guard, matching
// loadDashboardData's own pattern below.
// ------------------------------------------------------------------
function once(flagKey, loader) {
  if (uiState[flagKey]) return;
  uiState[flagKey] = true;
  loader().finally(() => {
    uiState[flagKey] = false;
  });
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
    const { user, token } = await api.login(email, password);
    authStore.setSession(token, user);
  } catch (err) {
    uiState.loginError = err.message;
  } finally {
    uiState.loginPending = false;
    render();
  }
}

function handleLogout() {
  api.logout().finally(() => {
    authStore.clear();
    render();
  });
}

async function handleAuditSearch(query) {
  uiState.auditQuery = query;
  uiState.auditError = null;
  uiState.auditJournal = null;
  uiState.auditChain = null;
  render();
  try {
    const journal = await api.getJournal(query);
    const auditEvents = await api.journalAuditTrail(query).catch(() => []);
    let evidence = null;
    const status = await api.evidenceStatus(query).catch(() => null);
    if (status && status.evidence_id) {
      evidence = await api.getEvidence(status.evidence_id).catch(() => null);
    }
    uiState.auditJournal = journal;
    uiState.auditChain = buildChainLinks({ journal, evidence, auditEvents });
  } catch (err) {
    uiState.auditError = err.message || "Could not find that journal.";
  } finally {
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
    accounts: uiState.accounts, periods: uiState.periods, onNavigate: nav, onRetry: () => { uiState.accounts = null; uiState.periods = null; render(); },
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
      rejectReason: uiState.evidenceRejectReason, onRejectReasonChange: (v) => { uiState.evidenceRejectReason = v; render(); },
    });
  }
  once("evidenceLoading", loadEvidenceList);
  return Evidence({
    role: authState.role, view: "list", loading: uiState.evidenceLoading, error: uiState.evidenceError,
    items: uiState.evidenceItems, onNavigate: nav, onRetry: loadEvidenceList,
    filterStatus: uiState.evidenceFilterStatus, filterType: uiState.evidenceFilterType,
    onFilterChange: (field, value) => {
      if (field === "status") uiState.evidenceFilterStatus = value; else uiState.evidenceFilterType = value;
      loadEvidenceList();
    },
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
    const query = {};
    if (uiState.evidenceFilterStatus) query.status = uiState.evidenceFilterStatus;
    if (uiState.evidenceFilterType) query.type = uiState.evidenceFilterType;
    uiState.evidenceItems = await api.listEvidence(query);
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
  uiState.evidenceUploadPending = true;
  uiState.evidenceUploadError = null;
  render();
  try {
    await api.uploadEvidence({
      file: uiState.evidenceUploadFile,
      type: uiState.evidenceUploadForm.type || "OTHER",
      linkedJournalId: uiState.evidenceUploadForm.linkedJournalId,
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

async function loadEvidenceDetail(id) {
  uiState.evidenceDetailLoading = true;
  uiState.evidenceDetailError = null;
  uiState.evidenceDetail = null;
  render();
  try {
    uiState.evidenceDetail = await api.getEvidence(id);
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
    return Reconciliation({
      role: authState.role, view: "new", form: uiState.reconciliationForm,
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
    reconciliations: uiState.reconciliations, onNavigate: nav, onRetry: loadReconciliations,
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
    const r = await api.createReconciliation(uiState.reconciliationForm);
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
    onSelectReportType: (t) => { uiState.reportType = t; uiState.reportResult = null; uiState.traceResult = null; render(); },
    onSelectPeriod: (id) => { uiState.selectedPeriodId = id; render(); },
    onSelectAccount: (id) => { uiState.selectedAccountId = id; render(); },
    onGenerate: () => handleGenerateReport(),
    onRetry: () => handleGenerateReport(),
  });
}

async function loadReportingPrereqs() {
  try {
    if (!uiState.periods) uiState.periods = await api.listPeriods();
    if (!uiState.accounts) uiState.accounts = await api.listAccounts();
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
    else if (uiState.reportType === "trace") uiState.traceResult = await api.traceLine(uiState.selectedAccountId, uiState.selectedPeriodId);
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
    onSelectPeriod: (id) => { uiState.selectedClosePeriodId = id; uiState.closeReadiness = null; uiState.activeCloseProcess = null; uiState.closeProcesses = null; loadPeriodCloseState(id); },
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
    if (!uiState.periods) uiState.periods = await api.listPeriods();
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
    selectedControlId: uiState.selectedControlId, onSelectControl: (id) => { uiState.selectedControlId = id; render(); },
  });
}

async function loadControlsAndExecutions() {
  uiState.complianceError = null;
  try {
    uiState.controls = await api.listControls();
    uiState.executions = await api.listExecutions();
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
  try {
    await api.executeControl(controlId, uiState.executeParams || undefined);
    uiState.executions = await api.listExecutions();
    uiState.selectedControlId = null;
  } catch (err) {
    uiState.complianceError = err.message;
  } finally {
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
    onChangeRole: (userId, role) => handleChangeRole(authState, userId, role),
    roleDrafts: uiState.roleDrafts, onRoleDraftChange: (userId, role) => { uiState.roleDrafts = { ...uiState.roleDrafts, [userId]: role }; render(); },
    onRevokeMember: (userId) => handleRevokeMember(authState, userId),
    currentUserId: authState.user && authState.user.id,
  });
}

async function loadAdminData(authState) {
  uiState.adminError = null;
  try {
    const orgs = await api.myOrganisations();
    uiState.organisation = orgs.find((o) => o.id === authState.organisationId) || null;
    uiState.members = await api.listMembers(authState.organisationId);
  } catch (err) {
    uiState.adminError = err.message || "Could not load organisation data.";
  } finally {
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
