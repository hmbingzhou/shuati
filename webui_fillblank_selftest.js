/* 回归测试：填空题必须按空位数渲染多个输入框（曾经只出 1 个空，多空题永远判错）
   运行：node webui_fillblank_selftest.js */
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
    querySelector() { return makeEl(); },
    querySelectorAll() { return []; },
    focus() {}, click() {}, getAttribute() { return null; },
  };
  return el;
}

const documentStub = {
  body: makeEl(),
  querySelector: () => makeEl(),
  querySelectorAll: () => [],
  createElement: () => makeEl(),
  addEventListener() {},
  getElementById: () => null,
};
const ctx = {
  console, document: documentStub, window: { addEventListener() {}, location: { hash: "" } },
  location: { hash: "" }, localStorage: { getItem: () => null, setItem() {} },
  setTimeout, clearTimeout, setInterval, clearInterval,
  Math, JSON, Date, Promise, Set, Map, Array, Object, String, Number, Boolean, RegExp, Error,
  encodeURIComponent, decodeURIComponent, encodeURI, isNaN, parseInt, parseFloat,
  toast() {}, confirm: () => true, alert() {},
};
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname, "webui", "app.js"), "utf8"), ctx, { filename: "app.js" });

const TEXT4 = "计算机网络数据传输的总时延是【1】、【2】、【3】和【4】";

/* ---------- 1) buildPool 必须把 blankCount / wholeString 带到练习池 ---------- */
const apiItems = [{
  subject: "计算机网络技术", index: 113, text: TEXT4, label: "填空题", type: "填空题",
  options: null, choice_type: null, flag_star: false, flag_cross: false,
  blankCount: 4, wholeString: false,
}];
ctx.api = async () => ({ items: apiItems, total: 1 });

(async () => {
  const pool = await ctx.buildPool({ scope: { type: "subject", name: "计算机网络技术" }, mode: "all" });
  check("buildPool 保留 blankCount", pool[0].blankCount === 4, pool[0]);
  check("buildPool 保留 wholeString", pool[0].wholeString === false, pool[0]);

  /* ---------- 2) 练习页：四空题渲染 4 个输入框 ---------- */
  const area = makeEl();
  const view = { querySelector: (sel) => (sel === "#answer-area" ? area : makeEl()), querySelectorAll: () => [] };
  ctx.buildAnswerArea(view, { pos: 0 }, pool[0]);
  const boxes = (area.innerHTML.match(/id="blank-\d+"/g) || []);
  check("练习页四空题渲染 4 个输入框", boxes.length === 4, boxes);
  check("练习页渲染含第4空", area.innerHTML.includes('id="blank-4"'));
  check("练习页四空题不走整串单输入", !area.innerHTML.includes("请输入完整答案"));

  /* ---------- 3) 兜底：池子里没有 blankCount，也要按题干【N】数出 4 个空 ---------- */
  const area2 = makeEl();
  const view2 = { querySelector: (sel) => (sel === "#answer-area" ? area2 : makeEl()), querySelectorAll: () => [] };
  ctx.buildAnswerArea(view2, { pos: 0 }, { type: "填空题", text: TEXT4, label: "填空题" });
  const boxes2 = (area2.innerHTML.match(/id="blank-\d+"/g) || []);
  check("缺 blankCount 时按【N】兜底为 4 个输入框", boxes2.length === 4, boxes2);

  /* ---------- 4) 整串模式仍是单输入 ---------- */
  const area3 = makeEl();
  const view3 = { querySelector: (sel) => (sel === "#answer-area" ? area3 : makeEl()), querySelectorAll: () => [] };
  ctx.buildAnswerArea(view3, { pos: 0 }, {
    type: "填空题", text: "code输出", label: "填空题", wholeString: true, blankCount: 1,
  });
  check("整串模式渲染单输入", area3.innerHTML.includes("请输入完整答案") && !area3.innerHTML.includes("blank-2"), area3.innerHTML);

  /* ---------- 5) 考试页同样按空位数渲染 ---------- */
  const examArea = makeEl();
  const examView = { querySelector: (sel) => (sel === "#exam-answer-area" ? examArea : makeEl()), querySelectorAll: () => [] };
  ctx.buildExamAnswerArea(examView, { unit: { index: 1 }, pos: 0 }, pool[0]);
  const examBoxes = (examArea.innerHTML.match(/id="exam-blank-\d+"/g) || []);
  check("考试页四空题渲染 4 个输入框", examBoxes.length === 4, examBoxes);

  console.log("\n" + (fails ? `失败 ${fails} 项` : "填空题多空渲染回归全部通过 ✔"));
  process.exit(fails ? 1 : 0);
})();
