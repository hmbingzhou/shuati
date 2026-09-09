/* ============================================================
   刷题软件 · 网页版 前端逻辑（无第三方依赖）
   ============================================================ */

"use strict";

/* ---------------- 小工具 ---------------- */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function fmtDateTime(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function fmtNow() { return fmtDateTime(new Date()); }

function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

/* 富文本渲染：转义 HTML、识别图片文件名、整行下划线转填空提示框 */
function renderRichText(text) {
  const lines = String(text == null ? "" : text).split("\n");
  const out = [];
  const re = /([A-Za-z0-9_\u4e00-\u9fa5.-]+\.(?:png|jpe?g|gif|bmp|webp))/gi;
  for (const line of lines) {
    if (/^_{2,}\s*$/.test(line)) {
      out.push('<div class="blank-line">＿＿＿＿＿＿＿＿</div>');
      continue;
    }
    let html = "";
    let last = 0;
    let m;
    re.lastIndex = 0;
    while ((m = re.exec(line)) !== null) {
      html += esc(line.slice(last, m.index));
      const token = m[1];
      html += `<img class="inline-img" src="pictures/${encodeURI(token)}" alt="${esc(token)}" loading="lazy" onerror="this.remove()">`;
      last = m.index + m[0].length;
    }
    html += esc(line.slice(last));
    out.push(html || "&nbsp;");
  }
  return out.join("\n");
}

function badgeHtml(label) {
  const safe = label || "未知题型";
  return `<span class="badge badge-${esc(safe)}">${esc(safe)}</span>`;
}

function ansShow(q, answer) {
  /* 答案的人类可读形式 */
  const ans = String(answer == null ? "" : answer);
  const t = q && q.type;
  if (t === "判断题") return ans === "正确" ? "正确" : "错误";
  if (t === "单选题" || t === "多选题") {
    const letters = ans.toUpperCase().replace(/\s/g, "").split("").filter(Boolean);
    return letters.join("、");
  }
  return ans;
}

/* ---------------- Toast ---------------- */

function toast(msg, kind = "info", ms = 2600) {
  const root = $("#toast-root");
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = msg;
  root.appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .3s"; }, ms);
  setTimeout(() => el.remove(), ms + 350);
}

/* ---------------- 弹窗 ---------------- */

function openModal(html, cls = "") {
  const root = $("#modal-root");
  root.innerHTML = `<div class="modal-mask"><div class="modal ${cls}">${html}</div></div>`;
  const mask = $(".modal-mask", root);
  const close = () => { root.innerHTML = ""; };
  mask.addEventListener("click", (e) => { if (e.target === mask) close(); });
  return { root, mask, close };
}

function confirmModal({ title = "确认操作", message = "", okText = "确认", danger = false }) {
  return new Promise((resolve) => {
    const m = openModal(`
      <div class="modal-head"><h3>${esc(title)}</h3><button class="modal-close">✕</button></div>
      <div class="modal-body">${message}</div>
      <div class="modal-foot">
        <button class="btn btn-ghost" data-act="cancel">取消</button>
        <button class="btn ${danger ? "btn-red" : "btn-primary"}" data-act="ok">${esc(okText)}</button>
      </div>`);
    $(".modal-close", m.mask).addEventListener("click", () => m.close());
    m.mask.addEventListener("click", (e) => {
      const act = e.target && e.target.dataset && e.target.dataset.act;
      if (act === "ok") { m.close(); resolve(true); }
      else if (act === "cancel") { m.close(); resolve(false); }
    });
  });
}

/* ---------------- 请求封装 ---------------- */

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch (e) {
    toast("网络错误：无法连接本地服务", "err");
    throw e;
  }
  let data = null;
  try { data = await res.json(); } catch (e) { /* 非 JSON */ }
  if (!res.ok || (data && data.ok === false)) {
    const msg = (data && data.error) ? data.error : `请求失败 (${res.status})`;
    toast(msg, "err");
    throw new Error(msg);
  }
  return data;
}

/* ---------------- 题目标记（⭐ 黄星 / ❌ 红叉） ---------------- */

function flagHtml(it) {
  return `<span class="flag-group">
    <button class="flag-btn flag-star ${it.flag_star ? "on" : ""}" data-flag="star" data-subj="${esc(it.subject)}" data-idx="${it.index}" title="标记/取消 黄星">⭐</button>
    <button class="flag-btn flag-cross ${it.flag_cross ? "on" : ""}" data-flag="cross" data-subj="${esc(it.subject)}" data-idx="${it.index}" title="标记/取消 红叉">❌</button>
  </span>`;
}

async function toggleQuestionFlag(btn) {
  const flag = btn.dataset.flag;
  const subject = btn.dataset.subj;
  const index = Number(btn.dataset.idx);
  const next = !btn.classList.contains("on");
  try {
    await api("POST", "/api/questions/flag", { subject, index, flag, value: next });
  } catch (e) { return; }
  btn.classList.toggle("on", next);
  // 若刷题会话里有同一题，同步状态（不重渲染，避免打断答题）
  if (state.practice) {
    const q = state.practice.pool.find((x) => x.subject === subject && x.index === index);
    if (q) {
      if (flag === "star") q.flag_star = next;
      else q.flag_cross = next;
    }
  }
}

/* ---------------- 全局状态 ---------------- */

const state = {
  route: "home",
  overview: null,
  overviewTs: 0,
  practice: null,
  libFilter: { subject: "全部科目", keyword: "", type: "全部", flags: "", page: 1 },
  wrongFilter: { subject: "全部科目", type: "全部" },
  importFlow: null,
  settings: { choiceAutoSubmit: false },
};

/* ---------------- 设置（localStorage） ---------------- */

function defaultSettings() {
  return { choiceAutoSubmit: false };
}

function loadSettings() {
  let s = defaultSettings();
  try {
    const raw = localStorage.getItem("shuati_settings");
    if (raw) s = Object.assign(defaultSettings(), JSON.parse(raw));
  } catch (e) { /* 用默认值 */ }
  state.settings = s;
}

function saveSettings() {
  try { localStorage.setItem("shuati_settings", JSON.stringify(state.settings)); } catch (e) { /* ignore */ }
}

const OVERVIEW_MAX_AGE = 4000;

async function getOverview(force = false) {
  if (!force && state.overview && Date.now() - state.overviewTs < OVERVIEW_MAX_AGE) return state.overview;
  const data = await api("GET", "/api/overview");
  state.overview = data;
  state.overviewTs = Date.now();
  return data;
}

function invalidateOverview() { state.overview = null; state.overviewTs = 0; }

/* ---------------- 路由 ---------------- */

function currentRoute() {
  const h = location.hash.replace(/^#\/?/, "");
  const known = ["home", "practice", "wrong", "recycle", "library", "import", "exam", "reports", "settings", "help"];
  return known.includes(h) ? h : "home";
}

function navTo(route) {
  if (currentRoute() === route) { render(); return; } // hash 未变（已在目标页）→ 手动重绘
  location.hash = `#/${route}`;
}

async function render() {
  const route = currentRoute();
  state.route = route;
  state.routeChanged = route !== state._prevRoute;
  $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.nav === route));
  const view = $("#view");
  view.innerHTML = '<div class="loading">加载中…</div>';
  try {
    if (route === "home") await renderHome(view);
    else if (route === "practice") await renderPractice(view);
    else if (route === "exam") await renderExamRoute(view);
    else if (route === "wrong") await renderWrong(view);
    else if (route === "recycle") await renderRecycle(view);
    else if (route === "library") await renderLibrary(view);
    else if (route === "import") await renderImport(view);
    else if (route === "reports") await renderReports(view);
    else if (route === "settings") await renderSettings(view);
    else if (route === "help") renderHelp(view);
  } catch (e) {
    view.innerHTML = `<div class="empty"><div class="big">⚠️</div>页面加载失败：${esc(e.message)}</div>`;
  }
  state._prevRoute = route;
}

/* ============================================================
   仪表盘
   ============================================================ */

function accuracyPillHtml(r) {
  if (!r || !r.total) return `<span class="acc-pill none">暂无记录</span>`;
  const a = r.accuracy == null ? 0 : Number(r.accuracy);
  const cls = a >= 80 ? "high" : a >= 60 ? "mid" : "low";
  return `<span class="acc-pill ${cls}" title="共答 ${r.total} 题">正确率 ${a}%（答${r.total}）</span>`;
}

function openSubjectRecords(subject, s) {
  const rec = s.records || { total: 0, correct: 0, wrong: 0, accuracy: null, types: [] };
  const exam = s.exam || { passRate: 0, mockAvg: 0, examCount: 0 };
  const wrongCount = s.wrongCount || 0;
  const rows = (rec.types && rec.types.length ? rec.types : []).map((t) => `
    <tr>
      <td>${esc(t.label)}</td>
      <td>${t.total}</td>
      <td style="color:var(--green)">${t.correct}</td>
      <td style="color:var(--red)">${t.wrong}</td>
      <td>${t.total ? `${t.accuracy}%` : "—"}</td>
    </tr>`).join("");
  const m = openModal(`
    <div class="modal-head"><h3>刷题记录 · ${esc(subject)}</h3><button class="modal-close">✕</button></div>
    <div class="modal-body">
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px">
        <button class="btn btn-primary btn-lg" data-act="brush">开始刷题</button>
        <button class="btn btn-ghost btn-lg" data-act="wrong" ${wrongCount ? "" : "disabled"}>复习错题</button>
        <button class="btn btn-ghost btn-lg" data-act="exam">📝 模拟考试</button>
      </div>
      <div class="small muted" style="margin-bottom:6px">
        平时：共答 ${rec.total} 题 · 答对 <span style="color:var(--green);font-weight:700">${rec.correct}</span> · 答错 <span style="color:var(--red);font-weight:700">${rec.wrong}</span> · 正确率 <b>${rec.total ? rec.accuracy + "%" : "—"}</b>
      </div>
      <div class="small muted" style="margin-bottom:10px">
        模拟考试：最近 ${exam.examCount} 次 · 均分 <b>${exam.mockAvg}</b> · 考试通过率 <b>${exam.passRate}%</b>
      </div>
      ${rec.total ? `
      <table class="rec-table">
        <thead><tr><th>题型</th><th>数量</th><th>答对</th><th>答错</th><th>正确率</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>` : `<div class="empty"><div class="big">📊</div>该科暂无平时刷题记录，去刷几道或来场模拟考试吧。</div>`}
    </div>
    <div class="modal-foot"><button class="btn btn-ghost" data-act="close">关闭</button></div>`, "modal-lg");
  $(".modal-close", m.mask).addEventListener("click", () => m.close());
  m.mask.addEventListener("click", (e) => {
    const el = e.target.closest("[data-act]");
    if (!el) return;
    const act = el.dataset.act;
    if (act === "close") { m.close(); return; }
    m.close();
    if (act === "brush") openPracticeConfig({ scope: { type: "subject", name: subject } });
    else if (act === "wrong") {
      if (!wrongCount) { toast("该科暂无错题", "info"); return; }
      openPracticeConfig({ scope: { type: "subject", name: subject }, wrong: true });
    } else if (act === "exam") openExam(subject);
  });
}

async function renderHome(view) {
  const ov = await getOverview(true);
  const allSubjects = ov.grades.flatMap((g) => g.subjects);
  const subjectsWithQ = allSubjects.filter((s) => s.questionCount > 0);
  const totalWrong = allSubjects.reduce((n, s) => n + s.wrongCount, 0);

  const progressCard = ov.hasProgress && ov.progress
    ? `
    <div class="card" style="padding:14px 18px;margin-bottom:20px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
      <span style="font-size:24px">⏸️</span>
      <div style="flex:1;min-width:200px">
        <div style="font-weight:700">上次刷题未完成</div>
        <div class="small muted">【${esc(ov.progress.subject)}】已完成 ${ov.progress.total - ov.progress.remainingCount} / ${ov.progress.total} 题，剩余 ${ov.progress.remainingCount} 题</div>
      </div>
      <button class="btn btn-primary" id="btn-resume">继续答题</button>
      <button class="btn btn-red-ghost btn-sm" id="btn-drop-progress">放弃进度</button>
    </div>`
    : "";

  const mixHero = `
    <div class="card" style="padding:16px 20px;margin-bottom:22px;display:flex;align-items:center;gap:16px;flex-wrap:wrap;
        background:linear-gradient(105deg,#4f6ef7,#6d8bff);border:none;color:#fff">
      <span style="font-size:30px">🚀</span>
      <div style="flex:1;min-width:200px">
        <div style="font-weight:800;font-size:17px">混合刷题</div>
        <div class="small" style="opacity:.9">跨全部科目随机出题，检验综合掌握情况</div>
      </div>
      <button class="btn btn-ghost" id="btn-mix-all">全部题目</button>
      <button class="btn btn-ghost" id="btn-mix-wrong" ${totalWrong === 0 ? "disabled" : ""}>仅错题</button>
    </div>`;

  let gradesHtml = "";
  for (const g of ov.grades) {
    const cards = g.subjects.map((s) => {
      const ex = s.exam || { passRate: 0, mockAvg: 0, examCount: 0 };
      return `
      <div class="subject-card clickable" data-subject="${esc(s.name)}" title="点击查看详细记录">
        <div class="subject-top">
          <span class="subject-name">${esc(s.name)}</span>
        </div>
        <div class="subject-pills">
          ${accuracyPillHtml(s.records)}
          <span class="exam-pill" title="最近${ex.examCount}次模拟考试均分 ${ex.mockAvg} ×0.6 + 平时正确率×0.4">考试通过率 ${ex.passRate}%</span>
        </div>
        <div class="subject-meta">
          <span>题库 ${s.questionCount} 题</span>
          ${s.wrongCount > 0 ? `<span class="warn">错题 ${s.wrongCount}</span>` : ""}
        </div>
      </div>`;
    }).join("");
    gradesHtml += `<div class="grade-block"><h3 class="grade-title">${esc(g.name)}</h3>
      <div class="subject-grid">${cards}</div></div>`;
  }

  view.innerHTML = `
    <div class="page-head"><h2>仪表盘</h2><div class="sub">欢迎回来，选择科目开始今天的刷题吧！</div></div>
    <div class="stat-grid">
      <div class="stat-card"><div class="stat-icon blue">📖</div><div class="stat-body">
        <div class="num">${ov.totalQuestions}</div><div class="lbl">题库总题数</div></div></div>
      <div class="stat-card"><div class="stat-icon green">✅</div><div class="stat-body">
        <div class="num">${subjectsWithQ.length}</div><div class="lbl">有题目的科目</div></div></div>
      <div class="stat-card"><div class="stat-icon red">❌</div><div class="stat-body">
        <div class="num">${totalWrong}</div><div class="lbl">错题总数</div></div></div>
      <div class="stat-card"><div class="stat-icon orange">🎯</div><div class="stat-body">
        <div class="num">${allSubjects.length}</div><div class="lbl">课程科目数</div></div></div>
    </div>
    ${progressCard}${mixHero}${gradesHtml}
    ${ov.totalQuestions === 0 ? '<div class="empty"><div class="big">📭</div>题库还是空的，请先到「题库管理」录入或导入题目。</div>' : ""}`;

  const resumeBtn = $("#btn-resume", view);
  if (resumeBtn) resumeBtn.addEventListener("click", () => startResumeSession());
  const dropBtn = $("#btn-drop-progress", view);
  if (dropBtn) dropBtn.addEventListener("click", async () => {
    if (await confirmModal({ title: "放弃进度", message: "确定放弃上次的刷题进度吗？进度文件将被删除。", okText: "放弃", danger: true })) {
      await api("DELETE", "/api/progress");
      toast("已放弃进度", "ok");
      render();
    }
  });
  const mixAll = $("#btn-mix-all", view);
  if (mixAll) mixAll.addEventListener("click", () => openPracticeConfig({ scope: { type: "all" } }));
  const mixWrong = $("#btn-mix-wrong", view);
  if (mixWrong) mixWrong.addEventListener("click", () => openPracticeConfig({ scope: { type: "all" }, wrong: true }));

  /* 整卡可点击：查看该科详细记录 */
  $$(".subject-card.clickable", view).forEach((card) => card.addEventListener("click", () => {
    const subject = card.dataset.subject;
    const s = allSubjects.find((x) => x.name === subject) || {};
    openSubjectRecords(subject, s);
  }));
}

/* ============================================================
   练习
   ============================================================ */

