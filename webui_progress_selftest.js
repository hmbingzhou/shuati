/* 回归测试：刷题进度自动保存（每答一题）+ 刷新后原地恢复，不退回首页
   运行：node webui_progress_selftest.js */
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
    innerHTML: "", children: [], parentNode: null, style: {}, dataset: {}, value: "", _h: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    addEventListener(t, f) { (this._h[t] = this._h[t] || []).push(f); },
    appendChild(c) { c.parentNode = this; this.children.push(c); return c; },
    insertAdjacentHTML() {}, remove() {},
    querySelector() { return makeEl(); }, querySelectorAll() { return []; },
    focus() {}, click() {}, getAttribute() { return null; },
  };
  return el;
}

const viewEl = makeEl();
const documentStub = {
  body: makeEl(),
  querySelector: (sel) => (sel === "#view" ? viewEl : makeEl()),
  querySelectorAll: () => [],
  createElement: () => makeEl(),
  addEventListener() {},
  getElementById: () => null,
};

const beacons = [];
const winListeners = {};
const windowStub = {
  addEventListener(t, f) { (winListeners[t] = winListeners[t] || []).push(f); },
  location: { hash: "#/practice" },
};

const calls = [];
const ctx = {
  console, document: documentStub, window: windowStub,
  location: { hash: "#/practice" },                 // 模拟「在刷题页面刷新」
  localStorage: { getItem: () => null, setItem() {} },
  setTimeout, clearTimeout, setInterval, clearInterval,
  Math, JSON, Date, Promise, Set, Map, Array, Object, String, Number, Boolean, RegExp, Error,
  encodeURIComponent, decodeURIComponent, encodeURI, isNaN, parseInt, parseFloat,
  toast() {},
  Blob: class Blob { constructor(parts, opts) { this.parts = parts; this.type = (opts || {}).type; } },
  navigator: { sendBeacon(url, blob) { beacons.push([url, blob]); return true; } },
  fetch: async () => ({}),
};
ctx.globalThis = ctx;

const QUESTION = (text, index) => ({
  subject: "数据结构", index, text, found: true,
  question: {
    label: "单选题", type: "单选题", options: [["A", "甲"], ["B", "乙"]],
    choice_type: "single", blankCount: null, wholeString: false,
    flag_star: false, flag_cross: false,
  },
});

/* app.js 内部的 api() 直接调全局 fetch，所以这里替换 fetch（而不是 ctx.api） */
ctx.fetch = async (url, opts) => {
  const method = (opts && opts.method) || "GET";
  const body = opts && opts.body ? JSON.parse(opts.body) : undefined;
  calls.push([method, url, body]);
  let data = { ok: true };
  if (url === "/api/overview") {
    data = {
      grades: [{ name: "大一上", subjects: [{ name: "数据结构", questionCount: 3, wrongCount: 0, records: { types: [], total: 0, correct: 0, wrong: 0, accuracy: null } }] }],
      totalQuestions: 3, totalWrong: 0, hasProgress: true,
      progress: { subject: "数据结构", total: 3, remainingCount: 2 },
    };
  } else if (url === "/api/progress" && method === "GET") {
    data = {
      exists: true,
      progress: {
        subject: "数据结构", mode: "all", type_label: null, total: 3,
        remaining: [{ subject: "数据结构", text: "题目二" }, { subject: "数据结构", text: "题目三" }],
      },
    };
  } else if (url === "/api/resolve") {
    data = { items: [QUESTION("题目二", 1), QUESTION("题目三", 2)] };
  }
  return { ok: true, status: 200, json: async () => data };
};

vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname, "webui", "app.js"), "utf8"), ctx, { filename: "app.js" });

