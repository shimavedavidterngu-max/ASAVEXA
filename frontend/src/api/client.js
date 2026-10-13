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
  constructor(status, body, path) {
    super(ApiError.describe(status, body, path));
    this.name = "ApiError";
    this.status = status;
    this.body = body;
    this.path = path;
    this.requestId = (body && body.request_id) || null;
  }

  /** The server's own explanation, as one readable sentence — including
   * FastAPI's 422 validation lists, which would otherwise print as
   * "[object Object]". */
  static serverDetail(body) {
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
    return (body && body.message) || "";
  }

  /** One clear message per kind of failure. A real HTTP response is
   * never described as a connection problem. Login/registration 401s
   * keep the server's own wording (wrong password is not an expired
   * session). */
  static describe(status, body, path) {
    const server = ApiError.serverDetail(body);
    const isAuthCall = typeof path === "string" && path.startsWith("/auth/") && !path.startsWith("/auth/select");
    const join = (friendly) => (server && !friendly.includes(server) ? `${friendly} ${server}` : friendly);
    if (status === 401) return isAuthCall && server ? server : "Your session has expired. Please sign in again.";
    // A shared-passport recipient is not an ASAVEXA user, so "you do not have permission" is the
    // wrong thing to tell them: the server's own wording (wrong code, link locked...) is the message.
    if (status === 403 && server && typeof path === "string" && path.startsWith("/shared-passport")) return server;
    if (status === 403) return join("You do not have permission to perform this action.");
    if (status === 404) return server ? server : "The requested ASAVEXA resource was not found.";
    if (status === 422) return join("The submitted data is invalid.");
    if (status >= 500) {
      const ref = body && body.request_id ? ` (reference ${body.request_id})` : "";
      return `ASAVEXA encountered a server error while processing this request.${ref}`;
    }
    return server || `Request failed (${status})`;
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
  /** `diagnosis`: "offline" | "cors" | "unreachable" (see ApiClient._diagnose). */
  constructor(cause, { diagnosis = "unreachable", origin = null, url = null } = {}) {
    let message = "Unable to connect to the ASAVEXA API. Please check the API service.";
    if (diagnosis === "offline") message = "Your device appears to be offline. Please check your internet connection.";
    if (diagnosis === "cors") {
      message = `The ASAVEXA API is running but is refusing requests from this website${origin ? ` (${origin})` : ""}. ` +
        "Add this address to CORS_ALLOWED_ORIGINS on the API service and redeploy it.";
    }
    super(message);
    this.name = "NetworkError";
    this.cause = cause;
    this.diagnosis = diagnosis;
    this.url = url;
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

  async _request(method, path, { body, query, token: tokenOverride } = {}) {
    let url = this.baseUrl + path;
    if (query) {
      const qs = new URLSearchParams(
        Object.entries(query).filter(([, v]) => v !== undefined && v !== null)
      ).toString();
      if (qs) url += `?${qs}`;
    }

    const headers = { Accept: "application/json" };
    // `token: null` = send no credentials at all; a string = use that bearer instead of the
    // organisation login. Shared-passport recipients are not ASAVEXA users: they must never
    // present, or be able to clear, an organisation session.
    const overridden = tokenOverride !== undefined;
    const token = overridden ? tokenOverride : this.getToken();
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
      throw await this._networkError(cause, url);
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
      const error = new ApiError(response.status, parsed, path);
      if (response.status === 401 && !overridden) this.onUnauthenticated();
      throw error;
    }
    return parsed;
  }

  /** A browser reports every failed fetch the same way ("Failed to
   * fetch"): server down, DNS, or a CORS refusal. Tell them apart with a
   * second, deliberately CORS-exempt probe (mode: "no-cors"): it
   * succeeds (opaque response) whenever the server answers at all. So
   * "normal request failed but the no-cors probe worked" means the API
   * is up and is refusing this website's origin. */
  async _networkError(cause, url) {
    const origin = typeof location !== "undefined" ? location.origin : null;
    const info = { diagnosis: "unreachable", origin, url };
    try {
      if (typeof navigator !== "undefined" && navigator.onLine === false) {
        info.diagnosis = "offline";
      } else {
        const ctl = typeof AbortController !== "undefined" ? new AbortController() : null;
        const timer = ctl ? setTimeout(() => ctl.abort(), 8000) : null;
        try {
          await this._fetch(this.baseUrl + "/health", { mode: "no-cors", signal: ctl ? ctl.signal : undefined });
          info.diagnosis = "cors";
        } finally {
          if (timer) clearTimeout(timer);
        }
      }
    } catch {
      // probe failed too: genuinely unreachable
    }
    if (typeof console !== "undefined") console.error("[ASAVEXA] request failed before any response", info, cause);
    return new NetworkError(cause, info);
  }

  /** Unauthenticated, uncooked GET for the Diagnostics page: returns
   * status/body instead of throwing on non-2xx. */
  async rawGet(path) {
    const started = Date.now();
    try {
      const response = await this._fetch(this.baseUrl + path, { headers: { Accept: "application/json" } });
      const text = await response.text();
      let body = text;
      try { body = JSON.parse(text); } catch { /* keep text */ }
      return { ok: response.ok, status: response.status, body, ms: Date.now() - started };
    } catch (cause) {
      const err = await this._networkError(cause, this.baseUrl + path);
      return { ok: false, status: 0, body: null, ms: Date.now() - started, error: err };
    }
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
      throw await this._networkError(cause, this.baseUrl + path);
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
      const error = new ApiError(response.status, parsed, path);
      if (response.status === 401) this.onUnauthenticated();
      throw error;
    }
    return parsed;
  }

  // ---- Auth (src/asavexa/api/routers/auth.py) ----
  register(email, password, confirm) {
    return this.post("/auth/register", confirm === undefined ? { email, password } : { email, password, confirm_password: confirm });
  }
  // Password recovery. The server answers the same way whether or not an account exists for the email.
  recoveryStatus() { return this.get("/auth/recovery/status"); }
  recoveryRequest(email) { return this.post("/auth/recovery/request", { email }); }
  recoveryVerify(email, code) { return this.post("/auth/recovery/verify", { email, code }); }
  recoveryReset(email, resetToken, newPassword, confirm) { return this.post("/auth/recovery/reset", { email, reset_token: resetToken, new_password: newPassword, confirm_password: confirm }); }
  // Email verification at sign-up. The server answers the same way whether or not an account exists for the email.
  verificationStatus() { return this.get("/auth/verification/status"); }
  verificationRequest(email) { return this.post("/auth/verification/request", { email }); }
  verificationConfirm(email, code) { return this.post("/auth/verification/confirm", { email, code }); }
  login(email, password) {
    return this.post("/auth/login", { email, password });
  }
  /** Second step of sign-in for accounts with multi-factor on: the challenge from login() plus the 6-digit (or recovery) code. */
  verifyMfa(challenge, code) {
    return this.post("/auth/mfa/verify", { challenge, code });
  }
  oidcConfig() {
    return this.get("/auth/oidc/config");
  }
  oidcStart(binding) {
    return this.post("/auth/oidc/start", { binding });
  }
  oidcCallback(code, state, binding) {
    return this.post("/auth/oidc/callback", { code, state, binding });
  }
  logout() {
    return this.post("/auth/logout");
  }

  // ---- Security & infrastructure (src/asavexa/api/routers/security.py) ----
  mySecurity() { return this.get("/security/me"); }
  mfaBegin() { return this.post("/security/me/mfa/begin"); }
  mfaConfirm(code) { return this.post("/security/me/mfa/confirm", { code }); }
  mfaDisable(code) { return this.post("/security/me/mfa/disable", { code }); }
  mfaRecoveryCodes(code) { return this.post("/security/me/mfa/recovery-codes", { code }); }
  revokeSession(id) { return this.delete(`/security/me/sessions/${encodeURIComponent(id)}`); }
  revokeOtherSessions() { return this.post("/security/me/sessions/revoke-others"); }
  exportMyData() { return this.get("/security/me/export"); }
  requestErasure() { return this.post("/security/me/erasure-request"); }
  securityOverview() { return this.get("/security/overview"); }
  securityMembers() { return this.get("/security/members"); }
  updateSecuritySettings(body) { return this.put("/security/settings", body); }
  rotateKeys(toKeyId) { return this.post("/security/keys/rotate", { to_key_id: toKeyId || null }); }
  verifyAuditChain() { return this.get("/security/audit/verify"); }
  securityHealth() { return this.get("/security/health"); }
  listSecurityAlerts(status) { return this.get("/security/alerts", status ? { status } : undefined); }
  refreshSecurityAlerts() { return this.post("/security/alerts/refresh"); }
  acknowledgeAlert(id, note) { return this.post(`/security/alerts/${encodeURIComponent(id)}/acknowledge`, { note }); }
  getRetention() { return this.get("/security/retention"); }
  setRetention(evidenceDays) { return this.put("/security/retention", { evidence_days: evidenceDays }); }
  placeHold(reason, evidenceId) { return this.post("/security/retention/holds", { reason, evidence_id: evidenceId || null }); }
  releaseHold(id) { return this.post(`/security/retention/holds/${encodeURIComponent(id)}/release`); }
  disposeEvidence(id, reason) { return this.post(`/security/retention/dispose/${encodeURIComponent(id)}`, { reason }); }
  privacyRequests() { return this.get("/security/privacy/requests"); }
  decidePrivacyRequest(id, approve, note) { return this.post(`/security/privacy/requests/${encodeURIComponent(id)}/decide`, { approve, note: note || "" }); }
  residencyReport() { return this.get("/security/residency"); }
  listVendors() { return this.get("/security/vendors"); }
  addVendor(v) { return this.post("/security/vendors", v); }
  updateVendor(id, v) { return this.put(`/security/vendors/${encodeURIComponent(id)}`, v); }
  seedVendors() { return this.post("/security/vendors/seed"); }
  evidenceStorage(id) { return this.get(`/evidence/${encodeURIComponent(id)}/storage`); }

  // ---- Professional validation (src/asavexa/api/routers/validation.py) ----
  validationGuide() { return this.get("/validation/guide"); }
  validationMe() { return this.get("/validation/me"); }
  validationPanel() { return this.get("/validation/panel"); }
  addReviewer(body) { return this.post("/validation/panel", body); }
  updateReviewer(id, body) { return this.put(`/validation/panel/${encodeURIComponent(id)}`, body); }
  verifyCredential(id, index, body) { return this.post(`/validation/panel/${encodeURIComponent(id)}/credentials/${encodeURIComponent(index)}/verify`, body); }
  setReviewerActive(id, active) { return this.post(`/validation/panel/${encodeURIComponent(id)}/${active ? "activate" : "deactivate"}`); }
  listEngagements() { return this.get("/validation/engagements"); }
  createEngagement(body) { return this.post("/validation/engagements", body); }
  getEngagement(id) { return this.get(`/validation/engagements/${encodeURIComponent(id)}`); }
  openEngagement(id) { return this.post(`/validation/engagements/${encodeURIComponent(id)}/open`); }
  withdrawEngagement(id, reason) { return this.post(`/validation/engagements/${encodeURIComponent(id)}/withdraw`, { reason }); }
  refreshEngagementSnapshot(id) { return this.post(`/validation/engagements/${encodeURIComponent(id)}/refresh-snapshot`); }
  assignReviewer(id, stage, reviewerId) { return this.post(`/validation/engagements/${encodeURIComponent(id)}/assignments`, { stage, reviewer_id: reviewerId }); }
  unassignReviewer(id, assignmentId) { return this.delete(`/validation/engagements/${encodeURIComponent(id)}/assignments/${encodeURIComponent(assignmentId)}`); }
  declareIndependence(id, body) { return this.post(`/validation/engagements/${encodeURIComponent(id)}/declarations`, body); }
  saveReview(id, body) { return this.post(`/validation/engagements/${encodeURIComponent(id)}/reviews`, body); }
  signReview(id, reviewId) { return this.post(`/validation/engagements/${encodeURIComponent(id)}/reviews/${encodeURIComponent(reviewId)}/sign`); }
  respondToObservation(id, reviewId, observationId, status, note) {
    return this.post(`/validation/engagements/${encodeURIComponent(id)}/reviews/${encodeURIComponent(reviewId)}/observations/${encodeURIComponent(observationId)}/response`, { status, note });
  }
  completeEngagement(id) { return this.post(`/validation/engagements/${encodeURIComponent(id)}/complete`); }
  validationStatement(id) { return this.get(`/validation/engagements/${encodeURIComponent(id)}/statement`); }

  // ---- Evidence Review (src/asavexa/api/routers/evidence_review.py) ----
  evidenceReview(periodId, report, accountId) { return this.get("/evidence-review/review", accountId ? { period_id: periodId, report, account_id: accountId } : { period_id: periodId, report }); }
  evidenceReviewCases() { return this.get("/evidence-review/cases"); }
  evidenceReviewCase(id) { return this.get(`/evidence-review/cases/${id}`); }
  openEvidenceReviewCase(body) { return this.post("/evidence-review/cases", body); }
  planEvidenceReviewAction(id, body) { return this.post(`/evidence-review/cases/${id}/plan`, body); }
  completeEvidenceReviewAction(id, body) { return this.post(`/evidence-review/cases/${id}/complete`, body); }
  verifyEvidenceReviewOutcome(id, body) { return this.post(`/evidence-review/cases/${id}/verify`, body); }
  recheckEvidenceReviewCase(id) { return this.post(`/evidence-review/cases/${id}/recheck`, {}); }

  // ---- Proof-to-Report Graph (src/asavexa/api/routers/proof.py) ----
  proofGraph(periodId, report) { return this.get("/proof/graph", { period_id: periodId, report }); }
  proofArchitecture() { return this.get("/proof/architecture"); }

  // ---- Professional workspaces + Financial Analysis (src/asavexa/api/routers/{workspaces,analysis}.py) ----
  workspaces() { return this.get("/workspaces"); }
  analysisOverview(periodId) { return this.get("/analysis/overview", { period_id: periodId }); }
  analysisRatios(periodId) { return this.get("/analysis/ratios", { period_id: periodId }); }
  analysisVariance(periodId) { return this.get("/analysis/variance", { period_id: periodId }); }
  analysisConfig() { return this.get("/analysis/config"); }
  saveAnalysisConfig(body) { return this.put("/analysis/config", body); }
  analysisBudget(periodId) { return this.get("/analysis/budget", { period_id: periodId }); }
  saveAnalysisBudget(body) { return this.put("/analysis/budget", body); }
  analysisBudgetVariance(periodId) { return this.get("/analysis/budget-variance", { period_id: periodId }); }
  addAnalysisComment(body) { return this.post("/analysis/commentary", body); }
  analysisSuggest(periodId) { return this.get("/analysis/suggest", { period_id: periodId }); }
  analysisScenarios(periodId) { return this.get("/analysis/scenarios", { period_id: periodId }); }
  saveAnalysisScenario(body, id) { return id ? this.put(`/analysis/scenarios/${encodeURIComponent(id)}`, body) : this.post("/analysis/scenarios", body); }
  runAnalysisScenario(id) { return this.get(`/analysis/scenarios/${encodeURIComponent(id)}/run`); }
  analysisBreakeven(body) { return this.post("/analysis/breakeven", body); }
  analysisReports() { return this.get("/analysis/reports"); }
  createAnalysisReport(body) { return this.post("/analysis/reports", body); }
  analysisReport(id) { return this.get(`/analysis/reports/${encodeURIComponent(id)}`); }
  submitAnalysisReport(id) { return this.post(`/analysis/reports/${encodeURIComponent(id)}/submit`); }
  approveAnalysisReport(id, note) { return this.post(`/analysis/reports/${encodeURIComponent(id)}/approve`, { note: note || "" }); }
  rejectAnalysisReport(id, note) { return this.post(`/analysis/reports/${encodeURIComponent(id)}/reject`, { note: note || "" }); }
  verifyAnalysisReport(id) { return this.get(`/analysis/reports/${encodeURIComponent(id)}/verify`); }
  /** The approved report as a CSV Blob (needs the Authorization header, so it cannot be a plain link). */
  async exportAnalysisReport(id) {
    const token = this.getToken();
    const url = `${this.baseUrl}/analysis/reports/${encodeURIComponent(id)}/export`;
    let response;
    try {
      response = await this._fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    } catch (cause) {
      throw await this._networkError(cause, url);
    }
    if (!response.ok) {
      let body = null;
      try { body = JSON.parse(await response.text()); } catch { /* keep null */ }
      throw new ApiError(response.status, body, `/analysis/reports/${id}/export`);
    }
    return { blob: await response.blob(), filename: (/filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") || "") || [])[1] || "analysis.csv" };
  }

  // ---- Forensic Accounting (src/asavexa/api/routers/forensic.py) ----
  forensicOptions() { return this.get("/forensic/options"); }
  forensicCases() { return this.get("/forensic/cases"); }
  createForensicCase(body) { return this.post("/forensic/cases", body); }
  forensicCase(id) { return this.get(`/forensic/cases/${encodeURIComponent(id)}`); }
  closeForensicCase(id, note) { return this.post(`/forensic/cases/${encodeURIComponent(id)}/close`, { note: note || "" }); }
  addForensicEvidence(id, body) { return this.post(`/forensic/cases/${encodeURIComponent(id)}/evidence`, body); }
  forensicCustody(id) { return this.get(`/forensic/cases/${encodeURIComponent(id)}/custody`); }
  runForensicAnalytics(id, body) { return this.post(`/forensic/cases/${encodeURIComponent(id)}/analytics`, body); }
  forensicRun(id) { return this.get(`/forensic/runs/${encodeURIComponent(id)}`); }
  createForensicFinding(caseId, body) { return this.post(`/forensic/cases/${encodeURIComponent(caseId)}/findings`, body); }
  updateForensicFinding(id, body) { return this.put(`/forensic/findings/${encodeURIComponent(id)}`, body); }
  discardForensicFinding(id) { return this.delete(`/forensic/findings/${encodeURIComponent(id)}`); }
  submitForensicFinding(id) { return this.post(`/forensic/findings/${encodeURIComponent(id)}/submit`); }
  approveForensicFinding(id, note) { return this.post(`/forensic/findings/${encodeURIComponent(id)}/approve`, { note: note || "" }); }
  rejectForensicFinding(id, note) { return this.post(`/forensic/findings/${encodeURIComponent(id)}/reject`, { note: note || "" }); }
  createForensicReport(caseId, title) { return this.post(`/forensic/cases/${encodeURIComponent(caseId)}/reports`, { title }); }
  forensicReport(id) { return this.get(`/forensic/reports/${encodeURIComponent(id)}`); }
  submitForensicReport(id) { return this.post(`/forensic/reports/${encodeURIComponent(id)}/submit`); }
  approveForensicReport(id, note) { return this.post(`/forensic/reports/${encodeURIComponent(id)}/approve`, { note: note || "" }); }
  rejectForensicReport(id, note) { return this.post(`/forensic/reports/${encodeURIComponent(id)}/reject`, { note: note || "" }); }
  async exportForensicReport(id) {
    const token = this.getToken();
    const url = `${this.baseUrl}/forensic/reports/${encodeURIComponent(id)}/export`;
    let response;
    try {
      response = await this._fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    } catch (cause) {
      throw await this._networkError(cause, url);
    }
    if (!response.ok) {
      let body = null;
      try { body = JSON.parse(await response.text()); } catch { /* keep null */ }
      throw new ApiError(response.status, body, `/forensic/reports/${id}/export`);
    }
    return { blob: await response.blob(), filename: (/filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") || "") || [])[1] || "forensic-report.csv" };
  }

  // ---- Governance, Risk and Compliance (src/asavexa/api/routers/grc.py) ----
  grcOptions() { return this.get("/grc/options"); }
  grcDashboard() { return this.get("/grc/dashboard"); }
  setGrcAppetite(appetite) { return this.put("/grc/appetite", { appetite }); }
  grcRisks(status, category) { return this.get("/grc/risks", { status: status || undefined, category: category || undefined }); }
  createGrcRisk(body) { return this.post("/grc/risks", body); }
  grcRisk(id) { return this.get(`/grc/risks/${encodeURIComponent(id)}`); }
  updateGrcRisk(id, body) { return this.put(`/grc/risks/${encodeURIComponent(id)}`, body); }
  treatGrcRisk(id) { return this.post(`/grc/risks/${encodeURIComponent(id)}/treat`); }
  acceptGrcRisk(id, body) { return this.post(`/grc/risks/${encodeURIComponent(id)}/accept`, body); }
  approveGrcAcceptance(id, note) { return this.post(`/grc/risks/${encodeURIComponent(id)}/approve-acceptance`, { note: note || "" }); }
  rejectGrcAcceptance(id, note) { return this.post(`/grc/risks/${encodeURIComponent(id)}/reject-acceptance`, { note: note || "" }); }
  reopenGrcRisk(id, note) { return this.post(`/grc/risks/${encodeURIComponent(id)}/reopen`, { note: note || "" }); }
  closeGrcRisk(id, note) { return this.post(`/grc/risks/${encodeURIComponent(id)}/close`, { note: note || "" }); }
  grcActions(riskId, status) { return this.get("/grc/actions", { risk_id: riskId || undefined, status: status || undefined }); }
  createGrcAction(body) { return this.post("/grc/actions", body); }
  updateGrcAction(id, body) { return this.put(`/grc/actions/${encodeURIComponent(id)}`, body); }
  completeGrcAction(id, body) { return this.post(`/grc/actions/${encodeURIComponent(id)}/complete`, body); }
  verifyGrcAction(id, note) { return this.post(`/grc/actions/${encodeURIComponent(id)}/verify`, { note: note || "" }); }
  sendBackGrcAction(id, note) { return this.post(`/grc/actions/${encodeURIComponent(id)}/send-back`, { note: note || "" }); }
  cancelGrcAction(id, note) { return this.post(`/grc/actions/${encodeURIComponent(id)}/cancel`, { note: note || "" }); }
  grcObligations(state) { return this.get("/grc/obligations", { state: state || undefined }); }
  createGrcObligation(body) { return this.post("/grc/obligations", body); }
  updateGrcObligation(id, body) { return this.put(`/grc/obligations/${encodeURIComponent(id)}`, body); }
  markGrcObligationMet(id, body) { return this.post(`/grc/obligations/${encodeURIComponent(id)}/met`, body); }
  retireGrcObligation(id, note) { return this.post(`/grc/obligations/${encodeURIComponent(id)}/retire`, { note: note || "" }); }
  async exportGrcRegister() {
    const token = this.getToken();
    const url = `${this.baseUrl}/grc/export`;
    let response;
    try {
      response = await this._fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    } catch (cause) {
      throw await this._networkError(cause, url);
    }
    if (!response.ok) {
      let body = null;
      try { body = JSON.parse(await response.text()); } catch { /* keep null */ }
      throw new ApiError(response.status, body, "/grc/export");
    }
    return { blob: await response.blob(), filename: (/filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") || "") || [])[1] || "asavexa-grc-register.csv" };
  }

  // ---- Public Finance (src/asavexa/api/routers/pubfin.py) ----
  pubfinOptions() { return this.get("/pubfin/options"); }
  pubfinOverview() { return this.get("/pubfin/overview"); }
  setPubfinPolicy(body) { return this.put("/pubfin/policy", body); }
  pubfinBudgets() { return this.get("/pubfin/budgets"); }
  createPubfinBudget(body) { return this.post("/pubfin/budgets", body); }
  pubfinBudget(id) { return this.get(`/pubfin/budgets/${encodeURIComponent(id)}`); }
  updatePubfinBudget(id, body) { return this.put(`/pubfin/budgets/${encodeURIComponent(id)}`, body); }
  discardPubfinBudget(id) { return this.delete(`/pubfin/budgets/${encodeURIComponent(id)}`); }
  submitPubfinBudget(id) { return this.post(`/pubfin/budgets/${encodeURIComponent(id)}/submit`); }
  approvePubfinBudget(id, note) { return this.post(`/pubfin/budgets/${encodeURIComponent(id)}/approve`, { note: note || "" }); }
  rejectPubfinBudget(id, note) { return this.post(`/pubfin/budgets/${encodeURIComponent(id)}/reject`, { note: note || "" }); }
  closePubfinBudget(id, note) { return this.post(`/pubfin/budgets/${encodeURIComponent(id)}/close`, { note: note || "" }); }
  proposePubfinVirement(id, body) { return this.post(`/pubfin/budgets/${encodeURIComponent(id)}/virements`, body); }
  approvePubfinVirement(id, vid, note) { return this.post(`/pubfin/budgets/${encodeURIComponent(id)}/virements/${encodeURIComponent(vid)}/approve`, { note: note || "" }); }
  rejectPubfinVirement(id, vid, note) { return this.post(`/pubfin/budgets/${encodeURIComponent(id)}/virements/${encodeURIComponent(vid)}/reject`, { note: note || "" }); }
  pubfinCommitments(budgetId, status) { return this.get("/pubfin/commitments", { budget_id: budgetId || undefined, status: status || undefined }); }
  createPubfinCommitment(body) { return this.post("/pubfin/commitments", body); }
  settlePubfinCommitment(id, body) { return this.post(`/pubfin/commitments/${encodeURIComponent(id)}/settle`, body); }
  cancelPubfinCommitment(id, note) { return this.post(`/pubfin/commitments/${encodeURIComponent(id)}/cancel`, { note: note || "" }); }
  pubfinProcurements() { return this.get("/pubfin/procurements"); }
  createPubfinProcurement(body) { return this.post("/pubfin/procurements", body); }
  pubfinProcurement(id) { return this.get(`/pubfin/procurements/${encodeURIComponent(id)}`); }
  addPubfinQuote(id, body) { return this.post(`/pubfin/procurements/${encodeURIComponent(id)}/quotes`, body); }
  proposePubfinAward(id, body) { return this.post(`/pubfin/procurements/${encodeURIComponent(id)}/award`, body); }
  approvePubfinAward(id, note) { return this.post(`/pubfin/procurements/${encodeURIComponent(id)}/approve-award`, { note: note || "" }); }
  rejectPubfinAward(id, note) { return this.post(`/pubfin/procurements/${encodeURIComponent(id)}/reject-award`, { note: note || "" }); }
  cancelPubfinProcurement(id, note) { return this.post(`/pubfin/procurements/${encodeURIComponent(id)}/cancel`, { note: note || "" }); }
  pubfinGrants() { return this.get("/pubfin/grants"); }
  createPubfinGrant(body) { return this.post("/pubfin/grants", body); }
  pubfinGrant(id) { return this.get(`/pubfin/grants/${encodeURIComponent(id)}`); }
  recordPubfinReceipt(id, body) { return this.post(`/pubfin/grants/${encodeURIComponent(id)}/receipts`, body); }
  addPubfinSpend(id, body) { return this.post(`/pubfin/grants/${encodeURIComponent(id)}/spend`, body); }
  approvePubfinSpend(id, sid, note) { return this.post(`/pubfin/grants/${encodeURIComponent(id)}/spend/${encodeURIComponent(sid)}/approve`, { note: note || "" }); }
  rejectPubfinSpend(id, sid, note) { return this.post(`/pubfin/grants/${encodeURIComponent(id)}/spend/${encodeURIComponent(sid)}/reject`, { note: note || "" }); }
  closePubfinGrant(id, note) { return this.post(`/pubfin/grants/${encodeURIComponent(id)}/close`, { note: note || "" }); }
  pubfinReports() { return this.get("/pubfin/reports"); }
  createPubfinReport(body) { return this.post("/pubfin/reports", body); }
  pubfinReport(id) { return this.get(`/pubfin/reports/${encodeURIComponent(id)}`); }
  submitPubfinReport(id) { return this.post(`/pubfin/reports/${encodeURIComponent(id)}/submit`); }
  approvePubfinReport(id, note) { return this.post(`/pubfin/reports/${encodeURIComponent(id)}/approve`, { note: note || "" }); }
  rejectPubfinReport(id, note) { return this.post(`/pubfin/reports/${encodeURIComponent(id)}/reject`, { note: note || "" }); }
  async exportPubfinReport(id) {
    const token = this.getToken();
    const url = `${this.baseUrl}/pubfin/reports/${encodeURIComponent(id)}/export`;
    let response;
    try {
      response = await this._fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    } catch (cause) {
      throw await this._networkError(cause, url);
    }
    if (!response.ok) {
      let body = null;
      try { body = JSON.parse(await response.text()); } catch { /* keep null */ }
      throw new ApiError(response.status, body, `/pubfin/reports/${id}/export`);
    }
    return { blob: await response.blob(), filename: (/filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") || "") || [])[1] || "accountability-report.csv" };
  }

  // ---- Business Development (src/asavexa/api/routers/bizdev.py) ----
  bdOptions() { return this.get("/bizdev/options"); }
  bdOverview() { return this.get("/bizdev/overview"); }
  setBdPolicy(body) { return this.put("/bizdev/policy", body); }
  bdAccounts() { return this.get("/bizdev/accounts"); }
  createBdAccount(body) { return this.post("/bizdev/accounts", body); }
  bdAccount(id) { return this.get(`/bizdev/accounts/${encodeURIComponent(id)}`); }
  updateBdAccount(id, body) { return this.put(`/bizdev/accounts/${encodeURIComponent(id)}`, body); }
  archiveBdAccount(id, note) { return this.post(`/bizdev/accounts/${encodeURIComponent(id)}/archive`, { note: note || "" }); }
  bdOpportunities(stage, accountId) { return this.get("/bizdev/opportunities", { stage: stage || undefined, account_id: accountId || undefined }); }
  createBdOpportunity(body) { return this.post("/bizdev/opportunities", body); }
  bdOpportunity(id) { return this.get(`/bizdev/opportunities/${encodeURIComponent(id)}`); }
  updateBdOpportunity(id, body) { return this.put(`/bizdev/opportunities/${encodeURIComponent(id)}`, body); }
  addBdActivity(id, body) { return this.post(`/bizdev/opportunities/${encodeURIComponent(id)}/activities`, body); }
  moveBdStage(id, stage, note) { return this.post(`/bizdev/opportunities/${encodeURIComponent(id)}/stage`, { stage, note: note || "" }); }
  markBdLost(id, note) { return this.post(`/bizdev/opportunities/${encodeURIComponent(id)}/lost`, { note: note || "" }); }
  requestBdWin(id, note) { return this.post(`/bizdev/opportunities/${encodeURIComponent(id)}/win/request`, { note: note || "" }); }
  approveBdWin(id, note) { return this.post(`/bizdev/opportunities/${encodeURIComponent(id)}/win/approve`, { note: note || "" }); }
  rejectBdWin(id, note) { return this.post(`/bizdev/opportunities/${encodeURIComponent(id)}/win/reject`, { note: note || "" }); }
  createBdProposal(id, body) { return this.post(`/bizdev/opportunities/${encodeURIComponent(id)}/proposals`, body); }
  updateBdProposal(id, pid, body) { return this.put(`/bizdev/opportunities/${encodeURIComponent(id)}/proposals/${encodeURIComponent(pid)}`, body); }
  bdProposalStep(id, pid, step, note) { return this.post(`/bizdev/opportunities/${encodeURIComponent(id)}/proposals/${encodeURIComponent(pid)}/${step}`, step === "submit" || step === "send" ? undefined : { note: note || "" }); }
  bdTargets() { return this.get("/bizdev/targets"); }
  createBdTarget(body) { return this.post("/bizdev/targets", body); }
  retireBdTarget(id, note) { return this.post(`/bizdev/targets/${encodeURIComponent(id)}/retire`, { note: note || "" }); }
  bdReports() { return this.get("/bizdev/reports"); }
  createBdReport(body) { return this.post("/bizdev/reports", body); }
  bdReport(id) { return this.get(`/bizdev/reports/${encodeURIComponent(id)}`); }
  submitBdReport(id) { return this.post(`/bizdev/reports/${encodeURIComponent(id)}/submit`); }
  approveBdReport(id, note) { return this.post(`/bizdev/reports/${encodeURIComponent(id)}/approve`, { note: note || "" }); }
  rejectBdReport(id, note) { return this.post(`/bizdev/reports/${encodeURIComponent(id)}/reject`, { note: note || "" }); }
  async exportBdReport(id) {
    const token = this.getToken();
    const url = `${this.baseUrl}/bizdev/reports/${encodeURIComponent(id)}/export`;
    let response;
    try {
      response = await this._fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    } catch (cause) {
      throw await this._networkError(cause, url);
    }
    if (!response.ok) {
      let body = null;
      try { body = JSON.parse(await response.text()); } catch { /* keep null */ }
      throw new ApiError(response.status, body, `/bizdev/reports/${id}/export`);
    }
    return { blob: await response.blob(), filename: (/filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") || "") || [])[1] || "pipeline-report.csv" };
  }

  // ---- Cybersecurity (src/asavexa/api/routers/cyber.py) ----
  cyOptions() { return this.get("/cyber/options"); }
  cyOverview() { return this.get("/cyber/overview"); }
  setCyPolicy(body) { return this.put("/cyber/policy", body); }
  cyAssets() { return this.get("/cyber/assets"); }
  createCyAsset(body) { return this.post("/cyber/assets", body); }
  cyAsset(id) { return this.get(`/cyber/assets/${encodeURIComponent(id)}`); }
  updateCyAsset(id, body) { return this.put(`/cyber/assets/${encodeURIComponent(id)}`, body); }
  retireCyAsset(id, note) { return this.post(`/cyber/assets/${encodeURIComponent(id)}/retire`, { note: note || "" }); }
  cyVulns(status, severity, assetId) { return this.get("/cyber/vulnerabilities", { status: status || undefined, severity: severity || undefined, asset_id: assetId || undefined }); }
  createCyVuln(body) { return this.post("/cyber/vulnerabilities", body); }
  cyVuln(id) { return this.get(`/cyber/vulnerabilities/${encodeURIComponent(id)}`); }
  cyVulnStep(id, step, body) { return this.post(`/cyber/vulnerabilities/${encodeURIComponent(id)}/${step}`, body || { note: "" }); }
  cyIncidents(status) { return this.get("/cyber/incidents", { status: status || undefined }); }
  createCyIncident(body) { return this.post("/cyber/incidents", body); }
  cyIncident(id) { return this.get(`/cyber/incidents/${encodeURIComponent(id)}`); }
  cyIncidentStep(id, step, body) { return this.post(`/cyber/incidents/${encodeURIComponent(id)}/${step}`, body || { note: "" }); }
  cyReviews() { return this.get("/cyber/reviews"); }
  createCyReview(body) { return this.post("/cyber/reviews", body); }
  cyReview(id) { return this.get(`/cyber/reviews/${encodeURIComponent(id)}`); }
  addCyEntry(id, body) { return this.post(`/cyber/reviews/${encodeURIComponent(id)}/entries`, body); }
  decideCyEntry(id, eid, decision, note) { return this.post(`/cyber/reviews/${encodeURIComponent(id)}/entries/${encodeURIComponent(eid)}/decide`, { decision, note: note || "" }); }
  confirmCyRemoved(id, eid) { return this.post(`/cyber/reviews/${encodeURIComponent(id)}/entries/${encodeURIComponent(eid)}/removed`); }
  cyReviewStep(id, step, note) { return this.post(`/cyber/reviews/${encodeURIComponent(id)}/${step}`, step === "submit" ? undefined : { note: note || "" }); }
  cyReports() { return this.get("/cyber/reports"); }
  createCyReport(body) { return this.post("/cyber/reports", body); }
  cyReport(id) { return this.get(`/cyber/reports/${encodeURIComponent(id)}`); }
  submitCyReport(id) { return this.post(`/cyber/reports/${encodeURIComponent(id)}/submit`); }
  approveCyReport(id, note) { return this.post(`/cyber/reports/${encodeURIComponent(id)}/approve`, { note: note || "" }); }
  rejectCyReport(id, note) { return this.post(`/cyber/reports/${encodeURIComponent(id)}/reject`, { note: note || "" }); }
  async exportCyReport(id) {
    const token = this.getToken();
    const url = `${this.baseUrl}/cyber/reports/${encodeURIComponent(id)}/export`;
    let response;
    try {
      response = await this._fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    } catch (cause) {
      throw await this._networkError(cause, url);
    }
    if (!response.ok) {
      let body = null;
      try { body = JSON.parse(await response.text()); } catch { /* keep null */ }
      throw new ApiError(response.status, body, `/cyber/reports/${id}/export`);
    }
    return { blob: await response.blob(), filename: (/filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") || "") || [])[1] || "posture-report.csv" };
  }

  // ---- Health Centre Administration (src/asavexa/api/routers/health.py) ----
  hcOptions() { return this.get("/health/options"); }
  hcGet(path, query) { return this.get("/health" + path, query); }
  hcPost(path, body) { return this.post("/health" + path, body); }
  hcPut(path, body) { return this.put("/health" + path, body); }
  async exportHcReport(id) {
    const token = this.getToken();
    const url = `${this.baseUrl}/health/reports/${encodeURIComponent(id)}/export`;
    let response;
    try {
      response = await this._fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    } catch (cause) {
      throw await this._networkError(cause, url);
    }
    if (!response.ok) {
      let body = null;
      try { body = JSON.parse(await response.text()); } catch { /* keep null */ }
      throw new ApiError(response.status, body, `/health/reports/${id}/export`);
    }
    return { blob: await response.blob(), filename: (/filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") || "") || [])[1] || "facility-report.csv" };
  }

  // ---- Tax Compliance (src/asavexa/api/routers/tax.py) ----
  taxOverview() { return this.get("/tax/overview"); }
  taxCountries(q, region) { return this.get("/tax/countries", { q: q || undefined, region: region || undefined }); }
  setTaxCountry(code, body) { return this.put(`/tax/countries/${encodeURIComponent(code)}`, body); }
  taxOptions() { return this.get("/tax/options"); }
  taxRules(country, status) { return this.get("/tax/rules", { country: country || undefined, status: status || undefined }); }
  createTaxRule(body) { return this.post("/tax/rules", body); }
  taxRule(id) { return this.get(`/tax/rules/${encodeURIComponent(id)}`); }
  updateTaxRule(id, body) { return this.put(`/tax/rules/${encodeURIComponent(id)}`, body); }
  discardTaxRule(id) { return this.delete(`/tax/rules/${encodeURIComponent(id)}`); }
  submitTaxRule(id) { return this.post(`/tax/rules/${encodeURIComponent(id)}/submit`); }
  approveTaxRule(id, note) { return this.post(`/tax/rules/${encodeURIComponent(id)}/approve`, { note: note || "" }); }
  rejectTaxRule(id, note) { return this.post(`/tax/rules/${encodeURIComponent(id)}/reject`, { note: note || "" }); }
  taxLedgerBase(periodId, kind) { return this.get("/tax/ledger-base", { period_id: periodId, kind }); }
  taxCalculate(body) { return this.post("/tax/calculate", body); }
  taxCalculations() { return this.get("/tax/calculations"); }
  taxCalendar(start, end) { return this.get("/tax/calendar", { start, end }); }
  markTaxFiled(body) { return this.post("/tax/filed", body); }

  // ---- ASAVEXA Network (src/asavexa/api/routers/network.py) ----
  networkGuide() { return this.get("/network/guide"); }
  networkMe() { return this.get("/network/me"); }
  setNetworkProfile(body) { return this.put("/network/profile", body); }
  networkInvites() { return this.get("/network/invites"); }
  createNetworkInvite(body) { return this.post("/network/invites", body); }
  cancelNetworkInvite(id) { return this.post(`/network/invites/${encodeURIComponent(id)}/cancel`); }
  previewNetworkInvite(code) { return this.post("/network/invites/preview", { code }); }
  acceptNetworkInvite(body) { return this.post("/network/invites/accept", body); }
  updateNetworkConnection(id, body) { return this.put(`/network/connections/${encodeURIComponent(id)}`, body); }
  endNetworkConnection(id, reason) { return this.post(`/network/connections/${encodeURIComponent(id)}/end`, { reason }); }
  networkAccessLog(id) { return this.get(`/network/connections/${encodeURIComponent(id)}/access-log`); }
  networkPassport(id) { return this.get(`/network/connections/${encodeURIComponent(id)}/passport`); }

  // ---- Real pilot (src/asavexa/api/routers/pilot.py) ----
  pilotGuide() { return this.get("/pilot/guide"); }
  pilotMe() { return this.get("/pilot/me"); }
  pilotEligible() { return this.get("/pilot/eligible"); }
  listPilots() { return this.get("/pilot/pilots"); }
  createPilot(body) { return this.post("/pilot/pilots", body); }
  getPilot(id) { return this.get(`/pilot/pilots/${encodeURIComponent(id)}`); }
  updatePilotTargets(id, targets) { return this.put(`/pilot/pilots/${encodeURIComponent(id)}/targets`, { targets }); }
  setPilotStatus(id, status) { return this.post(`/pilot/pilots/${encodeURIComponent(id)}/status`, { status }); }
  addPilotClient(id, body) { return this.post(`/pilot/pilots/${encodeURIComponent(id)}/clients`, body); }
  updatePilotClient(id, orgId, body) { return this.put(`/pilot/pilots/${encodeURIComponent(id)}/clients/${encodeURIComponent(orgId)}`, body); }
  removePilotClient(id, orgId, reason) { return this.post(`/pilot/pilots/${encodeURIComponent(id)}/clients/${encodeURIComponent(orgId)}/remove`, { reason }); }
  leavePilot(id, reason) { return this.post(`/pilot/pilots/${encodeURIComponent(id)}/leave`, { reason }); }
  pilotResults(id) { return this.get(`/pilot/pilots/${encodeURIComponent(id)}/results`); }
  pilotReport(id) { return this.get(`/pilot/pilots/${encodeURIComponent(id)}/report`); }
  takePilotSnapshot(id) { return this.post(`/pilot/pilots/${encodeURIComponent(id)}/snapshots`); }
  pilotSnapshots(id) { return this.get(`/pilot/pilots/${encodeURIComponent(id)}/snapshots`); }
  pilotLogs(id) { return this.get(`/pilot/pilots/${encodeURIComponent(id)}/logs`); }
  logPilotTime(id, body) { return this.post(`/pilot/pilots/${encodeURIComponent(id)}/time`, body); }
  logPilotIssue(id, body) { return this.post(`/pilot/pilots/${encodeURIComponent(id)}/issues`, body); }
  resolvePilotIssue(id, issueId, resolution) { return this.post(`/pilot/pilots/${encodeURIComponent(id)}/issues/${encodeURIComponent(issueId)}/resolve`, { resolution }); }
  logPilotPassportUse(id, body) { return this.post(`/pilot/pilots/${encodeURIComponent(id)}/passport-uses`, body); }
  myPilotSurvey(id) { return this.get(`/pilot/pilots/${encodeURIComponent(id)}/survey`); }
  submitPilotSurvey(id, body) { return this.post(`/pilot/pilots/${encodeURIComponent(id)}/survey`, body); }

  /** The decrypted original of an evidence file, as a Blob (the server sends it as a forced download). */
  async downloadEvidence(id) {
    const token = this.getToken();
    const url = `${this.baseUrl}/evidence/${encodeURIComponent(id)}/content`;
    let response;
    try {
      response = await this._fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    } catch (cause) {
      throw await this._networkError(cause, url);
    }
    if (!response.ok) {
      let body = null;
      try { body = JSON.parse(await response.text()); } catch { /* keep null */ }
      throw new ApiError(response.status, body, `/evidence/${id}/content`);
    }
    return { blob: await response.blob(), filename: (/filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") || "") || [])[1] || "evidence" };
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
  standardsCatalog() {
    return this.get("/standards/catalog");
  }
  resolveStandards(config) {
    return this.post("/standards/resolve", config);
  }
  getStandardsConfiguration() {
    return this.get("/standards/configuration");
  }
  saveStandardsConfiguration(config) {
    return this.put("/standards/configuration", config);
  }
  getPassport() {
    return this.get("/passport");
  }
  savePassportStructure(structure) {
    return this.put("/passport/structure", structure);
  }
  // ---- External data ingestion (preview writes nothing; commit re-reads the same file and checks the preview's fingerprint)
  ingestionLevels() {
    return this.get("/ingestion/levels");
  }
  _ingestForm({ file, purpose, reconciliationId, options, currency }) {
    const form = new FormData();
    form.append("file", file);
    form.append("purpose", purpose);
    if (reconciliationId) form.append("reconciliation_id", reconciliationId);
    if (options && Object.keys(options).length) form.append("options", JSON.stringify(options));
    if (currency) form.append("currency", currency);
    return form;
  }
  ingestionPreview(args) {
    return this._postForm("/ingestion/preview", this._ingestForm(args));
  }
  ingestionCommit({ fingerprint, acknowledge, evidenceType, allowDuplicate, ...rest }) {
    const form = this._ingestForm(rest);
    form.append("fingerprint", fingerprint);
    form.append("acknowledge", acknowledge ? "true" : "false");
    if (evidenceType) form.append("evidence_type", evidenceType);
    if (allowDuplicate) form.append("allow_duplicate", "true");
    return this._postForm("/ingestion/commit", form);
  }

  // ---- ASAVEXA AI (read-only: Explain, Detect, Recommend, Prove, and free-text Ask)
  aiExplain({ subjectType, subjectId }) {
    return this.post("/ai/explain", { subject_type: subjectType, subject_id: subjectId });
  }
  aiDetect({ periodId, limit } = {}) {
    return this.post("/ai/detect", { period_id: periodId || null, limit: limit || 20 });
  }
  aiRecommend({ scope, periodId, limit } = {}) {
    return this.post("/ai/recommend", { scope: scope || "all", period_id: periodId || null, limit: limit || 15 });
  }
  aiProve({ subjectType, subjectId, metric, periodId }) {
    return this.post("/ai/prove", { subject_type: subjectType, subject_id: subjectId || null, metric: metric || null, period_id: periodId || null });
  }
  aiAsk(question) {
    return this.post("/ai/ask", { question });
  }
  // ---- Permissioned sharing: organisation side
  createPassportShare(body) {
    return this.post("/passport/shares", body);
  }
  listPassportShares() {
    return this.get("/passport/shares");
  }
  getPassportShare(id) {
    return this.get(`/passport/shares/${encodeURIComponent(id)}`);
  }
  passportShareAccessLog(id) {
    return this.get(`/passport/shares/${encodeURIComponent(id)}/access-log`);
  }
  revokePassportShare(id, reason) {
    return this.post(`/passport/shares/${encodeURIComponent(id)}/revoke`, { reason: reason || null });
  }
  // ---- Permissioned sharing: recipient side (no organisation login involved)
  verifyShare({ accessToken, accessCode, email }) {
    return this._request("POST", "/shared-passport/verify", {
      body: { access_token: accessToken, access_code: accessCode, email: email || null }, token: null,
    });
  }
  viewSharedPassport(sessionToken) {
    return this._request("GET", "/shared-passport/view", { token: sessionToken });
  }
  downloadSharedPassport(sessionToken) {
    return this._request("GET", "/shared-passport/download", { token: sessionToken });
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
    return this.get("/reports/general-ledger", { period_id: periodId, account_ids: accountId });
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
