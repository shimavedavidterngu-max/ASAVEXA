import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Security, TABS, visibleTabs } from "../src/pages/Security.js";
import { Login, MfaStep, OrganisationPicker } from "../src/pages/Login.js";
import { makeBinding, parseOidcReturn, interpretLogin, parseRegions } from "../src/lib/signin.js";
import { ApiClient, ApiError } from "../src/api/client.js";
import { PERMISSIONS, ROLE_PERMISSIONS } from "../src/lib/permissions.js";

const text = (v) => JSON.stringify(v);
function find(v, pred, out = []) {
  if (!v || typeof v !== "object") return out;
  if (pred(v)) out.push(v);
  for (const c of v.children || []) find(c, pred, out);
  return out;
}
const byId = (v, id) => find(v, (n) => n.props && n.props.id === id)[0];
const buttons = (v, label) => find(v, (n) => n.tag === "button" && (n.children || []).some((c) => typeof c === "string" && c.includes(label)));
const noop = new Proxy({}, { get: () => () => {} });

const me = (over = {}) => ({ mfa_available: true, mfa: { enabled: false, recovery_codes_left: 0 }, idle_minutes: 30, privacy_requests: [],
  sessions: [{ session_id: "s1", current: true, ip: "1.1.1.1", user_agent: "Chrome", created_at: "2026-10-01T10:00:00+00:00", last_seen: "2026-10-01T10:05:00+00:00", auth_method: "PASSWORD", revoked: false }], ...over });
const baseSec = (over = {}) => ({ tab: "me", me: me(), mfa: {}, d: {}, ...over });

describe("permissions mirror", () => {
  test("security:manage is held by OWNER and ADMINISTRATOR only", () => {
    assert.ok(ROLE_PERMISSIONS.OWNER.includes(PERMISSIONS.SECURITY_MANAGE));
    assert.ok(ROLE_PERMISSIONS.ADMINISTRATOR.includes(PERMISSIONS.SECURITY_MANAGE));
    for (const role of Object.keys(ROLE_PERMISSIONS).filter((r) => !["OWNER", "ADMINISTRATOR"].includes(r))) {
      assert.ok(!ROLE_PERMISSIONS[role].includes(PERMISSIONS.SECURITY_MANAGE), `${role} must not have security:manage`);
    }
  });
});

