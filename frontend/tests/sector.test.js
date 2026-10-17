import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { sectorOf, SECTOR_OF_TYPE, SECTOR_LABEL } from "../src/lib/sector.js";
import { Home } from "../src/pages/Home.js";

const css = readFileSync(new URL("../src/styles/ledger.css", import.meta.url), "utf8");
const app = readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
const walk = (v, fn) => { if (!v || typeof v !== "object") return; fn(v); (v.children || []).forEach((c) => walk(c, fn)); };
const all = (v, pred) => { const out = []; walk(v, (n) => { if (pred(n)) out.push(n); }); return out; };

describe("sector from the organisation's saved type", () => {
  test("unknown, unconfigured or missing give no sector", () => {
    for (const c of [null, undefined, {}, { configured: false, entity_type: "HEALTH" }, { configured: true }, { configured: true, entity_type: "MARS" }]) assert.equal(sectorOf(c), null);
  });
  test("each known type maps to an accent that exists in the stylesheet, with a plain-words label", () => {
    for (const [type, id] of Object.entries(SECTOR_OF_TYPE)) {
      assert.deepEqual(sectorOf({ configured: true, entity_type: type }), { id, label: SECTOR_LABEL[id] }, type);
      assert.match(css, new RegExp(`\\[data-sector="${id}"\\]`), `${id} has no accent pair`);
    }
  });
  test("a college or university gets the university accent, a school keeps the school one", () => {
    assert.equal(sectorOf({ configured: true, entity_type: "EDUCATION", subtype: "COLLEGE" }).id, "university");
    assert.equal(sectorOf({ configured: true, entity_type: "EDUCATION", subtype: "SCHOOL" }).id, "school");
  });
  test("every type in the real server catalogue is mapped", () => {
    const py = readFileSync(new URL("../../src/asavexa/entities/catalog.py", import.meta.url), "utf8");
    const codes = [...py.matchAll(/^    \("([A-Z_]+)", "[^"]+", "[^"]+",$/gm)].map((m) => m[1]);
    assert.ok(codes.length >= 10, "could not read the catalogue");
    for (const c of codes) assert.ok(c in SECTOR_OF_TYPE, `${c} is not mapped`);
  });
});

describe("where the sector shows", () => {
  const base = { user: { email: "a@b.co" }, role: "OWNER", orgLabel: "Org", data: null, loading: true, onNavigate() {} };
  test("the home page names the sector in words, and says nothing when there is none", () => {
    assert.equal(all(Home({ ...base, sector: { id: "health", label: "Health and care" } }), (n) => n.props && n.props.id === "hm-sector").length, 1);
    assert.equal(all(Home({ ...base, sector: null }), (n) => n.props && n.props.id === "hm-sector").length, 0);
  });
  test("the shell carries data-sector only from this organisation's own configuration", () => {
    assert.match(app, /"data-sector": \(sectorOf\(uiState\.entity && uiState\.entity\.org === authState\.organisationId \? uiState\.entity\.cfg : null\)/);
  });
});
