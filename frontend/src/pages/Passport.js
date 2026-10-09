import { h, Fragment } from "../lib/vdom.js";
import { DataTable } from "../components/DataTable.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { StatusBadge } from "../components/StatusBadge.js";
import { allowed } from "../components/PermissionGate.js";
import { PERMISSIONS } from "../lib/permissions.js";

/**
 * VERA Financial Passport. Pure render function. Every number, status
 * and message shown here is computed by the backend from the live
 * records (GET /passport); this page only lays it out. Where the
 * backend says something is not available, the page says so too.
 */

export const OWNER_KINDS = ["INDIVIDUAL", "COMPANY", "FUND", "GOVERNMENT", "OTHER"];
export const RELATIONSHIPS = ["SUBSIDIARY", "ASSOCIATE", "JOINT_VENTURE", "BRANCH"];

const SECTIONS = [
  ["identity", "Identity"],
  ["financial_history", "Financial history"],
  ["evidence_quality", "Evidence quality"],
  ["governance", "Governance"],
  ["reporting", "Reporting"],
  ["audit_trail", "Audit trail"],
];

const STATUS_LABEL = { ok: "Complete", attention: "Needs attention", incomplete: "Not enough data" };
const STATUS_TONE = { ok: "pass", attention: "warn", incomplete: "neutral" };

export function fmtMoney(value, currency) {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  const s = n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return currency ? `${currency} ${s}` : s;
}

export function fmtWhen(iso) {
  if (!iso) return "—";
  const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(iso);
  return m ? `${m[1]} ${m[2]} UTC` : String(iso);
}

const pct = (v) => (v === null || v === undefined ? "—" : `${v}%`);
const val = (v) => (v === null || v === undefined || v === "" ? "—" : String(v));

function statusBadge(status) {
  return h("span", { className: `badge badge-${STATUS_TONE[status] || "neutral"}` }, STATUS_LABEL[status] || status);
}

function kv(label, value) {
  return h("div", { style: "display:flex; gap:8px; padding:4px 0; font-size:13.5px;" },
    h("div", { style: "min-width:190px; color: var(--ink-500);" }, label),
    h("div", { style: "font-weight:600; word-break:break-word;" }, value));
}

function attention(items) {
  if (!items || !items.length) return null;
  return h("div", { className: "alert alert-info", style: "margin-bottom:12px;" },
    h("ul", { style: "margin:0; padding-left:18px;" }, items.map((m) => h("li", {}, m))));
}

function sectionCard(id, title, data, ...body) {
  return h("div", { className: "card", id: `passport-${id}` },
    h("div", { style: "display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;" },
      h("h2", { style: "margin:0;" }, title), statusBadge(data.status)),
    h("div", { style: "height:8px;" }),
    attention(data.attention),
    ...body);
}

function withheldNote(section) {
  return section && section.detail_withheld
    ? h("p", { style: "font-size:12.5px; color: var(--ink-500); margin:8px 0;" }, section.detail_note || "Line-level detail was not included.")
    : null;
}

function sub(title) {
  return h("h3", { style: "margin:16px 0 6px; font-size:14px;" }, title);
}

