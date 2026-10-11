import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { ProgressBar } from "../components/Onboarding.js";
import { CATEGORIES, MONTHS, canSetUp, canOpenPeriod, suggestedWorkspaces } from "../lib/onboarding.js";
import { roleLabel } from "../lib/home.js";
import { WORKSPACE_TONE } from "../lib/analysis.js";

/**
 * Guided set-up of the organisation that is open: details, first accounting period, workspaces.
 * Everything is saved through the real endpoints; each step can be skipped and picked up again later.
 * Choosing a workspace here never changes anyone's permissions; roles are set only by the server.
 */
const Badge = ({ tone, label }) => h("span", { className: `badge badge-${tone || "neutral"}` }, label);
const fieldErr = (id, msg) => (msg ? h("div", { className: "ob-err", id: `${id}-err`, role: "alert" }, msg) : null);
const aria = (id, errors, key) => ({ "aria-invalid": errors[key] ? "true" : undefined, "aria-describedby": errors[key] ? `${id}-err` : undefined });

function settingsStep(p) {
  const { st } = p, f = st.form, e = st.errors || {};
  return h("form", { className: "card ob-card", id: "su-settings", noValidate: true, onSubmit: (ev) => { ev.preventDefault(); p.onSaveSettings(); } },
    h("h2", { id: "su-h-settings" }, "Organisation details"),
    h("p", { className: "hm-muted" }, "Only what is needed to start. The currency and financial year shape your first accounting period. The reporting framework is chosen separately under Standards & Policies."),
    st.error ? h("div", { className: "alert alert-error", id: "su-error", role: "alert" }, st.error) : null,
    h("div", { className: "field" }, h("label", { for: "su-legal" }, "Legal name"),
      h("input", { id: "su-legal", value: f.legal_name, maxlength: "200", ...aria("su-legal", e, "legal_name"), onInput: (ev) => p.onField("legal_name", ev.target.value) }), fieldErr("su-legal", e.legal_name)),
    h("div", { className: "field" }, h("label", { for: "su-type" }, "Kind of organisation"),
      h("select", { id: "su-type", ...aria("su-type", e, "organisation_type"), onChange: (ev) => p.onField("organisation_type", ev.target.value) },
        h("option", { value: "", selected: !f.organisation_type }, "Choose one…"), CATEGORIES.map((c) => h("option", { value: c, selected: f.organisation_type === c }, c))), fieldErr("su-type", e.organisation_type)),
    h("div", { className: "field" }, h("label", { for: "su-country" }, "Country"),
      st.countries && st.countries.length
        ? h("select", { id: "su-country", ...aria("su-country", e, "country"), onChange: (ev) => p.onCountry(ev.target.value) },
          h("option", { value: "", selected: !f.country }, "Choose a country…"), st.countries.map((c) => h("option", { value: c.code, selected: f.country === c.code }, c.name)))
        : h("input", { id: "su-country", value: f.country, placeholder: "Country name or code", ...aria("su-country", e, "country"), onInput: (ev) => p.onCountry(ev.target.value) }),
      st.countries && st.countries.length ? null : h("div", { className: "ob-fine", id: "su-country-note" }, "The country list could not be loaded, so type it in."),
      fieldErr("su-country", e.country)),
    h("div", { className: "ob-row" },
      h("div", { className: "field" }, h("label", { for: "su-currency" }, "Reporting currency"),
        h("input", { id: "su-currency", value: f.base_currency, maxlength: "3", autocapitalize: "characters", ...aria("su-currency", e, "base_currency"), onInput: (ev) => p.onField("base_currency", ev.target.value.toUpperCase(), true) }),
        h("div", { className: "ob-fine" }, "Filled in from the country. You can change it."), fieldErr("su-currency", e.base_currency)),
      h("div", { className: "field" }, h("label", { for: "su-month" }, "Financial year starts in"),
        h("select", { id: "su-month", ...aria("su-month", e, "fiscal_year_start_month"), onChange: (ev) => p.onField("fiscal_year_start_month", ev.target.value) },
          h("option", { value: "", selected: !f.fiscal_year_start_month }, "Choose a month…"), MONTHS.map((m, i) => h("option", { value: String(i + 1), selected: String(f.fiscal_year_start_month) === String(i + 1) }, m))), fieldErr("su-month", e.fiscal_year_start_month))),
    h("div", { className: "ob-actions" },
      h("button", { type: "submit", className: "btn btn-primary", id: "su-save-settings", disabled: st.saving }, st.saving ? "Saving…" : "Save and continue"),
      h("button", { type: "button", className: "btn btn-secondary", id: "su-skip-settings", onClick: () => p.onStep("period"), disabled: st.saving }, "Skip for now")));
}

