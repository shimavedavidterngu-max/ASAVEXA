import { h } from "../lib/vdom.js";
import { ui, frame } from "../lib/wsKit.js";
import { TABS, ATTENTION_TONE, CLASSES, statusOf, words, canPrepare, canApprove, canDecideAsset, canReview, canGrant, canDecideReview, canDecideGrant, canRevoke, canRetire, ownText } from "../lib/datagov.js";

/** Data governance. A register of data assets, reviews and time-limited access grants. It holds no data and enforces no access. */
export function Datagov({ st, role, userId: me, loading, onRetry, actions: a }) {
  const k = ui(st, a, statusOf);
  return frame({ st, p: "dg", title: "Data governance", tabs: TABS, loading, onRetry, a, k,
    banner: "This workspace keeps a register of the data your organisation holds, who owns it, how it is classified, how long it is kept, when it was last reviewed and who has time-limited access. A different person approves each asset, confirms each review and decides each access grant. It holds none of the data, enforces no access, scans nothing and applies no law. Use reference codes, not names or personal details.",
    body: () => (st.tab === "overview" ? overview(st, k, role, a) : assets(st, k, role, me, a)) });
}

function overview(st, k, role, a) {
  const o = st.ov; if (!o) return k.none("Nothing loaded yet.");
  const c = o.counts, by = o.by_classification, s = o.setting;
  return h("div", {},
    k.card("What needs attention", "dg-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, k.Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : k.none("Nothing needs attention.")),
    k.card("Approved assets", "dg-summary", h("ul", {}, CLASSES.map((cl) => h("li", { "data-class": cl }, `${words(cl)}: ${by[cl]}`)), h("li", { id: "dg-personal" }, `Holding personal data: ${o.personal_data_assets}`), h("li", { id: "dg-active-grants" }, `Active access grants: ${o.active_grants}`), h("li", { id: "dg-ontime" }, `Reviewed on time: ${o.reviews_on_time_pct} percent`))),
    k.card("Counts", "dg-counts", h("ul", {}, [["Waiting for a decision", c.proposed], ["Approved", c.approved], ["Rejected", c.rejected], ["Retired", c.retired]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    k.card("Settings", "dg-setting", h("p", { id: "dg-setting-meaning" }, s.meaning),
      canApprove(role) && st.forms.setting ? h("div", {}, k.row(k.field("Flag grants that expire within this many days", "dg-set-warn", k.text("setting", "expiry_warning_days", "dg-set-warn")), k.field("Most active grants on a restricted asset", "dg-set-max", k.text("setting", "max_restricted_grants", "dg-set-max"))),
        k.formError("setting"), k.btn("Save settings", "dg-set-save", () => a.saveSetting(), "primary", st.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only an approver can change these settings.")),
    k.limits(o.limitations, "dg-limits"));
}

function assets(st, k, role, me, a) {
  const s = st.sel.asset;
  return h("div", {},
    k.card("Data assets", "dg-assets", st.assets.length ? st.assets.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-asset": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${x.name}`), " ", k.St(x.status), " ", k.Badge({ tone: x.classification === "RESTRICTED" ? "warn" : "neutral", label: words(x.classification) }), x.review_overdue ? [" ", k.Badge({ tone: "warn", label: "Review overdue" })] : null, x.expiring_grants ? [" ", k.Badge({ tone: "warn", label: "Grants expiring" })] : null),
      h("div", { style: "color: var(--ink-500);" }, `Owner ${x.owner_ref} · personal data: ${x.personal_data === "YES" ? "yes" : "no"} · kept ${x.retention_months} month(s) · reviewed every ${x.review_every_months} month(s)${x.next_review_due ? " · next review " + x.next_review_due : ""}`),
      k.btn(s && s.id === x.id ? "Hide details" : "Details", `dg-as-open-${x.ref}`, () => a.selectAsset(s && s.id === x.id ? null : x.id), "secondary", st.busy))) : k.none("No assets yet.")),
    s ? detail(st, k, role, me, a, s) : null,
    canPrepare(role) ? k.card("Propose a data asset", "dg-asset-card",
      k.row(k.field("Name", "dg-as-name", k.text("asset", "name", "dg-as-name")), k.field("Owner reference (a code, not a name)", "dg-as-owner", k.text("asset", "owner_ref", "dg-as-owner")),
        k.field("Classification", "dg-as-class", k.sel("asset", "classification", "dg-as-class", CLASSES.map((c) => [c, words(c)]))), k.field("Holds personal data", "dg-as-pd", k.sel("asset", "personal_data", "dg-as-pd", [["NO", "No"], ["YES", "Yes"]]))),
      k.row(k.field("Keep for (months)", "dg-as-ret", k.text("asset", "retention_months", "dg-as-ret")), k.field("Review every (months)", "dg-as-rev", k.text("asset", "review_every_months", "dg-as-rev"))),
      k.field("Description (what it is, no personal details)", "dg-as-desc", k.text("asset", "description", "dg-as-desc")), k.formError("asset"), k.btn("Propose asset", "dg-as-save", () => a.createAsset(), "primary", st.busy)) : null);
}

function detail(st, k, role, me, a, x) {
  const dec = canDecideAsset(x, role, me);
  return k.card(`${x.ref} · ${x.name}`, "dg-asset-detail",
    h("div", { id: "dg-asset-facts" }, `${x.description}. Classification ${words(x.classification)}; owner ${x.owner_ref}; kept ${x.retention_months} month(s); reviewed every ${x.review_every_months} month(s)${x.next_review_due ? "; next review due " + x.next_review_due : ""}; ${x.active_grants} active grant(s).`),
    x.review_overdue ? h("div", { id: "dg-overdue-note" }, "The next review is overdue. This is a flag for a person to look at.") : null, x.too_many_grants ? h("div", { id: "dg-many-note" }, "This restricted asset has more active grants than your limit.") : null,
    x.decision_note ? h("div", {}, `Decision note: ${x.decision_note}`) : null, x.retire_note ? h("div", { id: "dg-retired" }, `Retired: ${x.retire_note}`) : null,
    dec ? h("div", {}, h("h4", {}, "Decide"), k.noteBox(`as-${x.id}`, "Note (approval: optional, at least 10 characters if given; rejection: required)", "dg-as-note"),
      k.btn("Approve asset", "dg-as-approve", () => a.approveAsset(x.id), "primary", st.busy), " ", k.btn("Reject asset", "dg-as-reject", () => a.rejectAsset(x.id), "secondary", st.busy)) :
      (x.status === "PROPOSED" && canApprove(role) ? h("p", { id: "dg-as-waiting", style: "color: var(--ink-500);" }, ownText) : null),
    h("div", { id: "dg-reviews" }, h("h4", {}, "Reviews"), x.reviews.length ? x.reviews.map((r) => h("div", { "data-review": String(r.no) }, `#${r.no} ${r.review_date}: ${r.outcome} `, k.St(r.status), r.decision_note ? ` Note: ${r.decision_note}` : "",
      canDecideReview(x, r, role, me) ? h("div", {}, k.noteBox(`rv-${x.id}-${r.no}`, "Note (confirmation: optional, at least 10 characters if given; rejection: required)", `dg-rv-${r.no}-note`), k.btn("Confirm review", `dg-rv-${r.no}-confirm`, () => a.confirmReview(x.id, r.no), "primary", st.busy), " ", k.btn("Reject review", `dg-rv-${r.no}-reject`, () => a.rejectReview(x.id, r.no), "secondary", st.busy)) :
        (r.status === "PROPOSED" && canApprove(role) && x.status === "APPROVED" ? h("p", { className: "dg-own", style: "color: var(--ink-500);" }, ownText) : null))) : k.none("No reviews yet.")),
    canReview(x, role) ? h("div", {}, h("h4", {}, "Record a review"), k.row(k.field("Review date", "dg-rv-date", k.text("review", "review_date", "dg-rv-date", "YYYY-MM-DD")), k.field("Outcome", "dg-rv-out", k.text("review", "outcome", "dg-rv-out"))), k.formError("review"), k.btn("Record review", "dg-rv-save", () => a.addReview(x.id), "primary", st.busy)) : null,
    h("div", { id: "dg-grants" }, h("h4", {}, "Access grants"), x.grants.length ? x.grants.map((g) => h("div", { "data-grant": String(g.no) },
      `#${g.no} ${g.person_ref}: ${g.access_level === "WRITE" ? "write" : "read"} access from ${g.starts_on} to ${g.expires_on} (${g.purpose}) `, k.St(g.state), g.status === "APPROVED" && g.state !== "EXPIRED" && g.state !== "NOT_YET_ACTIVE" ? ` ${g.days_to_expiry} day(s) left` : "", g.decision_note ? ` Note: ${g.decision_note}` : "", g.revoke_note ? ` Revoked: ${g.revoke_note}` : "",
      canDecideGrant(x, g, role, me) || canRevoke(x, g, role) ? h("div", {}, k.noteBox(`gr-${x.id}-${g.no}`, "Note (approval: optional, at least 10 characters if given; rejection and revoking: required)", `dg-gr-${g.no}-note`),
        canDecideGrant(x, g, role, me) ? [k.btn("Approve grant", `dg-gr-${g.no}-approve`, () => a.approveGrant(x.id, g.no), "primary", st.busy), " ", k.btn("Reject grant", `dg-gr-${g.no}-reject`, () => a.rejectGrant(x.id, g.no), "secondary", st.busy)] : null,
        canRevoke(x, g, role) ? k.btn("Revoke grant", `dg-gr-${g.no}-revoke`, () => a.revokeGrant(x.id, g.no), "secondary", st.busy) : null) :
        (g.status === "PROPOSED" && canApprove(role) && x.status === "APPROVED" ? h("p", { className: "dg-own", style: "color: var(--ink-500);" }, ownText) : null))) : k.none("No grants yet.")),
    canGrant(x, role) ? h("div", {}, h("h4", {}, "Propose an access grant"),
      k.row(k.field("Person reference (a code, not a name)", "dg-gr-person", k.text("grant", "person_ref", "dg-gr-person")), k.field("Access", "dg-gr-level", k.sel("grant", "access_level", "dg-gr-level", [["READ", "Read"], ["WRITE", "Write"]])),
        k.field("Starts", "dg-gr-start", k.text("grant", "starts_on", "dg-gr-start", "YYYY-MM-DD")), k.field("Expires", "dg-gr-end", k.text("grant", "expires_on", "dg-gr-end", "YYYY-MM-DD"))),
      k.field("Purpose", "dg-gr-purpose", k.text("grant", "purpose", "dg-gr-purpose")), k.formError("grant"), k.btn("Propose grant", "dg-gr-save", () => a.addGrant(x.id), "primary", st.busy)) : null,
    canRetire(x, role) ? h("div", {}, h("h4", {}, "Retire the asset"), k.noteBox(`rt-${x.id}`, "Reason (at least 10 characters)", "dg-rt-note"), k.btn("Retire asset", "dg-rt-save", () => a.retireAsset(x.id), "secondary", st.busy)) : null,
    h("div", {}, h("h4", {}, "History"), k.hist(x.history)));
}
