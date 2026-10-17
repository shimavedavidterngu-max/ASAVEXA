import { h } from "../lib/vdom.js";
import { ui, frame } from "../lib/wsKit.js";
import { TABS, KINDS, ATTENTION_TONE, statusOf, words, canPrepare, canApprove, canDecidePolicy, canRetirePolicy, canDecideRequest, canWithdraw, hasDecided, ownText, decidedText, stepLine } from "../lib/approvals.js";

/** Approval workflows. Policies with up to three steps and requests that move through them. An approval here is a record; nothing else is blocked or triggered by it. */
export function Approvals({ st, role, userId: me, loading, onRetry, actions: a }) {
  const k = ui(st, a, statusOf);
  return frame({ st, p: "apw", title: "Approval workflows", tabs: TABS, loading, onRetry, a, k,
    banner: "This workspace keeps approval policies (up to three steps, each needing a set number of different people) and the requests that move through them. The person who submitted a request can never decide it, and nobody decides the same request twice. An approval here is a record: nothing is paid, bought or signed because of it, and nothing else is blocked by it. Use codes, not names or bank details.",
    body: () => (st.tab === "overview" ? overview(st, k, role, a) : st.tab === "requests" ? requests(st, k, role, me, a) : policies(st, k, role, me, a)) });
}

function overview(st, k, role, a) {
  const o = st.ov; if (!o) return k.none("Nothing loaded yet.");
  const p = o.policies, r = o.requests;
  return h("div", {},
    k.card("What needs attention", "apw-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, k.Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", x.kind === "NO_ACTIVE_POLICY" ? x.text : `${x.count} ${x.text}`))) : k.none("Nothing needs attention.")),
    k.card("Amounts by currency (currencies are never added together)", "apw-currency", o.by_currency.length ? h("ul", {}, o.by_currency.map((t) => h("li", { "data-currency": t.currency }, `${t.currency}: waiting ${t.pending}, approved ${t.approved}`))) : k.none("No requests with an amount yet.")),
    k.card("Counts", "apw-counts", h("ul", {}, h("li", {}, `Policies: waiting for a decision ${p.proposed}, active ${p.active}, rejected ${p.rejected}, retired ${p.retired}`), h("li", {}, `Requests: waiting for approval ${r.pending}, approved ${r.approved}, rejected ${r.rejected}, withdrawn ${r.withdrawn}`))),
    k.settingCard("apw", role, canApprove, "A request has waited too long after this many days", "stale_days"),
    k.limits(o.limitations, "apw-limits"));
}

function requests(st, k, role, me, a) {
  const s = st.sel.request, active = st.policies.filter((p) => p.status === "ACTIVE");
  return h("div", {},
    k.card("Requests", "apw-requests", st.requests.length ? st.requests.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-request": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${x.title}`), " ", k.St(x.status), x.stale ? [" ", k.Badge({ tone: "warn", label: `Waiting ${x.waiting_days} day(s)` })] : null),
      h("div", { style: "color: var(--ink-500);" }, `Reference ${x.request_ref} · ${x.policy_name} (${x.policy_ref})${x.amount ? ` · ${x.amount} ${x.currency}` : ""}${x.status === "PENDING" ? ` · step ${x.current_step} of ${x.step_count}: ${x.current_label}, ${x.still_needed} more approval(s) needed` : ""}`),
      k.btn(s && s.id === x.id ? "Hide details" : "Details", `apw-rq-open-${x.ref}`, () => a.selectRequest(s && s.id === x.id ? null : x.id), "secondary", st.busy))) : k.none("No requests yet.")),
    s ? requestDetail(st, k, role, me, a, s) : null,
    canPrepare(role) ? k.card("Submit a request", "apw-request-card",
      active.length ? h("div", {}, k.row(k.field("Policy", "apw-rq-policy", k.sel("request", "policy_id", "apw-rq-policy", [["", "Choose a policy…"], ...active.map((p) => [p.id, `${p.ref} · ${p.name}`])])), k.field("Title", "apw-rq-title", k.text("request", "title", "apw-rq-title")), k.field("Reference (a code)", "apw-rq-ref", k.text("request", "request_ref", "apw-rq-ref"))),
        k.row(k.field("Amount (optional)", "apw-rq-amount", k.text("request", "amount", "apw-rq-amount")), k.field("Currency (with an amount)", "apw-rq-cur", k.text("request", "currency", "apw-rq-cur"))),
        k.field("Description (at least 10 characters)", "apw-rq-desc", k.text("request", "description", "apw-rq-desc")), k.formError("request"), k.btn("Submit request", "apw-rq-save", () => a.submitRequest(), "primary", st.busy)) :
        h("p", { id: "apw-rq-nopolicy", style: "color: var(--ink-500);" }, "No policy is active yet, so no request can be submitted. Propose a policy first; a different person must activate it.")) : null);
}