export function Passport({
  role, loading, error, onRetry, passport, refreshing,
  onRefresh, onDownload, onPrint, onOpenSharing,
  structureForm, structureSaving, structureError, structureSaved,
  onStructureChange, onAddRow, onRemoveRow, onSaveStructure,
}) {
  if (!allowed(role, PERMISSIONS.PASSPORT_MANAGE)) {
    return h("div", { className: "empty-state card" },
      h("h3", {}, "You don't have access to this"),
      h("p", {}, "The Financial Passport is available to owners, administrators and managers."));
  }
  const head = h("h1", {}, "VERA Financial Passport");
  if (loading && !passport) return h("div", {}, head, LoadingState("Assembling the passport from your records…"));
  if (error && !passport) return h("div", {}, head, ErrorState({ message: error, onRetry }));
  if (!passport) return h("div", {}, head, EmptyState({ title: "No passport yet", message: "It is built from your live records when you open this page." }));

  const p = passport;
  return h(
    "div", {},
    head,
    h("p", { style: "color: var(--ink-500); margin-top: -8px; margin-bottom: 16px;" },
      "A verifiable snapshot of who this organisation is, what its books show, how well they are evidenced, how they are governed and who did what. Built fresh from your records; nothing is estimated."),
    error ? h("div", { className: "alert alert-error" }, error) : null,
    h("div", { className: "card" },
      h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; justify-content:space-between; align-items:flex-start;" },
        h("div", {},
          kv("Organisation", val(p.identity.legal_entity.legal_name)),
          kv("Generated", `${fmtWhen(p.generated_at)} by ${val(p.generated_by)}`),
          kv("Fingerprint", h("code", { style: "font-size:12px;" }, p.fingerprint)),
          h("div", { style: "font-size:12px; color: var(--ink-500); margin-top:4px; max-width:640px;" }, p.fingerprint_note)),
        h("div", { style: "display:flex; gap:8px; flex-wrap:wrap;" },
          h("button", { className: "btn btn-secondary", disabled: refreshing, onClick: onRefresh }, refreshing ? "Refreshing…" : "Refresh"),
          h("button", { className: "btn btn-secondary", onClick: onDownload }, "Download JSON"),
          h("button", { className: "btn btn-secondary", onClick: onPrint }, "Print"),
          onOpenSharing ? h("button", { className: "btn btn-primary", onClick: onOpenSharing }, "Share…") : null)),
      h("div", { style: "display:flex; gap:10px; flex-wrap:wrap; margin-top:14px;" },
        sectionTiles(p))),
    PassportSections(p, { role, structureForm, structureSaving, structureError, structureSaved, onStructureChange, onAddRow, onRemoveRow, onSaveStructure })
  );
}

/** Status tiles for whichever sections the passport contains (a shared passport may hold only some). */
export function sectionTiles(p) {
  return SECTIONS.filter(([key]) => p[key]).map(([key, label]) => h("div", { style: "border:1px solid var(--line); border-radius:8px; padding:8px 12px; min-width:150px;" },
    h("div", { style: "font-size:11.5px; color: var(--ink-500); text-transform:uppercase;" }, label),
    h("div", { style: "margin-top:4px;" }, statusBadge(p[key].status)),
    h("div", { style: "font-size:12px; color: var(--ink-500); margin-top:4px;" },
      p[key].attention.length ? `${p[key].attention.length} point(s) to review` : "Nothing flagged")));
}

/** The section cards, in order, for whichever sections are present. `editor` is only passed on the
 * organisation's own page; recipients get a read-only rendering of the same cards. */
export function PassportSections(p, editor = {}) {
  const cur = p.financial_history && p.financial_history.currency;
  return Fragment([
    p.identity ? identityCard(p, editor) : null,
    p.financial_history ? financialCard(p, cur) : null,
    p.evidence_quality ? evidenceCard(p) : null,
    p.governance ? governanceCard(p) : null,
    p.reporting ? reportingCard(p) : null,
    p.audit_trail ? auditCard(p) : null,
  ]);
}

// ------------------------------------------------------------- identity
function identityCard(p, editor) {
  const i = p.identity;
  const e = i.legal_entity;
  return sectionCard("identity", "1. Identity", i,
    sub("Legal entity"),
    kv("Legal name", val(e.legal_name)), kv("Trading name", val(e.trading_name)),
    kv("Registration number", val(e.registration_number)), kv("Tax ID", val(e.tax_id)),
    kv("Organisation type", val(e.organisation_type)), kv("Industry", val(e.industry)),
    kv("Country", val(e.country)), kv("Base currency", val(e.base_currency)),
    kv("Financial year starts in month", val(e.fiscal_year_start_month)),
    sub("Ownership"),
    i.ownership.recorded
      ? DataTable({
          columns: [
            { key: "name", label: "Owner" }, { key: "kind", label: "Type" },
            { key: "ownership_percent", label: "Ownership", render: (o) => pct(o.ownership_percent) },
            { key: "notes", label: "Notes", render: (o) => val(o.notes) },
          ],
          rows: i.ownership.owners, emptyTitle: "No owners recorded",
        })
      : h("p", { style: "color: var(--ink-500);" }, "Not recorded yet."),
    i.ownership.recorded ? kv("Total recorded", pct(i.ownership.total_percent)) : null,
    i.ownership.updated_at ? kv("Last updated", `${fmtWhen(i.ownership.updated_at)} by ${val(i.ownership.updated_by)}`) : null,
    sub("Subsidiaries and related entities"),
    i.subsidiaries.recorded
      ? DataTable({
          columns: [
            { key: "name", label: "Entity" }, { key: "relationship", label: "Relationship" },
            { key: "jurisdiction", label: "Jurisdiction", render: (s) => val(s.jurisdiction) },
            { key: "registration_number", label: "Registration no.", render: (s) => val(s.registration_number) },
            { key: "ownership_percent", label: "Held", render: (s) => pct(s.ownership_percent) },
          ],
          rows: i.subsidiaries.items, emptyTitle: "None recorded", emptyMessage: "This organisation has no recorded subsidiaries.",
        })
      : h("p", { style: "color: var(--ink-500);" }, "Not recorded yet."),
    structureEditor(editor),
    sub("Reporting periods"),
    periodsTable(i.reporting_periods)
  );
}

