import { label, qtyText } from "./health.js";

/**
 * Health administration: follow the money for ONE department.   authorised -> purchased -> delivered -> unresolved
 * Finance and administration only. There is no patient field anywhere in this file or in the records it reads.
 * Honest by construction:
 *  - It only restates what the server recorded (statuses, references, quantities and amounts as text). It adds and compares no money.
 *  - A missing link is shown as missing; a list the page could not load (undefined) is shown as "Not checked", never as clean.
 *  - Deliveries are recorded by a person. This view does not confirm that anything arrived, and it does not buy or pay anything.
 * A step is { key, state: linked|missing|pending|unknown, stateLabel, title, meta }. The coarse state sets the SHAPE; stateLabel is the words.
 */
export const HEALTH_VOCAB = { authorised: "Authorised", purchased: "Purchased", delivered: "Delivered", unresolved: "Still unresolved" };
export const HEALTH_ORDER = ["authorised", "purchased", "delivered", "unresolved"];

const step = (key, state, stateLabel, title, meta) => ({ key, state, stateLabel: stateLabel || null, title: title || null, meta: meta || null });
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const ofDept = (list, deptId, poDept) => (Array.isArray(list) ? list.filter((x) => (poDept ? poDept[x.po_id] : x.dept_id) === deptId) : undefined);
const NOTE = "Recorded by a person; ASAVEXA has not confirmed that anything arrived.";

export function authorisedStep(deptId, exec) {
  if (exec === undefined) return step("authorised", "unknown");
  if (exec === null) return step("authorised", "missing", "No approved budget", null, "No approved budget covers this period. Approve a budget to see what is authorised.");
  const rows = (exec.rows || []).filter((r) => r.dept_id === deptId);
  if (!rows.length) return step("authorised", "missing", "No budget line", null, `Budget ${exec.ref} has no line for this department.`);
  const meta = rows.map((r) => `${label(r.category)}: authorised ${r.budget}, committed ${r.committed}, spent ${r.spent}, available ${r.available}${r.overspent ? " (overspent)" : ""}`).join(". ") + ".";
  return step("authorised", "linked", "Approved", `Budget ${exec.ref}, ${plural(rows.length, "line", "lines")}`, meta);
}

export function purchasedStep(orders) {
  if (orders === undefined) return step("purchased", "unknown");
  const live = orders.filter((o) => o.status !== "CANCELLED");
  if (!live.length) return step("purchased", "missing", "No orders", null, "No purchase order has been raised for this department.");
  const waiting = live.filter((o) => o.status === "PENDING_APPROVAL");
  const title = plural(live.length, "order", "orders");
  const exc = live.filter((o) => o.exception).map((o) => o.ref);
  const meta = exc.length ? `Approved over budget with a recorded reason: ${exc.join(", ")}.` : null;
  if (waiting.length) return step("purchased", "pending", "Waiting for approval", title, `${plural(waiting.length, "order is", "orders are")} waiting for a different person to approve it. ${meta || ""}`.trim());
  return step("purchased", "linked", "Approved", title, meta);
}

export function deliveredStep(orders) {
  if (orders === undefined) return step("delivered", "unknown");
  const approved = orders.filter((o) => ["OPEN", "PARTIAL", "RECEIVED"].includes(o.status));
  if (!approved.length) return step("delivered", "missing", "Nothing to deliver yet", null, "No approved order is waiting for goods.");
  const full = approved.filter((o) => o.status === "RECEIVED"), part = approved.filter((o) => o.status === "PARTIAL");
  const title = `${full.length} of ${plural(approved.length, "order", "orders")} fully received`;
  if (full.length === approved.length) return step("delivered", "linked", "Fully received", title, NOTE);
  if (full.length || part.length) return step("delivered", "pending", "Partly received", title, `${NOTE} ${part.length ? `Part received: ${part.map((o) => o.ref).join(", ")}.` : ""}`.trim());
  return step("delivered", "missing", "Nothing received yet", title, NOTE);
}

export function unresolvedStep(deptId, exec, invoices) {
  if (invoices === undefined) return step("unresolved", "unknown");
  const bad = invoices.filter((i) => i.status === "EXCEPTION"), wait = invoices.filter((i) => i.status === "MATCHED");
  const over = exec && Array.isArray(exec.rows) ? exec.rows.filter((r) => r.dept_id === deptId && r.overspent) : [];
  const unb = exec && Array.isArray(exec.unbudgeted) ? exec.unbudgeted.filter((u) => u.dept_id === deptId) : [];
  const parts = [];
  bad.forEach((i) => parts.push(`${i.ref} (${i.invoice_no}) amount ${i.amount} does not match: ${i.match && i.match.allowed != null ? `only ${i.match.allowed} has been received and not yet invoiced` : "more than was received"}`));
  wait.forEach((i) => parts.push(`${i.ref} (${i.invoice_no}) amount ${i.amount} matches and is waiting for a different person to verify it`));
  over.forEach((r) => parts.push(`${label(r.category)} is over its budget line`));
  unb.forEach((u) => parts.push(`${label(u.category)} has spending with no budget line`));
  if (!parts.length) return step("unresolved", "linked", "Nothing open", "No open items", "No unmatched invoice, unverified invoice or overspent line was found for this department.");
  const title = plural(parts.length, "open item", "open items");
  return step("unresolved", bad.length || over.length || unb.length ? "missing" : "pending", bad.length ? "Does not match" : over.length || unb.length ? "Needs a decision" : "Waiting for verification", title, parts.join(". ") + ".");
}

/** The whole trace for one department. `exec` is the budget-execution record (null = no approved budget, undefined = not loaded). */
export function buildDeptTrace({ dept, exec, pos, invoices }) {
  if (!dept) return null;
  const orders = ofDept(pos, dept.id);
  const poDept = Array.isArray(pos) ? Object.fromEntries(pos.map((p) => [p.id, p.dept_id])) : undefined;
  const invs = poDept && invoices !== undefined ? ofDept(invoices, dept.id, poDept) : undefined;
  const steps = [authorisedStep(dept.id, exec), purchasedStep(orders), deliveredStep(orders), unresolvedStep(dept.id, exec, invs)];
  return { dept, steps, orders: orders || [], invoices: invs || [], lines: exec && Array.isArray(exec.rows) ? exec.rows.filter((r) => r.dept_id === dept.id) : [], ordersKnown: orders !== undefined, invoicesKnown: invs !== undefined };
}

export const receivedText = (l) => `${qtyText(l.received_qty)}/${qtyText(l.qty)}`;
