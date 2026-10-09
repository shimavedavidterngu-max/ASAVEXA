import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  PassportSharing, presetRange, newWizard, validateStep, buildSharePayload, RECIPIENT_DEFAULTS, STEPS, actionLabel,
} from "../src/pages/PassportSharing.js";
import { SharedPassport } from "../src/pages/SharedPassport.js";
import { Passport } from "../src/pages/Passport.js";
import { ApiClient, ApiError } from "../src/api/client.js";

// Fixtures are the output of the REAL backend ShareService (see tests/test_passport_sharing.py).
const fx = JSON.parse(readFileSync(new URL("./fixtures/share-scenario.json", import.meta.url), "utf8"));
const passport = JSON.parse(readFileSync(new URL("./fixtures/passport-scenario.json", import.meta.url), "utf8"));
const text = (v) => JSON.stringify(v);
function find(v, pred, acc = []) { if (!v || typeof v !== "object") return acc; if (pred(v)) acc.push(v); for (const c of v.children || []) find(c, pred, acc); return acc; }
const byId = (v, id) => find(v, (n) => n.props && n.props.id === id)[0];
const noop = () => {};
const D = (s) => new Date(s + "T12:00:00Z");

describe("presetRange", () => {
  test("last 3 years ends today and starts the day after the same date 3 years ago", () => {
    assert.deepEqual(presetRange("3y", D("2026-10-09")), { date_from: "2023-10-10", date_to: "2026-10-09" });
  });
  test("last year is a full year", () => {
    assert.deepEqual(presetRange("1y", D("2026-12-31")), { date_from: "2026-01-01", date_to: "2026-12-31" });
  });
  test("29 February does not produce an invalid date", () => {
    const r = presetRange("1y", D("2028-02-29"));
    assert.equal(r.date_to, "2028-02-29");
    assert.match(r.date_from, /^2027-03-01$/);
  });
  test("custom has no preset range", () => assert.equal(presetRange("custom", D("2026-01-01")), null));
});

describe("wizard rules", () => {
  test("starts with the bank defaults: last three years, closed periods only, no detail, no download", () => {
    const w = newWizard(D("2026-10-09"));
    assert.equal(w.date_from, "2023-10-10");
    assert.equal(w.closed_periods_only, true);
    assert.equal(w.include_detail, false);
    assert.equal(w.allow_download, false);
    assert.deepEqual(w.scopes, RECIPIENT_DEFAULTS.BANK.scopes);
  });
  test("each step explains what is wrong in plain words", () => {
    const w = newWizard();
    assert.match(validateStep(0, w), /who you are sharing with/);
    w.recipient_name = "Bank"; w.recipient_email = "nope";
    assert.match(validateStep(0, w), /email/);
    w.recipient_email = "a@b.co";
    assert.equal(validateStep(0, w), null);
    w.scopes = [];
    assert.match(validateStep(1, w), /at least one/);
    w.scopes = ["IDENTITY"];
    w.date_from = "2026-02-01"; w.date_to = "2026-01-01";
    assert.match(validateStep(2, w), /must not be after/);
    w.date_to = "";
    assert.match(validateStep(2, w), /start and an end/);
    w.expires_in_days = "0";
    assert.match(validateStep(3, w), /between 1 and 365/);
    w.expires_in_days = "1.5";
    assert.match(validateStep(3, w), /between 1 and 365/);
  });
  test("payload matches the API contract and trims input", () => {
    const w = newWizard(D("2026-10-09"));
    w.recipient_name = "  First Bank  "; w.recipient_email = " "; w.purpose = "";
    w.expires_in_days = "14";
    const p = buildSharePayload(w);
    assert.equal(p.recipient_name, "First Bank");
    assert.equal(p.recipient_email, null);
    assert.equal(p.purpose, null);
    assert.equal(p.expires_in_days, 14);
    assert.deepEqual(Object.keys(p).sort(), ["allow_download", "closed_periods_only", "date_from", "date_to", "expires_in_days", "include_detail", "purpose", "recipient_email", "recipient_name", "recipient_type", "scopes"]);
  });
  test("every step has a title", () => assert.equal(STEPS.length, 5));
});

