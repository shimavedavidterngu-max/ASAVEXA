/**
 * A minimal hyperscript + mount utility. No framework, no build step,
 * no npm dependency (see docs/frontend-runtime-verification.md for
 * why: npm's registry is unreachable in this sandbox, so any
 * npm-installed framework was off the table).
 *
 * The key design choice: h(...) returns a plain, inert JS object (a
 * "vnode") — {tag, props, children} — never touching `document`.
 * Every component in this app is a pure function `Component(props) ->
 * vnode`, which means component LOGIC is fully testable in plain
 * Node (no DOM implementation available here — no jsdom, since that
 * too needs npm install). Only mount() below touches `document`, and
 * it is small and simple enough to trust without being unit-testable
 * itself in this environment; it can only be exercised in a real
 * browser. See docs/frontend-runtime-verification.md, "Verified vs
 * pending."
 */

export function h(tag, props, ...children) {
  return { tag, props: props || {}, children: children.flat(Infinity) };
}

/** Convenience: a fragment with no wrapping element. */
export function Fragment(children) {
  return { tag: null, props: {}, children: (children || []).flat(Infinity) };
}

/**
 * Renders a vnode tree into a real DOM node. Browser-only — nothing in
 * this function is unit-tested in this environment; component *logic*
 * is tested by asserting on the vnode tree h() returns, before it
 * ever reaches this function.
 */
export function mount(vnode, container) {
  // This app re-renders by replacing the whole tree (no diffing). Left
  // as-is, that destroys everything the browser keeps on the DOM nodes
  // themselves: keyboard focus and cursor position (typing lost focus
  // after every character), scroll position, and — critically — the
  // file a user just chose in an <input type="file"> (a file input's
  // value can never be set from script, so a rebuilt input always
  // shows "No file chosen"). Capture those before replacing the tree
  // and restore them after.
  const saved = captureUiState(container);
  container.replaceChildren();
  const node = render(vnode);
  if (node) container.appendChild(node);
  restoreUiState(container, saved);
  return node;
}

function pathFrom(container, el) {
  const path = [];
  let n = el;
  while (n && n !== container) {
    const parent = n.parentNode;
    if (!parent) return null;
    path.unshift(Array.prototype.indexOf.call(parent.childNodes, n));
    n = parent;
  }
  return n === container ? path : null;
}

function nodeAt(container, path) {
  let n = container;
  for (const i of path) {
    n = n && n.childNodes ? n.childNodes[i] : null;
    if (!n) return null;
  }
  return n;
}

const SCROLL_SELECTOR = ".app-main, .table-scroll, .modal";

function captureUiState(container) {
  const state = { files: [], focus: null, scrolls: [], windowY: 0 };
  if (typeof document === "undefined") return state;
  try {
    state.windowY = window.scrollY || 0;
    container.querySelectorAll('input[type="file"]').forEach((input) => {
      if (input.files && input.files.length > 0) {
        const path = pathFrom(container, input);
        if (path) state.files.push({ path, node: input, name: input.files[0].name });
      }
    });
    container.querySelectorAll(SCROLL_SELECTOR).forEach((el) => {
      if (el.scrollTop > 0 || el.scrollLeft > 0) {
        const path = pathFrom(container, el);
        if (path) state.scrolls.push({ path, top: el.scrollTop, left: el.scrollLeft });
      }
    });
    const active = document.activeElement;
    if (active && active !== document.body && container.contains(active)) {
      const path = pathFrom(container, active);
      if (path) {
        let start = null;
        let end = null;
        try {
          start = active.selectionStart;
          end = active.selectionEnd;
        } catch {
          // Inputs like type="date"/"number" throw on selectionStart.
        }
        state.focus = { path, start, end };
      }
    }
  } catch {
    // Restoring UI state is best-effort polish — never let it break a render.
  }
  return state;
}

function restoreUiState(container, state) {
  if (typeof document === "undefined") return;
  try {
    for (const { path, node, name } of state.files) {
      const fresh = nodeAt(container, path);
      // Only carry the chosen file over when the new tree still expects
      // that same file (data-file-name). After a successful upload the
      // page clears it, so the input correctly comes back empty.
      if (fresh && fresh.tagName === "INPUT" && fresh.type === "file" &&
          fresh.getAttribute("data-file-name") === name) {
        fresh.replaceWith(node);
      }
    }
    for (const { path, top, left } of state.scrolls) {
      const el = nodeAt(container, path);
      if (el && el.scrollTo) el.scrollTo(left, top);
    }
    if (state.windowY) window.scrollTo(0, state.windowY);
    if (state.focus) {
      const el = nodeAt(container, state.focus.path);
      if (el && typeof el.focus === "function") {
        el.focus({ preventScroll: true });
        if (state.focus.start !== null && state.focus.start !== undefined) {
          try {
            el.setSelectionRange(state.focus.start, state.focus.end);
          } catch {
            // Not a text-like input — focus alone is enough.
          }
        }
      }
    }
  } catch {
    // Best-effort, see captureUiState.
  }
}

function render(vnode) {
  if (vnode === null || vnode === undefined || vnode === false) return null;
  if (typeof vnode === "string" || typeof vnode === "number") {
    return document.createTextNode(String(vnode));
  }
  if (vnode.tag === null) {
    const frag = document.createDocumentFragment();
    for (const child of vnode.children) {
      const childNode = render(child);
      if (childNode) frag.appendChild(childNode);
    }
    return frag;
  }
  const el = document.createElement(vnode.tag);
  let pendingValue;
  for (const [key, value] of Object.entries(vnode.props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key.startsWith("on") && typeof value === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === "className") {
      el.setAttribute("class", value);
    } else if (key === "value" && "value" in el) {
      // Applied AFTER children are appended (below): for a <select>,
      // setting .value before its <option> children exist silently
      // does nothing, which made every dropdown snap back to its first
      // option on each re-render.
      pendingValue = value;
    } else if (typeof value === "boolean") {
      if (value) el.setAttribute(key, "");
    } else {
      el.setAttribute(key, value);
    }
  }
  for (const child of vnode.children) {
    const childNode = render(child);
    if (childNode) el.appendChild(childNode);
  }
  if (pendingValue !== undefined) el.value = pendingValue;
  return el;
}
