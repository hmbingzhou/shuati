/* 回归测试：图片选择器必须是独立叠加层，打开/选图不能销毁底层题目编辑弹窗
   运行：node webui_picker_selftest.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

let fails = 0;
function check(name, cond, detail) {
  console.log((cond ? "[ok] " : "[FAIL] ") + name + (cond ? "" : "  " + JSON.stringify(detail)));
  if (!cond) fails++;
}

function makeEl() {
  const el = {
    innerHTML: "", children: [], parentNode: null, style: {}, dataset: {}, _h: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    addEventListener(t, f) { (this._h[t] = this._h[t] || []).push(f); },
    appendChild(c) { c.parentNode = this; this.children.push(c); return c; },
    insertAdjacentHTML() {},
    remove() {
      if (this.parentNode) {
        const i = this.parentNode.children.indexOf(this);
        if (i >= 0) this.parentNode.children.splice(i, 1);
        this.parentNode = null;
      }
    },
    querySelector() { return makeEl(); },
    querySelectorAll() { return []; },
    focus() {}, click() {},
    getAttribute() { return null; },
  };
  return el;
}

const rootEl = makeEl();
rootEl.querySelector = (sel) => (sel === ".modal-mask" ? (rootEl._mask = rootEl._mask || makeEl()) : makeEl());

const bodyEl = makeEl();
const documentStub = {
  body: bodyEl,
  querySelector: (sel) => (sel === "#modal-root" ? rootEl : makeEl()),
  querySelectorAll: () => [],
  createElement: () => makeEl(),
  addEventListener() {},
  getElementById: () => null,
};
const windowStub = { addEventListener() {}, location: { hash: "" } };
const ctx = {
  console,
  document: documentStub,
  window: windowStub,
  location: { hash: "" },
  localStorage: { getItem: () => null, setItem() {} },
  setTimeout, clearTimeout, setInterval, clearInterval,
  Math, JSON, Date, Promise, Set, Map, Array, Object, String, Number, Boolean, RegExp, Error,
  encodeURIComponent, decodeURIComponent, encodeURI, isNaN, parseInt, parseFloat,
  api: async () => ({ ok: true, total: 1, items: [{ name: "Java/x.png", size: 1 }] }),
  fetch: async () => ({ ok: true, json: async () => ({ ok: true, name: "Java/up.png" }) }),
  toast() {},
};
ctx.globalThis = ctx;
windowStub.document = documentStub;

const src = fs.readFileSync(path.join(__dirname, "webui", "app.js"), "utf8");
vm.createContext(ctx);
vm.runInContext(src, ctx, { filename: "app.js" });

check("app.js 在桩环境中可加载", typeof ctx.openImagePicker === "function" && typeof ctx.overlayDialog === "function");

/* 1) 先模拟“打开题目编辑弹窗” */
ctx.openModal('<div id="q-text">题目编辑中</div>', "modal-lg");
check("编辑弹窗已挂到 #modal-root", rootEl.innerHTML.includes("题目编辑中"));

/* 2) 记录 openModal 是否被图片选择器误用 */
let openModalCalls = 0;
const realOpen = ctx.openModal;
ctx.openModal = function (...a) { openModalCalls++; return realOpen.apply(null, a); };

let picked = null;
ctx.openImagePicker((name) => { picked = name; }, "Java");

setTimeout(() => {
  check("图片选择器未调用 openModal(不销毁底层弹窗)", openModalCalls === 0, { openModalCalls });
  check("编辑弹窗内容仍在", rootEl.innerHTML.includes("题目编辑中"), rootEl.innerHTML);
  check("选择器叠加层已插入 body", bodyEl.children.length === 1, bodyEl.children.length);

  const mask = bodyEl.children[0];
  const fakeEvent = {
    target: {
      closest: (sel) => (sel === "[data-name]" ? { dataset: { name: "Java/x.png" } } : null),
    },
  };
  (mask._h.click || []).forEach((f) => f(fakeEvent));

  check("选中图片回调收到带科目前缀路径", picked === "Java/x.png", picked);
  check("叠加层关闭后已移除", bodyEl.children.length === 0, bodyEl.children.length);
  check("编辑弹窗在选图后依然存在", rootEl.innerHTML.includes("题目编辑中"));

  console.log("\n" + (fails ? `失败 ${fails} 项` : "图片选择器隔离回归全部通过 ✔"));
  process.exit(fails ? 1 : 0);
}, 30);
