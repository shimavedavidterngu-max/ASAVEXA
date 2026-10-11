import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";

/**
 * Health Centre Administration helpers. Financial and administrative only: there are no patient fields anywhere in these forms.
 * The server decides everything that matters (facility access, second-person approval, permissions); this file checks input early,
 * says who may press which button, and describes each list, form and action as data so the page can stay generic.
 */
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const caps = (role) => ({ read: has(role, PERMISSIONS.HEALTH_READ), prepare: has(role, PERMISSIONS.HEALTH_PREPARE), approve: has(role, PERMISSIONS.HEALTH_APPROVE), admin: has(role, PERMISSIONS.HEALTH_ADMIN), claims: has(role, PERMISSIONS.HEALTH_CLAIMS), staffing: has(role, PERMISSIONS.HEALTH_STAFFING) });
const e = encodeURIComponent;

export const qtyText = (s) => (/^-?\d+\.\d+$/.test(String(s)) ? String(s).replace(/0+$/, "").replace(/\.$/, "") : String(s));
export const STATE_TEXT = { UNAVAILABLE: "Not available", RESTRICTED: "Restricted", INCOMPLETE: "Incomplete" };
export const label = (s) => (s == null || s === "" ? "—" : String(s).replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase()));
export const isRealDate = (s) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s || "").trim());
  if (!m) return false;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return d.getUTCFullYear() === +m[1] && d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3];
};
export const isAmount = (s) => /^\d{1,12}(\.\d{1,2})?$/.test(String(s || "").trim());
export const isQty = (s) => /^\d{1,9}(\.\d{1,3})?$/.test(String(s || "").trim());
export const isSignedQty = (s) => /^-?\d{1,9}(\.\d{1,3})?$/.test(String(s || "").trim());
export const isInt = (s) => /^\d{1,9}$/.test(String(s || "").trim());
export const isMonth = (s) => /^\d{4}-(0[1-9]|1[0-2])$/.test(String(s || "").trim());
export const noteProblem = (n, what = "a reason", min = 3) => ((n || "").trim().length < min ? `Add ${what} (at least ${min} characters).` : null);

const TYPE_CHECK = {
  amount: [isAmount, "must be an amount like 1500 or 1500.50 (no commas)"], qty: [isQty, "must be a quantity like 12 or 12.5"], sqty: [isSignedQty, "must be a number like 3 or -2 (negative removes stock)"],
  int: [isInt, "must be a whole number"], date: [isRealDate, "must be a real date like 2026-02-10"], month: [isMonth, "must be a month like 2026-02"],
};

/** First problem with a form's values, or null. Fields: {k,label,type,req,min}. Lines: array of sub-field rows. */
export function formProblem(def, v) {
  for (const f of def.fields) {
    if (f.type === "lines") {
      const rows = v[f.k] || [];
      if (f.req && rows.length === 0) return `Add at least one ${f.item || "line"}.`;
      for (let i = 0; i < rows.length; i++) {
        const p = formProblem({ fields: f.fields }, rows[i]);
        if (p) return `${f.item || "Line"} ${i + 1}: ${p}`;
      }
      continue;
    }
    if (f.type === "check" || f.type === "evidence" || f.type === "facilities") continue;
    const x = v[f.k] == null ? "" : String(v[f.k]).trim();
    if (!x) { if (f.req) return `${f.label} is required.`; continue; }
    if (f.min && x.length < f.min) return `${f.label} needs at least ${f.min} characters.`;
    const t = TYPE_CHECK[f.type];
    if (t && !t[0](x)) return `${f.label} ${t[1]}.`;
    if (f.type === "currency" && !/^[A-Za-z]{3}$/.test(x)) return `${f.label} must be a three-letter code such as NGN.`;
  }
  return def.extra ? def.extra(v) : null;
}

/** Turn form values into the request body: trims text, drops blanks, keeps checkboxes and lines. */
export function formBody(def, v) {
  const out = {};
  for (const f of def.fields) {
    if (f.type === "lines") out[f.k] = (v[f.k] || []).map((r) => formBody({ fields: f.fields }, r));
    else if (f.type === "check") out[f.k] = !!v[f.k];
    else if (f.type === "facilities") out[f.k] = Array.isArray(v[f.k]) ? v[f.k] : [];
    else if (f.type === "evidence") out.evidence_ids = v.evidence_ids || [];
    else { const x = v[f.k] == null ? "" : String(v[f.k]).trim(); if (x !== "") out[f.k] = x; }
  }
  return out;
}
export const emptyForm = (def, row) => {
  const v = {};
  for (const f of def.fields) v[f.k] = f.type === "lines" ? [Object.fromEntries(f.fields.map((s) => [s.k, s.type === "check" ? false : (s.def || "")]))] : f.type === "check" ? !!f.def : f.type === "evidence" || f.type === "facilities" ? [] : (f.def || "");
  if (def.prefill && row) Object.assign(v, def.prefill(row));
  if (def.fields.some((f) => f.type === "evidence")) v.evidence_ids = [];
  return v;
};
export const blankLine = (f) => Object.fromEntries(f.fields.map((s) => [s.k, s.type === "check" ? false : (s.def || "")]));

const F = {
  text: (k, label, o = {}) => ({ k, label, type: "text", ...o }), area: (k, label, o = {}) => ({ k, label, type: "area", ...o }), amount: (k, label, o = {}) => ({ k, label, type: "amount", ...o }),
  qty: (k, label, o = {}) => ({ k, label, type: "qty", ...o }), date: (k, label, o = {}) => ({ k, label, type: "date", ...o }), int: (k, label, o = {}) => ({ k, label, type: "int", ...o }),
  sel: (k, label, opts, o = {}) => ({ k, label, type: "select", opts, ...o }), check: (k, label, o = {}) => ({ k, label, type: "check", ...o }), month: (k, label, o = {}) => ({ k, label, type: "month", ...o }),
  ev: () => ({ k: "evidence_ids", label: "Evidence (optional)", type: "evidence" }),
};

