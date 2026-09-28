import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { h, Fragment } from "../src/lib/vdom.js";

describe("h() — vnode construction (no DOM touched, plain data)", () => {
  test("builds a tag with props and text children", () => {
    const vnode = h("button", { className: "btn" }, "Click me");
    assert.equal(vnode.tag, "button");
    assert.equal(vnode.props.className, "btn");
    assert.deepEqual(vnode.children, ["Click me"]);
  });

  test("flattens nested/array children into one flat list", () => {
    const vnode = h("ul", {}, [h("li", {}, "a"), h("li", {}, "b")], h("li", {}, "c"));
    assert.equal(vnode.children.length, 3);
    assert.equal(vnode.children[2].children[0], "c");
  });

  test("omits falsy/undefined children naturally via flat()", () => {
    const showExtra = false;
    const vnode = h("div", {}, "always", showExtra && h("span", {}, "conditional"));
    assert.equal(vnode.children.length, 2);
    assert.equal(vnode.children[1], false); // filtered at render() time, not construction
  });

  test("Fragment has a null tag and holds its children directly", () => {
    const frag = Fragment([h("p", {}, "one"), h("p", {}, "two")]);
    assert.equal(frag.tag, null);
    assert.equal(frag.children.length, 2);
  });

  test("props default to an empty object when omitted", () => {
    const vnode = h("div");
    assert.deepEqual(vnode.props, {});
    assert.deepEqual(vnode.children, []);
  });
});
