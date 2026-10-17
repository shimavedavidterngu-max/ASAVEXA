import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { ProofLinks } from "../src/pages/ProofLinks.js";
import * as P from "../src/lib/proofLinks.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";

const text = (v) => JSON.stringify(v);
const vocab = () => ({
  types: [["evidence", "Evidence"], ["finding", "Finding"], ["control", "Control"], ["risk", "Risk"]].map(([code, label]) => ({ code, label })),
  relations: [
    { code: "EVIDENCES", label: "provides evidence for", from: ["evidence"], to: ["finding", "risk", "control"], symmetric: false },
    { code: "RAISED_BY", label: "was raised by", from: ["finding"], to: ["control"], symmetric: false },
    { code: "CONFLICTS_WITH", label: "conflicts with", from: ["evidence", "finding", "control", "risk"], to: ["evidence", "finding", "control", "risk"], symmetric: true },
  ],
  note: "A link is a claim somebody recorded.",
});
const link = (o = {}) => ({ id: "l1", status: "ACTIVE", basis: "RECORDED", relation: "EVIDENCES", from: { type: "evidence", id: "e1", label: "a.pdf" }, to: { type: "finding", id: "f1", label: "Finding one" },
  note: "", created_by: "u1", confirmed_by: null, disputed_by: null, history: [{ event: "CREATED", by: "u1", note: "" }], ...o });
const graph = (o = {}) => ({ focus: { type: "finding", id: "f1", label: "Finding one" }, nodes: [], links: [link()], gaps: [], truncated: false, depth: 1, ...o });
const pl = (o = {}) => ({ vocabulary: vocab(), choices: {}, find: { type: "", id: "", depth: 1 }, graph: graph(), form: { ...P.EMPTY_LINK }, gap: { ...P.EMPTY_GAP }, reasons: {}, formError: null, gapError: null, busy: false, error: null, notice: null, ...o });
const noop = new Proxy({}, { get: () => () => {} });
const page = (o = {}, role = "OWNER", me = "u2") => ProofLinks({ pl: pl(o), me, role, loading: false, onRetry() {}, actions: noop });

describe("helpers", () => {
  test("relations and target kinds follow what the server allows", () => {
    const v = vocab();
    assert.deepEqual(P.relationsFor(v, "finding", "").map((r) => r.code), ["RAISED_BY", "CONFLICTS_WITH"]);
    assert.deepEqual(P.relationsFor(v, "evidence", "control").map((r) => r.code), ["EVIDENCES", "CONFLICTS_WITH"]);
    assert.deepEqual(P.relationsFor(v, "risk", "evidence").map((r) => r.code), ["CONFLICTS_WITH"]);
    assert.ok(P.targetTypes(v, "finding").some((t) => t.code === "control"));
  });
  test("a link reads as one plain sentence", () => {
    assert.equal(P.linkSentence(vocab(), link()), "Evidence: a.pdf provides evidence for Finding: Finding one");
  });
  test("link form problems are named in order", () => {
    const f = { ...P.EMPTY_LINK };
    assert.match(P.linkProblem(f), /first record/);
    f.from_type = "evidence"; f.from_id = "e1"; assert.match(P.linkProblem(f), /related/);
    f.relation = "EVIDENCES"; assert.match(P.linkProblem(f), /second record/);
    f.to_type = "evidence"; f.to_id = "e1"; assert.match(P.linkProblem(f), /itself/);
    f.to_type = "finding"; f.to_id = "f1"; assert.equal(P.linkProblem(f), "");
  });
  test("payload carries refs and a trimmed note, or the problem", () => {
    assert.ok(P.linkPayload({ ...P.EMPTY_LINK }).problem);
    const r = P.linkPayload({ from_type: "evidence", from_id: "e1", to_type: "finding", to_id: "f1", relation: "EVIDENCES", note: "  seen  " });
    assert.deepEqual(r.body, { from_ref: { type: "evidence", id: "e1" }, to_ref: { type: "finding", id: "f1" }, relation: "EVIDENCES", note: "seen" });
  });
  test("gap payload needs a record, a relation and a reason", () => {
    const focus = { type: "finding", id: "f1" };
    assert.ok(P.gapPayload(null, { relation: "RAISED_BY", note: "x" }).problem);
    assert.ok(P.gapPayload(focus, { relation: "", note: "x" }).problem);
    assert.ok(P.gapPayload(focus, { relation: "RAISED_BY", note: "  " }).problem);
    assert.deepEqual(P.gapPayload(focus, { relation: "RAISED_BY", note: "n", expected_type: "control" }).body, { from_ref: focus, relation: "RAISED_BY", note: "n", expected_type: "control" });
  });
  test("buttons: nobody confirms their own link, and the disputer cannot reinstate", () => {
    assert.deepEqual(P.linkActions(link(), "u1", true, true), ["dispute", "retire"]);
    assert.deepEqual(P.linkActions(link(), "u2", true, true), ["confirm", "dispute", "retire"]);
    assert.deepEqual(P.linkActions(link({ confirmed_by: "u2" }), "u3", true, true), ["dispute", "retire"]);
    assert.deepEqual(P.linkActions(link({ status: "DISPUTED", disputed_by: "u2" }), "u2", true, true), ["retire"]);
    assert.deepEqual(P.linkActions(link({ status: "DISPUTED", disputed_by: "u2" }), "u3", true, true), ["reinstate", "retire"]);
    assert.deepEqual(P.linkActions(link({ status: "RETIRED" }), "u3", true, true), []);
    assert.deepEqual(P.linkActions(link(), "u2", false, false), []);
  });
  test("only another person with approval rights can waive an open gap", () => {
    const g = { status: "OPEN", created_by: "u1" };
    assert.ok(P.canWaive(g, "u2", true)); assert.ok(!P.canWaive(g, "u1", true)); assert.ok(!P.canWaive(g, "u2", false)); assert.ok(!P.canWaive({ ...g, status: "WAIVED" }, "u2", true));
  });
  test("unknown statuses are shown as they are, not as success", () => {
    assert.equal(P.linkStatus("WEIRD").tone, "neutral"); assert.equal(P.gapStatus("WEIRD").label, "WEIRD");
  });
});