const shares = [
  { ...fx.summary_create.share, status: "ACTIVE" },
  { ...fx.detail_create.share, id: "s2", status: "REVOKED", revoke_reason: "Deal cancelled" },
  { ...fx.detail_create.share, id: "s3", status: "LOCKED", failed_attempts: 5 },
];
const pageBase = { role: "OWNER", shares, onStart: noop, onBackToPassport: noop, onRevokeStart: noop, onShowLog: noop };

describe("Passport Sharing page", () => {
  test("lists shares with their status, scope, detail level and download permission", () => {
    const t = text(PassportSharing(pageBase));
    for (const s of ["First Bank Plc", "ACTIVE", "REVOKED", "LOCKED", "Deal cancelled", "Too many wrong codes", "Summary only", "view only"]) assert.ok(t.includes(s), s);
  });
  test("only active/locked shares offer Revoke", () => {
    const rows = find(PassportSharing(pageBase), (n) => n.props && n.props["data-share"]);
    const has = (r) => find(r, (n) => n.props && n.props["data-action"] === "revoke").length;
    assert.deepEqual(rows.map(has), [1, 0, 1]);
  });
  test("a manager can look but not create or revoke", () => {
    const v = PassportSharing({ ...pageBase, role: "MANAGER" });
    assert.equal(byId(v, "share-new"), undefined);
    assert.equal(find(v, (n) => n.props && n.props["data-action"] === "revoke").length, 0);
    assert.ok(text(v).includes("Only an owner or administrator"));
  });
  test("a role without Passport access is told so", () => {
    assert.ok(text(PassportSharing({ ...pageBase, role: "READ_ONLY" })).includes("You don't have access"));
  });
  test("empty and loading and error states", () => {
    assert.ok(text(PassportSharing({ ...pageBase, shares: [] })).includes("Nothing has been shared yet"));
    assert.ok(text(PassportSharing({ ...pageBase, shares: null, loading: true })).includes("Loading"));
    assert.ok(text(PassportSharing({ ...pageBase, shares: null, error: "boom" })).includes("boom"));
  });
  test("each wizard step renders its own controls; last step offers Generate", () => {
    const w = newWizard(D("2026-10-09"));
    w.recipient_name = "Bank";
    const ids = [];
    for (let i = 0; i < STEPS.length; i++) {
      w.step = i;
      const v = PassportSharing({ ...pageBase, wizard: w, onWizardChange: noop, onNext: noop, onBack: noop, onCreate: noop, onCancel: noop });
      ids.push(["share-name", "scope-IDENTITY", "share-preset", "share-download", "share-review"].map((id) => !!byId(v, id)));
      assert.equal(!!byId(v, "share-create"), i === STEPS.length - 1);
      assert.equal(!!byId(v, "share-next"), i < STEPS.length - 1);
    }
    assert.deepEqual(ids.map((r) => r.indexOf(true)), [0, 1, 2, 3, 4]);
  });
  test("custom dates are only editable when Custom is chosen", () => {
    const w = newWizard(D("2026-10-09")); w.step = 2;
    const mk = () => PassportSharing({ ...pageBase, wizard: w, onWizardChange: noop, onNext: noop, onBack: noop, onCreate: noop, onCancel: noop });
    assert.equal(byId(mk(), "share-from").props.disabled, true);
    w.preset = "custom";
    assert.equal(byId(mk(), "share-from").props.disabled, false);
  });
  test("the review step spells out exactly what will be shared", () => {
    const w = newWizard(D("2026-10-09")); w.step = 4; w.recipient_name = "First Bank"; w.recipient_email = "a@b.co";
    const t = text(byId(PassportSharing({ ...pageBase, wizard: w, onWizardChange: noop, onNext: noop, onBack: noop, onCreate: noop, onCancel: noop }), "share-review"));
    for (const s of ["First Bank", "a@b.co", "Totals and statuses only", "View only", "2023-10-10 to 2026-10-09", "closed periods only", "30 day"]) assert.ok(t.includes(s), s);
  });
  test("result card shows link and code, and says they are shown once", () => {
    const res = { ...fx.summary_create, access_token: "id.secret", access_code: "ABCDE-FGHJK" };
    const v = PassportSharing({ ...pageBase, result: res, link: "https://x/#/shared/id.secret", copied: null, onCopy: noop, onDone: noop });
    assert.equal(byId(v, "share-link").props.value, "https://x/#/shared/id.secret");
    assert.equal(byId(v, "share-code").props.value, "ABCDE-FGHJK");
    const t = text(v);
    assert.ok(t.includes("shown once"));
    assert.ok(t.includes("different route"));
    assert.equal(byId(v, "share-new"), undefined, "no second wizard while the secrets are on screen");
  });
  test("revoke panel asks for a reason; activity panel lists readable events", () => {
    const v = PassportSharing({ ...pageBase, revokeTarget: shares[0].id, revokeReason: "x", onRevokeReasonChange: noop, onRevokeConfirm: noop, onRevokeCancel: noop });
    assert.ok(byId(v, "revoke-reason") && byId(v, "revoke-confirm"));
    const log = [{ when: "2026-01-01T10:00:00+00:00", action: "PASSPORT_SHARE_DENIED", who: "recipient:unverified", reason: "wrong access code or email" }];
    const t = text(PassportSharing({ ...pageBase, logTarget: shares[0].id, log, onCloseLog: noop }));
    assert.ok(t.includes("Access refused") && t.includes("wrong access code or email"));
    assert.equal(actionLabel("SOMETHING_NEW"), "SOMETHING_NEW");
  });
  test("Passport page offers Share… only when given the handler", () => {
    const b = { role: "OWNER", passport, structureForm: { owners: [], subsidiaries: [] }, onRefresh: noop, onDownload: noop, onPrint: noop };
    assert.ok(!text(Passport(b)).includes("Share…"));
    assert.ok(text(Passport({ ...b, onOpenSharing: noop })).includes("Share…"));
  });
});

