import { h, Fragment } from "../lib/vdom.js";
import { summarise } from "../lib/selftest.js";

/**
 * Connection & Self-Test. Pure render function. Two tools:
 *  1. "Check connection": health, database and CORS checks against the
 *     real API, with a plain-language verdict.
 *  2. "Run full workflow self-test": drives the whole product against
 *     the real API (see lib/selftest.js) and shows pass/fail per step.
 */
const ICON = { pass: "✓", fail: "✗", warn: "!", skip: "–" };
const COLOR = { pass: "var(--ok, #1a7f4b)", fail: "var(--danger, #c0392b)", warn: "var(--warn, #b7791f)", skip: "var(--ink-500)" };

export function Diagnostics({ baseUrl, origin, connection, connectionRunning, onRunConnection, running, results, onRunSelfTest, onCopyReport, copied }) {
  const summary = summarise(results || []);
  return h(
    "div",
    {},
    h("h1", {}, "Connection & Self-Test"),
    h("p", { style: "color: var(--ink-500); margin-top: -8px; margin-bottom: 24px;" },
      "Checks that this website, the ASAVEXA API and the database are all talking to each other — using the real system, never a simulation."),
    h(
      "div", { className: "card" },
      h("h2", {}, "1. Connection check"),
      h("div", { style: "font-size:13px; color: var(--ink-500); margin-bottom:8px;" },
        h("div", {}, `This website: ${origin || "unknown"}`),
        h("div", {}, `API address: ${baseUrl}`)),
      h("button", { className: "btn btn-primary", disabled: connectionRunning, onClick: onRunConnection }, connectionRunning ? "Checking…" : "Check connection"),
      connection ? connectionReport(connection) : null
    ),
    h(
      "div", { className: "card" },
      h("h2", {}, "2. Full workflow self-test"),
      h("p", { style: "color: var(--ink-500); font-size:13px;" },
        "Runs the complete chain against the live system: organisation profile → accounts → balanced journal → invoice evidence → reconciliation → reports → compliance controls and findings → audit trail → period-close readiness → tenant isolation → persistence. " +
        "It creates clearly labelled “SelfTest” records in your current organisation (accounts, one period dated far in the future, one posted journal, one evidence file, one reconciliation, and a temporary second organisation to prove isolation). " +
        "It never closes your real periods."),
      h("button", { className: "btn btn-primary", disabled: running, onClick: onRunSelfTest }, running ? "Running…" : "Run self-test"),
      (results && results.length > 0)
        ? Fragment([
            h("div", { style: "margin-top:12px; font-weight:600;" },
              `${summary.pass} passed · ${summary.fail} failed · ${summary.warn} need attention · ${summary.skip} skipped${running ? " — running…" : ""}`),
            resultsTable(results),
            !running ? h("button", { className: "btn btn-secondary", style: "margin-top:12px;", onClick: onCopyReport }, copied ? "Copied ✓" : "Copy report") : null,
          ])
        : null
    )
  );
}

function connectionReport(c) {
  return h(
    "div", { style: "margin-top:12px;" },
    h("div", { className: `alert ${c.verdictOk ? "alert-info" : "alert-error"}` }, c.verdict),
    h("ul", { style: "margin:8px 0 0 18px; font-size:13px;" }, (c.lines || []).map((l) => h("li", {}, l)))
  );
}

function resultsTable(results) {
  let lastGroup = null;
  const rows = [];
  for (const r of results) {
    if (r.group !== lastGroup) {
      rows.push(h("tr", {}, h("td", { colspan: "3", style: "padding-top:12px; font-weight:600;" }, r.group)));
      lastGroup = r.group;
    }
    rows.push(
      h("tr", {},
        h("td", { style: `width:28px; color:${COLOR[r.status]}; font-weight:700;` }, ICON[r.status]),
        h("td", {}, r.name),
        h("td", { style: `font-size:12.5px; color:${r.status === "fail" ? COLOR.fail : "var(--ink-500)"}; word-break:break-word;` }, r.detail || "")
      )
    );
  }
  return h("div", { className: "table-scroll" }, h("table", { className: "data-table" }, h("tbody", {}, rows)));
}

export function formatReport(results, meta) {
  const s = summarise(results);
  const lines = [
    `ASAVEXA self-test — ${new Date().toISOString()}`,
    `Site: ${meta.origin}   API: ${meta.baseUrl}`,
    `${s.pass} passed, ${s.fail} failed, ${s.warn} need attention, ${s.skip} skipped`, "",
  ];
  for (const r of results) lines.push(`[${r.status.toUpperCase()}] ${r.group} / ${r.name}${r.detail ? ` — ${r.detail}` : ""}`);
  return lines.join("\n");
}
