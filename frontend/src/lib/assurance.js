/** Pure helpers for the Assurance page. No DOM, no network. The server owns the vocabulary; this only orders and words it for display. */

export const FACET_ORDER = ["recorded", "supported", "reconciled", "reviewed", "approved", "independently_verified"];
export const SHORT_FACET = { recorded: "Recorded", supported: "Supported", reconciled: "Reconciled", reviewed: "Reviewed", approved: "Approved", independently_verified: "Independently verified" };
export const FLAG_TEXT = { CONTESTED: "Contested", INCOMPLETE: "Incomplete", REJECTED: "Rejected", EXPIRED: "Expired", RETIRED: "Retired" };
export const flagText = (f) => FLAG_TEXT[f] || String(f || "");

/** One table row per record type: the counts in the vocabulary's order, never a score. */
export function summaryRows(summary) {
  return ((summary && summary.records) || []).map((r) => ({
    type: r.type, label: r.label, available: r.available !== false, total: r.total,
    counts: FACET_ORDER.map((f) => (r.facets && r.facets[f]) || 0),
    flagged: Object.entries(r.flags || {}).filter(([, n]) => n > 0).map(([f, n]) => ({ flag: f, text: flagText(f), n })),
    unmapped: r.unmapped || 0, canRely: r.can_rely_on || 0, attention: r.attention || [],
  }));
}

/** What to say when a type could not be read. Silence would look like "nothing there". */
export const unavailableText = (row) => `${row.label}: could not be read just now, so no counts are shown.`;

export const percent = (n, total) => (total ? Math.round((n * 1000) / total) / 10 : 0);

/** "3 of 4 (75%)" or "none" for an empty type. */
export const relyText = (row) => (row.total ? `${row.canRely} of ${row.total} (${percent(row.canRely, row.total)}%)` : "none yet");