function periodsTable(periods) {
  return DataTable({
    columns: [
      { key: "name", label: "Period" }, { key: "start_date", label: "From" }, { key: "end_date", label: "To" },
      { key: "status", label: "Status", render: (x) => StatusBadge({ status: x.status }) },
    ],
    rows: periods, emptyTitle: "No periods", emptyMessage: "No accounting periods have been opened.",
  });
}

function structureEditor({ role, structureForm, structureSaving, structureError, structureSaved, onStructureChange, onAddRow, onRemoveRow, onSaveStructure }) {
  if (!allowed(role, PERMISSIONS.ORG_MANAGE_SETTINGS) || !structureForm) return null;
  const f = structureForm;
  const input = (kind, i, field, value, extra = {}) =>
    h("input", { value: value || "", onInput: (e) => onStructureChange(kind, i, field, e.target.value), ...extra });
  const select = (kind, i, field, value, options) =>
    h("select", { value, onChange: (e) => onStructureChange(kind, i, field, e.target.value) },
      options.map((o) => h("option", { value: o }, o.replace(/_/g, " ").toLowerCase())));
  return h("div", { style: "margin-top:16px; border-top:1px solid var(--line); padding-top:12px;" },
    h("h3", { style: "font-size:14px; margin:0 0 8px;" }, "Edit owners and subsidiaries"),
    structureError ? h("div", { className: "alert alert-error" }, structureError) : null,
    structureSaved ? h("div", { className: "alert alert-info" }, "Saved.") : null,
    h("form", { onSubmit: (e) => { e.preventDefault(); onSaveStructure(); } },
      h("div", { style: "font-size:13px; font-weight:600; margin-bottom:4px;" }, "Owners"),
      f.owners.map((o, i) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; align-items:flex-end; margin-bottom:6px;", key: `o${i}` },
        h("div", { className: "field" }, h("label", {}, "Name"), input("owners", i, "name", o.name, { placeholder: "Owner name" })),
        h("div", { className: "field" }, h("label", {}, "Type"), select("owners", i, "kind", o.kind || "INDIVIDUAL", OWNER_KINDS)),
        h("div", { className: "field" }, h("label", {}, "Ownership %"), input("owners", i, "ownership_percent", o.ownership_percent, { inputmode: "decimal", placeholder: "e.g. 60" })),
        h("button", { type: "button", className: "btn btn-secondary", onClick: () => onRemoveRow("owners", i) }, "Remove"))),
      h("button", { type: "button", className: "btn btn-secondary", onClick: () => onAddRow("owners") }, "Add owner"),
      h("div", { style: "font-size:13px; font-weight:600; margin:14px 0 4px;" }, "Subsidiaries and related entities"),
      f.subsidiaries.map((s, i) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; align-items:flex-end; margin-bottom:6px;", key: `s${i}` },
        h("div", { className: "field" }, h("label", {}, "Name"), input("subsidiaries", i, "name", s.name, { placeholder: "Entity name" })),
        h("div", { className: "field" }, h("label", {}, "Relationship"), select("subsidiaries", i, "relationship", s.relationship || "SUBSIDIARY", RELATIONSHIPS)),
        h("div", { className: "field" }, h("label", {}, "Jurisdiction"), input("subsidiaries", i, "jurisdiction", s.jurisdiction)),
        h("div", { className: "field" }, h("label", {}, "Registration no."), input("subsidiaries", i, "registration_number", s.registration_number)),
        h("div", { className: "field" }, h("label", {}, "Held %"), input("subsidiaries", i, "ownership_percent", s.ownership_percent, { inputmode: "decimal" })),
        h("button", { type: "button", className: "btn btn-secondary", onClick: () => onRemoveRow("subsidiaries", i) }, "Remove"))),
      h("button", { type: "button", className: "btn btn-secondary", onClick: () => onAddRow("subsidiaries") }, "Add subsidiary"),
      h("div", { style: "margin-top:14px;" },
        h("button", { type: "submit", className: "btn btn-primary", disabled: structureSaving }, structureSaving ? "Saving…" : "Save ownership and subsidiaries"))));
}

