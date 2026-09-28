import { h } from "../lib/vdom.js";
import { DataTable } from "../components/DataTable.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { PermissionGate, allowed } from "../components/PermissionGate.js";
import { PERMISSIONS } from "../lib/permissions.js";

/**
 * Administration (Section 10). Organisation profile and membership
 * management — the real backend surface for this is exactly
 * auth.org_router (list/add/change-role/revoke members); there is no
 * separate "session administration" or "org-wide audit activity"
 * endpoint anywhere in the API (per-journal audit trail exists and is
 * already reachable from the Audit Workspace, but nothing aggregates
 * it at the organisation level). Rather than inventing one, this page
 * says so plainly (Section 5/13's "document rather than fabricate a
 * backend") instead of showing a fake activity feed.
 *
 * Every mutating action here is exposed only to a role actually
 * holding org:manage_users (Section 10: "Only expose actions to users
 * who have the corresponding permission") — and, same as everywhere
 * else in this frontend, the backend independently re-checks it
 * regardless of what this page decided to render.
 */
export function Administration({
  role, organisation, members, loading, error, onRetry,
  addForm, addError, addPending, onAddFieldChange, onSubmitAdd,
  onChangeRole, roleDrafts, onRoleDraftChange,
  onRevokeMember, currentUserId,
}) {
  if (!allowed(role, PERMISSIONS.ORG_MANAGE_USERS) && !allowed(role, PERMISSIONS.ORG_MANAGE_SETTINGS)) {
    return h("div", { className: "empty-state card" },
      h("h3", {}, "You don't have access to this"),
      h("p", {}, "Organisation management access is required to view Administration."));
  }

  return h(
    "div",
    {},
    h("h1", {}, "Administration"),
    h("p", { style: "color: var(--ink-500); margin-top: -8px; margin-bottom: 24px;" }, "Organisation profile and membership management."),
    error ? ErrorState({ message: error, onRetry }) : null,
    loading ? LoadingState() : h(
      "div",
      {},
      organisationCard(organisation),
      membersCard({ role, members, onChangeRole, roleDrafts, onRoleDraftChange, onRevokeMember, currentUserId }),
      PermissionGate({ role, permission: PERMISSIONS.ORG_MANAGE_USERS },
        addMemberCard({ addForm, addError, addPending, onAddFieldChange, onSubmitAdd })),
      h(
        "div", { className: "card" }, h("h3", {}, "Audit activity"),
        EmptyState({ title: "Not available at the organisation level", message: "Per-transaction audit history is available from the Audit Workspace by looking up a specific journal. There is no aggregated organisation-wide activity feed in the current API." })
      )
    )
  );
}

function organisationCard(organisation) {
  if (!organisation) return EmptyState({ title: "Organisation not found" });
  return h(
    "div", { className: "card" },
    h("h2", {}, organisation.name),
    h("div", { className: "mono", style: "font-size:12.5px; color: var(--ink-500);" }, organisation.id),
    h("div", { style: "margin-top:4px; color: var(--ink-500); font-size:13px;" }, `Created ${organisation.created_at}`)
  );
}

function membersCard({ role, members, onChangeRole, roleDrafts, onRoleDraftChange, onRevokeMember, currentUserId }) {
  const roles = ["OWNER", "ADMINISTRATOR", "ACCOUNTANT", "FINANCE_OFFICER", "AUDITOR", "REVIEWER", "APPROVER", "MANAGER", "EXTERNAL_AUDITOR", "INVESTOR_REVIEWER", "DONOR", "REGULATOR", "READ_ONLY"];
  return h(
    "div", { className: "card" }, h("h2", {}, "Members"),
    DataTable({
      columns: [
        { key: "user_id", label: "User" },
        { key: "role", label: "Role" },
        { key: "status", label: "Status" },
        {
          key: "actions", label: "",
          render: (m) => PermissionGate({ role, permission: PERMISSIONS.ORG_MANAGE_USERS },
            m.user_id === currentUserId
              ? h("span", { style: "color: var(--ink-500); font-size:12.5px;" }, "You cannot change your own role.")
              : h(
                  "div", { style: "display:flex; gap:4px; align-items:center;" },
                  h("select", { value: (roleDrafts && roleDrafts[m.user_id]) || m.role, onChange: (e) => onRoleDraftChange(m.user_id, e.target.value) },
                    roles.map((r) => h("option", { value: r }, r))),
                  h("button", { className: "btn btn-secondary", onClick: () => onChangeRole(m.user_id, (roleDrafts && roleDrafts[m.user_id]) || m.role) }, "Update"),
                  m.status === "ACTIVE" ? h("button", { className: "btn btn-danger", onClick: () => onRevokeMember(m.user_id) }, "Revoke") : null
                )),
        },
      ],
      rows: members || [], emptyTitle: "No members yet",
    })
  );
}

function addMemberCard({ addForm, addError, addPending, onAddFieldChange, onSubmitAdd }) {
  const f = addForm || {};
  const roles = ["OWNER", "ADMINISTRATOR", "ACCOUNTANT", "FINANCE_OFFICER", "AUDITOR", "REVIEWER", "APPROVER", "MANAGER", "EXTERNAL_AUDITOR", "INVESTOR_REVIEWER", "DONOR", "REGULATOR", "READ_ONLY"];
  return h(
    "div", { className: "card" }, h("h3", {}, "Add a member"),
    addError ? h("div", { className: "alert alert-error" }, addError) : null,
    h(
      "form", { onSubmit: (e) => { e.preventDefault(); onSubmitAdd(); } },
      h("div", { style: "display:flex; gap:12px; flex-wrap:wrap; align-items:flex-end;" },
        h("div", { className: "field" }, h("label", {}, "User id"), h("input", { value: f.user_id || "", required: true, onInput: (e) => onAddFieldChange("user_id", e.target.value) })),
        h("div", { className: "field" }, h("label", {}, "Role"),
          h("select", { value: f.role || "READ_ONLY", onChange: (e) => onAddFieldChange("role", e.target.value) },
            roles.map((r) => h("option", { value: r }, r)))),
        h("button", { type: "submit", className: "btn btn-primary", disabled: addPending }, addPending ? "Adding…" : "Add member")
      )
    )
  );
}
