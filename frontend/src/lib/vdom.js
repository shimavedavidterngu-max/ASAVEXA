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
  container.replaceChildren();
  const node = render(vnode);
  if (node) container.appendChild(node);
  return node;
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
  for (const [key, value] of Object.entries(vnode.props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key.startsWith("on") && typeof value === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === "className") {
      el.setAttribute("class", value);
    } else if (key === "value" && "value" in el) {
      el.value = value;
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
  return el;
}