async function openPracticeConfig({ scope = null, wrong = false } = {}) {
  const ov = await getOverview();
  const allSubjects = ov.grades.flatMap((g) => g.subjects);

  let scopeHtml = "";
  if (scope) {
    const scopeName = scope.type === "all" ? "全部科目混合" : scope.name;
    scopeHtml = `<p class="muted small">范围：<b>${esc(scopeName)}</b></p>`;
  } else {
    const rows = allSubjects.map((s) => `
      <label class="opt" style="cursor:pointer">
        <input type="radio" name="p-scope" value="${esc(s.name)}">
        <span class="opt-text"><b>${esc(s.name)}</b>（${s.questionCount} 题 · 错题 ${s.wrongCount}）</span>
      </label>`).join("");
    scopeHtml = `
      <div class="form-group">
        <label>选择范围</label>
        <label class="opt" style="cursor:pointer"><input type="radio" name="p-scope" value="__all__" checked>
          <span class="opt-text"><b>全部科目混合</b></span></label>
        ${rows}
      </div>`;
  }

  const wrongLine = wrong
    ? `<p class="small muted">本次为<b>错题复习</b>：答对会自动移出错题本，仍答错的会更新时间戳继续保留。</p>`
    : `<div class="form-group">
        <label style="display:flex;align-items:center;gap:8px;font-weight:400">
          <input type="checkbox" id="p-wrong"> 仅刷错题（从错题本抽取）
        </label>
      </div>`;

  const m = openModal(`
    <div class="modal-head"><h3>开始刷题</h3><button class="modal-close">✕</button></div>
    <div class="modal-body">
      ${scopeHtml}
      <div class="form-group">
        <label>刷题模式（按题型以选项卡切换）</label>
        <div class="mode-tabs">
          <button type="button" class="mode-tab active" data-mode="all">全部题目</button>
          <button type="button" class="mode-tab" data-mode="by_type_tf">判断题</button>
          <button type="button" class="mode-tab" data-mode="by_type_choice">选择题</button>
          <button type="button" class="mode-tab" data-mode="by_type_fill">填空题</button>
        </div>
      </div>
      ${wrongLine}
    </div>
    <div class="modal-foot">
      <button class="btn btn-ghost" data-act="cancel">取消</button>
      <button class="btn btn-primary" data-act="start">开始</button>
    </div>`, "modal-lg");

  $(".modal-close", m.mask).addEventListener("click", () => m.close());
  $$(".mode-tab", m.mask).forEach((t) => t.addEventListener("click", () => {
    $$(".mode-tab", m.mask).forEach((x) => x.classList.toggle("active", x === t));
  }));
  m.mask.addEventListener("click", async (e) => {
    const act = e.target && e.target.dataset && e.target.dataset.act;
    if (act === "cancel") { m.close(); return; }
    if (act !== "start") return;
    let selScope = scope;
    if (!scope) {
      const radio = $('input[name="p-scope"]:checked', m.mask);
      const val = radio ? radio.value : "__all__";
      selScope = { type: val === "__all__" ? "all" : "subject", name: val };
    }
    if (!selScope) { toast("请先选择科目", "err"); return; }
    const modeTab = $(".mode-tab.active", m.mask);
    const modeVal = modeTab ? modeTab.dataset.mode : "all";
    const wrongChecked = wrong ? true : !!(m.mask.querySelector("#p-wrong") && m.mask.querySelector("#p-wrong").checked);
    m.close();
    await startPracticeSession({ scope: selScope, mode: modeVal, wrong: wrongChecked });
  });
}

const TYPE_OF_MODE = { all: null, by_type_tf: "判断题", by_type_choice: "选择题", by_type_fill: "填空题" };

async function buildPool(cfg) {
  const typeLabel = TYPE_OF_MODE[cfg.mode] || null;

  if (cfg.wrong) {
    /* 从错题本取题（只取题库中仍存在的题目） */
    const wrongData = await api("GET", "/api/wrong");
    let records = wrongData.items.filter((r) => r.found);
    if (cfg.scope.type === "subject") records = records.filter((r) => r.subject === cfg.scope.name);
    if (typeLabel) records = records.filter((r) => r.question_type === typeLabel);
    return records.map((r) => ({
      subject: r.subject,
      index: r.question.index,
      text: r.question.text,
      label: r.question.label,
      type: r.question.type,
      options: r.question.options,
      choice_type: r.question.choice_type,
      flag_star: !!r.question.flag_star,
      flag_cross: !!r.question.flag_cross,
    }));
  }

  /* 从题库取题 */
  const subjectNames = cfg.scope.type === "all"
    ? (state.overview ? state.overview.grades.flatMap((g) => g.subjects).map((s) => s.name) : null)
    : [cfg.scope.name];
  let items = [];
  if (subjectNames) {
    for (const s of subjectNames) {
      const data = await api("GET", `/api/questions?subject=${encodeURIComponent(s)}&pageSize=2000`);
      items = items.concat(data.items);
    }
  } else {
    const data = await api("GET", "/api/questions?pageSize=2000");
    items = data.items;
  }
  if (typeLabel) {
    if (typeLabel === "选择题") items = items.filter((it) => it.label === "单选题" || it.label === "多选题");
    else items = items.filter((it) => it.label === typeLabel);
  }
  return items.map((it) => ({
    subject: it.subject,
    index: it.index,
    text: it.text,
    label: it.label,
    type: it.type,
    options: it.options,
    choice_type: it.choice_type,
    flag_star: !!it.flag_star,
    flag_cross: !!it.flag_cross,
  }));
}

async function startPracticeSession(cfg, resumeInfo = null) {
  let pool;
  let totalBase;
  let doneBefore = 0;
  let pcfg;
  let modeKey;
  let wrong;

  if (resumeInfo) {
    const pr = resumeInfo.progress;
    const resolved = await api("POST", "/api/resolve", { remaining: pr.remaining || [] });
    pool = resolved.items.filter((r) => r.found).map((r) => ({
      subject: r.subject, index: r.index, text: r.text,
      label: r.question ? r.question.label : "", type: r.question ? r.question.type : "",
      options: r.question ? r.question.options : null, choice_type: r.question ? r.question.choice_type : null,
      flag_star: r.question ? !!r.question.flag_star : false,
      flag_cross: r.question ? !!r.question.flag_cross : false,
    }));
    totalBase = pr.total || pool.length;
    doneBefore = Math.max(0, totalBase - pool.length);
    wrong = String(pr.mode || "").endsWith("wrong");
    const mixed = pr.subject === "所有科目" || String(pr.mode).startsWith("all");
    pcfg = {
      scope: { type: mixed ? "all" : "subject", name: pr.subject },
      typeLabel: pr.type_label || null,
    };
    modeKey = pr.mode || "all";
    if (pool.length === 0) {
      // 进度里的题目都已不存在：清掉进度并提示
      await api("DELETE", "/api/progress");
      toast("进度中的题目已不存在，进度已清除", "info");
      render();
      return;
    }
  } else {
    const ov = await getOverview(true);
    if (cfg.wrong && ov.totalWrong === 0) { toast("错题本是空的，无需复习", "info"); return; }
    pool = shuffle(await buildPool(cfg));
    totalBase = pool.length;
    pcfg = { scope: cfg.scope, typeLabel: TYPE_OF_MODE[cfg.mode] || null };
    modeKey = cfg.mode;
    wrong = cfg.wrong;
    if (pool.length === 0) {
      toast(cfg.wrong ? "所选范围内没有可复习的错题" : "所选范围内没有符合条件的题目", "info");
      return;
    }
  }

  state.practice = {
    cfg: pcfg, wrong, modeKey,
    pool, pos: 0, doneBefore, totalBase,
    startTime: fmtNow(), endTime: null,
    subjects: {},
    stats: { total: 0, correct: 0, wrong: 0 },
    finished: false,
    answered: false,   // 是否已提交当前题的答案
    cursor: 0,         // 当前展示位置（可回看 < pos 的已答题）
    history: [],       // history[题序号] = {userAnswer, correct, correctAnswer}
    reportSaved: false,
    reportSaveFailed: false,
    reportSaving: false,
    reportName: "",
    reportShown: false,
  };
  navTo("practice");
}

/* —— 练习界面 —— */

async function renderPractice(view) {
  const ov = await getOverview();

  if (!state.practice) {
    view.innerHTML = `
      <div class="page-head"><h2>开始刷题</h2><div class="sub">选择范围与模式开始练习，随时可暂停并保存进度。</div></div>
      ${ov.hasProgress ? `
        <div class="card" style="padding:14px 18px;margin-bottom:18px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
          <span style="font-size:24px">⏸️</span>
          <div style="flex:1;min-width:200px">
            <div style="font-weight:700">有未完成的刷题进度</div>
            <div class="small muted">【${esc(ov.progress.subject)}】已完成 ${ov.progress.total - ov.progress.remainingCount} / ${ov.progress.total} 题</div>
          </div>
          <button class="btn btn-primary" id="resume-session">继续上次答题</button>
        </div>` : ""}
      <div class="card" style="padding:22px 24px;text-align:center">
        <div style="font-size:40px;margin-bottom:8px">📝</div>
        <div style="font-weight:700;font-size:16px;margin-bottom:4px">选择科目与模式，开始刷题</div>
        <div class="small muted" style="margin-bottom:16px">支持全部题目 / 按题型 / 错题复习 / 全部科目混合</div>
        <button class="btn btn-primary" id="open-cfg">＋ 选择科目与模式开始</button>
      </div>`;
    const resume = $("#resume-session", view);
    if (resume) resume.addEventListener("click", () => startResumeSession());
    const openCfg = $("#open-cfg", view);
    if (openCfg) openCfg.addEventListener("click", () => openPracticeConfig());
    return;
  }

  const p = state.practice;
  if (p.finished) { renderPracticeResult(view, p); return; }
  if (p.pos >= p.pool.length) { await finishPractice(p); renderPracticeResult(view, p); return; }
  renderPracticeQuestion(view, p);
}

function reviewHtmlFor(q, h, cur) {
  const title = h.correct ? "✅ 回答正确！" : "❌ 回答错误！";
  return `
    <div class="feedback ${h.correct ? "correct" : "wrong"}">
      <div class="fb-title">${title}</div>
      <div class="fb-line">正确答案：<b>${esc(ansShow(q, h.correctAnswer))}</b></div>
      <div class="fb-line">你的答案：${esc(h.userAnswer || "（未作答）")}</div>
    </div>`;
}

function renderPracticeQuestion(view, p) {
  const cur = Math.max(0, Math.min(p.cursor == null ? p.pos : p.cursor, Math.max(p.pos, 0)));
  const isReview = cur < p.pos;   // 回看已作答的题（只读）
  const q = p.pool[cur];
  const idx = p.doneBefore + cur + 1;
  const percent = Math.round(((p.doneBefore + cur) / Math.max(1, p.totalBase)) * 100);
  const scopeName = p.cfg.scope.type === "all" ? "全部科目混合" : (p.cfg.scope.name || "");

  let modeTxt = p.wrong ? "错题复习" : "刷题";
  if (p.cfg.typeLabel) modeTxt += ` · ${p.cfg.typeLabel}`;

  const canPrev = cur > 0 && !!p.history[cur - 1];
  const canNext = cur + 1 < p.pos;   // 回看模式下还能继续往前往后

  view.innerHTML = `
    <div class="practice-bar">
      <span class="badge badge-plain">${esc(modeTxt)}</span>
      <span class="small muted">${esc(scopeName)}</span>
      <div class="progress-wrap">
        <div class="progress-track"><div class="progress-fill" style="width:${percent}%"></div></div>
        <div class="progress-lbl">第 ${idx} / ${p.totalBase} 题</div>
      </div>
      <div class="session-stats">
        <span>答对 <span class="ok">${p.stats.correct}</span></span>
        <span>答错 <span class="no">${p.stats.wrong}</span></span>
      </div>
    </div>
    <div class="card q-card">
      <div class="q-head">
        ${badgeHtml(q.label || q.type)}
        <span class="q-subject">${esc(q.subject)}</span>
        <span class="q-count">题库第 ${q.index + 1} 题</span>
        ${isReview ? '<span class="badge badge-plain">已作答 · 只读</span>' : ""}
        <span style="margin-left:auto"></span>
        ${flagHtml(q)}
      </div>
      <div class="q-text">${questionBodyHtml(q)}</div>
      ${isReview ? '<div id="review-body"></div>' : '<div id="answer-area"></div><div id="feedback-area"></div><div id="action-area"></div>'}
    </div>
    <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
      ${isReview || (canPrev && !p.answered)
        ? `<button class="btn btn-ghost" id="prev-btn" ${isReview && !canPrev ? "disabled" : ""}>◀ 上一题</button>` : ""}
      ${isReview
        ? `<button class="btn btn-primary" id="resume-btn">▶ ${canNext ? "下一题" : "返回当前题"}</button>` : ""}
      <button class="btn btn-ghost" id="quit-btn">⏸ 退出并保存进度</button>
    </div>`;

  const quit = $("#quit-btn", view);
  quit.addEventListener("click", () => quitPractice(p));

  if (isReview) {
    // 只读回看已答题目
    const h = p.history[cur];
    if (h) $("#review-body", view).innerHTML = reviewHtmlFor(q, h, cur);
    const prev = $("#prev-btn", view);
    if (prev) prev.addEventListener("click", () => { p.cursor = cur - 1; render(); });
    const resume = $("#resume-btn", view);
    if (resume) resume.addEventListener("click", () => {
      p.cursor = canNext ? cur + 1 : p.pos;
      render();
    });
    return;
  }

  // 当前未答题（正常作答模式）
  const prevBtn = $("#prev-btn", view);
  if (prevBtn) prevBtn.addEventListener("click", () => { p.cursor = cur - 1; render(); });
  buildAnswerArea(view, p, q);
}

/* 用户答案的可读拼接（填空多空 / 数组） */
function fmtUserAnswer(val) {
  if (Array.isArray(val)) return val.map((v) => (v === "" ? "（空）" : v)).join(" ｜ ");
  return String(val == null ? "" : val);
}

function blankTagHtml(text) {
  /* 题干静态展示：把空位标记 【N】 渲染成占位标签 */
  return String(text == null ? "" : text).replace(/(【\s*\d+\s*】)/g, (m) => `<span class="blank-tag">${esc(m)}</span>`);
}

function questionBodyHtml(q) {
  /* 题干渲染：填空题把空位标记显示为占位标签 */
  const html = renderRichText(q.text);
  return q.type === "填空题" ? blankTagHtml(html) : html;
}

