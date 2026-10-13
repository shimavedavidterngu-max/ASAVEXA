/** Pure helpers for the Agents page. No DOM, no network. The server decides; this only words it and hides buttons that could not work. */

export const DECISION_INFO = {
  ALLOW: { tone: "pass", label: "Allowed" }, REQUIRE_APPROVAL: { tone: "warn", label: "Needs approval" }, DENY: { tone: "fail", label: "Refused" },
};
export const decisionInfo = (d) => DECISION_INFO[d] || { tone: "neutral", label: d || "—" };

export const STATE_INFO = {
  PENDING: { tone: "warn", label: "Waiting for a person" }, APPROVED: { tone: "pass", label: "Approved, not yet used" }, REJECTED: { tone: "fail", label: "Rejected" },
  USED: { tone: "neutral", label: "Used once" }, EXPIRED: { tone: "neutral", label: "Expired" }, NOT_NEEDED: { tone: "pass", label: "No approval needed" }, REFUSED: { tone: "fail", label: "Refused" },
};
export const stateInfo = (s) => STATE_INFO[s] || { tone: "neutral", label: s || "—" };

export const AGENT_STATUS = { PROPOSED: { tone: "warn", label: "Proposed" }, ACTIVE: { tone: "pass", label: "Active" }, SUSPENDED: { tone: "warn", label: "Suspended" }, RETIRED: { tone: "neutral", label: "Retired" } };
export const agentStatus = (s) => AGENT_STATUS[s] || { tone: "neutral", label: s || "—" };

const ORDER = { ALLOW: 0, REQUIRE_APPROVAL: 1, DENY: 2 };
/** The stricter choices open to an organisation for one action. Never offers a looser one. */
export const stricterChoices = (effective) => Object.keys(ORDER).filter((k) => ORDER[k] > (ORDER[effective] ?? 2));

/** Actions an agent can be given: everything except what the policy forbids for every agent. */
export const grantable = (actions) => (actions || []).filter((a) => a.builtin !== "DENY");

export function agentActions(agent, me, canPrepare, canApprove) {
  if (!agent || !canApprove) return [];
  const out = [];
  if ((agent.status === "PROPOSED" || agent.status === "SUSPENDED") && me !== agent.proposed_by) out.push("activate");
  if (agent.status === "ACTIVE") out.push("suspend");
  if (agent.status !== "RETIRED") out.push("retire");
  return out;
}

export const canResolve = (d, me, canApprove) => !!(d && canApprove && d.state === "PENDING" && d.requested_by !== me);
export const needsIndependent = (d, me) => !!(d && d.state === "PENDING" && d.requested_by === me);

export function agentFormProblem(f) {
  if (!f.name.trim()) return "Give the agent a name.";
  if (!f.purpose.trim()) return "Say what the agent is for.";
  if (!f.owner) return "Choose who owns the agent.";
  if (!f.actions || f.actions.length === 0) return "Choose at least one action.";
  return null;
}
export const EMPTY_AGENT = { name: "", purpose: "", owner: "", actions: [] };