function mkPractice(over) {
  return Object.assign({
    cfg: { scope: { type: "subject", name: "数据结构" }, typeLabel: null },
    wrong: false, modeKey: "all",
    pool: [
      { subject: "数据结构", text: "题目一" },
      { subject: "数据结构", text: "题目二" },
      { subject: "数据结构", text: "题目三" },
    ],
    pos: 1, answered: false, doneBefore: 0, totalBase: 3, finished: false,
    stats: { total: 0, correct: 0, wrong: 0 }, subjects: {}, history: [],
  }, over);
}

(async () => {
  /* ---------- 1) 快照：剩余题目按「当前题是否已答」计算 ---------- */
  const p1 = mkPractice();
  const s1 = ctx.practiceSnapshot(p1);
  check("快照只含当前题及以后", s1 && s1.remaining.length === 2 && s1.remaining[0].text === "题目二", s1);

  const p2 = mkPractice({ answered: true });
  const s2 = ctx.practiceSnapshot(p2);
  check("已答本题后快照从下一题开始", s2 && s2.remaining.length === 1 && s2.remaining[0].text === "题目三", s2);

  check("已结束的练习不产生快照", ctx.practiceSnapshot(mkPractice({ finished: true })) === null);
  check("答到最后一题且已答，不产生空快照", ctx.practiceSnapshot(mkPractice({ pos: 2, answered: true })) === null);
  check("错题复习模式带 _wrong 后缀", ctx.practiceSnapshot(mkPractice({ wrong: true })).mode === "all_wrong");
  check("全部科目混合的科目名为「所有科目」",
    ctx.practiceSnapshot(mkPractice({ cfg: { scope: { type: "all" }, typeLabel: "单选题" } })).subject === "所有科目");

  /* ---------- 2) autosaveProgress 真的发 POST ---------- */
  calls.length = 0;
  await ctx.autosaveProgress(p1);
  const post = calls.filter((c) => c[0] === "POST" && c[1] === "/api/progress");
  check("每答一题会 POST /api/progress", post.length === 1, calls);
  check("保存内容带 remaining/total/mode",
    post[0] && post[0][2].remaining.length === 2 && post[0][2].total === 3 && post[0][2].mode === "all", post[0] && post[0][2]);

  calls.length = 0;
  await Promise.all([ctx.autosaveProgress(p1), ctx.autosaveProgress(p2)]);
  check("连续保存串行不丢失（两次都发出）",
    calls.filter((c) => c[1] === "/api/progress").length === 2, calls.length);

  /* ---------- 3) 刷新后原地恢复，不退回首页 ---------- */
  calls.length = 0;
  const view = viewEl;
  await ctx.renderPractice(view);
  check("刷新后自动读取进度", calls.some((c) => c[0] === "GET" && c[1] === "/api/progress"), calls.map((c) => c[1]));
  check("刷新后自动解析剩余题目", calls.some((c) => c[1] === "/api/resolve"), calls.map((c) => c[1]));
  check("刷新后停在刷题界面（有退出按钮）", view.innerHTML.includes("退出练习"), view.innerHTML.slice(0, 120));
  check("刷新后没有落到「开始刷题」选择页", !view.innerHTML.includes("选择科目与模式开始"));

  /* ---------- 4) 关页面时 beacon 兜底 ---------- */
  check("注册了 pagehide 兜底", (winListeners.pagehide || []).length === 1);
  check("注册了 beforeunload 兜底", (winListeners.beforeunload || []).length === 1);
  beacons.length = 0;
  ctx.flushProgressOnUnload();
  check("卸载时用 sendBeacon 发到最后一次进度", beacons.length === 1 && beacons[0][0] === "/api/progress", beacons.length);
  const payload = beacons[0] ? JSON.parse(beacons[0][1].parts[0]) : {};
  check("beacon 载荷是剩余题目快照", Array.isArray(payload.remaining) && payload.remaining.length >= 1, payload);

  console.log("\n" + (fails ? `失败 ${fails} 项` : "刷题进度自动保存/恢复回归全部通过 ✔"));
  process.exit(fails ? 1 : 0);
})();