// ---------------------------------------------------- financial history
function financialCard(p, cur) {
  const f = p.financial_history;
  const t = f.totals;
  const m = (v) => fmtMoney(v, cur);
  const periods = f.periods.filter((x) => x.has_activity);
  const cash = f.cash_flows;
  return sectionCard("financial", "2. Financial history", f,
    sub("All periods together"),
    kv("Revenue", m(t.revenue)), kv("Expenses", m(t.expenses)),
    kv("Net income", `${m(t.net_income)}${t.profitability ? ` (${t.profitability})` : ""}`),
    kv("Profit margin", pct(t.profit_margin_percent)),
    kv("Assets", m(t.assets)), kv("Liabilities", m(t.liabilities)), kv("Equity", m(t.equity)),
    h("div", { style: "font-size:12px; color: var(--ink-500); margin-top:4px;" }, f.totals_note),
    sub("By period"),
    DataTable({
      columns: [
        { key: "period_name", label: "Period" },
        { key: "revenue", label: "Revenue", align: "right", render: (x) => m(x.revenue) },
        { key: "expenses", label: "Expenses", align: "right", render: (x) => m(x.expenses) },
        { key: "net_income", label: "Net income", align: "right", render: (x) => m(x.net_income) },
        { key: "profit_margin_percent", label: "Margin", align: "right", render: (x) => pct(x.profit_margin_percent) },
        { key: "assets", label: "Assets", align: "right", render: (x) => m(x.assets) },
        { key: "liabilities", label: "Liabilities", align: "right", render: (x) => m(x.liabilities) },
        { key: "is_balanced", label: "Balanced", render: (x) => (x.is_balanced ? "✓" : "✗ No") },
      ],
      rows: periods, emptyTitle: "No posted activity", emptyMessage: "Post journals to build a financial history.",
    }),
    sub("Cash flows"),
    h("p", { style: "font-size:13px; color: var(--ink-500); margin:0 0 8px;" }, cash.note),
    cash.available
      ? Fragment([
          kv("Bank accounts", cash.accounts.map((a) => `${a.code} ${a.name}`).join(", ")),
          kv("Money in", m(cash.totals.inflow)), kv("Money out", m(cash.totals.outflow)), kv("Net movement", m(cash.totals.net)),
          DataTable({
            columns: [
              { key: "period_name", label: "Period" },
              { key: "inflow", label: "In", align: "right", render: (x) => m(x.inflow) },
              { key: "outflow", label: "Out", align: "right", render: (x) => m(x.outflow) },
              { key: "net", label: "Net", align: "right", render: (x) => m(x.net) },
            ],
            rows: cash.periods,
          }),
        ])
      : h("p", { style: "color: var(--ink-500);" }, `Not available: ${cash.reason}`)
  );
}