describe("Security page", () => {
  test("everyone sees My account; only owners/administrators see the organisation tabs", () => {
    assert.deepEqual(visibleTabs("ACCOUNTANT").map((t) => t.id), ["me"]);
    assert.deepEqual(visibleTabs(null).map((t) => t.id), ["me"]);
    assert.equal(visibleTabs("OWNER").length, TABS.length);
    assert.equal(visibleTabs("ADMINISTRATOR").length, TABS.length);
  });

  test("an accountant who somehow has an org tab selected is still shown My account", () => {
    const v = Security({ role: "ACCOUNTANT", sec: baseSec({ tab: "vendors" }), actions: noop });
    assert.ok(byId(v, "mfa-card"));
    assert.ok(!byId(v, "vendors-card"));
  });

  test("when keys are not set up, two-step sign-in says so and offers no setup button", () => {
    const v = Security({ role: "OWNER", sec: baseSec({ me: me({ mfa_available: false }) }), actions: noop });
    assert.ok(text(v).includes("not switched on for this platform yet"));
    assert.equal(buttons(v, "Set up two-step sign-in").length, 0);
  });

  test("setup shows the key and a confirm button wired to the action", () => {
    let confirmed = 0;
    const v = Security({ role: "OWNER", sec: baseSec({ mfa: { setup: { secret: "JBSWY3DPEHPK3PXP", otpauth_uri: "otpauth://totp/x" } } }), actions: { ...noop, mfaConfirm: () => confirmed++, mfaCodeChange: () => {} } });
    assert.equal(byId(v, "mfa-secret").children[0], "JBSWY3DPEHPK3PXP");
    buttons(v, "Turn on")[0].props.onClick();
    assert.equal(confirmed, 1);
  });

  test("recovery codes are shown once with an explicit dismiss", () => {
    let dismissed = false;
    const v = Security({ role: "OWNER", sec: baseSec({ mfa: { recovery: ["AAAA-1111", "BBBB-2222"] } }), actions: { ...noop, mfaDismissRecovery: () => { dismissed = true; } } });
    assert.ok(text(byId(v, "recovery-codes")).includes("AAAA-1111"));
    buttons(v, "I have saved them")[0].props.onClick();
    assert.ok(dismissed);
  });

  test("an error from the server is shown on the page, not swallowed", () => {
    const v = Security({ role: "OWNER", sec: baseSec({ mfa: { error: "That code is not right." } }), actions: noop });
    assert.ok(text(v).includes("That code is not right."));
    const v2 = Security({ role: "OWNER", sec: baseSec({ error: "Could not load." }), actions: noop, onRetry: () => {} });
    assert.ok(text(v2).includes("Could not load."));
  });

  test("devices: the current one cannot be signed out from the list; others can", () => {
    const sec = baseSec({ me: me({ sessions: [
      { session_id: "s1", current: true, created_at: "2026-10-01T10:00:00+00:00", last_seen: "2026-10-01T10:00:00+00:00" },
      { session_id: "s2", current: false, created_at: "2026-10-01T09:00:00+00:00", last_seen: "2026-10-01T09:30:00+00:00", ip: "2.2.2.2" } ] }) });
    let revoked = null;
    const v = Security({ role: "OWNER", sec, actions: { ...noop, revokeSession: (id) => { revoked = id; } } });
    const signOuts = buttons(v, "Sign out").filter((b) => b.children.includes("Sign out"));
    assert.equal(signOuts.length, 1);
    signOuts[0].props.onClick();
    assert.equal(revoked, "s2");
    assert.ok(byId(v, "revoke-others"));
  });

  test("erasure needs a confirmation step and is not offered twice", () => {
    let started = 0;
    const v = Security({ role: "OWNER", sec: baseSec(), actions: { ...noop, startErase: () => started++ } });
    buttons(v, "Request account erasure")[0].props.onClick();
    assert.equal(started, 1);
    assert.ok(!byId(v, "erase-confirm"));
    const confirming = Security({ role: "OWNER", sec: baseSec({ confirmErase: true }), actions: noop });
    assert.ok(byId(confirming, "erase-confirm"));
    const pending = Security({ role: "OWNER", sec: baseSec({ me: me({ privacy_requests: [{ id: "r", status: "PENDING", created_at: "2026-10-01T00:00:00+00:00" }] }) }), actions: noop });
    assert.ok(text(pending).includes("waiting for an owner"));
    assert.ok(!byId(pending, "erase-start"));
  });

  const overview = (over = {}) => ({ encryption: { configured: true, current_key: "k1", keys: ["k1", "k0"], keys_in_use: { k0: 2 } }, storage: { enabled: true, backend: "database", region: "NG" },
    audit_chain: { enabled: true, head: 12 }, mfa: { available: true, members: 3, with_mfa: 1, required: false }, sso: { configured: false },
    residency: { allowed_regions: ["NG"] }, retention: {}, holds: 1, alerts_open: 2, vendors_overdue: 1, backups: { known: false, detail: "No backup has reported in yet." },
    session_policy: { idle_minutes: 30, max_sessions: 5 }, ...over });

  test("overview reports honestly: partial two-step adoption is a warning, unknown backups are a warning", () => {
    const v = Security({ role: "OWNER", sec: baseSec({ tab: "overview", overview: overview() }), actions: noop });
    const t = text(byId(v, "overview-card"));
    assert.ok(t.includes("1 of 3 people"));
    assert.ok(t.includes("No backup has reported in yet."));
    assert.ok(t.includes("badge-warn"));
    const bare = Security({ role: "OWNER", sec: baseSec({ tab: "overview", overview: overview({ encryption: { configured: false, keys: [], keys_in_use: {} }, storage: { enabled: false }, audit_chain: { enabled: false } }) }), actions: noop });
    assert.ok(text(byId(bare, "overview-card")).includes("Not set up"));
    assert.equal(byId(bare, "rotate-keys").props.disabled, true);
  });

  test("the require-two-step checkbox and region box call their actions", () => {
    const calls = [];
    const v = Security({ role: "OWNER", sec: baseSec({ tab: "overview", overview: overview() }), actions: { ...noop, setRequireMfa: (b) => calls.push(["mfa", b]), regionsChange: (x) => calls.push(["reg", x]), saveRegions: () => calls.push(["save"]) } });
    byId(v, "require-mfa").props.onChange({ target: { checked: true } });
    byId(v, "regions").props.onInput({ target: { value: "NG, GH" } });
    byId(v, "save-regions").props.onClick();
    assert.deepEqual(calls, [["mfa", true], ["reg", "NG, GH"], ["save"]]);
  });

  test("alerts: open ones can be reviewed with a note; reviewed ones show the note", () => {
    const alerts = [
      { id: "a1", severity: "HIGH", title: "Two-step sign-in turned off", detail: "x", time: "2026-10-01T10:00:00+00:00", status: "OPEN" },
      { id: "a2", severity: "LOW", title: "Key rotation", detail: "y", time: "2026-10-01T10:00:00+00:00", status: "ACKNOWLEDGED", ack_note: "expected" } ];
    let started = null;
    const v = Security({ role: "OWNER", sec: baseSec({ tab: "alerts", alerts }), actions: { ...noop, ackStart: (id) => { started = id; } } });
    buttons(v, "Mark reviewed")[0].props.onClick();
    assert.equal(started, "a1");
    assert.ok(text(v).includes("Reviewed — expected"));
    const open = Security({ role: "OWNER", sec: baseSec({ tab: "alerts", alerts, ackTarget: "a1" }), actions: noop });
    assert.ok(byId(open, "ack-note"));
    const empty = Security({ role: "OWNER", sec: baseSec({ tab: "alerts", alerts: [] }), actions: noop });
    assert.ok(text(empty).includes("not a guarantee"));
  });

  test("audit integrity: intact, broken, and switched-off results are all distinct", () => {
    const run = (r) => text(byId(Security({ role: "OWNER", sec: baseSec({ tab: "audit", auditResult: r }), actions: noop }), "audit-card"));
    assert.ok(run({ enabled: true, ok: true, links: 9 }).includes("Intact"));
    const broken = run({ enabled: true, ok: false, problem_count: 2, links: 9, problems: [{ kind: "EVENT_CHANGED", seq: 4 }] });
    assert.ok(broken.includes("2 problem(s) found") && broken.includes("EVENT_CHANGED"));
    const off = run({ enabled: false, ok: null, note: "chain is not running" });
    assert.ok(off.includes("chain is not running") && !off.includes("Intact"));
  });

  test("retention: held evidence cannot be disposed of; due evidence asks for a reason first", () => {
    const retention = { policy: { days: { EVIDENCE: 2555 }, floor_days: { EVIDENCE: 2190 }, audit: "Audit events are never deleted." }, holds: [{ id: "h1", scope: "EVIDENCE:e1", reason: "audit", released_at: null }],
      due_for_disposal: [{ evidence_id: "e1", filename: "a.pdf", uploaded_at: "2018-01-01T00:00:00+00:00", due_at: "2024-01-01T00:00:00+00:00", on_hold: true, hold_reason: "audit" },
        { evidence_id: "e2", filename: "b.pdf", uploaded_at: "2018-01-01T00:00:00+00:00", due_at: "2024-01-01T00:00:00+00:00", on_hold: false }] };
    let disposeStart = null;
    const v = Security({ role: "OWNER", sec: baseSec({ tab: "retention", retention }), actions: { ...noop, disposeStart: (id) => { disposeStart = id; } } });
    const dispose = buttons(v, "Dispose…");
    assert.equal(dispose.length, 1);
    dispose[0].props.onClick();
    assert.equal(disposeStart, "e2");
    assert.ok(text(v).includes("On hold: audit"));
    assert.equal(byId(v, "ret-days").props.min, 2190);
    const confirming = Security({ role: "OWNER", sec: baseSec({ tab: "retention", retention, disposeTarget: "e2" }), actions: noop });
    assert.ok(byId(confirming, "dispose-reason"));
  });

  test("privacy requests: only pending ones can be decided", () => {
    const requests = [{ id: "r1", status: "PENDING", created_at: "2026-10-01T00:00:00+00:00" }, { id: "r2", status: "COMPLETED", created_at: "2026-09-01T00:00:00+00:00" }];
    const decided = [];
    const v = Security({ role: "OWNER", sec: baseSec({ tab: "privacy", requests }), actions: { ...noop, decide: (id, ok) => decided.push([id, ok]) } });
    buttons(v, "Approve erasure")[0].props.onClick();
    buttons(v, "Decline")[0].props.onClick();
    assert.deepEqual(decided, [["r1", true], ["r1", false]]);
    assert.equal(buttons(v, "Approve erasure").length, 1);
  });

  test("vendors: risk tier, overdue review and reasons are visible; out-of-region vendors are flagged", () => {
    const vendors = [{ id: "v1", name: "Render", purpose: "Hosting", data_categories: ["FINANCIAL"], region: "", risk_tier: "CRITICAL", risk_reasons: ["No signed agreement."], review_overdue: true, next_review_due: null }];
    const residency = { restricted: true, allowed_regions: ["NG"], locations: [{ what: "Database", region: "US", ok: false }], vendors_outside_policy: [{ vendor: "Render", region: "unspecified" }], note: "Regions are as declared." };
    const v = Security({ role: "OWNER", sec: baseSec({ tab: "vendors", vendors, residency }), actions: noop });
    const t = text(v);
    assert.ok(t.includes("CRITICAL") && t.includes("Never reviewed") && t.includes("No signed agreement."));
    assert.ok(t.includes("Render handles data in unspecified"));
    assert.ok(t.includes("badge-fail"));
  });
});

