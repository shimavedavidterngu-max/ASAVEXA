/** Pure helpers for the Professional Validation page: who may act, what is shown, and the request bodies. No DOM, no network. */

export const CONFIRMATIONS = [
  ["no_financial_interest", "I have no financial interest in this organisation (shares, loans, fees beyond this review)."],
  ["not_involved_in_preparing_records", "I was not involved in preparing the records or figures being reviewed."],
  ["no_close_personal_relationship", "I have no close personal or family relationship with people responsible for them."],
  ["no_other_threat_to_objectivity", "Nothing else threatens my objectivity in this review."],
];

export const STAGE_TONE = { UNCOVERED: "neutral", IN_PROGRESS: "warn", COVERED_CONCUR: "pass", COVERED_WITH_COMMENTS: "info", COVERED_LIMITED: "warn", COVERED_ADVERSE: "fail" };
export const OUTCOME_TONE = { INCOMPLETE: "warn", VALIDATED: "pass", VALIDATED_WITH_RESERVATIONS: "info", NOT_VALIDATED: "fail" };
export const SEVERITY_TONE = { CRITICAL: "fail", MAJOR: "fail", MINOR: "warn", ADVISORY: "neutral" };
export const CONCLUSION_TONE = { CONCURS: "pass", CONCURS_WITH_COMMENTS: "info", DISAGREES: "fail", UNABLE_TO_ASSESS: "warn" };

export const STAGE_STATUS_TEXT = {
  UNCOVERED: "No reviewer yet", IN_PROGRESS: "In progress", COVERED_CONCUR: "Reviewers concur", COVERED_WITH_COMMENTS: "Concur, with comments",
  COVERED_LIMITED: "Reviewer unable to assess", COVERED_ADVERSE: "A reviewer disagrees",
};
export const OUTCOME_TEXT = {
  INCOMPLETE: "Incomplete — not every stage has enough signed reviews", VALIDATED: "Validated by the reviewers",
  VALIDATED_WITH_RESERVATIONS: "Validated with reservations", NOT_VALIDATED: "Not validated — a reviewer disagrees",
};

export const humanize = (s) => (s ? String(s).replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase()) : "—");

/** Can the signed-in person act (declare, write, sign) for this reviewer? Linked reviewers act only as themselves; unlinked ones only through a manager. */
export function actingMode(me, reviewer) {
  if (!me || !reviewer) return "none";
  if (reviewer.user_id) return me.reviewer && me.reviewer.id === reviewer.id ? "self" : "none";
  return me.can_manage ? "on_behalf" : "none";
}

/** The reviewer's current position within an engagement stage. */
export function reviewState(detail, stage, reviewerId) {
  const all = (detail.reviews || []).filter((r) => r.stage === stage && r.reviewer_id === reviewerId);
  const draft = all.find((r) => r.status === "DRAFT") || null;
  const signed = all.filter((r) => r.status === "SIGNED").sort((a, b) => b.version - a.version)[0] || null;
  const decl = (detail.declarations || {})[reviewerId] || null;
  return { draft, signed, declaration: decl, independent: !!(decl && decl.independent), declared: !!decl };
}

/** Which panel members could be assigned to a stage: active, competent for it, and not already assigned. */
export function assignable(panel, guide, detail, stage) {
  const needed = ((guide && guide.stages) || []).find((s) => s.id === stage);
  const taken = new Set((detail.assignments || []).filter((a) => a.stage === stage).map((a) => a.reviewer_id));
  return (panel || []).filter((r) => r.active && !taken.has(r.id) && (!needed || r.specialisms.some((x) => needed.specialisms.includes(x))));
}

export function emptyObservation() { return { severity: "MINOR", text: "", recommendation: "" }; }

export function reviewForm(existing) {
  if (!existing) return { conclusion: "", scope_reviewed: "", basis: "", limitations: "", competence_confirmed: false, source_reference: "", observations: [] };
  return {
    conclusion: existing.conclusion || "", scope_reviewed: existing.scope_reviewed || "", basis: existing.basis || "", limitations: existing.limitations || "",
    competence_confirmed: !!existing.competence_confirmed, source_reference: existing.source_reference || "",
    observations: (existing.observations || []).map((o) => ({ id: o.id, severity: o.severity, text: o.text, recommendation: o.recommendation || "" })),
  };
}

export function reviewBody(stage, reviewerId, f, mode) {
  return {
    stage, reviewer_id: reviewerId, conclusion: f.conclusion || null, scope_reviewed: f.scope_reviewed || "", basis: f.basis || "", limitations: f.limitations || "",
    competence_confirmed: !!f.competence_confirmed, source_reference: mode === "on_behalf" ? (f.source_reference || "").trim() || null : null,
    observations: (f.observations || []).filter((o) => (o.text || "").trim()).map((o) => ({ ...(o.id ? { id: o.id } : {}), severity: o.severity, text: o.text.trim(), recommendation: (o.recommendation || "").trim() })),
  };
}

export function declarationBody(reviewerId, f, mode) {
  const conf = {}; for (const [k] of CONFIRMATIONS) conf[k] = !!(f.confirmations || {})[k];
  return { reviewer_id: reviewerId, independent: !!f.independent, details: (f.details || "").trim(), confirmations: conf, source_reference: mode === "on_behalf" ? (f.source_reference || "").trim() || null : null };
}

export function engagementBody(f, allStages) {
  const stages = (f.stages && f.stages.length ? f.stages : allStages);
  const n = parseInt(f.min_each, 10);
  const body = { title: (f.title || "").trim(), description: (f.description || "").trim(), as_of: (f.as_of || "").trim(), stages };
  if (n > 1) body.min_reviewers = Object.fromEntries(stages.map((s) => [s, n]));
  return body;
}

export function reviewerBody(f) {
  return {
    name: (f.name || "").trim(), email: (f.email || "").trim(), affiliation: (f.affiliation || "").trim(), specialisms: f.specialisms || [], user_id: f.user_id || null,
    credentials: [{ body: f.body || "", membership_no: (f.membership_no || "").trim(), jurisdiction: (f.jurisdiction || "").trim(), year_admitted: f.year_admitted ? parseInt(f.year_admitted, 10) : null }],
  };
}

/** Serious observations that still need a management reply, across effective signed reviews. */
export function openSeriousObservations(detail) {
  const out = [];
  for (const r of detail.reviews || []) {
    if (r.status !== "SIGNED") continue;
    for (const o of r.observations || []) if ((o.severity === "CRITICAL" || o.severity === "MAJOR") && !o.response) out.push({ review: r, observation: o });
  }
  return out;
}

export function credentialSummary(reviewer) {
  const c = reviewer.credentials || [];
  if (!c.length) return { tone: "warn", text: "No credentials recorded" };
  const v = c.filter((x) => x.status === "VERIFIED").length;
  if (v === c.length) return { tone: "pass", text: "All verified by a person" };
  if (v) return { tone: "info", text: `${v} of ${c.length} verified` };
  return { tone: "warn", text: "Declared only — not verified" };
}

/** The server sends bodies / specialisms / conclusions as {CODE: "description"}; accept a plain list too. Returns [[code, description], ...]. */
export function entries(x) {
  if (Array.isArray(x)) return x.map((c) => [c, humanize(c)]);
  return Object.entries(x || {});
}
