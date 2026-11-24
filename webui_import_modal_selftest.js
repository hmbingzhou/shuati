/* 回归测试：导入题目弹窗的「AI 解析」必须可选
   背景：合并后 AI 选项曾被渲染成 disabled，用户填了密钥也点不中。
   运行：node webui_import_modal_selftest.js */
"use strict";
const fs = require("fs");
const path = require("path");

let fails = 0;
function check(name, cond, detail) {
  console.log((cond ? "[ok] " : "[FAIL] ") + name + (cond ? "" : "  " + detail));
  if (!cond) fails++;
}

const src = fs.readFileSync(path.join(__dirname, "webui", "app.js"), "utf8");

/* 1) AI 选项不能带 disabled */
const aiRadioLine = src.split("\n").find((l) => l.includes('name="im-engine" value="ai"')) || "";
check("AI 选项存在", aiRadioLine.length > 0, aiRadioLine);
check("AI 选项没有 disabled 属性", !/disabled/.test(aiRadioLine), aiRadioLine.trim());

/* 2) 密钥输入框变化时放开/勾选 AI */
check("密钥输入有 input 监听", /#im-key", m\.mask\)\.addEventListener\("input"/.test(src));
const keyInputBlock = src.slice(src.indexOf('#im-key", m.mask).addEventListener("input"'),
                               src.indexOf('#im-key", m.mask).addEventListener("input"') + 700);
check("打字后自动勾选 AI", /aiRadio\.checked = true/.test(keyInputBlock), keyInputBlock.slice(0, 200));

/* 3) 解析时若无密钥要引导用户去填，而不是静默失败 */
const parseBlock = src.slice(src.indexOf('parseBtn.addEventListener("click"'));
check("无密钥时展开密钥设置区", /im-key-box/.test(parseBlock.slice(0, 900)), parseBlock.slice(0, 300));
check("无密钥时提示文案明确", /请先填写 DeepSeek 密钥|需要 DeepSeek 密钥/.test(parseBlock.slice(0, 900)));

/* 4) 旧的「清理逻辑」不能把 AI 置为 disabled */
check("清除密钥时不 disable AI 选项", !/aiRadio\.disabled = true/.test(src));

/* 5) 合并后只剩一个入口 */
check("只保留 openImportModal", src.includes("function openImportModal") || src.includes("async function openImportModal"));
check("旧的 openAiParseModal 已移除", !src.includes("function openAiParseModal"));
check("旧的 openFileImportModal 已移除", !src.includes("function openFileImportModal"));
check("题库页只有一个导入按钮", (src.match(/id="btn-import-modal"/g) || []).length === 1);

/* 6) 两个来源都在同一个弹窗里 */
check("有「粘贴文本」标签", src.includes('id="im-src-text"'));
check("有「上传文件」标签", src.includes('id="im-src-file"'));
check("文件上传带 engine 参数", /import\/file\?name=.*engine=\$\{eng\}/.test(src));
check("文本解析带 engine 参数", /\/api\/ai\/parse", \{[^}]*engine/.test(src));

console.log("\n" + (fails ? `失败 ${fails} 项` : "导入题目弹窗回归全部通过 ✔"));
process.exit(fails ? 1 : 0);
