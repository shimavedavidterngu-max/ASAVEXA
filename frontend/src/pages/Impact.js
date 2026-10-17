import { h } from "../lib/vdom.js";
import { ui, frame } from "../lib/wsKit.js";
import { TABS, ATTENTION_TONE, statusOf, words, canPrepare, canApprove, canDecideIndicator, canRead_, canDecideReading, canClose, ownText } from "../lib/impact.js";

/** Impact measurement. Indicators with a baseline and a target, and the readings reported against them. It collects and verifies no data. */
export function Impact({ st, role, userId: me, loading, onRetry, actions: a }) {
  const k = ui(st, a, statusOf);
  return frame({ st, p: "imp", title: "Impact measurement", tabs: TABS, loading, onRetry, a, k,
    banner: "This workspace keeps programme indicators (a baseline, a target and dates) and the readings people report against them, and works out the progress toward the target and the progress expected by today exactly. A different person approves each indicator and confirms each reading. It collects no data, verifies no result and shows nothing about what caused a change. Use reference codes, not names or personal details.",
    body: () => (st.tab === "overview" ? overview(st, k, role, a) : indicators(st, k, role, me, a)) });
}

function overview(st, k, role, a) {
  const o = st.ov; if (!o) return k.none("Nothing loaded yet.");
  const c = o.counts, s = o.setting, S = o.states;
  return h("div", {},
    k.card("What needs attention", "imp-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, k.Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : k.none("Nothing needs attention.")),
    k.card("Open indicators by progress", "imp-states", h("ul", {}, ["ACHIEVED", "ON_TRACK", "BEHIND", "OVERDUE", "NO_DATA"].map((x) => h("li", { "data-state": x }, `${statusOf(x).label}: ${S[x]}`)))),
    k.card("Counts", "imp-counts", h("ul", {}, [["Waiting for a decision", c.proposed], ["Open", c.approved], ["Rejected", c.rejected], ["Closed", c.closed]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    k.card("Settings", "imp-setting", h("p", { id: "imp-setting-meaning" }, s.meaning),
      canApprove(role) && st.forms.setting ? h("div", {}, k.row(k.field("Behind when this many percentage points below expected", "imp-set-tol", k.text("setting", "tolerance_points", "imp-set-tol")), k.field("A reading is stale after this many days", "imp-set-stale", k.text("setting", "stale_days", "imp-set-stale"))),
        k.formError("setting"), k.btn("Save settings", "imp-set-save", () => a.saveSetting(), "primary", st.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only an approver can change these settings.")),
    k.limits(o.limitations, "imp-limits"));
}

function indicators(st, k, role, me, a) {
  const s = st.sel.indicator;
  return h("div", {},
    k.card("Indicators", "imp-indicators", st.indicators.length ? st.indicators.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-indicator": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${x.title}`), " ", k.St(x.status), x.state ? [" ", k.St(x.state)] : null, x.stale ? [" ", k.Badge({ tone: "warn", label: "Reading is stale" })] : null),
      h("div", { style: "color: var(--ink-500);" }, `Programme ${x.programme_ref} · ${words(x.direction)} from ${x.baseline} to ${x.target} ${x.unit}${x.progress_pct != null ? " · progress " + x.progress_pct + " percent" : ""}`),
      k.btn(s && s.id === x.id ? "Hide details" : "Details", `imp-in-open-${x.ref}`, () => a.selectIndicator(s && s.id === x.id ? null : x.id), "secondary", st.busy))) : k.none("No indicators yet.")),
    s ? detail(st, k, role, me, a, s) : null,
    canPrepare(role) ? k.card("Propose an indicator", "imp-indicator-card",
      k.row(k.field("Title", "imp-in-title", k.text("indicator", "title", "imp-in-title")), k.field("Programme reference (a code)", "imp-in-prog", k.text("indicator", "programme_ref", "imp-in-prog")), k.field("Unit (for example households)", "imp-in-unit", k.text("indicator", "unit", "imp-in-unit")),
        k.field("Should it", "imp-in-dir", k.sel("indicator", "direction", "imp-in-dir", [["INCREASE", "Increase"], ["DECREASE", "Decrease"]]))),
      k.row(k.field("Baseline value", "imp-in-base", k.text("indicator", "baseline", "imp-in-base")), k.field("Baseline date", "imp-in-bdate", k.text("indicator", "baseline_date", "imp-in-bdate", "YYYY-MM-DD")),
        k.field("Target value", "imp-in-target", k.text("indicator", "target", "imp-in-target")), k.field("Target date", "imp-in-tdate", k.text("indicator", "target_date", "imp-in-tdate", "YYYY-MM-DD"))),
      k.formError("indicator"), k.btn("Propose indicator", "imp-in-save", () => a.createIndicator(), "primary", st.busy)) : null);
}

function detail(st, k, role, me, a, x) {
  const dec = canDecideIndicator(x, role, me);
  return k.card(`${x.ref} · ${x.title}`, "imp-indicator-detail",
    h("div", { id: "imp-facts" }, `Programme ${x.programme_ref}. ${words(x.direction)} from ${x.baseline} (${x.baseline_date}) to ${x.target} (${x.target_date}), measured in ${x.unit}.`),
    x.status === "APPROVED" ? h("div", { id: "imp-progress" }, x.latest_value != null ? `Latest confirmed reading ${x.latest_value} at ${x.latest_period_end}; progress ${x.progress_pct} percent; expected by today ${x.expected_pct} percent. ` : `No confirmed reading yet; expected by today ${x.expected_pct} percent. `, k.St(x.state)) : null,
    x.decision_note ? h("div", {}, `Decision note: ${x.decision_note}`) : null, x.close_note ? h("div", { id: "imp-closed" }, `Closed: ${x.close_note}`) : null,
    dec ? h("div", {}, h("h4", {}, "Decide"), k.noteBox(`in-${x.id}`, "Note (approval: optional, at least 10 characters if given; rejection: required)", "imp-in-note"),
      k.btn("Approve indicator", "imp-in-approve", () => a.approveIndicator(x.id), "primary", st.busy), " ", k.btn("Reject indicator", "imp-in-reject", () => a.rejectIndicator(x.id), "secondary", st.busy)) :
      (x.status === "PROPOSED" && canApprove(role) ? h("p", { id: "imp-in-waiting", style: "color: var(--ink-500);" }, ownText) : null),
    h("div", { id: "imp-readings" }, h("h4", {}, "Readings"), x.readings.length ? x.readings.map((r) => h("div", { "data-reading": String(r.no) }, `#${r.no} ${r.period_end}: ${r.value} (${r.source_note}) `, k.St(r.status), r.decision_note ? ` Note: ${r.decision_note}` : "",
      canDecideReading(x, r, role, me) ? h("div", {}, k.noteBox(`rd-${x.id}-${r.no}`, "Note (confirmation: optional, at least 10 characters if given; rejection: required)", `imp-rd-${r.no}-note`),
        k.btn("Confirm reading", `imp-rd-${r.no}-confirm`, () => a.confirmReading(x.id, r.no), "primary", st.busy), " ", k.btn("Reject reading", `imp-rd-${r.no}-reject`, () => a.rejectReading(x.id, r.no), "secondary", st.busy)) :
        (r.status === "PROPOSED" && canApprove(role) && x.status === "APPROVED" ? h("p", { className: "imp-own", style: "color: var(--ink-500);" }, ownText) : null))) : k.none("No readings yet.")),
    canRead_(x, role) ? h("div", {}, h("h4", {}, "Record a reading"), k.row(k.field("Period end", "imp-rd-date", k.text("reading", "period_end", "imp-rd-date", "YYYY-MM-DD")), k.field("Value", "imp-rd-value", k.text("reading", "value", "imp-rd-value"))),
      k.field("Where the figure came from (at least 10 characters)", "imp-rd-source", k.text("reading", "source_note", "imp-rd-source")), k.formError("reading"), k.btn("Record reading", "imp-rd-save", () => a.addReading(x.id), "primary", st.busy)) : null,
    canClose(x, role) ? h("div", {}, h("h4", {}, "Close the indicator"), k.noteBox(`cl-${x.id}`, "Reason (at least 10 characters)", "imp-cl-note"), k.btn("Close indicator", "imp-cl-save", () => a.closeIndicator(x.id), "secondary", st.busy)) : null,
    h("div", {}, h("h4", {}, "History"), k.hist(x.history)));
}