// ------------------------------------------------------- evidence quality
function evidenceCard(p) {
  const e = p.evidence_quality;
  const t = e.transactions;
  const b = e.bank_reconciliation;
  const cur = p.financial_history && p.financial_history.currency;
  return sectionCard("evidence", "3. Evidence quality", e,
    sub("Transactions"),
    kv("Posted transactions", t.total_posted),
    kv("Supported (evidence verified)", `${t.supported_verified} (${pct(t.supported_percent)})`),
    kv("Evidence attached, not verified", t.evidence_unverified),
    kv("Rejected or defective evidence", t.evidence_defective),
    kv("Missing evidence", t.missing_evidence),
    e.detail_withheld ? kv("Missing-evidence transactions", e.missing_evidence.count) : (e.missing_evidence.count
      ? Fragment([
          sub("Transactions with missing evidence"),
          DataTable({
            columns: [
              { key: "journal_number", label: "Journal" }, { key: "date", label: "Date" }, { key: "description", label: "Description" },
              { key: "amount", label: "Amount", align: "right", render: (x) => fmtMoney(x.amount, cur) },
            ],
            rows: e.missing_evidence.items,
          }),
          e.missing_evidence.truncated ? h("div", { style: "font-size:12px; color: var(--ink-500);" }, `Showing the first ${e.missing_evidence.items.length} of ${e.missing_evidence.count}.`) : null,
        ])
      : null),
    sub("Bank reconciliation"),
    kv("Bank transactions imported", b.bank_transactions), kv("Reconciled", b.reconciled), kv("Unreconciled", b.unreconciled),
    !e.detail_withheld && b.unreconciled
      ? DataTable({
          columns: [
            { key: "date", label: "Date" }, { key: "description", label: "Description" },
            { key: "direction", label: "Direction" },
            { key: "amount", label: "Amount", align: "right", render: (x) => fmtMoney(x.amount, x.currency) },
            { key: "status", label: "Status", render: (x) => StatusBadge({ status: x.status }) },
          ],
          rows: b.unreconciled_items,
        })
      : null,
    sub("Exceptions"),
    e.detail_withheld
      ? kv("Exceptions", e.exceptions.count)
      : DataTable({
          columns: [
            { key: "kind", label: "Kind", render: (x) => x.kind.replace(/_/g, " ").toLowerCase() },
            { key: "detail", label: "Detail" }, { key: "date", label: "Date", render: (x) => val(x.date) },
          ],
          rows: e.exceptions.items, emptyTitle: "No exceptions", emptyMessage: "Nothing in the evidence or reconciliation records is flagged.",
        }),
    withheldNote(e)
  );
}

// ------------------------------------------------------------ governance
const SOD_TONE = { pass: "pass", fail: "fail", not_tested: "neutral" };
const SOD_LABEL = { pass: "Pass", fail: "Violations found", not_tested: "Not tested yet" };

function governanceCard(p) {
  const g = p.governance;
  const c = g.controls;
  const sod = g.segregation_of_duties;
  const wh = g.detail_withheld;
  return sectionCard("governance", "4. Governance", g,
    sub("Approvals"),
    kv("Approval-type actions recorded", g.approvals.count),
    wh ? null : DataTable({
      columns: [
        { key: "when", label: "When", render: (x) => fmtWhen(x.when) }, { key: "who", label: "By" },
        { key: "action", label: "Action", render: (x) => x.action.replace(/_/g, " ").toLowerCase() },
      ],
      rows: g.approvals.recent, emptyTitle: "No approvals yet",
    }),
    sub("Controls"),
    kv("Controls defined / active", `${c.defined} / ${c.active}`), kv("Executions", c.executions),
    kv("Active controls never executed", c.never_executed), kv("Last executed", fmtWhen(c.last_executed_at)),
    kv("Latest result per control", Object.keys(c.latest_result_by_control).length
      ? Object.entries(c.latest_result_by_control).map(([k, v]) => `${k.replace(/_/g, " ").toLowerCase()}: ${v}`).join(", ") : "—"),
    sub("Segregation of duties"),
    h("p", { style: "font-size:13px; color: var(--ink-500); margin:0 0 8px;" }, sod.note),
    DataTable({
      columns: [
        { key: "label", label: "Check" },
        { key: "tested", label: "Cases tested", align: "right" },
        { key: "violations", label: "Violations", align: "right" },
        { key: "status", label: "Result", render: (x) => h("span", { className: `badge badge-${SOD_TONE[x.status]}` }, SOD_LABEL[x.status]) },
      ],
      rows: sod.checks,
    }),
    wh
      ? kv("Roles that can both create and post journals", sod.role_conflict_count === undefined ? "—" : sod.role_conflict_count)
      : (sod.role_conflicts.length
        ? Fragment([sub("People whose role can both create and post journals"),
            DataTable({ columns: [{ key: "person", label: "Person" }, { key: "role", label: "Role" }, { key: "conflict", label: "Conflict" }], rows: sod.role_conflicts })])
        : null),
    sub("Control exceptions"),
    kv("Open findings", `${g.control_exceptions.findings_open} of ${g.control_exceptions.findings_total}`),
    wh
      ? kv("Control exceptions", g.control_exceptions.count)
      : DataTable({
          columns: [
            { key: "kind", label: "Kind", render: (x) => x.kind.replace(/_/g, " ").toLowerCase() },
            { key: "control", label: "Control" }, { key: "severity", label: "Severity", render: (x) => val(x.severity) },
            { key: "detail", label: "Detail" },
          ],
          rows: g.control_exceptions.items, emptyTitle: "No control exceptions", emptyMessage: "No failing controls or open findings.",
        }),
    withheldNote(g)
  );
}