describe("Login: two-step and single sign-on", () => {
  test("the code step replaces the password form and submits a trimmed code", () => {
    let sent = null;
    const v = Login({ mfaStep: true, onMfaSubmit: (x) => { sent = x; }, onMfaCancel: () => {} });
    assert.ok(text(v).includes("Check it is you"));
    assert.ok(!text(v).includes("Create one"));
    const form = find(v, (n) => n.tag === "form")[0];
    form.props.onSubmit({ preventDefault() {}, target: { elements: { code: { value: " 123456 " } } } });
    assert.deepEqual(sent, { code: "123456" });
  });

  test("the code step can go back, shows errors, and disables while pending", () => {
    let back = 0;
    const v = MfaStep({ pending: true, error: "That code is not right.", onMfaSubmit() {}, onMfaCancel: () => back++ });
    assert.ok(text(v).includes("That code is not right."));
    assert.equal(find(v, (n) => n.tag === "button")[0].props.disabled, true);
    find(v, (n) => n.tag === "a")[0].props.onClick({ preventDefault() {} });
    assert.equal(back, 1);
  });

  test("the single sign-on button appears only when the server says it is set up, and never on the register screen", () => {
    const sso = (cfg, mode) => text(Login({ mode, sso: cfg, onSubmit() {}, onSwitchMode() {} }));
    assert.ok(sso({ enabled: true }, "login").includes("single sign-on"));
    assert.ok(!sso({ enabled: false }, "login").includes("single sign-on"));
    assert.ok(!sso(null, "login").includes("single sign-on"));
    assert.ok(!sso({ enabled: true }, "register").includes("single sign-on"));
  });

  test("the organisation picker offers a way to set up two-step sign-in before an organisation is open", () => {
    let opened = 0;
    const v = OrganisationPicker({ organisations: [], onSelect() {}, onCreateNew() {}, onSecurity: () => opened++ });
    byId(v, "picker-security").props.onClick({ preventDefault() {} });
    assert.equal(opened, 1);
    assert.ok(!byId(OrganisationPicker({ organisations: [], onSelect() {}, onCreateNew() {} }), "picker-security"));
  });
});