const sharedBase = { phase: "view", data: fx.summary, onDownload: noop, onPrint: noop, onClose: noop };

describe("Shared passport (recipient) page", () => {
  test("verification screen asks for code and email and shows errors", () => {
    const v = SharedPassport({ phase: "verify", code: "", email: "", error: "The access code or email is not correct.", onCodeChange: noop, onEmailChange: noop, onVerify: noop });
    assert.ok(byId(v, "shared-code") && byId(v, "shared-email"));
    assert.ok(text(v).includes("not correct"));
    assert.ok(!text(v).includes("Financial history"));
  });
  test("an expired session returns to verification with an explanation", () => {
    assert.ok(text(SharedPassport({ phase: "verify", expired: true, onCodeChange: noop, onEmailChange: noop, onVerify: noop })).includes("session ended"));
  });
  test("an incomplete link is explained", () => {
    assert.ok(byId(SharedPassport({ phase: "bad-link" }), "shared-bad-link"));
  });
  test("banner states organisation, recipient, purpose, scope, dates, periods and expiry", () => {
    const t = text(SharedPassport(sharedBase));
    for (const s of ["Meridian Textiles Limited", "First Bank Plc", "Loan application", "Identity", "Financial history", "2020-01-01 to 2039-12-31", "FY2026-M01", "Totals and statuses only", "Access ends"]) assert.ok(t.includes(s), s);
  });
  test("integrity badge passes for the real snapshot, and fails loudly when it does not", () => {
    assert.ok(text(byId(SharedPassport(sharedBase), "shared-integrity")).includes("Integrity check passed"));
    const bad = { ...fx.summary, integrity: { verified: false } };
    assert.ok(text(byId(SharedPassport({ ...sharedBase, data: bad }), "shared-integrity")).includes("FAILED"));
  });
  test("summary share withholds detail and says so, and exposes no private names", () => {
    const t = text(SharedPassport(sharedBase));
    assert.ok(t.includes("not included") || t.includes("withheld") || /detail/i.test(t));
    assert.ok(!t.includes("dara@meridian.test"), "team email leaked into a summary-level share");
  });
  test("detail share shows the line-level information that summary hides", () => {
    const sum = text(SharedPassport(sharedBase));
    const det = text(SharedPassport({ ...sharedBase, data: fx.detail }));
    assert.ok(det.length > sum.length);
    assert.ok(det.includes("dara@meridian.test"));
  });
  test("download button only exists when the organisation allowed it", () => {
    assert.equal(byId(SharedPassport(sharedBase), "shared-download"), undefined);
    assert.ok(byId(SharedPassport({ ...sharedBase, data: fx.detail }), "shared-download"));
  });
  test("the recipient never sees organisation controls", () => {
    const t = text(SharedPassport({ ...sharedBase, data: fx.detail }));
    for (const s of ["Save ownership", "Share…", "Revoke", "Sign out", "Administration"]) assert.ok(!t.includes(s), s);
  });
  test("only the shared sections appear", () => {
    const data = { ...fx.summary, share: { ...fx.summary.share, scopes: ["FINANCIAL_HISTORY"] }, sections: { financial_history: fx.summary.sections.financial_history } };
    const t = text(SharedPassport({ ...sharedBase, data }));
    assert.ok(t.includes("Financial history") && !t.includes("Audit trail") && !t.includes("Evidence quality"));
  });
});