function periodStep(p) {
  const { st, role } = p, e = st.errors || {}, f = st.period, have = st.periods || [];
  if (have.length) {
    return h("section", { className: "card ob-card", id: "su-period-have", "aria-labelledby": "su-h-period" },
      h("h2", { id: "su-h-period" }, "Accounting period"),
      h("p", { id: "su-period-msg" }, `This organisation already has ${have.length} accounting period${have.length === 1 ? "" : "s"}: ${have.slice(-3).map((x) => x.name).join(", ")}${have.length > 3 ? ", …" : ""}.`),
      nav(p, "workspaces", "Continue"));
  }
  if (!canOpenPeriod(role)) {
    return h("section", { className: "card ob-card", id: "su-period-denied", "aria-labelledby": "su-h-period" },
      h("h2", { id: "su-h-period" }, "Accounting period"),
      h("p", {}, "Opening an accounting period needs the “manage periods” permission, which your role does not have. Ask an administrator to do this step."),
      nav(p, "workspaces", "Continue"));
  }
  return h("form", { className: "card ob-card", id: "su-period", noValidate: true, onSubmit: (ev) => { ev.preventDefault(); p.onSavePeriod(); } },
    h("h2", { id: "su-h-period" }, "Open your first accounting period"),
    h("p", { className: "hm-muted" }, "Filled in from the financial-year month you chose. Change the dates if your first period is different."),
    st.error ? h("div", { className: "alert alert-error", id: "su-error", role: "alert" }, st.error) : null,
    h("div", { className: "field" }, h("label", { for: "su-pname" }, "Period name"),
      h("input", { id: "su-pname", value: f.name, maxlength: "60", ...aria("su-pname", e, "name"), onInput: (ev) => p.onPeriodField("name", ev.target.value) }), fieldErr("su-pname", e.name)),
    h("div", { className: "ob-row" },
      h("div", { className: "field" }, h("label", { for: "su-start" }, "First day"), h("input", { id: "su-start", type: "date", value: f.start, ...aria("su-start", e, "start"), onInput: (ev) => p.onPeriodField("start", ev.target.value) }), fieldErr("su-start", e.start)),
      h("div", { className: "field" }, h("label", { for: "su-end" }, "Last day"), h("input", { id: "su-end", type: "date", value: f.end, ...aria("su-end", e, "end"), onInput: (ev) => p.onPeriodField("end", ev.target.value) }), fieldErr("su-end", e.end))),
    h("div", { className: "ob-actions" },
      h("button", { type: "submit", className: "btn btn-primary", id: "su-save-period", disabled: st.saving }, st.saving ? "Opening…" : "Open the period and continue"),
      h("button", { type: "button", className: "btn btn-secondary", id: "su-skip-period", onClick: () => p.onStep("workspaces"), disabled: st.saving }, "Skip for now"),
      h("button", { type: "button", className: "btn btn-secondary", id: "su-back-period", onClick: () => p.onStep("settings"), disabled: st.saving }, "Back")));
}