describe("sign-in helpers", () => {
  test("binding is 64 hex characters and different each time", () => {
    const a = makeBinding(), b = makeBinding();
    assert.match(a, /^[0-9a-f]{64}$/);
    assert.notEqual(a, b);
    assert.equal(makeBinding(() => new Uint8Array(32)).length, 64);
  });

  test("the return address is parsed; provider errors are surfaced; anything else is ignored", () => {
    assert.deepEqual(parseOidcReturn("?code=abc&state=xyz"), { code: "abc", state: "xyz" });
    assert.deepEqual(parseOidcReturn("?error=access_denied&error_description=No+thanks"), { error: "No thanks" });
    assert.deepEqual(parseOidcReturn("?error=access_denied"), { error: "access_denied" });
    assert.equal(parseOidcReturn("?code=abc"), null);
    assert.equal(parseOidcReturn(""), null);
    assert.equal(parseOidcReturn(undefined), null);
  });

  test("a login reply is understood as done, needs-code, or an error", () => {
    assert.deepEqual(interpretLogin({ mfa_required: true, challenge: "c" }), { kind: "mfa", challenge: "c" });
    assert.equal(interpretLogin({ user: { id: "u" }, token: "t" }).kind, "done");
    assert.equal(interpretLogin({ mfa_required: true }).kind, "error");   // a code is required but no challenge came back
    assert.equal(interpretLogin(null).kind, "error");
    assert.equal(interpretLogin({ user: null, token: null, mfa_required: false }).kind, "error");
  });

  test("region lists are tidied", () => {
    assert.deepEqual(parseRegions("ng, GH ,, eu"), ["NG", "GH", "EU"]);
    assert.deepEqual(parseRegions(""), []);
    assert.deepEqual(parseRegions(undefined), []);
  });
});