// ------------------------------------------------------------- reporting
function reportingCard(p) {
  const r = p.reporting;
  return sectionCard("reporting", "5. Reporting", r,
    kv("Applicable framework", r.framework_name ? `${r.framework_name} (${r.framework})` : val(r.framework)),
    kv("Reporting jurisdiction", val(r.jurisdiction)), kv("Entity type", val(r.entity_type)),
    kv("Base currency", val(r.base_currency)), kv("Financial year starts in month", val(r.fiscal_year_start_month)),
    r.readiness ? kv("Mandatory statements available", `${r.readiness.mandatory_available} of ${r.readiness.mandatory_total}`) : null,
    sub("Reporting periods"),
    periodsTable(r.reporting_periods),
    r.disclaimer ? h("p", { style: "font-size:12px; color: var(--ink-500); margin-top:12px;" }, r.disclaimer) : null
  );
}

// ----------------------------------------------------------- audit trail
function auditCard(p) {
  const a = p.audit_trail;
  const wh = a.detail_withheld;
  return sectionCard("audit", "6. Audit trail", a,
    kv("Events on record", a.total_events), kv("First event", fmtWhen(a.first_event_at)), kv("Latest event", fmtWhen(a.last_event_at)),
    kv("Created / changed / approved", `${a.by_category.created} / ${a.by_category.changed} / ${a.by_category.approved}`),
    wh ? kv("People who acted", a.people_count === undefined ? "—" : a.people_count) : null,
    wh ? withheldNote(a) : Fragment([
      sub("Who did what"),
      DataTable({
        columns: [
          { key: "who", label: "Person" },
          { key: "created", label: "Created", align: "right" }, { key: "changed", label: "Changed", align: "right" },
          { key: "approved", label: "Approved", align: "right" },
          { key: "last_at", label: "Last active", render: (x) => fmtWhen(x.last_at) },
        ],
        rows: a.by_person, emptyTitle: "No activity recorded",
      }),
      sub("Journals: who created, who posted, when"),
      DataTable({
        columns: [
          { key: "journal_number", label: "Journal" }, { key: "status", label: "Status", render: (x) => StatusBadge({ status: x.status }) },
          { key: "created_by", label: "Created by", render: (x) => val(x.created_by) }, { key: "created_at", label: "Created", render: (x) => fmtWhen(x.created_at) },
          { key: "posted_by", label: "Posted by", render: (x) => val(x.posted_by) }, { key: "posted_at", label: "Posted", render: (x) => fmtWhen(x.posted_at) },
        ],
        rows: a.journal_provenance, emptyTitle: "No journals",
      }),
      a.period_locks.length
        ? Fragment([sub("Period locks"),
            DataTable({ columns: [{ key: "period", label: "Period" }, { key: "locked_by", label: "Locked by", render: (x) => val(x.locked_by) }, { key: "locked_at", label: "When", render: (x) => fmtWhen(x.locked_at) }], rows: a.period_locks })])
        : null,
      sub("Most recent events"),
      DataTable({
        columns: [
          { key: "when", label: "When", render: (x) => fmtWhen(x.when) }, { key: "who", label: "Who" },
          { key: "action", label: "Action", render: (x) => x.action.replace(/_/g, " ").toLowerCase() },
          { key: "category", label: "Kind" }, { key: "entity_type", label: "Record" },
        ],
        rows: a.recent_events.slice(0, 15), emptyTitle: "No events",
      }),
    ])
  );
}