function buildAnswerArea(view, p, q) {
  const area = $("#answer-area", view);
  const submitAuto = (userAnswer) => submitAnswer(view, p, q, userAnswer);

  if (q.type === "判断题") {
    area.innerHTML = `
      <div class="tf-buttons">
        <button class="tf-btn t" data-v="正确">✓ 正确</button>
        <button class="tf-btn f" data-v="错误">✗ 错误</button>
      </div>`;
    $$(".tf-btn", area).forEach((b) => b.addEventListener("click", () => submitAuto(b.dataset.v)));
    return;
  }

  if (q.type === "单选题" || q.type === "多选题") {
    const single = q.type === "单选题";
    const autoSubmitSingle = single && !!state.settings.choiceAutoSubmit;  // 设置：单选点击即提交
    const opts = (q.options || []).map(([letter, text]) => `
      <label class="opt" data-letter="${letter}">
        <span class="opt-key">${letter}</span>
        <span class="opt-text">${renderRichText(text)}</span>
      </label>`).join("");
    const submitBtn = autoSubmitSingle
      ? ""
      : '<button class="btn btn-primary" id="choice-submit" disabled>提交答案</button>';
    area.innerHTML = `
      <div class="opt-list" id="opt-list">
        ${single && autoSubmitSingle ? '<div class="small muted" style="margin-bottom:4px">单选题：点击选项即直接提交</div>'
          : single ? "" : '<div class="small muted" style="margin-bottom:4px">多选题：点击选择所有正确答案后手动提交</div>'}
        ${opts}
      </div>
      ${submitBtn}`;
    const list = $("#opt-list", area);
    const submit = $("#choice-submit", area);
    let sel = new Set();
    const refreshSubmit = () => { if (submit) submit.disabled = single ? sel.size !== 1 : sel.size < 1; };
    $$(".opt", list).forEach((o) => {
      o.addEventListener("click", () => {
        const letter = o.dataset.letter;
        if (single) {
          sel = new Set([letter]);
          $$(".opt", list).forEach((x) => x.classList.toggle("selected", x.dataset.letter === letter));
          if (autoSubmitSingle) submitAuto(letter);
        } else {
          if (sel.has(letter)) { sel.delete(letter); o.classList.remove("selected"); }
          else { sel.add(letter); o.classList.add("selected"); }
        }
        refreshSubmit();
      });
    });
    if (submit) submit.addEventListener("click", () => {
      const ans = LETTERS.filter((l) => sel.has(l)).join("");
      if (!ans) { toast("请选择答案", "info"); return; }
      submitAuto(ans);
    });
    return;
  }

  if (q.type === "填空题") {
    if (q.wholeString) {
      // 整串模式：一次输入完整答案（旧数据/代码输出题）
      area.innerHTML = `<input class="answer-input" id="fill-input" placeholder="请输入完整答案后回车提交" autocomplete="off">
        <button class="btn btn-primary" id="text-submit">提交答案</button>`;
      const input = $("#fill-input", area);
      const submit = $("#text-submit", area);
      const doSubmit = () => {
        const v = input.value.trim();
        if (!v) { toast("请输入答案", "info"); return; }
        submitAuto(v);
      };
      submit.addEventListener("click", doSubmit);
      input.addEventListener("keydown", (e) => { if (e.key === "Enter") doSubmit(); });
    } else {
      const n = q.blankCount || 1;
      let boxes = "";
      for (let i = 1; i <= n; i++) boxes += `
        <div class="fill-row"><span class="fill-idx">第${i}空</span>
        <input class="answer-input" id="blank-${i}" data-blank="${i}" placeholder="填写答案" autocomplete="off" style="flex:1"></div>`;
      area.innerHTML = `<div class="fill-list">${boxes}</div>
        <button class="btn btn-primary" id="fill-submit" style="margin-top:8px">提交答案</button>`;
      const submit = $("#fill-submit", area);
      const doSubmit = () => {
        const vals = [];
        for (let i = 1; i <= n; i++) vals.push($(`#blank-${i}`, area).value.trim());
        if (vals.every((v) => v === "")) { toast("请至少填写一个空", "info"); return; }
        submitAuto(vals);
      };
      submit.addEventListener("click", doSubmit);
      $$("input[data-blank]", area).forEach((el) =>
        el.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); doSubmit(); } }));
    }
    return;
  }

  if (q.type === "计算题") {
    area.innerHTML = `<input class="answer-input" id="fill-input" placeholder="请输入计算结果后回车提交" autocomplete="off">
      <button class="btn btn-primary" id="text-submit">提交答案</button>`;
    const input = $("#fill-input", area);
    const submit = $("#text-submit", area);
    const doSubmit = () => {
      const v = input.value.trim();
      if (!v) { toast("请输入答案", "info"); return; }
      submitAuto(v);
    };
    submit.addEventListener("click", doSubmit);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") doSubmit(); });
    return;
  }

  if (q.type === "简答题") {
    // 简答：不自动判分，提交后展示参考答案并自评
    area.innerHTML = `<textarea class="answer-input" id="essay-input" rows="4" placeholder="输入你的答案（支持多行）…"></textarea>
      <button class="btn btn-primary" id="essay-submit">提交答案</button>`;
    const submit = $("#essay-submit", area);
    submit.addEventListener("click", async () => {
      const v = $("#essay-input", area).value.trim();
      if (!v) { toast("请输入答案", "info"); return; }
      if (p.answered) return;
      p.answered = true;
      $$("button,input,textarea", area).forEach((el) => { el.disabled = true; });
      let data;
      try {
        data = await api("POST", "/api/answer", {
          subject: q.subject, index: q.index, answer: v, mode: p.wrong ? "wrong" : "all",
        });
      } catch (e) { return; }
      const fb = $("#feedback-area", view);
      fb.innerHTML = `
        <div class="feedback neutral">
          <div class="fb-title">📝 简答题（不自动判分）</div>
          <div class="fb-line">参考答案：${esc(data.answer || "（无）")}</div>
          <div class="fb-line">你的答案：${esc(v)}</div>
          <div class="hint" style="margin-top:6px">请对照参考答案自行判定：</div>
          <div style="display:flex;gap:8px;margin-top:8px">
            <button class="btn btn-primary" id="self-y">答对 ✓</button>
            <button class="btn btn-ghost" id="self-n">答错 ✗</button>
            <button class="btn btn-ghost" id="self-skip">跳过不计</button>
          </div>
        </div>`;
      const decide = async (selfCorrect) => {
        if (selfCorrect === null) {  // 跳过：不计统计
          p.answered = true;
          showNextButton(p, view);
          return;
        }
        try {
          await api("POST", "/api/answer/self", {
            subject: q.subject, index: q.index, answer: v, selfCorrect,
            mode: p.wrong ? "wrong" : "all",
          });
        } catch (e) { return; }
        finishAnsweredResult(view, p, q, v, selfCorrect, data.answer, fb);
      };
      $("#self-y", view).addEventListener("click", () => decide(true));
      $("#self-n", view).addEventListener("click", () => decide(false));
      $("#self-skip", view).addEventListener("click", () => decide(null));
    });
    return;
  }

  // 兜底：文本输入（不应出现）
  area.innerHTML = `<input class="answer-input" id="fill-input" placeholder="请输入答案" autocomplete="off">
    <button class="btn btn-primary" id="text-submit">提交答案</button>`;
  const input = $("#fill-input", area);
  const submit = $("#text-submit", area);
  const doSubmit = () => { const v = input.value.trim(); if (v) submitAuto(v); };
  submit.addEventListener("click", doSubmit);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") doSubmit(); });
}

/* 判分结果收尾：更新统计/历史/锁定输入/显示反馈/出现“下一题” */
function finishAnsweredResult(view, p, q, userAnswer, correct, correctText, fbEl) {
  p.stats.total += 1;
  if (correct) p.stats.correct += 1; else p.stats.wrong += 1;
  const s = p.subjects[q.subject] || (p.subjects[q.subject] = { total: 0, correct: 0, wrong: 0 });
  s.total += 1;
  if (correct) s.correct += 1; else s.wrong += 1;
  p.history[p.pos] = { userAnswer, correct, correctAnswer: correctText };

  const area = $("#answer-area", view);
  $$("button,input,textarea", area).forEach((el) => { el.disabled = true; });
  if (q.type === "判断题") {
    const correctVal = correctText === "正确" ? "正确" : "错误";
    $$(".tf-btn", area).forEach((b) => {
      const v = b.dataset.v;
      if (v === correctVal) b.classList.add("correct");
      else if (v === fmtUserAnswer(userAnswer)) b.classList.add("wrong");
    });
  } else if (q.type === "单选题" || q.type === "多选题") {
    const ansSet = new Set(String(correctText || "").toUpperCase().replace(/\s/g, "").split("").filter(Boolean));
    const userSet = new Set(String(userAnswer || "").toUpperCase().split("").filter(Boolean));
    $$(".opt", area).forEach((o) => {
      const letter = o.dataset.letter;
      if (ansSet.has(letter)) o.classList.add("correct");
      if (userSet.has(letter) && !ansSet.has(letter)) o.classList.add("wrong");
    });
  }
  if (fbEl) {
    fbEl.innerHTML = `
      <div class="feedback ${correct ? "correct" : "wrong"}">
        <div class="fb-title">${correct ? "✅ 回答正确！" : "❌ 回答错误！"}</div>
        ${correct ? "" : `<div class="fb-line">正确答案：<b>${esc(correctText)}</b></div>
        <div class="fb-line">你的答案：${esc(fmtUserAnswer(userAnswer))}</div>`}
      </div>`;
  }
  showNextButton(p, view);
}

function showNextButton(p, view) {
  const act = $("#action-area", view);
  const last = p.pos >= p.pool.length - 1;
  act.innerHTML = `<button class="btn btn-primary" id="next-btn" style="min-width:150px">${last ? "查看结果 🏁" : "下一题 →"}</button>`;
  $("#next-btn", view).addEventListener("click", () => { p.pos += 1; p.answered = false; p.cursor = p.pos; render(); });
}

async function submitAnswer(view, p, q, userAnswer) {
  if (p.answered) return;
  p.answered = true;
  const data = await api("POST", "/api/answer", {
    subject: q.subject, index: q.index, answer: userAnswer, mode: p.wrong ? "wrong" : "all",
  });
  if (data.auto === false) {
    // 简答不应走到这里（走 essay 流程）；兜底当跳过处理
    showNextButton(p, view);
    return;
  }
  finishAnsweredResult(view, p, q, userAnswer, data.correct, data.answer, $("#feedback-area", view));
}

async function finishPractice(p) {
  p.finished = true;
  p.endTime = fmtNow();
  // 答完最后一题：清除进度文件（与终端版一致）
  try { await api("DELETE", "/api/progress"); } catch (e) { /* ignore */ }
  // 每组完成自动保存报告
  if (p.stats.total > 0) await savePracticeReport(p);
}

async function savePracticeReport(p) {
  if (p.reportSaved || p.reportSaving) return !!p.reportSaved;
  p.reportSaving = true;
  try {
    const subjects = Object.entries(p.subjects).map(([name, s]) => ({ name, total: s.total, correct: s.correct, wrong: s.wrong }));
    const res = await api("POST", "/api/reports", { start_time: p.startTime, end_time: p.endTime, subjects });
    p.reportSaved = true;
    p.reportName = res.path || "";
    p.reportSaveFailed = false;
    toast("本次刷题报告已自动保存", "ok");
  } catch (e) { /* api 已提示 */ p.reportSaveFailed = true; }
  p.reportSaving = false;
  return !!p.reportSaved;
}

async function showReportModal(name) {
  let res;
  try {
    res = await api("GET", `/api/reports/${encodeURIComponent(name)}`);
  } catch (e) { return; }
  const m = openModal(`
    <div class="modal-head"><h3>刷题报告</h3><button class="modal-close">✕</button></div>
    <div class="modal-body"><pre class="report-content">${esc(res.content)}</pre></div>
    <div class="modal-foot">
      <button class="btn btn-ghost" data-act="close">关闭</button>
      <button class="btn btn-primary" data-act="goto">去「刷题报告」页</button>
    </div>`, "modal-lg");
  $(".modal-close", m.mask).addEventListener("click", () => m.close());
  m.mask.addEventListener("click", (e) => {
    const act = e.target && e.target.dataset && e.target.dataset.act;
    if (act === "close") m.close();
    else if (act === "goto") { m.close(); navTo("reports"); }
  });
}

function renderPracticeResult(view, p) {
  const rate = p.stats.total > 0 ? Math.round((p.stats.correct / p.stats.total) * 100) : 0;
  const scopeName = p.cfg.scope.type === "all" ? "全部科目混合" : (p.cfg.scope.name || "");
  const subjCards = Object.entries(p.subjects).map(([name, s]) => `
    <div class="summary-subject">
      <div class="ss-name">${esc(name)}</div>
      <div class="small">共 ${s.total} 题 · 对 <span style="color:var(--green);font-weight:700">${s.correct}</span> · 错 <span style="color:var(--red);font-weight:700">${s.wrong}</span></div>
    </div>`).join("");

  const reportStatus = p.reportSaved
    ? `<div class="feedback correct">📄 报告已自动保存：${esc(p.reportName)}</div>`
    : p.reportSaveFailed
      ? `<div class="feedback wrong">自动保存报告失败，可点下方「重试保存报告」。</div>`
      : `<div class="small muted">正在自动保存本次报告…</div>`;

  view.innerHTML = `
    <div class="page-head"><h2>本次练习完成 🎉</h2><div class="sub">${esc(p.startTime)} ～ ${esc(p.endTime)}</div></div>
    <div class="card" style="padding:22px 26px">
      <div style="display:flex;gap:26px;align-items:center;flex-wrap:wrap">
        <div style="text-align:center">
          <div style="font-size:46px;font-weight:800;color:${rate >= 60 ? "var(--green)" : "var(--orange)"}">${rate}%</div>
          <div class="small muted">正确率</div>
        </div>
        <div style="flex:1;min-width:200px">
          <div style="font-weight:700;font-size:17px">${esc(scopeName)} · ${p.wrong ? "错题复习" : "刷题"}</div>
          <div class="small muted">共 ${p.stats.total} 题，答对 ${p.stats.correct} 题，答错 ${p.stats.wrong} 题</div>
        </div>
      </div>
      ${Object.keys(p.subjects).length > 1 ? `<div class="summary-cards">${subjCards}</div>` : ""}
      <div style="margin-top:14px">${reportStatus}</div>
      <div style="display:flex;gap:10px;margin-top:14px;flex-wrap:wrap">
        <button class="btn btn-primary" id="report-view" style="${p.reportSaved ? "" : "display:none"}">📄 查看报告</button>
        <button class="btn btn-primary" id="report-retry" style="${p.reportSaveFailed ? "" : "display:none"}">↻ 重试保存报告</button>
        <button class="btn btn-ghost" id="again">再刷一组</button>
        <button class="btn btn-ghost" id="back-home">返回仪表盘</button>
      </div>
    </div>`;

  $("#again", view).addEventListener("click", () => { state.practice = null; navTo("practice"); });
  $("#back-home", view).addEventListener("click", () => { state.practice = null; invalidateOverview(); navTo("home"); });
  const viewBtn = $("#report-view", view);
  if (viewBtn) viewBtn.addEventListener("click", () => showReportModal(p.reportName));
  const retryBtn = $("#report-retry", view);
  if (retryBtn) retryBtn.addEventListener("click", async () => {
    await savePracticeReport(p);
    render();
  });

  // 自动保存成功：结果页首次出现时自动弹出报告一次
  if (p.reportSaved && !p.reportShown) {
    p.reportShown = true;
    showReportModal(p.reportName);
  }
}

/* —— 中途退出：保存进度 —— */

async function quitPractice(p) {
  if (!p || p.finished) { state.practice = null; navTo("home"); return; }
  const answeredCurrent = p.answered ? 1 : 0;
  const remaining = p.pool.slice(p.pos + answeredCurrent);
  const done = p.doneBefore + p.pos + answeredCurrent;
  const isMixed = p.cfg.scope.type === "all";
  const modeKey = p.modeKey || "all";

  const ok = await confirmModal({
    title: "暂停练习",
    message: `已完成 ${done} / ${p.totalBase} 题。<br>剩余 ${remaining.length} 题将保存为进度，之后可「继续答题」。`,
    okText: "保存进度并退出",
  });
  if (!ok) return;

  if (remaining.length > 0) {
    const mode = modeKey + (p.wrong && !String(modeKey).endsWith("wrong") ? "_wrong" : "");
    await api("POST", "/api/progress", {
      subject: isMixed ? "所有科目" : (p.cfg.scope.name || ""),
      mode,
      type_label: p.cfg.typeLabel || null,
      remaining: remaining.map((r) => ({ subject: r.subject, text: r.text })),
      total: p.totalBase,
    });
    toast("进度已保存，可在「开始刷题」或首页继续", "ok");
  }
  state.practice = null;
  invalidateOverview();
  navTo("home");
}

/* —— 继续答题 —— */

async function startResumeSession() {
  const pr = await api("GET", "/api/progress");
  if (!pr.exists) { toast("没有可继续的进度", "info"); return; }
  if (!pr.progress || !(pr.progress.remaining || []).length) {
    await api("DELETE", "/api/progress");
    toast("进度为空，已清除", "info");
    render();
    return;
  }
  await startPracticeSession(null, { progress: pr.progress });
}

/* ============================================================
   错题本
   ============================================================ */