function requestDetail(st, k, role, me, a, x) {
  const dec = canDecideRequest(x, role, me), wd = canWithdraw(x, role, me);
  return k.card(`${x.ref} · ${x.title}`, "apw-request-detail",
    h("div", { id: "apw-facts" }, `Reference ${x.request_ref}. ${words(x.request_kind)}, under ${x.policy_name} (${x.policy_ref}).${x.amount ? ` Amount ${x.amount} ${x.currency}.` : ""} ${x.description}`),
    h("div", { id: "apw-progress" }, x.status === "PENDING" ? `Waiting at step ${x.current_step} of ${x.step_count} (${x.current_label}); ${x.still_needed} more approval(s) needed at this step. ${x.approvals_so_far} of ${x.approvals_in_total} approvals recorded in total.` : `${x.approvals_so_far} of ${x.approvals_in_total} approvals were recorded.`),
    x.decision_note ? h("div", { id: "apw-decision" }, `Decision note: ${x.decision_note}`) : null, x.withdraw_note ? h("div", { id: "apw-withdrawn" }, `Withdrawn: ${x.withdraw_note}`) : null,
    h("ol", { id: "apw-steps" }, x.steps.map((s) => h("li", { "data-step": s.no }, stepLine(s, x.current_step), s.decisions.length ? h("ul", {}, s.decisions.map((d) => h("li", {}, `${words(d.decision)} on ${d.on} by ${d.by}${d.note ? `: ${d.note}` : ""}`))) : null))),
    dec ? h("div", {}, h("h4", {}, "Decide this step"), k.noteBox(`rq-${x.id}`, "Note (approval: optional, at least 10 characters if given; rejection: required)", "apw-rq-note"),
      k.btn("Approve", "apw-rq-approve", () => a.approveRequest(x.id), "primary", st.busy), " ", k.btn("Reject request", "apw-rq-reject", () => a.rejectRequest(x.id), "secondary", st.busy)) :
      (x.status === "PENDING" && canApprove(role) ? h("p", { id: "apw-rq-waiting", style: "color: var(--ink-500);" }, x.submitted_by === me ? ownText : hasDecided(x, me) ? decidedText : "") : null),
    wd ? h("div", {}, h("h4", {}, "Withdraw"), k.noteBox(`rq-${x.id}`, "Reason (at least 10 characters)", "apw-rq-wd-note"), k.btn("Withdraw request", "apw-rq-withdraw", () => a.withdrawRequest(x.id), "secondary", st.busy)) : null,
    h("div", {}, h("h4", {}, "History"), k.hist(x.history)));
}

function policies(st, k, role, me, a) {
  const s = st.sel.policy;
  return h("div", {},
    k.card("Policies", "apw-policies", st.policies.length ? st.policies.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-policy": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${x.name}`), " ", k.St(x.status), x.requests_under_way ? [" ", k.Badge({ tone: "info", label: `${x.requests_under_way} request(s) under way` })] : null),
      h("div", { style: "color: var(--ink-500);" }, `${words(x.request_kind)} · ${x.steps.length} step(s) · ${x.people_per_request} approval(s) in total`),
      k.btn(s && s.id === x.id ? "Hide details" : "Details", `apw-pl-open-${x.ref}`, () => a.selectPolicy(s && s.id === x.id ? null : x.id), "secondary", st.busy))) : k.none("No policies yet.")),
    s ? policyDetail(st, k, role, me, a, s) : null,
    canPrepare(role) ? k.card("Propose a policy", "apw-policy-card",
      k.row(k.field("Name", "apw-pl-name", k.text("policy", "name", "apw-pl-name")), k.field("Kind of request", "apw-pl-kind", k.sel("policy", "request_kind", "apw-pl-kind", KINDS.map((t) => [t, words(t)])))),
      ...[1, 2, 3].map((i) => k.row(k.field(`Step ${i} label${i > 1 ? " (optional)" : ""}`, `apw-pl-s${i}l`, k.text("policy", `s${i}l`, `apw-pl-s${i}l`)), k.field(`Step ${i}: different people needed (1 to 5)`, `apw-pl-s${i}n`, k.text("policy", `s${i}n`, `apw-pl-s${i}n`)))),
      k.field("Description (at least 10 characters)", "apw-pl-desc", k.text("policy", "description", "apw-pl-desc")), k.formError("policy"), k.btn("Propose policy", "apw-pl-save", () => a.createPolicy(), "primary", st.busy)) : null);
}

function policyDetail(st, k, role, me, a, x) {
  const dec = canDecidePolicy(x, role, me);
  return k.card(`${x.ref} · ${x.name}`, "apw-policy-detail",
    h("div", { id: "apw-pl-facts" }, `${words(x.request_kind)}. ${x.description}`),
    h("ol", { id: "apw-pl-steps" }, x.steps.map((s) => h("li", { "data-step": s.no }, `${s.label}: ${s.required} different ${s.required === 1 ? "person" : "people"}`))),
    x.decision_note ? h("div", {}, `Decision note: ${x.decision_note}`) : null, x.retire_note ? h("div", { id: "apw-pl-retired" }, `Retired: ${x.retire_note}`) : null,
    dec ? h("div", {}, h("h4", {}, "Decide"), k.noteBox(`pl-${x.id}`, "Note (activation: optional, at least 10 characters if given; rejection: required)", "apw-pl-note"),
      k.btn("Activate policy", "apw-pl-activate", () => a.activatePolicy(x.id), "primary", st.busy), " ", k.btn("Reject policy", "apw-pl-reject", () => a.rejectPolicy(x.id), "secondary", st.busy)) :
      (x.status === "PROPOSED" && canApprove(role) ? h("p", { id: "apw-pl-waiting", style: "color: var(--ink-500);" }, "You proposed this, so a different person must decide it.") : null),
    canRetirePolicy(x, role) ? h("div", {}, h("h4", {}, "Retire"), k.noteBox(`pl-${x.id}`, "Reason (at least 10 characters)", "apw-pl-retire-note"), k.btn("Retire policy", "apw-pl-retire", () => a.retirePolicy(x.id), "secondary", st.busy)) : null,
    h("div", {}, h("h4", {}, "History"), k.hist(x.history)));
}
