/* 回归测试：简答题/证明题「只看题 + 查看答案」模式（不作答、不计分）
   运行：node webui_essay_selftest.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

let fails = 0;
function check(name, cond, detail) {
  console.log((cond ? "[ok] " : "[FAIL] ") + name + (cond ? "" : "  " + JSON.stringify(detail)));
  if (!cond) fails++;
}

/* 记忆化 DOM 桩：同一选择器（含子元素）返回同一个元素，才能取到绑定的事件 */
function makeEl() {
  const kids = new Map();
  const el = {
    innerHTML: "", children: [], parentNode: null, style: {}, dataset: {}, value: "", disabled: false, _h: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    addEventListener(t, f) { (this._h[t] = this._h[t] || []).push(f); },
    appendChild(c) { c.parentNode = this; this.children.push(c); return c; },
    insertAdjacentHTML(pos, html) { this.innerHTML += html; },
    remove() { this.removed = true; },
    querySelector(sel) {
      if (!kids.has(sel)) kids.set(sel, makeEl());
      return kids.get(sel);
    },
    querySelectorAll() { return []; },
    focus() {}, click() {}, getAttribute() { return null; },
  };
  return el;
}
function memoEl() { return makeEl(); }

const documentStub = {
  body: makeEl(), querySelector: () => makeEl(), querySelectorAll: () => [],
  createElement: () => makeEl(), addEventListener() {}, getElementById: () => null,
};
const ctx = {
  console, document: documentStub, window: { addEventListener() {}, location: { hash: "" } },
  location: { hash: "" }, localStorage: { getItem: () => null, setItem() {} },
  setTimeout, clearTimeout, setInterval, clearInterval,
  Math, JSON, Date, Promise, Set, Map, Array, Object, String, Number, Boolean, RegExp, Error,
  encodeURIComponent, decodeURIComponent, encodeURI, isNaN, parseInt, parseFloat,
  toast() {}, Blob: class Blob { constructor(p) { this.parts = p; } },
  navigator: { sendBeacon: () => true }, fetch: async () => ({ ok: true, status: 200, json: async () => ({ ok: true }) }),
};
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname, "webui", "app.js"), "utf8"), ctx, { filename: "app.js" });

function run(q) {
  const view = memoEl();
  const p = { pos: 0, pool: [q], history: [], answered: false, cursor: 0, stats: { total: 0, correct: 0, wrong: 0 }, subjects: {} };
  ctx.buildAnswerArea(view, p, q);
  const area = view.querySelector("#answer-area");
  return { view, p, area };
}

/* ---------- 简答题 ---------- */
const q1 = { type: "简答题", text: "什么是中断？", answer: "CPU 暂停现行程序去处理紧急事件。", label: "简答题", index: 1, subject: "计算机组成原理" };
let { view, p, area } = run(q1);
check("简答题不渲染作答输入框", !area.innerHTML.includes("<textarea") && !area.innerHTML.includes("提交答案"));
check("简答题有「查看答案」按钮", area.innerHTML.includes("查看答案"));
check("简答题提示不计对错", area.innerHTML.includes("不计入对错"));

const btn = area.querySelector("#reveal-answer");
const box = area.querySelector("#reveal-area");
(btn._h.click || []).forEach((f) => f());
check("点「查看答案」后显示参考答案", box.innerHTML.includes("CPU 暂停现行程序"), box.innerHTML);
check("答案区标题为参考答案", box.innerHTML.includes("参考答案"));
check("查看后置为已答", p.answered === true);
check("查看后记入 history（correct 为 null，表示不计对错）",
  p.history.length === 1 && p.history[0].correct === null, p.history);
check("查看后出现下一题按钮", view.querySelector("#action-area").innerHTML.includes("下一题") ||
  view.querySelector("#action-area").innerHTML.includes("查看结果"));

/* ---------- 证明题 ---------- */
const q2 = { type: "证明题", text: "证明：二叉树的结点数 n = 2n0 + n1 - 1", answer: "证明过程……", label: "证明题", index: 2, subject: "数据结构" };
const r2 = run(q2);
check("证明题同样走查看答案模式", r2.area.innerHTML.includes("查看答案") && !r2.area.innerHTML.includes("<textarea"));
const btn2 = r2.area.querySelector("#reveal-answer");
const box2 = r2.area.querySelector("#reveal-area");
(btn2._h.click || []).forEach((f) => f());
check("证明题能显示参考答案", box2.innerHTML.includes("证明过程"), box2.innerHTML);

/* ---------- 回看（review）里的简答/证明 ---------- */
const reviewHtml = ctx.reviewHtmlFor(q1, { userAnswer: "", correct: null, correctAnswer: q1.answer }, 0);
check("回看时简答题显示参考答案而不是对错", reviewHtml.includes("已查看答案") && !reviewHtml.includes("回答错误"), reviewHtml);

/* ---------- 自动判分题型不受影响 ---------- */
const q3 = { type: "判断题", text: "1+1=2", answer: "正确", label: "判断题", index: 3, subject: "x" };
const r3 = run(q3);
check("判断题仍是选项按钮", r3.area.innerHTML.includes("tf-btn"));

console.log("\n" + (fails ? `失败 ${fails} 项` : "简答/证明「查看答案」模式回归全部通过 ✔"));
process.exit(fails ? 1 : 0);