async function renderWrong(view) {
  const f = state.wrongFilter;
  const params = new URLSearchParams();
  if (f.subject && f.subject !== "全部科目") params.set("subject", f.subject);
  const data = await api("GET", `/api/wrong?${params.toString()}`);
  const all = data.items;

  const subjectCounts = {};
  all.forEach((r) => { subjectCounts[r.subject] = (subjectCounts[r.subject] || 0) + 1; });
  const subjects = Object.keys(subjectCounts).sort();
  const typeCounts = {};
  all.forEach((r) => { typeCounts[r.question_type] = (typeCounts[r.question_type] || 0) + 1; });
  const types = Object.keys(typeCounts).sort();

  let shown = all;
  if (f.subject !== "全部科目") shown = shown.filter((r) => r.subject === f.subject);
  if (f.type !== "全部") shown = shown.filter((r) => r.question_type === f.type);

  const chipSubject = `<button class="chip ${f.subject === "全部科目" ? "active" : ""}" data-k="subject" data-v="全部科目">全部科目 (${all.length})</button>` +
    subjects.map((s) => `<button class="chip ${f.subject === s ? "active" : ""}" data-k="subject" data-v="${esc(s)}">${esc(s)} (${subjectCounts[s]})</button>`).join("");
  const chipType = `<button class="chip ${f.type === "全部" ? "active" : ""}" data-k="type" data-v="全部">全部题型</button>` +
    types.map((t) => `<button class="chip ${f.type === t ? "active" : ""}" data-k="type" data-v="${esc(t)}">${esc(t)} (${typeCounts[t]})</button>`).join("");

  const rows = shown.length === 0
    ? `<div class="empty"><div class="big">${all.length === 0 ? "🎉" : "🔍"}</div>${all.length === 0 ? "错题本是空的，继续保持！" : "没有符合条件的错题记录。"}</div>`
    : shown.map((r) => `
      <div class="wrong-item" data-idx="${r.index}">
        <div class="wrong-head">
          ${badgeHtml(r.question_type)}
          <span class="q-subject">${esc(r.subject)}</span>
          ${r.found ? "" : '<span class="stale-tip">题目已不在题库中</span>'}
          <div class="wrong-actions">
            ${r.found ? `<button class="btn btn-sm btn-ghost" data-a="review">复习本题</button>` : ""}
            <button class="btn btn-sm btn-red-ghost" data-a="del">删除</button>
          </div>
        </div>
        <div class="wrong-text clamped" data-a="expand">${renderRichText(r.question_text)}</div>
        <div class="wrong-answer-line">
          <span>我的答案 <span class="wa-wrong">${esc(r.wrong_answer || "（空）")}</span></span>
          <span>正确答案 <span class="wa-correct">${esc(r.correct_answer || "（空）")}</span></span>
          <span class="wa-time">🕐 ${esc(r.timestamp || "")}</span>
        </div>
      </div>`).join("");

  view.innerHTML = `
    <div class="page-head">
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
        <div><h2>错题本</h2><div class="sub">共 ${all.length} 条错题记录（复习中答对会自动移除）</div></div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-primary" id="btn-review-all" ${all.length === 0 ? "disabled" : ""}>▶ 复习全部错题</button>
          <button class="btn btn-red-ghost" id="btn-clear-all" ${all.length === 0 ? "disabled" : ""}>清空错题本</button>
        </div>
      </div>
    </div>
    <div class="filter-chips">${chipSubject}</div>
    <div class="filter-chips">${chipType}</div>
    ${rows}`;

  $$(".chip", view).forEach((c) => c.addEventListener("click", () => {
    const k = c.dataset.k, v = c.dataset.v;
    if (k === "subject") f.subject = v;
    if (k === "type") f.type = v;
    render();
  }));

  view.addEventListener("click", async (e) => {
    const expandEl = e.target.closest("[data-a='expand']");
    if (expandEl) { expandEl.classList.toggle("clamped"); return; }

    const btn = e.target.closest("[data-a]");
    if (!btn) return;
    const a = btn.dataset.a;
    const itemEl = btn.closest(".wrong-item");
    if (!itemEl) return;
    const idx = Number(itemEl.dataset.idx);
    const rec = all.find((x) => x.index === idx);
    if (!rec) return;

    if (a === "del") {
      if (await confirmModal({ title: "删除错题记录", message: `确定删除【${esc(rec.subject)}】的这条错题记录吗？`, okText: "删除", danger: true })) {
        await api("DELETE", `/api/wrong?index=${idx}`);
        toast("已删除", "ok");
        invalidateOverview();
        render();
      }
    } else if (a === "review") {
      await openPracticeConfig({ scope: { type: "subject", name: rec.subject }, wrong: true });
    }
  });

  $("#btn-review-all", view).addEventListener("click", () => {
    openPracticeConfig({ scope: { type: "all" }, wrong: true });
  });
  $("#btn-clear-all", view).addEventListener("click", async () => {
    const ok = await confirmModal({
      title: "清空整个错题本",
      message: "此操作将删除<b>全部</b>错题记录，不可恢复！<br>确认要清空吗？",
      okText: "确认清空",
      danger: true,
    });
    if (ok) {
      await api("DELETE", "/api/wrong?all=1");
      toast("错题本已清空", "ok");
      invalidateOverview();
      render();
    }
  });
}

/* ============================================================
   题库管理
   ============================================================ */

async function renderLibrary(view) {
  const f = state.libFilter;
  const ov = await getOverview();
  const allSubjects = ov.grades.flatMap((g) => g.subjects);

  const params = new URLSearchParams();
  if (f.subject !== "全部科目") params.set("subject", f.subject);
  if (f.keyword) params.set("keyword", f.keyword);
  if (f.type && f.type !== "全部") params.set("type", f.type);
  if (f.flags) params.set("flags", f.flags);
  params.set("page", String(f.page));
  params.set("pageSize", "20");
  const data = await api("GET", `/api/questions?${params.toString()}`);
  const pageSize = 20;
  const pages = Math.max(1, Math.ceil(data.total / pageSize));

  const selSubj = f.subject !== "全部科目" ? f.subject : "";
  const selInfo = allSubjects.find((x) => x.name === selSubj);
  const selCnt = selInfo ? selInfo.questionCount : 0;

  /* 批量勾选状态：以 subject|index 为键，每次重新渲染重置（换页/筛选后清空） */
  const selSet = new Set();
  state.libSel = selSet;
  const selKey = (subj, idx) => `${subj}|${idx}`;

  const sideList = `<button class="subj-item ${f.subject === "全部科目" ? "active" : ""}" data-subj="全部科目">
      <span>全部科目</span><span class="cnt">${ov.totalQuestions} 题</span></button>` +
    allSubjects.map((s) => `
      <button class="subj-item ${f.subject === s.name ? "active" : ""}" data-subj="${esc(s.name)}">
        <span>${esc(s.name)}</span><span class="cnt">${s.questionCount} 题</span>
      </button>`).join("");

  const rows = data.items.length === 0
    ? `<div class="empty"><div class="big">🔍</div>${(data.total === 0 && !f.keyword) ? "该范围还没有题目，点右上角「录入题目」添加。" : "没有符合条件的题目。"}</div>`
    : data.items.map((it) => `
      <div class="q-row" data-subj="${esc(it.subject)}" data-idx="${it.index}">
        <div class="q-row-head">
          <input type="checkbox" class="row-check" data-sel="${esc(selKey(it.subject, it.index))}" title="选择删除">
          <span class="idx">#${it.index + 1}</span>
          ${badgeHtml(it.label)}
          <span class="q-subject">${esc(it.subject)}</span>
          <span class="q-preview" data-a="expand">${esc(it.text.replace(/\n/g, " "))}</span>
          ${flagHtml(it)}
          <div class="q-row-actions">
            <button class="btn btn-sm btn-ghost" data-a="edit">编辑</button>
            <button class="btn btn-sm btn-red-ghost" data-a="del">删除</button>
          </div>
        </div>
      </div>`).join("");

  view.innerHTML = `
    <div class="page-head">
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
        <div><h2>题库管理</h2><div class="sub">浏览 / 搜索 / 录入 / 修改 / 删除题目（与终端版数据互通）</div></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn btn-ghost" id="btn-import-batch">📥 批量导入（judge）</button>
          <button class="btn btn-primary" id="btn-add">＋ 录入题目</button>
        </div>
      </div>
    </div>
    <div class="library-layout">
      <aside class="library-side">
        <div class="card side-card">
          <div class="side-title">科目</div>
          <div class="subj-list">${sideList}</div>
          <div class="side-actions">
            <button class="btn btn-sm btn-primary" id="lib-dup" ${selSubj && selCnt >= 2 ? "" : "disabled"}>🔎 题目查重${selSubj ? `：${esc(selSubj)}` : ""}</button>
          </div>
        </div>
      </aside>
      <section class="library-main">
        <div class="search-bar">
          <input class="search-input" id="kw" placeholder="搜索题干关键词…（全部科目时跨科目搜索）" value="${esc(f.keyword)}">
          <select class="answer-input" id="type-sel" style="width:auto">
            <option value="全部">全部题型</option>
            <option value="判断题">判断题</option>
            <option value="单选题">单选题</option>
            <option value="多选题">多选题</option>
            <option value="填空题">填空题</option>
            <option value="简答题">简答题</option>
            <option value="计算题">计算题</option>
          </select>
          <select class="answer-input" id="flag-sel" style="width:auto" title="按标记筛选">
            <option value="">全部标记</option>
            <option value="star">⭐ 黄星标记</option>
            <option value="cross">❌ 红叉标记</option>
            <option value="any">星或叉标记</option>
          </select>
          <button class="btn btn-primary" id="btn-search">搜索</button>
        </div>
        <div class="muted small" style="margin-bottom:10px">共 <b>${data.total}</b> 条结果</div>
        ${data.items.length ? `
        <div class="batch-bar">
          <label class="small" style="display:flex;align-items:center;gap:6px;cursor:pointer">
            <input type="checkbox" id="sel-page"> 全选本页
          </label>
          <span class="small muted" id="sel-count">已选 0 题</span>
          <button class="btn btn-sm btn-red-ghost" id="btn-sel-del" disabled>🗑 批量删除（移入回收站）</button>
        </div>` : ""}
        ${rows}
        <div class="pager">
          <button class="btn btn-sm btn-ghost" id="pg-first" title="首页" ${f.page <= 1 ? "disabled" : ""}>«</button>
          <button class="btn btn-sm btn-ghost" id="pg-minus2" title="前两页" ${f.page <= 2 ? "disabled" : ""}>−2 页</button>
          <button class="btn btn-sm btn-ghost" id="pg-prev" ${f.page <= 1 ? "disabled" : ""}>上一页</button>
          <span class="small muted">第 <b>${f.page}</b> / ${pages} 页</span>
          <button class="btn btn-sm btn-ghost" id="pg-next" ${f.page >= pages ? "disabled" : ""}>下一页</button>
          <button class="btn btn-sm btn-ghost" id="pg-plus2" title="后两页" ${f.page + 2 > pages ? "disabled" : ""}>+2 页</button>
          <button class="btn btn-sm btn-ghost" id="pg-last" title="末页" ${f.page >= pages ? "disabled" : ""}>»</button>
          <span class="pg-jump">
            <input class="search-input" id="pg-input" type="number" min="1" max="${pages}" placeholder="页" style="width:58px;padding:5px 8px">
            <button class="btn btn-sm btn-ghost" id="pg-go">跳转</button>
          </span>
        </div>
      </section>
    </div>`;

  $("#type-sel", view).value = f.type;
  $("#flag-sel", view).value = f.flags || "";

  $$(".subj-item", view).forEach((b) => b.addEventListener("click", () => {
    f.subject = b.dataset.subj; f.keyword = ""; f.flags = ""; f.page = 1; render();
  }));

  /* 侧栏下方：查重（当前科目） */
  const libDup = $("#lib-dup", view);
  if (libDup) libDup.addEventListener("click", () => {
    if (!selSubj) { toast("请先在左侧选择一个科目", "info"); return; }
    if (selCnt < 2) { toast("该科目题目不足 2 题，无法查重", "info"); return; }
    openDuplicates(selSubj);
  });

  /* 批量勾选：本页选择 + 批量删除 */
  const setSelUI = () => {
    const n = selSet.size;
    const countEl = $("#sel-count", view);
    const delBtn = $("#btn-sel-del", view);
    if (countEl) countEl.textContent = `已选 ${n} 题`;
    if (delBtn) delBtn.disabled = n === 0;
  };
  const pageKeys = data.items.map((it) => selKey(it.subject, it.index));
  $$(".row-check", view).forEach((c) => {
    c.checked = selSet.has(c.dataset.sel);
    c.addEventListener("change", () => {
      if (c.checked) selSet.add(c.dataset.sel); else selSet.delete(c.dataset.sel);
      const pageSelEl = $("#sel-page", view);
      if (pageSelEl) pageSelEl.checked = pageKeys.length > 0 && pageKeys.every((k) => selSet.has(k));
      setSelUI();
    });
  });
  const pageSelEl = $("#sel-page", view);
  if (pageSelEl) pageSelEl.addEventListener("change", () => {
    if (pageSelEl.checked) pageKeys.forEach((k) => selSet.add(k));
    else pageKeys.forEach((k) => selSet.delete(k));
    $$(".row-check", view).forEach((c) => { c.checked = pageSelEl.checked; });
    setSelUI();
  });
  const btnSelDel = $("#btn-sel-del", view);
  if (btnSelDel) btnSelDel.addEventListener("click", async () => {
    if (selSet.size === 0) return;
    const items = [...selSet].map((key) => {
      const [subj, idxStr] = key.split("|");
      const idx = Number(idxStr);
      const it = data.items.find((x) => x.subject === subj && x.index === idx);
      return { subject: subj, index: idx, text: it ? it.text : undefined };
    });
    const ok = await confirmModal({
      title: "批量删除题目",
      message: `确定删除选中的 <b>${selSet.size}</b> 题吗？<br>删除后将移入回收站（最多保存 500 条），并同步清理对应错题本记录。`,
      okText: "删除", danger: true,
    });
    if (!ok) return;
    const res = await api("POST", "/api/questions/batch-delete", { items });
    toast(`已删除 ${res.deleted} 题（已移入回收站）${(res.skipped || []).length ? `，${res.skipped.length} 题跳过` : ""}`, "ok");
    invalidateOverview();
    render();
  });

  const kw = $("#kw", view);
  const doSearch = () => { f.keyword = kw.value.trim(); f.page = 1; render(); };
  $("#btn-search", view).addEventListener("click", doSearch);
  kw.addEventListener("keydown", (e) => { if (e.key === "Enter") doSearch(); });
  $("#type-sel", view).addEventListener("change", (e) => { f.type = e.target.value; f.page = 1; render(); });
  $("#flag-sel", view).addEventListener("change", (e) => { f.flags = e.target.value; f.page = 1; render(); });
  const goPage = (p) => { const np = Math.max(1, Math.min(pages, Math.floor(p) || 1)); if (np !== f.page) { f.page = np; render(); } };
  $("#pg-first", view).addEventListener("click", () => goPage(1));
  $("#pg-last", view).addEventListener("click", () => goPage(pages));
  $("#pg-prev", view).addEventListener("click", () => goPage(f.page - 1));
  $("#pg-next", view).addEventListener("click", () => goPage(f.page + 1));
  $("#pg-minus2", view).addEventListener("click", () => goPage(f.page - 2));
  $("#pg-plus2", view).addEventListener("click", () => goPage(f.page + 2));
  const pgInput = $("#pg-input", view);
  const jumpGo = () => { const v = parseInt(pgInput.value, 10); if (!Number.isNaN(v)) goPage(v); };
  $("#pg-go", view).addEventListener("click", jumpGo);
  pgInput.addEventListener("keydown", (e) => { if (e.key === "Enter") jumpGo(); });
  setSelUI();

  view.addEventListener("click", async (e) => {
    const t = e.target.closest("[data-a]");
    if (!t) return;
    const a = t.dataset.a;
    const row = t.closest(".q-row");
    if (!row) return;
    const subj = row.dataset.subj;
    const idx = Number(row.dataset.idx);
    const item = data.items.find((x) => x.subject === subj && x.index === idx);
    if (!item) return;

    if (a === "expand") openQuestionDetail(item);
    else if (a === "edit") openQuestionEditor(item, async () => { toast("题目已更新", "ok"); invalidateOverview(); render(); });
    else if (a === "del") {
      const ok = await confirmModal({
        title: "删除题目",
        message: `确定删除【${esc(subj)}】的第 ${idx + 1} 题吗？<br>删除后将移入回收站，并同步清理对应错题本记录。`,
        okText: "删除", danger: true,
      });
      if (ok) {
        await api("DELETE", `/api/questions?subject=${encodeURIComponent(subj)}&index=${idx}`);
        toast("题目已删除", "ok");
        invalidateOverview();
        render();
      }
    }
  });

  $("#btn-add", view).addEventListener("click", () => openQuestionEditor(null, async () => { toast("题目已录入", "ok"); invalidateOverview(); render(); }));

  const batchBtn = $("#btn-import-batch", view);
  if (batchBtn) batchBtn.addEventListener("click", () => {
    if (f.subject !== "全部科目") {
      resetImportFlow(f.subject);                  // 每次进入都重新开始（带默认字段）
    } else {
      state.importFlow = null;
    }
    navTo("import");
  });
}

/* ============================================================
   题目查重（科目内相似题 + 相似度百分比）
   ============================================================ */

function simClass(sim) {
  if (sim >= 90) return "dup-90";
  if (sim >= 80) return "dup-80";
  if (sim >= 70) return "dup-70";
  return "dup-60";
}

function dupDetailHtml(it, tag) {
  const optsHtml = Array.isArray(it.options) && it.options.length
    ? `<div style="margin-top:6px">${it.options.map(([l, txt]) => `<div class="small"><b>${esc(l)}.</b> ${renderRichText(txt)}</div>`).join("")}</div>`
    : "";
  return `
    <div style="margin-bottom:6px"><span class="badge badge-${esc(it.label)}">${esc(it.label)}</span> ${tag}#${it.index + 1}</div>
    <div class="q-text" style="font-size:14.5px">${renderRichText(it.text)}</div>
    ${optsHtml}
    <div class="small" style="margin-top:4px">答案：<b>${esc(ansShow(it, it.answer))}</b></div>`;
}

