import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { FACET_ORDER, SHORT_FACET, summaryRows, unavailableText, relyText, flagText } from "../lib/assurance.js";

/**
 * Assurance: one plain vocabulary for how far each kind of record has been checked, and how many records of each kind have reached each stage.
 * These are facts, not a score. They do not say the figures are right or that anyone complies with a standard.
 */
export function Assurance({ as, loading, onRetry, onRefresh }) {
  return h("div", {},
    h("h1", {}, "Assurance"),
    h("p", { style: "color: var(--ink-500); margin-top:-8px;" }, "One set of plain words for how far each kind of record has been checked, whichever part of ASAVEXA holds it."),
    onRefresh ? h("button", { className: "btn btn-secondary", id: "as-refresh", disabled: loading, onClick: () => onRefresh(), style: "margin-bottom:12px;" }, loading ? "Refreshing…" : "Refresh the counts") : null,
    as.error ? ErrorState({ message: as.error, onRetry }) : null,
    loading ? LoadingState() : h("div", {}, legend(as.vocabulary), summaryCard(as.summary), mappingCard(as.vocabulary)));
}

function legend(v) {
  if (!v) return null;
  return h("div", { className: "card", id: "as-legend", style: "margin-bottom:16px;" },
    h("h3", {}, "The six kinds of assurance"),
    h("dl", { style: "margin:0;" }, v.facets.map((f) => h("div", { "data-facet": f.code, style: "margin-bottom:6px;" }, h("dt", {}, h("strong", {}, f.label)), h("dd", { style: "margin:0 0 0 12px;" }, f.meaning)))),
    h("h4", {}, "Why a record may not be relied on right now"),
    h("ul", { style: "padding-left:18px;" }, v.flags.map((f) => h("li", { "data-flag": f.code }, h("strong", {}, `${flagText(f.code)}: `), f.meaning))),
    h("p", { style: "color: var(--ink-500); font-size:0.9em;", id: "as-note" }, v.note));
}

function summaryCard(summary) {
  const rows = summaryRows(summary);
  return h("div", { className: "card", id: "as-summary", style: "margin-bottom:16px;" },
    h("h3", {}, "What has been checked"),
    !summary ? h("p", {}, "Not loaded.") : h("div", {},
      h("div", { style: "overflow-x:auto;" }, h("table", { className: "table" },
        h("thead", {}, h("tr", {}, [h("th", {}, "Record"), h("th", {}, "Total"), ...FACET_ORDER.map((f) => h("th", {}, SHORT_FACET[f])), h("th", {}, "Can be relied on"), h("th", {}, "Needs attention")])),
        h("tbody", {}, rows.map((r) => !r.available
          ? h("tr", { "data-record": r.type, "data-unavailable": "1" }, h("td", { colSpan: FACET_ORDER.length + 4 }, unavailableText(r)))
          : h("tr", { "data-record": r.type },
              h("td", {}, r.label), h("td", {}, String(r.total)), ...r.counts.map((n) => h("td", {}, String(n))), h("td", {}, relyText(r)),
              h("td", {}, r.flagged.length ? r.flagged.map((f) => `${f.n} ${f.text.toLowerCase()}`).join(", ") : "None", r.unmapped ? ` · ${r.unmapped} not mapped` : "")))))),
      h("p", { style: "color: var(--ink-500); font-size:0.9em;", id: "as-summary-note" }, summary.note)));
}

function mappingCard(v) {
  if (!v) return null;
  return h("details", { className: "card", id: "as-mapping" }, h("summary", {}, "How each part of ASAVEXA's own status words map"),
    v.records.map((rec) => h("div", { "data-map": rec.type, style: "margin-top:10px;" }, h("h4", {}, rec.label),
      h("table", { className: "table" }, h("thead", {}, h("tr", {}, ["Status in that part", "Means", "Carries", "Flag"].map((t) => h("th", {}, t)))),
        h("tbody", {}, rec.statuses.map((s) => h("tr", { "data-status": s.status }, h("td", {}, h("code", {}, s.status)), h("td", {}, s.headline), h("td", {}, s.facets.length ? s.facets.map((f) => SHORT_FACET[f] || f).join(", ") : "Nothing yet"), h("td", {}, s.flag ? flagText(s.flag) : "—"))))))));
}
