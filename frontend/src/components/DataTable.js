import { h } from "../lib/vdom.js";
import { EmptyState } from "./DataState.js";

/**
 * DataTable — a thin, generic wrapper around the `.data-table` CSS
 * class already defined in design-system.css (used ad hoc by
 * AuditWorkspace/Dashboard's own inline markup). Seven new areas each
 * need a sortable-by-nothing, filterable-by-caller results table
 * (accounts, journals, evidence, bank transactions, reconciliations,
 * controls, findings, remediations, members) with the same shape:
 * columns + rows + an empty state. Rather than hand-writing that table
 * scaffold seven times (Section 22: "duplicated API logic" /
 * inconsistent UI), it lives here once.
 *
 * `columns`: [{ key, label, render?(row) -> vnode|string, align? }]
 * `rows`: plain array of row objects (already paginated/filtered by
 * the caller — Section 16: pagination/filtering stay server-side,
 * this component never re-slices data itself).
 * `onRowClick(row)`: optional — makes rows keyboard-activatable too.
 */
export function DataTable({ columns, rows, emptyTitle, emptyMessage, onRowClick, getRowKey }) {
  if (!rows || rows.length === 0) {
    return EmptyState({ title: emptyTitle || "No records", message: emptyMessage });
  }
  const clickable = Boolean(onRowClick);
  return h(
    "div",
    { className: "table-scroll" },
    h(
      "table",
      { className: "data-table" },
      h("thead", {}, h("tr", {}, columns.map((c) => h("th", { style: c.align === "right" ? "text-align:right;" : undefined }, c.label)))),
      h(
        "tbody",
        {},
        rows.map((row, i) =>
          h(
            "tr",
            {
              tabindex: clickable ? "0" : undefined,
              role: clickable ? "button" : undefined,
              style: clickable ? "cursor:pointer;" : undefined,
              onClick: clickable ? () => onRowClick(row) : undefined,
              onKeydown: clickable
                ? (e) => {
                    if (e.key === "Enter" || e.key === " ") onRowClick(row);
                  }
                : undefined,
              key: getRowKey ? getRowKey(row) : i,
            },
            columns.map((c) =>
              h(
                "td",
                { className: c.align === "right" ? "amount" : undefined },
                c.render ? c.render(row) : row[c.key]
              )
            )
          )
        )
      )
    )
  );
}