function nav(p, next, label) {
  return h("div", { className: "ob-actions" },
    h("button", { className: "btn btn-primary", id: "su-next", onClick: () => p.onStep(next) }, label),
    h("button", { className: "btn btn-secondary", id: "su-back", onClick: () => p.onStep(next === "workspaces" ? "settings" : "period") }, "Back"));
}

function workspacesStep(p) {
  const { st, role } = p;
  const cat = (st.profile && st.profile.organisation_type) || st.form.organisation_type;
  const list = suggestedWorkspaces(cat, st.workspaces, role);
  return h("section", { className: "ob-final", id: "su-workspaces", "aria-labelledby": "su-h-ws" },
    h("div", { className: "card ob-card" },
      h("h2", { id: "su-h-ws" }, "Where to start"),
      h("p", { className: "hm-muted", id: "su-ws-note" }, "These are suggestions for this kind of organisation. Nothing is switched on or off here: you can open any workspace your role allows, and the server decides what your role allows."),
      !cat ? h("p", { id: "su-ws-nocat" }, "Choose the kind of organisation in the details step to see suggestions.")
        : !list.length ? h("p", { id: "su-ws-none" }, "The workspace list could not be loaded, so there are no suggestions right now. Open Professional Workspaces from the menu.")
        : h("div", { className: "hm-ws-grid", id: "su-ws-grid" }, list.map((w) => h("article", { className: "card hm-ws", "data-ws": w.id },
          h("div", { className: "hm-ws-head" }, h("h3", {}, w.name), w.status ? Badge({ tone: WORKSPACE_TONE[w.status], label: w.status }) : null),
          w.canOpen ? h("button", { className: "btn btn-secondary", id: `su-open-${w.id}`, onClick: () => p.onGo(w.path) }, "Open") : h("p", { className: "hm-muted" }, "Not available to your role."))))),
    h("div", { className: "card ob-card", id: "su-role" },
      h("h3", {}, "Your access"),
      h("p", {}, `You are signed in as ${roleLabel(role)} in this organisation. Roles are set only by the server and cannot be changed from this page. To give a colleague access, add them under Administration.`)),
    h("div", { className: "ob-actions" },
      h("button", { className: "btn btn-primary", id: "su-finish", onClick: p.onFinish }, "Go to my dashboard"),
      h("button", { className: "btn btn-secondary", id: "su-standards", onClick: () => p.onGo("/standards") }, "Choose the reporting framework"),
      h("button", { className: "btn btn-secondary", id: "su-back-ws", onClick: () => p.onStep("period") }, "Back")));
}

export function Setup(p) {
  const { st, role } = p;
  const head = h("div", {}, h("h1", { id: "su-h1" }, "Set up this organisation"),
    h("p", { className: "hm-sub" }, "Three short steps. Each saves as you go, and you can leave and come back."));
  if (!canSetUp(role)) {
    return h("div", { className: "su", id: "setup" }, head,
      h("div", { className: "card empty-state", id: "su-denied" }, h("h3", {}, "You cannot change this organisation's settings"),
        h("p", {}, "Setting up an organisation needs the “manage settings” permission, which your role does not have. Ask an administrator."),
        h("button", { className: "btn btn-primary", id: "su-home", onClick: () => p.onGo("/") }, "Back to the dashboard")));
  }
  if (st.loading) return h("div", { className: "su", id: "setup" }, head, LoadingState());
  if (st.loadError) return h("div", { className: "su", id: "setup" }, head, ErrorState({ message: st.loadError, onRetry: p.onRetry }));
  const stepId = { settings: "settings", period: "period", workspaces: "workspaces" }[st.step] || "settings";
  const body = stepId === "settings" ? settingsStep(p) : stepId === "period" ? periodStep(p) : workspacesStep(p);
  return h("div", { className: "su", id: "setup" }, head, ProgressBar({ current: stepId }), st.notice ? h("div", { className: "alert alert-info", id: "su-notice", role: "status" }, st.notice) : null, body);
}
