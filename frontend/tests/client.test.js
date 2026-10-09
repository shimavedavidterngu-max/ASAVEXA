/**
 * FRONTEND COMPONENT/UNIT TESTS — not real API integration tests.
 *
 * These run against a controlled, hand-written fetch fixture — never
 * a real network call, never a real FastAPI server (unavailable in
 * this environment; see docs/frontend-runtime-verification.md). Run
 * with: node --test frontend/tests/
 */
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { ApiClient, ApiError, NetworkError } from "../src/api/client.js";

/** A minimal, honest fetch fixture: records every call it received and
 * returns a pre-programmed response. Never simulates real HTTP/TCP
 * behavior — just the Response-shaped object our client actually reads. */
function makeFakeFetch(responder) {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    const { status, body } = responder(url, init);
    return {
      ok: status >= 200 && status < 300,
      status,
      text: async () => (body === undefined ? "" : JSON.stringify(body)),
    };
  };
  fetchImpl.calls = calls;
  return fetchImpl;
}

describe("ApiClient request construction", () => {
  test("GET builds the correct URL with base path and no body", async () => {
    const fetchImpl = makeFakeFetch(() => ({ status: 200, body: [{ id: "1" }] }));
    const client = new ApiClient({ fetchImpl, getToken: () => null });
    const result = await client.listAccounts();
    assert.equal(fetchImpl.calls.length, 1);
    assert.equal(fetchImpl.calls[0].url, "/api/accounts");
    assert.equal(fetchImpl.calls[0].init.method, "GET");
    assert.equal(fetchImpl.calls[0].init.body, undefined);
    assert.deepEqual(result, [{ id: "1" }]);
  });

  test("GET with query parameters omits undefined/null values", async () => {
    const fetchImpl = makeFakeFetch(() => ({ status: 200, body: { is_balanced: true } }));
    const client = new ApiClient({ fetchImpl, getToken: () => null });
    await client.trialBalance("period-123");
    assert.equal(fetchImpl.calls[0].url, "/api/reports/trial-balance?period_id=period-123");
  });

  test("POST sends a JSON body and Content-Type header", async () => {
    const fetchImpl = makeFakeFetch(() => ({ status: 201, body: { id: "j1" } }));
    const client = new ApiClient({ fetchImpl, getToken: () => null });
    await client.createDraftJournal({ date: "2026-01-01", description: "Test" });
    const call = fetchImpl.calls[0];
    assert.equal(call.init.method, "POST");
    assert.equal(call.init.headers["Content-Type"], "application/json");
    assert.deepEqual(JSON.parse(call.init.body), { date: "2026-01-01", description: "Test" });
  });

  test("a stored bearer token is attached to every request", async () => {
    const fetchImpl = makeFakeFetch(() => ({ status: 200, body: {} }));
    const client = new ApiClient({ fetchImpl, getToken: () => "secret-token-abc" });
    await client.me();
    assert.equal(fetchImpl.calls[0].init.headers.Authorization, "Bearer secret-token-abc");
  });

  test("no Authorization header is sent when there is no token", async () => {
    const fetchImpl = makeFakeFetch(() => ({ status: 200, body: {} }));
    const client = new ApiClient({ fetchImpl, getToken: () => null });
    await client.health();
    assert.equal(fetchImpl.calls[0].init.headers.Authorization, undefined);
  });
});

describe("ApiClient error mapping", () => {
  test("a 404 response raises ApiError with kind 'not_found'", async () => {
    const fetchImpl = makeFakeFetch(() => ({ status: 404, body: { detail: "Journal not found." } }));
    const client = new ApiClient({ fetchImpl, getToken: () => null });
    await assert.rejects(
      () => client.getJournal("does-not-exist"),
      (err) => {
        assert.ok(err instanceof ApiError);
        assert.equal(err.kind, "not_found");
        assert.equal(err.message, "Journal not found.");
        return true;
      }
    );
  });

  test("a 403 response raises ApiError with kind 'unauthorized'", async () => {
    const fetchImpl = makeFakeFetch(() => ({ status: 403, body: { detail: "Permission denied." } }));
    const client = new ApiClient({ fetchImpl, getToken: () => "tok" });
    await assert.rejects(() => client.postJournal("j1"), (err) => {
      assert.equal(err.kind, "unauthorized");
      return true;
    });
  });

  test("a 409 response raises ApiError with kind 'conflict'", async () => {
    const fetchImpl = makeFakeFetch(() => ({ status: 409, body: { detail: "You cannot change your own role." } }));
    const client = new ApiClient({ fetchImpl, getToken: () => "tok" });
    await assert.rejects(() => client.changeMemberRole("org1", "user1", "OWNER"), (err) => {
      assert.equal(err.kind, "conflict");
      return true;
    });
  });

  test("a 401 response triggers onUnauthenticated exactly once", async () => {
    const fetchImpl = makeFakeFetch(() => ({ status: 401, body: { detail: "Invalid or expired session." } }));
    let calledWith = 0;
    const client = new ApiClient({ fetchImpl, getToken: () => "expired-token", onUnauthenticated: () => { calledWith += 1; } });
    await assert.rejects(() => client.me());
    assert.equal(calledWith, 1);
  });

  test("a network failure raises NetworkError, not ApiError", async () => {
    const fetchImpl = async () => {
      throw new Error("connection refused");
    };
    const client = new ApiClient({ fetchImpl, getToken: () => null });
    await assert.rejects(() => client.health(), (err) => {
      assert.ok(err instanceof NetworkError);
      assert.ok(!(err instanceof ApiError));
      return true;
    });
  });

  test("a non-JSON error body still produces a usable ApiError", async () => {
    const fetchImpl = async () => ({ ok: false, status: 500, text: async () => "Internal Server Error" });
    const client = new ApiClient({ fetchImpl, getToken: () => null });
    await assert.rejects(() => client.health(), (err) => {
      assert.equal(err.kind, "server_error");
      assert.equal(err.message, "ASAVEXA encountered a server error while processing this request.");
      return true;
    });
  });
});