async function openDuplicates(subject, threshold = 60) {
  const m = openModal(`
    <div class="modal-head"><h3>题目查重 · ${esc(subject)}</h3><button class="modal-close">✕</button></div>
    <div class="modal-body" id="dup-body"><div class="loading">正在比对相似度…</div></div>`, "modal-lg");
  $(".modal-close", m.mask).addEventListener("click", () => m.close());

  let pairs = [];
  let total = 0;
  let truncated = false;
  const expanded = new Set();
  const picked = new Set();      // 要删除的题目（题库 index）
  const textByIndex = new Map(); // index -> 题干（删除时防错位）

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function progressHtml(pct, msg) {
    const p = Math.max(0, Math.min(100, Math.round(pct)));
    return `
      <div class="small muted" style="margin-bottom:6px">${esc(msg)}</div>
      <div class="progress-track"><div class="progress-fill" style="width:${p}%"></div></div>
      <div class="small muted" style="margin-top:6px">正在比对相似度… <b>${p}%</b></div>`;
  }

  async function load(subj, th) {
    const body = $("#dup-body", m.mask);
    if (!body) return;
    body.innerHTML = `<div id="dup-progress">${progressHtml(0, "正在启动查重任务…")}</div>`;

    let jobId;
    try {
      const st = await api("POST", "/api/duplicates/start", { subject: subj, threshold: th });
      jobId = st.jobId;
    } catch (e) {
      body.innerHTML = '<div class="empty"><div class="big">⚠️</div>查重任务启动失败</div>';
      return;
    }

    // 轮询进度直到完成/出错
    for (let guard = 0; guard < 6000; guard += 1) {
      await sleep(300);
      let pr;
      try {
        pr = await api("GET", `/api/duplicates/progress?job=${jobId}`);
      } catch (e) { return; }
      if (pr.state === "error") {
        body.innerHTML = `<div class="empty"><div class="big">⚠️</div>查重出错：${esc(pr.error || "未知错误")}</div>`;
        return;
      }
      if (pr.state === "done") {
        const res = await api("GET", `/api/duplicates/result?job=${jobId}`);
        const data = res.result || { total: 0, pairs: [] };
        pairs = data.pairs || [];
        total = data.total || 0;
        truncated = !!data.truncated;
        textByIndex.clear();
        pairs.forEach((p) => {
          textByIndex.set(p.a.index, p.a.text);
          textByIndex.set(p.b.index, p.b.text);
        });
        picked.clear();
        expanded.clear();
        renderBody(subj, th);
        return;
      }
      // 仍在运行：更新进度条
      const el = $("#dup-progress", body);
      if (el) el.innerHTML = progressHtml(pr.percent || 0, "查重任务运行中…");
    }
    body.innerHTML = '<div class="empty">查重超时，请重试。</div>';
  }

  function pickLine(it, tag) {
    const isPicked = picked.has(it.index);
    return `
      <div class="dup-line">
        <button class="dup-pick ${isPicked ? "picked" : ""}" data-pick="${it.index}" title="${isPicked ? "取消选择删除" : "选择删除此题"}">${isPicked ? "☑" : "☐"}</button>
        <span class="dup-mini"><b>${tag}#${it.index + 1}</b> [${esc(it.label)}]　${esc(it.preview)}</span>
      </div>`;
  }

  function renderBody(subj, th) {
    const body = $("#dup-body", m.mask);
    if (!body) return;
    const maxSim = pairs.length ? pairs[0].similarity : 0;

    const selBar = `
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px">
        <span class="small muted" id="dup-sel-count">已选 <b>${picked.size}</b> 题</span>
        <button class="btn btn-sm btn-red-ghost" id="dup-del-selected" ${picked.size ? "" : "disabled"}>🗑 删除所选（移入回收站）</button>
        <span class="small muted">在每对题左侧勾选可删除该题；相同题在多个结果对中自动去重。</span>
      </div>`;

    let listHtml;
    if (pairs.length === 0) {
      listHtml = `<div class="empty"><div class="big">🎉</div>未发现相似度 ≥ ${th}% 的题目（该科目共 ${total} 题）。<br>可把阈值调低再试。</div>`;
    } else {
      listHtml = pairs.map((p, i) => {
        const isOpen = expanded.has(i);
        return `
          <div class="dup-row" data-i="${i}" style="cursor:pointer">
            <span class="dup-sim ${simClass(p.similarity)}">${p.similarity}%${p.similarity >= 100 ? " 完全相同" : ""}</span>
            <div class="dup-desc">
              ${pickLine(p.a, "A")}
              ${pickLine(p.b, "B")}
            </div>
            <span class="dup-arrow">${isOpen ? "▴" : "▾"}</span>
          </div>
          ${isOpen ? `
          <div class="dup-detail">
            <div class="dup-side"><b style="color:var(--primary)">A　#${p.a.index + 1}</b>${dupDetailHtml(p.a, "A")}</div>
            <div class="dup-side"><b style="color:var(--orange)">B　#${p.b.index + 1}</b>${dupDetailHtml(p.b, "B")}</div>
          </div>` : ""}`;
      }).join("");
      if (truncated) listHtml += `<div class="small muted" style="margin-top:8px">相似题对较多，仅展示前 ${pairs.length} 对。</div>`;
    }

    body.innerHTML = `
      <div class="small muted" style="margin-bottom:8px">查重范围：同题型内比对（单选/多选/判断/填空各自比）；选择题含选项比对，选项换顺序不影响。</div>
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:10px">
        <div class="small muted">科目共 <b>${total}</b> 题 · 找到 <b>${pairs.length}</b> 对相似题（相似度 ≥ ${th}%）
          ${pairs.length ? `· 最高 <b>${maxSim}%</b>` : ""}</div>
        <label class="small muted">阈值
          <select class="answer-input" id="dup-th" style="width:auto;padding:3px 8px">
            ${[50, 60, 70, 80, 90].map((v) => `<option value="${v}" ${v === th ? "selected" : ""}>${v}%</option>`).join("")}
          </select>
        </label>
      </div>
      ${pairs.length ? selBar : ""}
      ${listHtml}`;

    $("#dup-th", body).addEventListener("change", (e) => load(subj, Number(e.target.value)));
    $$(".dup-pick", body).forEach((btn) => btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const idx = Number(btn.dataset.pick);
      if (picked.has(idx)) picked.delete(idx); else picked.add(idx);
      renderBody(subj, th);
    }));
    $$(".dup-row", body).forEach((row) => row.addEventListener("click", (e) => {
      if (e.target.closest(".dup-pick")) return;
      const i = Number(row.dataset.i);
      if (expanded.has(i)) expanded.delete(i); else expanded.add(i);
      renderBody(subj, th);
    }));
    const delBtn = $("#dup-del-selected", body);
    if (delBtn) delBtn.addEventListener("click", async () => {
      const n = picked.size;
      if (!n) return;
      const ok = await confirmModal({
        title: "删除选中的相似题",
        message: `确定删除选中的 <b>${n}</b> 题吗？<br>删除后将移入回收站，并同步清理对应错题本记录。`,
        okText: "删除", danger: true,
      });
      if (!ok) return;
      const items = [...picked].map((idx) => ({ subject: subj, index: idx, text: textByIndex.get(idx) }));
      const res = await api("POST", "/api/questions/batch-delete", { items });
      toast(`已删除 ${res.deleted} 题（已移入回收站）${(res.skipped || []).length ? `，${res.skipped.length} 题跳过` : ""}`, "ok");
      invalidateOverview();
      await load(subj, th);   // 删后重跑查重
    });
  }

  await load(subject, threshold);
}

function openQuestionDetail(item) {
  const optsHtml = Array.isArray(item.options) && item.options.length
    ? `<div style="margin-top:10px;border-top:1px dashed var(--line);padding-top:10px"><div class="detail-grid">${item.options.map(([l, txt]) => `<span class="k">${esc(l)}.</span><span class="v">${renderRichText(txt)}</span>`).join("")}</div></div>`
    : "";
  const m = openModal(`
    <div class="modal-head"><h3>题目详情 #${item.index + 1}</h3><button class="modal-close">✕</button></div>
    <div class="modal-body">
      <div style="margin-bottom:12px;display:flex;gap:8px;align-items:center">
        ${badgeHtml(item.label)} <span class="muted small">${esc(item.subject)}</span>
      </div>
      <div class="q-text">${renderRichText(item.text)}</div>
      ${optsHtml}
      <div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--line)">
        <div class="small"><b>正确答案：</b><span style="color:var(--green);font-weight:700">${esc(ansShow(item, item.answer))}</span></div>
      </div>
    </div>
    <div class="modal-foot">
      <button class="btn btn-ghost" data-act="close">关闭</button>
      <button class="btn btn-primary" data-act="edit">编辑此题</button>
    </div>`);
  $(".modal-close", m.mask).addEventListener("click", () => m.close());
  m.mask.addEventListener("click", (e) => {
    const act = e.target && e.target.dataset && e.target.dataset.act;
    if (act === "close") m.close();
    else if (act === "edit") {
      m.close();
      openQuestionEditor(item, async () => { toast("题目已更新", "ok"); invalidateOverview(); render(); });
    }
  });
}

/* —— 录入 / 编辑弹窗（v2：六题型 + 空位 + 图片库） —— */

const Q_TYPE_NAMES = ["判断题", "单选题", "多选题", "填空题", "简答题", "计算题"];
const BLANK_RE = /【\s*\d+\s*】/g;

function countBlanks(text) {
  const ms = String(text || "").match(BLANK_RE);
  return ms ? ms.length : 0;
}

function insertAtCursor(ta, token) {
  if (!ta) return;
  const s = ta.selectionStart == null ? ta.value.length : ta.selectionStart;
  const e = ta.selectionEnd == null ? ta.value.length : ta.selectionEnd;
  ta.value = ta.value.slice(0, s) + token + ta.value.slice(e);
  ta.focus();
  const pos = s + token.length;
  ta.setSelectionRange(pos, pos);
}

function openImagePicker(targetId, onPick) {
  (async () => {
    let data;
    try { data = await api("GET", "/api/pictures"); } catch (e) { return; }
    const imgs = (data.items || []).map((it) => `
      <button type="button" class="pic-item" data-name="${esc(it.name)}" title="${esc(it.name)}">
        <img src="pictures/${encodeURI(it.name)}" loading="lazy" alt="">
        <span>${esc(it.name)}</span>
      </button>`).join("");
    const m = openModal(`
      <div class="modal-head"><h3>🖼 图片库（点击插入）</h3><button class="modal-close">✕</button></div>
      <div class="modal-body">
        ${imgs ? `<div class="pic-grid">${imgs}</div>`
          : '<div class="empty">pictures/ 目录还没有图片</div>'}
      </div>
      <div class="modal-foot"><button class="btn btn-ghost" data-act="close">关闭</button></div>`, "modal-lg");
    $(".modal-close", m.mask).addEventListener("click", () => m.close());
    m.mask.addEventListener("click", (e) => {
      const el = e.target.closest("[data-name]");
      if (el) { m.close(); onPick(el.dataset.name); }
      else if (e.target.closest('[data-act="close"]')) m.close();
    });
    if (targetId) onPick = onPick; // 兼容旧调用
  })();
}

/* 空白答案编辑行渲染 */
function blanksEditorHtml(items, n) {
  const arr = items || [];
  let rows = "";
  for (let i = 0; i < n; i++) {
    const it = arr[i] || { accept: [], group: 0 };
    const accept = (it.accept || []).join(" | ");
    rows += `
      <div class="fill-editor-row">
        <span class="fill-idx">第${i + 1}空</span>
        <input class="answer-input fe-accept" data-i="${i}" placeholder="可接受答案，多个用 | 分隔，如：4 | 四" value="${esc(accept)}" style="flex:1">
        <input class="answer-input fe-group" data-i="${i}" type="number" min="0" value="${it.group ? it.group : 0}" title="可互换组号：给可互换的空填相同组号（0=按位）" style="width:110px">
        <span class="small muted">组号(可互换)</span>
      </div>`;
  }
  return rows;
}

