/**
 * ApiClient — the ONLY place in this frontend that calls `fetch`.
 * Every route path below was copied from the real router source
 * (src/asavexa/api/routers/*.py), not invented. See
 * docs/frontend-runtime-verification.md for the full route inventory
 * this was built from.
 *
 * Handles: base URL, Bearer auth, org context (no header — org_id
 * lives in the session server-side, exactly matching the backend's
 * own design; see security-architecture.md), JSON (de)serialization,
 * and mapping every backend error shape to a single ApiError.
 *
 * This client is a thin, honest wrapper — it does not retry mutating
 * requests (retrying a POST that already succeeded server-side but
 * whose response was lost could double-post a journal; unsafe), and
 * it does not implement any financial/business calculation of its own
 * (see docs/frontend-runtime-verification.md, "Never a parallel
 * accounting engine").
 */

export class ApiError extends Error {
  constructor(status, body) {
    super(ApiError.describe(status, body));
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }

  /** Turns any backend error shape into one readable sentence —
   * including FastAPI's 422 validation lists, which would otherwise
   * print as "[object Object]". */
  static describe(status, body) {
    const detail = body && body.detail;
    if (Array.isArray(detail)) {
      const parts = detail.map((d) => {
        const field = Array.isArray(d.loc) ? d.loc.filter((x) => x !== "body").join(".") : "";
        const msg = d.msg || "is invalid";
        return field ? `${field}: ${msg}` : msg;
      });
      if (parts.length) return parts.join("; ");
    }
    if (typeof detail === "string" && detail) return detail;
    return (body && body.message) || `Request failed (${status})`;
  }

  /** UX-level classification — mirrors the backend's own status
   * buckets (see docs/security-architecture.md's error-behavior
   * section), never re-derives them independently. */
  get kind() {
    if (this.status === 401) return "unauthenticated";
    if (this.status === 403) return "unauthorized";
    if (this.status === 404) return "not_found";
    if (this.status === 409) return "conflict";
    if (this.status === 422) return "validation";
    if (this.status >= 500) return "server_error";
    return "bad_request";
  }
}

export class NetworkError extends Error {
  constructor(cause) {
    super("Could not reach the ASAVEXA API. Check your connection and try again.");
    this.name = "NetworkError";
    this.cause = cause;
  }
}

const DEFAULT_BASE_URL = "/api"; // reverse-proxied to the FastAPI app in production; see docs/frontend-runtime-verification.md

export class ApiClient {
  constructor({ baseUrl = DEFAULT_BASE_URL, getToken, onUnauthenticated, fetchImpl } = {}) {
    this.baseUrl = baseUrl;
    this.getToken = getToken || (() => null);
    this.onUnauthenticated = onUnauthenticated || (() => {});
    this._fetch = fetchImpl || (typeof fetch !== "undefined" ? fetch.bind(globalThis) : null);
    if (!this._fetch) {
      throw new Error("No fetch implementation available — pass fetchImpl explicitly (e.g. in tests).");
    }
  }