export const FORMS = {
  facility: { title: "Facility", fields: [F.text("name", "Name", { req: 1, min: 2 }), F.sel("type", "Facility type", "facility_types", { req: 1 }), F.sel("ownership", "Ownership", "ownership", { req: 1 }), F.text("region", "Region", { req: 1, min: 2 }), F.text("address", "Address"),
    { k: "currency", label: "Operating currency", type: "currency", req: 1, def: "NGN" }, F.int("fy_start_month", "Financial year starts in month (1-12)", { def: "1" }), F.int("min_quotes", "Quotes required before an order (0-5)", { def: "0" }), F.int("expiry_alert_days", "Warn about expiry this many days ahead", { def: "90" }),
    F.check("block_overspend", "Block orders that exceed the approved budget", { def: true }), F.text("tax_note", "Tax settings (note)")],
    prefill: (r) => ({ name: r.name, type: r.type, ownership: r.ownership, region: r.region, address: r.address || "", currency: r.currency, fy_start_month: String(r.fy_start_month), min_quotes: String(r.min_quotes), expiry_alert_days: String(r.expiry_alert_days), block_overspend: !!r.block_overspend, tax_note: r.tax_note || "" } ),
    submit: (api, fid, b, row) => (row ? api.hcPut(`/facilities/${e(row.id)}`, b) : api.hcPost("/facilities", b)), done: "Facility saved." },
  department: { title: "Department", fields: [F.text("code", "Code", { req: 1, min: 2 }), F.text("name", "Name", { req: 1, min: 2 }), F.text("cost_centre", "Cost centre (optional)")], submit: (api, fid, b) => api.hcPost(`/facilities/${e(fid)}/departments`, b), done: "Department added." },
  budget: { title: "Budget", fields: [F.text("name", "Name", { req: 1, min: 3 }), F.date("period_start", "Starts", { req: 1 }), F.date("period_end", "Ends", { req: 1 }),
    { k: "lines", type: "lines", item: "budget line", req: 1, fields: [F.sel("dept_id", "Department", "depts", { req: 1 }), F.sel("category", "Category", "categories", { req: 1 }), F.amount("amount", "Amount", { req: 1 }), F.text("account_id", "Ledger account id (optional)")] }, F.ev()],
    prefill: (r) => ({ name: r.name, period_start: r.period_start, period_end: r.period_end, lines: r.lines.map((l) => ({ dept_id: l.dept_id, category: l.category, amount: l.amount, account_id: l.account_id || "" })) }),
    submit: (api, fid, b, row) => (row ? api.hcPut(`/budgets/${e(row.id)}`, b) : api.hcPost(`/facilities/${e(fid)}/budgets`, b)), done: "Budget saved as a draft." },
  revise: { title: "Revise approved budget", fields: [F.area("note", "Why is it being revised?", { req: 1, min: 10 })], submit: (api, fid, b, row) => api.hcPost(`/budgets/${e(row.id)}/revise`, b), done: "Revision started as a new draft version." },
  transfer: { title: "Move budget between lines", fields: [F.sel("from_line", "From line", "row_lines", { req: 1 }), F.sel("to_line", "To line", "row_lines", { req: 1 }), F.amount("amount", "Amount", { req: 1 }), F.area("reason", "Reason", { req: 1, min: 10 })],
    submit: (api, fid, b, row) => api.hcPost(`/budgets/${e(row.id)}/transfers`, b), done: "Transfer requested. A different person must approve it." },
  supplier: { title: "Supplier", fields: [F.text("name", "Name", { req: 1, min: 2 }), F.text("contact", "Business contact details")], submit: (api, fid, b) => api.hcPost(`/facilities/${e(fid)}/suppliers`, b), done: "Supplier added." },
  requisition: { title: "Purchase requisition", fields: [F.sel("dept_id", "Department", "depts", { req: 1 }), F.sel("category", "Budget category", "categories", { req: 1 }), F.area("justification", "Justification", { req: 1, min: 5 }),
    { k: "lines", type: "lines", item: "item", req: 1, fields: [F.text("description", "Description", { req: 1, min: 2 }), F.sel("item_id", "Stock item (optional)", "items"), F.qty("qty", "Quantity", { req: 1 }), F.amount("unit_price", "Unit price", { req: 1 })] }, F.ev()],
    submit: (api, fid, b) => api.hcPost(`/facilities/${e(fid)}/requisitions`, b), done: "Requisition saved as a draft." },
  quote: { title: "Add a supplier quote", fields: [F.sel("supplier_id", "Supplier", "suppliers", { req: 1 }), F.amount("amount", "Quoted amount", { req: 1 }), F.text("note", "Note"), F.ev()], submit: (api, fid, b, row) => api.hcPost(`/requisitions/${e(row.id)}/quotes`, b), done: "Quote added." },
  po: { title: "Raise purchase order", fields: [F.sel("supplier_id", "Authorised supplier", "suppliers", { req: 1 })], submit: (api, fid, b, row) => api.hcPost(`/requisitions/${e(row.id)}/po`, b), done: "Purchase order raised. A different person must approve it." },
  receive: { title: "Receive goods", fields: [F.text("delivery_note", "Delivery note number", { req: 1, min: 2 }),
    { k: "lines", type: "lines", item: "delivered line", req: 1, fields: [F.int("line_no", "Order line no.", { req: 1 }), F.qty("qty", "Quantity received", { req: 1 }), F.text("batch", "Batch or lot (needed for expiry items)"), F.date("expiry", "Expiry date"), F.text("location", "Storage location", { def: "MAIN" })] }, F.ev()],
    submit: (api, fid, b, row) => api.hcPost(`/pos/${e(row.id)}/receive`, b), done: "Goods receipt recorded." },
  invoice: { title: "Record supplier invoice", fields: [F.text("invoice_no", "Supplier invoice number", { req: 1 }), F.date("invoice_date", "Invoice date", { req: 1 }), F.date("due_date", "Due date"), F.amount("amount", "Invoice amount", { req: 1 }), F.ev()],
    submit: (api, fid, b, row) => api.hcPost(`/pos/${e(row.id)}/invoices`, b), done: "Invoice recorded and matched against the order and goods received." },
  payment: { title: "Pay invoice", fields: [F.text("payment_ref", "Payment reference", { req: 1, min: 3 })], submit: (api, fid, b, row) => api.hcPost(`/invoices/${e(row.id)}/pay`, b), done: "Marked as paid." },
  credit: { title: "Credit note", fields: [F.amount("amount", "Credit amount", { req: 1 }), F.text("reason", "Reason", { req: 1, min: 5 })], submit: (api, fid, b, row) => api.hcPost(`/invoices/${e(row.id)}/credit`, b), done: "Credit note applied." },
  item: { title: "Stock item", fields: [F.text("sku", "SKU", { req: 1, min: 2 }), F.text("name", "Name", { req: 1, min: 2 }), F.sel("category", "Category", "item_categories", { req: 1 }), F.text("uom", "Unit of measure", { req: 1 }), F.qty("reorder_level", "Reorder level", { def: "0" }), F.check("tracks_expiry", "Tracks batch and expiry")],
    submit: (api, fid, b) => api.hcPost(`/facilities/${e(fid)}/items`, b), done: "Item added." },
  issue: { title: "Issue stock", fields: [F.qty("qty", "Quantity", { req: 1 }), F.text("location", "From location", { def: "MAIN" }), F.text("purpose", "Purpose: a department or activity, never a patient", { req: 1, min: 3 }), F.sel("dept_id", "Department (optional)", "depts")],
    submit: (api, fid, b, row) => api.hcPost(`/items/${e(row.item_id || row.id)}/issue`, b), done: "Stock issued (earliest expiry first)." },
  stocktransfer: { title: "Transfer stock", fields: [F.qty("qty", "Quantity", { req: 1 }), F.text("from_location", "From location", { req: 1, def: "MAIN" }), F.text("to_location", "To location", { req: 1 })], submit: (api, fid, b, row) => api.hcPost(`/items/${e(row.item_id || row.id)}/transfer`, b), done: "Stock transferred." },
  adjust: { title: "Stock adjustment or write-off", fields: [F.sel("kind", "Kind", "adjustment_kinds", { req: 1 }), F.text("batch", "Batch or lot"), F.date("expiry", "Expiry date of that lot"), F.text("location", "Location", { def: "MAIN" }), { k: "qty_delta", label: "Change in quantity (negative removes stock)", type: "sqty", req: 1 }, F.area("reason", "Reason", { req: 1, min: 10 }), F.ev()],
    submit: (api, fid, b, row) => api.hcPost(`/items/${e(row.item_id || row.id)}/adjustments`, b), done: "Adjustment requested. A different person must approve it before stock changes." },
  count: { title: "Physical stock count", fields: [F.qty("counted_qty", "Quantity counted", { req: 1 }), F.text("batch", "Batch or lot"), F.date("expiry", "Expiry date of that lot"), F.text("location", "Location", { def: "MAIN" })], submit: (api, fid, b, row) => api.hcPost(`/items/${e(row.item_id || row.id)}/count`, b), done: "Count recorded. Any difference is waiting for approval as an adjustment." },
  fee: { title: "Billing item and price", fields: [F.text("name", "Billing item", { req: 1, min: 2 }), F.sel("service_category", "Service category", "service_categories", { req: 1 }), F.amount("price", "Price", { req: 1 }), F.date("effective_from", "Effective from", { req: 1 })], submit: (api, fid, b) => api.hcPost(`/facilities/${e(fid)}/fees`, b), done: "Price saved." },
  receipt: { title: "Record a receipt", fields: [F.sel("service_category", "Service category", "service_categories", { req: 1 }), F.sel("fee_id", "Billing item (optional)", "fees"), F.amount("amount", "Amount received", { req: 1 }), F.date("date", "Date", { req: 1 }), F.sel("method", "Payment method", "payment_methods", { req: 1 })],
    submit: (api, fid, b) => api.hcPost(`/facilities/${e(fid)}/receipts`, b), done: "Receipt recorded. No patient details are kept." },
  refund: { title: "Request a refund", fields: [F.amount("amount", "Refund amount", { req: 1 }), F.area("reason", "Reason (no patient names)", { req: 1, min: 10 })], submit: (api, fid, b, row) => api.hcPost(`/receipts/${e(row.id)}/refunds`, b), done: "Refund requested. A different person must approve it." },
  payer: { title: "Payer", fields: [F.text("name", "Payer name", { req: 1, min: 2 }), F.sel("kind", "Payer type", "payer_kinds", { req: 1 })], submit: (api, fid, b) => api.hcPost(`/facilities/${e(fid)}/payers`, b), done: "Payer added." },
  claim: { title: "Claim (no patient details)", fields: [F.sel("payer_id", "Payer", "payers", { req: 1 }), F.text("external_ref", "Payer's claim reference (letters, numbers and . _ / - only)"), F.sel("service_category", "Billing category", "service_categories", { req: 1 }), F.month("service_month", "Service month", { req: 1 }), F.amount("amount", "Claim amount", { req: 1 })],
    submit: (api, fid, b) => api.hcPost(`/facilities/${e(fid)}/claims`, b), done: "Claim saved as a draft with a random internal reference." },
  claimpay: { title: "Record payer payment", fields: [F.amount("amount", "Amount paid", { req: 1 }), F.text("payment_ref", "Payer's payment reference", { req: 1, min: 3 }), F.date("date", "Date paid", { req: 1 }), F.ev()], submit: (api, fid, b, row) => api.hcPost(`/claims/${e(row.id)}/payments`, b), done: "Payment recorded against the claim." },
  claimreject: { title: "Payer rejected the claim", fields: [F.sel("code", "Reason", "rejection_codes", { req: 1 }), F.text("note", "Short note (never a patient's name)")], submit: (api, fid, b, row) => api.hcPost(`/claims/${e(row.id)}/reject`, b), done: "Claim marked as rejected." },
  claimresubmit: { title: "Resubmit the claim", fields: [F.amount("amount", "Corrected amount (optional)"), F.text("note", "What was corrected", { req: 1, min: 3 })], submit: (api, fid, b, row) => api.hcPost(`/claims/${e(row.id)}/resubmit`, b), done: "Claim resubmitted." },
  reconcile: { title: "Reconcile with the payer's statement", fields: [F.date("start", "From", { req: 1 }), F.date("end", "To", { req: 1 }), { k: "statement_amount", label: "Total on the payer's statement", type: "amount", req: 1 }, F.text("note", "Note")], submit: (api, fid, b, row) => api.hcPost(`/facilities/${e(fid)}/payers/${e(row.id)}/reconcile`, b), done: "Reconciliation recorded." },
  resolve: { title: "Explain the difference", fields: [F.area("note", "How was the difference explained?", { req: 1, min: 10 })], submit: (api, fid, b, row) => api.hcPost(`/reconciliations/${e(row.id)}/resolve`, b), done: "Difference explained." },
  asset: { title: "Equipment", fields: [F.text("tag", "Asset tag", { req: 1, min: 2 }), F.text("name", "Name", { req: 1, min: 2 }), F.sel("category", "Category", "asset_categories", { req: 1 }), F.sel("dept_id", "Department", "depts", { req: 1 }), F.text("location", "Location"), F.date("acquisition_date", "Acquired on", { req: 1 }),
    F.amount("cost", "Cost", { req: 1 }), F.text("supplier", "Supplier"), F.date("warranty_until", "Warranty ends"), F.int("maintenance_interval_days", "Service every (days)"), F.sel("condition", "Condition", "conditions"), F.ev()], submit: (api, fid, b) => api.hcPost(`/facilities/${e(fid)}/assets`, b), done: "Equipment registered." },
  maintenance: { title: "Maintenance request", fields: [F.sel("kind", "Kind", "maintenance_kinds", { req: 1 }), F.area("description", "What needs doing", { req: 1, min: 3 }), F.date("due_date", "Due by", { req: 1 })], submit: (api, fid, b, row) => api.hcPost(`/assets/${e(row.id)}/maintenance`, b), done: "Maintenance requested." },
  complete: { title: "Complete maintenance", fields: [F.date("completed_date", "Completed on", { req: 1 }), F.amount("cost", "Cost", { def: "0" }), F.int("downtime_days", "Days out of service", { def: "0" }), F.area("work_note", "What was done", { req: 1, min: 3 }), F.ev()], submit: (api, fid, b, row) => api.hcPost(`/maintenance/${e(row.id)}/complete`, b), done: "Maintenance completed." },
  staffing: { title: "Staffing cost summary (department totals only)", fields: [F.sel("dept_id", "Department", "depts", { req: 1 }), F.month("month", "Month", { req: 1 }), F.int("headcount", "Number of staff", { req: 1 }), F.amount("gross_cost", "Gross pay cost", { req: 1 }), F.amount("allowances", "Allowances", { def: "0" }), F.text("source", "Source (payroll system or summary reference)", { req: 1, min: 3 }), F.ev()],
    submit: (api, fid, b) => api.hcPost(`/facilities/${e(fid)}/staffing`, b), done: "Summary recorded. A different person must approve it before it counts." },
  report: { title: "Facility performance report", fields: [F.text("title", "Title", { req: 1, min: 3 }), F.date("period_start", "From", { req: 1 }), F.date("period_end", "To", { req: 1 })], submit: (api, fid, b) => api.hcPost(`/facilities/${e(fid)}/reports`, b), done: "Report created. Submitting freezes the figures." },
  access: { title: "Give someone access to facilities", fields: [F.text("user_id", "User id", { req: 1 }), { k: "facility_ids", label: "Facilities", type: "facilities" }], submit: (api, fid, b) => api.hcPut(`/access/${e(b.user_id)}`, { facility_ids: b.facility_ids || [] }), done: "Access saved." },
};
FORMS.access.extra = (v) => ((v.facility_ids || []).length ? null : "Choose at least one facility (or remove the person's access from the list).");