describe("client: recipient requests", () => {
  const mk = (status, body, getToken = () => "ORG-TOKEN") => {
    const calls = [];
    const fetchImpl = async (url, init) => { calls.push({ url, init }); return { ok: status < 300, status, text: async () => JSON.stringify(body) }; };
    return { c: new ApiClient({ baseUrl: "", fetchImpl, getToken, onUnauthenticated: () => calls.push("LOGGED-OUT") }), calls };
  };
  test("verify never sends the organisation's token", async () => {
    const { c, calls } = mk(200, { session_token: "s" });
    await c.verifyShare({ accessToken: "a.b", accessCode: "X", email: "e@x.co" });
    assert.equal(calls[0].url, "/shared-passport/verify");
    assert.equal(calls[0].init.headers.Authorization, undefined);
    assert.deepEqual(JSON.parse(calls[0].init.body), { access_token: "a.b", access_code: "X", email: "e@x.co" });
  });
  test("view and download send the recipient's session token, not the organisation's", async () => {
    const { c, calls } = mk(200, {});
    await c.viewSharedPassport("SESSION");
    await c.downloadSharedPassport("SESSION");
    assert.equal(calls[0].url, "/shared-passport/view");
    assert.equal(calls[0].init.headers.Authorization, "Bearer SESSION");
    assert.equal(calls[1].url, "/shared-passport/download");
    assert.equal(calls[1].init.headers.Authorization, "Bearer SESSION");
  });
  test("a 403 from the recipient endpoints shows the server's message and never logs anybody out", async () => {
    const { c, calls } = mk(403, { detail: "The access code or email is not correct." });
    await assert.rejects(() => c.verifyShare({ accessToken: "a.b", accessCode: "X" }), (e) => e instanceof ApiError && e.message === "The access code or email is not correct.");
    assert.ok(!calls.includes("LOGGED-OUT"));
  });
  test("a 401-free design: an expired recipient session (403) does not trigger organisation logout", async () => {
    const { c, calls } = mk(403, { message: "Your verified session has ended. Please verify again." });
    await assert.rejects(() => c.viewSharedPassport("old"), /session has ended/);
    assert.ok(!calls.includes("LOGGED-OUT"));
  });
  test("organisation-side share calls use the organisation token and the right paths", async () => {
    const { c, calls } = mk(200, []);
    await c.listPassportShares();
    await c.revokePassportShare("abc", "done");
    await c.passportShareAccessLog("abc");
    assert.deepEqual(calls.map((x) => x.url), ["/passport/shares", "/passport/shares/abc/revoke", "/passport/shares/abc/access-log"]);
    assert.equal(calls[0].init.headers.Authorization, "Bearer ORG-TOKEN");
    assert.deepEqual(JSON.parse(calls[1].init.body), { reason: "done" });
  });
});
