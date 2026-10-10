import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Network } from "../src/pages/Network.js";
import * as N from "../src/lib/network.js";
import { PERMISSIONS, ROLE_PERMISSIONS } from "../src/lib/permissions.js";
import { ApiClient } from "../src/api/client.js";

const text = (v) => JSON.stringify(v);
function find(v, pred, out = []) { if (!v || typeof v !== "object") return out; if (pred(v)) out.push(v); for (const c of v.children || []) find(c, pred, out); return out; }
const byId = (v, id) => find(v, (n) => n.props && n.props.id === id)[0];
const noop = new Proxy({}, { get: () => () => {} });
const TYPES = { BUSINESS: "Business or NGO", ACCOUNTANT: "Accountant / accounting firm", AUDITOR: "Auditor", BANK: "Bank or lender", INVESTOR: "Investor", DONOR: "Donor or funder", REGULATOR: "Regulator" };
const grant = (o = {}) => ({ scopes: ["IDENTITY", "FINANCIAL_HISTORY"], include_detail: false, closed_periods_only: true, date_from: "2023-01-01", date_to: "2026-10-10", ...o });
const conn = (o = {}) => ({ id: "c1", role: "PROVIDER", status: "ACTIVE", purpose: "Statutory audit", grant: grant(), created_at: "2026-10-01T00:00:00Z", expires_at: new Date(Date.now() + 30 * 86400000).toISOString(), counterparty: { name: "Audit LLP", type: "AUDITOR" }, history: [], views: 2, last_viewed_at: "2026-10-05T00:00:00Z", ...o });
const me = (o = {}) => ({ profile: { org_type: "BUSINESS", display_name: "Adaeze Bakery", description: "" }, active: 1, by_type: {}, pending_invites: 0, can_offer_to: ["ACCOUNTANT", "AUDITOR", "BANK", "INVESTOR", "DONOR", "REGULATOR"], connections: [conn()], types: TYPES, scopes: [], can_manage: true, ...o });
const net = (o = {}) => ({ tab: "connections", guide: { how_it_works: ["Data flows from a business.", "Both sides must agree."] }, me: me(), invites: [], form: null, created: null, code: "", preview: null, accept: { scopes: [], detail: false }, view: null, log: null, logFor: null, busy: false, ...o });
const page = (n, loading = false) => Network({ net: n, loading, onRetry() {}, actions: noop });

describe("permission", () => {
  test("network:manage is held by OWNER and ADMINISTRATOR only", () => {
    assert.ok(ROLE_PERMISSIONS.OWNER.includes(PERMISSIONS.NETWORK_MANAGE)); assert.ok(ROLE_PERMISSIONS.ADMINISTRATOR.includes(PERMISSIONS.NETWORK_MANAGE));
    for (const r of Object.keys(ROLE_PERMISSIONS).filter((x) => !["OWNER", "ADMINISTRATOR"].includes(x))) assert.ok(!ROLE_PERMISSIONS[r].includes(PERMISSIONS.NETWORK_MANAGE), r);
  });
});