const mine = (row, userId) => ["created_by", "requested_by", "recorded_by", "submitted_by", "received_by"].some((k) => row[k] && row[k] === userId);
const isDraftish = (r) => ["DRAFT", "REJECTED"].includes(r.status);
const act = (id, label, perm, when, extra) => ({ id, label, perm, when, ...extra });
const call = (fn, done, note) => ({ call: fn, done, note });
const post = (path, bodyFn) => (api, row, note) => api.hcPost(path(row), bodyFn ? bodyFn(note, row) : { note: note || "" });

/** Every list in the workspace: how to load it, what to show, and what can be done to a row. */
export const SECTIONS = {
  facilities: { tab: "setup", title: "Facilities", need: "read", load: (api) => api.hcGet("/facilities"), create: { form: "facility", perm: "admin", label: "New facility" },
    cols: [["Ref", (r) => r.ref], ["Name", (r) => r.name], ["Type", (r) => label(r.type)], ["Region", (r) => r.region], ["Currency", (r) => r.currency], ["Status", (r) => label(r.status)]],
    actions: [act("view", "View", "read", () => true, { detail: (api, fid, r) => Promise.resolve([`${r.name} (${r.ref}): ${label(r.type)}, ${label(r.ownership)}, ${r.region}.`, `Currency ${r.currency}. Orders over budget are ${r.block_overspend ? "blocked" : "allowed"}. Quotes required: ${r.min_quotes}. Expiry warning: ${r.expiry_alert_days} days.`, `Departments: ${r.departments.map((d) => d.code + (d.active ? "" : " (inactive)")).join(", ") || "none"}.`]) }),
      act("edit", "Edit", "admin", () => true, { form: "facility" }),
      act("off", "Deactivate", "admin", (r) => r.status === "ACTIVE", { ...call((api, r, n) => api.hcPost(`/facilities/${e(r.id)}/status`, { active: false, note: n }), "Facility deactivated. Its history is kept.", { label: "reason", min: 3 }) }),
      act("on", "Reactivate", "admin", (r) => r.status === "INACTIVE", { ...call((api, r, n) => api.hcPost(`/facilities/${e(r.id)}/status`, { active: true, note: n }), "Facility reactivated.", { label: "reason", min: 3 }) })] },
  departments: { tab: "setup", title: "Departments", need: "read", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}`).then((f) => f.departments), create: { form: "department", perm: "admin", label: "New department" },
    cols: [["Code", (r) => r.code], ["Name", (r) => r.name], ["Cost centre", (r) => r.cost_centre || "—"], ["Active", (r) => (r.active ? "Yes" : "No")]],
    actions: [act("deact", "Deactivate", "admin", (r) => r.active, call((api, r, n, fid) => api.hcPost(`/facilities/${e(fid)}/departments/${e(r.id)}/active`, { active: false }), "Department deactivated.")),
      act("react", "Reactivate", "admin", (r) => !r.active, call((api, r, n, fid) => api.hcPost(`/facilities/${e(fid)}/departments/${e(r.id)}/active`, { active: true }), "Department reactivated."))] },
  access: { tab: "setup", title: "Who can see which facility", need: "admin", load: (api) => api.hcGet("/access").then((m) => Object.entries(m).map(([u, f]) => ({ id: u, user_id: u, facility_ids: f }))), create: { form: "access", perm: "admin", label: "Give access" },
    cols: [["User id", (r) => r.user_id], ["Facilities", (r, ctx) => r.facility_ids.map((i) => (ctx.facilities.find((f) => f.id === i) || {}).ref || i).join(", ")]],
    actions: [act("revoke", "Remove access", "admin", () => true, call((api, r) => api.hcPut(`/access/${e(r.user_id)}`, { facility_ids: [] }), "Access removed."))] },
  budgets: { tab: "budgets", title: "Budgets", need: "read", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/budgets`), create: { form: "budget", perm: "prepare", label: "New budget" },
    cols: [["Ref", (r) => r.ref], ["Name", (r) => r.name], ["Period", (r) => `${r.period_start} to ${r.period_end}`], ["Version", (r) => String(r.version)], ["Status", (r) => label(r.status)]],
    actions: [act("exec", "Budget versus actual", "read", (r) => r.status === "APPROVED" || r.status === "SUPERSEDED", { detail: (api, fid, r) => api.hcGet(`/facilities/${e(fid)}/budgets/${e(r.id)}/execution`).then((x) => [...x.rows.map((l) => `${l.dept} / ${label(l.category)}: budget ${l.budget}, spent ${l.spent}, committed ${l.committed}, available ${l.available}${l.used_pct ? ` (${l.used_pct}% used)` : ""}${l.overspent ? " - OVERSPENT" : ""}`), ...(x.unbudgeted || []).map((u) => `${u.dept} / ${label(u.category)}: NOT BUDGETED, spent ${u.spent}, committed ${u.committed}`), `Total on budget lines: budget ${x.totals.budget}, spent ${x.totals.spent}, committed ${x.totals.committed}, available ${x.totals.available}.`, ...(Number(x.totals.unbudgeted_spent) || Number(x.totals.unbudgeted_committed) ? [`Spending on lines with no budget: spent ${x.totals.unbudgeted_spent}, committed ${x.totals.unbudgeted_committed}. Total spent including this: ${x.totals.total_spent}.`] : []), x.note]) }),
      act("edit", "Edit", "prepare", isDraftish, { form: "budget" }),
      act("submit", "Submit", "prepare", isDraftish, call((api, r) => api.hcPost(`/budgets/${e(r.id)}/submit`), "Submitted. A different person must approve it.")),
      act("approve", "Approve", "approve", (r, u) => r.status === "SUBMITTED" && r.submitted_by !== u, call((api, r) => api.hcPost(`/budgets/${e(r.id)}/approve`), "Budget approved.")),
      act("reject", "Send back", "approve", (r, u) => r.status === "SUBMITTED" && r.submitted_by !== u, call((api, r, n) => api.hcPost(`/budgets/${e(r.id)}/reject`, { note: n }), "Sent back.", { label: "a note saying why", min: 3 })),
      act("revise", "Revise", "prepare", (r) => r.status === "APPROVED", { form: "revise" }), act("transfer", "Move between lines", "prepare", (r) => r.status === "APPROVED", { form: "transfer" }),
      act("decide-transfer", "Decide transfers", "approve", (r, u) => r.status === "APPROVED" && (r.transfers || []).some((t) => t.status === "PENDING" && t.requested_by !== u), call(async (api, r, n, fid, ok, u) => { const t = r.transfers.find((x) => x.status === "PENDING" && x.requested_by !== u); return api.hcPost(`/budgets/${e(r.id)}/transfers/${e(t.id)}/decide`, { ok: true, note: n }); }, "Transfer approved."))] },
  requisitions: { tab: "procurement", title: "Requisitions", need: "read", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/requisitions`), create: { form: "requisition", perm: "prepare", label: "New requisition" },
    cols: [["Ref", (r) => r.ref], ["Department", (r) => r.dept], ["Category", (r) => label(r.category)], ["Total", (r) => r.total], ["Quotes", (r) => String(r.quotes.length)], ["Status", (r) => label(r.status)]],
    actions: [act("submit", "Submit", "prepare", isDraftish, call((api, r) => api.hcPost(`/requisitions/${e(r.id)}/submit`), "Submitted for approval.")),
      act("approve", "Approve", "approve", (r, u) => r.status === "SUBMITTED" && r.requested_by !== u, call((api, r) => api.hcPost(`/requisitions/${e(r.id)}/decide`, { ok: true }), "Requisition approved.")),
      act("reject", "Send back", "approve", (r, u) => r.status === "SUBMITTED" && r.requested_by !== u, call((api, r, n) => api.hcPost(`/requisitions/${e(r.id)}/decide`, { ok: false, note: n }), "Sent back.", { label: "a note saying why", min: 3 })),
      act("quote", "Add quote", "prepare", (r) => ["DRAFT", "SUBMITTED", "APPROVED"].includes(r.status), { form: "quote" }), act("po", "Raise order", "prepare", (r) => r.status === "APPROVED", { form: "po" }),
      act("view", "Quotes", "read", (r) => r.quotes.length > 0, { detail: (api, fid, r) => Promise.resolve(r.quote_comparison.map((q) => `${q.supplier}: ${q.amount}${q.lowest ? " (lowest)" : ""}`)) })] },
  orders: { tab: "procurement", title: "Purchase orders", need: "read", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/pos`),
    cols: [["Ref", (r) => r.ref], ["Supplier", (r) => r.supplier], ["Total", (r) => r.total], ["Received", (r) => r.lines.map((l) => `${qtyText(l.received_qty)}/${qtyText(l.qty)}`).join(", ")], ["Status", (r) => label(r.status)]],
    actions: [act("approve", "Approve", "approve", (r, u) => r.status === "PENDING_APPROVAL" && r.created_by !== u, call((api, r, n) => api.hcPost(`/pos/${e(r.id)}/approve`, { exception_note: n }), "Order approved.", { label: "an exception reason (only needed when the order exceeds the available budget)", min: 0 })),
      act("receive", "Receive goods", "prepare", (r) => ["OPEN", "PARTIAL"].includes(r.status), { form: "receive" }), act("invoice", "Record invoice", "prepare", (r) => ["PARTIAL", "RECEIVED"].includes(r.status), { form: "invoice" }),
      act("cancel", "Cancel", "prepare", (r) => ["PENDING_APPROVAL", "OPEN"].includes(r.status), call((api, r, n) => api.hcPost(`/pos/${e(r.id)}/cancel`, { note: n }), "Order cancelled.", { label: "a reason", min: 3 })),
      act("view", "Lines", "read", () => true, { detail: (api, fid, r) => Promise.resolve([...r.lines.map((l) => `Line ${l.line_no}: ${l.description}, ${l.qty} at ${l.unit_price}, received ${l.received_qty}`), r.exception ? `Approved over budget: ${r.exception.note}` : "No budget exception."]) })] },
  goods: { tab: "procurement", title: "Goods received", need: "read", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/goods-receipts`), cols: [["Ref", (r) => r.ref], ["Order", (r) => r.po_ref], ["Delivery note", (r) => r.delivery_note], ["Date", (r) => r.date]], actions: [] },
  invoices: { tab: "procurement", title: "Supplier invoices", need: "read", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/invoices`),
    cols: [["Ref", (r) => r.ref], ["Supplier", (r) => r.supplier], ["Invoice no.", (r) => r.invoice_no], ["Amount", (r) => r.amount], ["Payable", (r) => r.net_payable], ["Match", (r) => (r.match.matched ? "Matched" : "Does not match")], ["Status", (r) => label(r.status)]],
    actions: [act("verify", "Verify", "approve", (r, u) => ["MATCHED", "EXCEPTION"].includes(r.status) && r.recorded_by !== u, call((api, r, n) => api.hcPost(`/invoices/${e(r.id)}/verify`, { exception_note: n }), "Invoice verified.", { label: "an exception reason (needed only when it does not match)", min: 0 })),
      act("approve-pay", "Approve payment", "approve", (r, u) => r.status === "VERIFIED" && r.recorded_by !== u && r.verified_by !== u, call((api, r) => api.hcPost(`/invoices/${e(r.id)}/approve-payment`), "Payment approved.")),
      act("pay", "Pay", "prepare", (r) => r.status === "PAYMENT_APPROVED", { form: "payment" }), act("credit", "Credit note", "approve", (r) => !["PAID", "CANCELLED"].includes(r.status), { form: "credit" }),
      act("cancel", "Cancel", "prepare", (r) => !["PAID", "CANCELLED"].includes(r.status), call((api, r, n) => api.hcPost(`/invoices/${e(r.id)}/cancel`, { note: n }), "Invoice cancelled.", { label: "a reason", min: 3 }))] },
  suppliers: { tab: "procurement", title: "Suppliers", need: "read", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/suppliers`), create: { form: "supplier", perm: "prepare", label: "New supplier" }, cols: [["Ref", (r) => r.ref], ["Name", (r) => r.name], ["Status", (r) => label(r.status)]],
    actions: [act("suspend", "Suspend", "prepare", (r) => r.status === "AUTHORISED", call((api, r, n) => api.hcPost(`/suppliers/${e(r.id)}/status`, { authorised: false, note: n }), "Supplier suspended.", { label: "a reason", min: 3 })),
      act("authorise", "Authorise", "prepare", (r) => r.status === "SUSPENDED", call((api, r, n) => api.hcPost(`/suppliers/${e(r.id)}/status`, { authorised: true, note: n }), "Supplier authorised.", { label: "a reason", min: 3 }))] },
  payables: { tab: "procurement", title: "Supplier payables ageing", need: "read", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/payables-ageing`).then((x) => [...x.rows.map((r) => ({ id: r.supplier, ...r })), { id: "_t", supplier: "Total", ...x.totals }]), actions: [],
    cols: [["Supplier", (r) => r.supplier], ["0-30", (r) => r["0-30"]], ["31-60", (r) => r["31-60"]], ["61-90", (r) => r["61-90"]], ["Over 90", (r) => r["over 90"]], ["Total", (r) => r.total]] },
  stock: { tab: "inventory", title: "Stock on hand", need: "read", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/stock`).then((x) => x.items.map((i) => ({ ...i, id: i.item_id, _alerts: x.alerts }))), actions: [
      act("issue", "Issue", "prepare", (r) => Number(r.on_hand) > 0, { form: "issue" }), act("transfer", "Transfer", "prepare", (r) => Number(r.on_hand) > 0, { form: "stocktransfer" }), act("adjust", "Adjust or write off", "prepare", (r) => r.lots.length > 0, { form: "adjust" }), act("count", "Count", "prepare", () => true, { form: "count" }),
      act("view", "Lots and history", "read", () => true, { detail: (api, fid, r) => api.hcGet(`/items/${e(r.item_id)}/movements`).then((m) => [`Costing: moving weighted average (${r.avg_cost}).`, ...r.lots.map((l) => `Lot ${l.batch || "-"} at ${l.location}: ${l.qty}${l.expiry ? ", expires " + l.expiry : ""}`), "History:", ...m.map((x) => `${String(x.at).slice(0, 10)} ${label(x.type)} ${x.qty} at ${x.unit_cost} (${x.ref})`)]) })],
    cols: [["SKU", (r) => r.sku], ["Item", (r) => r.name], ["On hand", (r) => `${qtyText(r.on_hand)} ${r.uom}`], ["Average cost", (r) => r.avg_cost], ["Value", (r) => r.value], ["Reorder at", (r) => r.reorder_level], ["Alert", (r) => (r.low ? "Low stock" : "")]] },
  items: { tab: "inventory", title: "Item catalogue", need: "read", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/items`), create: { form: "item", perm: "prepare", label: "New item" }, actions: [], cols: [["SKU", (r) => r.sku], ["Name", (r) => r.name], ["Category", (r) => label(r.category)], ["Unit", (r) => r.uom], ["Expiry tracked", (r) => (r.tracks_expiry ? "Yes" : "No")]] },
  adjustments: { tab: "inventory", title: "Adjustments and write-offs", need: "read", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/adjustments`),
    cols: [["Ref", (r) => r.ref], ["Item", (r) => r.item], ["Kind", (r) => label(r.kind)], ["Change", (r) => r.qty_delta], ["Status", (r) => label(r.status)]],
    actions: [act("approve", "Approve", "approve", (r, u) => r.status === "PENDING" && r.requested_by !== u, call((api, r) => api.hcPost(`/adjustments/${e(r.id)}/decide`, { ok: true }), "Adjustment approved.")),
      act("reject", "Refuse", "approve", (r, u) => r.status === "PENDING" && r.requested_by !== u, call((api, r, n) => api.hcPost(`/adjustments/${e(r.id)}/decide`, { ok: false, note: n }), "Adjustment refused.", { label: "a note saying why", min: 3 }))] },
  receipts: { tab: "revenue", title: "Receipts", need: "read", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/receipts`), create: { form: "receipt", perm: "prepare", label: "Record receipt" },
    cols: [["Reference", (r) => r.ref], ["Date", (r) => r.date], ["Category", (r) => label(r.service_category)], ["Amount", (r) => r.amount], ["Refunded", (r) => r.refunded], ["Method", (r) => label(r.method)]],
    actions: [act("refund", "Request refund", "prepare", () => true, { form: "refund" }),
      act("approve", "Approve refund", "approve", (r, u) => (r.refunds || []).some((x) => x.status === "PENDING" && x.requested_by !== u), call((api, r) => { const x = r.refunds.find((y) => y.status === "PENDING"); return api.hcPost(`/receipts/${e(r.id)}/refunds/${e(x.id)}/decide`, { ok: true }); }, "Refund approved."))] },
  fees: { tab: "revenue", title: "Fee schedule", need: "read", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/fees`), create: { form: "fee", perm: "prepare", label: "New price" }, cols: [["Ref", (r) => r.ref], ["Billing item", (r) => r.name], ["Category", (r) => label(r.service_category)], ["Price", (r) => r.price], ["From", (r) => r.effective_from], ["Status", (r) => label(r.status)]],
    actions: [act("retire", "Retire", "prepare", (r) => r.status === "ACTIVE", call((api, r, n) => api.hcPost(`/fees/${e(r.id)}/retire`, { note: n }), "Price retired.", { label: "a reason", min: 3 }))] },
  claims: { tab: "claims", title: "Claims register", need: "claims", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/claims`), create: { form: "claim", perm: "prepare", label: "New claim" },
    cols: [["Reference", (r) => r.ref], ["Payer", (r) => r.payer], ["Payer ref", (r) => r.external_ref || "—"], ["Month", (r) => r.service_month], ["Claimed", (r) => r.amount], ["Paid", (r) => r.paid], ["Outstanding", (r) => r.outstanding], ["Status", (r) => label(r.status)]],
    actions: [act("submit", "Submit", "prepare", (r) => r.status === "DRAFT", call((api, r) => api.hcPost(`/claims/${e(r.id)}/submit`), "Claim submitted.")), act("pay", "Record payment", "prepare", (r) => ["SUBMITTED", "PARTIALLY_PAID"].includes(r.status), { form: "claimpay" }),
      act("reject", "Rejected by payer", "prepare", (r) => r.status === "SUBMITTED", { form: "claimreject" }), act("resubmit", "Resubmit", "prepare", (r) => r.status === "REJECTED", { form: "claimresubmit" }),
      act("writeoff", "Ask to write off", "prepare", (r) => ["SUBMITTED", "PARTIALLY_PAID", "REJECTED"].includes(r.status) && !(r.writeoff && r.writeoff.status === "PENDING"), call((api, r, n) => api.hcPost(`/claims/${e(r.id)}/writeoff`, { reason: n }), "Write-off requested. A different person must approve it.", { label: "a reason", min: 10 })),
      act("approve-wo", "Approve write-off", "approve", (r, u) => !!(r.writeoff && r.writeoff.status === "PENDING" && r.writeoff.requested_by !== u), call((api, r) => api.hcPost(`/claims/${e(r.id)}/writeoff/decide`, { ok: true }), "Written off.")),
      act("reject-wo", "Refuse write-off", "approve", (r, u) => !!(r.writeoff && r.writeoff.status === "PENDING" && r.writeoff.requested_by !== u), call((api, r, n) => api.hcPost(`/claims/${e(r.id)}/writeoff/decide`, { ok: false, note: n }), "Write-off refused.", { label: "a note saying why", min: 3 })),
      act("view", "History", "claims", () => true, { detail: (api, fid, r) => Promise.resolve([...r.payments.map((p) => `Payment ${p.amount} on ${p.date} (${p.ref})`), ...r.history.map((h) => `${String(h.at).slice(0, 10)} ${label(h.event)}${h.note ? ": " + h.note : ""}`)]) })] },
  payers: { tab: "claims", title: "Payers", need: "read", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/payers`), create: { form: "payer", perm: "prepare", label: "New payer" }, cols: [["Ref", (r) => r.ref], ["Name", (r) => r.name], ["Type", (r) => label(r.kind)]],
    actions: [act("reconcile", "Reconcile statement", "claims", () => true, { form: "reconcile" })] },
  receivables: { tab: "claims", title: "Receivables ageing", need: "claims", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/receivables-ageing`).then((x) => [...x.rows.map((r) => ({ id: r.payer, ...r })), { id: "_t", payer: "Total", ...x.totals }]), actions: [],
    cols: [["Payer", (r) => r.payer], ["0-30", (r) => r["0-30"]], ["31-60", (r) => r["31-60"]], ["61-90", (r) => r["61-90"]], ["Over 90", (r) => r["over 90"]], ["Total", (r) => r.total]] },
  reconciliations: { tab: "claims", title: "Payer reconciliations", need: "claims", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/reconciliations`), cols: [["Ref", (r) => r.ref], ["Payer", (r) => r.payer], ["Period", (r) => `${r.start} to ${r.end}`], ["Our records", (r) => r.recorded_amount], ["Statement", (r) => r.statement_amount], ["Difference", (r) => r.difference], ["Status", (r) => label(r.status)]],
    actions: [act("resolve", "Explain difference", "prepare", (r) => r.status === "DIFFERENCE", { form: "resolve" })] },
  assets: { tab: "assets", title: "Equipment register", need: "read", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/assets`), create: { form: "asset", perm: "prepare", label: "New equipment" },
    cols: [["Ref", (r) => r.ref], ["Tag", (r) => r.tag], ["Name", (r) => r.name], ["Department", (r) => r.dept], ["Cost", (r) => r.cost], ["Condition", (r) => label(r.condition)], ["Next service", (r) => r.next_due || "—"], ["Status", (r) => label(r.status)]],
    actions: [act("maintain", "Request maintenance", "prepare", (r) => r.status === "ACTIVE", { form: "maintenance" }),
      act("retire", "Put forward for retirement", "prepare", (r) => r.status === "ACTIVE", call((api, r, n) => api.hcPost(`/assets/${e(r.id)}/retirement`, { reason: n }), "Retirement requested. A different person must approve it.", { label: "a reason", min: 10 })),
      act("retire-ok", "Approve retirement", "approve", (r, u) => r.status === "DISPOSAL_PENDING" && !!r.retirement && r.retirement.requested_by !== u, call((api, r) => api.hcPost(`/assets/${e(r.id)}/retirement/decide`, { ok: true }), "Retired. Post any disposal entry in the ledger.")),
      act("retire-no", "Refuse retirement", "approve", (r, u) => r.status === "DISPOSAL_PENDING" && !!r.retirement && r.retirement.requested_by !== u, call((api, r, n) => api.hcPost(`/assets/${e(r.id)}/retirement/decide`, { ok: false, note: n }), "Retirement refused.", { label: "a note saying why", min: 3 })),
      act("view", "Evidence", "read", () => true, { detail: (api, fid, r) => Promise.resolve([`Warranty: ${r.warranty_until || "none recorded"}${r.under_warranty ? " (in force)" : ""}.`, ...(r.evidence.length ? r.evidence.map((x) => `Evidence: ${x.filename}`) : ["No evidence linked."]), ...r.history.map((h) => `${String(h.at).slice(0, 10)} ${label(h.event)}`)]) })] },
  maintenance: { tab: "assets", title: "Maintenance", need: "read", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/maintenance`), cols: [["Ref", (r) => r.ref], ["Asset", (r) => `${r.tag} ${r.asset}`], ["Kind", (r) => label(r.kind)], ["Due", (r) => r.due_date], ["Cost", (r) => r.cost || "—"], ["Downtime (days)", (r) => (r.downtime_days == null ? "—" : String(r.downtime_days))], ["Status", (r) => label(r.status)]],
    actions: [act("complete", "Complete", "prepare", (r) => r.status === "REQUESTED", { form: "complete" }), act("cancel", "Cancel", "prepare", (r) => r.status === "REQUESTED", call((api, r, n) => api.hcPost(`/maintenance/${e(r.id)}/cancel`, { note: n }), "Request cancelled.", { label: "a reason", min: 3 }))] },
  due: { tab: "assets", title: "Maintenance due (next 30 days)", need: "read", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/maintenance-due`).then((x) => x.map((r, i) => ({ id: `${r.ref}-${i}`, ...r }))), actions: [], cols: [["Asset", (r) => `${r.tag} ${r.asset}`], ["Source", (r) => (r.kind === "SCHEDULE" ? "Service schedule" : "Open request")], ["Due", (r) => r.due], ["Overdue", (r) => (r.overdue ? "Yes" : "")]] },
  staffing: { tab: "staffing", title: "Staffing cost summaries", need: "staffing", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/staffing`).then((x) => x.rows), create: { form: "staffing", perm: "staffing", label: "New summary" },
    cols: [["Ref", (r) => r.ref], ["Department", (r) => r.dept], ["Month", (r) => r.month], ["Staff", (r) => String(r.headcount)], ["Gross cost", (r) => r.gross_cost], ["Allowances", (r) => r.allowances], ["Status", (r) => label(r.status)]],
    actions: [act("approve", "Approve", "approve", (r, u) => r.status === "SUBMITTED" && r.recorded_by !== u, call((api, r) => api.hcPost(`/staffing/${e(r.id)}/decide`, { ok: true }), "Summary approved.")),
      act("reject", "Send back", "approve", (r, u) => r.status === "SUBMITTED" && r.recorded_by !== u, call((api, r, n) => api.hcPost(`/staffing/${e(r.id)}/decide`, { ok: false, note: n }), "Sent back.", { label: "a note saying why", min: 3 }))] },
  reports: { tab: "reports", title: "Reports", need: "read", load: (api, fid) => api.hcGet(`/facilities/${e(fid)}/reports`), create: { form: "report", perm: "prepare", label: "New report" },
    cols: [["Ref", (r) => r.ref], ["Title", (r) => r.title], ["Period", (r) => `${r.period_start} to ${r.period_end}`], ["Version", (r) => String(r.version)], ["Status", (r) => label(r.status)]],
    actions: [act("submit", "Freeze and submit", "prepare", isDraftish, call((api, r) => api.hcPost(`/reports/${e(r.id)}/submit`), "Frozen and submitted. A different person must approve it.")),
      act("approve", "Approve", "approve", (r, u) => r.status === "SUBMITTED" && r.submitted_by !== u, call((api, r) => api.hcPost(`/reports/${e(r.id)}/decide`, { ok: true }), "Report approved.")),
      act("reject", "Send back", "approve", (r, u) => r.status === "SUBMITTED" && r.submitted_by !== u, call((api, r, n) => api.hcPost(`/reports/${e(r.id)}/decide`, { ok: false, note: n }), "Sent back.", { label: "a note saying why", min: 3 })),
      act("view", "View figures", "read", (r) => r.status !== "DRAFT", { detail: (api, fid, r) => api.hcGet(`/reports/${e(r.id)}`).then((x) => { const m = x.snapshot.dashboard.metrics; return [`Frozen ${String(x.snapshot.generated_at).slice(0, 10)}, version ${x.version}, fingerprint ${String(x.fingerprint).slice(0, 16)}...`, ...Object.values(m).map((k) => `${k.label}: ${k.value == null ? STATE_TEXT[k.state] || "—" : k.value}`), x.snapshot.claims_restricted ? "Claims figures are hidden from you." : ""].filter(Boolean); }) }),
      act("export", "Download CSV", "read", (r) => r.status === "APPROVED", { export: true })] },
};

export const TABS = [["dashboard", "Dashboard", "read"], ["setup", "Setup", "read"], ["budgets", "Budgets", "read"], ["procurement", "Procurement", "read"], ["inventory", "Inventory", "read"], ["revenue", "Revenue", "read"], ["claims", "Claims", "claims"], ["assets", "Equipment", "read"], ["staffing", "Staffing costs", "staffing"], ["reports", "Reports", "read"]];
export const sectionsOf = (tab) => Object.entries(SECTIONS).filter(([, s]) => s.tab === tab).map(([id, s]) => [id, s]);
export const visibleTabs = (c) => TABS.filter(([, , need]) => c[need]);
export const visibleSections = (tab, c) => sectionsOf(tab).filter(([, s]) => c[s.need]);
export const visibleActions = (sec, row, c, userId, ctx) => sec.actions.filter((a) => c[a.perm] && a.when(row, userId, ctx));
export const needsNote = (a, row) => (a.note ? (typeof a.note.min === "function" ? a.note.min(row) : a.note.min) : 0);
