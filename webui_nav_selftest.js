/* 移动端导航与返回键回归测试（最小 DOM 桩）
   覆盖：顶部/底部导航同源渲染、更多菜单、Android 返回键三级行为、index.html PWA 元信息
   运行：node webui_nav_selftest.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

let fails = 0;
function check(name, cond, detail) {
  console.log((cond ? "[ok] " : "[FAIL] ") + name + (cond ? "" : "  " + JSON.stringify(detail)));
  if (!cond) fails++;
}

const EXPECTED = ["home", "practice", "wrong", "recycle", "library", "import", "reports", "settings", "help"];
const PRIMARY = ["home", "practice", "wrong", "library"];
function makeEl(tag) {
  const el = {
    tagName: (tag || "div").toUpperCase(),
    innerHTML: "", children: [], parentNode: null, className: "", dataset: {}, style: {},
    _h: {}, _clicks: 0,
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
    querySelector(sel) { return this._q ? this._q(sel) : makeEl(); },
    querySelectorAll() { return []; },
    closest() { return null; },
    click() { this._clicks++; },
    focus() {}, setSelectionRange() {},
    getAttribute() { return null; },
  };
  return el;
}

const registry = {};
function stable(sel) {
  if (!registry[sel]) registry[sel] = makeEl();
  return registry[sel];
}

const bodyEl = makeEl("body");
const rootEl = stable("#modal-root");
rootEl.querySelector = (sel) => {
  if (sel === ".modal-mask") return (rootEl._mask = rootEl._mask || makeEl());
  if (sel === ".modal-close") return (rootEl._close = rootEl._close || makeEl());
  return makeEl();
};

const documentStub = {
  body: bodyEl,
  createElement: (t) => makeEl(t),
  querySelector: (sel) => stable(sel),
  querySelectorAll: (sel) => {
    if (sel === "body > .modal-mask") return bodyEl.children.filter((c) => String(c.className).includes("modal-mask"));
    if (sel === "[data-nav]") return [];
    return [];
  },
  addEventListener() {},
  getElementById: (id) => stable("#" + id),
};
const windowStub = { addEventListener() {}, scrollTo() {} };
const ctx = {
  console, document: documentStub, window: windowStub,
  location: { hash: "" },
  localStorage: { getItem: () => null, setItem() {} },
  setTimeout, clearTimeout, setInterval, clearInterval,
  Math, JSON, Date, Promise, Set, Map, Array, Object, String, Number, Boolean, RegExp, Error,
  encodeURIComponent, decodeURIComponent, encodeURI, isNaN, parseInt, parseFloat,
  addEventListener() {}, scrollTo() {},
  api: async () => ({ ok: true }),
  fetch: async () => ({ ok: true, json: async () => ({ ok: true }) }),
  toast() {},
};
ctx.globalThis = ctx;
ctx.window = ctx;              // 浏览器里 window === globalThis，桩环境保持同样语义
ctx.document = documentStub;

const src = fs.readFileSync(path.join(__dirname, "webui", "app.js"), "utf8");
vm.createContext(ctx);
vm.runInContext(src, ctx, { filename: "app.js" });

/* 1) 导航同源渲染 */
check("renderNav 可用", typeof ctx.renderNav === "function");
ctx.renderNav();
const navHtml = stable("#nav").innerHTML;
const navRoutes = [...navHtml.matchAll(/data-nav="([^"]+)"/g)].map((m) => m[1]);
check("顶部导航覆盖全部 9 个路由", JSON.stringify(navRoutes) === JSON.stringify(EXPECTED), navRoutes);

const bnHtml = stable("#bottom-nav").innerHTML;
const bnRoutes = [...bnHtml.matchAll(/data-nav="([^"]+)"/g)].map((m) => m[1]);
check("底部导航只放 4 个主入口", JSON.stringify(bnRoutes) === JSON.stringify(PRIMARY), bnRoutes);
check("底部导航含“更多”按钮", bnHtml.includes('id="bn-more"'));

/* 2) “更多”菜单列出其余 5 项 */
const other = EXPECTED.filter((r) => !PRIMARY.includes(r));
ctx.openMoreMenu(other.map((r) => ({ route: r, label: r, icon: "•" })));
const modalHtml = rootEl.innerHTML;
check("更多菜单包含其余 5 个路由", other.every((r) => modalHtml.includes(`data-nav="${r}"`)), modalHtml.slice(0, 200));

/* 3) 路由识别：每个已知路由都能被 currentRoute 识别 */
let routeOk = true;
for (const r of EXPECTED) {
  ctx.location.hash = `#/${r}`;
  if (ctx.currentRoute() !== r) routeOk = false;
}
ctx.location.hash = "#/不存在的页面";
const fallbackOk = ctx.currentRoute() === "home";
check("currentRoute 识别全部路由并回退 home", routeOk && fallbackOk);

/* 4) Android 返回键：叠加层 → 弹窗 → 回首页 → 交给系统 */
const overlay = makeEl(); overlay.className = "modal-mask"; bodyEl.appendChild(overlay);
let handled = ctx.__shuatiAndroidBack();
check("返回键先关闭图库/叠加层", handled === true && bodyEl.children.length === 0);

rootEl.innerHTML = "<div class='modal-mask'>editor</div>";
const closeProbe = rootEl.querySelector(".modal-close");   // 触发桩内部创建（真实环境由 DOM 提供）
closeProbe._clicks = 0;
handled = ctx.__shuatiAndroidBack();
check("返回键其次关闭题目弹窗", handled === true && closeProbe._clicks === 1, closeProbe._clicks);

rootEl.innerHTML = "";
ctx.location.hash = "#/settings";
handled = ctx.__shuatiAndroidBack();
check("返回键再回到首页", handled === true && ctx.location.hash === "#/home", ctx.location.hash);

handled = ctx.__shuatiAndroidBack();
check("首页无弹窗时返回 false（交给系统退出）", handled === false);

/* 5) index.html 的移动端/PWA 元信息 */
const html = fs.readFileSync(path.join(__dirname, "webui", "index.html"), "utf8");
check("viewport 含 viewport-fit=cover", /viewport-fit=cover/.test(html));
check("声明 theme-color", /name="theme-color"/.test(html));
check("引用 manifest", /rel="manifest"/.test(html) && fs.existsSync(path.join(__dirname, "webui", "manifest.webmanifest")));
check("引用 PWA 图标", /icons\/icon-192\.png/.test(html) && fs.existsSync(path.join(__dirname, "webui", "icons", "icon-192.png")));
check("存在底部导航容器", /id="bottom-nav"/.test(html));
const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, "webui", "manifest.webmanifest"), "utf8"));
check("manifest 含 192/512/maskable 图标与独立显示模式",
  manifest.display === "standalone" && manifest.icons.length >= 3
  && manifest.icons.some((i) => i.purpose === "maskable"), manifest.icons);

console.log("\n" + (fails ? `失败 ${fails} 项` : "移动端导航/返回键回归全部通过 ✔"));
process.exit(fails ? 1 : 0);