describe("pure helpers", () => {
  test("invite validation", () => {
    const ok = { ...N.emptyInviteForm(), counterparty_type: "AUDITOR", purpose: "Audit 2026" };
    assert.equal(N.inviteProblem(ok, ["AUDITOR"]), null);
    assert.match(N.inviteProblem({ ...ok, counterparty_type: "" }, ["AUDITOR"]), /Choose/); assert.match(N.inviteProblem({ ...ok, counterparty_type: "BUSINESS" }, ["AUDITOR"]), /cannot be connected/);
    assert.match(N.inviteProblem({ ...ok, purpose: "x" }, ["AUDITOR"]), /for/); assert.match(N.inviteProblem({ ...ok, scopes: [] }, ["AUDITOR"]), /at least one/);
    assert.match(N.inviteProblem({ ...ok, connection_days: "0" }, ["AUDITOR"]), /1 to 365/); assert.match(N.inviteProblem({ ...ok, invite_days: "31" }, ["AUDITOR"]), /1 to 30/);
    assert.match(N.inviteProblem({ ...ok, date_from: "2026-05-01", date_to: "2026-01-01" }, ["AUDITOR"]), /start date/);
  });
  test("the safe defaults are summary-only and finished periods", () => {
    const f = N.emptyInviteForm(); assert.equal(f.include_detail, false); assert.equal(f.closed_periods_only, true); assert.ok(!f.scopes.includes("AUDIT_TRAIL"));
    const b = N.inviteBody({ ...f, counterparty_type: "BANK", purpose: " Loan ", connection_days: "60", invite_days: "7" });
    assert.deepEqual([b.purpose, b.connection_days, b.invite_days, b.grant.include_detail, b.grant.closed_periods_only], ["Loan", 60, 7, false, true]); assert.ok(!("date_from" in b.grant));
  });
  test("accepting a request: asking for exactly what was requested sends no grant; sharing less sends a narrower one; detail can never be added", () => {
    const pv = { grant: grant({ scopes: ["IDENTITY", "FINANCIAL_HISTORY"], include_detail: false }) };
    assert.equal(N.acceptGrant(pv, ["IDENTITY", "FINANCIAL_HISTORY"], false, true), null);
    assert.deepEqual(N.acceptGrant(pv, ["IDENTITY"], false, true), { scopes: ["IDENTITY"], include_detail: false, closed_periods_only: true });
    assert.deepEqual(N.acceptGrant(pv, ["IDENTITY", "GOVERNANCE"], true, true).scopes, ["IDENTITY"]);        // a scope that was not requested is dropped, not added
    assert.equal(N.acceptGrant(pv, ["IDENTITY"], true, true).include_detail, false);
    const pd = { grant: grant({ include_detail: true }) }; assert.equal(N.acceptGrant(pd, ["IDENTITY", "FINANCIAL_HISTORY"], false, true).include_detail, false);
  });
  test("what each side may do", () => {
    assert.ok(N.canOpen(conn({ role: "VIEWER" }))); assert.ok(!N.canOpen(conn())); assert.ok(!N.canOpen(conn({ role: "VIEWER", status: "EXPIRED" })));
    assert.ok(N.canChange(conn())); assert.ok(!N.canChange(conn({ role: "VIEWER" }))); assert.ok(N.canEnd(conn({ role: "VIEWER" }))); assert.ok(!N.canEnd(conn({ status: "REVOKED" })));
    assert.match(N.roleLine(conn()), /You share your information with Audit LLP/); assert.match(N.roleLine(conn({ role: "VIEWER" })), /shares its information with you/);
    assert.equal(N.daysLeft({ expires_at: "2000-01-01T00:00:00Z" }), 0); assert.match(N.grantLine(grant()), /Summary only\. Finished periods only/);
  });
  test("map counts only active connections by kind", () => {
    const c = N.mapCounts([conn(), conn({ id: "2", counterparty: { name: "B", type: "BANK" } }), conn({ id: "3", status: "REVOKED", counterparty: { name: "B2", type: "BANK" } })], TYPES);
    assert.equal(c.AUDITOR, 1); assert.equal(c.BANK, 1); assert.equal(c.REGULATOR, 0);
  });
});