describe("ApiClient route coverage sanity", () => {
  test("every method call produces exactly the path documented in the router inventory", async () => {
    const fetchImpl = makeFakeFetch(() => ({ status: 200, body: {} }));
    const client = new ApiClient({ fetchImpl, getToken: () => "tok" });
    const cases = [
      [() => client.login("a@b.com", "pw"), "/api/auth/login"],
      [() => client.listFindings(), "/api/compliance/findings"],
      [() => client.getFinding("f1"), "/api/compliance/findings/f1"],
      [() => client.verifyRemediation("r1"), "/api/compliance/remediations/r1/verify"],
      [() => client.checkCloseReadiness("p1"), "/api/period-close/periods/p1/readiness"],
      [() => client.evidenceStatus("j1"), "/api/evidence/status?journal_id=j1"],
    ];
    for (const [call, expectedUrl] of cases) {
      fetchImpl.calls.length = 0;
      await call();
      assert.equal(fetchImpl.calls[0].url, expectedUrl);
    }
  });
});

import { ApiError as ApiErrorForDescribe } from "../src/api/client.js";
import { test as t2 } from "node:test";
import assert2 from "node:assert/strict";

t2("ApiError turns a FastAPI 422 validation list into a readable sentence", () => {
  const err = new ApiErrorForDescribe(422, { detail: [{ loc: ["body", "contact_email"], msg: "value is not a valid email address" }] });
  assert2.equal(err.message, "The submitted data is invalid. contact_email: value is not a valid email address");
});

t2("ApiError keeps string detail and domain-error message shapes", () => {
  assert2.equal(new ApiErrorForDescribe(400, { detail: "Nope" }).message, "Nope");
  assert2.equal(new ApiErrorForDescribe(409, { error: "X", message: "Conflict here" }).message, "Conflict here");
});

import { ApiClient as Client2, NetworkError as NetErr2 } from "../src/api/client.js";

t2("every HTTP status gets its own message and none is described as a network failure", () => {
  const msg = (st, body, path = "/accounts") => new ApiErrorForDescribe(st, body, path).message;
  assert2.equal(msg(401, {}), "Your session has expired. Please sign in again.");
  assert2.equal(msg(401, { detail: "Invalid email or password." }, "/auth/login"), "Invalid email or password.");
  assert2.match(msg(403, { detail: "You do not have 'x'." }), /^You do not have permission to perform this action\./);
  assert2.equal(msg(404, {}), "The requested ASAVEXA resource was not found.");
  assert2.match(msg(422, { detail: [] }), /^The submitted data is invalid\./);
  assert2.match(msg(500, { request_id: "r1" }), /^ASAVEXA encountered a server error while processing this request\. \(reference r1\)/);
  assert2.equal(msg(409, { message: "Already exists." }), "Already exists.");
  for (const st of [400, 401, 403, 404, 409, 422, 500]) assert2.ok(!/connect/i.test(msg(st, {})));
});

t2("a failed fetch is diagnosed: reachable-but-blocked is reported as CORS, dead is reported as unreachable", async () => {
  const mk = (probeWorks) => new Client2({
    baseUrl: "https://api.example",
    fetchImpl: async (url, opts) => {
      if (opts && opts.mode === "no-cors") { if (probeWorks) return {}; throw new TypeError("down"); }
      throw new TypeError("Failed to fetch");
    },
  });
  await assert2.rejects(() => mk(true).get("/accounts"), (e) => e instanceof NetErr2 && e.diagnosis === "cors" && /CORS_ALLOWED_ORIGINS/.test(e.message));
  await assert2.rejects(() => mk(false).get("/accounts"), (e) => e instanceof NetErr2 && e.diagnosis === "unreachable" && e.message === "Unable to connect to the ASAVEXA API. Please check the API service.");
});