async function openQuestionEditor(item, onSaved) {
  const ov = await getOverview();
  const allSubjects = ov.grades.flatMap((g) => g.subjects);
  const isEdit = !!item;
  const initType = isEdit ? item.type : "判断题";
  const itemAnswer = item && item.answer;

  const subjectOptions = allSubjects.map((s) => `<option value="${esc(s.name)}" ${isEdit && s.name === item.subject ? "selected" : ""}>${esc(s.name)}</option>`).join("");
  const typeOptions = Q_TYPE_NAMES.map((t) =>
    `<option value="${t}" ${t === initType ? "selected" : ""}>${t}</option>`).join("");

  const m = openModal(`
    <div class="modal-head"><h3>${isEdit ? "编辑题目" : "录入题目（逐题导入）"}</h3><button class="modal-close">✕</button></div>
    <div class="modal-body">
      <div class="form-row">
        <div class="form-group">
          <label>科目</label>
          <select class="answer-input" id="q-subject" ${isEdit ? "disabled" : ""}>${subjectOptions}</select>
        </div>
        <div class="form-group">
          <label>题型</label>
          <select class="answer-input" id="q-type" ${isEdit ? "disabled" : ""}>${typeOptions}</select>
        </div>
      </div>
      <div class="form-group">
        <label>题干</label>
        <div style="margin-bottom:6px;display:flex;gap:6px;flex-wrap:wrap">
          <button type="button" class="btn btn-ghost q-tool-btn" data-tool="blank">＋ 插入空位</button>
          <button type="button" class="btn btn-ghost q-tool-btn" data-tool="img">🖼 插入图片</button>
        </div>
        <textarea class="answer-input" id="q-text" rows="5" placeholder="支持多行；填空请用【＋插入空位】插入编号空位；图片文件名写在文本中即可自动显示">${isEdit ? esc(item.text) : ""}</textarea>
        <div class="hint" id="q-text-hint"></div>
      </div>
      <div class="form-group" id="q-options-group" style="display:none">
        <label>选项（每行一个选项，自动编号 A/B/C…；选项文本可含图片名）</label>
        <div style="margin-bottom:6px"><button type="button" class="btn btn-ghost q-tool-btn" data-tool="optimg">🖼 在选项区插入图片行</button></div>
        <textarea class="answer-input" id="q-options" rows="4" placeholder="选项内容1&#10;选项内容2&#10;选项内容3"></textarea>
      </div>
      <div class="form-group" id="q-blanks-group" style="display:none">
        <label>填空答案（每空：可接受答案用 | 分隔；组号相同的空可互换顺序）</label>
        <div id="q-blanks"></div>
      </div>
      <div class="form-group" id="q-whole-group" style="display:none">
        <label>参考答案（整串模式：按整串判定，用于代码/运行结果类题目）</label>
        <textarea class="answer-input" id="q-whole" rows="3" placeholder="参考答案（原样输入）"></textarea>
      </div>
      <div class="form-group" id="q-answer-group">
        <label id="q-answer-label">答案</label>
        <div id="q-answer-input"></div>
        <div class="hint" id="q-tip"></div>
      </div>
    </div>
    <div class="modal-foot">
      ${isEdit ? "" : `<button class="btn btn-ghost" data-act="save-continue">保存并继续录入</button>`}
      <button class="btn btn-ghost" data-act="cancel">取消</button>
      <button class="btn btn-primary" data-act="save">${isEdit ? "保存修改" : "保存"}</button>
    </div>`, "modal-lg");

  const close = () => m.close();
  $(".modal-close", m.mask).addEventListener("click", close);

  const typeSel = $("#q-type", m.mask);
  const optGroup = $("#q-options-group", m.mask);
  const blanksGroup = $("#q-blanks-group", m.mask);
  const wholeGroup = $("#q-whole-group", m.mask);
  const ansWrap = $("#q-answer-input", m.mask);
  const ansLabel = $("#q-answer-label", m.mask);
  const tip = $("#q-tip", m.mask);
  const textTa = $("#q-text", m.mask);
  const optTa = $("#q-options", m.mask);
  const textHint = $("#q-text-hint", m.mask);

  /* 初始填入选项 */
  if (isEdit && Array.isArray(item.options)) {
    optTa.value = item.options.map(([, txt]) => txt).join("\n");
  }

  const currentOptionLines = () => optTa.value.split("\n").map((s) => s.trim()).filter(Boolean);

  /* 填空编辑器（随题干空位数刷新） */
  let blankItems = [];
  function refreshBlankRows() {
    const t = typeSel.value;
    if (t !== "填空题") return;
    const n = countBlanks(textTa.value);
    textHint.textContent = n ? `已识别 ${n} 个空位。每个空的答案填写在下方。` : "还没有空位：请把光标放到要填空的位置，点「＋插入空位」。";
    $("#q-blanks", m.mask).innerHTML = n ? blanksEditorHtml(blankItems, n) : "";
    if (n === 0) $("#q-blanks-group", m.mask).style.display = "none";
    else $("#q-blanks-group", m.mask).style.display = "";
    if (blankItems.length !== n) blankItems = Array.from({ length: n }, (_, i) => blankItems[i] || { accept: [], group: 0 });
  }

  const insertBlank = () => {
    const n = countBlanks(textTa.value);
    insertAtCursor(textTa, `【${n + 1}】`);
    refreshBlankRows();
  };

  $$(".q-tool-btn", m.mask).forEach((b) => b.addEventListener("click", () => {
    const tool = b.dataset.tool;
    if (tool === "blank") insertBlank();
    else if (tool === "img") openImagePicker(null, (name) => insertAtCursor(textTa, name));
    else if (tool === "optimg") openImagePicker(null, (name) => {
      optTa.value = optTa.value ? optTa.value.replace(/\s*$/, "") + "\n" + name : name;
      refreshAnswerUI();
    });
  }));

  function refreshAnswerUI() {
    const t = typeSel.value;
    const isChoice = t === "单选题" || t === "多选题";
    optGroup.style.display = isChoice ? "" : "none";
    wholeGroup.style.display = t === "填空题" && isEdit && item.wholeString ? "" : "none";
    blanksGroup.style.display = t === "填空题" ? "" : "none";
    $("#q-answer-group", m.mask).style.display = (t === "判断题" || t === "单选题" || t === "多选题" || t === "简答题" || t === "计算题") ? "" : "none";
    ansLabel.textContent = t === "简答题" ? "参考答案" : (t === "计算题" ? "参考答案（计算结果）" : "答案");
    const lines = isChoice ? currentOptionLines() : [];
    const letters = LETTERS.slice(0, lines.length);

    if (t === "判断题") {
      tip.textContent = "";
      ansWrap.innerHTML = `<select class="answer-input" id="q-ans" style="width:auto"><option value="正确">正确</option><option value="错误">错误</option></select>`;
    } else if (t === "单选题") {
      tip.textContent = lines.length ? `有效选项：${letters.join(" / ")}` : "请先在上方输入选项";
      ansWrap.innerHTML = `<select class="answer-input" id="q-ans" style="width:auto">${letters.map((l) => `<option value="${l}">${l}</option>`).join("")}</select>`;
    } else if (t === "多选题") {
      tip.textContent = "输入正确选项字母，如 ABD（至少 2 个）";
      ansWrap.innerHTML = `<input class="answer-input" id="q-ans" placeholder="如：ABD">`;
    } else if (t === "简答题" || t === "计算题") {
      tip.textContent = "";
      ansWrap.innerHTML = `<textarea class="answer-input" id="q-ans" rows="3" placeholder="参考答案"></textarea>`;
    }

    /* 回填已有答案 */
    if (isEdit && itemAnswer !== undefined && itemAnswer !== null) {
      if (t === "判断题") { const el = $("#q-ans", m.mask); if (el) el.value = itemAnswer === "错误" ? "错误" : "正确"; }
      else if (t === "单选题") { const el = $("#q-ans", m.mask); if (el && typeof itemAnswer === "string") el.value = itemAnswer.trim().toUpperCase(); }
      else if (t === "多选题") { const el = $("#q-ans", m.mask); if (el) el.value = typeof itemAnswer === "string" ? itemAnswer : (itemAnswer && itemAnswer.items ? "" : String(itemAnswer)); }
      else if (t === "简答题" || t === "计算题") { const el = $("#q-ans", m.mask); if (el) el.value = typeof itemAnswer === "string" ? itemAnswer : ""; }
    }
    if (t === "填空题") {
      const wholeEl = $("#q-whole", m.mask);
      if (wholeEl) wholeEl.value = (isEdit && item.wholeString && typeof itemAnswer === "string") ? itemAnswer : "";
      // 载入每空答案
      if (isEdit && !item.wholeString && itemAnswer && itemAnswer.items) {
        blankItems = (itemAnswer.items || []).map((it) => ({
          accept: (it.accept || []).slice(), group: it.group || 0,
        }));
      } else if (!isEdit) {
        blankItems = [];
      }
      refreshBlankRows();
    }
    if (t !== "填空题") textHint.textContent = t === "填空题" ? textHint.textContent : "";
  }
  typeSel.addEventListener("change", refreshAnswerUI);
  optTa.addEventListener("input", refreshAnswerUI);
  textTa.addEventListener("input", refreshBlankRows);
  refreshAnswerUI();

  function collectBlanksFromDom() {
    const rows = $$(".fill-editor-row", m.mask);
    const items = [];
    rows.forEach((row) => {
      const i = Number($(".fe-accept", row).dataset.i);
      const acceptRaw = $(".fe-accept", row).value;
      const groupRaw = Number($(".fe-group", row).value) || 0;
      const accept = acceptRaw.split("|").map((s) => s.trim()).filter(Boolean);
      const it = { accept };
      if (groupRaw > 0) it.group = groupRaw;
      items[i] = it;
    });
    // 填满空白位置
    const n = countBlanks(textTa.value);
    while (items.length < n) items.push({ accept: [] });
    return items.slice(0, n).map((it) => it || { accept: [] });
  }

  function buildPayload() {
    const subject = $("#q-subject", m.mask).value;
    const text = textTa.value.trim();
    const t = typeSel.value;
    if (!subject) throw new Error("请选择科目");
    if (!text) throw new Error("题干不能为空");

    if (t === "判断题") {
      const v = ($("#q-ans", m.mask) || {}).value === "错误" ? "错误" : "正确";
      return { subject, question: { type: "判断题", text, answer: v } };
    }
    if (t === "填空题") {
      if (isEdit && item.wholeString) {
        const whole = ($("#q-whole", m.mask) || {}).value;
        if (!whole.trim()) throw new Error("参考答案不能为空");
        return { subject, question: { type: "填空题", text, answer: { whole: true, items: [{ accept: [whole.trim()] }] } } };
      }
      const n = countBlanks(text);
      if (n === 0) throw new Error("题干里没有空位：请用「＋插入空位」在题目中插入【N】");
      const items = collectBlanksFromDom();
      if (items.some((it) => !it.accept.length)) throw new Error("每个空都要填写可接受答案");
      return { subject, question: { type: "填空题", text, answer: { items } } };
    }
    const ansEl = $("#q-ans", m.mask);
    if (!ansEl || !String(ansEl.value).trim()) throw new Error("答案不能为空");

    if (t === "单选题" || t === "多选题") {
      const lines = currentOptionLines();
      if (lines.length === 0) throw new Error("请至少输入一个选项");
      const options = lines.map((ln, i) => [LETTERS[i], ln.replace(/^[A-Za-z][.)、．．\s]+/, "").trim()]);
      if (t === "多选题" && options.length < 2) throw new Error("多选题至少需要两个选项");
      const valid = options.map(([l]) => l);
      let answer = String(ansEl.value).trim().toUpperCase().replace(/\s/g, "");
      if (t === "多选题") {
        if (answer.length < 2) throw new Error("多选题至少需要两个正确答案");
        for (const ch of answer) if (!valid.includes(ch)) throw new Error(`无效的答案选项: ${ch}`);
        if (new Set(answer.split("")).size !== answer.length) throw new Error("答案选项不能重复");
      } else {
        if (!valid.includes(answer)) throw new Error(`答案必须是 ${valid.join(" / ")} 之一`);
      }
      return { subject, question: { type: t, text, options, answer } };
    }
    if (t === "简答题" || t === "计算题") {
      return { subject, question: { type: t, text, answer: String(ansEl.value).trim() } };
    }
    throw new Error(`不支持的题型: ${t}`);
  }

  async function doSave() {
    let payload;
    try { payload = buildPayload(); } catch (e) { toast(e.message, "err"); return false; }
    if (isEdit) {
      payload.question.flag_star = !!item.flag_star;
      payload.question.flag_cross = !!item.flag_cross;
      await api("PUT", "/api/questions", { subject: payload.subject, index: item.index, question: payload.question });
    } else {
      await api("POST", "/api/questions", payload);
    }
    return true;
  }

  m.mask.addEventListener("click", async (e) => {
    const act = e.target && e.target.dataset && e.target.dataset.act;
    if (act === "cancel") { m.close(); return; }
    if (act === "save-continue") {
      if (await doSave()) {
        onSaved();
        textTa.value = "";
        optTa.value = "";
        blankItems = [];
        refreshAnswerUI();
        toast("已保存，继续录入下一题", "ok");
      }
      return;
    }
    if (act === "save") {
      if (await doSave()) { m.close(); onSaved(); }
    }
  });
}

/* ============================================================
   刷题报告
   ============================================================ */

