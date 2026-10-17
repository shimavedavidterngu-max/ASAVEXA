/** Stage 14: match a grant to impact indicators by the programme reference typed on both records. Pure: no DOM, no network, no arithmetic.
 *  - A match is two people typing the same code. It is not a verified link and does not show the grant caused any change.
 *  - Every figure is a string the server worked out; nothing is recomputed here.
 *  - Not loaded (undefined) is "Not checked", never "none". No reading is "No confirmed reading yet", never zero. */
export const PROGRAMME_LIMIT = "Matched only by the programme reference typed on the grant and on the indicator. This does not show that the grant caused any change, and ASAVEXA does not verify the readings.";
export const STATE_WORDS = { NO_DATA: "No confirmed reading yet", ACHIEVED: "Target reached", ON_TRACK: "On track", BEHIND: "Behind the progress expected by today", OVERDUE: "Past the target date without reaching the target" };
const norm = (s) => String(s == null ? "" : s).trim().toLowerCase();

export function refProblem(v) {
  const s = String(v == null ? "" : v).trim();
  return s && (s.length < 2 || s.length > 40) ? "The programme reference must be 2 to 40 characters, or left empty." : null;
}

/** indicators: array (loaded), undefined (not checked). Returns {kind, ref, rows}. */
export function programmeLink(grant, indicators) {
  const ref = grant && grant.programme_ref ? String(grant.programme_ref).trim() : "";
  if (!ref) return { kind: "no-ref", ref: "", rows: [] };
  if (!Array.isArray(indicators)) return { kind: "unknown", ref, rows: [] };
  const rows = indicators.filter((x) => x.status === "APPROVED" && norm(x.programme_ref) === norm(ref)).map(rowOf);
  return { kind: rows.length ? "matched" : "none", ref, rows };
}

export function rowOf(x) {
  const state = STATE_WORDS[x.state] || "Not shown";
  const reading = x.latest_value == null ? "No confirmed reading yet." : `Latest confirmed reading ${x.latest_value} ${x.unit} (period ending ${x.latest_period_end}); ${x.progress_pct}% of the way from the baseline to the target.`;
  return { id: x.id, ref: x.ref, title: x.title, state: x.state, text: `${x.ref} ${x.title}: ${state}. ${reading}`, stale: !!x.stale };
}