describe("page", () => {
  test("shows the neighbourhood, who recorded each link and that a second person has not confirmed it", () => {
    const t = text(page());
    assert.match(t, /Links around Finding: Finding one/); assert.match(t, /provides evidence for/);
    assert.match(t, /Recorded by a person/); assert.match(t, /Not yet confirmed by a second person/);
  });
  test("system links say so", () => assert.match(text(page({ graph: graph({ links: [link({ basis: "SYSTEM" })] }) })), /while doing other work/));
  test("an empty neighbourhood says so rather than showing a blank", () => assert.match(text(page({ graph: graph({ links: [] }) })), /No links are recorded/));
  test("a truncated picture is flagged", () => assert.match(text(page({ graph: graph({ truncated: true }) })), /cut short/));
  test("missing links are listed with their reason", () => {
    const g = graph({ gaps: [{ id: "g1", status: "OPEN", from: { type: "finding", id: "f1", label: "Finding one" }, relation: "RAISED_BY", expected_type: "control", note: "no control recorded", created_by: "u1" }] });
    const t = text(page({ graph: g }));
    assert.match(t, /Still missing/); assert.match(t, /no control recorded/); assert.match(t, /waive/i);
  });
  test("a reader without prepare rights sees no forms or buttons", () => {
    const t = text(page({}, "AUDITOR"));
    assert.doesNotMatch(t, /pl-add-go/); assert.doesNotMatch(t, /data-act/);
  });
  test("an error and a notice are shown", () => {
    assert.match(text(page({ error: "Nope" })), /Nope/); assert.match(text(page({ notice: "Link recorded." })), /Link recorded/);
  });
  test("the explanation says a link does not make the claim true", () => assert.match(text(page()), /does not make the claim true/));
});

describe("wiring", () => {
  test("client methods hit the right paths", async () => {
    const calls = []; const c = new ApiClient("http://x"); c._request = async (m, p, o) => { calls.push([m, p, o && o.body, o && o.query]); return {}; };
    await c.proofLinkVocabulary(); await c.proofLinkChoices("evidence"); await c.proofLinkGraph("finding", "f 1", 2); await c.addProofLink({ a: 1 });
    await c.proofLinkAction("l1", "confirm", { note: "x" }); await c.addProofLinkGap({ b: 2 }); await c.waiveProofLinkGap("g1", { reason: "r" });
    assert.deepEqual(calls.map((x) => x[1]), ["/proof-links/vocabulary", "/proof-links/choices", "/proof-links/graph", "/proof-links", "/proof-links/l1/confirm", "/proof-links/gaps", "/proof-links/gaps/g1/waive"]);
    assert.deepEqual(calls[2][3], { type: "finding", id: "f 1", depth: 2 });
  });
  test("the page is in the menu group for trust", () => assert.ok(NAV_GROUPS.some((g) => g.paths.includes("/proof-links"))));
});

describe("superseding", () => {
  const l2 = (o = {}) => link({ id: "l2", to: { type: "finding", id: "f2", label: "Finding two" }, ...o });
  test("replacements are other active links from the same record", () => {
    assert.deepEqual(P.supersedeCandidates(link(), [link(), l2()]).map((x) => x.id), ["l2"]);
    assert.deepEqual(P.supersedeCandidates(link(), [link(), l2({ status: "RETIRED" })]), []);
    assert.deepEqual(P.supersedeCandidates(link(), [link(), l2({ from: { type: "evidence", id: "e9", label: "z" } })]), []);
    assert.deepEqual(P.supersedeCandidates(link({ status: "RETIRED" }), [link(), l2()]), []); assert.deepEqual(P.supersedeCandidates(null, [l2()]), []);
  });
  test("the button appears only when there is a replacement, and a superseded link offers nothing", () => {
    assert.deepEqual(P.linkActions(link(), "u1", true, true, 1), ["dispute", "supersede", "retire"]);
    assert.deepEqual(P.linkActions(link(), "u1", true, true, 0), ["dispute", "retire"]);
    assert.deepEqual(P.linkActions(link({ status: "DISPUTED", disputed_by: "u2" }), "u2", true, true, 1), ["supersede", "retire"]);
    assert.deepEqual(P.linkActions(link({ status: "SUPERSEDED" }), "u3", true, true, 1), []); assert.deepEqual(P.linkActions(link(), "u1", false, true, 1), []);
    assert.equal(P.linkStatus("SUPERSEDED").label, "Superseded");
  });
  test("the page offers a choice of replacement and shows the status", () => {
    const t = text(page({ graph: graph({ links: [link(), l2()] }) }, "OWNER", "u1")); for (const s of ["pl-replace-l1", "Replace with newer link", "Replace with…"]) assert.ok(t.includes(s), s);
    const t2 = text(page({ graph: graph({ links: [link({ status: "SUPERSEDED" }), l2()] }) }, "OWNER", "u1")); assert.ok(t2.includes("Superseded")); assert.ok(!t2.includes("pl-replace-l1"));
  });
});