  async _request(method, path, { body, query } = {}) {
    let url = this.baseUrl + path;
    if (query) {
      const qs = new URLSearchParams(
        Object.entries(query).filter(([, v]) => v !== undefined && v !== null)
      ).toString();
      if (qs) url += `?${qs}`;
    }

    const headers = { Accept: "application/json" };
    const token = this.getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";

    let response;
    try {
      response = await this._fetch(url, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch (cause) {
      throw new NetworkError(cause);
    }

    let parsed = null;
    const text = await response.text();
    if (text) {
      try {
        parsed = JSON.parse(text);
      } catch {
        parsed = { detail: text };
      }
    }

    if (!response.ok) {
      const error = new ApiError(response.status, parsed);
      if (response.status === 401) this.onUnauthenticated();
      throw error;
    }
    return parsed;
  }

  get(path, query) {
    return this._request("GET", path, { query });
  }
  post(path, body, query) {
    return this._request("POST", path, { body: body ?? {}, query });
  }
  put(path, body) {
    return this._request("PUT", path, { body: body ?? {} });
  }
  patch(path, body) {
    return this._request("PATCH", path, { body: body ?? {} });
  }
  delete(path) {
    return this._request("DELETE", path);
  }

  /**
   * Multipart upload — the one request this client sends that is not
   * JSON, because POST /evidence is genuinely `multipart/form-data`
   * server-side (see api/routers/evidence.py: `File(...)`/`Form(...)`
   * parameters, not a Pydantic body). Kept as its own method rather
   * than teaching `_request` a body-type branch every other call would
   * pay for; still the ONLY place besides `_request` that calls
   * `fetch`, still Bearer-authenticated the same way, still maps
   * every non-2xx response through the same ApiError/NetworkError
   * shape callers already handle everywhere else.
   */
  async _postForm(path, formData) {
    const headers = { Accept: "application/json" };
    const token = this.getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    // Deliberately no Content-Type here — the browser sets the
    // multipart boundary itself; setting it manually corrupts the body.
    let response;
    try {
      response = await this._fetch(this.baseUrl + path, { method: "POST", headers, body: formData });
    } catch (cause) {
      throw new NetworkError(cause);
    }
    let parsed = null;
    const text = await response.text();
    if (text) {
      try {
        parsed = JSON.parse(text);
      } catch {
        parsed = { detail: text };
      }
    }
    if (!response.ok) {
      const error = new ApiError(response.status, parsed);
      if (response.status === 401) this.onUnauthenticated();
      throw error;
    }
    return parsed;
  }

  // ---- Auth (src/asavexa/api/routers/auth.py) ----
  register(email, password) {
    return this.post("/auth/register", { email, password });
  }
  login(email, password) {
    return this.post("/auth/login", { email, password });
  }
  logout() {
    return this.post("/auth/logout");
  }
  me() {
    return this.get("/auth/me");
  }
  selectOrganisation(orgId) {
    return this.post("/auth/select-organisation", { org_id: orgId });
  }
  createOrganisation(name) {
    return this.post("/organisations", { name });
  }
  getOrganisationProfile() {
    return this.get("/organisation-profile");
  }
  updateOrganisationProfile(profile) {
    return this.put("/organisation-profile", profile);
  }
  myOrganisations() {
    return this.get("/organisations/mine");
  }
  listMembers(orgId) {
    return this.get(`/organisations/${orgId}/members`);
  }
  addMember(orgId, userId, role) {
    return this.post(`/organisations/${orgId}/members`, { user_id: userId, role });
  }
  changeMemberRole(orgId, userId, role) {
    return this.patch(`/organisations/${orgId}/members/${userId}/role`, { role });
  }
  revokeMember(orgId, userId) {
    return this.delete(`/organisations/${orgId}/members/${userId}`);
  }

  // ---- Accounting (accounts.py, periods.py, journals.py) ----
  createAccount(body) {
    return this.post("/accounts", body);
  }
  listAccounts() {
    return this.get("/accounts");
  }
  getLedger(accountId, periodId) {
    return this.get(`/accounts/${accountId}/ledger`, { period_id: periodId });
  }
  openPeriod(body) {
    return this.post("/periods", body);
  }
  listPeriods() {
    return this.get("/periods");
  }
  lockPeriod(periodId, reason) {
    return this.post(`/periods/${periodId}/lock`, { reason });
  }
  getTrialBalanceLegacy(periodId) {
    return this.get(`/periods/${periodId}/trial-balance`);
  }
  createDraftJournal(body) {
    return this.post("/journals", body);
  }
  listJournals(query) {
    return this.get("/journals", query);
  }
  getJournal(journalId) {
    return this.get(`/journals/${journalId}`);
  }
  postJournal(journalId) {
    return this.post(`/journals/${journalId}/post`);
  }
  reverseJournal(journalId, reason) {
    return this.post(`/journals/${journalId}/reverse`, { reason });
  }
  journalAuditTrail(journalId) {
    return this.get(`/journals/${journalId}/audit-trail`);
  }

  // ---- Evidence (evidence.py) ----
  /**
   * `file` must be a real File/Blob (a browser File object from an
   * <input type="file">, or an equivalent Blob in tests) — this method
   * never accepts or fabricates raw bytes/base64 of its own; the
   * browser computes the real multipart body from it. `type` must be
   * one of evidence.domain.enums.EvidenceType's real values.
   */
  uploadEvidence({ file, type, linkedJournalId, linkedTransactionRef, allowDuplicate }) {
    const form = new FormData();
    form.append("file", file);
    form.append("type", type);
    if (linkedJournalId) form.append("linked_journal_id", linkedJournalId);
    if (linkedTransactionRef) form.append("linked_transaction_ref", linkedTransactionRef);
    if (allowDuplicate) form.append("allow_duplicate", "true");
    return this._postForm("/evidence", form);
  }
  listEvidence(query) {
    return this.get("/evidence", query);
  }
  evidenceStatus(journalId, transactionRef) {
    return this.get("/evidence/status", { journal_id: journalId, transaction_ref: transactionRef });
  }
  getEvidence(evidenceId) {
    return this.get(`/evidence/${evidenceId}`);
  }
  verifyEvidence(evidenceId) {
    return this.post(`/evidence/${evidenceId}/verify`);
  }
  rejectEvidence(evidenceId, reason) {
    return this.post(`/evidence/${evidenceId}/reject`, { reason });
  }

  // ---- Reconciliation (reconciliation.py) ----
  createReconciliation(body) {
    return this.post("/reconciliations", body);
  }
  listReconciliations(query) {
    return this.get("/reconciliations", query);
  }
  getReconciliation(id) {
    return this.get(`/reconciliations/${id}`);
  }
  importTransactions(reconciliationId, rows) {
    return this.post(`/reconciliations/${reconciliationId}/transactions`, { rows });
  }
  listReconciliationTransactions(reconciliationId) {
    return this.get(`/reconciliations/${reconciliationId}/transactions`);
  }
  submitReconciliation(id) {
    return this.post(`/reconciliations/${id}/submit`);
  }
  approveReconciliation(id) {
    return this.post(`/reconciliations/${id}/approve`);
  }
  rejectReconciliation(id, reason) {
    return this.post(`/reconciliations/${id}/reject`, { reason });
  }
  /** Attaches an evidence id already returned by uploadEvidence() —
   * this endpoint never accepts a file itself (see
   * api/routers/reconciliation.py's own docstring). */
  attachEvidenceToReconciliation(reconciliationId, evidenceId) {
    return this.post(`/reconciliations/${reconciliationId}/evidence`, { evidence_id: evidenceId });
  }
  getTransaction(transactionId) {
    return this.get(`/reconciliations/transactions/${transactionId}`);
  }
  manualMatch(transactionId, journalId) {
    return this.post(`/reconciliations/transactions/${transactionId}/manual-match`, { journal_id: journalId });
  }
  rejectMatch(transactionId, reason) {
    return this.post(`/reconciliations/transactions/${transactionId}/reject-match`, { reason });
  }
  approveTransaction(transactionId) {
    return this.post(`/reconciliations/transactions/${transactionId}/approve`);
  }

  // ---- Reporting (reporting.py — all GET, all read-only, all
  //      authoritative-value passthrough; see "no parallel accounting
  //      engine" in docs/frontend-runtime-verification.md) ----
  trialBalance(periodId) {
    return this.get("/reports/trial-balance", { period_id: periodId });
  }
  incomeStatement(periodId) {
    return this.get("/reports/income-statement", { period_id: periodId });
  }
  balanceSheet(periodId) {
    return this.get("/reports/balance-sheet", { period_id: periodId });
  }
  generalLedger(periodId, accountId) {
    return this.get("/reports/general-ledger", { period_id: periodId, account_id: accountId });
  }
  traceLine(accountId, periodId) {
    return this.get("/reports/trace", { account_id: accountId, period_id: periodId });
  }
  reconciliationSummary(bankAccountId) {
    return this.get("/reports/reconciliation-summary", { bank_account_id: bankAccountId });
  }
  /** Phase 1 "evidence completeness score" — see
   * src/asavexa/api/routers/reporting.py's /reports/evidence-completeness. */
  evidenceCompleteness(accountId, periodId) {
    return this.get("/reports/evidence-completeness", { account_id: accountId, period_id: periodId });
  }

  // ---- Audit (audit.py — generic, entity-agnostic audit-event feed;
  //      journalAuditTrail() above is the Journal-specific equivalent
  //      and predates this) ----
  entityAuditTrail(entityType, entityId) {
    return this.get(`/audit/entity/${entityType}/${entityId}`);
  }

  // ---- Period Close (period_close.py) ----
  checkCloseReadiness(periodId, requiredEvidenceRefs) {
    return this.post(`/period-close/periods/${periodId}/readiness`, { required_evidence_refs: requiredEvidenceRefs });
  }
  requestClose(periodId, requiredEvidenceRefs) {
    return this.post(`/period-close/periods/${periodId}/request`, { required_evidence_refs: requiredEvidenceRefs });
  }
  activeCloseProcess(periodId) {
    return this.get(`/period-close/periods/${periodId}/active`);
  }
  listCloseProcesses(periodId) {
    return this.get(`/period-close/periods/${periodId}/processes`);
  }
  getCloseProcess(processId) {
    return this.get(`/period-close/processes/${processId}`);
  }
  recheckCloseControls(processId, requiredEvidenceRefs) {
    return this.post(`/period-close/processes/${processId}/recheck`, { required_evidence_refs: requiredEvidenceRefs });
  }
  reviewClose(processId) {
    return this.post(`/period-close/processes/${processId}/review`);
  }
  approveClose(processId, reason) {
    return this.post(`/period-close/processes/${processId}/approve`, { reason });
  }
  rejectClose(processId, reason) {
    return this.post(`/period-close/processes/${processId}/reject`, { reason });
  }

  // ---- Controls & Compliance (compliance.py) ----
  defineControl(body) {
    return this.post("/compliance/controls", body);
  }
  seedStandardControls() {
    return this.post("/compliance/controls/seed-standard");
  }
  deactivateControl(controlId) {
    return this.post(`/compliance/controls/${controlId}/deactivate`);
  }
  listControls(activeOnly) {
    return this.get("/compliance/controls", { active_only: activeOnly });
  }
  getControl(controlId) {
    return this.get(`/compliance/controls/${controlId}`);
  }
  executeControl(controlId, periodId, params) {
    return this.post(`/compliance/controls/${controlId}/execute`, { period_id: periodId, params: params ?? {} });
  }
  reviewExecution(executionId) {
    return this.post(`/compliance/executions/${executionId}/review`);
  }
  getExecution(executionId) {
    return this.get(`/compliance/executions/${executionId}`);
  }
  listExecutions(periodId) {
    return this.get("/compliance/executions", { period_id: periodId });
  }
  createFindingFromExecution(executionId, description) {
    return this.post(`/compliance/executions/${executionId}/create-finding`, { description });
  }
  listFindings(status) {
    return this.get("/compliance/findings", { status });
  }
  getFinding(findingId) {
    return this.get(`/compliance/findings/${findingId}`);
  }
  startFindingReview(findingId) {
    return this.post(`/compliance/findings/${findingId}/start-review`);
  }
  sendFindingBackToOpen(findingId, reason) {
    return this.post(`/compliance/findings/${findingId}/send-back-to-open`, { reason });
  }
  markRemediationRequired(findingId, reason) {
    return this.post(`/compliance/findings/${findingId}/mark-remediation-required`, { reason });
  }
  markResolvedWithoutRemediation(findingId, reason) {
    return this.post(`/compliance/findings/${findingId}/mark-resolved-without-remediation`, { reason });
  }
  reopenFinding(findingId, reason) {
    return this.post(`/compliance/findings/${findingId}/reopen`, { reason });
  }
  closeFinding(findingId) {
    return this.post(`/compliance/findings/${findingId}/close`);
  }
  createRemediation(findingId, action, owner, dueDate) {
    return this.post(`/compliance/findings/${findingId}/remediations`, { action, owner, due_date: dueDate });
  }
  getRemediation(remediationId) {
    return this.get(`/compliance/remediations/${remediationId}`);
  }
  startRemediation(remediationId) {
    return this.post(`/compliance/remediations/${remediationId}/start`);
  }
  completeRemediation(remediationId, completionEvidenceRef) {
    return this.post(`/compliance/remediations/${remediationId}/complete`, { completion_evidence_ref: completionEvidenceRef });
  }
  verifyRemediation(remediationId, note) {
    return this.post(`/compliance/remediations/${remediationId}/verify`, { note });
  }
  rejectRemediation(remediationId, reason) {
    return this.post(`/compliance/remediations/${remediationId}/reject`, { reason });
  }

  // ---- Health (main.py) ----
  health() {
    return this.get("/health");
  }
  ready() {
    return this.get("/ready");
  }
}
