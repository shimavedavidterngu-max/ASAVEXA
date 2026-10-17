/** Pure helpers for the Proof Links page (Stage 13). No DOM, no network. The server decides who may do what; this only words things and hides buttons that could not work. */

export const LINK_STATUS = { ACTIVE: { tone: "pass", label: "Active" }, DISPUTED: { tone: "warn", label: "Disputed" }, RETIRED: { tone: "neutral", label: "Retired" }, SUPERSEDED: { tone: "neutral", label: "Superseded" } };
export const linkStatus = (s) => LINK_STATUS[s] || { tone: "neutral", label: s || "—" };
export const GAP_STATUS = { OPEN: { tone: "warn", label: "Still missing" }, FILLED: { tone: "pass", label: "Filled" }, WAIVED: { tone: "neutral", label: "Waived" } };
export const gapStatus = (s) => GAP_STATUS[s] || { tone: "neutral", label: s || "—" };
export const basisText = (b) => (b === "SYSTEM" ? "Recorded by ASAVEXA while doing other work" : "Recorded by a person");

export const typeLabel = (vocab, code) => ((vocab && vocab.types) || []).find((t) => t.code === code)?.label || String(code || "");
export const relationOf = (vocab, code) => ((vocab && vocab.relations) || []).find((r) => r.code === code) || null;
export const nodeText = (vocab, n) => (n ? `${typeLabel(vocab, n.type)}: ${n.label}` : "");

/** Relations that can join these two kinds. Either kind may be empty to mean "not chosen yet". */
export function relationsFor(vocab, fromType, toType) {
  return ((vocab && vocab.relations) || []).filter((r) => (!fromType || r.from.includes(fromType)) && (!toType || r.to.includes(toType)));
}
/** Kinds a record of `fromType` can be linked TO, by any relation. */
export function targetTypes(vocab, fromType) {
  const out = new Set();
  for (const r of relationsFor(vocab, fromType, "")) r.to.forEach((t) => out.add(t));
  return ((vocab && vocab.types) || []).filter((t) => out.has(t.code));
}

/** One plain sentence for a link: "Evidence: a.pdf provides evidence for Finding: …". */
export function linkSentence(vocab, l) {
  const r = relationOf(vocab, l.relation);
  return `${nodeText(vocab, l.from)} ${r ? r.label : l.relation} ${nodeText(vocab, l.to)}`;
}

export const EMPTY_LINK = { from_type: "", from_id: "", to_type: "", to_id: "", relation: "", note: "" };
export const EMPTY_GAP = { relation: "", expected_type: "", note: "" };

export function linkProblem(f) {
  if (!f.from_type || !f.from_id) return "Choose the first record.";
  if (!f.relation) return "Choose how the two records are related.";
  if (!f.to_type || !f.to_id) return "Choose the second record.";
  if (f.from_type === f.to_type && f.from_id === f.to_id) return "A record cannot be linked to itself.";
  return "";
}
export function linkPayload(f) {
  const problem = linkProblem(f);
  if (problem) return { problem };
  return { body: { from_ref: { type: f.from_type, id: f.from_id }, to_ref: { type: f.to_type, id: f.to_id }, relation: f.relation, note: (f.note || "").trim() } };
}
export function gapPayload(focus, f) {
  if (!focus) return { problem: "Open a record first; the missing link belongs to it." };
  if (!f.relation) return { problem: "Choose the kind of link that is missing." };
  if (!(f.note || "").trim()) return { problem: "Say what is missing and why it matters." };
  const body = { from_ref: { type: focus.type, id: focus.id }, relation: f.relation, note: f.note.trim() };
  if (f.expected_type) body.expected_type = f.expected_type;
  return { body };
}

/** Buttons a person can usefully press on a link. The server still checks; this just avoids offering what cannot work. */
export function linkActions(l, me, canPrepare, canApprove, candidates = 0) {
  const out = [];
  if (!l) return out;
  if (l.status === "ACTIVE" && canApprove && !l.confirmed_by && l.created_by !== me) out.push("confirm");
  if (l.status === "ACTIVE" && canPrepare) out.push("dispute");
  if (l.status === "DISPUTED" && canApprove && l.disputed_by !== me) out.push("reinstate");
  if ((l.status === "ACTIVE" || l.status === "DISPUTED") && canPrepare && candidates > 0) out.push("supersede");
  if (l.status !== "RETIRED" && l.status !== "SUPERSEDED" && canPrepare) out.push("retire");
  return out;
}
export const ACTION_TEXT = { confirm: "Confirm", dispute: "Dispute", reinstate: "Reinstate", supersede: "Replace with newer link", retire: "Retire" };
export const ACTION_NOTICE = { confirm: "Confirmed by you.", dispute: "Marked as disputed.", reinstate: "Reinstated.", supersede: "Superseded. Both links stay in the history.", retire: "Retired. It stays in the history." };
/** confirm needs no reason; the others do. */
export const needsReason = (a) => a !== "confirm";
export const canWaive = (g, me, canApprove) => !!g && canApprove && g.status === "OPEN" && g.created_by !== me;

export const sameNode = (a, b) => !!a && !!b && a.type === b.type && a.id === b.id;
/** Nodes of a graph other than the focus, in the order the server gave them. */
export const otherNodes = (g) => ((g && g.nodes) || []).filter((n) => !sameNode(n, g.focus));
export const confirmedText = (l) => (l.confirmed_by ? "Confirmed by a second person" : l.status === "ACTIVE" ? "Not yet confirmed by a second person" : "");
/** Other active links that start from the same record as this one: the only valid replacements. */
export const supersedeCandidates = (l, links) => (l && (l.status === "ACTIVE" || l.status === "DISPUTED") ? (links || []).filter((x) => x.id !== l.id && x.status === "ACTIVE" && sameNode(x.from, l.from)) : []);
