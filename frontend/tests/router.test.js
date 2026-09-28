import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { matchRoute } from "../src/lib/router.js";

const routes = [
  { path: "/", name: "dashboard" },
  { path: "/evidence", name: "evidence-list" },
  { path: "/evidence/:evidenceId", name: "evidence-detail" },
  { path: "/compliance/findings/:findingId", name: "finding-detail" },
];

describe("matchRoute — pure path matching, no DOM/window involved", () => {
  test("matches a static route exactly", () => {
    const result = matchRoute(routes, "/evidence");
    assert.equal(result.route.name, "evidence-list");
    assert.deepEqual(result.params, {});
  });

  test("matches a parameterized route and extracts the param", () => {
    const result = matchRoute(routes, "/evidence/ev-123");
    assert.equal(result.route.name, "evidence-detail");
    assert.deepEqual(result.params, { evidenceId: "ev-123" });
  });

  test("more specific static routes are not shadowed by parameterized ones when ordered first", () => {
    const result = matchRoute(routes, "/evidence");
    assert.equal(result.route.name, "evidence-list", "should not match the :evidenceId route with an empty param");
  });

  test("decodes URL-encoded characters in path parameters", () => {
    const result = matchRoute(routes, "/evidence/ev%2Fslash");
    assert.equal(result.params.evidenceId, "ev/slash");
  });

  test("returns null for a path that matches nothing", () => {
    assert.equal(matchRoute(routes, "/not-a-real-route"), null);
  });

  test("a route with two segments after the prefix does not match a single-param pattern", () => {
    assert.equal(matchRoute(routes, "/evidence/a/b"), null);
  });
});