describe("API client: security endpoints", () => {
  const make = (responder) => {
    const calls = [];
    const fetchImpl = async (url, init) => {
      calls.push({ url, init });
      const r = responder(url, init);
      return { ok: r.status < 300, status: r.status, text: async () => (r.body === undefined ? "" : JSON.stringify(r.body)), blob: async () => r.blob, headers: { get: (k) => (r.headers || {})[k] || null } };
    };
    return { client: new ApiClient({ baseUrl: "http://x", fetchImpl, getToken: () => "tok" }), calls };
  };

  test("methods, paths and bodies", async () => {
    const { client, calls } = make(() => ({ status: 200, body: {} }));
    await client.verifyMfa("ch", "123456");
    await client.oidcStart("b".repeat(20));
    await client.mfaConfirm("111111");
    await client.revokeSession("a b");
    await client.setRetention(3000);
    await client.placeHold("why", null);
    await client.decidePrivacyRequest("r1", false, "no");
    await client.listSecurityAlerts("OPEN");
    const seen = calls.map((c) => `${c.init.method} ${c.url.replace("http://x", "")}`);
    assert.deepEqual(seen, [
      "POST /auth/mfa/verify", "POST /auth/oidc/start", "POST /security/me/mfa/confirm", "DELETE /security/me/sessions/a%20b",
      "PUT /security/retention", "POST /security/retention/holds", "POST /security/privacy/requests/r1/decide", "GET /security/alerts?status=OPEN" ]);
    assert.deepEqual(JSON.parse(calls[0].init.body), { challenge: "ch", code: "123456" });
    assert.deepEqual(JSON.parse(calls[4].init.body), { evidence_days: 3000 });
    assert.deepEqual(JSON.parse(calls[6].init.body), { approve: false, note: "no" });
  });

  test("downloadEvidence sends the bearer token and returns the file name the server chose", async () => {
    const { client, calls } = make(() => ({ status: 200, blob: "BLOB", headers: { "Content-Disposition": 'attachment; filename="inv_1.pdf"' } }));
    const r = await client.downloadEvidence("e/1");
    assert.equal(calls[0].url, "http://x/evidence/e%2F1/content");
    assert.equal(calls[0].init.headers.Authorization, "Bearer tok");
    assert.deepEqual(r, { blob: "BLOB", filename: "inv_1.pdf" });
  });

  test("downloadEvidence turns a refusal into a readable ApiError", async () => {
    const { client } = make(() => ({ status: 404, body: { message: "File storage is not switched on" } }));
    await assert.rejects(() => client.downloadEvidence("e1"), (e) => e instanceof ApiError && e.status === 404 && /not switched on/.test(e.message));
  });

  test("a locked or MFA-required response keeps the server's wording", async () => {
    const { client } = make(() => ({ status: 403, body: { error: "MfaRequiredError", message: "This organisation requires multi-factor sign-in." } }));
    await assert.rejects(() => client.selectOrganisation("o"), (e) => /requires multi-factor/.test(e.message));
  });
});

describe("Evidence detail: original file", () => {
  test("shows a download button only when the file is stored; says plainly when it is not", async () => {
    const { Evidence } = await import("../src/pages/Evidence.js");
    const detail = { id: "e1", original_filename: "inv.pdf", status: "UPLOADED", type: "INVOICE", content_type: "application/pdf", size_bytes: 10, file_hash: "a".repeat(64), uploaded_by: "u", uploaded_at: "t" };
    let got = null;
    const stored = Evidence({ role: "OWNER", view: "detail", detail, storage: { stored: true, info: { backend: "database" } }, onDownload: (id) => { got = id; }, onNavigate() {}, onRetry() {} });
    byId(stored, "download-evidence").props.onClick();
    assert.equal(got, "e1");
    const none = Evidence({ role: "OWNER", view: "detail", detail, storage: { stored: false }, onNavigate() {}, onRetry() {} });
    assert.ok(!byId(none, "download-evidence"));
    assert.ok(text(none).includes("file itself is not stored"));
    const failed = Evidence({ role: "OWNER", view: "detail", detail, storage: { stored: true, info: {} }, downloadError: "The stored file does not match", onDownload() {}, onNavigate() {}, onRetry() {} });
    assert.ok(text(failed).includes("does not match"));
  });
});