async function renderReports(view) {
  const data = await api("GET", "/api/reports");
  const rows = data.items.length === 0
    ? `<div class="empty"><div class="big">📄</div>还没有刷题报告。<br>完成一组练习后会<strong>自动保存</strong>，或使用终端版生成的报告也会显示在这里。</div>`
    : data.items.map((r) => `
      <div class="report-item" data-name="${esc(r.name)}">
        <span class="report-icon">📄</span>
        <span class="report-name">${esc(r.name)}</span>
        <span class="report-meta">${esc(r.mtime)}<br>${r.size} 字节</span>
        <button class="btn btn-sm btn-red-ghost report-del" data-name="${esc(r.name)}" title="删除该报告">删除</button>
      </div>`).join("");

  view.innerHTML = `
    <div class="page-head"><h2>刷题报告</h2><div class="sub">共 ${data.total} 份 · 点击查看内容，删除前请确认</div></div>
    <div class="card">${rows}</div>
    <div id="report-body" style="margin-top:16px"></div>`;

  $$(".report-item", view).forEach((item) => item.addEventListener("click", async (e) => {
    if (e.target.closest(".report-del")) return;
    const name = item.dataset.name;
    const res = await api("GET", `/api/reports/${encodeURIComponent(name)}`);
    $("#report-body", view).innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <h3 style="margin:0;font-size:16px">${esc(name)}</h3>
        <button class="btn btn-sm btn-ghost" id="report-hide">收起</button>
      </div>
      <pre class="report-content">${esc(res.content)}</pre>`;
    $("#report-hide", view).addEventListener("click", () => { $("#report-body", view).innerHTML = ""; });
  }));

  $$(".report-del", view).forEach((btn) => btn.addEventListener("click", async (e) => {
    e.stopPropagation();
    const name = btn.dataset.name;
    const ok = await confirmModal({
      title: "删除报告",
      message: `确定删除报告「${esc(name)}」吗？<br>删除后不可恢复。`,
      okText: "删除", danger: true,
    });
    if (!ok) return;
    await api("DELETE", `/api/reports?name=${encodeURIComponent(name)}`);
    toast("报告已删除", "ok");
    render();
  }));
}

/* ============================================================
   批量导入（judge 转换）
   ============================================================ */

/* 进入/重置批量导入流程 */
function resetImportFlow(prefillSubject) {
  const f = {
    step: 1,                       // 1=选年级科目，2=judge+文本+预览+导入
    grade: "",
    subject: "",
    prefill: prefillSubject || "",
    judges: [],
    judgeTotal: 0,
    judgeLoading: false,
    judgeId: "",
    raw: "",
    preview: null,
    count: 0,
    busy: false,
    done: false,
    lastInserted: 0,
  };
  state.importFlow = f;
  return f;
}

async function loadJudgeList(flow) {
  flow.judgeLoading = true;
  try {
    const data = await api("GET", "/api/import/judges");
    flow.judges = data.judges || [];
    flow.judgeTotal = data.total || 0;
  } catch (e) { /* api 已提示 */ }
  flow.judgeLoading = false;
}

function gradeOfSubject(ov, subject) {
  for (const g of ov.grades) {
    if (g.subjects.some((s) => s.name === subject)) return g.name;
  }
  return "";
}

async function renderImport(view) {
  const ov = await getOverview();
  const allSubjects = ov.grades.flatMap((g) => g.subjects);
  const flow = state.importFlow || resetImportFlow(null);
  state.importFlow = flow;

  // 每次从其它页面进入批量导入界面时，自动重新读取 judge 清单（数量与文件名实时）
  if (state.routeChanged && flow.step === 2 && !flow.busy && !flow.judgeLoading) {
    await loadJudgeList(flow);
  }

  // 预填科目 -> 自动带出年级
  if (flow.prefill && !flow.subject) {
    flow.subject = flow.prefill;
    flow.grade = gradeOfSubject(ov, flow.prefill);
  }

  /* ---------- 第 1 步：选择年级与科目 ---------- */
  if (flow.step === 1) {
    const gradeOptions = ov.grades
      .map((g) => `<option value="${esc(g.name)}" ${g.name === flow.grade ? "selected" : ""}>${esc(g.name)}</option>`)
      .join("");
    const gradeSubjects = (ov.grades.find((g) => g.name === flow.grade) || { subjects: [] }).subjects;
    const subjectOptions = gradeSubjects
      .map((s) => `<option value="${esc(s.name)}" ${s.name === flow.subject ? "selected" : ""}>${esc(s.name)}（${s.questionCount}题）</option>`)
      .join("");

    view.innerHTML = `
      <div class="page-head"><h2>批量导入题目</h2>
        <div class="sub">第 1 步：选择目标年级与科目，确定后进入转换录入界面。</div></div>
      <div class="card" style="padding:24px 28px;max-width:560px">
        <div class="form-group">
          <label>年级</label>
          <select class="answer-input" id="imp-grade" style="width:100%"><option value="">请选择</option>${gradeOptions}</select>
        </div>
        <div class="form-group">
          <label>科目</label>
          <select class="answer-input" id="imp-subject" style="width:100%">
            <option value="">${gradeSubjects.length ? "请选择科目" : "（该年级暂无科目）"}</option>${subjectOptions}
          </select>
        </div>
        <div style="display:flex;gap:10px;margin-top:16px">
          <button class="btn btn-ghost" id="imp-back">返回</button>
          <button class="btn btn-primary" id="imp-next" ${flow.subject ? "" : "disabled"}>确定，进入录入界面 →</button>
        </div>
      </div>`;

    const gradeSel = $("#imp-grade", view);
    const subjSel = $("#imp-subject", view);
    const nextBtn = $("#imp-next", view);

    gradeSel.addEventListener("change", () => {
      flow.grade = gradeSel.value;
      flow.subject = "";
      render();
    });
    subjSel.addEventListener("change", () => {
      flow.subject = subjSel.value;
      nextBtn.disabled = !flow.subject;
    });
    $("#imp-back", view).addEventListener("click", () => navTo("library"));
    nextBtn.addEventListener("click", async () => {
      if (!flow.subject) { toast("请先选择科目", "info"); return; }
      flow.step = 2;
      flow.preview = null;
      flow.done = false;
      await loadJudgeList(flow);
      render();
    });
    return;
  }

  /* ---------- 第 2 步：judge + 原始文本 + 预览 + 导入 ---------- */
  const scopeGrade = flow.grade ? `【${esc(flow.grade)}】` : "";
  const judgeOptionsHtml = (flow.judgeLoading ? [] : flow.judges).map((j) =>
    `<option value="${esc(j.id)}" ${j.id === flow.judgeId ? "selected" : ""}>${esc(j.name)} —— ${esc(j.desc)}</option>`).join("");

  let previewHtml = "";
  if (flow.preview !== null) {
    if (flow.count > 0) {
      previewHtml = `
        <div class="feedback correct" style="margin-top:14px"><b>✅ 识别到 ${flow.count} 道题</b>（下方为转换后文本预览）</div>
        <pre class="report-content" style="margin-top:8px">${esc(flow.preview)}</pre>`;
    } else {
      previewHtml = `
        <div class="feedback wrong" style="margin-top:14px"><b>⚠️ 未识别到任何题目</b><br>请检查原始文本格式，或换一个转换规则再试。</div>`;
    }
  }

  view.innerHTML = `
    <div class="page-head">
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
        <div><h2>批量导入题目</h2>
          <div class="sub">第 2 步 · 目标：${scopeGrade}<b>${esc(flow.subject)}</b>（确定后可直接录入题库）</div>
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-ghost" id="imp-back2">← 重选科目</button>
        </div>
      </div>
    </div>
    <div class="card" style="padding:20px 24px">
      <div class="form-group">
        <label>转换规则（judge）—— 共 ${flow.judgeLoading ? "…读取中" : `<b>${flow.judgeTotal}</b> 个`}（自动读取 convert_tools/ 目录）</label>
        <div style="display:flex;gap:8px">
          <select class="answer-input" id="imp-judge" style="flex:1" ${flow.judgeLoading ? "disabled" : ""}>
            <option value="">${flow.judgeLoading ? "读取中…" : "请选择转换规则"}</option>${judgeOptionsHtml}
          </select>
          <button class="btn btn-ghost" id="imp-refresh" ${flow.judgeLoading ? "disabled" : ""}>⟳ 刷新</button>
        </div>
        <div class="hint">judge 文件名即显示名；判断题答案自动存为“正确/错误”，选择题字母数≥2 自动记为多选题（v2 存储为 单选题/多选题）。</div>
      </div>
      <div class="form-group">
        <label>待导入的原始文本</label>
        <textarea class="answer-input" id="imp-text" rows="10" placeholder="把考试导出的原始文本粘贴到这里（如 分数/作者/单位/题干/T/F/参考答案 格式）">${esc(flow.raw)}</textarea>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button class="btn btn-primary" id="imp-preview" ${flow.busy || flow.judgeLoading ? "disabled" : ""}>🔎 转换并预览</button>
        <button class="btn btn-green" id="imp-apply" disabled>✔ 确认导入 <span id="imp-apply-n">0</span> 题</button>
      </div>
      ${previewHtml}
    </div>`;

  const judgeSel = $("#imp-judge", view);
  const textArea = $("#imp-text", view);
  const previewBtn = $("#imp-preview", view);
  const applyBtn = $("#imp-apply", view);
  const applyN = $("#imp-apply-n", view);

  const updateApply = () => {
    if (applyN) applyN.textContent = String(flow.count);
    if (applyBtn) applyBtn.disabled = !(flow.count > 0) || flow.busy || flow.done || !judgeSel.value || !textArea.value.trim();
  };
  updateApply();

  judgeSel.addEventListener("change", () => { flow.judgeId = judgeSel.value; updateApply(); });
  textArea.addEventListener("input", () => { flow.raw = textArea.value; updateApply(); });

  $("#imp-back2", view).addEventListener("click", () => {
    flow.step = 1; flow.preview = null; flow.done = false;
    render();
  });
  $("#imp-refresh", view).addEventListener("click", async () => {
    await loadJudgeList(flow);
    flow.preview = null; flow.done = false;
    render();
  });

  previewBtn.addEventListener("click", async () => {
    const judgeId = judgeSel.value;
    const text = textArea.value;
    if (!judgeId) { toast("请先选择转换规则", "info"); return; }
    if (!text.trim()) { toast("请先粘贴原始文本", "info"); return; }
    flow.busy = true;
    previewBtn.disabled = true;
    applyBtn.disabled = true;
    try {
      const res = await api("POST", "/api/import/preview", { subject: flow.subject, judge: judgeId, text });
      flow.count = res.count || 0;
      flow.preview = res.preview || "";
      flow.judgeId = judgeId;
    } catch (e) { /* api 已提示 */ }
    flow.busy = false;
    render();
  });

  applyBtn.addEventListener("click", async () => {
    if (!(flow.count > 0)) { toast("请先转换预览", "info"); return; }
    const judgeId = judgeSel.value || flow.judgeId;
    if (!judgeId) { toast("请选择转换规则并重新预览", "info"); return; }
    flow.judgeId = judgeId;
    flow.busy = true;
    applyBtn.disabled = true;
    previewBtn.disabled = true;
    let ok = false;
    try {
      const res = await api("POST", "/api/import/apply", {
        subject: flow.subject, judge: flow.judgeId, text: flow.raw,
      });
      ok = true;
      flow.lastInserted = res.inserted || 0;
      invalidateOverview();
    } catch (e) { /* api 已提示；失败时保留 raw/preview/count 便于直接重试 */ }
    flow.busy = false;
    if (ok) {
      // 成功：自动清空本批，回到“可继续粘贴下一批”的状态（无需刷新）
      flow.raw = "";
      flow.preview = null;
      flow.count = 0;
      flow.done = false;
      toast(`已导入 ${flow.lastInserted} 道题，可直接粘贴下一批继续`, "ok");
    }
    render();
  });
}

/* ============================================================
   回收站
   ============================================================ */

async function renderRecycle(view) {
  const data = await api("GET", "/api/recycle");
  const all = data.items || [];
  state.recycleFilter = state.recycleFilter || { subject: "全部科目" };
  const f = state.recycleFilter;
  const subjects = [...new Set(all.map((i) => i.subject))].sort();

  const items = f.subject === "全部科目" ? all : all.filter((i) => i.subject === f.subject);
  const sel = new Set();

  const subjOptions = `<button class="chip ${f.subject === "全部科目" ? "active" : ""}" data-k="全部科目">全部科目 (${all.length})</button>` +
    subjects.map((s) => `<button class="chip ${f.subject === s ? "active" : ""}" data-k="${esc(s)}">${esc(s)}</button>`).join("");

  const rows = items.length === 0
    ? `<div class="empty"><div class="big">🗑</div>回收站是空的。<br>在「题库管理」或「查重结果」中删除的题目会先进这里（最多保存 500 条）。</div>`
    : items.map((r) => `
      <div class="q-row" data-id="${r.id}">
        <div class="q-row-head">
          <input type="checkbox" class="row-check" data-sel="${r.id}" title="选择">
          <span class="idx">#${r.original_index + 1}</span>
          ${badgeHtml(r.label)}
          <span class="q-subject">${esc(r.subject)}</span>
          <span class="q-preview" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(r.preview)}</span>
          <span class="muted small" style="white-space:nowrap">${esc(r.deleted_at || "")}</span>
          <div class="q-row-actions">
            <button class="btn btn-sm btn-green" data-a="restore">恢复</button>
            <button class="btn btn-sm btn-red-ghost" data-a="purge">彻底删除</button>
          </div>
        </div>
      </div>`).join("");

  view.innerHTML = `
    <div class="page-head">
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
        <div><h2>回收站</h2><div class="sub">删除的题目先到这里 · 已存 <b>${all.length}</b> / 500 条（超出自动丢弃最旧）</div></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn btn-ghost" id="re-restore-sel" disabled>↩ 恢复所选</button>
          <button class="btn btn-red-ghost" id="re-purge-sel" disabled>🗑 彻底删除所选</button>
          <button class="btn btn-red-ghost" id="re-purge-all" ${all.length ? "" : "disabled"}>清空回收站</button>
        </div>
      </div>
    </div>
    <div class="filter-chips">${subjOptions}</div>
    <div class="muted small" style="margin:0 2px 10px">当前显示 <b>${items.length}</b> 条 · 已选 <b id="re-count">0</b> 条</div>
    ${rows}`;

  const setSelUI = () => {
    const n = sel.size;
    const c = $("#re-count", view);
    if (c) c.textContent = String(n);
    const r1 = $("#re-restore-sel", view);
    const r2 = $("#re-purge-sel", view);
    if (r1) r1.disabled = n === 0;
    if (r2) r2.disabled = n === 0;
  };

  $$(".chip", view).forEach((c) => c.addEventListener("click", () => {
    f.subject = c.dataset.k;
    render();
  }));

  $$(".row-check", view).forEach((c) => c.addEventListener("change", () => {
    if (c.checked) sel.add(c.dataset.sel); else sel.delete(c.dataset.sel);
    setSelUI();
  }));

  view.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-a]");
    if (!btn) return;
    const row = btn.closest(".q-row");
    if (!row) return;
    const id = Number(row.dataset.id);
    const act = btn.dataset.a;
    if (act === "restore") {
      await api("POST", "/api/recycle/restore", { ids: [id] });
      toast("已恢复该题", "ok");
      invalidateOverview();
      render();
    } else if (act === "purge") {
      const ok = await confirmModal({ title: "彻底删除", message: "从回收站彻底删除后<b>不可恢复</b>，确定吗？", okText: "彻底删除", danger: true });
      if (ok) {
        await api("DELETE", `/api/recycle?id=${id}`);
        toast("已彻底删除", "ok");
        render();
      }
    }
  });

  $("#re-restore-sel", view).addEventListener("click", async () => {
    if (!sel.size) return;
    await api("POST", "/api/recycle/restore", { ids: [...sel].map(Number) });
    toast(`已恢复 ${sel.size} 条`, "ok");
    invalidateOverview();
    render();
  });
  $("#re-purge-sel", view).addEventListener("click", async () => {
    if (!sel.size) return;
    const ok = await confirmModal({ title: "彻底删除所选", message: `将彻底删除选中的 <b>${sel.size}</b> 条记录，不可恢复。`, okText: "彻底删除", danger: true });
    if (ok) {
      await api("DELETE", `/api/recycle?ids=${[...sel].join(",")}`);
      toast("已彻底删除", "ok");
      render();
    }
  });
  $("#re-purge-all", view).addEventListener("click", async () => {
    const ok = await confirmModal({ title: "清空回收站", message: `将彻底删除全部 <b>${all.length}</b> 条记录，不可恢复。`, okText: "清空", danger: true });
    if (ok) {
      await api("DELETE", "/api/recycle?all=1");
      toast("回收站已清空", "ok");
      render();
    }
  });
  setSelUI();
}

/* ============================================================
   设置
   ============================================================ */

async function renderSettings(view) {
  // 汇总默认记录（含各科 records），供重置摘要显示
  let total = 0, correct = 0, wrong = 0, acc = null;
  try {
    const ov = await getOverview(true);
    const subs = ov.grades.flatMap((g) => g.subjects);
    for (const s of subs) {
      const r = s.records;
      if (r) { total += r.total || 0; correct += r.correct || 0; }
    }
    wrong = total - correct;
    acc = total ? (correct / total * 100).toFixed(1) : null;
  } catch (e) { /* ignore */ }

  view.innerHTML = `
    <div class="page-head"><h2>设置</h2><div class="sub">更改即时保存到本浏览器，下次自动生效。</div></div>
    <div class="card" style="padding:20px 24px;max-width:680px">
      <div class="form-group">
        <label>答题方式（选择题）</label>
        <label class="opt" style="cursor:pointer;display:flex;align-items:center">
          <input type="radio" name="choice-mode" value="manual" ${state.settings.choiceAutoSubmit ? "" : "checked"}>
          <span class="opt-text">单选/多选：点击选项后需点「提交答案」</span>
        </label>
        <label class="opt" style="cursor:pointer;display:flex;align-items:center">
          <input type="radio" name="choice-mode" value="auto" ${state.settings.choiceAutoSubmit ? "checked" : ""}>
          <span class="opt-text">单选：点击选项即直接提交（多选题仍为点选后手动提交）</span>
        </label>
        <div class="hint">该设置仅影响刷题中的<strong>单选题</strong>；判断题/填空题/多选题不受影响。</div>
      </div>
    </div>
    <div class="card" style="padding:20px 24px;max-width:680px;margin-top:14px">
      <div class="form-group" style="margin-bottom:6px">
        <label>刷题记录（正确率统计）</label>
        <div class="small muted">当前共答 <b>${total}</b> 题 · 答对 <span style="color:var(--green);font-weight:700">${correct}</span> · 答错 <span style="color:var(--red);font-weight:700">${wrong}</span> · 总正确率 <b>${acc === null ? "—" : acc + "%"}</b></div>
        <div class="hint">记录在首页每科卡片可见；账号功能将在后续版本接入（当前为公共记录）。</div>
      </div>
      <button class="btn btn-red-ghost" id="btn-reset-records" ${total ? "" : "disabled"}>🗑 重置刷题记录</button>
    </div>
    <div class="card" style="padding:20px 24px;max-width:680px;margin-top:14px">
      <div class="form-group">
        <label>数据存档</label>
        <div class="small muted">把当前全部题库、错题本、标记、正确率与考试记录、刷题进度打包成 zip。把文件交给新安装的程序，用「导入存档」即可直接恢复进度。</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
          <button class="btn btn-primary" id="btn-archive-save">📦 保存并下载存档</button>
          <input type="file" id="archive-file" accept=".zip,application/zip" style="display:none">
          <button class="btn btn-ghost" id="btn-archive-import">📥 导入存档</button>
        </div>
        <div class="hint" id="archive-last">尚未生成存档。导入前会先自动备份当前数据到 backups/。</div>
      </div>
    </div>
    <div class="card" style="padding:20px 24px;max-width:680px;margin-top:14px">
      <div class="form-group">
        <label>题库更新（远程 GitHub）</label>
        <div class="small muted">题库由维护者发布在 GitHub 仓库。点「检查更新」联网对比远程清单；有变化时点「立即更新」下载。更新前会自动把旧题库备份到 <b>backups/</b>，更新后页面自动刷新。</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
          <button class="btn btn-ghost" id="btn-bank-check">🔍 检查更新</button>
          <button class="btn btn-primary" id="btn-bank-update" disabled>⬇️ 立即更新</button>
        </div>
        <div class="hint" id="bank-status">尚未检查。用 git clone 安装的会自动识别仓库；用 zip 安装的请先按《接入GitHub完整流程.md》配置远程仓库。</div>
      </div>
    </div>`;

  $$('input[name="choice-mode"]', view).forEach((r) => r.addEventListener("change", () => {
    state.settings.choiceAutoSubmit = (r.value === "auto");
    saveSettings();
    toast(state.settings.choiceAutoSubmit ? "已开启：单选题点击即提交" : "已关闭：单选题手动提交", "ok");
  }));

  $("#btn-reset-records", view).addEventListener("click", async () => {
    const ok = await confirmModal({
      title: "重置刷题记录",
      message: "将清空全部<strong>正确率刷题记录</strong>（首页各科正确率归零），此操作不可恢复。确定重置吗？",
      okText: "重置", danger: true,
    });
    if (!ok) return;
    await api("POST", "/api/records/reset", {});
    toast("刷题记录已重置", "ok");
    invalidateOverview();
    render();
  });

  /* ---------- 数据存档 ---------- */
  const lastEl = $("#archive-last", view);
  $("#btn-archive-save", view).addEventListener("click", async () => {
    const res = await api("GET", "/api/archive/save");
    if (lastEl) lastEl.textContent = `已生成：${res.name}（含 ${res.files} 个数据文件 / ${res.questions} 题，保存于 backups/）`;
    toast("存档已生成，正在下载", "ok");
    const a = document.createElement("a");
    a.href = `/api/archive/download?name=${encodeURIComponent(res.name)}`;
    a.download = res.name;
    document.body.appendChild(a);
    a.click();
    a.remove();
  });

  const fileInput = $("#archive-file", view);
  $("#btn-archive-import", view).addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    const file = fileInput.files && fileInput.files[0];
    fileInput.value = "";
    if (!file) return;
    const ok = await confirmModal({
      title: "导入存档",
      message: `将用「${esc(file.name)}」<strong>覆盖</strong>当前题库/记录/进度。<br>导入前服务端会先自动备份当前数据到 backups/（可回退）。继续吗？`,
      okText: "导入并覆盖", danger: true,
    });
    if (!ok) return;
    try {
      const resp = await fetch("/api/archive/restore", { method: "POST", body: file });
      let data = null;
      try { data = await resp.json(); } catch (e) { /* 非 JSON */ }
      if (!resp.ok || (data && data.ok === false)) {
        toast((data && data.error) || `导入失败 (${resp.status})`, "err");
        return;
      }
      toast(`导入成功：${data.restored.length} 个文件 / ${data.questions} 题（原数据备份：${data.backup}）`, "ok");
      invalidateOverview();
      setTimeout(() => location.reload(), 1300);
    } catch (e) {
      toast("网络错误：导入失败", "err");
    }
  });

  /* ---------- 题库更新（远程 GitHub） ---------- */
  const bankStatus = $("#bank-status", view);
  const btnCheck = $("#btn-bank-check", view);
  const btnUpdate = $("#btn-bank-update", view);

  async function bankDoUpdate() {
    btnUpdate.disabled = true;
    bankStatus.textContent = "正在下载并更新题库…（需要联网，请稍候）";
    try {
      const r = await api("POST", "/api/bank/update");
      if (!r.ok) {
        bankStatus.innerHTML = `✗ ${esc(r.error || r.summary || "更新失败")}`;
        return;
      }
      bankStatus.innerHTML = `✓ ${esc(r.summary)}${r.backup ? `（旧文件已备份到 backups/${esc(r.backup)}）` : ""}`;
      toast("题库更新完成，页面即将刷新", "ok");
      setTimeout(() => location.reload(), 1500);
    } catch (e) {
      bankStatus.textContent = "网络错误：更新失败";
    } finally {
      btnUpdate.disabled = false;
    }
  }

  btnUpdate.addEventListener("click", bankDoUpdate);

  btnCheck.addEventListener("click", async () => {
    btnCheck.disabled = true;
    btnUpdate.disabled = true;
    bankStatus.textContent = "正在检查更新…（需要联网，请稍候）";
    try {
      const info = await api("GET", "/api/bank/info");
      if (!info.configured) {
        bankStatus.innerHTML = `⚠️ 未配置远程仓库。<br>${esc((info.error || "").replace(/\n/g, "<br>"))}`;
        return;
      }
      const r = await api("GET", "/api/bank/check");
      if (!r.ok) {
        bankStatus.innerHTML = `✗ ${esc(r.error || r.summary || "检查失败")}`;
        return;
      }
      bankStatus.innerHTML = `远程仓库：<a href="${esc(r.remote.url)}" target="_blank" rel="noopener">${esc(r.remote.url)}</a>（分支 ${esc(r.remote.branch)}）`;
      if (r.has_updates) {
        bankStatus.innerHTML += `<br>发现更新：${esc(r.summary)}`;
        btnUpdate.disabled = false;
      } else {
        bankStatus.innerHTML += `<br>✓ ${esc(r.summary)}`;
      }
    } catch (e) {
      bankStatus.textContent = "网络错误：检查失败";
    } finally {
      btnCheck.disabled = false;
    }
  });
}

/* ============================================================
   模拟考试
   ============================================================ */

async function openExam(subject) {
  let res;
  try {
    res = await api("POST", "/api/exams/build", { subject });
  } catch (e) { return; }
  const items = res.items || [];
  if (!items.length) { toast("该科目没有可考的题目", "info"); return; }
  state.exam = {
    subject, items,
    stage: "intro",   // intro -> run -> result
    pos: 0,
    total: items.length,
    answered: 0,
    correct: 0,
    perType: {},
    finished: false,
    saved: false,
    lastScore: null,
  };
  navTo("exam");
}

function examPerType(ex) {
  const m = {};
  for (const it of ex.items) {
    const k = it.label || it.type;
    m[k] = m[k] || { total: 0, correct: 0 };
    m[k].total += 1;
  }
  return m;
}

async function renderExamRoute(view) {
  const ex = state.exam;
  if (!ex) {
    view.innerHTML = `<div class="empty"><div class="big">📝</div>当前没有模拟考试会话。<br><button class="btn btn-primary" onclick="location.hash='#/home'">返回首页选择科目</button></div>`;
    return;
  }
  if (ex.stage === "intro") {
    const comp = examPerType(ex);
    const rows = Object.entries(comp).map(([label, c]) => `
      <tr><td>${esc(label)}</td><td>${c.total}</td></tr>`).join("");
    view.innerHTML = `
      <div class="page-head"><h2>模拟考试 · ${esc(ex.subject)}</h2>
        <div class="sub">共 ${ex.total} 题 · 抽题权重：未考过 > 错题本 > 普通（配置见 exam_config.py）</div></div>
      <div class="card" style="padding:20px 24px;max-width:560px">
        <table class="rec-table"><thead><tr><th>题型</th><th>题数</th></tr></thead><tbody>${rows}</tbody></table>
        <div style="display:flex;gap:10px;margin-top:16px;flex-wrap:wrap">
          <button class="btn btn-primary" id="exam-start">开始考试</button>
          <button class="btn btn-ghost" id="exam-cancel">返回</button>
        </div>
      </div>`;
    $("#exam-start", view).addEventListener("click", () => { ex.stage = "run"; render(); });
    $("#exam-cancel", view).addEventListener("click", () => { state.exam = null; navTo("home"); });
    return;
  }
  if (ex.stage === "result") {
    if (!ex.saved && ex.answered > 0) {
      ex.saved = true;
      try { await api("POST", "/api/exams/save", { subject: ex.subject, score: ex.lastScore }); } catch (e) { /* api 已提示 */ }
    }
    const comp = examPerType(ex);
    const rows = Object.entries(comp).map(([label, c]) => {
      const st = ex.perType[label] || { correct: 0 };
      const wrong = c.total - (st.correct || 0);
      return `<tr><td>${esc(label)}</td><td>${c.total}</td><td style="color:var(--green)">${st.correct || 0}</td><td style="color:var(--red)">${wrong}</td></tr>`;
    }).join("");
    view.innerHTML = `
      <div class="page-head"><h2>模拟考试结果 · ${esc(ex.subject)}</h2></div>
      <div class="card" style="padding:22px 26px;max-width:620px">
        <div style="text-align:center;padding:6px 0 14px">
          <div style="font-size:52px;font-weight:800;color:${ex.lastScore >= 60 ? "var(--green)" : "var(--orange)"}">${ex.lastScore} 分</div>
          <div class="small muted">已答 ${ex.answered} / ${ex.total} 题 · 答对 ${ex.correct} 题</div>
        </div>
        ${ex.saved ? '<div class="feedback correct">本次成绩已计入考试记录（最近10次均分参与通过率）。</div>' : ""}
        <table class="rec-table"><thead><tr><th>题型</th><th>题数</th><th>答对</th><th>答错</th></tr></thead><tbody>${rows}</tbody></table>
        <div style="display:flex;gap:10px;margin-top:16px;flex-wrap:wrap">
          <button class="btn btn-primary" id="exam-again">再考一次</button>
          <button class="btn btn-ghost" id="exam-home">返回首页</button>
        </div>
      </div>`;
    $("#exam-again", view).addEventListener("click", () => { state.exam = null; openExam(ex.subject); });
    $("#exam-home", view).addEventListener("click", () => { state.exam = null; invalidateOverview(); navTo("home"); });
    return;
  }

  /* 作答中 */
  const q = ex.items[ex.pos];
  const idx = ex.pos + 1;
  view.innerHTML = `
    <div class="practice-bar">
      <span class="badge badge-plain">模拟考试</span>
      <span class="small muted">${esc(ex.subject)}</span>
      <div class="progress-wrap">
        <div class="progress-track"><div class="progress-fill" style="width:${Math.round(ex.pos / ex.total * 100)}%"></div></div>
        <div class="progress-lbl">第 ${idx} / ${ex.total} 题</div>
      </div>
      <button class="btn btn-sm btn-red-ghost" id="exam-finish">交卷</button>
    </div>
    <div class="card q-card">
      <div class="q-head">${badgeHtml(q.label || q.type)}<span class="q-subject">${esc(q.subject)}</span><span class="q-count">题库第 ${q.index + 1} 题</span></div>
      <div class="q-text">${questionBodyHtml(q)}</div>
      <div id="exam-answer-area"></div>
    </div>`;
  buildExamAnswerArea(view, ex, q);
  $("#exam-finish", view).addEventListener("click", () => { finishExam(ex); });
}

function buildExamAnswerArea(view, ex, q) {
  const area = $("#exam-answer-area", view);

  const record = (correct, count = true) => {
    if (count) ex.answered += 1;
    if (correct) ex.correct += 1;
    const st = ex.perType[q.label] || (ex.perType[q.label] = { correct: 0 });
    if (correct) st.correct += 1;
  };
  const advance = async () => {
    if (ex.pos + 1 >= ex.total) { ex.pos += 1; finishExam(ex); }
    else { ex.pos += 1; render(); }
  };
  const submitAuto = async (ans) => {
    const data = await api("POST", "/api/answer", { subject: q.subject, index: q.index, answer: ans, mode: "all", exam: true });
    if (data.auto === false) return;
    record(data.correct);
    advance();
  };

  if (q.type === "判断题") {
    area.innerHTML = `<div class="tf-buttons">
      <button class="tf-btn t" data-v="正确">✓ 正确</button>
      <button class="tf-btn f" data-v="错误">✗ 错误</button></div>`;
    $$(".tf-btn", area).forEach((b) => b.addEventListener("click", () => submitAuto(b.dataset.v)));
    return;
  }

  if (q.type === "单选题" || q.type === "多选题") {
    const single = q.type === "单选题";
    const opts = (q.options || []).map(([letter, text]) => `
      <label class="opt" data-letter="${letter}"><span class="opt-key">${letter}</span><span class="opt-text">${renderRichText(text)}</span></label>`).join("");
    area.innerHTML = `<div class="opt-list" id="opt-list">${opts}</div>
      <button class="btn btn-primary" id="exam-choice-submit" disabled>提交答案</button>`;
    const list = $("#opt-list", area);
    const submit = $("#exam-choice-submit", area);
    const sel = new Set();
    const refresh = () => { submit.disabled = single ? sel.size !== 1 : sel.size < 1; };
    $$(".opt", list).forEach((o) => o.addEventListener("click", () => {
      const letter = o.dataset.letter;
      if (single) { sel.clear(); sel.add(letter); $$(".opt", list).forEach((x) => x.classList.toggle("selected", x.dataset.letter === letter)); }
      else if (sel.has(letter)) { sel.delete(letter); o.classList.remove("selected"); }
      else { sel.add(letter); o.classList.add("selected"); }
      refresh();
    }));
    submit.addEventListener("click", () => {
      const ans = LETTERS.filter((l) => sel.has(l)).join("");
      if (ans) submitAuto(ans);
    });
    return;
  }

  if (q.type === "填空题") {
    if (q.wholeString) {
      area.innerHTML = `<input class="answer-input" id="exam-fill" placeholder="请输入完整答案" autocomplete="off">
        <button class="btn btn-primary" id="exam-text-submit">提交答案</button>`;
      $("#exam-text-submit", area).addEventListener("click", () => {
        const v = $("#exam-fill", area).value.trim();
        if (v) submitAuto(v);
      });
      $("#exam-fill", area).addEventListener("keydown", (e) => { if (e.key === "Enter") { const v = e.target.value.trim(); if (v) submitAuto(v); } });
    } else {
      const n = q.blankCount || 1;
      let boxes = "";
      for (let i = 1; i <= n; i++) boxes += `
        <div class="fill-row"><span class="fill-idx">第${i}空</span>
        <input class="answer-input" id="exam-blank-${i}" placeholder="填写答案" autocomplete="off" style="flex:1"></div>`;
      area.innerHTML = `<div class="fill-list">${boxes}</div>
        <button class="btn btn-primary" id="exam-fill-submit" style="margin-top:8px">提交答案</button>`;
      const doSubmit = () => {
        const vals = [];
        for (let i = 1; i <= n; i++) vals.push($(`#exam-blank-${i}`, area).value.trim());
        if (vals.every((v) => v === "")) { toast("请至少填写一个空", "info"); return; }
        submitAuto(vals);
      };
      $("#exam-fill-submit", area).addEventListener("click", doSubmit);
      $$("input", area).forEach((el) => el.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); doSubmit(); } }));
    }
    return;
  }

  if (q.type === "计算题") {
    area.innerHTML = `<input class="answer-input" id="exam-fill" placeholder="请输入计算结果" autocomplete="off">
      <button class="btn btn-primary" id="exam-text-submit">提交答案</button>`;
    $("#exam-text-submit", area).addEventListener("click", () => {
      const v = $("#exam-fill", area).value.trim();
      if (v) submitAuto(v);
    });
    $("#exam-fill", area).addEventListener("keydown", (e) => { if (e.key === "Enter") { const v = e.target.value.trim(); if (v) submitAuto(v); } });
    return;
  }

  if (q.type === "简答题") {
    area.innerHTML = `<textarea class="answer-input" id="exam-essay" rows="4" placeholder="输入你的答案（支持多行）…"></textarea>
      <button class="btn btn-primary" id="exam-essay-submit">提交答案</button>`;
    $("#exam-essay-submit", area).addEventListener("click", async () => {
      const v = $("#exam-essay", area).value.trim();
      if (!v) { toast("请输入答案", "info"); return; }
      let data;
      try {
        data = await api("POST", "/api/answer", { subject: q.subject, index: q.index, answer: v, mode: "all", exam: true });
      } catch (e) { return; }
      $$("button,input,textarea", area).forEach((el) => { el.disabled = true; });
      area.insertAdjacentHTML("beforeend", `
        <div class="feedback neutral" style="margin-top:10px">
          <div class="fb-line">参考答案：${esc(data.answer || "（无）")}</div>
          <div class="hint" style="margin:6px 0">请自评：</div>
          <div style="display:flex;gap:8px">
            <button class="btn btn-primary" id="exam-self-y">答对 ✓</button>
            <button class="btn btn-ghost" id="exam-self-n">答错 ✗</button>
            <button class="btn btn-ghost" id="exam-self-skip">跳过不计</button>
          </div>
        </div>`);
      const decide = async (selfCorrect) => {
        if (selfCorrect !== null) {
          try {
            await api("POST", "/api/answer/self", { subject: q.subject, index: q.index, answer: v, selfCorrect, mode: "all", exam: true });
          } catch (e) { return; }
          record(selfCorrect);
        }
        advance();
      };
      $("#exam-self-y", view).addEventListener("click", () => decide(true));
      $("#exam-self-n", view).addEventListener("click", () => decide(false));
      $("#exam-self-skip", view).addEventListener("click", () => decide(null));
    });
    return;
  }

  // 兜底文本输入
  area.innerHTML = `<input class="answer-input" id="exam-fill" placeholder="请输入答案" autocomplete="off">
    <button class="btn btn-primary" id="exam-text-submit">提交答案</button>`;
  $("#exam-text-submit", area).addEventListener("click", () => {
    const v = $("#exam-fill", area).value.trim();
    if (v) submitAuto(v);
  });
}

