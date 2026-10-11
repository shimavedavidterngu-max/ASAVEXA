import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";

/** Tax Compliance helpers. No tax rate lives in the frontend: every rate shown here arrived from a rule on the server. */
export const TABS = [["countries", "Countries"], ["rules", "Rules"], ["calculator", "Calculator"], ["calendar", "Calendar"]];
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canPrepare = (role) => has(role, PERMISSIONS.TAX_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.TAX_APPROVE);

export const RULE_STATE = { DRAFT: { tone: "neutral", label: "Draft" }, SUBMITTED: { tone: "info", label: "Waiting for review" }, APPROVED: { tone: "pass", label: "In force" }, REJECTED: { tone: "fail", label: "Sent back" }, SUPERSEDED: { tone: "neutral", label: "Replaced" } };
export const ruleState = (s) => RULE_STATE[s] || { tone: "neutral", label: s || "—" };
export const CAL_STATE = { OVERDUE: { tone: "fail", label: "Overdue" }, DUE_SOON: { tone: "warn", label: "Due soon" }, UPCOMING: { tone: "neutral", label: "Upcoming" }, FILED: { tone: "pass", label: "Filed (recorded by a person)" } };
export const calState = (s) => CAL_STATE[s] || { tone: "neutral", label: s };

export function num(v) {
  if (v == null || v === "") return "—";
  const m = /^(-?)(\d+)(?:\.(\d+))?$/.exec(String(v));
  if (!m) return String(v);
  return `${m[1]}${m[2].replace(/\B(?=(\d{3})+(?!\d))/g, ",")}${m[3] ? "." + m[3] : ""}`;
}

export const emptyRule = (country = "") => ({ id: "", replaces: "", country, tax_type: "VAT_GST", name: "", method: "FLAT", rate: "", brackets: [{ from: "0", up_to: "", rate: "" }], rounding: "HALF_UP",
  effective_from: "", effective_to: "", authority: "", source_title: "", source_url: "", notes: "", filing_on: false, frequency: "QUARTERLY", due_days: "30", period_anchor: "", form: "" });

export function ruleProblem(f) {
  if (!f.country) return "Choose a country.";
  if ((f.name || "").trim().length < 3) return "Give the rule a name (at least 3 characters).";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(f.effective_from || "")) return "Enter the date the rule starts, like 2026-01-01.";
  if (f.effective_to && !/^\d{4}-\d{2}-\d{2}$/.test(f.effective_to)) return "The end date must look like 2026-12-31, or be left empty.";
  if (f.effective_to && f.effective_to < f.effective_from) return "The end date cannot be before the start date.";
  if ((f.authority || "").trim().length < 2) return "Name the tax authority.";
  if ((f.source_title || "").trim().length < 5) return "Say which law, section or notice this comes from.";
  if (!/^https?:\/\/\S+\.\S+$/.test((f.source_url || "").trim())) return "Add a link to the official source (starting with https://).";
  if (f.method === "FLAT") {
    const r = String(f.rate).trim();
    if (!/^\d+(\.\d+)?$/.test(r) || +r > 100) return "The rate must be a number from 0 to 100.";
  } else {
    let expect = 0;
    for (const [i, b] of f.brackets.entries()) {
      const lo = String(b.from).trim(), hi = String(b.up_to).trim(), rate = String(b.rate).trim();
      if (!/^\d+(\.\d+)?$/.test(lo) || !/^\d+(\.\d+)?$/.test(rate) || +rate > 100) return `Band ${i + 1}: start and rate must be numbers (rate 0 to 100).`;
      if (+lo !== expect) return `Band ${i + 1} must start at ${expect}, where the previous band ends.`;
      if (hi === "") { if (i !== f.brackets.length - 1) return "Only the last band can have no end."; } else {
        if (!/^\d+(\.\d+)?$/.test(hi) || +hi <= +lo) return `Band ${i + 1} must end above where it starts.`;
        expect = +hi;
      }
    }
  }
  if (f.filing_on && !/^\d+$/.test(String(f.due_days).trim())) return "Days after the period ends must be a whole number.";
  return null;
}

export function ruleBody(f) {
  const body = { country: f.country, tax_type: f.tax_type, name: f.name.trim(), method: f.method, rounding: f.rounding, effective_from: f.effective_from, effective_to: f.effective_to || null,
    authority: f.authority.trim(), source_title: f.source_title.trim(), source_url: f.source_url.trim(), notes: (f.notes || "").trim(), filing: null, replaces: f.replaces || null };
  if (f.method === "FLAT") body.rate = String(f.rate).trim();
  else body.brackets = f.brackets.map((b) => ({ from: String(b.from).trim(), up_to: String(b.up_to).trim() === "" ? null : String(b.up_to).trim(), rate: String(b.rate).trim() }));
  if (f.filing_on) body.filing = { frequency: f.frequency, due_days_after_period_end: String(f.due_days).trim(), period_anchor: f.period_anchor || f.effective_from, form: (f.form || "").trim() };
  return body;
}

export function ruleForm(r) {
  return { id: r.id, replaces: "", country: r.country, tax_type: r.tax_type, name: r.name, method: r.method, rate: r.rate || "", brackets: (r.brackets || [{ from: "0", up_to: "", rate: "" }]).map((b) => ({ from: b.from, up_to: b.up_to == null ? "" : b.up_to, rate: b.rate })),
    rounding: r.rounding, effective_from: r.effective_from, effective_to: r.effective_to || "", authority: r.authority, source_title: r.source_title, source_url: r.source_url, notes: r.notes || "",
    filing_on: !!r.filing, frequency: r.filing ? r.filing.frequency : "QUARTERLY", due_days: r.filing ? String(r.filing.due_days_after_period_end) : "30", period_anchor: r.filing ? r.filing.period_anchor : "", form: r.filing ? r.filing.form : "" };
}

export function ruleActions(rule, role, userId) {
  const s = rule ? rule.status : null, mine = !!rule && (rule.submitted_by === userId || rule.created_by === userId);
  return {
    edit: canPrepare(role) && (s === "DRAFT" || s === "REJECTED"),
    submit: canPrepare(role) && (s === "DRAFT" || s === "REJECTED"),
    discard: canPrepare(role) && (s === "DRAFT" || s === "REJECTED"),
    replace: canPrepare(role) && s === "APPROVED",
    decide: canApprove(role) && s === "SUBMITTED" && !mine,
    ownSubmission: canApprove(role) && s === "SUBMITTED" && mine,
  };
}

export const calcProblem = (f) => {
  if (!f.rule_id) return "Choose a rule in force.";
  if (!/^\d+(\.\d+)?$/.test(String(f.amount).trim())) return "The amount must be a positive number.";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(f.date || "")) return "Enter the date the amount relates to, like 2026-03-31.";
  return null;
};
export const rateText = (r) => (r.method === "FLAT" ? `${r.rate}%` : `${(r.brackets || []).length} bands`);
export const todayIso = (d = new Date()) => d.toISOString().slice(0, 10);