describe("page", () => {
  test("a business sees its map, its connection, what was granted and how often it was opened", () => {
    const v = page(net()); const t = text(v);
    assert.equal(find(v, (n) => n.props && n.props["data-type"]).length, 7); assert.ok(t.includes("This is you")); assert.ok(byId(v, "conn-grant-c1")); assert.ok(t.includes("Opened 2 times"));
    assert.ok(byId(v, "change-c1")); assert.ok(byId(v, "end-c1")); assert.ok(byId(v, "log-c1")); assert.ok(!byId(v, "open-c1"));            // the business cannot "open" its own data through the viewer route
  });
  test("a viewer can open, cannot change, and is not shown view counts", () => {
    const v = page(net({ me: me({ profile: { org_type: "AUDITOR", display_name: "Audit LLP" }, can_offer_to: ["BUSINESS"], connections: [conn({ role: "VIEWER", views: undefined, counterparty: { name: "Adaeze Bakery", type: "BUSINESS" } })] }) }));
    assert.ok(byId(v, "open-c1")); assert.ok(!byId(v, "change-c1")); assert.ok(!byId(v, "log-c1")); assert.ok(!text(v).includes("Opened"));
  });
  test("a member without manage rights sees connections only", () => {
    const v = page(net({ me: me({ can_manage: false }) })); assert.equal(find(v, (n) => n.props && n.props.role === "tab").length, 1); assert.ok(!byId(v, "end-c1"));
    assert.ok(!byId(v, "change-c1"));
  });
  test("without a profile a manager is sent to the profile form and the other tabs are disabled", () => {
    const v = page(net({ me: me({ profile: null, connections: [], can_offer_to: [] }) })); assert.ok(byId(v, "np-save")); assert.equal(byId(v, "net-tab-connect").props.disabled, true);
    assert.ok(text(v).includes("Tell the network who you are"));
  });
  test("an expired connection offers nothing but is still listed, with no open button", () => {
    const v = page(net({ me: me({ connections: [conn({ role: "VIEWER", status: "EXPIRED" })] }) })); assert.ok(!byId(v, "open-c1")); assert.ok(text(byId(v, "conn-status-c1")).includes("Expired"));
  });
  test("business invites show only its own options; a bank can only ask a business", () => {
    const biz = page(net({ tab: "connect", form: { kind: "invite", f: N.emptyInviteForm() } })); const opts = find(byId(biz, "inv-type"), (n) => n.tag === "option").map((o) => o.props.value).filter(Boolean);
    assert.deepEqual(opts, ["ACCOUNTANT", "AUDITOR", "BANK", "INVESTOR", "DONOR", "REGULATOR"]);
    const bank = page(net({ tab: "connect", me: me({ profile: { org_type: "BANK", display_name: "First" }, can_offer_to: ["BUSINESS"], connections: [] }), form: { kind: "invite", f: N.emptyInviteForm() } }));
    assert.deepEqual(find(byId(bank, "inv-type"), (n) => n.tag === "option").map((o) => o.props.value).filter(Boolean), ["BUSINESS"]); assert.ok(text(bank).includes("Ask a business"));
  });
  test("the code is shown once, with the warning", () => {
    const v = page(net({ tab: "connect", created: { code: "ASX-ABCDE-FGHJK", note: "shown once" } })); assert.equal(text(byId(v, "invite-code")).includes("ASX-ABCDE-FGHJK"), true); assert.ok(text(v).includes("shown once"));
  });
  test("a request preview lets the business tick fewer boxes, never more", () => {
    const pv = { kind: "REQUEST", from: { name: "First Bank", type: "BANK" }, purpose: "Loan", note: "", grant: grant(), connection_days: 90, you_decide: true, explain: "You can share less, never more." };
    const v = page(net({ tab: "connect", preview: pv, accept: { scopes: ["IDENTITY", "FINANCIAL_HISTORY"], detail: false } }));
    assert.equal(find(v, (n) => n.props && n.props.id && String(n.props.id).startsWith("pv-")).length, 2);          // only the requested sections are offered
    assert.ok(!byId(v, "pv-GOVERNANCE")); assert.ok(!byId(v, "pv-detail"));
    assert.equal(byId(page(net({ tab: "connect", preview: pv, accept: { scopes: [], detail: false } })), "accept-btn").props.disabled, true);              // nothing ticked: cannot agree
  });
  test("an offer preview shows what is offered and offers no editing", () => {
    const pv = { kind: "OFFER", from: { name: "Adaeze Bakery", type: "BUSINESS" }, purpose: "Audit", note: "", grant: grant(), connection_days: 90, you_decide: false, explain: "This business offers you the information below." };
    const v = page(net({ tab: "connect", me: me({ profile: { org_type: "AUDITOR", display_name: "A" }, can_offer_to: ["BUSINESS"], connections: [] }), preview: pv }));
    assert.ok(byId(v, "pv-grant")); assert.equal(find(v, (n) => n.props && n.props.id && String(n.props.id).startsWith("pv-") && n.props.id !== "pv-grant").length, 0);
  });
  test("what a connected organisation sees: scope, disclaimer and fingerprint are on screen", () => {
    const v = page(net({ view: { share: { organisation: "Adaeze Bakery Ltd", viewer: "Audit LLP", purpose: "Audit", scopes: ["IDENTITY"], include_detail: false, closed_periods_only: true, date_from: "2023-01-01", date_to: "2026-10-10", taken_at: "2026-10-10T00:00:00Z", expires_at: "2027-01-01T00:00:00Z" },
      sections: { identity: { name: "Adaeze" } }, fingerprint: "ab".repeat(32), disclaimer: "Not an audit opinion." } }));
    assert.ok(byId(v, "view-disclaimer")); assert.ok(text(byId(v, "view-scope")).includes("Summary only")); assert.equal(find(v, (n) => n.props && n.props["data-section"]).length, 1); assert.ok(text(v).includes("abababab"));
  });
  test("loading and errors", () => { assert.ok(text(page(net(), true)).toLowerCase().includes("loading")); assert.ok(text(page(net({ error: "Boom" }))).includes("Boom")); });
});

describe("api client", () => {
  test("paths", async () => {
    const calls = []; const c = new ApiClient("http://x", () => "t"); c._fetch = async (url, init) => { calls.push([init.method, url]); return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }); };
    await c.previewNetworkInvite("ASX-1"); await c.acceptNetworkInvite({ code: "x" }); await c.updateNetworkConnection("a/b", {}); await c.endNetworkConnection("c1", "r"); await c.networkPassport("c1"); await c.setNetworkProfile({});
    assert.deepEqual(calls.map((x) => x.join(" ")), ["POST /api/network/invites/preview", "POST /api/network/invites/accept", "PUT /api/network/connections/a%2Fb", "POST /api/network/connections/c1/end", "GET /api/network/connections/c1/passport", "PUT /api/network/profile"]);
  });
});