function finishExam(ex) {
  if (ex.finished) return;
  ex.finished = true;
  const score = ex.answered ? Math.round((ex.correct / ex.answered) * 1000) / 10 : 0;
  ex.lastScore = score;
  ex.stage = "result";
  render();
}



function renderHelp(view) {
  view.innerHTML = `
    <div class="page-head"><h2>使用说明</h2></div>
    <div class="card" style="padding:22px 26px">
      <div class="help-block">
        <h3>📖 与终端版的关系</h3>
        <p>网页版与终端版共用同一套题库数据（<code>data/</code>）、错题本与刷题进度，<b>数据完全互通</b>：网页版做错的题会进入错题本，终端版「刷错题」时同样能看到。</p>
      </div>
      <div class="help-block">
        <h3>🎯 开始刷题</h3>
        <ul>
          <li>在<b>仪表盘</b>点击科目卡片的「开始刷题」，或点顶部「开始刷题」选择范围与模式。</li>
          <li>支持：刷全部题目、按题型（判断/选择/填空）、仅错题复习、全部科目混合刷题；计算题自动判分、简答题作答后自评。</li>
          <li>每题即时判定对错；答错的自动记入错题本；错题复习中答对会自动移出错题本。</li>
          <li>中途点「退出并保存进度」，之后通过「继续答题」接着刷（终端版也能继续同一份进度）。</li>
        </ul>
      </div>
      <div class="help-block">
        <h3>🗂 题库管理 / 📥 批量导入</h3>
        <ul>
          <li>「题库管理」：左侧选科目（或「全部科目」跨科目搜索），可按题型过滤、搜索关键词；「＋录入题目」逐题录入。</li>
          <li>「批量导入」：选年级→科目→选转换规则（judge，数量与文件名自动读取 <code>convert_tools/</code> 目录）→ 粘贴原始文本 → 预览识别题数与转换结果 → 确认后直接入库。</li>
          <li>判断题答案自动存为「正确/错误」；选择题答案字母 ≥2 记为多选题。</li>
          <li>删除题目会同步清理该题在错题本中的记录（与终端版一致）。</li>
          <li>「题目查重」：同一题型内两两比对（判断/单选/多选/填空各自比，跨题型不比）；选择题同时比对选项，选项顺序不同不影响查重。</li>
        </ul>
      </div>
      <div class="help-block">
        <h3>🖥 终端版批量导入</h3>
        <p>终端主菜单选「批量导入题目（judge 转换）」：先把原始文本保存到 <code>convert_tools/text.txt</code>，再选 judge，程序打印识别题数并把结果写入 <code>convert_tools/text_converted.txt</code>（不自动入库）。</p>
      </div>
      <div class="help-block">
        <h3>📄 刷题报告</h3>
        <p>每组刷题完成后会<b>自动保存</b>并弹出报告；报告写入 <code>reports/</code> 目录（与终端版同目录），可在「刷题报告」页查看或删除。</p>
      </div>
      <div class="help-block">
        <h3>🖼 图片题目</h3>
        <p>题干中的 <code>1.png</code> 等文件名会自动从 <code>pictures/</code> 目录加载图片显示。</p>
      </div>
    </div>`;
}

/* ============================================================
   启动
   ============================================================ */

window.addEventListener("hashchange", () => { render(); });
window.addEventListener("DOMContentLoaded", () => { loadSettings(); render(); });

/* ⭐/❌ 题目标记（全局点击委托，题库管理行与刷题页通用） */
document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-flag]");
  if (btn) { e.preventDefault(); toggleQuestionFlag(btn); }
});
