/* 回归测试：部分分（多选漏选 / 填空按空）在练习页的展示
   运行：node webui_partial_selftest.js */
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
  const kids = new Map();
  const el = {
    innerHTML: "", children: [], style: {}, dataset: {}, value: "", disabled: false, _h: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    addEventListener(t, f) { (this._h[t] = this._h[t] || []).push(f); },
    appendChild(c) { this.children.push(c); return c; },
    insertAdjacentHTML(p, h) { this.innerHTML += h; },
    remove() {},
    querySelector(sel) { if (!kids.has(sel)) kids.set(sel, makeEl()); return kids.get(sel); },
    querySelectorAll() { return []; },
    focus() {}, click() {}, getAttribute() { return null; },
  };
  return el;
}
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
  toast() {}, fetch: async () => ({ ok: true, json: async () => ({}) }),
  navigator: { sendBeacon: () => true }, Blob: class {},
};
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname, "webui", "app.js"), "utf8"), ctx, { filename: "app.js" });

/* 隔离外部副作用 */
ctx.showNextButton = () => {};
ctx.autosaveProgress = () => {};

function mkP() {
  return { pos: 0, pool: [{}], answered: false, cursor: 0,
    stats: { total: 0, correct: 0, wrong: 0 }, subjects: {}, history: [] };
}

/* ---------- 多选漏选：0.667 ---------- */
{
  const view = makeEl();
  const fb = makeEl();
  const p = mkP();
  ctx.finishAnsweredResult(view, p, { type: "多选题", subject: "计组", label: "多选题" },
    "AB", false, "ABD", fb, 0.6667);
  check("部分分显示「部分正确」", fb.innerHTML.includes("部分正确"), fb.innerHTML);
  check("部分分显示百分比 67%", fb.innerHTML.includes("67%"), fb.innerHTML);
  check("部分分仍显示正确答案", fb.innerHTML.includes("ABD"), fb.innerHTML);
  check("部分分提示计入错题本", fb.innerHTML.includes("错题本"), fb.innerHTML);
  check("部分分记为答错", p.stats.wrong === 1 && p.stats.correct === 0, p.stats);
  check("history 记录分数", Math.abs((p.history[0].score || 0) - 0.6667) < 1e-6, p.history[0]);
}

/* ---------- 全对 ---------- */
{
  const fb = makeEl();
  const p = mkP();
  ctx.finishAnsweredResult(makeEl(), p, { type: "多选题", subject: "计组", label: "多选题" },
    "ABD", true, "ABD", fb, 1);
  check("全对显示「回答正确」", fb.innerHTML.includes("回答正确") && !fb.innerHTML.includes("部分正确"), fb.innerHTML);
  check("全对记为答对", p.stats.correct === 1 && p.stats.wrong === 0, p.stats);
}

/* ---------- 全错 ---------- */
{
  const fb = makeEl();
  const p = mkP();
  ctx.finishAnsweredResult(makeEl(), p, { type: "多选题", subject: "计组", label: "多选题" },
    "ABC", false, "ABD", fb, 0);
  check("全错显示「回答错误」", fb.innerHTML.includes("回答错误") && !fb.innerHTML.includes("部分正确"), fb.innerHTML);
}

/* ---------- 老接口：不传 score 时按布尔处理 ---------- */
{
  const fb = makeEl();
  const p = mkP();
  ctx.finishAnsweredResult(makeEl(), p, { type: "判断题", subject: "计组", label: "判断题" },
    "正确", true, "正确", fb);
  check("不传 score 时按布尔判分", fb.innerHTML.includes("回答正确") && p.stats.correct === 1, fb.innerHTML);
  check("不传 score 时 history.score = 1", p.history[0].score === 1, p.history[0]);
}

console.log("\n" + (fails ? `失败 ${fails} 项` : "部分分展示回归全部通过 ✔"));
process.exit(fails ? 1 : 0);
